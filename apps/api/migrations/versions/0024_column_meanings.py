"""comprehension: significados de columnas escritos por el usuario (Fase 24, ADR-041)"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: una tabla nueva, inmutable y sólo de añadir (vale el último significado de cada
    # columna de la misma fuente). Nunca cambia un cálculo: sólo cómo se describe la columna.
    op.create_table(
        "column_meanings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("source_key", sa.String(length=700), nullable=False),
        sa.Column("column_name", sa.String(length=200), nullable=False),
        sa.Column("meaning", sa.String(length=300), nullable=True),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["dataset_version_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("owner_id", "project_id", "version_id", "source_key"):
        op.create_index(
            op.f(f"ix_column_meanings_{column}"), "column_meanings", [column], unique=False
        )
    op.execute(
        "CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON column_meanings "
        "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM column_meanings")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen significados escritos por el usuario.")
    op.execute("DROP TRIGGER immutable_record ON column_meanings")
    for column in ("source_key", "version_id", "project_id", "owner_id"):
        op.drop_index(op.f(f"ix_column_meanings_{column}"), table_name="column_meanings")
    op.drop_table("column_meanings")
