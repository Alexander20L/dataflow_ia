"""Copia de tablas de SQL Server (Fase 18B, regla `sqlserver-selection-v1`; Fase 31,
`sqlserver-selection-v2`: un esquema opcional y hasta 10 tablas).

Sólo se usa desde el subproceso de ingesta. La conexión es de lectura, cifrada y de un solo uso:
la contraseña no se guarda ni se registra. Cada tabla elegida se copia completa (o se omite con su
motivo si supera los límites: nunca se trunca) y se convierte en celdas canónicas de texto.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from dataflow.platform.errors import ApplicationError

SELECTION_RULE = "sqlserver-selection-v1"
MAX_TABLES = 5
# Fase 31: un esquema se analiza como modelo de datos; caben más tablas.
SELECTION_RULE_V2 = "sqlserver-selection-v2"
MAX_TABLES_V2 = 10
UNSUPPORTED = {
    "binary",
    "varbinary",
    "image",
    "timestamp",
    "rowversion",
    "xml",
    "geography",
    "geometry",
    "hierarchyid",
    "sql_variant",
}
TABLES = """
SELECT s.name, t.name, SUM(p.rows)
FROM sys.tables AS t
JOIN sys.schemas AS s ON s.schema_id = t.schema_id
JOIN sys.partitions AS p ON p.object_id = t.object_id AND p.index_id IN (0, 1)
WHERE t.is_ms_shipped = 0
GROUP BY s.name, t.name
"""
FOREIGN_KEYS = """
SELECT ps.name, pt.name, pc.name, rs.name, rt.name, rc.name
FROM sys.foreign_key_columns AS fkc
JOIN sys.tables AS pt ON pt.object_id = fkc.parent_object_id
JOIN sys.schemas AS ps ON ps.schema_id = pt.schema_id
JOIN sys.columns AS pc
  ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
JOIN sys.tables AS rt ON rt.object_id = fkc.referenced_object_id
JOIN sys.schemas AS rs ON rs.schema_id = rt.schema_id
JOIN sys.columns AS rc
  ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
"""
COLUMNS = """
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
"""


class Cursor(Protocol):
    def execute(self, operation: str) -> object: ...
    def fetchall(self) -> Sequence[Sequence[Any]]: ...
    def fetchmany(self, size: int) -> Sequence[Sequence[Any]]: ...


class Connection(Protocol):
    def cursor(self) -> Cursor: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class Column:
    name: str
    type: str


@dataclass
class Candidate:
    schema: str
    name: str
    rows: int
    columns: list[Column]

    @property
    def label(self) -> str:
        return f"{self.schema}.{self.name}"

    @property
    def supported(self) -> list[Column]:
        return [c for c in self.columns if c.type.lower() not in UNSUPPORTED]


@dataclass
class TableCopy:
    schema: str
    name: str
    headers: list[str]
    rows: list[list[str | None]]
    excluded: list[Column] = field(default_factory=list)
    # Fase 19: claves foráneas declaradas (columna, esquema.tabla.columna referenciada).
    foreign_keys: list[tuple[str, str]] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.schema}.{self.name}"


@dataclass
class Snapshot:
    tables: list[TableCopy]
    omitted: list[tuple[str, str]]  # (esquema.tabla, motivo)
    # Fase 32: cómo se cifró la conexión (`verified`, `encrypted` o `none`), si se sabe.
    tls: str | None = None


# Fase 32 (ADR-050): lo que devuelve el servidor es entrada no confiable. La copia se lee por
# lotes y se cuentan sus bytes: una celda demasiado grande omite la tabla y pasar del total
# detiene la copia. Nunca se trunca.
BATCH = 1000


@dataclass
class Budget:
    max_bytes: int = 50 * 1024 * 1024
    max_cell_bytes: int = 64 * 1024
    used: int = 0


def cell_size(value: object) -> int:
    if isinstance(value, str | bytes | bytearray | memoryview):
        return len(value)
    return 16


def too_large(budget: Budget) -> ApplicationError:
    return fail(
        "DATABASE_TOO_LARGE",
        f"La base supera el tamaño que se puede copiar ({budget.max_bytes // (1024 * 1024)} MB). "
        "Elige un esquema con menos datos.",
    )


def fetch_rows(cursor: Any, max_rows: int, budget: Budget) -> list[Sequence[Any]] | str:
    """Filas de la consulta ya ejecutada, o el motivo por el que la tabla se omite."""
    rows: list[Sequence[Any]] = []
    while True:
        batch = cursor.fetchmany(BATCH)
        if not batch:
            return rows
        for record in batch:
            size = 0
            for value in record:
                length = cell_size(value)
                if length > budget.max_cell_bytes:
                    return (
                        f"Tiene celdas de más de {budget.max_cell_bytes // 1024} KB: "
                        "no se copia en parte."
                    )
                size += length
            budget.used += size
            if budget.used > budget.max_bytes:
                raise too_large(budget)
            rows.append(record)
            if len(rows) > max_rows:
                return f"Más de {max_rows} registros: no se copia en parte."


def fail(code: str, message: str) -> ApplicationError:
    return ApplicationError(code, message, 422)


def quote(identifier: str) -> str:
    return "[" + identifier.replace("]", "]]") + "]"


def catalog(cursor: Cursor) -> list[Candidate]:
    cursor.execute(TABLES)
    sizes = {(str(s), str(t)): int(n or 0) for s, t, n in cursor.fetchall()}
    cursor.execute(COLUMNS)
    columns: dict[tuple[str, str], list[Column]] = {}
    for schema, table, name, kind in cursor.fetchall():
        key = (str(schema), str(table))
        if key in sizes:
            columns.setdefault(key, []).append(Column(str(name), str(kind)))
    return [
        Candidate(schema, name, rows, columns.get((schema, name), []))
        for (schema, name), rows in sorted(sizes.items())
    ]


def choose(
    candidates: list[Candidate], max_rows: int, max_columns: int, limit: int = MAX_TABLES
) -> tuple[list[Candidate], list[tuple[str, str]]]:
    """Regla `sqlserver-selection-v1`: tablas de usuario con al menos dos columnas admitidas y
    dos registros, dentro de los límites; de mayor a menor tamaño (registros × columnas), empates
    por nombre; hasta `MAX_TABLES`. Lo demás se omite con su motivo."""
    eligible: list[Candidate] = []
    omitted: list[tuple[str, str]] = []
    for item in candidates:
        width = len(item.supported)
        if width < 2:
            omitted.append((item.label, "Menos de dos columnas con tipos admitidos."))
        elif item.rows < 2:
            omitted.append((item.label, "Menos de dos registros."))
        elif item.rows > max_rows:
            omitted.append((item.label, f"Más de {max_rows} registros: no se copia en parte."))
        elif width > max_columns:
            omitted.append((item.label, f"Más de {max_columns} columnas."))
        else:
            eligible.append(item)
    eligible.sort(key=lambda c: (-(c.rows * len(c.supported)), c.schema, c.name))
    omitted.extend((c.label, "Hay otras tablas más grandes.") for c in eligible[limit:])
    return eligible[:limit], omitted


def canonical(value: object) -> str | None:
    """Celda canónica de texto (la misma gramática que lee el perfil)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        return format(Decimal(repr(value)), "f")
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value).upper()
    if isinstance(value, bytes):
        return None
    text = str(value)
    return text if text != "" else None


def dates_only(rows: list[list[str | None]], index: int, values: list[object]) -> None:
    """Una columna de fecha y hora cuyas horas son todas medianoche se publica como fecha."""
    moments = [v for v in values if isinstance(v, datetime)]
    if moments and all(m.time() == time(0) and m.tzinfo is None for m in moments):
        for row, value in zip(rows, values, strict=True):
            if isinstance(value, datetime):
                row[index] = value.date().isoformat()


def copy(
    cursor: Cursor, table: Candidate, max_rows: int, budget: Budget | None = None
) -> TableCopy | str:
    """Copia completa de la tabla o el motivo por el que se omite."""
    columns = table.supported
    names = ", ".join(quote(c.name) for c in columns)
    cursor.execute(
        f"SELECT TOP ({max_rows + 1}) {names} FROM {quote(table.schema)}.{quote(table.name)}"
    )
    raw = fetch_rows(cursor, max_rows, budget or Budget())
    if isinstance(raw, str):
        return raw
    if len(raw) < 2:
        return "Menos de dos registros."
    rows = [[canonical(v) for v in record] for record in raw]
    for index, column in enumerate(columns):
        if column.type.lower() in {"datetime", "datetime2", "smalldatetime"}:
            dates_only(rows, index, [record[index] for record in raw])
    headers = [c.name for c in columns]
    if len(set(headers)) != len(headers) or any(not h.strip() for h in headers):
        return "Nombres de columna vacíos o repetidos."
    excluded = [c for c in table.columns if c not in columns]
    return TableCopy(table.schema, table.name, headers, rows, excluded)


def foreign_keys(cursor: Cursor) -> dict[tuple[str, str], list[tuple[str, str]]]:
    """Claves foráneas por tabla; si la cuenta no puede leerlas, ninguna (no es un error)."""
    try:
        cursor.execute(FOREIGN_KEYS)
        rows = cursor.fetchall()
    except Exception:
        return {}
    found: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for schema, table, column, ref_schema, ref_table, ref_column in rows:
        found.setdefault((str(schema), str(table)), []).append(
            (str(column), f"{ref_schema}.{ref_table}.{ref_column}")
        )
    return found


def snapshot(
    connection: Connection,
    max_rows: int,
    max_columns: int,
    schema: str | None = None,
    budget: Budget | None = None,
) -> Snapshot:
    """`sqlserver-selection-v2`: las tablas del esquema pedido (o de todos), hasta 10."""
    cursor = connection.cursor()
    candidates = [c for c in catalog(cursor) if schema is None or c.schema == schema]
    if schema is not None and not candidates:
        raise ApplicationError(
            "SQLSERVER_SCHEMA_EMPTY",
            f"El esquema «{schema}» no existe o no tiene tablas que la cuenta pueda leer.",
            422,
        )
    chosen, omitted = choose(candidates, max_rows, max_columns, MAX_TABLES_V2)
    declared = foreign_keys(cursor)
    budget = budget or Budget()
    tables: list[TableCopy] = []
    for table in chosen:
        result = copy(cursor, table, max_rows, budget)
        if isinstance(result, str):
            omitted.append((table.label, result))
        else:
            copied = {c for c in result.headers}
            result.foreign_keys = [
                (column, reference)
                for column, reference in declared.get((table.schema, table.name), [])
                if column in copied
            ]
            tables.append(result)
    if not tables:
        raise ApplicationError(
            "SQLSERVER_NO_TABLES",
            "La base no tiene tablas con al menos dos columnas y dos registros dentro de los "
            "límites.",
            422,
            {"omitted": [{"table": t, "reason": r} for t, r in omitted]},
        )
    return Snapshot(tables, omitted)


def connect(
    server: str, port: int, database: str, user: str, password: str, timeout: int
) -> Connection:
    """Conexión cifrada y de sólo lectura de intención (la cuenta debería tener sólo SELECT)."""
    import pymssql  # sólo en el subproceso de ingesta

    try:
        connection: Connection = pymssql.connect(
            server=server,
            port=str(port),
            user=user,
            password=password,
            database=database,
            login_timeout=min(timeout, 15),
            timeout=timeout,
            appname="DataFlow AI",
            encryption="require",
        )
    except pymssql.Error as exc:
        raise fail(
            "SQLSERVER_CONNECTION",
            "No se pudo conectar a SQL Server: revisa servidor, puerto, base, usuario y "
            "contraseña, y que la conexión cifrada esté permitida.",
        ) from exc
    return connection


def read_database(
    opener: Callable[[], Connection],
    max_rows: int,
    max_columns: int,
    schema: str | None = None,
    budget: Budget | None = None,
) -> Snapshot:
    connection = opener()
    try:
        return snapshot(connection, max_rows, max_columns, schema, budget)
    except ApplicationError:
        raise
    except Exception as exc:
        raise fail(
            "SQLSERVER_READ",
            "No se pudieron leer las tablas: la cuenta necesita permiso de lectura (SELECT) y "
            "acceso a las vistas de catálogo.",
        ) from exc
    finally:
        connection.close()
