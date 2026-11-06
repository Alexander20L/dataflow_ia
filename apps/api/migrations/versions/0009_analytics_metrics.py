"""analytics metrics: user-defined metrics as immutable revisions"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: sólo tablas nuevas; planes, ejecuciones, versiones y diagnósticos no cambian.
    op.create_table(
        "analytics_metric_families",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("base_version_id", sa.Uuid(), nullable=False),
        sa.Column("base_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("base_sha256", sa.String(length=64), nullable=False),
        sa.Column("head_revision", sa.Integer(), nullable=False),
        sa.Column("head_revision_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["base_artifact_id"], ["execution_artifacts.id"]),
        sa.ForeignKeyConstraint(["base_version_id"], ["dataset_version_records.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("owner_id", "project_id"):
        op.create_index(
            op.f(f"ix_analytics_metric_families_{column}"),
            "analytics_metric_families",
            [column],
            unique=False,
        )
    op.create_table(
        "analytics_metric_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("previous_revision_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["family_id"], ["analytics_metric_families.id"]),
        sa.ForeignKeyConstraint(["previous_revision_id"], ["analytics_metric_revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "revision", name="uq_analytics_metric_family_revision"),
    )
    op.create_index(
        op.f("ix_analytics_metric_revisions_family_id"),
        "analytics_metric_revisions",
        ["family_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_analytics_metric_head",
        "analytics_metric_families",
        "analytics_metric_revisions",
        ["head_revision_id"],
        ["id"],
    )
    op.create_table(
        "analytics_metric_save_requests",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["analytics_metric_revisions.id"]),
        sa.PrimaryKeyConstraint("owner_id", "scope_id", "request_key"),
    )
    for table in ("analytics_metric_revisions", "analytics_metric_save_requests"):
        op.execute(
            f"CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
        )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM analytics_metric_families")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen métricas de análisis.")
    for table in ("analytics_metric_save_requests", "analytics_metric_revisions"):
        op.execute(f"DROP TRIGGER immutable_record ON {table}")
    op.drop_table("analytics_metric_save_requests")
    op.drop_constraint("fk_analytics_metric_head", "analytics_metric_families", type_="foreignkey")
    op.drop_index(
        op.f("ix_analytics_metric_revisions_family_id"), table_name="analytics_metric_revisions"
    )
    op.drop_table("analytics_metric_revisions")
    for column in ("project_id", "owner_id"):
        op.drop_index(
            op.f(f"ix_analytics_metric_families_{column}"), table_name="analytics_metric_families"
        )
    op.drop_table("analytics_metric_families")
