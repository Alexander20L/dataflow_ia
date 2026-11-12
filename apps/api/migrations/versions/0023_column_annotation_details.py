"""inspection: textos nulos declarados y decisión sobre datos personales (Fase 23, ADR-040)"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: una tabla nueva junto a `column_annotations` (no se le añaden columnas). Cada fila
    # completa una corrección del diccionario: inmutable y sólo de añadir, como su corrección.
    op.create_table(
        "column_annotation_details",
        sa.Column("annotation_id", sa.Uuid(), nullable=False),
        sa.Column("null_tokens", sa.JSON(), nullable=False),
        sa.Column("personal", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["annotation_id"], ["column_annotations.id"]),
        sa.PrimaryKeyConstraint("annotation_id"),
    )
    op.execute(
        "CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON column_annotation_details "
        "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM column_annotation_details")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen textos nulos o datos personales.")
    op.execute("DROP TRIGGER immutable_record ON column_annotation_details")
    op.drop_table("column_annotation_details")
