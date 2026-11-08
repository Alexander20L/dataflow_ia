"""Dashboard sin política, semántica, llamadas IA ni cambios al original."""

import json
from pathlib import Path

import polars as pl
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_csv_ingestion import account, project, upload

from dataflow.bootstrap.services import make_runner
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.ingestion import processor


def compute(tmp_path: Path, content: bytes, interpreted: bool = False) -> dict:
    source = tmp_path / "input.csv"
    source.write_bytes(content)
    processor.read(source, tmp_path, "auto", 100000, 128)
    processor.profile(
        tmp_path / "data.parquet",
        tmp_path,
        ",",
        "a" * 64,
        100000,
        128,
        include_overview=True,
        include_interpretation=interpreted,
    )
    return json.loads((tmp_path / "profile.json").read_text(encoding="utf-8"))["overview"]


def test_automatic_dashboard_has_exact_statistics_without_business_assumptions(
    tmp_path: Path,
) -> None:
    content = (
        b"id,fecha,region,importe\n001,2026-01-01,Norte,10\n002,2026-01-02,Sur,20\n"
        b"003,2026-02-01,Norte,\n004,2026-02-02,Sur,30\n"
    )
    overview = compute(tmp_path, content)
    kpis = {kpi["id"]: kpi for kpi in overview["kpis"]}
    assert kpis["rows"]["value"] == "4"
    assert kpis["completeness"]["value"] == "93.75"
    assert kpis["c3_mean"]["value"] == "20.000000"
    assert kpis["c3_mean"]["excluded_rows"] == 1
    assert not any(kpi["column"] == "id" for kpi in overview["kpis"])
    assert not any("Ingresos" in kpi["label"] for kpi in overview["kpis"])
    dates = next(chart for chart in overview["charts"] if chart["id"] == "c1_months")
    assert dates["points"] == [{"label": "2026-01", "value": 2}, {"label": "2026-02", "value": 2}]
    assert overview["table_detail"]["rows"][0][0] == "001"
    assert compute(tmp_path, content) == overview
    assert (tmp_path / "input.csv").read_bytes() == content


def test_ambiguous_numbers_and_identifiers_are_not_aggregated(tmp_path: Path) -> None:
    overview = compute(tmp_path, b'codigo,importe\n007,"1,234"\n008,"2,345"\n')
    assert len(overview["kpis"]) == 4
    assert overview["table_detail"]["rows"] == [["007", "1,234"], ["008", "2,345"]]


def test_detail_is_bounded_and_duplicate_rows_are_preserved(tmp_path: Path) -> None:
    content = ("texto\n" + ("x" * 350 + "\n") * 30).encode()
    overview = compute(tmp_path, content)
    assert overview["kpis"][3]["value"] == "29"
    assert overview["table_detail"]["total_rows"] == 30
    assert len(overview["table_detail"]["rows"]) == 20
    assert overview["table_detail"]["truncated"]
    assert overview["table_detail"]["cells_truncated"]
    assert pl.read_parquet(tmp_path / "data.parquet").height == 30


def test_category_limit_preserves_coverage_and_tie_order(tmp_path: Path) -> None:
    labels = [f"grupo-{index:02}" for index in range(15)]
    content = ("categoria\n" + "\n".join(reversed(labels * 2)) + "\n").encode()
    overview = compute(tmp_path, content)
    chart = next(chart for chart in overview["charts"] if chart["id"] == "c0_counts")
    assert [point["label"] for point in chart["points"]] == labels[:12]
    assert chart["omitted_groups"] == 3
    assert chart["valid_rows"] == 24
    assert chart["excluded_rows"] == 6
    assert sum(point["value"] for point in chart["points"]) == chart["valid_rows"]


def test_saved_legacy_profile_is_not_silently_upgraded(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    source.write_bytes(b"valor\n10\n20\n")
    processor.read(source, tmp_path, "auto", 100000, 128)
    processor.profile(tmp_path / "data.parquet", tmp_path, ",", "a" * 64, 100000, 128)
    profile = json.loads((tmp_path / "profile.json").read_text(encoding="utf-8"))
    assert "overview" not in profile


def test_import_publishes_dashboard_without_policy_and_restores_it_after_reload(
    client: TestClient, db: Session, objects: LocalObjects
) -> None:
    headers = account(client)
    pid = project(client, headers)
    content = b"region,importe\nNorte,10\nSur,20\nNorte,30\n"
    version = upload(client, headers, pid, content).json()
    make_runner(db, objects).run_once()
    response = client.get(f"/api/v1/versions/{version['id']}/diagnostic")
    assert response.status_code == 200, response.text
    overview = response.json()["profile"]["overview"]
    assert overview["kpis"][0]["value"] == "3"
    assert overview["algorithm"] == "automatic-overview-v2"
    assert overview["interpretation"]["rules_version"] == "automatic-interpretation-v1"
    assert (
        client.get(f"/api/v1/versions/{version['id']}/diagnostic").json()["profile"]["overview"]
        == overview
    )
    original = client.get(f"/api/v1/versions/{version['id']}/original")
    assert original.content == content
    table = client.get(f"/api/v1/versions/{version['id']}/representations").json()[0]
    context = client.get(f"/api/v1/representations/{table['id']}/understanding").json()
    assert context["head"] is None
    account(client)
    assert client.get(f"/api/v1/versions/{version['id']}/diagnostic").status_code == 404
