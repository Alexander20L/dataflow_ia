"""execution error details: structured detail of failed attempts (strict conversions)"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: sólo una tabla nueva; ejecuciones, intentos y versiones existentes no cambian.
    op.create_table(
        "execution_error_details",
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["execution_attempts.id"]),
        sa.ForeignKeyConstraint(["execution_id"], ["execution_runs.id"]),
        sa.PrimaryKeyConstraint("attempt_id"),
    )
    op.create_index(
        op.f("ix_execution_error_details_execution_id"),
        "execution_error_details",
        ["execution_id"],
        unique=False,
    )
    op.execute(
        "CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON execution_error_details "
        "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM execution_error_details")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen detalles de errores de ejecución.")
    op.execute("DROP TRIGGER immutable_record ON execution_error_details")
    op.drop_index(
        op.f("ix_execution_error_details_execution_id"), table_name="execution_error_details"
    )
    op.drop_table("execution_error_details")
