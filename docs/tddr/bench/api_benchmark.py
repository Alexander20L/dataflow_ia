"""Benchmark de la API de DataFlow AI (TDDR, sección 5): latencia, throughput, errores y tiempo
del recorrido automático completo (carga -> informe).

Requiere la API con worker en marcha (ver docs/tddr/anexos/D-instalacion.md). Uso:
  apps/api/.venv/Scripts/python.exe docs/tddr/bench/api_benchmark.py http://127.0.0.1:8011 \
      > docs/tddr/bench/api_results.json
"""

import asyncio
import base64
import csv
import io
import json
import math
import random
import statistics
import sys
import time
import uuid
from pathlib import Path

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8011"
ORIGIN = "http://localhost:3002"
ROOT = Path(__file__).resolve().parents[3]
REPS = 5
LATENCY_N = 300


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def describe(values: list[float], scale: float = 1.0) -> dict:
    v = [x * scale for x in values]
    mean = statistics.mean(v)
    sd = statistics.stdev(v) if len(v) > 1 else 0.0
    # IC 95 % de la media con t de Student (tabla para gl pequeños, normal para n grande).
    t = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}
    crit = t.get(len(v) - 1, 1.96)
    half = crit * sd / math.sqrt(len(v)) if len(v) > 1 else 0.0
    return {
        "n": len(v),
        "media": round(mean, 3),
        "de": round(sd, 3),
        "ic95": [round(mean - half, 3), round(mean + half, 3)],
        "p50": round(pct(v, 0.5), 3),
        "p90": round(pct(v, 0.9), 3),
        "p99": round(pct(v, 0.99), 3),
        "min": round(min(v), 3),
        "max": round(max(v), 3),
    }


def kruskal(groups: list[list[float]]) -> dict:
    """H de Kruskal-Wallis (con rangos medios en empates) y valor p para gl = 2 (exacto: e^-H/2)."""
    flat = sorted((x, g) for g, values in enumerate(groups) for x in values)
    ranks: list[float] = [0.0] * len(flat)
    i = 0
    while i < len(flat):
        j = i
        while j + 1 < len(flat) and flat[j + 1][0] == flat[i][0]:
            j += 1
        for k in range(i, j + 1):
            ranks[k] = (i + j) / 2 + 1
        i = j + 1
    n = len(flat)
    sums = [0.0] * len(groups)
    for (x, g), r in zip(flat, ranks):
        sums[g] += r
    h = 12 / (n * (n + 1)) * sum(s * s / len(groups[g]) for g, s in enumerate(sums)) - 3 * (n + 1)
    df = len(groups) - 1
    p = math.exp(-h / 2) if df == 2 else None
    # Tamaño del efecto épsilon² = H / (n - 1).
    return {"H": round(h, 3), "gl": df, "p": p, "epsilon2": round(h / (n - 1), 3)}


def synthetic_csv(rows: int, seed: int) -> bytes:
    rng = random.Random(seed)
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["id_pedido", "fecha", "ciudad", "canal", "categoria", "unidades", "monto", "a_tiempo"])
    cities = ["Lima", "Arequipa", "Trujillo", "Cusco", "Piura"]
    for i in range(1, rows + 1):
        city = rng.choice(cities)
        w.writerow(
            [
                i,
                f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                city,
                rng.choice(["Web", "Vendedor", "Teléfono"]),
                rng.choice(["Abarrotes", "Bebidas", "Limpieza", "Lácteos"]),
                rng.randint(1, 20),
                f"{rng.uniform(10, 900) * (1.3 if city == 'Lima' else 1):.2f}",
                "no" if rng.random() < (0.1 if city == "Lima" else 0.3) else "si",
            ]
        )
    return out.getvalue().encode("utf-8")


class Api:
    def __init__(self) -> None:
        self.c = httpx.Client(base_url=BASE, headers={"Origin": ORIGIN}, timeout=120)

    def register(self) -> None:
        r = self.c.post(
            "/api/v1/auth/register",
            json={
                "name": "Benchmark TDDR",
                "email": f"bench-{uuid.uuid4()}@example.com",
                "password": "Benchmark-TDDR-segura-2026",
            },
        )
        r.raise_for_status()
        token = self.c.get("/api/v1/auth/me").json()["csrf_token"]
        self.c.headers["X-CSRF-Token"] = token

    def project(self, name: str) -> str:
        r = self.c.post("/api/v1/projects", json={"name": name})
        r.raise_for_status()
        return r.json()["id"]

    def upload_csv(self, project: str, name: str, data: bytes) -> dict:
        r = self.c.post(
            f"/api/v1/projects/{project}/imports",
            params={"file_name": name},
            headers={"Content-Type": "text/csv", "Idempotency-Key": str(uuid.uuid4())},
            content=data,
        )
        r.raise_for_status()
        return r.json()

    def upload_related(self, project: str, files: list[Path]) -> dict:
        body = {
            "files": [
                {"name": f.name, "content_base64": base64.b64encode(f.read_bytes()).decode()}
                for f in files
            ]
        }
        r = self.c.post(
            f"/api/v1/projects/{project}/imports/related",
            json=body,
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        r.raise_for_status()
        return r.json()

    def wait_project(self, project: str, started: float, limit: float = 900) -> dict:
        """Espera a que todas las versiones del proyecto completen sus etapas."""
        stage_times: dict[str, list[float]] = {}
        while time.perf_counter() - started < limit:
            versions = self.c.get(f"/api/v1/projects/{project}/versions").json()
            items = versions["items"] if isinstance(versions, dict) else versions
            done, failed = True, 0
            progress = []
            for v in items:
                p = self.c.get(f"/api/v1/versions/{v['id']}/progress").json()
                progress.append(p)
                done = done and p["complete"]
                failed += sum(s["state"] == "failed" for s in p["stages"])
            if items and done:
                elapsed = time.perf_counter() - started
                for p in progress:
                    for s in p["stages"]:
                        stage_times.setdefault(s["id"], []).append(1 if s["state"] == "done" else 0)
                return {
                    "segundos": elapsed,
                    "versiones": len(items),
                    "etapas_fallidas": failed,
                    "estados": {
                        k: f"{sum(v)}/{len(v)} hechas" for k, v in sorted(stage_times.items())
                    },
                }
            time.sleep(0.5)
        raise TimeoutError(project)


async def throughput(cookies: httpx.Cookies, path: str, concurrency: int, seconds: float) -> dict:
    ok = errors = 0
    lat: list[float] = []
    end = time.perf_counter() + seconds
    async with httpx.AsyncClient(base_url=BASE, cookies=cookies, timeout=30) as client:

        async def worker() -> None:
            nonlocal ok, errors
            while time.perf_counter() < end:
                t = time.perf_counter()
                try:
                    r = await client.get(path)
                    if r.status_code < 400:
                        ok += 1
                    else:
                        errors += 1
                except httpx.HTTPError:
                    errors += 1
                lat.append(time.perf_counter() - t)

        start = time.perf_counter()
        await asyncio.gather(*(worker() for _ in range(concurrency)))
        dur = time.perf_counter() - start
    return {
        "concurrencia": concurrency,
        "req_s": round((ok + errors) / dur, 1),
        "ok": ok,
        "errores": errors,
        "tasa_error": round(errors / max(ok + errors, 1), 4),
        "lat_ms_p50": round(pct(lat, 0.5) * 1000, 1),
        "lat_ms_p90": round(pct(lat, 0.9) * 1000, 1),
        "lat_ms_p99": round(pct(lat, 0.99) * 1000, 1),
    }


def main() -> None:
    api = Api()
    api.register()
    results: dict = {"base": BASE, "repeticiones": REPS}

    # 1. Recorrido completo: un CSV de ejemplo del repositorio y el conjunto relacionado.
    single = ROOT / "examples" / "ventas_calidad.csv"
    related = sorted((ROOT / "examples" / "relacionadas").glob("*.csv"))
    e2e: dict[str, list[dict]] = {"csv_ventas_calidad": [], "relacionadas_5_csv": []}
    for i in range(REPS):
        p = api.project(f"Bench CSV {i}")
        t = time.perf_counter()
        api.upload_csv(p, single.name, single.read_bytes())
        e2e["csv_ventas_calidad"].append(api.wait_project(p, t))
        p = api.project(f"Bench relacionados {i}")
        t = time.perf_counter()
        api.upload_related(p, related)
        e2e["relacionadas_5_csv"].append(api.wait_project(p, t))
    results["recorrido_completo"] = {
        k: {
            "segundos": describe([r["segundos"] for r in v]),
            "versiones": v[0]["versiones"],
            "etapas_fallidas": sum(r["etapas_fallidas"] for r in v),
            "estados_ultima": v[-1]["estados"],
        }
        for k, v in e2e.items()
    }

    # 2. Escalabilidad del recorrido completo con el número de filas.
    sizes = [1_000, 10_000, 50_000]
    scale: dict[int, list[float]] = {}
    failed = 0
    for n in sizes:
        data = synthetic_csv(n, n)
        for i in range(REPS):
            p = api.project(f"Bench {n} filas {i}")
            t = time.perf_counter()
            api.upload_csv(p, f"pedidos_{n}.csv", data)
            r = api.wait_project(p, t)
            scale.setdefault(n, []).append(r["segundos"])
            failed += r["etapas_fallidas"]
    results["escalabilidad_filas"] = {
        str(n): {"bytes": len(synthetic_csv(n, n)), "segundos": describe(v)}
        for n, v in scale.items()
    }
    results["escalabilidad_etapas_fallidas"] = failed
    results["kruskal_wallis_tiempo_vs_filas"] = kruskal([scale[n] for n in sizes])

    # 3. Latencia de lectura (secuencial, LATENCY_N peticiones por ruta).
    versions = api.c.get(f"/api/v1/projects/{p}/versions").json()
    items = versions["items"] if isinstance(versions, dict) else versions
    version = items[0]["id"]
    routes = {
        "GET /health/live": "/health/live",
        "GET /auth/me": "/api/v1/auth/me",
        "GET /projects": "/api/v1/projects",
        "GET /versions/{id}/progress": f"/api/v1/versions/{version}/progress",
        "GET /versions/{id}/preview": f"/api/v1/versions/{version}/preview",
        "GET /versions/{id}/dashboard": f"/api/v1/versions/{version}/dashboard",
        "GET /versions/{id}/inspection": f"/api/v1/versions/{version}/inspection",
    }
    latency = {}
    for name, path in routes.items():
        lat, errs = [], 0
        for _ in range(LATENCY_N):
            t = time.perf_counter()
            r = api.c.get(path)
            lat.append(time.perf_counter() - t)
            errs += r.status_code >= 400
        latency[name] = {"ms": describe(lat, 1000), "errores": errs}
    results["latencia_lectura"] = latency

    # 4. Throughput con concurrencia creciente (15 s por nivel).
    tp = {}
    for path_name, path in (
        ("GET /projects", "/api/v1/projects"),
        ("GET /versions/{id}/dashboard", f"/api/v1/versions/{version}/dashboard"),
    ):
        tp[path_name] = [
            asyncio.run(throughput(api.c.cookies, path, c, 15)) for c in (1, 5, 10, 20)
        ]
    results["throughput"] = tp
    json.dump(results, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
