"""ingestion: copias de bases en segundo plano (Fase 33, ADR-051)"""

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva. El estado de cada copia de base en segundo plano, sin credenciales: la contraseña
    # sólo vive en la memoria de la API mientras dura la copia.
    op.create_table(
        "database_copies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("engine", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("server", sa.String(length=300), nullable=False),
        sa.Column("database_name", sa.String(length=128), nullable=False),
        sa.Column("schema_name", sa.String(length=128), nullable=True),
        sa.Column("tables", sa.Integer(), nullable=True),
        sa.Column("omitted", sa.Integer(), nullable=True),
        sa.Column("version_id", sa.Uuid(), nullable=True),
        sa.Column("model", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("owner_id", "project_id"):
        op.create_index(
            op.f(f"ix_database_copies_{column}"), "database_copies", [column], unique=False
        )


def downgrade() -> None:
    for column in ("project_id", "owner_id"):
        op.drop_index(op.f(f"ix_database_copies_{column}"), table_name="database_copies")
    op.drop_table("database_copies")
