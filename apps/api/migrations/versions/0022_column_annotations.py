"""inspection: correcciones manuales del diccionario de datos (Fase 22, ADR-039)"""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: una tabla nueva, inmutable y sólo de añadir (vale la última corrección de cada
    # columna de la misma fuente). Nunca modifica el archivo ni los resultados calculados.
    op.create_table(
        "column_annotations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("source_key", sa.String(length=700), nullable=False),
        sa.Column("column_name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=True),
        sa.Column("nature", sa.String(length=20), nullable=True),
        sa.Column("time_format", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["dataset_version_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("owner_id", "project_id", "version_id"):
        op.create_index(
            op.f(f"ix_column_annotations_{column}"), "column_annotations", [column], unique=False
        )
    op.execute(
        "CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON column_annotations "
        "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM column_annotations")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen correcciones del diccionario.")
    op.execute("DROP TRIGGER immutable_record ON column_annotations")
    for column in ("version_id", "project_id", "owner_id"):
        op.drop_index(op.f(f"ix_column_annotations_{column}"), table_name="column_annotations")
    op.drop_table("column_annotations")
