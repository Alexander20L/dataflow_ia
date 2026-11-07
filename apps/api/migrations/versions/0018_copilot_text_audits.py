"""copilot: saved text audits of published dashboard revisions (Fase 11F)

Encadenada detrás de 0017 (Fase 11E) al integrarse con las entregas 11A–11E.
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: una tabla nueva; dashboards, ejecuciones y llamadas del copiloto no cambian.
    op.create_table(
        "copilot_text_audits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("dashboard_revision_id", sa.Uuid(), nullable=False),
        sa.Column("audit_key", sa.String(length=64), nullable=False),
        sa.Column("result_sha256", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("prompt_id", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("cards", sa.JSON(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["call_id"], ["copilot_ai_calls.id"]),
        sa.ForeignKeyConstraint(["dashboard_revision_id"], ["dashboard_revisions.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dashboard_revision_id", "audit_key", name="uq_copilot_text_audit_key"),
    )
    for column in ("owner_id", "project_id", "dashboard_revision_id"):
        op.create_index(
            op.f(f"ix_copilot_text_audits_{column}"), "copilot_text_audits", [column], unique=False
        )
    op.execute(
        "CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON copilot_text_audits "
        "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM copilot_text_audits")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen auditorías textuales guardadas.")
    op.execute("DROP TRIGGER immutable_record ON copilot_text_audits")
    for column in ("dashboard_revision_id", "project_id", "owner_id"):
        op.drop_index(op.f(f"ix_copilot_text_audits_{column}"), table_name="copilot_text_audits")
    op.drop_table("copilot_text_audits")
