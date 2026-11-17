"""Reglas puras del efecto de una limpieza (sin Polars ni SQL)."""

from dataflow.modules.cleaning.contracts import (
    ApprovalSource,
    ApprovedEffect,
    EffectCounts,
    EffectManifest,
)
from dataflow.modules.executions.public import Lease
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError

MAX_SAMPLES = 50


def effect_sha256(manifest: EffectManifest) -> str:
    return digest("effect", manifest.model_dump(mode="json"))


def check_counts(counts: EffectCounts) -> None:
    """Invariantes de las operaciones v1: ninguna crea ni reordena registros."""
    if (
        counts.output_rows + counts.excluded_rows != counts.input_rows
        or counts.modified_rows > counts.output_rows
        or counts.modified_cells < counts.modified_rows
        or counts.created_nulls > counts.modified_cells
    ):
        raise ApplicationError("EFFECT_INVALID", "Los conteos del efecto son incoherentes.", 409)


def require_same_effect(approved: str, computed: str) -> None:
    if approved != computed:
        raise ApplicationError(
            "PREVIEW_EFFECT_MISMATCH",
            "Los datos, el plan o el sistema cambiaron desde la vista previa. "
            "Genera una vista previa nueva y vuelve a aprobar.",
            409,
        )


def require_valid_approval(approvals: ApprovalSource, lease: Lease) -> ApprovedEffect:
    run = lease.execution
    approved = approvals.approved_effect(run.request_key) if run.request_key else None
    if approved is None or run.plan is None or approved.plan_revision_id != run.plan.id:
        raise ApplicationError(
            "APPROVAL_REQUIRED", "La aplicación requiere una aprobación vigente.", 409
        )
    if approved.revoked:
        raise ApplicationError("APPROVAL_REVOKED", "La aprobación fue revocada.", 409)
    return approved
