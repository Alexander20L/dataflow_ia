# DataFlow AI — guía para Claude

Plataforma de análisis de datos **completamente automático** sobre archivos propios (CSV, Excel): subir →
resultados, sin formularios ni aprobaciones. Monorepo: `apps/api` (FastAPI, monolito
modular + worker del mismo código), `apps/web` (Next.js), `packages/api-client` (cliente generado desde
OpenAPI), `contracts/` (OpenAPI vigente y contratos de diseño `analysis/v1`), `docs/` (arquitectura y ADR).
Documentación y UI en español.

## Principio: automático, determinista y trazable (desde la Fase 13, ADR-026)

- **Sin intervención manual**: al subir una fuente el sistema lee, perfila, limpia, evalúa, analiza, publica
  el dashboard y lo explica. No hay aprobaciones, políticas, mapeos ni formularios en el recorrido.
  Sustituye al antiguo «principio híbrido» (la persona aprobaba el `effect_sha256`; ADR-013/015/022/023).
- **El motor determinista decide y calcula** con reglas versionadas (Polars, hashes canónicos, conteos
  exactos sobre todo el dataset). Sólo transformaciones seguras y sin pérdida; ante la duda, no se
  transforma y se explica la limitación.
- **La IA sólo explica** resultados publicados; ninguna cifra sale del modelo (sólo `{{evidence:id}}`).
  Desactivada por defecto (`DATAFLOW_AI_PROVIDER=disabled`).
- El original y las versiones publicadas son inmutables: limpiar crea una versión derivada con linaje y el
  efecto exacto (`effect_sha256`) queda registrado como decisión del sistema.

Referencias obligatorias: `docs/architecture/phase-1/execution-contract.md` (catálogo objetivo, gramáticas
de conversión §3, hash canónico §6), `docs/architecture/phase-N.md` y `docs/adr/0NN-*.md`.

## Arquitectura y reglas de módulos

Módulos en `apps/api/src/dataflow/modules/`: identity, projects, audit, datasets, ingestion, understanding,
quality, planning, executions, cleaning, analytics, copilot; dashboards y reports sólo conservan sus clases
de tabla (Fase 13). Adaptador de IA en `integrations/ai` (puerto `AIProvider`, proveedor falso; sólo
`anthropic_provider.py` importa el SDK); lectores de fuentes en `integrations/sources` (sólo desde el
subproceso de ingesta).
Composición en `bootstrap/` (`bootstrap/operations.py` une
descriptor de catálogo + ejecutor y falla al arrancar si falta uno).

- Capas: domain (sin frameworks) → application (dominio + puertos) → infrastructure → presentation (HTTP/DTO).
  Domain y application no importan infrastructure.
- Entre módulos **sólo** `dataflow.modules.<m>.public` o `.contracts`. Dependencias acíclicas.
- **executions** no importa planning, cleaning, quality, ingestion, understanding ni analytics: recibe puertos
  (`StepRegistry`, `StepExecutor`, `InputResolver`, finalizadores, ganchos de publicación).
- planning no importa polars/duckdb ni implementaciones de operaciones (validación pura en `planning/domain.py`).
- copilot sólo usa `integrations.ai` y `audit`: explica el dashboard publicado (C2, `bootstrap/overview_audit.py`),
  controla disponibilidad y presupuesto y verifica cifras. Ya no conversa ni propone acciones.
- No volver a crear `automation`, `templates` ni `analysis_sessions` (prueba AST). La detección pura de
  contextos vive en `understanding/templates.py`.
- El cómputo de cleaning (`domain`, `contracts`, `infrastructure`, `engine`, `processor`) no accede a la BD.
- Todo esto lo verifica `apps/api/tests/test_architecture.py` (AST). No debilitar esas pruebas.
- Web: comportamiento por funcionalidad en `apps/web/src/features/<f>`; tipos HTTP sólo del cliente generado.

## Convenciones

- **Operaciones versionadas** `modulo.nombre@N` (p. ej. `cleaning.trim_whitespace@1`). Cambiar semántica =
  nueva versión u operación; el catálogo (`analysis-vN`) se versiona y los planes guardados conservan el suyo.
  Columnas siempre por ID (`x-dataflow-column-ref`), nunca por nombre; en Polars, alias neutros (no `pl.col(nombre)`).
- **Revisiones inmutables** (planes, semántica): crear con `Idempotency-Key`, nuevas revisiones con
  `expected_revision` (409 si cambió); sin cambios no se crea revisión. Triggers `dataflow_immutable_record`.
- **Migraciones aditivas** en `apps/api/migrations/versions/NNNN_*.py`, cada una con `tests/test_migration_NNNN.py`
  (ida y vuelta, `compare_metadata`, inmutabilidad, downgrade bloqueado si hay datos nuevos). Preferir tablas
  nuevas a columnas nuevas en tablas existentes (ver ADR-014/015). Única excepción: 0019 (Fase 13, ADR-026)
  elimina las tablas de 0013–0017 por decisión explícita; un borrado de datos siempre se consulta antes.
- **OpenAPI y cliente se regeneran con scripts, nunca a mano** (`contracts/openapi/dataflow.json`,
  `packages/api-client/src/schema.ts`). Exportar **con Python 3.12** (3.13+ cambia frases HTTP).
- Errores API estables con `code` y `correlation_id`; excepciones de dominio sin HTTP.
- Python snake_case y mypy strict; TypeScript estricto; commits convencionales en español.
- Cada fase: `docs/architecture/phase-N.md`, ADR nuevo, versión de API y README actualizados.

## Comandos (PowerShell, desde la raíz salvo indicación)

```powershell
# Preparación
npm install
docker compose -f infrastructure/compose/compose.yaml up -d postgres   # requerido por pytest y la API

# Backend
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests -q
apps/api/.venv/Scripts/python.exe -m ruff check apps/api/src apps/api/tests apps/api/migrations apps/api/scripts
apps/api/.venv/Scripts/python.exe -m ruff format --check apps/api
Push-Location apps/api; .venv/Scripts/python.exe -m mypy; Pop-Location

# Web y contratos
npm run typecheck
npm run lint
npm run build
npm run format:check
npm run contracts:check

# Contrato HTTP (el .venv usa Python 3.12.10; no usar `py` por defecto, que es 3.14)
apps/api/.venv/Scripts/python.exe apps/api/scripts/export_openapi.py
npm run api:generate
apps/api/.venv/Scripts/python.exe apps/api/scripts/export_openapi.py --check

# E2E (requiere `npm run build`; API en 8001, web en 3100, base dataflow_e2e; en serie, workers: 1)
apps/api/.venv/Scripts/python.exe apps/api/scripts/prepare_e2e_db.py
npm run test:e2e

# Ejecutar en local
Push-Location apps/api; .\.venv\Scripts\python.exe -m dataflow.bootstrap.run --with-worker; Pop-Location
npm run dev --workspace @dataflow/web -- --port 3002
```

Batería completa = pytest + ruff + mypy + typecheck + lint + build + format:check + contracts:check +
`export_openapi.py --check` + test:e2e.

## Estado (2026-11-08)

| Fase | API  | Rama                           | Estado                                                                       |
| ---- | ---- | ------------------------------ | ---------------------------------------------------------------------------- |
| 1–3  | 0.5  | `main`                         | contratos, datasets/ejecuciones separados, semántica                         |
| 4    | 0.6  | `feat/fase-4-planificacion`    | planes versionados, catálogo `analysis-v1`, worker por pasos                 |
| 5    | 0.7  | `feat/fase-5-limpieza`         | trim/filter_rows, vista previa, aprobación, derivada; con commits, sin push  |
| 6A   | 0.8  | `feat/fase-6-conversiones`     | tablas tipadas, cast, normalize_null_tokens, deduplicate; migración 0007     |
| 6B   | 0.9  | `feat/fase-6-conversiones`     | csv-quality-v2, conjuntos de reglas, quality.evaluate@2; migración 0008      |
| 7A   | 0.10 | `feat/fase-7-analisis`         | métricas, analytics.query@1, evidencia por cifra; migración 0009; con commit |
| 7B   | 0.11 | `feat/fase-7-analisis`         | analytics.query@2: comparaciones, ranking, % del total; `analysis-v6`        |
| 8    | 0.12 | `feat/fase-8-dashboards`       | dashboards persistidos, «Actualizar» explícito, historial; migración 0010    |
| 9    | 0.13 | `feat/fase-9-informes`         | informes, PDF en el worker (ReportLab), CSV estándar/Excel; migración 0011   |
| 10   | 0.14 | `feat/fase-10-copiloto`        | copiloto IA (Anthropic), propuestas validadas, cifras por evidencia; 0012    |
| 11   | 0.14 | `feat/fase-11*` (PR)           | 11.0 estabilización, query@3; pipeline 0013–0017 y 11F (0018) retirados      |
| 12A  | 0.14 | `feat/fase-12a-excel` (PR)     | importación .xlsx (`read_xlsx@1`, lector OOXML propio), `analysis-v8`        |
| A–C  | 0.17 | `develop`                      | dashboard descriptivo (`profile@2/@3`), interpretación, explicación IA (C2)  |
| 13   | 0.18 | `feat/fase-13-solo-automatico` | un solo recorrido automático; manual y política retirados; migración 0019    |

Tipos y celdas canónicas: `platform/tabular.py` (hash lógico único). `tests/test_text_golden.py` protege los
resultados de las tablas de texto y `tests/test_analytics_query_v1_golden.py` los de `analytics.query@1`:
no regenerar sus referencias para hacer pasar una prueba.
Integración: `develop` contiene las Fases 4 a 12A y A–C (merge `--no-ff` o PR). Fase 13: ADR-026 sustituye
al principio híbrido y a ADR-023; las pruebas de los servicios conservados sin rutas públicas usan
`apps/api/tests/service_routes.py` (router sólo de pruebas). Lo siguiente es la Fase 14 (limpieza, calidad y
análisis automáticos sobre los motores conservados). Fase 7 completa (7A y 7B): ADR-018 y
ADR-019; `analytics.query@1` no cambia y la interfaz usa `@2`. Fase 8: ADR-020; `dashboards` no importa
planning, executions ni analytics (puerto en `bootstrap/dashboards_access.py`, prueba AST). Fase 9:
ADR-021; el PDF es una ejecución `report_render` (entrada `report` y operación interna fuera del
catálogo, `bootstrap/reports_access.py`). El perfil CSV `standard` (`platform/csv_export.py`) no cambia
nunca: garantiza la ida y vuelta con la ingesta.
IA: `DATAFLOW_AI_PROVIDER=fake` en E2E; `tests/ai/test_ai_live.py` sólo corre con `DATAFLOW_AI_LIVE_TESTS=1` y
clave. Cambiar el prompt de `copilot/overview.py` exige subir su versión. Al escribir archivos desde scripts en Windows, forzar LF.
Pendientes conocidos: deuda de nombre `dataset_import_bindings` (ADR-015); tablas sin uso de las Fases 4–10
y dependencia `reportlab` sin uso (decidir en la Fase 14). Al añadir una migración, las pruebas de migraciones
anteriores excluyen sus tablas nuevas (`LATER_TABLES`).

## Forma de trabajo

Ritmo desde la Fase 8 (para avanzar más rápido):

- **1 o 2 etapas por fase.** Normalmente: etapa 1 = backend (dominio, migración, API, contrato y cliente
  regenerados, pruebas); etapa 2 = interfaz, E2E y documentación.
- **Una sola propuesta corta antes de programar**: contradicciones con el código real, plan de 1 o 2 etapas
  y sólo las decisiones que bloqueen o no se puedan deshacer (cambios de contrato existente, borrado de
  datos, dependencias nuevas). Las demás se toman con la opción recomendada y se registran en el ADR de
  la fase. Si no hay decisiones bloqueantes, decirlo y esperar sólo el «adelante».
- **Durante el trabajo**: sólo las pruebas del área que se toca (rápidas).
- **Al final de cada etapa**: batería completa y resumen breve (qué se hizo, resultados, decisiones tomadas
  por cuenta propia). Sin tablas de detalle salvo que algo falle.
- **Al terminar la fase**: commits convencionales (puede ser uno por etapa) y merge `--no-ff` en `develop`.
  Repetir la batería sobre `develop` **sólo si `develop` avanzó** desde que se creó la rama (si no, el
  árbol resultante es el mismo ya probado). Pedir confirmación **una sola vez**, con el resumen final,
  antes del commit y el merge. **Nunca push sin preguntar.**
- No cambia: migraciones aditivas, OpenAPI y cliente regenerados con scripts (nunca a mano), regresión de
  resultados existentes, reglas de módulos y señalar contradicciones entre el diseño pedido y el código.
