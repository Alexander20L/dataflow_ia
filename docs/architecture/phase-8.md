# Fase 8 — Dashboards persistidos

API 0.12. [ADR-020](../adr/020-persisted-dashboards.md).

Objetivo: el usuario crea dashboards con sus propios análisis, cierra sesión y los recupera con sus gráficos y su configuración. El dashboard no calcula nada propio: cada tarjeta apunta a un análisis (`analytics.query@2`) y a la ejecución exacta que muestra.

## Recorrido

Análisis → «Calcular» → «Añadir a un dashboard» (dashboard nuevo o existente, título, forma, tamaño y métrica) → etapa **Visualización** → cuadrícula de tarjetas → mover con botones, cambiar tamaño, quitar, filtros globales → «De dónde sale este número» desde cada cifra → «Actualizar sobre vN» cuando se quiera recalcular.

## Modelo

Revisiones inmutables por dashboard, como la semántica, las reglas y las métricas: crear con `Idempotency-Key`, revisar con `expected_revision` (409 `DASHBOARD_CONFLICT`) y sin cambios no hay revisión. Un dashboard pertenece a un proyecto.

| Elemento      | Contenido                                                                                                                  |
| ------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Tarjeta       | `id` estable, título, `plan_revision_id`, `execution_id` (nulo si no se pudo ejecutar), forma, tamaño, métrica (`m0`…)     |
| Forma         | `kpi` (resultado de una fila), `line` (agrupación temporal), `bar` (una dimensión o sólo el periodo), `table` (cualquiera) |
| Tamaño        | `small`, `medium`, `large` en una cuadrícula CSS de 6 columnas (2, 3 y 6); una sola columna en móvil                       |
| Filtro global | dimensión (por ID) y valores canónicos de la Fase 6                                                                        |
| Revisión      | contenido con hash (dominio `dashboard`), `cause` (`create`, `edit`, `refresh`) y versión elegida al actualizar            |

Al guardar se valida cada tarjeta: plan `analytics.query@2` de un solo paso y del mismo proyecto, ejecución de esa misma revisión del plan, métrica existente y forma compatible con la consulta (422 `DASHBOARD_INVALID`).

## Estado de cada tarjeta

Un error de una tarjeta no rompe las demás. Cada tarjeta muestra la versión, la fecha de ejecución y su forma.

| Estado                         | Cuándo                                                                   |
| ------------------------------ | ------------------------------------------------------------------------ |
| `ready`                        | ejecución terminada con filas                                            |
| `pending`                      | en cola o en ejecución («Calculando…»; la vista se consulta de nuevo)    |
| `failed`                       | la ejecución falló (p. ej. `RESULT_TOO_LARGE`) — «Ejecución fallida»     |
| `insufficient_data`            | resultado sin filas — «Datos insuficientes»                              |
| `semantic_requirement_missing` | el plan no es válido por un requisito semántico pendiente                |
| `invalid_plan`                 | el plan no es válido por otro motivo (métrica no aplicable a la versión) |
| `not_executed`                 | la tarjeta no tiene ejecución                                            |

## Filtros globales

Una ejecución es fija y el dashboard no calcula: el filtro **sólo oculta filas** del resultado ya calculado. Las cifras y su evidencia no cambian, y el % del total sigue referido al total completo. Se aplica a las tarjetas cuya consulta agrupa por esa dimensión; en las demás (incluidos los KPI) la tarjeta dice «Filtro no aplicable». La aplicabilidad se calcula a partir de las dimensiones del plan.

## «Actualizar»

Acción explícita sobre la versión elegida (la que se está viendo); el dashboard nunca cambia solo al subir datos. Crea una revisión nueva (`cause: refresh`) y conserva la anterior.

- Un plan está fijado a su tabla: si la tarjeta ya apunta a la tabla y a la revisión semántica vigente de esa versión, se reutiliza su plan y se ejecuta de nuevo; si no, se crea **un plan nuevo** con los mismos pasos, la tabla de esa versión y su revisión semántica vigente. Los planes guardados no cambian (la lista de planes del proyecto crece con los creados por «Actualizar»).
- Si el plan nuevo no es válido (p. ej. la versión no tiene la semántica confirmada), la tarjeta queda sin ejecución y lo indica.
- Las tarjetas que comparten plan comparten ejecución. Las claves de planes y ejecuciones derivan de la `Idempotency-Key` de la solicitud: repetirla no crea nada nuevo.
- La revisión se crea al momento con las ejecuciones en cola; las tarjetas muestran «Calculando…» hasta que terminan.

## API 0.12

| Ruta                                            | Función                                                                  |
| ----------------------------------------------- | ------------------------------------------------------------------------ |
| GET `/api/v1/projects/{id}/dashboards`          | Dashboards del proyecto (revisión vigente y número de revisiones)        |
| POST `/api/v1/projects/{id}/dashboards`         | Alta (`Idempotency-Key`)                                                 |
| GET `/api/v1/dashboards/{family_id}`            | Revisión vigente y estado de cada tarjeta                                |
| POST `/api/v1/dashboards/{family_id}/revisions` | Nueva revisión (`expected_revision`, `Idempotency-Key`)                  |
| POST `/api/v1/dashboards/{family_id}/refresh`   | «Actualizar» sobre `version_id` (`expected_revision`, `Idempotency-Key`) |
| GET `/api/v1/dashboard-revisions/{revision_id}` | Revisión exacta                                                          |

Sesión y propietario en todas (ajeno: 404); Origin y CSRF en las mutaciones. Cambios aditivos: ningún contrato existente cambia.

## Arquitectura y persistencia

Módulo `dashboards` (contratos, dominio puro, aplicación, infraestructura, presentación). No importa planning, executions ni analytics: bootstrap (`dashboards_access.py`) le da planes, ejecuciones, versiones y la revisión semántica vigente por un puerto. La prueba AST `test_dashboards_depend_only_on_their_ports` lo protege.

Migración **0010**, sólo aditiva: `dashboard_families`, `dashboard_revisions` y `dashboard_save_requests` (las dos últimas inmutables por trigger). Downgrade bloqueado si hay dashboards. **Actualizar desde 0.11 / esquema 0009**: desplegar API y worker juntos.

## Interfaz

- Etapa **Visualización** activa para datos propios (la demostración del fixture no cambia).
- Gráficos con el componente `Chart` existente (ECharts, sin dependencias nuevas). Debajo de cada gráfico, «Ver cifras y su procedencia» lista los valores exactos, cada uno con su panel «De dónde sale este número»; los KPI y las tablas lo abren desde la cifra.
- **Historial de ejecuciones** (pendiente de la Fase 7): el panel de ejecuciones muestra el resultado de las ejecuciones de `analytics.query@1` y `@2`, con su procedencia.

## Pruebas

- API (`test_dashboards.py`): revisiones, conflicto, idempotencia (misma clave y otro cuerpo: 409), estado de cada tarjeta, filtro no aplicable, validación de la forma y de la ejecución, ejecución fallida y datos insuficientes sin romper las demás, «Actualizar» sobre la misma versión (planes reutilizados, ejecuciones nuevas, repetición idempotente) y sobre la v1 sin semántica (planes nuevos, requisito pendiente, planes guardados intactos), aislamiento por usuario, CSRF y versión ajena.
- Migración 0010 (`test_migration_0010.py`); las pruebas de 0005–0009 excluyen las tablas nuevas de su comparación de esquema.
- Navegador (`dashboards.spec.ts`): con un CSV propio, dos análisis añadidos a un dashboard (barras y KPI), mover y filtrar, procedencia desde la tarjeta, cerrar sesión, volver y encontrarlo igual (orden, tamaños, filtro, cifras), sin desbordamiento a 390 px.

### Verificación local — 2026-11-06

Python 3.12.10. Backend: 359 pruebas (Ruff y mypy strict sin errores), contrato exportado sin diferencias y `contracts:check` correcto. Web: typecheck, lint, format y build correctos. E2E en serie: 18/18.
