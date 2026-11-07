"""analysis_sessions: one active source per project (Fase 11A)"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aditiva: sólo tablas nuevas; versiones, planes y resultados no cambian.
    op.create_table(
        "analysis_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("head_input_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )
    op.create_index(
        op.f("ix_analysis_sessions_owner_id"), "analysis_sessions", ["owner_id"], unique=False
    )
    op.create_table(
        "analysis_session_input_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("version_kind", sa.String(length=16), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("table_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("table_sha256", sa.String(length=64), nullable=False),
        sa.Column("selected_by", sa.Uuid(), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["selected_by"], ["identity_users.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["analysis_sessions.id"]),
        sa.ForeignKeyConstraint(["table_artifact_id"], ["execution_artifacts.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["dataset_version_records.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "revision", name="uq_analysis_session_input_revision"),
    )
    op.create_index(
        op.f("ix_analysis_session_input_revisions_session_id"),
        "analysis_session_input_revisions",
        ["session_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_analysis_session_head",
        "analysis_sessions",
        "analysis_session_input_revisions",
        ["head_input_id"],
        ["id"],
    )
    op.execute(
        "CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON "
        "analysis_session_input_revisions "
        "FOR EACH ROW EXECUTE FUNCTION dataflow_immutable_record()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM analysis_sessions")):
        raise RuntimeError("ROLL_FORWARD_REQUIRED: existen sesiones de análisis.")
    op.execute("DROP TRIGGER immutable_record ON analysis_session_input_revisions")
    op.drop_constraint("fk_analysis_session_head", "analysis_sessions", type_="foreignkey")
    op.drop_index(
        op.f("ix_analysis_session_input_revisions_session_id"),
        table_name="analysis_session_input_revisions",
    )
    op.drop_table("analysis_session_input_revisions")
    op.drop_index(op.f("ix_analysis_sessions_owner_id"), table_name="analysis_sessions")
    op.drop_table("analysis_sessions")
