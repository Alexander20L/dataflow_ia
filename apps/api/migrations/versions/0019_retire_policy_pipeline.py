"""retire the policy-governed pipeline (Fase 13, ADR-026)

Única migración no aditiva del proyecto, decidida explícitamente en la Fase 13: el recorrido
automático por política (Fases 11A-11E: sesión de análisis, políticas, pipeline, mapeos de moldes y
su dashboard) se retira en favor del recorrido automático sin configuración. Sus tablas y sus datos
se eliminan. Las versiones, aprobaciones, planes, métricas y dashboards que ese pipeline creó en
tablas de otros módulos se conservan.

El downgrade vuelve a crear esas tablas **vacías** (con las migraciones 0013-0017 originales): los
datos borrados no se recuperan.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

# Orden de creación (0013 → 0017). Un único DROP TABLE resuelve sus referencias mutuas.
RETIRED_TABLES = (
    "analysis_sessions",
    "analysis_session_input_revisions",
    "automation_policy_families",
    "automation_policy_revisions",
    "automation_policy_save_requests",
    "automation_approvals",
    "automation_runs",
    "automation_step_attempts",
    "template_mapping_families",
    "template_mapping_revisions",
    "template_mapping_save_requests",
    "automation_run_interpretations",
    "automation_run_analyses",
)
RETIRED_MIGRATIONS = (
    "0013_analysis_sessions.py",
    "0014_automation_policies.py",
    "0015_automation_runs.py",
    "0016_template_mappings.py",
    "0017_automation_analyses.py",
)


def upgrade() -> None:
    # Sin CASCADE: si otra tabla dependiera de éstas, la migración debe fallar, no romperla.
    op.execute("DROP TABLE " + ", ".join(RETIRED_TABLES))


def migration(name: str) -> ModuleType:
    path = Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location(f"retired_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def downgrade() -> None:
    for name in RETIRED_MIGRATIONS:
        migration(name).upgrade()
