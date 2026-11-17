"""dashboards: persisted dashboards as immutable revisions"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: sólo tablas nuevas; planes, ejecuciones, métricas y versiones no cambian.
    op.create_table(
        "dashboard_families",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("head_revision", sa.Integer(), nullable=False),
        sa.Column("head_revision_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("owner_id", "project_id"):
        op.create_index(
            op.f(f"ix_dashboard_families_{column}"), "dashboard_families", [column], unique=False
        )
    op.create_table(
        "dashboard_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("previous_revision_id", sa.Uuid(), nullable=True),
        sa.Column("cause", sa.String(length=16), nullable=False),
        sa.Column("refreshed_version_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["family_id"], ["dashboard_families.id"]),
        sa.ForeignKeyConstraint(["previous_revision_id"], ["dashboard_revisions.id"]),
        sa.ForeignKeyConstraint(["refreshed_version_id"], ["dataset_version_records.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "revision", name="uq_dashboard_family_revision"),
    )
    op.create_index(
        op.f("ix_dashboard_revisions_family_id"), "dashboard_revisions", ["family_id"], unique=False
    )
    op.create_foreign_key(
        "fk_dashboard_head",
        "dashboard_families",
        "dashboard_revisions",
        ["head_revision_id"],
        ["id"],
    )
    op.create_table(
        "dashboard_save_requests",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["dashboard_revisions.id"]),
        sa.PrimaryKeyConstraint("owner_id", "scope_id", "request_key"),
    )
    for table in ("dashboard_revisions", "dashboard_save_requests"):
        op.execute(
            f"CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
        )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM dashboard_families")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen dashboards.")
    for table in ("dashboard_save_requests", "dashboard_revisions"):
        op.execute(f"DROP TRIGGER immutable_record ON {table}")
    op.drop_table("dashboard_save_requests")
    op.drop_constraint("fk_dashboard_head", "dashboard_families", type_="foreignkey")
    op.drop_index(op.f("ix_dashboard_revisions_family_id"), table_name="dashboard_revisions")
    op.drop_table("dashboard_revisions")
    for column in ("project_id", "owner_id"):
        op.drop_index(op.f(f"ix_dashboard_families_{column}"), table_name="dashboard_families")
    op.drop_table("dashboard_families")
