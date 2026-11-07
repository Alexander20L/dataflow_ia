"""ingestion_connections + ingestion_extractions: SQL Server (Fase 12B)"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: tablas nuevas; versiones, planes y ejecuciones no cambian.
    op.create_table(
        "ingestion_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("database", sa.String(length=128), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("password_ciphertext", sa.Text(), nullable=False),
        sa.Column("encrypt", sa.Boolean(), nullable=False),
        sa.Column("trust_server_certificate", sa.Boolean(), nullable=False),
        sa.Column("allowed_objects", sa.JSON(), nullable=False),
        sa.Column("can_write", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("owner_id", "project_id"):
        op.create_index(
            op.f(f"ix_ingestion_connections_{column}"),
            "ingestion_connections",
            [column],
            unique=False,
        )
    op.create_table(
        "ingestion_extractions",
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("schema_name", sa.String(length=128), nullable=False),
        sa.Column("object_name", sa.String(length=128), nullable=False),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("byte_count", sa.Integer(), nullable=False),
        sa.Column("consistency", sa.String(length=32), nullable=False),
        sa.Column("server_version", sa.String(length=128), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["ingestion_connections.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["dataset_version_records.id"]),
        sa.PrimaryKeyConstraint("version_id"),
    )
    op.create_index(
        op.f("ix_ingestion_extractions_connection_id"),
        "ingestion_extractions",
        ["connection_id"],
        unique=False,
    )
    # La procedencia de una extracción es inmutable, como el original que describe.
    op.execute(
        "CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON ingestion_extractions "
        "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM ingestion_connections")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen conexiones de SQL Server.")
    op.execute("DROP TRIGGER immutable_record ON ingestion_extractions")
    op.drop_index(
        op.f("ix_ingestion_extractions_connection_id"), table_name="ingestion_extractions"
    )
    op.drop_table("ingestion_extractions")
    for column in ("project_id", "owner_id"):
        op.drop_index(
            op.f(f"ix_ingestion_connections_{column}"), table_name="ingestion_connections"
        )
    op.drop_table("ingestion_connections")
