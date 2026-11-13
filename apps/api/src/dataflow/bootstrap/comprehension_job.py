"""Comprensión del negocio (Fase 19, ADR-036): une la cola, las medidas, la IA y las valoraciones
del usuario sin acoplar los módulos entre sí.

Tras publicar una carga con interpretación analítica se encola un trabajo `comprehension`
(antes que la investigación) cuyo input fija el perfil y la tabla de la carga y una instantánea de
las valoraciones previas de la misma fuente. Siempre se ejecuta: sin IA calcula escalas,
asociaciones y relaciones por los datos.

Fase 23 (`business-comprehension-v2`, ADR-040): el input fija también una instantánea de las
correcciones del Diccionario de la fuente. Al calcular, la comprensión parte de la misma
clasificación que la pestaña Dataset (mismas reglas sobre la misma tabla) con esas correcciones
encima; las columnas con datos personales se tratan como texto y no se envían a la IA. Una
corrección nueva encola otra comprensión de la versión (y, al publicarse, otra exploración, otro
dashboard y otra versión del informe).
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4, uuid5

from sqlalchemy.orm import Session

from dataflow.bootstrap.dashboard_job import request_report_update
from dataflow.bootstrap.exploration_job import request_exploration_update
from dataflow.bootstrap.loads import same_load
from dataflow.modules.comprehension.contracts import (
    AIColumn,
    AIComprehension,
    ColumnMeaning,
    Comprehension,
    ComprehensionScope,
    ComprehensionView,
    DatedAttribute,
    DimensionInfo,
    Entity,
    FeedbackRequest,
    Formula,
    Grain,
    MeaningRequest,
    MeasureInfo,
    Period,
    Relationship,
    UserMeaning,
    Verdict,
)
from dataflow.modules.comprehension.domain import (
    accept_ai,
    classified_roles,
    classify,
    closure,
    dimension_infos,
    grain,
    measure_infos,
    period_of,
    relationships,
    scales,
    structural,
    with_user_meanings,
)
from dataflow.modules.comprehension.infrastructure import (
    SQLFeedbackRepository,
    SQLMeaningRepository,
)
from dataflow.modules.comprehension.measures import (
    associations,
    dependencies,
    distinct_counts,
    distinct_values,
    month_counts,
    per_year,
    same_entities,
    thresholds,
    weighted_sums,
)
from dataflow.modules.copilot.application import CopilotService
from dataflow.modules.copilot.comprehension import PROMPT_ID, PROMPT_VERSION, comprehend, context
from dataflow.modules.copilot.contracts import CallRecord
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
from dataflow.modules.inspection.contracts import INSPECTION_RULES, ColumnAnnotation
from dataflow.modules.inspection.domain import classification, dictionary
from dataflow.modules.inspection.engine import classify_table
from dataflow.modules.inspection.infrastructure import SQLColumnAnnotations
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.modules.understanding.contracts import AnalyticalInterpretation, DatasetProfile
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError
from dataflow.platform.timing import date_role, explain

STEP = "comprehension.understand"
RULES = "business-comprehension-v4"
V3 = "business-comprehension-v3"
GROUNDED = {V3, RULES}  # versiones con grano, fórmulas y significados (Fase 24)


def source_key(file_name: str, plan: dict[str, Any]) -> str:
    """Identidad de la fuente entre versiones: archivo y hoja, tabla o segmentos leídos. Una
    versión derivada (Fase 23) hereda la de su carga en `source_key`."""
    if plan.get("source_key"):
        return str(plan["source_key"])
    steps = plan.get("steps", [])
    read: dict[str, Any] = next((s for s in steps if s.get("id") == "read"), {})
    parameters = read.get("parameters", {})
    detail = {
        k: parameters[k] for k in ("sheet", "table", "segments") if parameters.get(k) is not None
    }
    origin = plan.get("source_origin") or {}
    if origin.get("table"):
        detail["origin"] = origin["table"]
    return f"{file_name}|{json.dumps(detail, sort_keys=True, ensure_ascii=False)}"[:600]


def declared_keys(plan: dict[str, Any]) -> list[tuple[str, str]]:
    origin = plan.get("source_origin") or {}
    return [
        (str(item["column"]), str(item["references"]))
        for item in origin.get("foreign_keys", [])
        if item.get("column") and item.get("references")
    ]


def snapshot(annotations: dict[str, ColumnAnnotation]) -> list[list[str]]:
    """Lo que cuenta de las correcciones para la comprensión, como lista ordenada de textos (el
    hash canónico sólo admite claves en snake_case): columna, rol, naturaleza y la decisión sobre
    datos personales («yes», «no» o vacío)."""
    return sorted(
        [
            name,
            note.role or "",
            note.nature or "",
            "" if note.personal is None else "yes" if note.personal else "no",
        ]
        for name, note in annotations.items()
        if note.role or note.nature or note.personal is not None
    )


def from_snapshot(items: list[list[str]], version: UUID) -> dict[str, ColumnAnnotation]:
    moment = datetime(2000, 1, 1, tzinfo=UTC)
    return {
        name: ColumnAnnotation(
            column=name,
            role=role or None,
            nature=nature or None,
            time_format=None,
            notes=None,
            confirmed=False,
            version_id=version,
            created_at=moment,
            personal=None if personal == "" else personal == "yes",
        )
        for name, role, nature, personal in items
    }


def enqueue_comprehension(
    executions: Executions,
    datasets: Datasets,
    feedback: SQLFeedbackRepository,
    lease: Lease,
    profile: Artifact,
    table: Artifact,
    config: ProcessingConfig,
    annotations: SQLColumnAnnotations | None = None,
) -> None:
    run = lease.execution
    assert run.plan
    key = uuid5(lease.execution_id, "comprehension@1")
    version = datasets.get(lease.owner_id, lease.version_id)
    source = source_key(version.file_name, run.plan.content)
    # Lista ordenada de pares: el hash canónico sólo admite claves en snake_case.
    verdicts = sorted(
        [key, verdict]
        for key, verdict in feedback.for_source(lease.owner_id, run.project_id, source).items()
    )
    corrections = (
        snapshot(annotations.for_source(lease.owner_id, run.project_id, source))
        if annotations is not None
        else []
    )
    fingerprint = digest(
        "comprehension_request",
        {
            "profile_sha256": profile.content.sha256,
            "table_sha256": table.content.sha256,
            "verdicts": verdicts,
            "annotations": corrections,
            "operation": f"{STEP}@1",
        },
    )
    if executions.find_request(lease.owner_id, run.project_id, "comprehension", key, fingerprint):
        return
    content = {
        "objective": None,
        "input": {
            "kind": "comprehension",
            "alias": "source",
            "version_id": str(version.id),
            "version_content_sha256": version.content.sha256,
            "file_name": version.file_name,
            "source_key": source,
            "artifact_id": str(profile.id),
            "artifact_sha256": profile.content.sha256,
            "producer_execution_id": str(profile.execution_id),
            "table_artifact_id": str(table.id),
            "table_key": table.content.key,
            "table_sha256": table.content.sha256,
            "table_byte_size": table.content.byte_size,
            "verdicts": verdicts,
            "declared": [list(pair) for pair in declared_keys(run.plan.content)],
            # Fase 23: IDs de las columnas y correcciones del Diccionario de la fuente.
            "column_ids": [str(c["id"]) for c in table.columns or []],
            "annotations": corrections,
        },
        "steps": [
            {
                "id": "understand",
                "operation": STEP,
                "version": 1,
                "input": {"kind": "input", "alias": "source"},
                "parameters": {"rules": RULES},
            }
        ],
        # Una llamada facturable no se reintenta.
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
        profile.id,
        profile.content.sha256,
        kind="comprehension",
    )


def request_comprehension_update(
    executions: Executions,
    annotations: SQLColumnAnnotations,
    owner: UUID,
    version: UUID,
    source: str,
) -> Execution | None:
    """Fase 23: encola otra comprensión de la versión con las correcciones vigentes del
    Diccionario (misma tabla, mismo perfil, mismas valoraciones). No hace nada si la versión no
    tiene comprensión `business-comprehension-v2` (cargas anteriores a la Fase 23) o si la última
    ya usa esas correcciones. La comprensión anterior se conserva."""
    runs = [r for r in executions.for_version(owner, version) if r.kind == "comprehension"]
    if not runs:
        return None
    base = runs[0]
    assert base.plan and base.input_artifact_id and base.input_artifact_sha256
    given = base.plan.content["input"]
    if "column_ids" not in given:
        return None
    corrections = snapshot(annotations.for_source(owner, base.project_id, source))
    if given.get("annotations", []) == corrections:
        return None
    content = {
        **base.plan.content,
        "input": {**given, "annotations": corrections},
        "trigger": "dictionary",
    }
    fingerprint = digest(
        "comprehension_update",
        {
            "base_sha256": base.plan.content_sha256,
            "annotations": corrections,
            "count": len(runs),
        },
    )
    key = uuid5(version, f"comprehension-update:{len(runs)}:{fingerprint}")
    if executions.find_request(owner, base.project_id, "comprehension", key, fingerprint):
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
        kind="comprehension",
    )


class ComprehensionInput:
    """Comprueba que el perfil y la tabla fijados son los de la carga."""

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
        profile = self.executions.artifact(run.owner_id, run.input_artifact_id)
        table = self.executions.artifact(run.owner_id, UUID(given["table_artifact_id"]))
        if (
            profile.kind != "profile"
            or table.kind != "table"
            or profile.version_id != version.id
            or table.version_id != version.id
            or not same_load(self.executions, run.owner_id, profile, table)
            or str(profile.id) != given.get("artifact_id")
            or str(version.id) != given.get("version_id")
            or version.content.sha256 != given.get("version_content_sha256")
            or profile.content.sha256 != given.get("artifact_sha256")
            or profile.content.sha256 != run.input_artifact_sha256
            or table.content.key != given.get("table_key")
            or table.content.sha256 != given.get("table_sha256")
            or table.content.byte_size != given.get("table_byte_size")
        ):
            raise ApplicationError(
                "INPUT_MISMATCH", "El perfil fijado para la comprensión no coincide.", 409
            )
        return StepInput("comprehension", profile.content, table.content.sha256)


CONFIDENCE: dict[str, Literal["high", "medium", "low"]] = {
    "alta": "high",
    "media": "medium",
    "baja": "low",
}


@dataclass
class Understood:
    """Fase 24: lo que la comprensión v3 añade por reglas sobre la tabla completa."""

    grain: Grain | None = None
    formulas: list[Formula] = field(default_factory=list)
    measures: list[MeasureInfo] = field(default_factory=list)
    dimensions: list[DimensionInfo] = field(default_factory=list)
    period: Period | None = None
    structural: list[Relationship] = field(default_factory=list)
    dated: list[DatedAttribute] = field(default_factory=list)
    pairs: set[frozenset[str]] = field(default_factory=set)


def understand(
    table: bytes,
    analysis: AnalyticalInterpretation | None,
    roles: list[tuple[str, str]],
    dimensions: list[str],
    hidden: set[str],
    verdicts: dict[str, Verdict],
    v4: bool = False,
) -> Understood:
    """Grano, columnas calculadas (sumas ponderadas, productos ya comprobados por la
    interpretación y umbrales), misma entidad 1:1, periodo, medidas y dimensiones."""
    measures = [name for name, role in roles if role == "measure"]
    counts = distinct_counts(table, dimensions)
    dichotomous = [d for d in dimensions if counts.get(d) == 2]
    formulas = weighted_sums(table, measures)
    if analysis is not None:
        for item in analysis.relationships:
            if item.compared_rows and item.matching_rows == item.compared_rows:
                formulas.append(
                    Formula(
                        column=item.target,
                        kind="product",
                        sources=list(item.factors),
                        expression=f"{item.target} = {' × '.join(item.factors)}",
                        rows=item.compared_rows,
                        matching_rows=item.matching_rows,
                        tolerance=item.tolerance,
                        method="Producto comprobado fila a fila por la interpretación analítica.",
                    )
                )
    taken = {f.column for f in formulas}
    # Un umbral por columna dicotómica: si varias medidas la separan, la calculada primero (es la
    # que la define); si no, la primera medida.
    by_column: dict[str, Formula] = {}
    for cut in thresholds(table, measures, dichotomous):
        chosen = by_column.get(cut.column)
        if cut.column in taken or (chosen and chosen.sources[0] in taken):
            continue
        if chosen is None or cut.sources[0] in taken:
            by_column[cut.column] = cut
    formulas += list(by_column.values())
    derived = {f.column for f in formulas}
    pairs = {
        frozenset((target, source))
        for target, sources in closure(formulas).items()
        for source in sources
    }
    candidates = [
        name
        for name, role in roles
        if role in {"identifier", "dimension", "text"} and name not in hidden
    ]
    period = None
    dated: list[DatedAttribute] = []
    found_grain = grain([(k.columns, k.unique) for k in analysis.keys]) if analysis else grain([])
    if analysis is not None and analysis.time is not None:
        axis = analysis.time
        per_month = month_counts(table, axis.kind, axis.columns)
        # Fase 28: una fecha que describe a la entidad no es una línea de tiempo.
        # La clave de una entidad no incluye el periodo: con una fila por mes (clave Año + Mes)
        # la tabla es una serie temporal, no un padrón.
        entity = any(k.unique and not set(k.columns) & set(axis.columns) for k in analysis.keys)
        role = date_role(entity, list(per_month.values())) if v4 else "events"
        if role == "attribute":
            dated.append(
                DatedAttribute(
                    column=axis.columns[0],
                    first=axis.first,
                    last=axis.last,
                    per_year=per_year(per_month),
                    reason=explain(role, axis.columns[0], list(per_month.values())),
                )
            )
        else:
            period = period_of(
                axis.kind, axis.columns, axis.first, axis.last, axis.periods, axis.missing_count
            )
    current = dict(roles)
    columns = (
        [
            (c.name, current.get(c.name, c.role), c.additivity, c.unit_label, c.monetary)
            for c in analysis.columns
        ]
        if analysis
        else []
    )
    return Understood(
        grain=found_grain,
        dated=dated,
        formulas=formulas,
        measures=measure_infos(columns, derived),
        dimensions=dimension_infos(dimensions, counts, derived),
        period=period,
        structural=structural(formulas, same_entities(table, candidates), period, verdicts),
        pairs=pairs,
    )


def current(
    result: Comprehension,
    verdicts: dict[str, Verdict],
    meanings: Mapping[str, UserMeaning],
) -> Comprehension:
    """La comprensión publicada con las valoraciones y los significados vigentes del usuario
    encima (Fase 24): lo calculado no cambia, sólo cómo se lee."""
    return result.model_copy(
        update={
            "relationships": [
                classify(r.model_copy(update={"verdict": verdicts.get(r.key, r.verdict)}))
                for r in result.relationships
            ],
            "meanings": with_user_meanings(result.meanings, meanings),
        }
    )


def ai_columns(
    profile: DatasetProfile,
    scale_of: dict[str, str],
    roles_of: dict[str, str] | None = None,
    hidden: set[str] | None = None,
) -> list[AIColumn]:
    """Nombre y perfil agregado de cada columna. Fase 23: con el rol vigente (con las
    correcciones del Diccionario) y sin las columnas con datos personales."""
    analysis = profile.overview.analysis if profile.overview else None
    roles: dict[str, str] = {c.name: c.role for c in analysis.columns} if analysis else {}
    roles |= roles_of or {}
    columns = []
    for column in profile.columns:
        if column.name in (hidden or set()):
            continue
        numeric = column.numeric
        columns.append(
            AIColumn(
                name=column.name,
                type=column.suggested_type,
                role=roles.get(column.name, "text"),
                scale=scale_of.get(column.name, "nominal"),
                distinct=column.unique_count,
                nulls=column.null_count,
                rows=profile.row_count,
                frequent=column.examples[:5] if roles.get(column.name) == "dimension" else [],
                minimum=numeric.minimum if numeric else None,
                maximum=numeric.maximum if numeric else None,
            )
        )
    return columns


class ComprehensionStep:
    output_kind: ArtifactKind = "comprehension"
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
        if source.kind != "comprehension" or lease.attempt_id not in self.prepared:
            raise ApplicationError("INPUT_MISMATCH", "No se preparó la comprensión.", 409)
        unavailable = self.prepared.pop(lease.attempt_id)
        plan = lease.execution.plan
        assert plan
        given = plan.content["input"]
        profile = DatasetProfile.model_validate_json(self.objects.read(source.content))
        table = self.objects.read(
            StoredObject(given["table_key"], given["table_sha256"], given["table_byte_size"])
        )
        analysis = profile.overview.analysis if profile.overview else None
        roles: list[tuple[str, str]] = (
            [(c.name, c.role) for c in analysis.columns]
            if analysis
            else [(c.name, "text") for c in profile.columns]
        )
        declared: dict[str, str] = {}
        corrected: list[str] = []
        personal: list[str] = []
        v2 = "column_ids" in given
        # Fase 24: grano, fórmulas, misma entidad, periodo, medidas y dimensiones.
        rules_asked = (plan.content["steps"][0].get("parameters") or {}).get("rules")
        v3 = rules_asked in GROUNDED
        if v2:
            # Fase 23: la clasificación de la pestaña Dataset con las correcciones fijadas.
            columns = classify_table(table, [UUID(i) for i in given["column_ids"]], profile)
            entries = dictionary(
                columns,
                INSPECTION_RULES,
                from_snapshot(given.get("annotations", []), lease.version_id),
                lease.version_id,
            )
            roles, declared, corrected, personal = classified_roles(
                roles,
                [
                    (c.name, c.role, c.nature, c.personal, c.corrected)
                    for c in classification(entries)
                ],
            )
        hidden = set(personal)
        names = [name for name, _ in roles if name not in hidden]
        measures = [name for name, role in roles if role == "measure"]
        dimensions = [name for name, role in roles if role == "dimension"]
        distinct = distinct_values(table, dimensions)
        rule_scales = scales(roles, distinct, None, declared)
        limitations = [
            "La comprensión de la IA son hipótesis sobre nombres y un perfil agregado: no vio "
            "filas. Cada relación lleva la medida calculada que la respalda o no.",
            "Una asociación no es una causa.",
        ]
        if analysis is None:
            limitations.append("Esta carga no tiene interpretación analítica: todo es texto.")
        if corrected:
            limitations.append(
                "La clasificación de "
                + ", ".join(f"«{n}»" for n in corrected)
                + " viene de tus correcciones en el Diccionario de la pestaña Dataset."
            )
        if personal:
            limitations.append(
                "Las columnas con datos personales ("
                + ", ".join(f"«{n}»" for n in personal)
                + ") se tratan como texto y no se envían a la IA."
            )

        accepted: AIComprehension | None = None
        discarded: list[str] = []
        calls: list[dict[str, object]] = []
        ai_state, ai_reason = "unavailable", unavailable
        provider = self.copilot.provider
        if provider is not None and unavailable is None:
            output, call, error = comprehend(
                provider,
                context(
                    [
                        item.model_dump()
                        for item in ai_columns(
                            profile,
                            {s.column: s.scale for s in rule_scales},
                            dict(roles),
                            hidden,
                        )
                    ],
                    profile.row_count,
                    str(given["file_name"]),
                ),
                self.copilot.config.max_output_tokens,
            )
            if call is not None:
                calls.append(call.model_dump(mode="json"))
            if output is None:
                ai_state, ai_reason = "failed", error
            else:
                raw = AIComprehension(
                    domain=output.dominio,
                    entities=[Entity(name=e.nombre, columns=e.columnas) for e in output.entidades],
                    meanings=[
                        ColumnMeaning(
                            column=c.columna,
                            meaning=c.significado,
                            entity=c.entidad,
                            confidence=CONFIDENCE[c.confianza] if v3 else None,
                            reason=(c.justificacion.strip() or None) if v3 else None,
                        )
                        for c in output.columnas
                    ],
                    orders={o.columna: o.orden for o in output.ordenes},
                    relationships=[
                        (r.columnas[0], r.columnas[1], r.tipo.strip().casefold(), r.hipotesis)
                        for r in output.relaciones
                    ],
                    questions=output.preguntas,
                )
                accepted, discarded = accept_ai(raw, names)
                ai_state, ai_reason = "ready", None
        final_scales = scales(roles, distinct, accepted.orders if accepted else None, declared)
        found, matrix = associations(table, measures, dimensions)
        ai_pairs = accepted.relationships if accepted else []
        dependency_pairs = [
            (a, b) for a, b, kind, _ in ai_pairs if kind in {"dependencia", "jerarquia"}
        ]
        if analysis is not None:
            dependency_pairs += [(d.determinant, d.dependent) for d in analysis.dependencies]
        checked = dependencies(table, dependency_pairs)
        verdicts = {str(k): v for k, v in given.get("verdicts", [])}
        understood = Understood()
        if v3:
            understood = understand(
                table, analysis, roles, dimensions, hidden, verdicts, rules_asked == RULES
            )
            if understood.formulas:
                limitations.append(
                    "Las columnas calculadas a partir de otras ("
                    + ", ".join(f"«{f.column}»" for f in understood.formulas)
                    + ") se muestran como fórmulas: sus asociaciones con sus propias fuentes no "
                    "se proponen como hallazgos."
                )
        result = Comprehension(
            rules_version=(rules_asked if rules_asked in GROUNDED else V3)
            if v3
            else ("business-comprehension-v2" if v2 else "business-comprehension-v1"),
            scope=ComprehensionScope(
                execution_id=lease.execution_id,
                version_id=lease.version_id,
                profile_sha256=source.content.sha256,
                table_sha256=str(given["table_sha256"]),
            ),
            ai_state=ai_state,
            ai_reason=ai_reason,
            domain=accepted.domain if accepted and accepted.domain else None,
            entities=accepted.entities if accepted else [],
            meanings=accepted.meanings if accepted else [],
            scales=final_scales,
            associations=found,
            matrix_columns=matrix,
            relationships=relationships(
                ai_pairs,
                found,
                checked,
                [(str(pair[0]), str(pair[1])) for pair in given.get("declared", [])],
                verdicts,
                [(d.determinant, d.dependent) for d in analysis.dependencies] if analysis else [],
                understood.structural,
                understood.pairs,
            ),
            questions=accepted.questions if accepted else [],
            discarded=discarded,
            limitations=limitations,
            calls=calls,
            corrected_columns=corrected,
            personal_columns=personal,
            grain=understood.grain,
            formulas=understood.formulas,
            measures=understood.measures,
            dimensions=understood.dimensions,
            period=understood.period,
            dated_attributes=understood.dated,
        )
        prefix = f"artifacts/{lease.owner_id}/{lease.version_id}/{lease.token}/{step.id}"
        stored = self.objects.put(f"{prefix}/comprehension.json", result.model_dump_json().encode())
        return StepResult(
            [
                ArtifactOutput(
                    uuid4(),
                    step.id,
                    "comprehension",
                    "comprehension",
                    stored,
                    "application/json",
                    len(result.relationships),
                    len(result.matrix_columns),
                )
            ]
        )


def record_comprehension_calls(
    db: Session, lease: Lease, output: ArtifactOutput, objects: ObjectStore
) -> None:
    """Registra la llamada a la IA en el consumo (presupuestos durables) al publicar."""
    ProjectPermissions(db).require(lease.owner_id, lease.execution.project_id, writable=True)
    result = Comprehension.model_validate_json(objects.read(output.content))
    if (
        result.scope.execution_id != lease.execution_id
        or result.scope.profile_sha256 != lease.execution.input_artifact_sha256
    ):
        raise ApplicationError(
            "OUTPUT_MANIFEST_INVALID", "La comprensión no corresponde a su perfil.", 409
        )
    repository = SQLCopilotRepository(db)
    for item in result.calls:
        call: dict[str, Any] = dict(item)
        repository.log_call(
            CallRecord(
                owner_id=lease.owner_id,
                project_id=lease.execution.project_id,
                conversation_id=None,
                task="business_comprehension",
                provider=str(call["provider"]),
                model=str(call["model"]),
                parameters=dict(call["parameters"]),
                prompt_id=PROMPT_ID,
                prompt_version=PROMPT_VERSION,
                context_sha256=str(call["context_sha256"]),
                input_tokens=int(call["input_tokens"]),
                output_tokens=int(call["output_tokens"]),
                cache_read_tokens=int(call["cache_read_tokens"]),
                cache_write_tokens=int(call["cache_write_tokens"]),
                cost_usd=Decimal(str(call["cost_usd"])) if call.get("cost_usd") else None,
                latency_ms=int(call["latency_ms"]),
                outcome=str(call["outcome"]),  # type: ignore[arg-type]
                validation={"comprehension": str(lease.execution_id), "ai": result.ai_state},
                error_code=call.get("error_code"),
            )
        )


class ComprehensionAccess:
    """Lectura de la comprensión, valoraciones y significados del usuario; nunca llama a la
    IA. Fase 24: una valoración rehace la exploración, el dashboard y el informe."""

    def __init__(
        self,
        db: Session,
        datasets: Datasets,
        executions: Executions,
        objects: ObjectStore,
        feedback: SQLFeedbackRepository,
        meanings: SQLMeaningRepository | None = None,
    ) -> None:
        self.db, self.datasets, self.executions = db, datasets, executions
        self.objects, self.feedback = objects, feedback
        self.meanings = meanings or SQLMeaningRepository(db)

    def run(self, owner: UUID, version: UUID) -> Execution:
        self.datasets.get(owner, version)
        runs = [r for r in self.executions.for_version(owner, version) if r.kind == "comprehension"]
        if not runs:
            raise ApplicationError(
                "COMPREHENSION_NOT_AVAILABLE",
                "Esta versión no tiene comprensión del negocio: se procesó antes de la Fase 19.",
                404,
            )
        return runs[0]

    def result(self, owner: UUID, run: Execution) -> Comprehension | None:
        if run.state != "succeeded":
            return None
        artifact = next(
            a for a in self.executions.artifacts(owner, run.id) if a.kind == "comprehension"
        )
        result = Comprehension.model_validate_json(self.objects.read(artifact.content))
        if result.scope.execution_id != run.id:
            raise ApplicationError(
                "INTEGRITY_ERROR", "La comprensión no corresponde a esta versión.", 409
            )
        return result

    def view(self, owner: UUID, version: UUID) -> ComprehensionView:
        run = self.run(owner, version)
        if run.state in {"queued", "running"}:
            return ComprehensionView(state=run.state, execution_id=run.id)
        result = self.result(owner, run)
        if result is None:
            return ComprehensionView(
                state="failed", execution_id=run.id, reason=run.error_code or "cancelled"
            )
        feedback = self.feedback.for_version(owner, version)
        if result.rules_version in GROUNDED:
            assert run.plan
            source = str(run.plan.content["input"]["source_key"])
            result = current(
                result,
                {f.relationship_key: f.verdict for f in feedback},
                self.meanings.for_source(owner, run.project_id, source),
            )
        return ComprehensionView(
            state="ready",
            execution_id=run.id,
            comprehension=result,
            feedback=feedback,
            recalculating=any(
                r.kind in {"exploration", "dashboard"} and r.state in {"queued", "running"}
                for r in self.executions.for_version(owner, version)
            ),
        )

    def judge(self, owner: UUID, version: UUID, request: FeedbackRequest) -> ComprehensionView:
        """Valoración opcional: no recalcula nada; la siguiente carga de la misma fuente la usa."""
        run = self.run(owner, version)
        result = self.result(owner, run)
        if result is None:
            raise ApplicationError(
                "COMPREHENSION_NOT_READY", "La comprensión todavía no está lista.", 409
            )
        if request.relationship_key not in {r.key for r in result.relationships}:
            raise ApplicationError(
                "RELATIONSHIP_NOT_FOUND", "Esa relación no está en esta comprensión.", 404
            )
        ProjectPermissions(self.db).require(owner, run.project_id, writable=True)
        assert run.plan
        source = str(run.plan.content["input"]["source_key"])
        self.feedback.add(
            owner, run.project_id, version, source, request.relationship_key, request.verdict
        )
        if result.rules_version in GROUNDED:
            # Fase 24: la valoración cuenta ya (no sólo en la siguiente carga).
            request_exploration_update(
                self.executions,
                owner,
                version,
                dict(self.feedback.for_source(owner, run.project_id, source)),
            )
        self.db.commit()
        return self.view(owner, version)

    def describe(self, owner: UUID, version: UUID, request: MeaningRequest) -> ComprehensionView:
        """Fase 24: significado escrito o confirmado por el usuario. Es un metadato de la fuente
        y la columna (lo heredan las versiones siguientes) y no cambia ningún cálculo."""
        run = self.run(owner, version)
        result = self.result(owner, run)
        if result is None:
            raise ApplicationError(
                "COMPREHENSION_NOT_READY", "La comprensión todavía no está lista.", 409
            )
        if request.column not in {s.column for s in result.scales}:
            raise ApplicationError("UNKNOWN_COLUMN", "La columna no existe en esta versión.", 404)
        if request.meaning is not None and not request.meaning.strip() and not request.confirmed:
            raise ApplicationError("MEANING_INVALID", "El significado está vacío.", 422)
        if request.unknown and (request.confirmed or (request.meaning or "").strip()):
            raise ApplicationError(
                "MEANING_INVALID",
                "Una columna desconocida no lleva significado ni confirmación.",
                422,
            )
        ProjectPermissions(self.db).require(owner, run.project_id, writable=True)
        assert run.plan
        self.meanings.add(
            owner,
            run.project_id,
            version,
            str(run.plan.content["input"]["source_key"]),
            request.column,
            request.meaning,
            request.confirmed,
            request.unknown,
        )
        # Fase 24B: el informe describe las columnas con el significado vigente; se pide otra
        # versión (la anterior se conserva). Ningún cálculo cambia.
        request_report_update(self.executions, owner, version, "meaning")
        self.db.commit()
        return self.view(owner, version)
