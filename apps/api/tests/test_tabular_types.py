"""Fase 6 · A1: tablas con columnas tipadas en hash, perfil, calidad y vista previa."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import polars as pl
import pytest

from dataflow.modules.ingestion import processor
from dataflow.modules.ingestion.analytical import PolarsPreview
from dataflow.modules.ingestion.executor import table_metadata
from dataflow.platform.errors import ApplicationError
from dataflow.platform.tabular import canonical_cell, display_cell, table_logical_sha256

VERSION = UUID("00000000-0000-4000-8000-000000000016")
LIMITS = (100_000, 128)


def typed_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "cliente": pl.Series(["A", " ", "B", "A"], dtype=pl.String),
            "unidades": pl.Series([1, None, -3, 1], dtype=pl.Int64),
            "importe": pl.Series(
                [Decimal("10.50"), Decimal("0.00"), None, Decimal("10.50")],
                dtype=pl.Decimal(38, 2),
            ),
            "fecha": pl.Series(
                [date(2026, 2, 28), date(1, 1, 1), date(9999, 12, 31), date(2026, 2, 28)],
                dtype=pl.Date,
            ),
            "activo": pl.Series([True, False, None, True], dtype=pl.Boolean),
        }
    )


def parquet(frame: pl.DataFrame, path: Path) -> Path:
    frame.write_parquet(path)
    return path


def test_canonical_cells_follow_execution_contract() -> None:
    assert canonical_cell(0, "integer", {}) == "0"
    assert canonical_cell(-0, "integer", {}) == "0"
    assert canonical_cell(2**62, "integer", {}) == str(2**62)  # fuera del rango seguro JSON
    assert canonical_cell(Decimal("-0.00"), "decimal", {"scale": 2}) == "0.00"
    assert canonical_cell(Decimal("1.5"), "decimal", {"scale": 2}) == "1.50"
    assert canonical_cell(Decimal("12"), "decimal", {"scale": 0}) == "12"
    assert canonical_cell(date(1, 1, 1), "date", {}) == "0001-01-01"
    assert canonical_cell(True, "boolean", {}) is True
    assert display_cell(False, "boolean", {}) == "false"
    assert canonical_cell(" 007 ", "string", {}) == " 007 "
    assert canonical_cell(None, "decimal", {"scale": 2}) is None


def test_typed_table_metadata_and_logical_hash(tmp_path: Path) -> None:
    frame = typed_frame()
    columns, logical = table_metadata(VERSION, parquet(frame, tmp_path / "t.parquet").read_bytes())
    assert [(c["technical_type"], c["type_parameters"]) for c in columns] == [
        ("string", {}),
        ("integer", {}),
        ("decimal", {"scale": 2}),
        ("date", {}),
        ("boolean", {}),
    ]
    assert logical == table_logical_sha256(columns, frame.clone())
    # El mismo contenido como texto es otra tabla lógica: cambiar el tipo cambia el hash.
    text = frame.select(pl.all().cast(pl.String))
    text_columns, text_logical = table_metadata(
        VERSION, parquet(text, tmp_path / "s.parquet").read_bytes()
    )
    assert text_logical != logical
    with pytest.raises(ApplicationError) as mismatch:
        table_logical_sha256(columns, text)
    assert mismatch.value.code == "SCHEMA_MISMATCH"


@pytest.mark.parametrize(
    "series",
    [
        pl.Series("x", [1.5], dtype=pl.Float64),
        pl.Series("x", [1], dtype=pl.Int32),
        pl.Series("x", [Decimal("1.5")], dtype=pl.Decimal(10, 1)),
        pl.Series("x", [Decimal("1.5")], dtype=pl.Decimal(38, 13)),
    ],
)
def test_physical_types_outside_the_catalog_are_rejected(series: pl.Series) -> None:
    with pytest.raises(ApplicationError) as error:
        table_metadata(VERSION, _bytes(pl.DataFrame([series])))
    assert error.value.code == "UNSUPPORTED_COLUMN_TYPE"


def _bytes(frame: pl.DataFrame) -> bytes:
    import io

    buffer = io.BytesIO()
    frame.write_parquet(buffer)
    return buffer.getvalue()


def test_profile_and_quality_of_typed_table(tmp_path: Path) -> None:
    source = parquet(typed_frame(), tmp_path / "data.parquet")
    processor.profile(source, tmp_path, ",", "0" * 64, *LIMITS)
    processor.quality(source, tmp_path, *LIMITS)
    profile = json.loads((tmp_path / "profile.json").read_text(encoding="utf-8"))
    quality = json.loads((tmp_path / "quality.json").read_text(encoding="utf-8"))
    columns = {c["name"]: c for c in profile["columns"]}

    assert columns["cliente"]["technical_type"] == "string"
    assert columns["cliente"]["examples"] == ["A", " ", "B"]
    units = columns["unidades"]
    assert (units["technical_type"], units["suggested_type"]) == ("integer", "integer")
    assert (units["null_count"], units["unique_count"]) == (1, 2)
    assert units["numeric"] == {
        "count": 3,
        "total": "-1",
        "mean": "-0." + "3" * 50,  # precisión de 50 dígitos, como en texto numérico
        "minimum": "-3",
        "maximum": "1",
    }
    amount = columns["importe"]
    assert amount["examples"] == ["10.50", "0.00"]
    assert amount["numeric"]["total"] == "21.00"
    assert columns["fecha"]["examples"] == ["2026-02-28", "0001-01-01", "9999-12-31"]
    assert columns["fecha"]["numeric"] is None
    assert columns["activo"]["examples"] == ["true", "false"]

    rules = sorted((issue["rule"], issue["column"]) for issue in quality["issues"])
    # Q-003 sólo en texto; Q-001 en columnas tipadas; Q-002 compara valores tipados.
    assert rules == [
        ("Q-001", "activo"),
        ("Q-001", "importe"),
        ("Q-001", "unidades"),
        ("Q-002", None),
        ("Q-003", "cliente"),
    ]
    assert quality["duplicate_rows"] == 1 and quality["missing_cells"] == 3


def test_preview_renders_typed_cells_canonically(tmp_path: Path) -> None:
    content = parquet(typed_frame(), tmp_path / "t.parquet").read_bytes()
    page = PolarsPreview().read(content, 10, 0)
    assert page.rows[1].values == {
        "cliente": " ",
        "unidades": None,
        "importe": "0.00",
        "fecha": "0001-01-01",
        "activo": "false",
    }
    nulls = PolarsPreview().read(content, 10, 0, "Q-001", "importe")
    assert [row.row_number for row in nulls.rows] == [3] and nulls.total == 1
    duplicates = PolarsPreview().read(content, 10, 0, "Q-002")
    assert [row.row_number for row in duplicates.rows] == [4]


@pytest.mark.parametrize("name", ["^id$", "a|b", "*", "importe.*", "(x)"])
def test_preview_filters_do_not_interpret_headers_as_expressions(name: str, tmp_path: Path) -> None:
    frame = pl.DataFrame(
        {
            name: pl.Series(["1", None, " ", "1"], dtype=pl.String),
            "otra": pl.Series(["x", "y", "z", "x"], dtype=pl.String),
        }
    )
    content = parquet(frame, tmp_path / "t.parquet").read_bytes()
    preview = PolarsPreview()
    pages: dict[str, Any] = {
        rule: [row.row_number for row in preview.read(content, 10, 0, rule, name).rows]
        for rule in ["Q-001", "Q-003"]
    }
    pages["Q-002"] = [row.row_number for row in preview.read(content, 10, 0, "Q-002").rows]
    assert pages == {"Q-001": [2], "Q-003": [3], "Q-002": [4]}
    paged = preview.read(content, 1, 1)
    assert [row.row_number for row in paged.rows] == [2] and paged.total == 4
