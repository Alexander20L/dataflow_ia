"""quality rulesets: user-configured csv-quality-v2 rules as immutable revisions"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: sólo tablas nuevas; planes, ejecuciones, versiones y diagnósticos no cambian.
    op.create_table(
        "quality_ruleset_families",
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
        sa.UniqueConstraint("base_artifact_id"),
    )
    op.create_index(
        op.f("ix_quality_ruleset_families_owner_id"),
        "quality_ruleset_families",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quality_ruleset_families_project_id"),
        "quality_ruleset_families",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "quality_ruleset_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("previous_revision_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["family_id"], ["quality_ruleset_families.id"]),
        sa.ForeignKeyConstraint(["previous_revision_id"], ["quality_ruleset_revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "revision", name="uq_quality_ruleset_family_revision"),
    )
    op.create_index(
        op.f("ix_quality_ruleset_revisions_family_id"),
        "quality_ruleset_revisions",
        ["family_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_quality_ruleset_head",
        "quality_ruleset_families",
        "quality_ruleset_revisions",
        ["head_revision_id"],
        ["id"],
    )
    op.create_table(
        "quality_ruleset_save_requests",
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["quality_ruleset_families.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["quality_ruleset_revisions.id"]),
        sa.PrimaryKeyConstraint("family_id", "request_key"),
    )
    for table in ("quality_ruleset_revisions", "quality_ruleset_save_requests"):
        op.execute(
            f"CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
        )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM quality_ruleset_families")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen conjuntos de reglas de calidad.")
    for table in ("quality_ruleset_save_requests", "quality_ruleset_revisions"):
        op.execute(f"DROP TRIGGER immutable_record ON {table}")
    op.drop_table("quality_ruleset_save_requests")
    op.drop_constraint("fk_quality_ruleset_head", "quality_ruleset_families", type_="foreignkey")
    op.drop_index(
        op.f("ix_quality_ruleset_revisions_family_id"), table_name="quality_ruleset_revisions"
    )
    op.drop_table("quality_ruleset_revisions")
    op.drop_index(
        op.f("ix_quality_ruleset_families_project_id"), table_name="quality_ruleset_families"
    )
    op.drop_index(
        op.f("ix_quality_ruleset_families_owner_id"), table_name="quality_ruleset_families"
    )
    op.drop_table("quality_ruleset_families")
