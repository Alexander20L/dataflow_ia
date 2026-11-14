"""Proceso aislado y acotado; no importa ni utiliza conexiones de base de datos."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import TypeAdapter

from dataflow.integrations.sources.pdf_reader import read_table as pdf_read_table
from dataflow.integrations.sources.pdf_reader import select as pdf_select
from dataflow.integrations.sources.sqlserver_reader import connect, read_database
from dataflow.integrations.sources.xlsx_reader import (
    SELECTION_RULE_V2,
    Workbook,
    read_xlsx,
    workbook_facts,
)
from dataflow.modules.ingestion.contracts import (
    ConvertedColumn,
    ExcludedColumn,
    ForeignKey,
    KeptColumn,
    OmittedSource,
    PdfChoice,
    PdfSelection,
    ReadPdfParameters,
    SheetFacts,
    SnapshotTable,
    SourceFacts,
    SourceReading,
    SqlSnapshot,
)
from dataflow.modules.ingestion.domain import ENGINE_VERSION, detect_separator
from dataflow.modules.quality.public import (
    Rule,
    RulesetReference,
    assess,
    evaluate_quality,
    evaluate_rules,
)
from dataflow.modules.understanding.contracts import DatasetProfile, profile_json
from dataflow.modules.understanding.public import (
    analytical_overview,
    analyze,
    automatic_overview,
    interpret,
    profile_rows,
)
from dataflow.platform.csv_export import write_csv
from dataflow.platform.data_types import DataType
from dataflow.platform.errors import ApplicationError
from dataflow.platform.parquet_metadata import READING_KEY
from dataflow.platform.regional import LABELS as VALUE_LABELS
from dataflow.platform.regional import read_values
from dataflow.platform.tabular import Cell, display_cell, frame_types

PREVIEW_ROWS = 20
RULES: TypeAdapter[list[Rule]] = TypeAdapter(list[Rule])


def parse_csv(
    content: bytes,
    separator: str,
    max_rows: int,
    max_columns: int,
    encoding: str = "utf-8-sig",
) -> tuple[list[str], list[list[str | None]], str]:
    try:
        text = content.decode(encoding)
    except UnicodeDecodeError as exc:
        raise ApplicationError(
            "CSV_ENCODING",
            "El CSV no está en UTF-8 ni en Windows-1252; guárdalo en UTF-8 y vuelve a subirlo.",
            422,
        ) from exc
    if "\x00" in text:
        raise ApplicationError(
            "CSV_BINARY", "El archivo contiene bytes nulos y no es un CSV admitido.", 422
        )
    if separator == "auto":
        try:
            separator = detect_separator(text)
        except csv.Error:
            separator = ","
    elif separator == "tab":
        separator = "\t"
    if separator not in {",", ";", "\t"}:
        raise ApplicationError("CSV_SEPARATOR", "Separador no admitido.", 422)
    csv.field_size_limit(10000)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=separator, strict=True)
    try:
        headers = next(reader, [])
        if (
            not headers
            or len(headers) > max_columns
            or any(not h.strip() or len(h) > 200 for h in headers)
        ):
            raise ApplicationError(
                "CSV_HEADERS",
                "La cabecera debe tener entre 1 y 128 nombres no vacíos de hasta 200 caracteres.",
                422,
            )
        if len(set(headers)) != len(headers):
            raise ApplicationError(
                "CSV_DUPLICATE_HEADERS", "La cabecera contiene nombres de columna repetidos.", 422
            )
        rows: list[list[str | None]] = []
        for record in reader:
            if not record:
                continue
            if len(record) != len(headers):
                raise ApplicationError(
                    "CSV_SHAPE",
                    f"El registro {len(rows) + 1} no tiene el número de columnas de la cabecera.",
                    422,
                )
            if len(rows) >= max_rows:
                raise ApplicationError(
                    "CSV_ROW_LIMIT",
                    "El archivo supera el límite de registros de este incremento.",
                    422,
                )
            rows.append([value if value != "" else None for value in record])
    except csv.Error as exc:
        raise ApplicationError(
            "CSV_MALFORMED",
            "CSV mal formado o campo de más de 10.000 caracteres. Revisa comillas y separadores.",
            422,
        ) from exc
    if not rows:
        raise ApplicationError(
            "CSV_NO_ROWS", "El CSV no contiene registros después de la cabecera.", 422
        )
    return headers, rows, separator


def load_table(
    source: Path, max_rows: int, max_columns: int
) -> tuple[list[str], list[list[Cell]], list[tuple[DataType, dict[str, Any]]]]:
    """Tabla publicada: texto nullable o columnas tipadas del catálogo (Fase 6). Un tipo físico
    fuera del catálogo se rechaza con UNSUPPORTED_COLUMN_TYPE."""
    frame = pl.read_parquet(source)
    if frame.height > max_rows or frame.width > max_columns:
        raise ApplicationError(
            "TABLE_LIMIT", "La tabla supera los límites fijados en el plan.", 422
        )
    types = frame_types(frame)
    return frame.columns, [list(row) for row in frame.iter_rows()], types


def read(
    source: Path,
    output: Path,
    separator: str,
    max_rows: int,
    max_columns: int,
    encoding: str | None = None,
) -> None:
    """ingestion.read_csv@1: CSV original → Parquet de texto nullable. Con `encoding`
    (read_csv@2, Fase 18) se lee con esa codificación y con `regional-values-v1`."""
    content = source.read_bytes()
    headers, rows, actual_separator = parse_csv(
        content, separator, max_rows, max_columns, encoding or "utf-8-sig"
    )
    if encoding is None:
        write_table(output, headers, rows)
    else:
        reading = regional(headers, rows, "csv", file_convention=True)
        reading.encoding = encoding  # type: ignore[assignment]
        reading.separator = actual_separator
        write_table(output, headers, rows, reading)
    (output / "read.json").write_text(
        json.dumps(
            {
                "separator": actual_separator,
                "source_sha256": hashlib.sha256(content).hexdigest(),
                "row_count": len(rows),
                "column_count": len(headers),
            }
        ),
        encoding="utf-8",
    )


def regional(
    headers: list[str], rows: list[list[str | None]], kind: str, file_convention: bool
) -> SourceReading:
    """Aplica `regional-values-v1` en su sitio y devuelve la decisión para los metadatos."""
    result = read_values(rows, file_convention)
    rows[:] = result.rows
    return SourceReading(
        format=kind,
        convention=result.convention,
        converted=[
            ConvertedColumn(
                column=headers[item.column],
                kind=item.kind,
                format=item.format,
                values=item.values,
                by_file_convention=item.by_file_convention,
                explanation=(
                    f"Leída como {VALUE_LABELS[item.format]}"
                    + (
                        " por la convención del resto del archivo"
                        if item.by_file_convention
                        else ""
                    )
                    + f"; {item.values} valores reescritos en formato canónico."
                ),
            )
            for item in result.converted
        ],
        kept_as_text=[
            KeptColumn(column=headers[item.column], kind=item.kind, reason=item.reason)
            for item in result.kept
        ],
    )


def write_table(
    output: Path,
    headers: list[str],
    rows: list[list[str | None]],
    reading: SourceReading | None = None,
) -> None:
    frame = pl.DataFrame(rows, schema={name: pl.String for name in headers}, orient="row")
    frame.write_parquet(
        output / "data.parquet",
        compression="zstd",
        statistics=True,
        metadata={READING_KEY: reading.model_dump_json()} if reading else None,
    )


def read_xlsx_table(
    source: Path, output: Path, selection: dict[str, Any], max_rows: int, max_columns: int
) -> None:
    """ingestion.read_xlsx@1: libro original → Parquet de texto nullable (una hoja/tabla).
    Con `values` (read_xlsx@2, Fase 18), los textos regionales se leen con
    `regional-values-v1` sin convención de archivo (los números nativos ya son canónicos)."""
    content = source.read_bytes()
    result = read_xlsx(
        content,
        selection["sheet"],
        selection.get("table"),
        int(selection.get("header_row") or 1),
        max_rows,
        max_columns,
    )
    reading = (
        regional(result.headers, result.rows, "xlsx", file_convention=False)
        if selection.get("values")
        else None
    )
    write_table(output, result.headers, result.rows, reading)
    (output / "read.json").write_text(
        json.dumps(
            {
                # Procedencia tabular neutra: igual que las tablas publicadas (contrato 0.4/0.5).
                "separator": ",",
                "source_sha256": hashlib.sha256(content).hexdigest(),
                "row_count": len(result.rows),
                "column_count": len(result.headers),
                "sheet": result.sheet,
                "table": result.table,
                "warning_count": result.warning_count,
                "warnings": result.warnings,
            }
        ),
        encoding="utf-8",
    )


def snapshot_sqlserver(source: Path, output: Path, max_rows: int, max_columns: int) -> None:
    """Fase 18B: copia las tablas elegidas por `sqlserver-selection-v1` como CSV estándar. La
    contraseña sólo existe en el directorio temporal de este proceso."""
    params = json.loads(source.read_text(encoding="utf-8"))
    result = read_database(
        lambda: connect(
            str(params["server"]),
            int(params["port"]),
            str(params["database"]),
            str(params["user"]),
            str(params["password"]),
            int(params["timeout"]),
        ),
        max_rows,
        max_columns,
    )
    snapshot = SqlSnapshot(
        tables=[
            SnapshotTable(
                label=table.label,
                headers=table.headers,
                csv=write_csv(table.headers, table.rows, "standard").decode("utf-8"),
                excluded_columns=[
                    ExcludedColumn(column=c.name, type=c.type, reason=f"Tipo {c.type} no admitido.")
                    for c in table.excluded
                ],
                foreign_keys=[
                    ForeignKey(column=column, references=reference)
                    for column, reference in table.foreign_keys
                ],
            )
            for table in result.tables
        ],
        omitted=[OmittedSource(table=t, reason=r) for t, r in result.omitted],
    )
    (output / "snapshot.json").write_text(snapshot.model_dump_json(), encoding="utf-8")


def select_pdf(source: Path, output: Path, max_rows: int, max_columns: int) -> None:
    """Fase 18B: tablas del PDF elegidas por `pdf-selection-v1`."""
    chosen = pdf_select(source.read_bytes(), max_rows, max_columns)
    selection = PdfSelection(
        main=PdfChoice(label=chosen.main.label, segments=chosen.main.segments),
        additional=[PdfChoice(label=t.label, segments=t.segments) for t in chosen.additional],
        omitted=[OmittedSource(table=t, reason=r) for t, r in chosen.omitted],
    )
    (output / "selection.json").write_text(selection.model_dump_json(), encoding="utf-8")


def read_pdf(
    source: Path, output: Path, parameters: dict[str, Any], max_rows: int, max_columns: int
) -> None:
    """ingestion.read_pdf@1: la tabla fijada en el plan → Parquet de texto nullable, con
    `regional-values-v1` y convención de archivo (el PDF es texto, como un CSV)."""
    content = source.read_bytes()
    chosen = ReadPdfParameters.model_validate(parameters)
    table = pdf_read_table(content, list(chosen.segments), max_rows, max_columns)
    rows = [list(row) for row in table.rows]
    reading = regional(table.headers, rows, "pdf", file_convention=True)
    write_table(output, table.headers, rows, reading)
    (output / "read.json").write_text(
        json.dumps(
            {
                "separator": ",",
                "source_sha256": hashlib.sha256(content).hexdigest(),
                "row_count": len(rows),
                "column_count": len(table.headers),
            }
        ),
        encoding="utf-8",
    )


def inspect_xlsx(
    source: Path, output: Path, selection: dict[str, Any], max_rows: int, max_columns: int
) -> None:
    """Hojas, tablas y vista previa de la selección; un problema de la hoja elegida no
    impide listar el libro (se devuelve en `problem`)."""
    book = Workbook(source.read_bytes())
    automatic: dict[str, Any] | None = None
    additional: list[dict[str, Any]] = []
    if selection.get("sheet") is None and selection.get("table") is None:
        # Sin hoja ni tabla pedidas decide la regla: xlsx-selection-v2 desde la Fase 18 (la
        # principal es la de v1; las demás tablas con datos se analizan aparte).
        chosen = book.automatic_tables(max(1, max_rows + 1) * max_columns)
        selection = {"sheet": chosen.sheet, "table": chosen.table, "header_row": chosen.header_row}
        automatic = {
            "rule": SELECTION_RULE_V2,
            "sheet": chosen.sheet,
            "table": chosen.table,
            "header_row": chosen.header_row,
            "omitted": [{"sheet": s, "table": t} for s, t in chosen.omitted],
            "analyzed_together": [{"sheet": s, "table": t} for s, t, _ in chosen.additional],
        }
        additional = [{"sheet": s, "table": t, "header_row": h} for s, t, h in chosen.additional]
    sheet, table = book.select(selection.get("sheet"), selection.get("table"))
    header_row = int(selection.get("header_row") or 1)
    inspection: dict[str, Any] = {
        "selection": automatic,
        "additional": additional,
        "sheets": [{"name": s.name, "hidden": s.hidden, "tables": s.tables} for s in book.sheets],
        "sheet": sheet.name,
        "table": table.name if table else None,
        "header_row": table.first_row if table else header_row,
        "columns": [],
        "rows": [],
        "row_count": 0,
        "warnings": [],
        "warning_count": 0,
        "problem": None,
    }
    try:
        result = book.read_table(
            sheet.name, table.name if table else None, header_row, max_rows, max_columns
        )
        inspection.update(
            columns=result.headers,
            rows=result.rows[:PREVIEW_ROWS],
            row_count=len(result.rows),
            warnings=result.warnings,
            warning_count=result.warning_count,
        )
    except ApplicationError as exc:
        inspection["problem"] = {"code": exc.code, "message": exc.message}
    (output / "inspect.json").write_text(json.dumps(inspection), encoding="utf-8")


def profile(
    source: Path,
    output: Path,
    separator: str,
    source_sha256: str,
    max_rows: int,
    max_columns: int,
    include_overview: bool = False,
    include_interpretation: bool = False,
    include_analysis: bool = False,
) -> None:
    """understanding.profile@1 sobre una tabla; separador y hash son procedencia del original."""
    headers, rows, types = load_table(source, max_rows, max_columns)
    result = DatasetProfile(
        engine_version=ENGINE_VERSION,
        polars_version=pl.__version__,
        source_sha256=source_sha256,
        separator=separator,
        row_count=len(rows),
        column_count=len(headers),
        columns=profile_rows(headers, rows, types),
    )
    if include_analysis:
        cells = text_cells(rows, types)
        result.overview = analytical_overview(result, cells, analyze(result, cells))
    elif include_overview or include_interpretation:
        result.overview = automatic_overview(
            result, rows, types, interpret(result) if include_interpretation else None
        )
    version = (
        4 if include_analysis else 3 if include_interpretation else 2 if include_overview else 1
    )
    (output / "profile.json").write_text(profile_json(result, version), encoding="utf-8")


def text_cells(
    rows: list[list[Cell]], types: list[tuple[DataType, dict[str, Any]]]
) -> list[list[str | None]]:
    """Celdas como texto canónico (el mismo de vistas y hashes) para las reglas puras."""
    return [[display_cell(value, *types[index]) for index, value in enumerate(row)] for row in rows]


def analytical_quality(source: Path, output: Path, max_rows: int, max_columns: int) -> None:
    """quality.evaluate@3: csv-quality-v1 más hallazgos automatic-quality-v1."""
    headers, rows, types = load_table(source, max_rows, max_columns)
    report = evaluate_quality(headers, rows, [data_type for data_type, _ in types])
    cells = text_cells(rows, types)
    profile = DatasetProfile(
        engine_version=ENGINE_VERSION,
        polars_version=pl.__version__,
        source_sha256="",
        separator="",
        row_count=len(rows),
        column_count=len(headers),
        columns=profile_rows(headers, rows, types),
    )
    report.analytical = assess(analyze(profile, cells), cells)
    (output / "quality.json").write_text(report.serialized(3), encoding="utf-8")


def quality(source: Path, output: Path, max_rows: int, max_columns: int) -> None:
    """quality.evaluate@1 sobre una tabla."""
    headers, rows, types = load_table(source, max_rows, max_columns)
    report = evaluate_quality(headers, rows, [data_type for data_type, _ in types])
    (output / "quality.json").write_text(report.serialized(1), encoding="utf-8")


def quality_rules(
    source: Path,
    output: Path,
    columns: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    reference: dict[str, Any],
    max_rows: int,
    max_columns: int,
) -> None:
    """quality.evaluate@2: reglas técnicas (csv-quality-v1) y del usuario por separado."""
    headers, rows, _ = load_table(source, max_rows, max_columns)
    report = evaluate_rules(
        headers,
        rows,
        columns,
        RULES.validate_python(rules),
        RulesetReference.model_validate(reference),
    )
    (output / "quality_rules.json").write_text(report.model_dump_json(), encoding="utf-8")


def source_facts(
    source: Path, output: Path, parameters: dict[str, Any], max_rows: int, max_columns: int
) -> None:
    """Fase 22 (`source-facts-v1`): datos del original para la pestaña Dataset. Lee el original
    con los parámetros fijados en el plan de la carga; no publica tablas ni cambia nada."""
    content = source.read_bytes()
    kind = parameters.get("format")
    facts = SourceFacts(format="other", size_bytes=len(content))
    if kind == "csv":
        encoding = str(parameters.get("encoding") or "utf-8-sig")
        separator = str(parameters.get("separator") or ",")
        text = content.decode(encoding)
        blank = 0
        csv.field_size_limit(10000)
        for record in csv.reader(io.StringIO(text, newline=""), delimiter=separator, strict=True):
            if not record:
                blank += 1
        facts = SourceFacts(
            format="csv",
            size_bytes=len(content),
            encoding=encoding,
            separator=separator,
            blank_lines=blank,
        )
    elif kind == "xlsx":
        found = workbook_facts(
            content,
            parameters.get("sheet"),
            parameters.get("table"),
            int(parameters.get("header_row") or 1),
            max_rows,
            max_columns,
        )
        facts = SourceFacts(
            format="xlsx",
            size_bytes=len(content),
            sheets=[
                SheetFacts(
                    name=sheet.name,
                    hidden=sheet.hidden,
                    tables=sheet.tables,
                    selected=sheet.name == found.sheet,
                )
                for sheet in found.sheets
            ],
            sheet=found.sheet,
            table=found.table,
            used_range=found.used_range,
            header_row=found.header_row,
            empty_rows=found.empty_rows,
            empty_columns=found.empty_columns,
            formula_cells=found.formula_cells,
            date_cells=found.date_cells,
            inexact_numbers=found.inexact_numbers,
        )
    elif kind == "pdf":
        facts = SourceFacts(format="pdf", size_bytes=len(content))
    (output / "facts.json").write_text(facts.model_dump_json(), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=[
            "read",
            "read_xlsx",
            "inspect_xlsx",
            "profile",
            "automatic_profile",
            "interpreted_profile",
            "analytical_profile",
            "quality",
            "analytical_quality",
            "quality_rules",
            "snapshot_sqlserver",
            "select_pdf",
            "read_pdf",
            "source_facts",
        ],
        required=True,
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-rows", type=int, required=True)
    parser.add_argument("--max-columns", type=int, required=True)
    parser.add_argument("--separator", default=",")
    parser.add_argument("--encoding")
    parser.add_argument("--source-sha256")
    parser.add_argument("--columns-json")
    parser.add_argument("--rules-json")
    parser.add_argument("--reference-json")
    parser.add_argument("--xlsx-json")
    parser.add_argument("--pdf-json")
    parser.add_argument("--facts-json")
    args = parser.parse_args()
    try:
        if args.mode == "read":
            read(
                args.input,
                args.output,
                args.separator,
                args.max_rows,
                args.max_columns,
                args.encoding,
            )
        elif args.mode == "source_facts":
            source_facts(
                args.input,
                args.output,
                json.loads(args.facts_json),
                args.max_rows,
                args.max_columns,
            )
        elif args.mode == "snapshot_sqlserver":
            snapshot_sqlserver(args.input, args.output, args.max_rows, args.max_columns)
        elif args.mode == "select_pdf":
            select_pdf(args.input, args.output, args.max_rows, args.max_columns)
        elif args.mode == "read_pdf":
            read_pdf(
                args.input,
                args.output,
                json.loads(args.pdf_json),
                args.max_rows,
                args.max_columns,
            )
        elif args.mode in {"read_xlsx", "inspect_xlsx"}:
            handler = read_xlsx_table if args.mode == "read_xlsx" else inspect_xlsx
            handler(
                args.input,
                args.output,
                json.loads(args.xlsx_json),
                args.max_rows,
                args.max_columns,
            )
        elif args.mode in {
            "profile",
            "automatic_profile",
            "interpreted_profile",
            "analytical_profile",
        }:
            if not args.source_sha256:
                raise ApplicationError("PROCESSING_ERROR", "Falta el hash de procedencia.", 422)
            profile(
                args.input,
                args.output,
                args.separator,
                args.source_sha256,
                args.max_rows,
                args.max_columns,
                include_overview=args.mode == "automatic_profile",
                include_interpretation=args.mode == "interpreted_profile",
                include_analysis=args.mode == "analytical_profile",
            )
        elif args.mode == "quality":
            quality(args.input, args.output, args.max_rows, args.max_columns)
        elif args.mode == "analytical_quality":
            analytical_quality(args.input, args.output, args.max_rows, args.max_columns)
        else:
            quality_rules(
                args.input,
                args.output,
                json.loads(args.columns_json),
                json.loads(args.rules_json),
                json.loads(args.reference_json),
                args.max_rows,
                args.max_columns,
            )
    except ApplicationError as exc:
        (args.output / "error.json").write_text(
            json.dumps({"code": exc.code, "message": exc.message}), encoding="utf-8"
        )
        raise SystemExit(2) from None
    except Exception:
        (args.output / "error.json").write_text(
            json.dumps(
                {"code": "PROCESSING_ERROR", "message": "No se pudo completar el procesamiento."}
            ),
            encoding="utf-8",
        )
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
