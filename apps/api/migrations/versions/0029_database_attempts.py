"""ingestion: intentos de conexión a bases de datos (Fase 32, ADR-050)"""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: sólo huellas de la cuenta, de la IP de origen y del destino, para limitar los
    # intentos por usuario, por día y por destino. No es un registro de auditoría: se purga a
    # las 24 h y se puede borrar sin perder nada del producto.
    op.create_table(
        "database_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_key", sa.String(length=64), nullable=False),
        sa.Column("client_key", sa.String(length=64), nullable=False),
        sa.Column("target_key", sa.String(length=64), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("user_key", "target_key", "created_at"):
        op.create_index(
            op.f(f"ix_database_attempts_{column}"), "database_attempts", [column], unique=False
        )


def downgrade() -> None:
    for column in ("created_at", "target_key", "user_key"):
        op.drop_index(op.f(f"ix_database_attempts_{column}"), table_name="database_attempts")
    op.drop_table("database_attempts")
