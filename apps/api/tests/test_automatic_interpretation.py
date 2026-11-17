"""Interpretación sin confirmar semántica ni atribuir métricas de negocio por nombres."""

from pathlib import Path

from test_automatic_overview import compute


def test_sales_interpretation_is_a_candidate_not_a_business_confirmation(tmp_path: Path) -> None:
    data = (
        b"id,fecha,region,importe\n001,2026-01-01,Norte,10\n002,2026-01-02,Sur,20\n"
        b"003,2026-02-01,Norte,30\n004,2026-02-02,Sur,40\n"
    )
    overview = compute(tmp_path, data, interpreted=True)
    interpretation = overview["interpretation"]
    assert interpretation["context"] == "sales"
    assert interpretation["label"] == "Posible contexto de ventas"
    assert [column["role"] for column in interpretation["columns"]] == [
        "identifier",
        "date",
        "category",
        "numeric",
    ]
    assert interpretation["candidates"][0]["template"] == "sales@1"
    assert not any("Ingresos" in kpi["label"] for kpi in overview["kpis"])
    assert not any(kpi["id"].endswith("total") for kpi in overview["kpis"])
    assert compute(tmp_path, data, interpreted=True) == overview


def test_inventory_context_does_not_invent_stock_or_valuation(tmp_path: Path) -> None:
    overview = compute(
        tmp_path,
        (
            b"producto,stock,costo,fecha_corte\nA,10,2.50,2026-01-01\n"
            b"B,20,3.00,2026-01-01\nA,12,2.70,2026-02-01\n"
        ),
        interpreted=True,
    )
    assert overview["interpretation"]["context"] == "inventory"
    assert any("cortes de inventario" in text for text in overview["interpretation"]["limitations"])
    assert not any("Valor del inventario" in kpi["label"] for kpi in overview["kpis"])


def test_competing_templates_and_incomplete_types_remain_explicitly_ambiguous(
    tmp_path: Path,
) -> None:
    overview = compute(
        tmp_path,
        (
            b"producto,stock,costo,fecha,region,importe\nA,10,2,2026-01-01,Norte,20\n"
            b"B,20,3,2026-01-02,Sur,30\n"
        ),
        interpreted=True,
    )
    assert overview["interpretation"]["context"] == "ambiguous"
    assert {item["template"] for item in overview["interpretation"]["candidates"]} == {
        "sales@1",
        "inventory@1",
    }
    partial = compute(tmp_path, b"producto,stock\nA,10\nB,20\n", interpreted=True)
    assert partial["interpretation"]["context"] == "ambiguous"
    assert "cut_date" in partial["interpretation"]["candidates"][0]["missing_roles"]


def test_identifier_names_never_become_amount_candidates_or_statistics(tmp_path: Path) -> None:
    overview = compute(
        tmp_path,
        (b"revenue_id,accountID,fecha,region\n10,20,2026-01-01,Norte\n11,21,2026-01-02,Sur\n"),
        interpreted=True,
    )
    assert len(overview["kpis"]) == 4
    assert overview["interpretation"]["context"] == "generic"
    assert overview["interpretation"]["columns"][1]["role"] == "identifier"
    assert not overview["interpretation"]["candidates"]


def test_interpretation_prioritizes_dates_and_does_not_change_old_snapshot(tmp_path: Path) -> None:
    data = b"grupo_a,grupo_b,grupo_c,fecha\nA,B,C,2026-01-01\nA,B,C,2026-01-02\n"
    legacy = compute(tmp_path, data)
    assert legacy["algorithm"] == "automatic-overview-v1"
    assert "interpretation" not in legacy
    assert not any(chart["type"] == "line" for chart in legacy["charts"])
    interpreted = compute(tmp_path, data, interpreted=True)
    assert interpreted["charts"][0]["type"] == "line"
    assert interpreted["table_detail"] == legacy["table_detail"]


def test_multiple_currencies_block_combined_amount_statistics_without_blocking_dashboard(
    tmp_path: Path,
) -> None:
    overview = compute(
        tmp_path,
        (
            b"fecha,region,importe,moneda,cantidad\n2026-01-01,Norte,10,EUR,1\n"
            b"2026-01-02,Sur,20,USD,2\n2026-02-01,Norte,30,EUR,3\n"
        ),
        interpreted=True,
    )
    assert not any(kpi["column"] == "importe" for kpi in overview["kpis"])
    assert any(kpi["column"] == "cantidad" for kpi in overview["kpis"])
    assert any("más de una moneda" in text for text in overview["interpretation"]["limitations"])
    assert overview["kpis"][0]["value"] == "3"
    assert len(overview["table_detail"]["rows"]) == 3
