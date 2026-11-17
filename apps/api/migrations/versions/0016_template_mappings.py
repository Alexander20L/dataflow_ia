"""template_mappings: confirmed reusable interpretations (Fase 11D)"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: sólo tablas nuevas.
    op.create_table(
        "template_mapping_families",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("template", sa.String(length=32), nullable=False),
        sa.Column("head_revision", sa.Integer(), nullable=False),
        sa.Column("head_revision_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "template", name="uq_template_mapping_project_template"),
    )
    for column in ("owner_id", "project_id"):
        op.create_index(
            op.f(f"ix_template_mapping_families_{column}"),
            "template_mapping_families",
            [column],
            unique=False,
        )
    op.create_table(
        "template_mapping_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("previous_revision_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["family_id"], ["template_mapping_families.id"]),
        sa.ForeignKeyConstraint(["previous_revision_id"], ["template_mapping_revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "revision", name="uq_template_mapping_revision"),
    )
    op.create_index(
        op.f("ix_template_mapping_revisions_family_id"),
        "template_mapping_revisions",
        ["family_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_template_mapping_head",
        "template_mapping_families",
        "template_mapping_revisions",
        ["head_revision_id"],
        ["id"],
    )
    op.create_table(
        "template_mapping_save_requests",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["template_mapping_revisions.id"]),
        sa.PrimaryKeyConstraint("owner_id", "scope_id", "request_key"),
    )
    for table in ("template_mapping_revisions", "template_mapping_save_requests"):
        op.execute(
            f"CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
        )
    # Interpretación aplicada por cada pipeline: tabla 1:1 aparte (sin columnas nuevas en
    # automation_runs, como exigen los ADR-014 y ADR-015).
    op.create_table(
        "automation_run_interpretations",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("mapping_revision_id", sa.Uuid(), nullable=True),
        sa.Column("semantic_revision_id", sa.Uuid(), nullable=True),
        sa.Column("pass_number", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["automation_runs.id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM template_mapping_families")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen mapeos confirmados.")
    op.drop_table("automation_run_interpretations")
    for table in ("template_mapping_save_requests", "template_mapping_revisions"):
        op.execute(f"DROP TRIGGER immutable_record ON {table}")
    op.drop_table("template_mapping_save_requests")
    op.drop_constraint("fk_template_mapping_head", "template_mapping_families", type_="foreignkey")
    op.drop_index(
        op.f("ix_template_mapping_revisions_family_id"),
        table_name="template_mapping_revisions",
    )
    op.drop_table("template_mapping_revisions")
    for column in ("project_id", "owner_id"):
        op.drop_index(
            op.f(f"ix_template_mapping_families_{column}"),
            table_name="template_mapping_families",
        )
    op.drop_table("template_mapping_families")
