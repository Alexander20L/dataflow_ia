"""cleaning: approvals of exact effects and derived version lineage"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: sólo tablas nuevas; versiones, ejecuciones y planes existentes no cambian.
    op.create_table(
        "cleaning_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_revision_id", sa.Uuid(), nullable=False),
        sa.Column("preview_execution_id", sa.Uuid(), nullable=False),
        sa.Column("effect_sha256", sa.String(length=64), nullable=False),
        sa.Column("input_artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("semantic_revision_id", sa.Uuid(), nullable=True),
        sa.Column("config_sha256", sa.String(length=64), nullable=False),
        sa.Column("environment_sha256", sa.String(length=64), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["identity_users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["plan_revision_id"],
            ["execution_plan_revisions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["preview_execution_id"],
            ["execution_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["semantic_revision_id"],
            ["semantic_revisions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_cleaning_approvals_plan_revision_id"),
        "cleaning_approvals",
        ["plan_revision_id"],
        unique=False,
    )
    op.create_index(
        "uq_cleaning_approval_active",
        "cleaning_approvals",
        ["preview_execution_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_table(
        "dataset_version_lineage",
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("parent_version_id", sa.Uuid(), nullable=False),
        sa.Column("producer_execution_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_version_id"],
            ["dataset_version_records.id"],
        ),
        sa.ForeignKeyConstraint(
            ["producer_execution_id"],
            ["execution_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["dataset_version_records.id"],
        ),
        sa.PrimaryKeyConstraint("version_id"),
        sa.UniqueConstraint("producer_execution_id"),
    )
    op.create_index(
        op.f("ix_dataset_version_lineage_parent_version_id"),
        "dataset_version_lineage",
        ["parent_version_id"],
        unique=False,
    )
    op.execute(
        "CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON dataset_version_lineage "
        "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
    )
    # Una aprobación sólo puede revocarse (revoked_at NULL → fecha); nada más cambia ni se borra.
    op.execute("""
        CREATE FUNCTION dataflow_cleaning_approval_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' OR OLD.revoked_at IS NOT NULL OR NEW.revoked_at IS NULL OR
             ROW(NEW.id, NEW.plan_revision_id, NEW.preview_execution_id, NEW.effect_sha256,
                 NEW.input_artifact_sha256, NEW.semantic_revision_id, NEW.config_sha256,
                 NEW.environment_sha256, NEW.approved_by, NEW.approved_at) IS DISTINCT FROM
             ROW(OLD.id, OLD.plan_revision_id, OLD.preview_execution_id, OLD.effect_sha256,
                 OLD.input_artifact_sha256, OLD.semantic_revision_id, OLD.config_sha256,
                 OLD.environment_sha256, OLD.approved_by, OLD.approved_at) THEN
            RAISE EXCEPTION 'IMMUTABLE_APPROVAL' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
    """)
    op.execute(
        "CREATE TRIGGER approval_guard BEFORE UPDATE OR DELETE ON cleaning_approvals "
        "FOR EACH ROW EXECUTE FUNCTION dataflow_cleaning_approval_guard()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM cleaning_approvals")) or connection.scalar(
        sa.text("SELECT count(*) FROM dataset_version_lineage")
    ):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen aprobaciones o versiones derivadas.")
    op.execute("DROP TRIGGER approval_guard ON cleaning_approvals")
    op.execute("DROP FUNCTION dataflow_cleaning_approval_guard()")
    op.execute("DROP TRIGGER immutable_record ON dataset_version_lineage")
    op.drop_index(
        op.f("ix_dataset_version_lineage_parent_version_id"), table_name="dataset_version_lineage"
    )
    op.drop_table("dataset_version_lineage")
    op.drop_index("uq_cleaning_approval_active", table_name="cleaning_approvals")
    op.drop_index(op.f("ix_cleaning_approvals_plan_revision_id"), table_name="cleaning_approvals")
    op.drop_table("cleaning_approvals")
