"""Contratos de la entrega (Fase 17, ADR-034): informe automático y progreso por etapas.

El informe (`delivery.report@1`, reglas `automatic-report-v1`) sólo reordena lo ya publicado
(hallazgos, investigación, explicación verificada, calidad y limitaciones); no calcula ninguna
cifra y cada cifra conserva su `evidence_id`. El progreso se deriva de los trabajos de la cola.
"""

from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

OPERATION = "delivery.report@1"
RULES = "automatic-report-v1"


class DeliveryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReportTable(DeliveryModel):
    headers: list[str]
    rows: list[list[str]]


class ReportChart(DeliveryModel):
    """Ilustración vectorial de una serie ya calculada; la trazabilidad está en la tabla."""

    type: Literal["bar", "line"]
    title: str
    labels: list[str]
    values: list[str]  # cifras canónicas (Decimal en texto)


class ReportBlock(DeliveryModel):
    title: str | None = None
    badge: str | None = None
    paragraphs: list[str] = Field(default_factory=list)
    table: ReportTable | None = None
    chart: ReportChart | None = None


class ReportSection(DeliveryModel):
    id: str
    title: str
    intro: str | None = None
    blocks: list[ReportBlock]


class ReportSource(DeliveryModel):
    """De dónde sale cada parte del informe (ids y hashes de lo publicado)."""

    project_id: UUID
    version_id: UUID
    version_number: int
    file_name: str
    analysis_execution_id: UUID
    analysis_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    investigation_execution_id: UUID
    investigation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    quality_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ReportDocument(DeliveryModel):
    schema_version: Literal[1] = 1
    operation: Literal["delivery.report@1"] = "delivery.report@1"
    rules_version: Literal["automatic-report-v1"] = "automatic-report-v1"
    title: str
    source: ReportSource
    generated_at: datetime
    sections: list[ReportSection]
    evidence_ids: list[str]


class ReportView(BaseModel):
    """Estado del informe de una versión (sólo lectura)."""

    state: Literal["queued", "running", "ready", "failed"]
    reason: str | None = None
    execution_id: UUID
    file_name: str | None = None
    byte_size: int | None = None
    sha256: str | None = None
    generated_at: datetime | None = None
    evidence_count: int | None = None


StageId = Literal["analysis", "comprehension", "investigation", "report"]
StageState = Literal["pending", "queued", "running", "done", "failed", "skipped"]


class Stage(BaseModel):
    id: StageId
    title: str
    state: StageState
    detail: str
    execution_id: UUID | None = None
    finished_at: datetime | None = None


class Progress(BaseModel):
    """Etapas de una carga en orden; `complete` cuando ninguna queda pendiente."""

    version_id: UUID
    complete: bool
    stages: list[Stage]


class RunSummary(DeliveryModel):
    """Lo que el progreso necesita de un trabajo de la cola (sin depender de executions)."""

    id: UUID
    kind: str
    state: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    error_code: str | None = None
    finished_at: datetime | None = None


class DeliveryAccess(Protocol):
    def report(self, owner: UUID, version: UUID) -> ReportView: ...
    def pdf(self, owner: UUID, version: UUID) -> tuple[bytes, str]: ...
    def progress(self, owner: UUID, version: UUID) -> Progress: ...
