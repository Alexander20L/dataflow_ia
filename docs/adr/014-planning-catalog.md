# ADR-014 — Planes versionados, catálogo de operaciones y worker por pasos

Estado: implementado en Fase 4 / API 0.6. Desarrolla el contrato de planes y el registro de operaciones de Fase 1 ([execution-contract](../architecture/phase-1/execution-contract.md), [module-boundaries](../architecture/phase-1/module-boundaries.md)).

## Contexto

Hasta 0.5 las ejecuciones usaban planes de sistema construidos al vuelo (`csv_import`, `table_analysis`) y el worker despachaba por tipo de ejecución con una correspondencia operación → salida fijada en código. El usuario no podía componer, guardar ni volver a ejecutar un plan, y añadir operaciones (limpieza en Fase 5) obligaba a tocar executions.

## Decisión

- Nuevo módulo planning (domain/application/infrastructure/presentation, `contracts.py`, `public.py`). `OperationDescriptor` declara nombre, versión, entrada (`source|table`), salida (`table|profile|quality`), esquema Pydantic de parámetros, requisitos semánticos y `transforms_data`. Las referencias a columnas se marcan en el esquema con `x-dataflow-column-ref` y se validan por ID.
- Validación pura en `planning/domain.py`: devuelve problemas con código (`EMPTY_PLAN`, `TOO_MANY_STEPS`, `DUPLICATE_STEP_ID`, `INVALID_STEP_REFERENCE`, `UNSUPPORTED_OPERATION`, `INPUT_KIND_MISMATCH`, `INVALID_PARAMETERS`, `UNKNOWN_COLUMN`, `SEMANTIC_REQUIREMENT_MISSING`), nunca excepciones por contenido incompleto. Estado derivado: incompleto si hay problemas, válido si no. Un plan incompleto se guarda pero no se encola (422 `PLAN_INCOMPLETE`).
- Catálogo `analysis-v1` limitado a operaciones con ejecutor: `ingestion.read_csv@1`, `understanding.profile@1`, `quality.evaluate@1`. Ninguna exige revisión semántica (se mantiene Fase 3). Cada módulo es dueño del esquema de parámetros de su operación; bootstrap (`bootstrap/operations.py`) une descriptor y ejecutor y falla al arrancar si falta uno o la salida no coincide.
- executions sigue siendo dueño de `execution_plan_revisions` y expone `save_plan_revision`, `plan_revision`, `lock_plan_family`, `plans_for_project` y `enqueue_existing_plan`. planning depende de `executions.public`; executions recibe el registro como puerto (`StepRegistry`, `StepExecutor`, `InputResolver`) y no importa planning, cleaning, quality, ingestion ni understanding (prueba AST).
- **Vínculo 1:1 en tabla aparte** (`execution_plan_bindings`: proyecto, artefacto, hash y revisión semántica) en lugar de columnas nuevas en `execution_plan_revisions`. Añadir columnas hacía que el ORM las emitiera en todo INSERT/SELECT de planes y rompía el código y las pruebas 0.5 sobre esquemas anteriores; la tabla aparte deja intactos los planes de sistema. Un plan de usuario es una revisión con vínculo; los de sistema no aparecen en el listado.
- `planning_validations` (por revisión y versión de catálogo, inmutable, se recalcula sólo si cambia el catálogo) y `planning_create_requests` (Idempotency-Key de creación) pertenecen a planning.
- Revisiones: `expected_revision` bajo lock de la revisión 1 de la familia (fila estable); el segundo guardado concurrente lee la cabeza nueva y recibe 409. Sin cambios no se crea revisión. La entrada de una familia no cambia entre revisiones; al guardar y al encolar se vuelve a verificar la tabla exacta y nunca se sustituye por la versión predeterminada.
- **Worker por pasos**: recorre los pasos del plan y pide cada ejecutor al registro. Un subproceso por paso (`processor.py --mode read|profile|quality`) con un plazo total compartido que no supera `timeout_seconds`; la lease de 120 s sigue cubriendo cálculo y publicación. El paso de lectura entrega al siguiente la tabla con el separador efectivo y el hash del original, que el perfil conserva como procedencia. Los planes 0.5 ya tenían formato de pasos: el adaptador es común.
- El worker reclama sólo los tipos de ejecución declarados (`csv_import`, `table_analysis`, `plan`); un worker anterior no reclama `plan`.
- Las rutas de análisis 0.5 (`/versions/{id}/analyses`, `/executions/{id}/quality|profile`) pasan a ingestion con el mismo contrato (diff OpenAPI vacío).

## Alternativas y consecuencias

Ejecutar todos los pasos de diagnóstico en un único subproceso evitaría arrancar Python+Polars varias veces, pero mantendría un ejecutor fusionado que el registro no describe y que la limpieza tendría que reabrir. Se aceptó el coste: cada paso suma ~0,9 s de arranque en Windows (≈0,5 s Polars, ≈0,2 s Pydantic), una importación pasa de un subproceso a tres y, en E2E en serie, los recorridos con CSV tardan 3-6 s más. Con varios workers de Playwright en un equipo modesto la CPU se satura y fallan también recorridos de `main`: se documenta ejecutar `--workers=1` en esos equipos. Si el coste importa, la optimización prevista es agrupar pasos contiguos de diagnóstico sobre la misma entrada dentro del mismo ejecutor de motor, sin cambiar planes ni hashes.

Los resultados no cambian: una prueba de regresión compara byte a byte (salvo la versión de Polars, fijada por el lock) el perfil y la calidad publicados frente a referencias generadas con el pipeline anterior para CSV con coma, `;` + BOM + multilínea y tabuladores.

El E2E de un requisito semántico real se añadirá con la primera operación que lo declare (Fase 7, métricas que exigen una columna confirmada como medida). El dominio ya lo valida (`ConfirmedColumnRole`) y la UI enlaza ese problema con Entendimiento.
