"""curation: valoración «sí va / no va» de los hallazgos del dashboard (Fase 21, ADR-038)"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: una tabla nueva, inmutable y sólo de añadir (vale la última valoración).
    op.create_table(
        "finding_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("item_key", sa.String(length=700), nullable=False),
        sa.Column("verdict", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["dataset_version_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("owner_id", "project_id", "version_id"):
        op.create_index(
            op.f(f"ix_finding_feedback_{column}"), "finding_feedback", [column], unique=False
        )
    op.execute(
        "CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON finding_feedback "
        "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM finding_feedback")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen valoraciones de hallazgos.")
    op.execute("DROP TRIGGER immutable_record ON finding_feedback")
    for column in ("version_id", "project_id", "owner_id"):
        op.drop_index(op.f(f"ix_finding_feedback_{column}"), table_name="finding_feedback")
    op.drop_table("finding_feedback")
