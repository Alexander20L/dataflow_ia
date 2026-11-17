"""Referencia dorada de tablas de texto (Fase 6, etapa A1).

Capturada ANTES de introducir columnas tipadas: hash lógico y esquema de la tabla publicada,
perfil, calidad, vista previa de ingesta (con cada filtro de incidencia) y efecto de las
limpiezas de Fase 5 sobre los CSV del repositorio. Ampliar el motor a tipos reales no puede
cambiar ningún resultado de tablas de texto: si esta prueba falla, el cambio no es aditivo.

Las referencias no se regeneran para hacer pasar la prueba.
"""

import io
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import polars as pl
import pytest

from dataflow.modules.cleaning.infrastructure import (
    SOURCE_ROW,
    attach_lineage,
    effect,
    filter_rows,
    table_digest,
    trim_whitespace,
)
from dataflow.modules.ingestion import processor
from dataflow.modules.ingestion.analytical import PolarsPreview
from dataflow.modules.ingestion.executor import table_metadata

ROOT = Path(__file__).resolve().parents[3]
TESTS = Path(__file__).resolve().parent
GOLDEN = TESTS / "fixtures" / "phase6_text_golden"
SOURCES = {
    "semicolon_bom": TESTS / "fixtures" / "phase4_regression" / "semicolon_bom.csv",
    "tabs": TESTS / "fixtures" / "phase4_regression" / "tabs.csv",
    "ventas_calidad_fixture": TESTS / "fixtures" / "phase4_regression" / "ventas_calidad.csv",
    "ventas_calidad_example": ROOT / "examples" / "ventas_calidad.csv",
}
# ID de versión fijo: los IDs de columna se derivan de él.
VERSION = UUID("00000000-0000-4000-8000-000000000006")
LIMITS = (100_000, 128)


def cleaned(
    frame: pl.DataFrame, columns: list[dict[str, Any]], result: pl.DataFrame
) -> dict[str, Any]:
    counts, samples, _, lineage_sha = effect(frame, result, columns)
    table = result.drop(SOURCE_ROW)
    return {
        "logical_content_sha256": table_digest(columns, table),
        "row_lineage_sha256": lineage_sha,
        "counts": counts.model_dump(mode="json"),
        "samples": [sample.model_dump(mode="json") for sample in samples],
    }


def capture(source: Path, workdir: Path) -> dict[str, Any]:
    workdir.mkdir(parents=True, exist_ok=True)
    processor.read(source, workdir, "auto", *LIMITS)
    parquet = (workdir / "data.parquet").read_bytes()
    columns, logical = table_metadata(VERSION, parquet)
    processor.profile(workdir / "data.parquet", workdir, "auto", "0" * 64, *LIMITS)
    processor.quality(workdir / "data.parquet", workdir, *LIMITS)
    profile = json.loads((workdir / "profile.json").read_text(encoding="utf-8"))
    profile.pop("polars_version")
    quality = json.loads((workdir / "quality.json").read_text(encoding="utf-8"))

    preview = PolarsPreview()
    pages: dict[str, Any] = {"all": preview.read(parquet, 10, 0).model_dump(mode="json")}
    for issue in quality["issues"]:
        pages[issue["id"]] = preview.read(
            parquet, 10, 0, issue["rule"], issue["column"]
        ).model_dump(mode="json")

    frame = attach_lineage(pl.read_parquet(io.BytesIO(parquet)))
    names = [str(column["name"]) for column in columns]
    trimmed = trim_whitespace(frame, names)
    return {
        "columns": columns,
        "logical_content_sha256": logical,
        "profile": profile,
        "quality": quality,
        "preview": pages,
        "cleaning": {
            "trim_all": cleaned(frame, columns, trimmed),
            "drop_null_any": cleaned(frame, columns, filter_rows(frame, names, "is_null", "any")),
            "drop_whitespace_all": cleaned(
                frame, columns, filter_rows(frame, names, "is_whitespace_only", "all")
            ),
            "trim_then_drop_null": cleaned(
                frame, columns, filter_rows(trimmed, names, "is_null", "any")
            ),
        },
    }


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_text_tables_keep_their_golden_results(name: str, tmp_path: Path) -> None:
    golden = json.loads((GOLDEN / f"{name}.golden.json").read_text(encoding="utf-8"))
    assert capture(SOURCES[name], tmp_path) == golden
