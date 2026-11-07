"""Lector de SQL Server (Fase 12B) con pyodbc + Microsoft ODBC Driver 18.

Sólo se ejecuta en el subproceso aislado de ingesta. Reglas:

- Conexión cifrada (`Encrypt=yes`); `TrustServerCertificate` sólo si la conexión lo pide.
- Sin SQL arbitrario: el objeto se valida contra INFORMATION_SCHEMA y se cita
  (`[esquema].[objeto]`); el límite de filas va como parámetro.
- Tiempo de consulta, filas y bytes acotados: superarlos aborta sin devolver una tabla.
- Lectura con instantánea consistente (`SNAPSHOT`) si la base la permite; si no, se registra
  `read_committed_snapshot` o `none` para que la interfaz lo muestre.
- Valores a texto canónico (decimales exactos, fechas ISO, booleanos `true`/`false`); los
  tipos binarios o espaciales se rechazan con su columna.
- Los mensajes de error nunca incluyen la cadena de conexión ni la contraseña.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from dataflow.platform.errors import ApplicationError

READER_VERSION = "sqlserver-reader-1"
UNSUPPORTED_TYPES = {
    "binary",
    "varbinary",
    "image",
    "timestamp",
    "rowversion",
    "geography",
    "geometry",
    "hierarchyid",
    "sql_variant",
    "xml",
}


def fail(code: str, message: str) -> ApplicationError:
    return ApplicationError(code, message, 422)


@dataclass(frozen=True)
class ConnectionParameters:
    host: str
    port: int
    database: str
    username: str
    password: str
    encrypt: bool = True
    trust_server_certificate: bool = False
    driver: str = "ODBC Driver 18 for SQL Server"

    def odbc(self, timeout: int) -> str:
        def braced(value: str) -> str:
            return "{" + value.replace("}", "}}") + "}"

        parts = {
            "DRIVER": braced(self.driver),
            "SERVER": braced(f"tcp:{self.host},{self.port}"),
            "DATABASE": braced(self.database),
            "UID": braced(self.username),
            "PWD": braced(self.password),
            "Encrypt": "yes" if self.encrypt else "no",
            "TrustServerCertificate": "yes" if self.trust_server_certificate else "no",
            "ApplicationIntent": "ReadOnly",
            "Connection Timeout": str(max(1, min(timeout, 30))),
        }
        return ";".join(f"{key}={value}" for key, value in parts.items())


@dataclass
class Extraction:
    headers: list[str]
    sql_types: list[str]
    rows: list[list[str | None]]
    consistency: str
    byte_count: int
    server_version: str
    warnings: list[str] = field(default_factory=list)


def quote(identifier: str) -> str:
    return "[" + identifier.replace("]", "]]") + "]"


def canonical(value: Any, column: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        raise fail("SQL_UNSUPPORTED_TYPE", f"La columna «{column}» es binaria y no se admite.")
    return str(value)


def server_message(exc: Exception) -> str:
    """Mensaje de SQL Server sin prefijos del controlador. Nunca contiene la cadena de
    conexión: pyodbc sólo devuelve el texto del servidor y el número de error."""
    text = str(exc.args[1]) if len(exc.args) > 1 else ""
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = re.sub(r"\(SQL\w+\)\s*$", "", text).strip()
    return text[:300]


def connect(parameters: ConnectionParameters, timeout: int) -> Any:
    try:
        import pyodbc
    except ImportError as exc:  # sin unixODBC o sin la extensión instalada
        raise ApplicationError(
            "SQL_DRIVER_UNAVAILABLE", "El controlador ODBC de SQL Server no está instalado.", 503
        ) from exc
    try:
        connection = pyodbc.connect(parameters.odbc(timeout), autocommit=True, timeout=timeout)
    except pyodbc.InterfaceError as exc:
        state = exc.args[0] if exc.args else ""
        if state == "IM002":
            raise ApplicationError(
                "SQL_DRIVER_UNAVAILABLE",
                "El controlador ODBC Driver 18 for SQL Server no está instalado.",
                503,
            ) from None
        raise fail("SQL_LOGIN_FAILED", "Usuario o contraseña no válidos.") from None
    except pyodbc.Error as exc:
        state = str(exc.args[0]) if exc.args else ""
        if state in {"28000", "28P01"}:
            raise fail("SQL_LOGIN_FAILED", "Usuario o contraseña no válidos.") from None
        raise fail(
            "SQL_CONNECTION_FAILED",
            f"No se pudo conectar a SQL Server ({state or 'sin código'}). Revisa servidor, "
            "puerto, base de datos y certificado.",
        ) from None
    connection.timeout = timeout  # tiempo máximo por consulta
    return connection


def objects(connection: Any) -> list[dict[str, str]]:
    cursor = connection.cursor()
    cursor.execute(
        "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES "
        "ORDER BY TABLE_SCHEMA, TABLE_NAME"
    )
    return [
        {
            "schema": str(schema),
            "name": str(name),
            "kind": "view" if str(kind).upper() == "VIEW" else "table",
        }
        for schema, name, kind in cursor.fetchall()
    ]


def can_write(connection: Any) -> bool:
    cursor = connection.cursor()
    cursor.execute(
        "SELECT CASE WHEN HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'INSERT') = 1 "
        "OR HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'UPDATE') = 1 "
        "OR HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'DELETE') = 1 "
        "OR IS_ROLEMEMBER('db_owner') = 1 OR IS_ROLEMEMBER('db_datawriter') = 1 "
        "OR IS_SRVROLEMEMBER('sysadmin') = 1 THEN 1 ELSE 0 END"
    )
    return bool(cursor.fetchone()[0])


def server_version(connection: Any) -> str:
    cursor = connection.cursor()
    cursor.execute("SELECT CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(128))")
    return str(cursor.fetchone()[0])


def discover(parameters: ConnectionParameters, timeout: int) -> dict[str, Any]:
    connection = connect(parameters, timeout)
    try:
        return {
            "objects": objects(connection),
            "can_write": can_write(connection),
            "server_version": server_version(connection),
        }
    finally:
        connection.close()


def consistency(connection: Any) -> str:
    cursor = connection.cursor()
    cursor.execute(
        "SELECT snapshot_isolation_state, is_read_committed_snapshot_on "
        "FROM sys.databases WHERE name = DB_NAME()"
    )
    row = cursor.fetchone()
    if row is None:
        return "none"
    if int(row[0]) == 1:
        return "snapshot"
    return "read_committed_snapshot" if bool(row[1]) else "none"


def extract(
    parameters: ConnectionParameters,
    schema: str,
    name: str,
    max_rows: int,
    max_columns: int,
    max_bytes: int,
    timeout: int,
    truncate: bool = False,
) -> Extraction:
    """`truncate`: vista previa; se detiene en `max_rows` sin error."""
    connection = connect(parameters, timeout)
    try:
        available = {(o["schema"], o["name"]) for o in objects(connection)}
        if (schema, name) not in available:
            raise fail(
                "SQL_OBJECT_NOT_FOUND", f"El objeto {schema}.{name} no existe o no es visible."
            )
        cursor = connection.cursor()
        cursor.execute(
            "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
            schema,
            name,
        )
        columns = [(str(column), str(kind).lower()) for column, kind in cursor.fetchall()]
        if not columns:
            raise fail("SQL_OBJECT_NOT_FOUND", f"El objeto {schema}.{name} no tiene columnas.")
        if len(columns) > max_columns:
            raise fail("SQL_COLUMN_LIMIT", "El objeto supera el límite de columnas.")
        for column, kind in columns:
            if kind in UNSUPPORTED_TYPES:
                raise fail(
                    "SQL_UNSUPPORTED_TYPE",
                    f"La columna «{column}» es de tipo {kind}, que no se admite.",
                )
            if not column.strip() or len(column) > 200:
                raise fail("SQL_HEADERS", "Un nombre de columna está vacío o es demasiado largo.")
        mode = consistency(connection)
        version = server_version(connection)
        connection.autocommit = False
        if mode == "snapshot":
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SNAPSHOT")
        selected = ", ".join(quote(column) for column, _ in columns)
        cursor.execute(
            f"SELECT TOP (?) {selected} FROM {quote(schema)}.{quote(name)}",
            max_rows + 1,
        )
        rows: list[list[str | None]] = []
        size = 0
        while (batch := cursor.fetchmany(1000)) and not (truncate and len(rows) >= max_rows):
            for record in batch:
                if len(rows) >= max_rows:
                    if truncate:
                        break
                    raise fail("SQL_ROW_LIMIT", "El objeto supera el límite de filas.")
                values = [
                    canonical(value, column)
                    for value, (column, _) in zip(record, columns, strict=True)
                ]
                size += sum(len(v.encode("utf-8")) for v in values if v is not None)
                if size > max_bytes:
                    raise fail("SQL_BYTE_LIMIT", "La extracción supera el límite de tamaño.")
                rows.append(values)
        connection.rollback()
        return Extraction(
            [column for column, _ in columns],
            [kind for _, kind in columns],
            rows,
            mode,
            size,
            version,
        )
    except ApplicationError:
        raise
    except Exception as exc:
        import pyodbc

        if isinstance(exc, pyodbc.Error):
            state = str(exc.args[0]) if exc.args else ""
            if state == "HYT00":
                raise fail("SQL_TIMEOUT", "La consulta superó el tiempo permitido.") from None
            detail = server_message(exc)
            if re.search(r"\((229|230|262|297|300)\)", detail):
                raise fail(
                    "SQL_PERMISSION_DENIED",
                    f"El usuario no tiene permiso para leer ese objeto: {detail}",
                ) from None
            raise fail(
                "SQL_QUERY_FAILED", f"La consulta falló ({state or 'sin código'}): {detail}"
            ) from None
        raise
    finally:
        connection.close()
