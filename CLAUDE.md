# DataFlow AI — guía para Claude

Plataforma de análisis de datos **supervisado** sobre CSV propios. Monorepo: `apps/api` (FastAPI, monolito
modular + worker del mismo código), `apps/web` (Next.js), `packages/api-client` (cliente generado desde
OpenAPI), `contracts/` (OpenAPI vigente y contratos de diseño `analysis/v1`), `docs/` (arquitectura y ADR).
Documentación y UI en español.

## Principio híbrido

- **El motor determinista calcula** (Polars, hashes canónicos, conteos exactos sobre todo el dataset).
- **La persona aprueba** el efecto exacto (`effect_sha256`) antes de publicar cualquier transformación.
- **La IA sólo propondrá** operaciones del catálogo; nunca autoriza ni ejecuta. Hoy no hay proveedor de IA.
- El original y las versiones publicadas son inmutables: limpiar crea una versión derivada con linaje.

Referencias obligatorias: `docs/architecture/phase-1/execution-contract.md` (catálogo objetivo, gramáticas
de conversión §3, hash canónico §6), `docs/architecture/phase-N.md` y `docs/adr/0NN-*.md`.

## Arquitectura y reglas de módulos

Módulos en `apps/api/src/dataflow/modules/`: identity, projects, audit, datasets, ingestion, understanding,
quality, planning, executions, cleaning, analytics. Composición en `bootstrap/` (`bootstrap/operations.py` une
descriptor de catálogo + ejecutor y falla al arrancar si falta uno).

- Capas: domain (sin frameworks) → application (dominio + puertos) → infrastructure → presentation (HTTP/DTO).
  Domain y application no importan infrastructure.
- Entre módulos **sólo** `dataflow.modules.<m>.public` o `.contracts`. Dependencias acíclicas.
- **executions** no importa planning, cleaning, quality, ingestion, understanding ni analytics: recibe puertos
  (`StepRegistry`, `StepExecutor`, `InputResolver`, finalizadores, ganchos de publicación).
- planning no importa polars/duckdb ni implementaciones de operaciones (validación pura en `planning/domain.py`).
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
  nuevas a columnas nuevas en tablas existentes (ver ADR-014/015).
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

## Estado (2026-11-05)

| Fase | API  | Rama                        | Estado                                                                       |
| ---- | ---- | --------------------------- | ---------------------------------------------------------------------------- |
| 1–3  | 0.5  | `main`                      | contratos, datasets/ejecuciones separados, semántica                         |
| 4    | 0.6  | `feat/fase-4-planificacion` | planes versionados, catálogo `analysis-v1`, worker por pasos                 |
| 5    | 0.7  | `feat/fase-5-limpieza`      | trim/filter_rows, vista previa, aprobación, derivada; con commits, sin push  |
| 6A   | 0.8  | `feat/fase-6-conversiones`  | tablas tipadas, cast, normalize_null_tokens, deduplicate; migración 0007     |
| 6B   | 0.9  | `feat/fase-6-conversiones`  | csv-quality-v2, conjuntos de reglas, quality.evaluate@2; migración 0008      |
| 7A   | 0.10 | `feat/fase-7-analisis`      | métricas, analytics.query@1, evidencia por cifra; migración 0009; con commit |
| 7B   | 0.11 | `feat/fase-7-analisis`      | pendiente: comparaciones, ranking, participación (misma rama)                |

Tipos y celdas canónicas: `platform/tabular.py` (hash lógico único). `tests/test_text_golden.py` protege los
resultados de las tablas de texto: no regenerar sus referencias para hacer pasar una prueba.
Integración: `develop` contiene las Fases 4 a 6 (merge `--no-ff`). La Fase 7 se mezcla en `develop` al
terminar la 7B. **Traspaso 7B**: sección «Pendiente: 7B» de `docs/architecture/phase-7.md` (decisiones
aprobadas D7/D9, desempate, plan B1-B4 y lo descubierto en 7A).
Pendientes conocidos: deuda de nombre `dataset_import_bindings` (ADR-015); copiar reglas de calidad y
métricas entre importaciones (ADR-017, ADR-018).

## Forma de trabajo

- Plan antes de programar; esperar aprobación. Etapas pequeñas y verificables, una a la vez.
- Al cerrar cada etapa, ejecutar la batería correspondiente y mostrar los resultados reales.
- **Sin commits ni push sin permiso explícito.** Sin modificar contratos generados a mano.
- Señalar contradicciones entre el diseño pedido y el código real antes de implementar.
