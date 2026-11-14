"""planning: user plan bindings to exact tables and persisted validations"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TABLES = ["execution_plan_bindings", "planning_validations", "planning_create_requests"]


def upgrade() -> None:
    # Aditiva: sólo tablas nuevas; execution_plan_revisions y los planes 0.5 no cambian.
    op.create_table(
        "execution_plan_bindings",
        sa.Column("plan_revision_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("input_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("input_artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("semantic_revision_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["input_artifact_id"],
            ["execution_artifacts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["plan_revision_id"],
            ["execution_plan_revisions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.ForeignKeyConstraint(
            ["semantic_revision_id"],
            ["semantic_revisions.id"],
        ),
        sa.PrimaryKeyConstraint("plan_revision_id"),
    )
    op.create_index(
        op.f("ix_execution_plan_bindings_project_id"),
        "execution_plan_bindings",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "planning_validations",
        sa.Column("plan_revision_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_version", sa.String(length=40), nullable=False),
        sa.Column("problems", sa.JSON(), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["plan_revision_id"],
            ["execution_plan_revisions.id"],
        ),
        sa.PrimaryKeyConstraint("plan_revision_id", "catalog_version"),
    )
    op.create_table(
        "planning_create_requests",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("plan_revision_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["identity_users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["plan_revision_id"],
            ["execution_plan_revisions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("project_id", "request_key"),
    )
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
        )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text("SELECT count(*) FROM execution_plan_bindings")
    ) or connection.scalar(sa.text("SELECT count(*) FROM planning_validations")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen planes de usuario o validaciones.")
    for table in TABLES:
        op.execute(f"DROP TRIGGER immutable_record ON {table}")
    op.drop_table("planning_create_requests")
    op.drop_table("planning_validations")
    op.drop_index(
        op.f("ix_execution_plan_bindings_project_id"), table_name="execution_plan_bindings"
    )
    op.drop_table("execution_plan_bindings")
