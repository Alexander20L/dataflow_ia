import csv
import io
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from dataflow.modules.datasets.contracts import StoredObject

__all__ = ["StoredObject", "Version", "ENGINE_VERSION", "ImportState"]

ImportState = Literal["queued", "processing", "succeeded", "failed", "cancelled"]
MAX_ATTEMPTS = 3
LEASE_SECONDS = 120
ENGINE_VERSION = "csv-ingestion-1"


def consistent(text: str, separator: str) -> bool:
    """Todos los registros de la muestra (sin el último, quizá cortado) tienen el ancho de la
    cabecera con ese separador."""
    try:
        records = [r for r in csv.reader(io.StringIO(text, newline=""), delimiter=separator) if r]
    except csv.Error:
        return False
    body = records[1:-1] if len(records) > 2 else records[1:]
    return bool(records) and all(len(r) == len(records[0]) for r in body)


def detect_separator(text: str) -> str:
    """Separador entre «,», «;» y tabulador con `csv.Sniffer` sobre los primeros 64 KB. Fase 22:
    si el resultado no da registros del mismo ancho (por ejemplo, por una línea en blanco entre
    registros), se vuelve a detectar sin las líneas en blanco y se usa sólo si ese sí es
    coherente. Los archivos que ya se leían bien no cambian. Lanza csv.Error si no se detecta."""
    sample = text[:65536]
    first = sniff(sample)
    # Antes, sin detección se usaba «,»: si «,» es coherente, sigue igual.
    if consistent(sample, first or ","):
        return first or ","
    second = sniff("\n".join(line for line in sample.splitlines() if line.strip()))
    if second is not None and consistent(sample, second):
        return second
    if first is None:
        raise csv.Error("Could not determine delimiter")
    return first


def sniff(text: str) -> str | None:
    try:
        return csv.Sniffer().sniff(text, delimiters=",;\t").delimiter
    except csv.Error:
        return None


@dataclass(frozen=True)
class Version:
    id: UUID
    dataset_id: UUID
    project_id: UUID
    number: int
    file_name: str
    sha256: str
    byte_size: int
    created_at: datetime
    execution_id: UUID
    state: ImportState
    row_count: int | None
    column_count: int | None
    error_code: str | None
    error_message: str | None
    attempts: int
    kind: Literal["imported", "derived"] = "imported"
    parent_version_id: UUID | None = None
    # Fase 13B: decisión automática de hoja o tabla de un .xlsx (`xlsx-selection-v1`).
    source_selection: dict[str, Any] | None = None
    # Fase 18B: tabla copiada de SQL Server o tabla de un PDF (`SourceOrigin`).
    source_origin: dict[str, Any] | None = None
