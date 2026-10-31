"""Versiones inmutables, cola durable y artefactos CSV."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id", sa.Uuid(), sa.ForeignKey("projects.id"), unique=True, nullable=False
        ),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("identity_users.id"), nullable=False),
    )
    op.create_index("ix_datasets_owner_id", "datasets", ["owner_id"])
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("dataset_id", sa.Uuid(), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("original_key", sa.String(500), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dataset_id", "number", name="uq_version_number"),
    )
    op.create_index("ix_dataset_versions_dataset_id", "dataset_versions", ["dataset_id"])
    op.create_table(
        "import_executions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "version_id",
            sa.Uuid(),
            sa.ForeignKey("dataset_versions.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("identity_users.id"), nullable=False),
        sa.Column("request_key", sa.Uuid(), nullable=False),
        sa.Column("separator", sa.String(8), nullable=False),
        sa.Column("engine_version", sa.String(40), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("column_count", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(60), nullable=True),
        sa.Column("error_message", sa.String(300), nullable=True),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "request_key", name="uq_import_request"),
    )
    op.create_index("ix_import_executions_owner_id", "import_executions", ["owner_id"])
    op.create_index("ix_import_queue", "import_executions", ["state", "created_at"])
    op.create_table(
        "analysis_artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("version_id", sa.Uuid(), sa.ForeignKey("dataset_versions.id"), nullable=False),
        sa.Column("execution_id", sa.Uuid(), sa.ForeignKey("import_executions.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.UniqueConstraint("version_id", "kind", name="uq_artifact_kind"),
    )


def downgrade() -> None:
    for table in ["analysis_artifacts", "import_executions", "dataset_versions", "datasets"]:
        op.drop_table(table)
