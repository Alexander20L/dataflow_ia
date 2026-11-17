"""Dataset sintético de aceptación de la Fase 14 (forma del archivo real del usuario).

Determinista y sin aleatoriedad: Year + Month (nombre en inglés), Customer (código),
Customer_Name, Product, Region, Units_Sold, Price_per_Unit y Revenue = Units × Price.

Problemas deliberados (resultados esperados en las pruebas):
- C003 aparece como «Ana Torres» y, en marzo–mayo de 2024, como «Ana T.».
- Falta julio de 2024 completo.
- Una fila con Units_Sold = 400 (atípico) en 2024-10.
- No hay columna de moneda.
"""

from decimal import Decimal

MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
CUSTOMERS = [
    ("C001", "Comercial Andina", "Norte"),
    ("C002", "Distribuidora Sur", "Sur"),
    ("C003", "Ana Torres", "Centro"),
    ("C004", "Tecnologías Lima", "Centro"),
    ("C005", "Bodega Norte", "Norte"),
    ("C006", "Suministros Pacífico", "Sur"),
]
PRODUCTS = [
    ("Laptop", Decimal("850.00")),
    ("Monitor", Decimal("210.50")),
    ("Teclado", Decimal("35.90")),
    ("Mouse", Decimal("18.75")),
]
HEADER = [
    "Year",
    "Month",
    "Customer",
    "Customer_Name",
    "Product",
    "Region",
    "Units_Sold",
    "Price_per_Unit",
    "Revenue",
]


def reference_rows() -> list[list[str]]:
    rows: list[list[str]] = []
    for year in (2023, 2024):
        for month_index, month in enumerate(MONTHS):
            if year == 2024 and month == "July":
                continue
            for customer_index, (code, name, region) in enumerate(CUSTOMERS):
                if code == "C003" and year == 2024 and month in {"March", "April", "May"}:
                    name = "Ana T."
                for offset in (0, 1):
                    product, base = PRODUCTS[(customer_index + month_index + offset) % 4]
                    units = 1 + (3 * customer_index + 5 * month_index + 7 * offset + year) % 19
                    if year == 2024 and month == "October" and code == "C001" and offset == 0:
                        units = 400
                    price = (
                        base if year == 2023 else (base * Decimal("1.05")).quantize(Decimal("0.01"))
                    )
                    revenue = (price * units).quantize(Decimal("0.01"))
                    rows.append(
                        [
                            str(year),
                            month,
                            code,
                            name,
                            product,
                            region,
                            str(units),
                            str(price),
                            str(revenue),
                        ]
                    )
    return rows


def reference_csv() -> bytes:
    lines = [",".join(HEADER)] + [",".join(row) for row in reference_rows()]
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")
