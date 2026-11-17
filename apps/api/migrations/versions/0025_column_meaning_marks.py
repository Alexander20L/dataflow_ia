"""comprehension: columnas marcadas como desconocidas por el usuario (Fase 24B, ADR-042)"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: una tabla nueva junto a `column_meanings` (no se le añaden columnas). Cada fila
    # completa un significado del usuario: inmutable y sólo de añadir, como su significado.
    op.create_table(
        "column_meaning_marks",
        sa.Column("meaning_id", sa.Uuid(), nullable=False),
        sa.Column("unknown", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["meaning_id"], ["column_meanings.id"]),
        sa.PrimaryKeyConstraint("meaning_id"),
    )
    op.execute(
        "CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON column_meaning_marks "
        "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM column_meaning_marks")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen columnas marcadas como desconocidas.")
    op.execute("DROP TRIGGER immutable_record ON column_meaning_marks")
    op.drop_table("column_meaning_marks")
