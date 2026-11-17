"""automation_runs: durable automatic pipeline and immutable step log (Fase 11C)"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: sólo tablas nuevas; el pipeline referencia lo que crean los casos de uso.
    op.create_table(
        "automation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("policy_revision_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("step", sa.String(length=16), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("plan_revision_id", sa.Uuid(), nullable=True),
        sa.Column("preview_execution_id", sa.Uuid(), nullable=True),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("apply_execution_id", sa.Uuid(), nullable=True),
        sa.Column("derived_version_id", sa.Uuid(), nullable=True),
        sa.Column("rules_execution_id", sa.Uuid(), nullable=True),
        sa.Column("result_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["policy_revision_id"], ["automation_policy_revisions.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["dataset_version_records.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", name="uq_automation_run_version"),
    )
    for column in ("owner_id", "project_id", "state"):
        op.create_index(
            op.f(f"ix_automation_runs_{column}"), "automation_runs", [column], unique=False
        )
    op.create_table(
        "automation_step_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("step", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["automation_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_automation_step_attempt_sequence"),
    )
    op.create_index(
        op.f("ix_automation_step_attempts_run_id"),
        "automation_step_attempts",
        ["run_id"],
        unique=False,
    )
    op.execute(
        "CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON automation_step_attempts "
        "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM automation_runs")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen pipelines automáticos.")
    op.execute("DROP TRIGGER immutable_record ON automation_step_attempts")
    op.drop_index(op.f("ix_automation_step_attempts_run_id"), table_name="automation_step_attempts")
    op.drop_table("automation_step_attempts")
    for column in ("state", "project_id", "owner_id"):
        op.drop_index(op.f(f"ix_automation_runs_{column}"), table_name="automation_runs")
    op.drop_table("automation_runs")
