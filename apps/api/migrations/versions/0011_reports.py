"""reports: report revisions and PDF renders"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

IMMUTABLE = ("report_revisions", "report_save_requests", "report_renders")


def upgrade() -> None:
    # Aditiva: sólo tablas nuevas; ejecuciones, dashboards y versiones existentes no cambian.
    op.create_table(
        "report_families",
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
            op.f(f"ix_report_families_{column}"), "report_families", [column], unique=False
        )
    op.create_table(
        "report_revisions",
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
        sa.ForeignKeyConstraint(["family_id"], ["report_families.id"]),
        sa.ForeignKeyConstraint(["previous_revision_id"], ["report_revisions.id"]),
        sa.ForeignKeyConstraint(["refreshed_version_id"], ["dataset_version_records.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "revision", name="uq_report_family_revision"),
    )
    op.create_index(
        op.f("ix_report_revisions_family_id"), "report_revisions", ["family_id"], unique=False
    )
    op.create_foreign_key(
        "fk_report_head", "report_families", "report_revisions", ["head_revision_id"], ["id"]
    )
    op.create_table(
        "report_save_requests",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["report_revisions.id"]),
        sa.PrimaryKeyConstraint("owner_id", "scope_id", "request_key"),
    )
    op.create_table(
        "report_renders",
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["execution_id"], ["execution_runs.id"]),
        sa.ForeignKeyConstraint(["family_id"], ["report_families.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["report_revisions.id"]),
        sa.PrimaryKeyConstraint("execution_id"),
    )
    for column in ("family_id", "owner_id"):
        op.create_index(
            op.f(f"ix_report_renders_{column}"), "report_renders", [column], unique=False
        )
    for table in IMMUTABLE:
        op.execute(
            f"CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
        )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM report_families")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen informes.")
    for table in IMMUTABLE:
        op.execute(f"DROP TRIGGER immutable_record ON {table}")
    for column in ("owner_id", "family_id"):
        op.drop_index(op.f(f"ix_report_renders_{column}"), table_name="report_renders")
    op.drop_table("report_renders")
    op.drop_table("report_save_requests")
    op.drop_constraint("fk_report_head", "report_families", type_="foreignkey")
    op.drop_index(op.f("ix_report_revisions_family_id"), table_name="report_revisions")
    op.drop_table("report_revisions")
    for column in ("project_id", "owner_id"):
        op.drop_index(op.f(f"ix_report_families_{column}"), table_name="report_families")
    op.drop_table("report_families")
