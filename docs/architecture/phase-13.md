# Fase 13 — Un solo recorrido automático

Estado: **implementada** (API 0.18.0, migración 0019). Decisión: [ADR-026](../adr/026-fully-automatic-single-path.md).

## Objetivo

Dejar un único recorrido, sin interacción manual: **subir un archivo → resultados**. Se retiran el
pipeline gobernado por política (Fase 11A–11E) y todas las funciones manuales de las Fases 4 a 10
de la API y de la interfaz. La Fase 14 hará que ese recorrido use los motores conservados
(limpieza segura, reglas de calidad, análisis con evidencia).

## Recorrido vigente

```
Subida (CSV o .xlsx) ──▶ original inmutable + hash
        │
        ▼ worker: csv_import
ingestion.read_csv@1 / read_xlsx@1 → understanding.profile@3 → quality.evaluate@1
        │                (dashboard descriptivo + interpretación por reglas)
        ▼
publicación ──▶ overview_audit (sólo si hay proveedor de IA configurado)
        │
        ▼
Interfaz: «Tu análisis automático» + «Explicación automática IA», sin botones de decisión
```

## Qué se retiró

| Área                             | Backend                                                                                    | Interfaz                                                                     |
| -------------------------------- | ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| Pipeline por política (11A–11E)  | módulos `automation`, `analysis_sessions`, `templates`; `reconcile()` del worker; 20 rutas | `features/automation`, `templates`, `analysis-sessions`                      |
| Semántica (Fase 3)               | 4 rutas                                                                                    | revisión semántica                                                           |
| Planes (Fase 4)                  | 7 rutas                                                                                    | editor de planes y ejecuciones                                               |
| Limpieza supervisada (Fases 5–6) | 6 rutas (se conserva `GET /versions/{id}/lineage`)                                         | propuesta, vista previa, aprobación                                          |
| Reglas de calidad (6B)           | 5 rutas                                                                                    | editor de reglas                                                             |
| Métricas (7)                     | 3 rutas (se conservan resultado, evidencia y CSV del análisis)                             | etapa de análisis                                                            |
| Dashboards editables (8)         | servicio y 6 rutas                                                                         | etapa de visualización                                                       |
| Informes y PDF (9)               | servicio, paso `reports.render_pdf@1` y 10 rutas                                           | etapa de explicación                                                         |
| Copiloto (10) y auditoría 11F    | chat, acciones, prompts y 11 rutas                                                         | panel del copiloto                                                           |
| Análisis a petición              | `POST /versions/{id}/analyses`, `cancel-analysis`                                          | —                                                                            |
| Demo de ventas                   | —                                                                                          | `/workspace/ventas-2026`, `/analysis`, `/dashboards`, `/reports`, `/history` |

Las tablas de las Fases 3–10 y 11F **se conservan con sus datos** (sólo quedan sus clases de
tabla); las de 11A–11E se eliminan en la migración 0019.

## Qué se conservó para la Fase 14

- Servicios y motores: planning, cleaning (vista previa, efecto, aplicación, propuesta de 11A),
  quality (`csv-quality-v2`), analytics (`analytics.query@1..3`, métricas, evidencia),
  understanding (revisiones semánticas). Las pruebas los ejercitan con
  `apps/api/tests/service_routes.py`, un router sólo de pruebas.
- Copiloto reducido a la explicación automática: disponibilidad, presupuesto, verificación de
  cifras y registro de consumo.
- `understanding/templates.py`: detección pura de contextos (antes en `templates`), sin cambios de
  resultado.

## Contrato HTTP (0.18.0): de 108 a 34 operaciones

Quedan: identidad, proyectos, importaciones (CSV, XLSX e inspección), versiones (detalle,
diagnóstico, vista previa, original, exportación CSV), ejecuciones (lectura, artefactos,
representaciones, perfil, calidad, cancelar importación), linaje, resultado/evidencia/CSV de
análisis y la explicación automática (`/versions/{id}/overview-audit`).

## Pruebas

- Arquitectura: `test_retired_policy_pipeline_does_not_come_back` y `test_context_detection_is_pure`.
- Migraciones: `test_migration_0019.py` (elimina las tablas y sus datos, conserva el resto, el
  downgrade las recrea vacías). Las pruebas de 0010–0012 y 0018 insertan sus registros sin los
  servicios retirados.
- E2E: `automatic-overview.spec.ts` (sin botones de decisión, rutas retiradas → 404),
  `csv.spec.ts` y `projects.spec.ts`.

## Pendiente (Fase 14)

Limpieza automática segura, dashboard completo en la versión limpia, reglas de calidad deducidas,
análisis con evidencia (`analytics.query@3`), robustez del encadenado, Excel en el asistente y
E2E de cero clics con XLSX. Decidir el destino de las tablas sin uso de las Fases 4–10 y de
`reportlab`.

## Fase 13B — Excel e IA sin configuración

Estado: **implementada** (API 0.19.0, sin migración). Decisión: [ADR-027](../adr/027-excel-and-ai-without-configuration.md).

Cierra los dos pasos que aún dependían de una persona tras la Fase 13:

| Antes (0.18)                                                                   | Ahora (0.19)                                                                                                                                                         |
| ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `uploadXlsx` exigía `sheet`; la interfaz pedía hoja o tabla y fila de cabecera | Sin `sheet` ni `table`, el sistema aplica `xlsx-selection-v1` al recibir el libro y lo informa en `source_selection` (versión y plan). Con `sheet`, igual que en 12A |
| `/new` sólo aceptaba CSV                                                       | `/new` y el espacio de trabajo aceptan `.csv` y `.xlsx` con un único botón «Subir y analizar»; la versión muestra «Se importó la hoja… No se importaron…»            |
| El CSV ofrecía elegir separador                                                | Siempre detección automática en la interfaz (la API conserva el parámetro)                                                                                           |
| `DATAFLOW_AI_PROVIDER=disabled` por defecto                                    | `auto` por defecto: Anthropic si hay clave, si no desactivada (`disabled`, `fake` y `anthropic` siguen)                                                              |

- `ingestion.read_xlsx@1` y el catálogo `analysis-v10` no cambian: la decisión se toma antes y
  se fija como parámetros explícitos del plan.
- `inspectXlsx` sin `sheet` ni `table` devuelve la elección automática en `selection`; la
  interfaz ya no lo usa.
- Pruebas: reglas de elección (títulos, tablas, hojas ocultas, ilegibles o protegidas, empates),
  subida sin hoja con idempotencia y plan, rechazo de libros dañados, `auto` con y sin clave; E2E
  `xlsx.spec.ts` (libro con portada y título importado con cero clics desde `/new`).

## Fase 13C — Las cargas esperan en cola

Estado: **implementada** (API 0.20.0, sin migración). Decisión: [ADR-028](../adr/028-upload-queue.md).

| Antes (0.19)                                                                             | Ahora (0.20)                                                                                                 |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| 409 `QUEUE_LIMIT` con 3 trabajos activos; 409 `PROJECT_BUSY` con otra carga del proyecto | La carga se registra y espera en cola; sólo se rechaza con 50 trabajos pendientes (`QUEUE_LIMIT`)            |
| La persona debía esperar y volver a subir                                                | El worker ejecuta como máximo 3 trabajos por propietario y una importación por proyecto, en orden de llegada |

- Pruebas: `test_uploads_wait_in_queue_instead_of_being_rejected` (límites al reclamar y orden) y
  `test_queued_uploads_are_processed_in_order`.
