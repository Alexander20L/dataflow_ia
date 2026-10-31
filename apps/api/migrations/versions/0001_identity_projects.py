"""Identidad, sesiones, proyectos y auditoría inicial."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "identity_users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
    )
    op.create_table(
        "identity_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("identity_users.id"), nullable=False),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_identity_sessions_user_id", "identity_sessions", ["user_id"])
    op.create_index("ix_identity_sessions_expires_at", "identity_sessions", ["expires_at"])
    op.create_table(
        "identity_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email_key", sa.String(64), nullable=False),
        sa.Column("ip_key", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for col in ["email_key", "ip_key", "created_at"]:
        op.create_index(f"ix_identity_attempts_{col}", "identity_attempts", [col])
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("identity_users.id"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_projects_owner_status", "projects", ["owner_id", "status"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for col in ["actor_id", "entity_id"]:
        op.create_index(f"ix_audit_events_{col}", "audit_events", [col])


def downgrade() -> None:
    for table in [
        "audit_events",
        "projects",
        "identity_attempts",
        "identity_sessions",
        "identity_users",
    ]:
        op.drop_table(table)
