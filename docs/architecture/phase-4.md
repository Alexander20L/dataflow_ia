# Fase 4 — Planificación y catálogo de operaciones

API 0.6. [ADR-014](../adr/014-planning-catalog.md). Planning conserva planes como revisiones inmutables sobre una tabla exacta, los valida contra un catálogo y los ejecuta mediante un registro de operaciones. No transforma datos: la limpieza llega en Fase 5.

## Recorrido e interfaz

CSV procesado → **Planes y ejecuciones** → nuevo plan → tabla de entrada y revisión semántica opcional → añadir operaciones del catálogo → parámetros → guardar (revisión inmutable) → resumen con problemas pendientes → corregir → guardar → ejecutar → resultados en el historial de ejecuciones.

- Selector de planes de la versión y «Nuevo plan». La tabla de un plan guardado no cambia; sus revisiones sí pueden cambiar pasos y revisión semántica.
- Catálogo con lo aplicable a la tabla: «Leer CSV» se muestra deshabilitado (requiere el original) y los requisitos que faltan se etiquetan.
- Formulario de parámetros generado desde el JSON Schema del catálogo: constantes, enumeraciones, `T | None`, listas, booleanos, números y selectores de columnas (`x-dataflow-column-ref`).
- Resumen: estado, tabla de entrada con SHA-256 completo y versión, revisión semántica fijada, hash del contenido y versión de catálogo. Cada problema enlaza a dónde se resuelve: el paso, el catálogo o **Entendimiento** (cambia la etapa del workspace).
- Cambios sin guardar: insignia, aviso al recargar/cerrar/navegar y confirmación al cambiar de plan, versión, página o carga (hook compartido con el editor semántico). Un conflicto conserva el borrador y ofrece cargar la revisión del servidor.
- «Ejecutar plan» sólo con la revisión guardada, válida y sin cambios pendientes. Sustituye al formulario ad hoc de 0.5; el endpoint `/versions/{id}/analyses` se mantiene por compatibilidad.

## Catálogo `analysis-v1`

| Operación                 | Entrada → salida | Parámetros                                                                                           |
| ------------------------- | ---------------- | ---------------------------------------------------------------------------------------------------- |
| `ingestion.read_csv@1`    | fuente → tabla   | separador efectivo `,`/`;`/TAB, solicitado opcional; UTF-8-sig, parser estricto, vacíos→null (fijos) |
| `understanding.profile@1` | tabla → perfil   | `algorithm`: `column-profile-v1`                                                                     |
| `quality.evaluate@1`      | tabla → calidad  | `rule_set` `csv-quality-v1`, reglas exactas Q-001/Q-002/Q-003, `score` `cell_completeness_v1`        |

Ninguna exige revisión semántica (decisión de Fase 3). Los parámetros válidos se guardan completos, con los valores por defecto del catálogo; los incompletos se guardan tal cual para corregirlos.

## Validación

Pura, sin Polars ni SQL. Hasta 16 pasos con IDs únicos; cada paso consume el input o la salida tabular de un paso anterior.

| Código                         | Se produce cuando                                                        | Se resuelve en |
| ------------------------------ | ------------------------------------------------------------------------ | -------------- |
| `EMPTY_PLAN`                   | el plan no tiene pasos                                                   | catálogo       |
| `TOO_MANY_STEPS`               | más de 16 pasos                                                          | pasos          |
| `DUPLICATE_STEP_ID`            | dos pasos con el mismo ID                                                | paso           |
| `INVALID_STEP_REFERENCE`       | referencia adelantada, a sí mismo, inexistente o a una salida no tabular | paso           |
| `UNSUPPORTED_OPERATION`        | operación/versión fuera del catálogo                                     | paso           |
| `INPUT_KIND_MISMATCH`          | la operación requiere otra entrada (p. ej. `read_csv` sobre una tabla)   | paso/entrada   |
| `INVALID_PARAMETERS`           | parámetros que no cumplen el esquema                                     | paso           |
| `UNKNOWN_COLUMN`               | ID de columna inexistente en la tabla fijada                             | paso           |
| `SEMANTIC_REQUIREMENT_MISSING` | falta revisión fijada o una columna confirmada con el rol requerido      | Entendimiento  |

Una operación desconocida no genera además errores de referencia en los pasos que dependen de ella.

## API

| Ruta                                                     | Función                                                                    |
| -------------------------------------------------------- | -------------------------------------------------------------------------- |
| GET `/api/v1/operations`                                 | Catálogo con descriptores y esquemas de parámetros                         |
| GET `/api/v1/representations/{id}/applicable-operations` | Aplicables y requisitos que faltan; `?semantic_revision_id=` opcional      |
| POST `/api/v1/projects/{id}/plans`                       | Revisión 1 con `Idempotency-Key`; misma clave y contenido devuelve el plan |
| POST `/api/v1/plans/{family_id}/revisions`               | Nueva revisión con `expected_revision`; 409 si cambió; sin cambios no crea |
| GET `/api/v1/plans/{revision_id}`                        | Revisión exacta con su validación                                          |
| GET `/api/v1/projects/{id}/plans`                        | Última revisión de cada plan, paginada; excluye planes de sistema          |
| POST `/api/v1/plans/{revision_id}/executions`            | Encola la revisión guardada (`kind: plan`); 422 `PLAN_INCOMPLETE`          |

Sesión/propietario en todas; Origin y CSRF en mutaciones. Ajeno/inexistente: 404. Tabla de otro proyecto o hash distinto: 409 `INPUT_MISMATCH`. Revisión semántica que no coincide: 409. Archivado: lectura sí, guardar/ejecutar 409 `PROJECT_ARCHIVED`. Claves o valores no canónicos en parámetros: 422 `PLAN_NOT_CANONICAL`. Cambio aditivo en el contrato: 7 operaciones nuevas y `plan` en el enum `kind` de `ExecutionResponse`.

## Persistencia

Migración 0005, sólo aditiva:

- `execution_plan_bindings` (executions): vínculo 1:1 de una revisión de usuario con proyecto, artefacto de entrada, su hash y revisión semántica. Los planes de sistema no tienen vínculo.
- `planning_validations` (planning): problemas, validez y fecha por revisión y versión de catálogo. Se recalcula sólo si cambia `catalog_version`.
- `planning_create_requests` (planning): identidad de la solicitud de creación y revisión resultante.

Las tres son inmutables (trigger `dataflow_immutable_record`). El downgrade se rechaza si hay planes de usuario o validaciones. `execution_runs.plan_id` apunta a la revisión exacta: encolar no copia el plan. `expected_revision` se protege con lock de la revisión 1 de la familia más la unicidad `(family_id, revision)`.

## Ejecución por pasos

El worker resuelve cada paso en el registro y ejecuta un subproceso por paso con plazo total compartido (≤ `timeout_seconds`, lease de 120 s intacta). Sólo reclama los tipos que conoce: un worker anterior a 0.6 no reclama `plan`. Una operación desconocida falla con `UNSUPPORTED_OPERATION` sin publicar nada.

Coste medido en Windows: ~0,9 s de arranque por subproceso; una importación pasa de ~0,9 s a ~2,7 s de cálculo. Resultados idénticos a 0.5 (prueba de regresión con referencias del pipeline anterior).

## Compatibilidad

Las ejecuciones 0.5 (`csv_import`, `table_analysis`) se ejecutan con el mismo adaptador y se consultan igual; sus planes validan sin problemas contra `analysis-v1`. Las rutas de análisis 0.5 viven ahora en ingestion con contrato idéntico.

## Pendiente

- **E2E de requisito semántico**: añadido en [Fase 6](phase-6.md) (`cleaning-cast.spec.ts`) con la primera regla semántica real: convertir a número un identificador confirmado exige confirmación explícita. El requisito positivo (columna confirmada como medida y fecha de negocio) tiene su E2E desde la [Fase 7](phase-7.md) (`analytics.spec.ts`).
- Limpieza (`cleaning.*`), vista previa y aprobación: Fase 5.

## Pruebas

Dominio: caso positivo y negativo por código, incluido el requisito semántico que se resuelve al fijar una revisión. Migración 0005 desde datos 0.5 reales (ida y vuelta, `compare_metadata`, inmutabilidad, downgrade bloqueado). Worker: regresión byte a byte, worker sin `plan`, operación desconocida, plazo compartido, registro coherente. Integración: guardar → recargar → ejecutar, cambio de versión predeterminada sin alterar la entrada, problemas, idempotencia, accesos cruzados, CSRF/Origin, archivado, semántica fijada y falsificada, compatibilidad 0.5 y revisiones concurrentes. Navegador: `planning.spec.ts` (plan vacío → `EMPTY_PLAN` → catálogo → corregir → aviso de cambios → guardar → ejecutar → recargar → nueva versión predeterminada → ejecutar sobre la tabla fijada); `executions.spec.ts` y `semantics.spec.ts` ejecutan desde planes guardados.

Las pruebas de navegador comparten una API y un único worker de cola: en paralelo agotan las esperas de 20 s, también en `main`. Por eso `playwright.config.ts` fija `workers: 1`.

### Verificación local — 2026-11-05

Python 3.12.10 (como CI y Docker; con 3.13+ el contrato exportado difiere en dos frases HTTP). Backend: 81 pruebas, Ruff y mypy strict sin errores; `export_openapi.py --check` correcto. Web: typecheck, lint y build correctos. E2E en serie: 11/11; `main` en las mismas condiciones: 10/10. Con 3 workers fallan 7/10 de `main` y 8/11 de esta rama por saturación de CPU.
