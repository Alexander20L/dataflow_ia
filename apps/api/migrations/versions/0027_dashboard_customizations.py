"""curation: versiones personalizadas del dashboard (Fase 26, ADR-044)"""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: una tabla nueva, inmutable y sólo de añadir. Cada fila es una revisión de la
    # versión personalizada del dashboard de una versión del dataset; la automática no se toca.
    op.create_table(
        "dashboard_customizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("dashboard_execution_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("layout", sa.JSON(), nullable=False),
        sa.Column("layout_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["dataset_version_records.id"]),
        sa.ForeignKeyConstraint(["dashboard_execution_id"], ["execution_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id", "version_id", "revision", name="uq_dashboard_customization"
        ),
    )
    for column in ("owner_id", "project_id", "version_id"):
        op.create_index(
            f"ix_dashboard_customizations_{column}", "dashboard_customizations", [column]
        )
    op.execute(
        "CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON dashboard_customizations "
        "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM dashboard_customizations")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen versiones personalizadas del dashboard.")
    op.execute("DROP TRIGGER immutable_record ON dashboard_customizations")
    for column in ("version_id", "project_id", "owner_id"):
        op.drop_index(
            f"ix_dashboard_customizations_{column}", table_name="dashboard_customizations"
        )
    op.drop_table("dashboard_customizations")
