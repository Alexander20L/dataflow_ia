"""comprehension: objetivo del análisis elegido por el usuario (Fase 29, ADR-047)"""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: una tabla nueva, inmutable y sólo de añadir (vale el último objetivo de la misma
    # fuente). Una fila sin columna vuelve al objetivo propuesto por las reglas o la IA.
    op.create_table(
        "analysis_targets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("source_key", sa.String(length=700), nullable=False),
        sa.Column("column_name", sa.String(length=200), nullable=True),
        sa.Column("value", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["dataset_version_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("owner_id", "project_id", "version_id", "source_key"):
        op.create_index(
            op.f(f"ix_analysis_targets_{column}"), "analysis_targets", [column], unique=False
        )
    op.execute(
        "CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON analysis_targets "
        "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM analysis_targets")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen objetivos elegidos por el usuario.")
    op.execute("DROP TRIGGER immutable_record ON analysis_targets")
    for column in ("source_key", "version_id", "project_id", "owner_id"):
        op.drop_index(op.f(f"ix_analysis_targets_{column}"), table_name="analysis_targets")
    op.drop_table("analysis_targets")
