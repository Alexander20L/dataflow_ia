"""automation_run_analyses: automatic dashboard of each pipeline (Fase 11E)"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: una tabla nueva 1:1 con el pipeline; dashboards, métricas y planes no cambian.
    op.create_table(
        "automation_run_analyses",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("template", sa.String(length=32), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("dashboard_family_id", sa.Uuid(), nullable=True),
        sa.Column("dashboard_revision_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["automation_runs.id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        op.f("ix_automation_run_analyses_project_id"),
        "automation_run_analyses",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM automation_run_analyses")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen dashboards automáticos.")
    op.drop_index(
        op.f("ix_automation_run_analyses_project_id"), table_name="automation_run_analyses"
    )
    op.drop_table("automation_run_analyses")
