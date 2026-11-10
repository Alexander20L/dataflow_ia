"""comprehension: valoraciones del usuario sobre las relaciones (Fase 19, ADR-036)"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: una tabla nueva, inmutable y sólo de añadir (vale la última valoración).
    op.create_table(
        "comprehension_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("source_key", sa.String(length=600), nullable=False),
        sa.Column("relationship_key", sa.String(length=400), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["dataset_version_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("owner_id", "project_id", "version_id", "source_key"):
        op.create_index(
            op.f(f"ix_comprehension_feedback_{column}"),
            "comprehension_feedback",
            [column],
            unique=False,
        )
    op.execute(
        "CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON comprehension_feedback "
        "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM comprehension_feedback")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen valoraciones de relaciones.")
    op.execute("DROP TRIGGER immutable_record ON comprehension_feedback")
    for column in ("source_key", "version_id", "project_id", "owner_id"):
        op.drop_index(
            op.f(f"ix_comprehension_feedback_{column}"), table_name="comprehension_feedback"
        )
    op.drop_table("comprehension_feedback")
