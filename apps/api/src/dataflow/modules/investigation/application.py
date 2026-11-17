"""Ciclo acotado de la investigación (`investigation-v1`, Fase 16).

Iteración 1: seguimientos por reglas (siempre, también sin IA). Iteraciones siguientes: la IA
propone en un esquema cerrado, Python valida y el motor calcula. Al final la IA explica los
hallazgos y la investigación citando sólo evidencias. Cada límite (iteraciones, llamadas, costo,
tiempo y consultas) corta el ciclo y queda registrado.
"""

from collections.abc import Callable
from decimal import Decimal
from typing import Protocol

from dataflow.modules.analytics.contracts import (
    AutomaticAnalysis,
    FollowUpQuery,
    FollowUpResult,
)
from dataflow.modules.investigation.contracts import (
    Consumption,
    ExplainedFigure,
    ExplanationReply,
    Finding,
    Investigation,
    InvestigationLimits,
    InvestigationScope,
    ModelCall,
    Proposal,
    ProposalContext,
    ProposalReply,
    StopReason,
)
from dataflow.modules.investigation.domain import KINDS, Catalog, rule_queries, validate

MAX_FIGURES = 64


class FollowUps(Protocol):
    def compute(self, queries: list[FollowUpQuery], timeout: float) -> list[FollowUpResult]: ...


class Proposer(Protocol):
    def propose(self, context: ProposalContext) -> ProposalReply: ...


class Explainer(Protocol):
    def explain(
        self, figures: list[ExplainedFigure], limitations: list[str], iteration: int
    ) -> ExplanationReply: ...


class Budget:
    def __init__(self, limits: InvestigationLimits, clock: Callable[[], float]) -> None:
        self.limits, self.clock = limits, clock
        self.start = clock()
        self.calls: list[ModelCall] = []

    @property
    def cost(self) -> Decimal:
        return sum((Decimal(c.cost_usd) for c in self.calls if c.cost_usd), Decimal(0))

    def elapsed(self) -> float:
        return self.clock() - self.start

    def remaining(self) -> float:
        return max(1.0, self.limits.max_seconds - self.elapsed())

    def exhausted(self) -> StopReason | None:
        if len(self.calls) >= self.limits.max_ai_calls:
            return "max_ai_calls"
        if self.cost >= self.limits.cost:
            return "max_cost"
        if self.elapsed() >= self.limits.max_seconds:
            return "max_seconds"
        return None

    def consumption(self) -> Consumption:
        return Consumption(
            ai_calls=len(self.calls),
            cost_usd=str(self.cost),
            elapsed_ms=int(self.elapsed() * 1000),
        )


def explained_figures(
    analysis: AutomaticAnalysis, results: list[FollowUpResult], scope: InvestigationScope
) -> list[ExplainedFigure]:
    """Cifras que la explicación puede citar: las de cada resultado y las de los hallazgos."""
    figures: list[ExplainedFigure] = []
    for result in results:
        if result.insight is None:
            continue
        figures.extend(
            ExplainedFigure(
                evidence_id=figure.evidence_id,
                label=f"{result.insight.title}: {figure.label}",
                value=figure.value,
                unit=figure.unit,
                execution_id=scope.execution_id,
            )
            for figure in result.insight.figures
            if figure.value is not None
        )
    for insight in analysis.insights:
        figures.extend(
            ExplainedFigure(
                evidence_id=figure.evidence_id,
                label=f"{insight.title}: {figure.label}",
                value=figure.value,
                unit=figure.unit,
                execution_id=scope.analysis_execution_id,
            )
            for figure in insight.figures
            if figure.value is not None
        )
    return figures[:MAX_FIGURES]


class Investigator:
    def __init__(
        self,
        followups: FollowUps,
        proposer: Proposer | None,
        explainer: Explainer | None,
        limits: InvestigationLimits,
        clock: Callable[[], float],
        unavailable: str | None = None,
    ) -> None:
        self.followups, self.proposer, self.explainer = followups, proposer, explainer
        self.limits, self.clock = limits, clock
        self.unavailable = unavailable or (None if proposer and explainer else "disabled")

    def run(self, analysis: AutomaticAnalysis, scope: InvestigationScope) -> Investigation:
        budget = Budget(self.limits, self.clock)
        catalog = Catalog(analysis)
        proposals: list[Proposal] = []
        results: list[FollowUpResult] = []
        done: set[str] = set()

        def compute(accepted: list[FollowUpQuery]) -> None:
            if accepted:
                results.extend(self.followups.compute(accepted, budget.remaining()))
                done.update(query.key for query in accepted)

        # Iteración 1: reglas.
        accepted: list[FollowUpQuery] = []
        for query, motive in rule_queries(catalog):
            reason = None
            if query.key in done or query.key in {q.key for q in accepted}:
                continue
            if len(accepted) >= self.limits.max_queries:
                reason = "Se alcanzó el máximo de consultas de la investigación."
            proposals.append(
                Proposal(
                    origin="rule",
                    iteration=1,
                    kind=query.kind,
                    dimension=query.dimension,
                    month=query.month,
                    year=query.year,
                    group=query.group,
                    motive=motive,
                    status="rejected" if reason else "accepted",
                    reason=reason,
                    key=None if reason else query.key,
                )
            )
            if reason is None:
                accepted.append(query)
        compute(accepted)
        iterations = 1
        stopped: StopReason = "max_iterations"
        if not catalog.measure or not catalog.dimensions or not catalog.months:
            stopped = "nothing_to_investigate"
        elif self.unavailable or self.proposer is None:
            stopped = "ai_unavailable"
        else:
            for iteration in range(2, self.limits.max_iterations + 1):
                limit = budget.exhausted()
                if limit is None and len(done) >= self.limits.max_queries:
                    limit = "max_queries"
                if limit is not None:
                    stopped = limit
                    break
                iterations = iteration
                reply = self.proposer.propose(
                    ProposalContext(
                        iteration=iteration,
                        measure=catalog.measure,
                        kinds=KINDS,
                        dimensions=catalog.dimensions,
                        months=catalog.months,
                        years=catalog.years,
                        groups=catalog.groups,
                        # Resultados ya calculados: la IA los lee para proponer el siguiente
                        # paso, nunca para citar cifras.
                        findings=catalog.findings()
                        + [
                            Finding(
                                id=result.key,
                                title=result.insight.title,
                                statement=result.insight.statement,
                            )
                            for result in results
                            if result.insight
                        ],
                        done=sorted(done),
                        max_proposals=self.limits.max_proposals_per_call,
                    )
                )
                if reply.call is not None:
                    budget.calls.append(reply.call)
                if reply.error is not None:
                    stopped = "ai_error"
                    break
                accepted = []
                for raw in reply.proposals[: self.limits.max_proposals_per_call]:
                    candidate, reason = validate(raw, catalog, done | {q.key for q in accepted})
                    if (
                        candidate is not None
                        and len(done) + len(accepted) >= self.limits.max_queries
                    ):
                        candidate, reason = None, "Se alcanzó el máximo de consultas."
                    proposals.append(
                        Proposal(
                            origin="ai",
                            iteration=iteration,
                            kind=raw.kind,
                            dimension=raw.dimension,
                            month=raw.month,
                            year=raw.year,
                            group=raw.group,
                            motive=raw.motive or "Sin motivo.",
                            status="accepted" if candidate else "rejected",
                            reason=reason,
                            key=candidate.key if candidate else None,
                        )
                    )
                    if candidate is not None:
                        accepted.append(candidate)
                if not accepted:
                    stopped = "no_new_proposals"
                    break
                compute(accepted)
        limitations = [
            "Cada cifra la calcula el motor determinista; la IA sólo propone qué investigar y "
            "explica resultados ya calculados.",
            "Las asociaciones con grupos no demuestran causas.",
        ]
        explanation = ExplanationReply(state="unavailable", reason=self.unavailable or "disabled")
        if self.explainer is not None and not self.unavailable:
            limit = budget.exhausted()
            if limit is not None:
                explanation = ExplanationReply(state="unavailable", reason=limit)
            else:
                explanation = self.explainer.explain(
                    explained_figures(analysis, results, scope),
                    [*limitations, *analysis.limitations],
                    iterations + 1,
                )
                if explanation.call is not None:
                    budget.calls.append(explanation.call)
        return Investigation(
            scope=scope,
            limits=self.limits,
            iterations=iterations,
            proposals=proposals,
            results=results,
            calls=budget.calls,
            consumption=budget.consumption(),
            stopped=stopped,
            ai="unavailable" if self.unavailable else "available",
            ai_reason=self.unavailable,
            explanation_state=explanation.state,
            explanation_reason=explanation.reason,
            explanation=explanation.content,
            limitations=limitations,
        )
