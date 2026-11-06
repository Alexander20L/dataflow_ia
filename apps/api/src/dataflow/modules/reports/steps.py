"""Ejecutor de reports.render_pdf@1 (operación interna, fuera del catálogo de usuario)."""

from pathlib import Path
from uuid import uuid4

from dataflow.modules.datasets.public import ObjectStore
from dataflow.modules.executions.public import (
    ArtifactKind,
    ArtifactOutput,
    Lease,
    PlanStepSpec,
    StepInput,
    StepResult,
)
from dataflow.platform.errors import ApplicationError
from dataflow.platform.isolation import run_isolated

MODULE = "dataflow.modules.reports.processor"


class RenderReportStep:
    """Recibe la instantánea del informe (entrada `report`) y publica el PDF como artefacto."""

    output_kind: ArtifactKind = "report_pdf"
    transforms_data = False

    def __init__(self, objects: ObjectStore, root: Path) -> None:
        self.objects, self.root = objects, root

    def compute(
        self, lease: Lease, step: PlanStepSpec, source: StepInput, timeout: float
    ) -> StepResult:
        if source.kind != "report":
            raise ApplicationError("INPUT_KIND_MISMATCH", "El PDF requiere un informe.", 409)
        files = run_isolated(
            self.root,
            MODULE,
            {"snapshot.json": self.objects.read(source.content)},
            ["--input", "{dir}/snapshot.json"],
            ["report.pdf"],
            timeout,
        )
        prefix = f"artifacts/{lease.owner_id}/{lease.version_id}/{lease.token}/{step.id}"
        content = self.objects.put(f"{prefix}/report.pdf", files["report.pdf"])
        return StepResult(
            [
                ArtifactOutput(
                    uuid4(),
                    step.id,
                    "report_pdf",
                    "report_pdf",
                    content,
                    "application/pdf",
                    0,  # un PDF no tiene filas ni columnas
                    0,
                )
            ]
        )
