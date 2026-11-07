"""automation_policies: versioned automation policy and policy-granted approvals (Fase 11B)"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: sólo tablas nuevas; aprobaciones, planes y versiones existentes no cambian.
    op.create_table(
        "automation_policy_families",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("head_revision", sa.Integer(), nullable=False),
        sa.Column("head_revision_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )
    op.create_index(
        op.f("ix_automation_policy_families_owner_id"),
        "automation_policy_families",
        ["owner_id"],
        unique=False,
    )
    op.create_table(
        "automation_policy_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("previous_revision_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["family_id"], ["automation_policy_families.id"]),
        sa.ForeignKeyConstraint(["previous_revision_id"], ["automation_policy_revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "revision", name="uq_automation_policy_revision"),
    )
    op.create_index(
        op.f("ix_automation_policy_revisions_family_id"),
        "automation_policy_revisions",
        ["family_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_automation_policy_head",
        "automation_policy_families",
        "automation_policy_revisions",
        ["head_revision_id"],
        ["id"],
    )
    op.create_table(
        "automation_policy_save_requests",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["automation_policy_revisions.id"]),
        sa.PrimaryKeyConstraint("owner_id", "scope_id", "request_key"),
    )
    op.create_table(
        "automation_approvals",
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("policy_revision_id", sa.Uuid(), nullable=False),
        sa.Column("preview_execution_id", sa.Uuid(), nullable=False),
        sa.Column("effect_sha256", sa.String(length=64), nullable=False),
        sa.Column("evaluation", sa.JSON(), nullable=False),
        sa.Column("executor", sa.String(length=16), nullable=False),
        sa.Column("pipeline_run_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approval_id"], ["cleaning_approvals.id"]),
        sa.ForeignKeyConstraint(["policy_revision_id"], ["automation_policy_revisions.id"]),
        sa.ForeignKeyConstraint(["preview_execution_id"], ["execution_runs.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("approval_id"),
    )
    op.create_index(
        op.f("ix_automation_approvals_project_id"),
        "automation_approvals",
        ["project_id"],
        unique=False,
    )
    for table in (
        "automation_policy_revisions",
        "automation_policy_save_requests",
        "automation_approvals",
    ):
        op.execute(
            f"CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
        )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM automation_policy_families")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen políticas de automatización.")
    for table in (
        "automation_approvals",
        "automation_policy_save_requests",
        "automation_policy_revisions",
    ):
        op.execute(f"DROP TRIGGER immutable_record ON {table}")
    op.drop_index(op.f("ix_automation_approvals_project_id"), table_name="automation_approvals")
    op.drop_table("automation_approvals")
    op.drop_table("automation_policy_save_requests")
    op.drop_constraint(
        "fk_automation_policy_head", "automation_policy_families", type_="foreignkey"
    )
    op.drop_index(
        op.f("ix_automation_policy_revisions_family_id"),
        table_name="automation_policy_revisions",
    )
    op.drop_table("automation_policy_revisions")
    op.drop_index(
        op.f("ix_automation_policy_families_owner_id"), table_name="automation_policy_families"
    )
    op.drop_table("automation_policy_families")
