"""Copia de tablas de SQL Server (Fase 18B, regla `sqlserver-selection-v1`).

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
COLUMNS = """
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
"""


class Cursor(Protocol):
    def execute(self, operation: str) -> object: ...
    def fetchall(self) -> Sequence[Sequence[Any]]: ...


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

    @property
    def label(self) -> str:
        return f"{self.schema}.{self.name}"


@dataclass
class Snapshot:
    tables: list[TableCopy]
    omitted: list[tuple[str, str]]  # (esquema.tabla, motivo)


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
    candidates: list[Candidate], max_rows: int, max_columns: int
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
    omitted.extend((c.label, "Hay otras tablas más grandes.") for c in eligible[MAX_TABLES:])
    return eligible[:MAX_TABLES], omitted


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


def copy(cursor: Cursor, table: Candidate, max_rows: int) -> TableCopy | str:
    """Copia completa de la tabla o el motivo por el que se omite."""
    columns = table.supported
    names = ", ".join(quote(c.name) for c in columns)
    cursor.execute(
        f"SELECT TOP ({max_rows + 1}) {names} FROM {quote(table.schema)}.{quote(table.name)}"
    )
    raw = cursor.fetchall()
    if len(raw) > max_rows:
        return f"Más de {max_rows} registros: no se copia en parte."
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


def snapshot(connection: Connection, max_rows: int, max_columns: int) -> Snapshot:
    cursor = connection.cursor()
    chosen, omitted = choose(catalog(cursor), max_rows, max_columns)
    tables: list[TableCopy] = []
    for table in chosen:
        result = copy(cursor, table, max_rows)
        if isinstance(result, str):
            omitted.append((table.label, result))
        else:
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


def read_database(opener: Callable[[], Connection], max_rows: int, max_columns: int) -> Snapshot:
    connection = opener()
    try:
        return snapshot(connection, max_rows, max_columns)
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
