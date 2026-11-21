"""Benchmark reproducible de la detección de relaciones `relations-v1` (TDDR, sección 5).

Genera esquemas sintéticos con verdad de referencia (claves foráneas intencionales) y compara:
  - P  : relations-v1 (nombre + contención total + desambiguación), el método del sistema;
  - B1 : sólo nombre (la misma afinidad de nombres, sin comprobar valores);
  - B2 : sólo valores (dependencias de inclusión: columna ⊆ clave de otra tabla, >= 2 valores).
Métricas: precisión, exhaustividad (recall) y F1 sobre pares (tabla.columna -> tabla), IC 95 %
por bootstrap de esquemas y prueba de McNemar por pares. Mide además el tiempo de `relate()`.

Uso (desde la raíz del repo):
  apps/api/.venv/Scripts/python.exe docs/tddr/bench/relations_benchmark.py > docs/tddr/bench/relations_results.json
"""

import json
import math
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "api" / "src"))

from dataflow.modules.ingestion.relations import (  # noqa: E402
    Table,
    affinity,
    candidates,
    keys,
    relate,
)

SEED = 2026
SCHEMAS = 200
ENTITIES = [
    ("clientes", "cliente", "Cliente"),
    ("productos", "producto", "Producto"),
    ("estudiantes", "estudiante", "Estudiante"),
    ("empleados", "empleado", "Empleado"),
    ("pacientes", "paciente", "Paciente"),
    ("proveedores", "proveedor", "Proveedor"),
    ("medicos", "medico", "Medico"),
    ("cursos", "curso", "Curso"),
]
DIMENSIONS = [
    ("ciudades", "ciudad", "Ciudad"),
    ("carreras", "carrera", "Carrera"),
    ("categorias", "categoria", "Categoria"),
    ("sedes", "sede", "Sede"),
]
FACTS = ["ventas", "asistencia", "notas", "citas", "reclamos", "pagos", "pedidos", "visitas"]
FREE_NAMES = ["comprador", "responsable", "titular", "asignado", "referencia"]


def key_name(rng: random.Random, stem: str, camel: str) -> str:
    return rng.choice(["id", "id", "codigo", f"id_{stem}", f"{camel}ID"])


def fk_name(rng: random.Random, parent_key: str, stem: str, camel: str) -> tuple[str, str]:
    """Nombre de la clave foránea según la convención de la clave del padre (o libre)."""
    if rng.random() < 0.12:
        return rng.choice(FREE_NAMES), "libre"
    if parent_key == "id":
        return rng.choice([f"id_{stem}", f"{stem}_id", f"Id{camel}", f"{camel}Id"]), "convencion"
    if parent_key == "codigo":
        return rng.choice([f"codigo_{stem}", f"{stem}_codigo"]), "convencion"
    return parent_key, "mismo_nombre"


def ids(rng: random.Random, n: int) -> list[str]:
    start = rng.choice([1, 1, 100, 1000])
    return [str(start + i) for i in range(n)]


def schema(rng: random.Random, index: int):
    """Un esquema: dimensión <- entidad <- 1..3 tablas de hechos (y a veces otra entidad)."""
    tables: list[Table] = []
    truth: set[tuple[str, str, str]] = set()
    kinds: dict[tuple[str, str, str], tuple[str, bool]] = {}
    ents = rng.sample(ENTITIES, 2)
    dim = rng.choice(DIMENSIONS)

    def entity(spec, rows: int, dim_keys: list[str] | None, dim_key: str | None):
        label, stem, camel = spec
        pk = key_name(rng, stem, camel)
        values = ids(rng, rows)
        headers = [pk, "nombre", "edad"]
        data = [[v, f"{camel} {v}", str(rng.randint(18, 70))] for v in values]
        if dim_keys is not None and dim_key is not None:
            fk, kind = fk_name(rng, dim_key, dim[1], dim[2])
            headers.append(fk)
            orphan = rng.random() < 0.1
            for row in data:
                row.append(rng.choice(dim_keys))
            if orphan:
                data[0][-1] = "999999"
            truth.add((f"{label}.csv", fk, f"{dim[0]}.csv"))
            kinds[(f"{label}.csv", fk, f"{dim[0]}.csv")] = (kind, orphan)
        tables.append(Table(f"{label}.csv", headers, data))
        return pk, values

    dim_pk = key_name(rng, dim[1], dim[2])
    dim_values = ids(rng, rng.randint(4, 12))
    tables.append(
        Table(f"{dim[0]}.csv", [dim_pk, dim[1]], [[v, f"{dim[2]} {v}"] for v in dim_values])
    )
    e1_pk, e1_values = entity(ents[0], rng.randint(30, 150), dim_values, dim_pk)
    second = rng.random() < 0.5
    if second:
        e2_pk, e2_values = entity(ents[1], rng.randint(20, 80), None, None)
    for fact in rng.sample(FACTS, rng.randint(1, 3)):
        n = rng.randint(80, 400)
        headers = ["id", "fecha", "cantidad", "monto"]
        data = [
            [
                str(i + 1),
                f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                str(rng.randint(1, 10)),
                f"{rng.uniform(5, 900):.2f}",
            ]
            for i in range(n)
        ]
        targets = [(ents[0], e1_pk, e1_values)]
        if second and rng.random() < 0.6:
            targets.append((ents[1], e2_pk, e2_values))
        for (label, stem, camel), pk, values in targets:
            fk, kind = fk_name(rng, pk, stem, camel)
            if fk in headers:
                continue
            headers.append(fk)
            orphan = rng.random() < 0.1
            for row in data:
                row.append(rng.choice(values))
            if orphan:
                data[rng.randrange(n)][-1] = "888888"
            truth.add((f"{fact}.csv", fk, f"{label}.csv"))
            kinds[(f"{fact}.csv", fk, f"{label}.csv")] = (kind, orphan)
        tables.append(Table(f"{fact}.csv", headers, data))
    return tables, truth, kinds


def proposed(tables: list[Table]) -> set[tuple[str, str, str]]:
    return {(r.table, r.column, r.references_table) for r in candidates(tables, []) if r.valid}


def name_only(tables: list[Table]) -> set[tuple[str, str, str]]:
    found = set()
    for parent in tables:
        for key in keys(parent):
            for child in tables:
                if child is parent:
                    continue
                for column in child.headers:
                    if affinity(column, parent, parent.headers[key]):
                        found.add((child.label, column, parent.label))
    return found


def inclusion_only(tables: list[Table]) -> set[tuple[str, str, str]]:
    found = set()
    for parent in tables:
        parent_keys = [{row[k] for row in parent.rows} for k in keys(parent)]
        for child in tables:
            if child is parent:
                continue
            own = set(keys(child))
            for c, column in enumerate(child.headers):
                if c in own and column.lower() == "id":
                    continue
                values = {row[c] for row in child.rows if row[c] is not None}
                if len(values) >= 2 and any(values <= k for k in parent_keys):
                    found.add((child.label, column, parent.label))
    return found


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def mcnemar(b: int, c: int) -> tuple[float, float]:
    """Chi² de McNemar con corrección de continuidad (gl = 1) y su valor p."""
    if b + c == 0:
        return 0.0, 1.0
    chi = (abs(b - c) - 1) ** 2 / (b + c)
    return chi, math.erfc(math.sqrt(chi / 2))


def main() -> None:
    rng = random.Random(SEED)
    methods = {"P_relations_v1": proposed, "B1_nombre": name_only, "B2_inclusion": inclusion_only}
    per_schema = []
    decisions: dict[str, list[bool]] = {m: [] for m in methods}
    by_kind: dict[str, dict[str, list[int]]] = {}
    total_truth = 0
    for i in range(SCHEMAS):
        tables, truth, kinds = schema(rng, i)
        total_truth += len(truth)
        preds = {m: f(tables) for m, f in methods.items()}
        universe = truth.union(*preds.values())
        for pair in sorted(universe):
            for m in methods:
                decisions[m].append((pair in preds[m]) == (pair in truth))
        row = {}
        for m in methods:
            tp = len(preds[m] & truth)
            row[m] = (tp, len(preds[m] - truth), len(truth - preds[m]))
        per_schema.append(row)
        for pair, (kind, orphan) in kinds.items():
            group = f"{kind}{'+huerfanos' if orphan else ''}"
            stats = by_kind.setdefault(group, {m: [0, 0] for m in methods})
            for m in methods:
                stats[m][0] += pair in preds[m]
                stats[m][1] += 1

    results: dict = {"seed": SEED, "schemas": SCHEMAS, "true_relations": total_truth}
    boot = random.Random(SEED + 1)
    for m in methods:
        tp = sum(r[m][0] for r in per_schema)
        fp = sum(r[m][1] for r in per_schema)
        fn = sum(r[m][2] for r in per_schema)
        p, r, f = prf(tp, fp, fn)
        f1s = []
        for _ in range(2000):
            sample = [per_schema[boot.randrange(SCHEMAS)] for _ in range(SCHEMAS)]
            f1s.append(
                prf(
                    sum(s[m][0] for s in sample),
                    sum(s[m][1] for s in sample),
                    sum(s[m][2] for s in sample),
                )[2]
            )
        f1s.sort()
        results[m] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f, 4),
            "f1_ci95": [round(f1s[49], 4), round(f1s[1949], 4)],
        }
    for base in ("B1_nombre", "B2_inclusion"):
        a, b = decisions["P_relations_v1"], decisions[base]
        only_p = sum(1 for x, y in zip(a, b) if x and not y)
        only_b = sum(1 for x, y in zip(a, b) if y and not x)
        chi, pval = mcnemar(only_p, only_b)
        results[f"mcnemar_P_vs_{base}"] = {
            "pairs": len(a),
            "solo_P_acierta": only_p,
            "solo_base_acierta": only_b,
            "chi2": round(chi, 3),
            "p": pval,
        }
    results["recall_por_tipo"] = {
        g: {m: f"{v[0]}/{v[1]}" for m, v in s.items()} for g, s in sorted(by_kind.items())
    }

    # Tiempo de relate() con 4 tablas (entidad, dimensión y dos tablas de hechos) por tamaño.
    timing = {}
    for rows in (1_000, 10_000, 100_000):
        trng = random.Random(rows)
        ent = [str(i) for i in range(1, 501)]
        tables = [
            Table("ciudades.csv", ["id", "ciudad"], [[str(i), f"C{i}"] for i in range(1, 11)]),
            Table(
                "clientes.csv",
                ["id", "nombre", "id_ciudad"],
                [[v, f"N{v}", str(trng.randint(1, 10))] for v in ent],
            ),
        ]
        for fact in ("pedidos", "reclamos"):
            tables.append(
                Table(
                    f"{fact}.csv",
                    ["id", "id_cliente", "monto", "resuelto"],
                    [
                        [str(i), trng.choice(ent), f"{trng.uniform(1, 99):.2f}", trng.choice("sn")]
                        for i in range(1, rows + 1)
                    ],
                )
            )
        runs = []
        for _ in range(5):
            start = time.perf_counter()
            relate(tables, [], 128)
            runs.append(time.perf_counter() - start)
        timing[str(rows)] = {
            "media_s": round(statistics.mean(runs), 4),
            "de_s": round(statistics.stdev(runs), 4),
            "mediana_s": round(statistics.median(runs), 4),
        }
    results["tiempo_relate_4_tablas_por_filas_de_hechos"] = timing
    json.dump(results, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
