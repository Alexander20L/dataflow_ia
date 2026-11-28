# Anexo F — Resultados completos de pruebas (incluidos los negativos)

Resultados en bruto: [`bench/relations_results.json`](../bench/relations_results.json) y
[`bench/api_results.json`](../bench/api_results.json). Scripts: `bench/relations_benchmark.py`,
`bench/api_benchmark.py`, `bench/screens.mjs` (cómo ejecutarlos: Anexo D §D.5).

## F.1 Integración continua sobre `main` `64a3e45` (20-11-2026)

| Workflow (ejecución)                    | Pasos                                                                                                                        | Resultado                                                                                                                                                 |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend (44839469563)                   | ruff check · ruff format --check · mypy · alembic upgrade/check · pytest · export_openapi --check · regeneración del cliente | **Éxito**. `All checks passed!` · `330 files already formatted` · `Success: no issues found in 201 source files` · **`789 passed, 1 skipped in 416.87s`** |
| Frontend (44839469412)                  | lint · typecheck · build · Playwright E2E                                                                                    | **Éxito**. `Compiled successfully` · **`18 passed (1.9m)`**                                                                                               |
| Analysis design contracts (44839469589) | `contracts:check`                                                                                                            | **Éxito**                                                                                                                                                 |
| Deploy (44839469472)                    | `images` (build y push a GHCR) · `deploy` (SSH)                                                                              | `images`: **éxito**; `deploy`: **omitido** (sin `DEPLOY_HOST` configurado)                                                                                |

La prueba omitida es `tests/ai/test_ai_live.py`, que sólo corre con `DATAFLOW_AI_LIVE_TESTS=1` y una clave
real. Las líneas `FATAL: password authentication failed` del registro de PostgreSQL en la CI las provocan
a propósito las pruebas de conexión a bases con credenciales incorrectas.

### Pruebas E2E (Chromium, en serie)

| #   | Spec               | Escenario                                                                   | Tiempo |
| --- | ------------------ | --------------------------------------------------------------------------- | ------ |
| 1   | analysis           | Análisis con criterio: periodo mensual, medidas y clientes limitados        | 9,0 s  |
| 2   | analyst            | Objetivo, factores con significancia y cambio de objetivo                   | 6,9 s  |
| 3   | automatic-overview | Subir CSV muestra el dashboard sin ningún paso manual                       | 5,6 s  |
| 4   | comprehension      | Grano, fórmulas, relaciones por familia y significado propio                | 5,4 s  |
| 5   | criteria           | Fecha que describe al registro, sin evolución mensual                       | 3,9 s  |
| 6   | csv                | CSV real: dashboard automático, descarga íntegra y versiones independientes | 7,0 s  |
| 7   | csv                | Un CSV inválido muestra un error real y conserva su original                | 2,9 s  |
| 8   | dashboard          | Indicadores con origen, filtros y versión personalizada                     | 5,3 s  |
| 9   | dataset            | Inspección completa y corrección manual persistente                         | 4,9 s  |
| 10  | dataset            | Las correcciones cuentan y los textos sin dato crean una versión            | 10,4 s |
| 11  | investigation      | Plan, árbol, evidencias e historial                                         | 7,1 s  |
| 12  | projects           | Registro, persistencia, edición, archivo y aislamiento entre cuentas        | 2,4 s  |
| 13  | regional           | CSV regional: se lee solo y se explica cómo                                 | 4,0 s  |
| 14  | regional           | PDF con tablas: cada tabla se analiza sola                                  | 5,0 s  |
| 15  | regional           | SQL Server desactivado: se explica sin guardar nada                         | 0,7 s  |
| 16  | related            | Archivos relacionados: foto del esquema y vista general                     | 13,6 s |
| 17  | report             | Vista previa, revisión, versión nueva e historial del informe               | 10,4 s |
| 18  | xlsx               | Excel: el sistema elige la hoja y lo explica                                | 3,6 s  |

### Cobertura de la batería del backend

82 archivos de prueba y 525 funciones `test_` (muchas parametrizadas, de ahí los 789 casos): dominio de cada
módulo, servicios con PostgreSQL real, 22 pruebas de migraciones (ida y vuelta, `compare_metadata`,
inmutabilidad), 17 reglas de arquitectura por AST, pruebas _golden_ de tablas de texto y de
`analytics.query@1` (sus referencias no se regeneran para hacer pasar una prueba), lectores de CSV, Excel,
PDF, SQL Server y PostgreSQL, conector de bases públicas y verificación de cifras de la IA con el proveedor
determinista.

## F.2 Benchmark de relaciones (completo)

Semilla 2026, 200 esquemas, 718 relaciones verdaderas.

| Método           | TP  | FP    | FN  | Precisión | Recall | F1     | IC 95 % F1       |
| ---------------- | --- | ----- | --- | --------- | ------ | ------ | ---------------- |
| P `relations-v1` | 560 | 0     | 158 | 1,0000    | 0,7799 | 0,8764 | [0,8585; 0,8937] |
| B1 sólo nombre   | 623 | 570   | 95  | 0,5222    | 0,8677 | 0,6520 | [0,6339; 0,6720] |
| B2 sólo valores  | 647 | 2.674 | 71  | 0,1948    | 0,9011 | 0,3204 | [0,3062; 0,3357] |

McNemar (3.962 pares): P vs. B1 → 570 / 63, χ² = 404,48, p = 5,83 × 10⁻⁹⁰; P vs. B2 → 2.674 / 87,
χ² = 2.422,09, p < 10⁻³⁰⁰ (por debajo de la precisión de coma flotante; el script imprime 0,0).

**Resultados negativos.** P no detecta ninguna clave foránea con nombre libre (0/95) ni con un valor
huérfano (0/71); 8 cumplen ambas condiciones, así que se pierden 158 relaciones, el 22 % de las
verdaderas. Falsos positivos de las líneas base por
columna: B1 — `monto` 370, `nombre` 200; B2 — `cantidad` 848, `edad` 623, `codigo` 170, `id_sede` 81,
`id_carrera` 56, `id_medico` 46, `id_paciente` 35, `id_categoria` 35 (y otros).

Tiempo de `relate()` (4 tablas): 1.000 filas 0,0125 ± 0,0009 s; 10.000 filas 0,1241 ± 0,0377 s; 100.000
filas 0,8604 ± 0,0470 s.

## F.3 Benchmark de la API (completo)

Ver Tablas 5.4–5.7 del TDDR y `api_results.json`. Resumen: 25 cargas, 60 versiones, 0 etapas fallidas;
2.100 peticiones de latencia y 13.288 de throughput, 0 errores; Kruskal-Wallis del tiempo frente a filas
H(2) = 12,50, p = 0,0019, ε² = 0,893.

**Resultados negativos.**

- `GET /versions/{id}/dashboard` con 20 clientes simultáneos: p90 = 661,7 ms y p99 = 738,5 ms, por encima
  del objetivo de 500 ms; el throughput no crece por encima de ~44 req/s desde 5 clientes.
- `GET /projects` no escala por encima de ~218 req/s (un proceso de uvicorn): con 20 clientes la latencia
  p99 sube a 156,8 ms.
- `GET /auth/me` y `/health/live` tienen valores máximos aislados de 35–40 ms frente a medianas de 2–6 ms
  (pausas del sistema).

## F.4 IA real

69 llamadas del 20-11-2026: 67 aceptadas, **2 errores del proveedor por tiempo agotado** (≈ 30 s, tareas
`exploration_proposal` y `exploration_relevance`); en ambos casos el recorrido terminó sin el texto de la IA.
Coste total 2,518 USD. Tiempo de carga a informe con IA real (16 versiones): 273,1 ± 119,2 s.

## F.5 Otros resultados negativos observados

- **Batería local lenta.** En el PC de desarrollo (Windows, PostgreSQL en Docker Desktop) `pytest` completo
  llevaba un 36 % tras unos 45 minutos y se interrumpió para no interferir con las mediciones; en la CI
  (Linux) la misma batería tarda 6 min 57 s. La diferencia se atribuye al arranque de subprocesos y a la E/S
  de Docker Desktop en Windows.
- **E2E con límite de 30 s en local.** Durante la Fase 31 (18-11-2026), `csv.spec` superaba en este equipo
  el límite de 30 s (también en `develop`); en la CI pasa en 7,0 s.
- **Análisis poco útil sin IA.** Con el proveedor de pruebas, la investigación de la vista general de
  `examples/relacionadas` propuso «evolución mensual de la suma de `costo_semestre`» (§5.7).
- **Despliegue automático omitido** en la CI de `64a3e45` (F.1).
