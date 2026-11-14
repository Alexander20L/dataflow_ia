"""exploration: peticiones de pausa o cancelación de una investigación (Fase 25, ADR-043)"""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: una tabla nueva, inmutable y sólo de añadir. Cada fila es una petición del usuario
    # sobre una ejecución de investigación; el trabajo la mira entre una investigación y otra.
    op.create_table(
        "investigation_controls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('pause', 'cancel')", name="ck_investigation_control_action"),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["execution_id"], ["execution_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_investigation_controls_execution_id", "investigation_controls", ["execution_id"]
    )
    op.execute(
        "CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON investigation_controls "
        "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM investigation_controls")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen peticiones de control registradas.")
    op.execute("DROP TRIGGER immutable_record ON investigation_controls")
    op.drop_index("ix_investigation_controls_execution_id", table_name="investigation_controls")
    op.drop_table("investigation_controls")
