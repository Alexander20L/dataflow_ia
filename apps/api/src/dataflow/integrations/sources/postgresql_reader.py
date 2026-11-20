"""Copia de tablas de PostgreSQL (Fase 31, ADR-049, regla `postgresql-selection-v1`).

Sólo se usa desde el subproceso de ingesta, igual que el lector de SQL Server: conexión de un
solo uso en una transacción de sólo lectura y con tiempo máximo por consulta; la contraseña no se
guarda ni se registra. Se leen las tablas de **un esquema** (por defecto `public`); cada tabla
elegida se copia completa (o se omite con su motivo si supera los límites: nunca se trunca) en
celdas canónicas de texto, con las mismas reglas que SQL Server (`sqlserver-selection-v2`: hasta
10 tablas).

Fase 32 (ADR-050): la conexión puede ir fijada a una dirección ya comprobada por
`database-destination-v1` (`hostaddr`; el nombre sólo sirve para verificar el certificado), con
`verify-full` en el modo público, y todo lo que devuelve el servidor tiene límites: catálogo
acotado y copia por lotes con un cursor del servidor y cuenta de bytes.
"""

from collections.abc import Callable
from typing import Any

from dataflow.integrations.sources.sqlserver_reader import (
    MAX_TABLES_V2,
    Budget,
    Candidate,
    Column,
    Connection,
    Snapshot,
    TableCopy,
    canonical,
    choose,
    dates_only,
    fail,
    fetch_rows,
)
from dataflow.platform.errors import ApplicationError

SELECTION_RULE = "postgresql-selection-v1"
# Fase 32: el catálogo de un servidor que no controlamos también se acota.
MAX_CATALOG_TABLES = 500
MAX_CATALOG_COLUMNS = 5000
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
LIMIT 501
"""
COLUMNS = """
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = %s
ORDER BY table_name, ordinal_position
LIMIT 5001
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


def crowded(schema: str) -> ApplicationError:
    return fail(
        "DATABASE_TOO_LARGE",
        f"El esquema «{schema}» tiene más de {MAX_CATALOG_TABLES} tablas o "
        f"{MAX_CATALOG_COLUMNS} columnas. Elige un esquema más pequeño.",
    )


def catalog(cursor: Any, schema: str) -> list[Candidate]:
    cursor.execute(TABLES, (schema,))
    listed = cursor.fetchall()
    if len(listed) > MAX_CATALOG_TABLES:
        raise crowded(schema)
    estimates = {str(name): int(rows) for name, rows in listed}
    cursor.execute(COLUMNS, (schema,))
    described = cursor.fetchall()
    if len(described) > MAX_CATALOG_COLUMNS:
        raise crowded(schema)
    columns: dict[str, list[Column]] = {}
    for table, name, kind in described:
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


def copy(cursor: Any, table: Candidate, max_rows: int, budget: Budget) -> TableCopy | str:
    """Copia completa de la tabla o el motivo por el que se omite. `cursor` es un cursor del
    servidor: las filas llegan por lotes y no todas a la vez."""
    columns = supported(table)
    names = ", ".join(quote(c.name) for c in columns)
    cursor.execute(
        f"SELECT {names} FROM {quote(table.schema)}.{quote(table.name)} LIMIT {max_rows + 1}"
    )
    raw = fetch_rows(cursor, max_rows, budget)
    if isinstance(raw, str):
        return raw
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


def snapshot(
    connection: Connection,
    schema: str,
    max_rows: int,
    max_columns: int,
    budget: Budget | None = None,
) -> Snapshot:
    budget = budget or Budget()
    cursor: Any = connection.cursor()
    candidates = catalog(cursor, schema)
    # La regla de elección es la de SQL Server sobre las columnas que PostgreSQL admite.
    eligible = [Candidate(c.schema, c.name, c.rows, supported(c)) for c in candidates]
    chosen, omitted = choose(eligible, max_rows, max_columns, MAX_TABLES_V2)
    originals = {(c.schema, c.name): c for c in candidates}
    declared = foreign_keys(cursor, schema)
    tables: list[TableCopy] = []
    for index, table in enumerate(chosen):
        streaming: Any = connection.cursor(name=f"dataflow_copy_{index}")  # type: ignore[call-arg]
        try:
            result = copy(streaming, originals[(table.schema, table.name)], max_rows, budget)
        finally:
            streaming.close()
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
    server: str,
    port: int,
    database: str,
    user: str,
    password: str,
    timeout: int,
    address: str | None = None,
    verify: bool = False,
    ca_file: str | None = None,
) -> Connection:
    """Conexión de un solo uso: sólo lectura y tiempo máximo por consulta. Servidores de la
    lista: SSL si el servidor lo ofrece (`prefer`; un servidor local sin SSL también vale).
    Fase 32: `address` fija la dirección comprobada (`hostaddr`: no se vuelve a resolver el
    nombre) y `verify` exige un certificado válido para ese nombre (`verify-full`) emitido por
    una autoridad del sistema o por la de `ca_file`."""
    import psycopg  # sólo en el subproceso de ingesta; la base es la del usuario, no la nuestra

    parameters: dict[str, Any] = {
        "host": server,
        "port": port,
        "dbname": database,
        "user": user,
        "password": password,
        "connect_timeout": min(timeout, 15),
        "application_name": "DataFlow AI",
        "options": f"-c statement_timeout={timeout * 1000} -c default_transaction_read_only=on",
        "sslmode": "prefer",
    }
    if address:
        parameters["hostaddr"] = address
    if verify:
        parameters["sslmode"] = "verify-full"
        parameters["sslrootcert"] = ca_file or "system"
    try:
        connection = psycopg.connect(**parameters)
        connection.read_only = True
    except psycopg.Error as exc:
        if verify and any(word in str(exc).lower() for word in ("ssl", "certificate", "tls")):
            raise fail(
                "DATABASE_TLS_UNVERIFIED",
                "No se pudo verificar la conexión cifrada con el servidor. Si tu proveedor usa "
                "su propio certificado, añádelo en «Opciones avanzadas».",
            ) from exc
        raise fail(
            "POSTGRESQL_CONNECTION",
            "No se pudo conectar a PostgreSQL: revisa servidor, puerto, base, usuario y "
            "contraseña.",
        ) from exc
    return connection


def tls_state(connection: Connection, verify: bool) -> str:
    """`verified` (verify-full), `encrypted` (SSL sin verificar) o `none`."""
    pgconn = getattr(connection, "pgconn", None)
    if pgconn is None or not getattr(pgconn, "ssl_in_use", False):
        return "none"
    return "verified" if verify else "encrypted"


def read_database(
    opener: Callable[[], Connection],
    schema: str,
    max_rows: int,
    max_columns: int,
    budget: Budget | None = None,
    verify: bool = False,
) -> Snapshot:
    connection = opener()
    try:
        result = snapshot(connection, schema, max_rows, max_columns, budget)
        result.tls = tls_state(connection, verify)
        return result
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
