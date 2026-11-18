"""Copia de tablas de PostgreSQL (Fase 31, ADR-049, regla `postgresql-selection-v1`).

Sólo se usa desde el subproceso de ingesta, igual que el lector de SQL Server: conexión de un
solo uso en una transacción de sólo lectura y con tiempo máximo por consulta; la contraseña no se
guarda ni se registra. Se leen las tablas de **un esquema** (por defecto `public`); cada tabla
elegida se copia completa (o se omite con su motivo si supera los límites: nunca se trunca) en
celdas canónicas de texto, con las mismas reglas que SQL Server (`sqlserver-selection-v2`: hasta
10 tablas).
"""

from collections.abc import Callable
from typing import Any

from dataflow.integrations.sources.sqlserver_reader import (
    MAX_TABLES_V2,
    Candidate,
    Column,
    Connection,
    Snapshot,
    TableCopy,
    canonical,
    choose,
    dates_only,
    fail,
)
from dataflow.platform.errors import ApplicationError

SELECTION_RULE = "postgresql-selection-v1"
UNSUPPORTED = {
    "bytea",
    "array",
    "user-defined",
    "xml",
    "json",
    "jsonb",
    "tsvector",
    "tsquery",
    "interval",
    "money",
    "bit",
    "bit varying",
    "point",
    "line",
    "lseg",
    "box",
    "path",
    "polygon",
    "circle",
}
TABLES = """
SELECT c.relname, GREATEST(c.reltuples, -1)::bigint
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = %s AND c.relkind IN ('r', 'p') AND NOT c.relispartition
ORDER BY c.relname
"""
COLUMNS = """
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = %s
ORDER BY table_name, ordinal_position
"""
FOREIGN_KEYS = """
SELECT cl.relname, att.attname, rns.nspname, rcl.relname, ratt.attname
FROM pg_constraint AS c
JOIN pg_class AS cl ON cl.oid = c.conrelid
JOIN pg_namespace AS ns ON ns.oid = cl.relnamespace
JOIN pg_class AS rcl ON rcl.oid = c.confrelid
JOIN pg_namespace AS rns ON rns.oid = rcl.relnamespace
JOIN pg_attribute AS att ON att.attrelid = c.conrelid AND att.attnum = c.conkey[1]
JOIN pg_attribute AS ratt ON ratt.attrelid = c.confrelid AND ratt.attnum = c.confkey[1]
WHERE c.contype = 'f' AND ns.nspname = %s AND cardinality(c.conkey) = 1
"""


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def catalog(cursor: Any, schema: str) -> list[Candidate]:
    cursor.execute(TABLES, (schema,))
    estimates = {str(name): int(rows) for name, rows in cursor.fetchall()}
    cursor.execute(COLUMNS, (schema,))
    columns: dict[str, list[Column]] = {}
    for table, name, kind in cursor.fetchall():
        if str(table) in estimates:
            columns.setdefault(str(table), []).append(Column(str(name), str(kind)))
    found: list[Candidate] = []
    for name, estimate in sorted(estimates.items()):
        rows = estimate
        if rows < 0:  # nunca analizada: se cuenta
            cursor.execute(f"SELECT count(*) FROM {quote(schema)}.{quote(name)}")
            rows = int(cursor.fetchall()[0][0])
        found.append(Candidate(schema, name, rows, columns.get(name, [])))
    return found


def supported(table: Candidate) -> list[Column]:
    return [c for c in table.columns if c.type.lower() not in UNSUPPORTED]


def copy(cursor: Any, table: Candidate, max_rows: int) -> TableCopy | str:
    """Copia completa de la tabla o el motivo por el que se omite."""
    columns = supported(table)
    names = ", ".join(quote(c.name) for c in columns)
    cursor.execute(
        f"SELECT {names} FROM {quote(table.schema)}.{quote(table.name)} LIMIT {max_rows + 1}"
    )
    raw = cursor.fetchall()
    if len(raw) > max_rows:
        return f"Más de {max_rows} registros: no se copia en parte."
    if len(raw) < 2:
        return "Menos de dos registros."
    rows = [[canonical(v) for v in record] for record in raw]
    for index, column in enumerate(columns):
        if column.type.lower() == "timestamp without time zone":
            dates_only(rows, index, [record[index] for record in raw])
    headers = [c.name for c in columns]
    if len(set(headers)) != len(headers) or any(not h.strip() for h in headers):
        return "Nombres de columna vacíos o repetidos."
    excluded = [c for c in table.columns if c not in columns]
    return TableCopy(table.schema, table.name, headers, rows, excluded)


def foreign_keys(cursor: Any, schema: str) -> dict[str, list[tuple[str, str]]]:
    """Claves foráneas de una columna por tabla; si no se pueden leer, ninguna."""
    try:
        cursor.execute(FOREIGN_KEYS, (schema,))
        rows = cursor.fetchall()
    except Exception:
        return {}
    found: dict[str, list[tuple[str, str]]] = {}
    for table, column, ref_schema, ref_table, ref_column in rows:
        found.setdefault(str(table), []).append(
            (str(column), f"{ref_schema}.{ref_table}.{ref_column}")
        )
    return found


def snapshot(connection: Connection, schema: str, max_rows: int, max_columns: int) -> Snapshot:
    cursor: Any = connection.cursor()
    candidates = catalog(cursor, schema)
    # La regla de elección es la de SQL Server sobre las columnas que PostgreSQL admite.
    eligible = [Candidate(c.schema, c.name, c.rows, supported(c)) for c in candidates]
    chosen, omitted = choose(eligible, max_rows, max_columns, MAX_TABLES_V2)
    originals = {(c.schema, c.name): c for c in candidates}
    declared = foreign_keys(cursor, schema)
    tables: list[TableCopy] = []
    for table in chosen:
        result = copy(cursor, originals[(table.schema, table.name)], max_rows)
        if isinstance(result, str):
            omitted.append((table.label, result))
        else:
            copied = set(result.headers)
            result.foreign_keys = [
                (column, reference)
                for column, reference in declared.get(table.name, [])
                if column in copied
            ]
            tables.append(result)
    if not tables:
        raise ApplicationError(
            "POSTGRESQL_NO_TABLES",
            f"El esquema «{schema}» no tiene tablas con al menos dos columnas y dos registros "
            "dentro de los límites.",
            422,
            {"omitted": [{"table": t, "reason": r} for t, r in omitted]},
        )
    return Snapshot(tables, omitted)


def connect(
    server: str, port: int, database: str, user: str, password: str, timeout: int
) -> Connection:
    """Conexión de un solo uso: sólo lectura, tiempo máximo por consulta y SSL si el servidor
    lo ofrece (`prefer`; un servidor local sin SSL también vale)."""
    import psycopg  # sólo en el subproceso de ingesta; la base es la del usuario, no la nuestra

    try:
        connection = psycopg.connect(
            host=server,
            port=port,
            dbname=database,
            user=user,
            password=password,
            connect_timeout=min(timeout, 15),
            sslmode="prefer",
            application_name="DataFlow AI",
            options=f"-c statement_timeout={timeout * 1000} -c default_transaction_read_only=on",
        )
        connection.read_only = True
    except psycopg.Error as exc:
        raise fail(
            "POSTGRESQL_CONNECTION",
            "No se pudo conectar a PostgreSQL: revisa servidor, puerto, base, usuario y "
            "contraseña.",
        ) from exc
    return connection


def read_database(
    opener: Callable[[], Connection], schema: str, max_rows: int, max_columns: int
) -> Snapshot:
    connection = opener()
    try:
        return snapshot(connection, schema, max_rows, max_columns)
    except ApplicationError:
        raise
    except Exception as exc:
        raise fail(
            "POSTGRESQL_READ",
            "No se pudieron leer las tablas: la cuenta necesita permiso de lectura (SELECT) "
            f"sobre el esquema «{schema}».",
        ) from exc
    finally:
        connection.close()
