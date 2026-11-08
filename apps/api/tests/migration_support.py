"""Apoyo de las pruebas de migraciones.

Las pruebas de migraciones anteriores comparan su esquema con los modelos registrados. Las tablas
creadas por migraciones posteriores a 0012 todavía no existen en esas revisiones y se excluyen de
la comparación; cada migración nueva añade aquí sus tablas.

Las tablas del pipeline por política (0013-0017) ya no tienen modelos: la migración 0019 (Fase 13,
ADR-026) las elimina. Al comparar una revisión anterior a 0019 se excluyen.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from dataflow.modules.dashboards.infrastructure import (
    DashboardFamilyRecord,
    DashboardRevisionRecord,
    DashboardSaveRequest,
)
from dataflow.modules.reports.infrastructure import (
    ReportFamilyRecord,
    ReportRevisionRecord,
    ReportSaveRequest,
)

TABLES_AFTER_0012 = {
    # 0018: auditorías textuales guardadas (11F)
    "copilot_text_audits",
}

# Tablas creadas en 0013-0017 y eliminadas por 0019.
RETIRED_IN_0019 = {
    "analysis_sessions",
    "analysis_session_input_revisions",
    "automation_policy_families",
    "automation_policy_revisions",
    "automation_policy_save_requests",
    "automation_approvals",
    "automation_runs",
    "automation_step_attempts",
    "template_mapping_families",
    "template_mapping_revisions",
    "template_mapping_save_requests",
    "automation_run_interpretations",
    "automation_run_analyses",
}


def table_of(obj: object, name: str | None, type_: str) -> str | None:
    return name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)


def exists_at_0012(
    obj: object, name: str | None, type_: str, reflected: bool, other: object
) -> bool:
    return table_of(obj, name, type_) not in TABLES_AFTER_0012


def modelled_before_0019(
    obj: object, name: str | None, type_: str, reflected: bool, other: object
) -> bool:
    return table_of(obj, name, type_) not in RETIRED_IN_0019


def insert_dashboard(db: Session, owner: UUID, project: UUID) -> UUID:
    """Una revisión de dashboard (Fase 8) con su solicitud idempotente, sin el servicio retirado
    en la Fase 13: las tablas se conservan y sus garantías se siguen probando."""
    family, revision, now = uuid4(), uuid4(), datetime.now(UTC)
    db.add(
        DashboardFamilyRecord(
            id=family,
            project_id=project,
            owner_id=owner,
            head_revision=1,
            head_revision_id=None,
            created_at=now,
        )
    )
    db.flush()
    db.add(
        DashboardRevisionRecord(
            id=revision,
            family_id=family,
            revision=1,
            previous_revision_id=None,
            cause="create",
            refreshed_version_id=None,
            content={"title": "Ventas", "cards": []},
            content_sha256="d" * 64,
            created_by=owner,
            created_at=now,
        )
    )
    db.flush()
    db.add(
        DashboardSaveRequest(
            owner_id=owner,
            scope_id=project,
            request_key=uuid4(),
            fingerprint="f" * 64,
            revision_id=revision,
        )
    )
    db.flush()
    return revision


def insert_report(db: Session, owner: UUID, project: UUID) -> UUID:
    """Una revisión de informe (Fase 9) con su solicitud idempotente (ver `insert_dashboard`)."""
    family, revision, now = uuid4(), uuid4(), datetime.now(UTC)
    db.add(
        ReportFamilyRecord(
            id=family,
            project_id=project,
            owner_id=owner,
            head_revision=1,
            head_revision_id=None,
            created_at=now,
        )
    )
    db.flush()
    db.add(
        ReportRevisionRecord(
            id=revision,
            family_id=family,
            revision=1,
            previous_revision_id=None,
            cause="create",
            refreshed_version_id=None,
            content={"title": "Informe", "blocks": []},
            content_sha256="r" * 64,
            created_by=owner,
            created_at=now,
        )
    )
    db.flush()
    db.add(
        ReportSaveRequest(
            owner_id=owner,
            scope_id=project,
            request_key=uuid4(),
            fingerprint="f" * 64,
            revision_id=revision,
        )
    )
    db.flush()
    return revision
