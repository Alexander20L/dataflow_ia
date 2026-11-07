"""Tablas creadas por migraciones posteriores a 0012 (Fase 11).

Las pruebas de migraciones anteriores comparan su esquema con los modelos registrados; estas
tablas todavía no existen en esa revisión y se excluyen de la comparación. Cada migración nueva
añade aquí sus tablas.
"""

TABLES_AFTER_0012 = {
    # 0013: sesión de análisis con fuente única (11A)
    "analysis_sessions",
    "analysis_session_input_revisions",
    # 0014: política de automatización y aprobaciones por política (11B)
    "automation_policy_families",
    "automation_policy_revisions",
    "automation_policy_save_requests",
    "automation_approvals",
    # 0015: pipeline automático y registro de pasos (11C)
    "automation_runs",
    "automation_step_attempts",
}


def exists_at_0012(
    obj: object, name: str | None, type_: str, reflected: bool, other: object
) -> bool:
    table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
    return table not in TABLES_AFTER_0012
