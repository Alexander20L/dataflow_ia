"""Tablas creadas por migraciones posteriores a 0012 (Fase 11).

Las pruebas de migraciones anteriores comparan su esquema con los modelos registrados; estas
tablas todavía no existen en esa revisión y se excluyen de la comparación. Cada migración nueva
añade aquí sus tablas.
"""

TABLES_AFTER_0012 = {
    # 0013: sesión de análisis con fuente única (11A)
    "analysis_sessions",
    "analysis_session_input_revisions",
}


def exists_at_0012(
    obj: object, name: str | None, type_: str, reflected: bool, other: object
) -> bool:
    table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
    return table not in TABLES_AFTER_0012
