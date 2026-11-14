"""Exploración guiada (Fase 20, ADR-037) e investigación (Fase 25, ADR-043): une la cola, la
comprensión, el motor `explore-v1`/`explore-v2` y la IA.

Al publicarse la comprensión de una carga se encola un trabajo `exploration` que fija la
comprensión, el perfil (aditividad) y la tabla. Siempre se ejecuta: sin IA investiga con el plan
de reglas. Desde la Fase 25 las cargas nuevas usan `exploration.explore@2` (`investigation-v2`):
plan, árbol de investigaciones secundarias, evidencias, clasificación y control (pausar,
cancelar, reanudar y volver a investigar). El artefacto conserva el formato de `explore-v1`
(resultados y propuestas), así que el dashboard y el informe lo leen igual.
"""

import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4, uuid5

from sqlalchemy.orm import Session

from dataflow.modules.comprehension.contracts import Comprehension
from dataflow.modules.comprehension.domain import classify
from dataflow.modules.copilot.application import CopilotService
from dataflow.modules.copilot.contracts import CallRecord, ConsultaIA
from dataflow.modules.copilot.exploration import (
    JUDGE_ID,
    JUDGE_VERSION,
    PROPOSE_ID,
    PROPOSE_VERSION,
    judge_context,
    judge_results,
    propose_context,
    propose_queries,
)
from dataflow.modules.copilot.infrastructure import SQLCopilotRepository
from dataflow.modules.datasets.public import Datasets, ObjectStore, StoredObject
from dataflow.modules.executions.public import (
    Artifact,
    ArtifactKind,
    ArtifactOutput,
    Execution,
    Executions,
    Lease,
    PlanRevision,
    PlanStepSpec,
    ProcessingConfig,
    StepInput,
    StepResult,
)
from dataflow.modules.exploration.contracts import (
    ControlSource,
    Exploration,
    ExplorationLimits,
    ExplorationScope,
    ExplorationView,
    ExploreProposal,
    ExploreQuery,
    ExploreResult,
    InvestigationConsumption,
    InvestigationHistory,
    InvestigationNode,
    InvestigationRun,
    RawQuery,
)
from dataflow.modules.exploration.domain import (
    KINDS,
    Catalog,
    additive_columns,
    clean_reason,
    rule_queries,
    validate,
)
from dataflow.modules.exploration.engine import compute, row_count
from dataflow.modules.exploration.infrastructure import SQLInvestigationControls
from dataflow.modules.exploration.investigator import (
    Investigator,
    JudgeReply,
    Verdict,
    plan_nodes,
)
from dataflow.modules.exploration.plan import (
    ai_draft,
    projected,
    proposals,
    rule_plan,
    target_words,
)
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.modules.understanding.contracts import DatasetProfile
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError

STEP = "exploration.explore"
RULES_BY_VERSION = {
    2: "investigation-v2",
    3: "investigation-v3",
    4: "investigation-v4",
}
VERSION = 4  # Fase 29: las cargas nuevas se investigan con `investigation-v4` (explore-v4)
Trigger = Literal["load", "feedback", "restart", "resume"]


def stored(item: Artifact) -> dict[str, object]:
    return {
        "artifact_id": str(item.id),
        "key": item.content.key,
        "sha256": item.content.sha256,
        "byte_size": item.content.byte_size,
    }


def reference(item: dict[str, Any]) -> StoredObject:
    return StoredObject(str(item["key"]), str(item["sha256"]), int(item["byte_size"]))


def enqueue_exploration(
    executions: Executions,
    lease: Lease,
    comprehension: Artifact,
    config: ProcessingConfig,
) -> None:
    run = lease.execution
    assert run.plan and run.input_artifact_id
    given = run.plan.content["input"]
    profile = executions.artifact(lease.owner_id, run.input_artifact_id)
    key = uuid5(lease.execution_id, "exploration@1")
    fingerprint = digest(
        "exploration_request",
        {
            "comprehension_sha256": comprehension.content.sha256,
            "table_sha256": given["table_sha256"],
            "operation": f"{STEP}@1",
        },
    )
    if executions.find_request(lease.owner_id, run.project_id, "exploration", key, fingerprint):
        return
    content = {
        "objective": None,
        "input": {
            "kind": "exploration",
            "alias": "source",
            "version_id": given["version_id"],
            "version_content_sha256": given["version_content_sha256"],
            "artifact_id": str(comprehension.id),
            "artifact_sha256": comprehension.content.sha256,
            "producer_execution_id": str(comprehension.execution_id),
            "profile": stored(profile),
            "table": {
                "artifact_id": given["table_artifact_id"],
                "key": given["table_key"],
                "sha256": given["table_sha256"],
                "byte_size": given["table_byte_size"],
            },
        },
        "steps": [
            {
                "id": "explore",
                "operation": STEP,
                "version": VERSION,
                "input": {"kind": "input", "alias": "source"},
                "parameters": {"limits": ExplorationLimits().model_dump(mode="json")},
            }
        ],
        # Llamadas facturables: un solo intento.
        "config": config.model_copy(update={"max_attempts": 1}).model_dump(),
    }
    plan = PlanRevision(
        uuid4(), uuid4(), 1, content, digest("plan", content), lease.owner_id, datetime.now(UTC)
    )
    executions.enqueue_followup(
        lease.owner_id,
        run.project_id,
        lease.version_id,
        key,
        fingerprint,
        plan,
        str(lease.execution_id),
        comprehension.id,
        comprehension.content.sha256,
        kind="exploration",
    )


def with_verdicts(comprehension: Comprehension, verdicts: dict[str, Any]) -> Comprehension:
    """La comprensión con las valoraciones vigentes encima (y su estado recalculado)."""
    if not verdicts:
        return comprehension
    return comprehension.model_copy(
        update={
            "relationships": [
                classify(r.model_copy(update={"verdict": verdicts.get(r.key, r.verdict)}))
                for r in comprehension.relationships
            ]
        }
    )


def request_exploration_update(
    executions: Executions, owner: UUID, version: UUID, verdicts: dict[str, str]
) -> Execution | None:
    """Fase 24 (ADR-041): otra exploración de la versión con las valoraciones vigentes de las
    relaciones; al publicarse se rehacen el dashboard y el informe. Sin exploración previa, o si
    la última ya usa esas valoraciones, no hace nada. Lo anterior se conserva."""
    runs = [r for r in executions.for_version(owner, version) if r.kind == "exploration"]
    if not runs:
        return None
    base = runs[0]
    assert base.plan and base.input_artifact_id and base.input_artifact_sha256
    given = base.plan.content["input"]
    snapshot = sorted([key, verdict] for key, verdict in verdicts.items())
    if given.get("verdicts", []) == snapshot:
        return None
    content = {
        **base.plan.content,
        "input": {**{k: v for k, v in given.items() if k != "resume"}, "verdicts": snapshot},
        "trigger": "feedback",
    }
    fingerprint = digest(
        "exploration_update",
        {"base_sha256": base.plan.content_sha256, "verdicts": snapshot, "count": len(runs)},
    )
    key = uuid5(version, f"exploration-update:{len(runs)}:{fingerprint}")
    if executions.find_request(owner, base.project_id, "exploration", key, fingerprint):
        return None
    plan = PlanRevision(
        uuid4(), uuid4(), 1, content, digest("plan", content), owner, datetime.now(UTC)
    )
    return executions.enqueue_followup(
        owner,
        base.project_id,
        version,
        key,
        fingerprint,
        plan,
        str(uuid5(version, fingerprint)),  # correlación (36 caracteres)
        base.input_artifact_id,
        base.input_artifact_sha256,
        kind="exploration",
    )


def request_investigation(
    executions: Executions,
    owner: UUID,
    version: UUID,
    trigger: Literal["restart", "resume"],
    resume: Artifact | None = None,
) -> Execution:
    """Fase 25: volver a investigar la versión (con la misma comprensión) o reanudar la
    investigación pausada desde su artefacto. Siempre con `investigation-v2`; lo anterior se
    conserva en el historial."""
    runs = [r for r in executions.for_version(owner, version) if r.kind == "exploration"]
    base = runs[0]
    assert base.plan and base.input_artifact_id and base.input_artifact_sha256
    given = {k: v for k, v in base.plan.content["input"].items() if k != "resume"}
    if resume is not None:
        given["resume"] = {"execution_id": str(resume.execution_id), **stored(resume)}
    step = {**base.plan.content["steps"][0], "version": VERSION}
    step["parameters"] = {"limits": ExplorationLimits().model_dump(mode="json")}
    content = {**base.plan.content, "input": given, "steps": [step], "trigger": trigger}
    fingerprint = digest(
        "investigation_request",
        {"base_sha256": base.plan.content_sha256, "trigger": trigger, "count": len(runs)},
    )
    key = uuid5(version, f"investigation-{trigger}:{len(runs)}:{fingerprint}")
    plan = PlanRevision(
        uuid4(), uuid4(), 1, content, digest("plan", content), owner, datetime.now(UTC)
    )
    return executions.enqueue_followup(
        owner,
        base.project_id,
        version,
        key,
        fingerprint,
        plan,
        str(uuid5(version, fingerprint)),
        base.input_artifact_id,
        base.input_artifact_sha256,
        kind="exploration",
    )


class ExplorationInput:
    """Comprueba que la comprensión, el perfil y la tabla fijados son los de la carga."""

    def __init__(
        self, datasets: Datasets, executions: Executions, projects: ProjectPermissions
    ) -> None:
        self.datasets, self.executions, self.projects = datasets, executions, projects

    def prepare(self, lease: Lease) -> StepInput:
        run = lease.execution
        assert run.plan and run.input_artifact_id
        self.projects.require(run.owner_id, run.project_id, writable=True)
        version = self.datasets.get(run.owner_id, run.version_id)
        given = run.plan.content["input"]
        comprehension = self.executions.artifact(run.owner_id, run.input_artifact_id)
        profile = self.executions.artifact(run.owner_id, UUID(given["profile"]["artifact_id"]))
        table = self.executions.artifact(run.owner_id, UUID(given["table"]["artifact_id"]))
        if (
            comprehension.kind != "comprehension"
            or profile.kind != "profile"
            or table.kind != "table"
            or {comprehension.version_id, profile.version_id, table.version_id} != {version.id}
            or str(version.id) != given.get("version_id")
            or version.content.sha256 != given.get("version_content_sha256")
            or comprehension.content.sha256 != run.input_artifact_sha256
            or profile.content != reference(given["profile"])
            or table.content != reference(given["table"])
        ):
            raise ApplicationError(
                "INPUT_MISMATCH", "La comprensión fijada para la exploración no coincide.", 409
            )
        return StepInput("exploration", comprehension.content, table.content.sha256)


def ai_rows(result: ExploreResult, limit: int) -> list[list[str | None]]:
    return [
        [*row.groups, *[f.value for f in row.figures], str(row.rows)] for row in result.rows[:limit]
    ]


class ExplorationStep:
    output_kind: ArtifactKind = "exploration"
    transforms_data = False

    def __init__(self, objects: ObjectStore, copilot: CopilotService) -> None:
        self.objects, self.copilot = objects, copilot
        self.prepared: dict[UUID, str | None] = {}

    def prepare(self, lease: Lease, step: PlanStepSpec) -> None:
        reason = None
        try:
            self.copilot.available(lease.owner_id, lease.execution.project_id)
        except ApplicationError as error:
            reason = (
                error.code
                if error.code != "COPILOT_UNAVAILABLE"
                else (self.copilot.config.unavailable or "disabled")
            )
        self.prepared[lease.attempt_id] = reason

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        if source.kind != "exploration" or lease.attempt_id not in self.prepared:
            raise ApplicationError("INPUT_MISMATCH", "No se preparó la exploración.", 409)
        unavailable = self.prepared.pop(lease.attempt_id)
        plan = lease.execution.plan
        assert plan
        given = plan.content["input"]
        limits = ExplorationLimits.model_validate(step.parameters.get("limits", {}))
        comprehension = Comprehension.model_validate_json(self.objects.read(source.content))
        # Fase 24: las validaciones hechas después de la comprensión (instantánea del plan)
        # mandan sobre las que ella conocía: una relación rechazada no se explora.
        comprehension = with_verdicts(
            comprehension, {str(k): v for k, v in given.get("verdicts", [])}
        )
        profile = DatasetProfile.model_validate_json(self.objects.read(reference(given["profile"])))
        table = self.objects.read(reference(given["table"]))
        analysis = profile.overview.analysis if profile.overview else None
        catalog = Catalog(
            comprehension,
            additive_columns({c.name: c.additivity for c in analysis.columns} if analysis else {}),
        )
        execution = str(lease.execution_id)
        done: set[str] = set()
        proposals: list[ExploreProposal] = []
        queries: list[tuple[ExploreQuery, int]] = []

        def consider(raw: RawQuery, origin: str, motive: str) -> None:
            query, reason = validate(raw, catalog, done)
            if query is not None and len(queries) >= limits.max_queries:
                query, reason = None, "Se alcanzó el límite de consultas."
            proposals.append(
                ExploreProposal(
                    origin=origin,
                    query=raw.model_dump(exclude={"motive"}, exclude_none=True),
                    motive=motive,
                    status="accepted" if query else "rejected",
                    reason=reason,
                    key=query.key if query else None,
                )
            )
            if query is not None:
                done.add(query.key)
                queries.append((query, len(proposals) - 1))

        for raw, motive in rule_queries(comprehension, catalog):
            consider(raw, "rule", motive)

        provider = self.copilot.provider
        tokens = self.copilot.config.max_output_tokens
        active = provider is not None and unavailable is None and limits.max_ai_calls > 0
        calls: list[dict[str, object]] = []
        ai_state: str = "unavailable"
        ai_reason: str | None = unavailable or "disabled"
        if active and provider is not None:
            relations = [
                (r.columns[0], r.columns[1], r.detail)
                for r in comprehension.relationships
                if r.status == "confirmed"
                and r.verdict != "not_relevant"
                # Fase 24: una fórmula, una misma entidad o un periodo no son hallazgos.
                and r.kind not in {"derived", "same_entity", "period"}
            ]
            output, call, error = propose_queries(
                provider,
                propose_context(
                    comprehension.domain,
                    catalog.describe(),
                    relations,
                    comprehension.questions,
                    KINDS,
                    sorted(done),
                    limits.max_ai_proposals,
                ),
                tokens,
            )
            if call is not None:
                calls.append({**call.model_dump(mode="json"), "purpose": "proposal"})
            if output is None:
                ai_state, ai_reason = "failed", error
            else:
                ai_state, ai_reason = "ready", None
                for item in output.consultas[: limits.max_ai_proposals]:
                    consider(
                        RawQuery(
                            kind=item.tipo,
                            measure=item.medida,
                            measure_b=item.medida_b,
                            dimensions=item.dimensiones,
                            aggregation=item.agregacion,
                            filter_column=item.filtro_columna,
                            filter_value=item.filtro_valor,
                            limit=item.limite,
                        ),
                        "ai",
                        item.motivo,
                    )

        results: list[ExploreResult] = []
        for query, index in queries:
            computed = compute(table, query, execution)
            if isinstance(computed, str):
                proposals[index] = proposals[index].model_copy(
                    update={"status": "rejected", "reason": computed, "key": None}
                )
                continue
            results.append(computed)

        origin = {p.key: p.origin for p in proposals if p.key}
        judged: dict[str, tuple[bool, str]] = {}
        if (
            ai_state == "ready"
            and provider is not None
            and results
            and len(calls) < (limits.max_ai_calls)
        ):
            verdicts, call, error = judge_results(
                provider,
                judge_context(
                    [
                        {
                            "key": r.key,
                            "title": r.title,
                            "columns": r.columns,
                            "rows": ai_rows(r, limits.ai_rows),
                            "total_groups": r.total_groups,
                        }
                        for r in results
                    ]
                ),
                tokens,
            )
            if call is not None:
                calls.append({**call.model_dump(mode="json"), "purpose": "relevance"})
            if verdicts is not None:
                by_key = {r.key: r for r in results}
                for judgment in verdicts.juicios:
                    found = by_key.get(judgment.clave)
                    if found is None:
                        continue
                    allowed = [*found.columns, *[g for row in found.rows for g in row.groups]]
                    reason = clean_reason(judgment.motivo, allowed) or (
                        "Motivo retirado: contenía cifras que no salen del resultado."
                    )
                    judged[judgment.clave] = (judgment.relevante, reason)
        final: list[ExploreResult] = []
        for result in results:
            if result.key in judged:
                relevant, reason = judged[result.key]
                final.append(
                    result.model_copy(
                        update={"relevant": relevant, "judged_by": "ai", "reason": reason}
                    )
                )
            elif origin.get(result.key) == "rule":
                final.append(
                    result.model_copy(
                        update={
                            "relevant": True,
                            "judged_by": "rules",
                            "reason": "Explora una relación confirmada por los datos.",
                        }
                    )
                )
            else:
                final.append(result)
        exploration = Exploration(
            scope=ExplorationScope(
                execution_id=lease.execution_id,
                version_id=lease.version_id,
                comprehension_sha256=source.content.sha256,
                table_sha256=str(given["table"]["sha256"]),
            ),
            limits=limits,
            ai_state=ai_state,
            ai_reason=ai_reason,
            proposals=proposals,
            results=final,
            excluded=sorted(catalog.excluded),
            calls=calls,
            limitations=[
                "Las cifras se calculan sobre todas las filas; la IA sólo vio hasta "
                f"{limits.ai_rows} filas de cada resultado para juzgar su relevancia.",
                "Una diferencia entre grupos o una correlación no es una causa.",
            ],
        )
        prefix = f"artifacts/{lease.owner_id}/{lease.version_id}/{lease.token}/{step.id}"
        content = self.objects.put(
            f"{prefix}/exploration.json", exploration.model_dump_json().encode()
        )
        return StepResult(
            [
                ArtifactOutput(
                    uuid4(),
                    step.id,
                    "exploration",
                    "exploration",
                    content,
                    "application/json",
                    len(final),
                    len(proposals),
                )
            ]
        )


class InvestigationTreeStep:
    """`exploration.explore@2` (Fase 25, `investigation-v2`): plan, árbol, evidencias,
    clasificación y control. Escribe el artefacto `exploration` con sus nodos y, como
    proyección, los resultados y propuestas que leen el dashboard y el informe."""

    output_kind: ArtifactKind = "exploration"
    transforms_data = False

    def __init__(
        self, objects: ObjectStore, copilot: CopilotService, controls: ControlSource
    ) -> None:
        self.objects, self.copilot, self.controls = objects, copilot, controls
        self.prepared: dict[UUID, str | None] = {}

    def prepare(self, lease: Lease, step: PlanStepSpec) -> None:
        reason = None
        try:
            self.copilot.available(lease.owner_id, lease.execution.project_id)
        except ApplicationError as error:
            reason = (
                error.code
                if error.code != "COPILOT_UNAVAILABLE"
                else (self.copilot.config.unavailable or "disabled")
            )
        self.prepared[lease.attempt_id] = reason

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        if source.kind != "exploration" or lease.attempt_id not in self.prepared:
            raise ApplicationError("INPUT_MISMATCH", "No se preparó la investigación.", 409)
        unavailable = self.prepared.pop(lease.attempt_id)
        started = time.monotonic()
        plan = lease.execution.plan
        assert plan
        given = plan.content["input"]
        trigger: Trigger = plan.content.get("trigger") or "load"
        limits = ExplorationLimits.model_validate(step.parameters.get("limits", {}))
        limits = limits.model_copy(
            update={"max_seconds": max(1, min(limits.max_seconds, int(timeout) - 5))}
        )
        comprehension = with_verdicts(
            Comprehension.model_validate_json(self.objects.read(source.content)),
            {str(k): v for k, v in given.get("verdicts", [])},
        )
        profile = DatasetProfile.model_validate_json(self.objects.read(reference(given["profile"])))
        table = self.objects.read(reference(given["table"]))
        analysis = profile.overview.analysis if profile.overview else None
        catalog = Catalog(
            comprehension,
            additive_columns({c.name: c.additivity for c in analysis.columns} if analysis else {}),
        )
        execution = str(lease.execution_id)
        provider = self.copilot.provider
        tokens = self.copilot.config.max_output_tokens
        active = provider is not None and unavailable is None and limits.max_ai_calls > 0
        calls: list[dict[str, object]] = []
        ai_state: str = "unavailable"
        ai_reason: str | None = unavailable or "disabled"
        cost = Decimal(0)
        limitations: list[str] = []
        resumed: UUID | None = None
        results: dict[str, ExploreResult] = {}

        def spend(call: Any, purpose: str) -> None:
            nonlocal cost
            calls.append({**call.model_dump(mode="json"), "purpose": purpose})
            cost += Decimal(str(call.cost_usd)) if call.cost_usd else Decimal(0)

        if given.get("resume"):
            previous = Exploration.model_validate_json(
                self.objects.read(reference(given["resume"]))
            )
            if not previous.resumable:
                raise ApplicationError(
                    "INPUT_MISMATCH", "La investigación anterior no se puede reanudar.", 409
                )
            resumed = previous.scope.execution_id
            nodes = list(previous.nodes)
            results = {
                r.key: r.model_copy(update={"relevant": None, "judged_by": None, "reason": None})
                for r in previous.results
            }
            if active:
                ai_state, ai_reason = "ready", None
        else:
            drafts = rule_plan(comprehension, catalog)
            if active and provider is not None:
                relations = [
                    (r.columns[0], r.columns[1], r.detail)
                    for r in comprehension.relationships
                    if r.status == "confirmed"
                    and r.verdict != "not_relevant"
                    and r.kind not in {"derived", "same_entity", "period"}
                ]
                output, call, error = propose_queries(
                    provider,
                    propose_context(
                        comprehension.domain,
                        catalog.describe(),
                        relations,
                        comprehension.questions,
                        catalog.kinds(),
                        [],
                        limits.max_ai_proposals,
                        target_words(catalog) if catalog.target else None,
                    ),
                    tokens,
                )
                if call is not None:
                    spend(call, "proposal")
                if output is None:
                    ai_state, ai_reason = "failed", error
                else:
                    ai_state, ai_reason = "ready", None
                    offset = len(drafts)
                    for item in output.consultas[: limits.max_ai_proposals]:
                        raw = raw_query(item)
                        drafts.append(
                            ai_draft(
                                raw.model_copy(
                                    update={"depends_on": [offset + d for d in item.depende_de]}
                                ),
                                catalog.measures + catalog.dimensions,
                            )
                        )
            nodes, limitations = plan_nodes(drafts, catalog, limits.max_nodes)

        judge = None
        if ai_state == "ready" and provider is not None:

            def judge(items: list[tuple[InvestigationNode, ExploreResult]]) -> JudgeReply:
                verdicts, call, _ = judge_results(
                    provider,
                    judge_context(
                        [
                            {
                                "key": item.id,
                                "title": result.title,
                                "question": item.question,
                                "columns": result.columns,
                                "rows": ai_rows(result, limits.ai_rows),
                                "total_groups": result.total_groups,
                            }
                            for item, result in items
                        ],
                        catalog.kinds(),
                        catalog.describe(),
                    ),
                    tokens,
                )
                spent = Decimal(0)
                if call is not None:
                    spend(call, "relevance")
                    spent = Decimal(str(call.cost_usd)) if call.cost_usd else Decimal(0)
                found: dict[str, Verdict] = {}
                by_node = {item.id: result for item, result in items}
                for judgment in verdicts.juicios if verdicts else []:
                    if judgment.clave not in by_node:
                        continue
                    result = by_node[judgment.clave]
                    allowed = [*result.columns, *[g for row in result.rows for g in row.groups]]
                    reason = clean_reason(judgment.motivo, allowed) or (
                        "Motivo retirado: contenía cifras que no salen del resultado."
                    )
                    found[judgment.clave] = Verdict(
                        judgment.relevante,
                        reason,
                        [
                            raw_query(child).model_copy(update={"depends_on": []})
                            for child in judgment.profundizar[: limits.max_children]
                        ],
                    )
                return JudgeReply(found, spent, call is not None)

        investigator = Investigator(
            catalog,
            lambda query: compute(table, query, execution, catalog.period),
            row_count(table),
            limits,
            time.monotonic,
            lambda: self.controls.requested(lease.execution_id),
            judge,
            lease.execution_id,
            ai_calls=len(calls),
            cost=cost,
        )
        outcome = investigator.run(nodes, results)
        final = [
            projected(item, outcome.results[item.key])
            for item in outcome.nodes
            if item.status == "computed" and item.key in outcome.results
        ]
        exploration = Exploration(
            rules_version=RULES_BY_VERSION[min(step.version, 4)],
            operation=f"{STEP}@{min(step.version, 4)}",
            scope=ExplorationScope(
                execution_id=lease.execution_id,
                version_id=lease.version_id,
                comprehension_sha256=source.content.sha256,
                table_sha256=str(given["table"]["sha256"]),
            ),
            limits=limits,
            ai_state=ai_state,
            ai_reason=ai_reason,
            proposals=proposals(outcome.nodes),
            results=final,
            excluded=sorted(catalog.excluded),
            calls=calls,
            limitations=[
                "Las cifras se calculan sobre todas las filas con valor; la IA sólo vio hasta "
                f"{limits.ai_rows} filas de cada resultado para interpretarlo y no aporta "
                "cifras.",
                "La clasificación es de reglas (relevance-v3: cada grupo o mes con al menos "
                "10 registros y, en los factores del objetivo, una prueba estadística "
                "significativa tras corregir por comparaciones múltiples); el juicio de la IA "
                "sólo puede rebajarla."
                if step.version >= 4
                else "La clasificación es de reglas (relevance-v2: cada grupo o mes con al "
                "menos 10 registros); el juicio de la IA sólo puede rebajarla.",
                *limitations,
                *outcome.limitations,
            ],
            nodes=outcome.nodes,
            stopped=outcome.stopped,
            resumed_from=resumed,
            trigger=trigger,
            consumption=InvestigationConsumption(
                nodes=sum(
                    1
                    for n in outcome.nodes
                    if n.status in {"computed", "failed"} and n.execution_id == lease.execution_id
                ),
                ai_calls=len(calls),
                cost_usd=str(
                    sum((Decimal(str(c.get("cost_usd") or 0)) for c in calls), Decimal(0))
                ),
                elapsed_ms=int((time.monotonic() - started) * 1000),
            ),
        )
        prefix = f"artifacts/{lease.owner_id}/{lease.version_id}/{lease.token}/{step.id}"
        content = self.objects.put(
            f"{prefix}/exploration.json", exploration.model_dump_json().encode()
        )
        return StepResult(
            [
                ArtifactOutput(
                    uuid4(),
                    step.id,
                    "exploration",
                    "exploration",
                    content,
                    "application/json",
                    len(final),
                    len(outcome.nodes),
                )
            ]
        )


def raw_query(item: ConsultaIA) -> RawQuery:
    return RawQuery(
        kind=item.tipo,
        measure=item.medida,
        measure_b=item.medida_b,
        dimensions=item.dimensiones,
        aggregation=item.agregacion,
        filter_column=item.filtro_columna,
        filter_value=item.filtro_valor,
        limit=item.limite,
        target=item.objetivo,
        target_value=item.valor_objetivo,
        motive=item.motivo,
        question=item.pregunta,
        hypothesis=item.hipotesis,
        expected=item.esperado,
        priority=item.prioridad,
    )


def record_exploration_calls(
    db: Session, lease: Lease, output: ArtifactOutput, objects: ObjectStore
) -> None:
    ProjectPermissions(db).require(lease.owner_id, lease.execution.project_id, writable=True)
    result = Exploration.model_validate_json(objects.read(output.content))
    if (
        result.scope.execution_id != lease.execution_id
        or result.scope.comprehension_sha256 != lease.execution.input_artifact_sha256
    ):
        raise ApplicationError(
            "OUTPUT_MANIFEST_INVALID", "La exploración no corresponde a su comprensión.", 409
        )
    repository = SQLCopilotRepository(db)
    for item in result.calls:
        call: dict[str, Any] = dict(item)
        proposal = call.get("purpose") == "proposal"
        repository.log_call(
            CallRecord(
                owner_id=lease.owner_id,
                project_id=lease.execution.project_id,
                conversation_id=None,
                task="exploration_proposal" if proposal else "exploration_relevance",
                provider=str(call["provider"]),
                model=str(call["model"]),
                parameters=dict(call["parameters"]),
                prompt_id=PROPOSE_ID if proposal else JUDGE_ID,
                prompt_version=PROPOSE_VERSION if proposal else JUDGE_VERSION,
                context_sha256=str(call["context_sha256"]),
                input_tokens=int(call["input_tokens"]),
                output_tokens=int(call["output_tokens"]),
                cache_read_tokens=int(call["cache_read_tokens"]),
                cache_write_tokens=int(call["cache_write_tokens"]),
                cost_usd=Decimal(str(call["cost_usd"])) if call.get("cost_usd") else None,
                latency_ms=int(call["latency_ms"]),
                outcome=str(call["outcome"]),  # type: ignore[arg-type]
                validation={"exploration": str(lease.execution_id), "ai": result.ai_state},
                error_code=call.get("error_code"),
            )
        )


class ExplorationAccess:
    """Lectura de la exploración de una versión; nunca recalcula ni llama a la IA. Desde la Fase
    25 también da el historial y registra el control del usuario (pausar, cancelar, reanudar y
    volver a investigar)."""

    def __init__(
        self,
        datasets: Datasets,
        executions: Executions,
        objects: ObjectStore,
        db: Session | None = None,
    ) -> None:
        self.datasets, self.executions, self.objects = datasets, executions, objects
        self.db = db
        self.controls = SQLInvestigationControls(db) if db is not None else None

    def runs(self, owner: UUID, version: UUID) -> list[Execution]:
        self.datasets.get(owner, version)
        return [r for r in self.executions.for_version(owner, version) if r.kind == "exploration"]

    def latest(self, owner: UUID, version: UUID) -> Execution:
        runs = self.runs(owner, version)
        if not runs:
            raise ApplicationError(
                "EXPLORATION_NOT_AVAILABLE",
                "Esta versión no tiene exploración guiada: se procesó antes de la Fase 20 o su "
                "comprensión no terminó.",
                404,
            )
        return runs[0]

    def artifact(self, owner: UUID, run: Execution) -> Artifact:
        return next(a for a in self.executions.artifacts(owner, run.id) if a.kind == "exploration")

    def result(self, owner: UUID, run: Execution) -> Exploration | None:
        if run.state != "succeeded":
            return None
        found = Exploration.model_validate_json(
            self.objects.read(self.artifact(owner, run).content)
        )
        if found.scope.execution_id != run.id:
            raise ApplicationError(
                "INTEGRITY_ERROR", "La exploración no corresponde a esta versión.", 409
            )
        return found

    def view(self, owner: UUID, version: UUID, execution: UUID | None = None) -> ExplorationView:
        if execution is not None:
            run = next((r for r in self.runs(owner, version) if r.id == execution), None)
            if run is None:
                raise ApplicationError(
                    "EXECUTION_NOT_FOUND", "Esa investigación no es de esta versión.", 404
                )
            return self.described(owner, run)
        try:
            run = self.latest(owner, version)
        except ApplicationError as error:
            # Fase 21: mientras la comprensión sigue en marcha la exploración aún no tiene
            # trabajo (se encola al publicarse); no es un 404 y la interfaz sigue preguntando.
            waiting = any(
                r.kind == "comprehension" and r.state in {"queued", "running"}
                for r in self.executions.for_version(owner, version)
            )
            if error.code == "EXPLORATION_NOT_AVAILABLE" and waiting:
                return ExplorationView(state="queued")
            raise
        return self.described(owner, run)

    def described(self, owner: UUID, run: Execution) -> ExplorationView:
        control = self.controls.requested(run.id) if self.controls else None
        if run.state in {"queued", "running"}:
            return ExplorationView(state=run.state, execution_id=run.id, control=control)
        found = self.result(owner, run)
        if found is None:
            return ExplorationView(
                state="failed", execution_id=run.id, reason=run.error_code or "cancelled"
            )
        return ExplorationView(
            state="ready",
            execution_id=run.id,
            exploration=found,
            control=control,
            resumable=found.resumable,
        )

    def history(self, owner: UUID, version: UUID) -> InvestigationHistory:
        """Fase 25: todas las investigaciones de la versión, de la más reciente a la primera."""
        items = []
        for run in self.runs(owner, version):
            found = self.result(owner, run)
            assert run.plan
            items.append(
                InvestigationRun(
                    execution_id=run.id,
                    state=run.state,
                    created_at=run.created_at,
                    finished_at=run.finished_at,
                    error_code=run.error_code,
                    trigger=(found.trigger if found else None)
                    or run.plan.content.get("trigger")
                    or "load",
                    stopped=found.stopped if found else None,
                    resumed_from=found.resumed_from if found else None,
                    nodes=len(found.nodes or found.proposals) if found else None,
                    computed=(
                        sum(1 for n in found.nodes if n.status == "computed")
                        if found.nodes
                        else len(found.results)
                    )
                    if found
                    else None,
                    relevant=sum(1 for r in found.results if r.relevant) if found else None,
                )
            )
        return InvestigationHistory(items=items)

    def command(
        self, owner: UUID, version: UUID, action: Literal["pause", "cancel", "resume", "restart"]
    ) -> ExplorationView:
        """Fase 25: pausar o cancelar la investigación en marcha (se detiene al terminar la
        investigación en curso, conservando lo calculado), reanudar la pausada o volver a
        investigar. Lo anterior se conserva siempre."""
        assert self.db is not None and self.controls is not None
        run = self.latest(owner, version)
        ProjectPermissions(self.db).require(owner, run.project_id, writable=True)
        if action in {"pause", "cancel"}:
            if run.state not in {"queued", "running"}:
                raise ApplicationError(
                    "INVESTIGATION_FINISHED", "La investigación ya terminó.", 409
                )
            if self.controls.requested(run.id) is None:
                self.controls.add(owner, run.id, "pause" if action == "pause" else "cancel")
            self.db.commit()
            return self.view(owner, version)
        if run.state in {"queued", "running"}:
            raise ApplicationError(
                "INVESTIGATION_RUNNING",
                "La investigación sigue en marcha: páusala o cancélala antes.",
                409,
            )
        resume: Artifact | None = None
        if action == "resume":
            found = self.result(owner, run)
            if found is None or not found.resumable:
                raise ApplicationError(
                    "INVESTIGATION_NOT_RESUMABLE",
                    "Sólo se reanuda una investigación pausada (o detenida por tiempo) con "
                    "investigaciones pendientes.",
                    409,
                )
            resume = self.artifact(owner, run)
        created = request_investigation(
            self.executions, owner, version, "resume" if action == "resume" else "restart", resume
        )
        self.db.commit()
        return self.view(owner, version, created.id)
