"""Ciclo acotado de la investigación (`investigation-v2`, Fase 25, ADR-043), con puertos.

Recorre el árbol por niveles: calcula las investigaciones pendientes del nivel (en orden de
prioridad y respetando dependencias), las evalúa por reglas, pide a la IA un juicio del nivel
(que sólo puede rebajar un resultado y proponer preguntas secundarias) y decide si profundizar.
Antes de cada cálculo mira la petición de control (pausa o cancelación) y los límites de tiempo,
investigaciones, profundidad, llamadas a la IA y coste. Todo el estado vive en los nodos, así que
una investigación pausada se reanuda desde donde quedó sin repetir lo calculado.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from dataflow.modules.exploration.contracts import (
    ControlAction,
    Criterion,
    ExplorationLimits,
    ExploreQuery,
    ExploreResult,
    InvestigationNode,
    RawQuery,
    StopReason,
)
from dataflow.modules.exploration.domain import Catalog, validate
from dataflow.modules.exploration.plan import (
    CLASSES,
    Draft,
    ai_draft,
    evaluate,
    lower,
    node,
    rule_children,
    unanswerable,
)


@dataclass(frozen=True)
class Verdict:
    relevant: bool
    reason: str | None  # ya sin cifras propias
    children: list[RawQuery] = field(default_factory=list)


@dataclass(frozen=True)
class JudgeReply:
    verdicts: dict[str, Verdict]  # por id de nodo
    cost: Decimal
    called: bool  # hubo llamada facturable (aunque fallara)


Judge = Callable[[list[tuple[InvestigationNode, ExploreResult]]], JudgeReply]


@dataclass
class Outcome:
    nodes: list[InvestigationNode]
    results: dict[str, ExploreResult]
    stopped: StopReason
    limitations: list[str]
    ai_calls: int
    cost: Decimal


class Investigator:
    def __init__(
        self,
        catalog: Catalog,
        compute: Callable[[ExploreQuery], ExploreResult | str],
        total_rows: int,
        limits: ExplorationLimits,
        clock: Callable[[], float],
        control: Callable[[], ControlAction | None],
        judge: Judge | None,
        execution_id: UUID,
        ai_calls: int = 0,
        cost: Decimal = Decimal(0),
    ) -> None:
        self.catalog, self.compute, self.total_rows = catalog, compute, total_rows
        self.limits, self.clock, self.control, self.judge = limits, clock, control, judge
        self.execution_id = execution_id
        self.ai_calls, self.cost = ai_calls, cost
        self.started = clock()
        self.limitations: list[str] = []

    # --- utilidades ---------------------------------------------------------------------------

    def ai_left(self) -> bool:
        return (
            self.judge is not None
            and self.ai_calls < self.limits.max_ai_calls
            and self.cost < Decimal(self.limits.max_cost_usd)
        )

    def note(self, text: str) -> None:
        if text not in self.limitations:
            self.limitations.append(text)

    def stop_reason(self) -> StopReason | None:
        requested = self.control()
        if requested == "pause":
            return "paused"
        if requested == "cancel":
            return "cancelled"
        if self.clock() - self.started >= self.limits.max_seconds:
            return "max_seconds"
        return None

    @staticmethod
    def ordered(nodes: list[InvestigationNode]) -> list[InvestigationNode]:
        """Por prioridad y posición, con cada dependencia antes que quien depende de ella."""
        pending = sorted(nodes, key=lambda n: (n.priority, [int(p) for p in n.id.split(".")]))
        ids = {n.id for n in pending}
        result: list[InvestigationNode] = []
        placed: set[str] = set()
        while pending:
            for item in pending:
                if all(d in placed or d not in ids for d in item.depends_on):
                    break
            else:
                item = pending[0]  # ciclo: se rompe por prioridad
            pending.remove(item)
            placed.add(item.id)
            result.append(item)
        return result

    # --- ciclo --------------------------------------------------------------------------------

    def run(self, nodes: list[InvestigationNode], results: dict[str, ExploreResult]) -> Outcome:
        state = {n.id: n for n in nodes}
        stopped: StopReason = "completed"
        for depth in range(self.limits.max_depth + 1):
            level = [n for n in state.values() if n.depth == depth]
            if not level:
                break
            for item in self.ordered([n for n in level if n.status == "pending"]):
                reason = self.stop_reason()
                if reason is not None:
                    return self.finish(state, results, reason)
                state[item.id] = self.calculate(state[item.id], state, results)
            if any(n.status == "computed" and not n.judged for n in state.values()):
                reason = self.stop_reason()
                if reason is not None:
                    return self.finish(state, results, reason)
            children = self.assess(depth, state, results)
            if self.grow(depth, state, results, children):
                stopped = "max_nodes"
        return self.finish(state, results, stopped)

    def calculate(
        self,
        item: InvestigationNode,
        state: dict[str, InvestigationNode],
        results: dict[str, ExploreResult],
    ) -> InvestigationNode:
        blocked = [
            d for d in item.depends_on if d in state and state[d].status in {"rejected", "failed"}
        ]
        if blocked:
            return item.model_copy(
                update={
                    "status": "rejected",
                    "reason": f"Depende de la investigación {blocked[0]}, que no se pudo calcular.",
                    "classification": "inconclusive",
                    "decision": "finish",
                    "decision_reason": "No se calcula sin la investigación de la que depende.",
                }
            )
        query = ExploreQuery.model_validate(item.query)
        try:
            computed = self.compute(query)
        except Exception as error:  # noqa: BLE001 - el fallo de una investigación no para el resto
            return item.model_copy(
                update={
                    "status": "failed",
                    "reason": f"Error de ejecución ({type(error).__name__}): no se pudo calcular.",
                    "execution_id": self.execution_id,
                    "decision": "finish",
                    "decision_reason": "La ejecución falló; el resto de la investigación sigue.",
                }
            )
        if isinstance(computed, str):
            classification, criteria = unanswerable(computed)
            return item.model_copy(
                update={
                    "status": "computed",
                    "reason": computed,
                    "execution_id": self.execution_id,
                    "classification": classification,
                    "criteria": criteria,
                    "judged": True,
                    "decision": "finish",
                    "decision_reason": "Sin resultado que evaluar: " + computed,
                }
            )
        classification, criteria, limitations = evaluate(query, computed, self.total_rows)
        results[computed.key] = computed
        return item.model_copy(
            update={
                "status": "computed",
                "execution_id": self.execution_id,
                "rows_considered": computed.covered_rows,
                "total_rows": self.total_rows,
                "classification": classification,
                "criteria": criteria,
                "limitations": limitations,
            }
        )

    def assess(
        self, depth: int, state: dict[str, InvestigationNode], results: dict[str, ExploreResult]
    ) -> dict[str, list[RawQuery]]:
        """Juicio de la IA sobre los resultados del nivel (si queda presupuesto)."""
        waiting = [
            n
            for n in state.values()
            if n.depth == depth and n.status == "computed" and not n.judged and n.key in results
        ]
        verdicts: dict[str, Verdict] = {}
        if waiting and self.ai_left() and self.judge is not None:
            reply = self.judge([(n, results[n.key or ""]) for n in waiting])
            if reply.called:
                self.ai_calls += 1
                self.cost += reply.cost
            verdicts = reply.verdicts
        elif waiting and self.judge is not None:
            self.note("Se agotó el presupuesto de IA: el resto se evaluó sólo por reglas.")
        children: dict[str, list[RawQuery]] = {}
        for item in waiting:
            verdict = verdicts.get(item.id)
            update: dict[str, object] = {"judged": True}
            criteria = list(item.criteria)
            if verdict is None:
                criteria.append(
                    Criterion(
                        name="business",
                        assessment="Sin juicio de la IA: se clasifica sólo por reglas.",
                    )
                )
            else:
                classification = item.classification
                if not verdict.relevant and classification in {"relevant", "secondary"}:
                    classification = lower(classification)
                criteria.append(
                    Criterion(
                        name="business",
                        assessment=(
                            "La IA lo considera relevante para el negocio."
                            if verdict.relevant
                            else "La IA no lo considera relevante para el negocio."
                        ),
                    )
                )
                update |= {"classification": classification, "interpretation": verdict.reason}
                children[item.id] = verdict.children
            update["criteria"] = criteria
            state[item.id] = item.model_copy(update=update)
        return children

    def grow(
        self,
        depth: int,
        state: dict[str, InvestigationNode],
        results: dict[str, ExploreResult],
        proposed: dict[str, list[RawQuery]],
    ) -> bool:
        """Decide profundizar o terminar en cada resultado del nivel y crea sus hijos. Devuelve
        si se dejó alguna pregunta secundaria por el límite de investigaciones."""
        done = {n.key for n in state.values() if n.key}
        limited = False
        for item in sorted(
            (n for n in state.values() if n.depth == depth and n.decision is None),
            key=lambda n: (n.priority, n.id),
        ):
            classification = item.classification
            label = CLASSES[classification] if classification else "Sin clase"
            if item.status != "computed" or item.key not in results:
                state[item.id] = item.model_copy(
                    update={"decision": "finish", "decision_reason": "Sin resultado que evaluar."}
                )
                continue
            if classification not in {"relevant", "secondary"}:
                state[item.id] = item.model_copy(
                    update={"decision": "finish", "decision_reason": f"{label}: no se profundiza."}
                )
                continue
            if depth >= self.limits.max_depth:
                state[item.id] = item.model_copy(
                    update={
                        "decision": "finish",
                        "decision_reason": "Se alcanzó la profundidad máxima "
                        f"({self.limits.max_depth}).",
                    }
                )
                continue
            query = ExploreQuery.model_validate(item.query)
            drafts = rule_children(item, query, results[item.key or ""], self.catalog) + [
                ai_draft(raw, item.columns) for raw in proposed.get(item.id, [])
            ]
            created = 0
            for draft in drafts:
                if created >= self.limits.max_children:
                    break
                accepted = sum(1 for n in state.values() if n.status != "rejected")
                validated, reason = validate(draft.raw, self.catalog, done)
                if validated is None and draft.origin == "rule":
                    continue  # una pregunta de reglas repetida o no aplicable no es una rama
                if validated is not None and accepted >= self.limits.max_nodes:
                    limited = True
                    self.note(
                        f"Se alcanzó el límite de {self.limits.max_nodes} investigaciones: "
                        "quedaron preguntas secundarias sin abrir."
                    )
                    break
                identifier = (
                    f"{item.id}.{sum(1 for n in state.values() if n.parent == item.id) + 1}"
                )
                child = node(identifier, draft, validated, reason, parent=item.id)
                state[identifier] = child
                if validated is not None:
                    done.add(validated.key)
                    created += 1
            state[item.id] = state[item.id].model_copy(
                update={
                    "decision": "deepen" if created else "finish",
                    "decision_reason": (
                        f"{label}: se abre{'n' if created > 1 else ''} {created} "
                        f"investigaci{'ones' if created > 1 else 'ón'} secundaria"
                        f"{'s' if created > 1 else ''}."
                        if created
                        else f"{label}, pero no hay preguntas secundarias válidas."
                    ),
                }
            )
        return limited

    def finish(
        self,
        state: dict[str, InvestigationNode],
        results: dict[str, ExploreResult],
        stopped: StopReason,
    ) -> Outcome:
        pending = [n for n in state.values() if n.status == "pending"]
        if pending and stopped in {"paused", "max_seconds"}:
            self.note(f"Quedan {len(pending)} investigaciones pendientes: se pueden reanudar.")
        if pending and stopped == "cancelled":
            self.note(f"Se canceló con {len(pending)} investigaciones sin calcular.")
        nodes = sorted(state.values(), key=lambda n: [int(p) for p in n.id.split(".")])
        return Outcome(nodes, results, stopped, self.limitations, self.ai_calls, self.cost)


def plan_nodes(
    drafts: list[Draft], catalog: Catalog, max_nodes: int
) -> tuple[list[InvestigationNode], list[str]]:
    """El plan inicial: cada propuesta validada (o rechazada con su motivo), con su id."""
    done: set[str] = set()
    nodes: list[InvestigationNode] = []
    limitations: list[str] = []
    ids: dict[int, str] = {}
    for index, draft in enumerate(drafts):
        query, reason = validate(draft.raw, catalog, done)
        accepted = sum(1 for n in nodes if n.status != "rejected")
        if query is not None and accepted >= max_nodes:
            limitations.append(
                f"El plan se limitó a {max_nodes} investigaciones; el resto no se calculó."
            )
            break
        identifier = str(len(nodes) + 1)
        ids[index] = identifier
        depends = [ids[d] for d in draft.depends_on if d in ids and d != index]
        nodes.append(node(identifier, draft, query, reason, depends_on=depends))
        if query is not None:
            done.add(query.key)
    return nodes, limitations
