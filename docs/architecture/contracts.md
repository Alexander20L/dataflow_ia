# Contratos propuestos — v1

> Diseño conceptual inicial. El contrato implementado se consulta en `contracts/openapi/dataflow.json` y el recorrido 0.3 en `increment-03.md`. Para la siguiente separación de datasets/planes/ejecuciones, consultar [Fase 1](phase-1/README.md). Las rutas de la tabla siguiente no describen por sí solas el estado actual.

No son endpoints implementados. FastAPI será la fuente del esquema OpenAPI; se exportará una instantánea y se generará packages/api-client en CI. Revisar cambios incompatibles antes de publicar.

| Operación         | Endpoint propuesto                    | Resultado                               |
| ----------------- | ------------------------------------- | --------------------------------------- |
| Proyectos         | GET/POST /api/v1/projects             | Lista paginada / 201                    |
| Carga             | POST /api/v1/projects/{id}/uploads    | Sesión con límites y destino autorizado |
| Confirmar ingesta | POST /api/v1/uploads/{id}/complete    | 202, execution_id y Location            |
| Versiones         | GET /api/v1/datasets/{id}/versions    | Metadatos autorizados                   |
| Vista previa      | GET /api/v1/versions/{id}/preview     | Paginación, columnas y filas acotadas   |
| Plan              | POST /api/v1/projects/{id}/plans      | Revisión inmutable                      |
| Ejecutar          | POST /api/v1/executions               | 202 con Idempotency-Key                 |
| Estado            | GET /api/v1/executions/{id}           | Estados, progreso y artefactos          |
| Cancelar          | POST /api/v1/executions/{id}/cancel   | Solicitud de cancelación                |
| Propuesta         | GET /api/v1/executions/{id}/proposals | Operaciones y evidencia                 |
| Aprobar           | POST /api/v1/proposals/{id}/approvals | Actor, hash y dataset_version_id        |
| Artefactos        | GET /api/v1/artifacts/{id}            | Metadatos / acceso temporal             |

Fechas ISO-8601, instantes UTC, identificadores UUID, paginación acotada y orden estable. Error: `{ "code": "VERSION_CONFLICT", "message": "…", "correlation_id": "…", "details": [] }`. 401 sin sesión, 403/404 según política de visibilidad, 409 para conflictos, 422 para validación, 429 para límites.

Dentro del monolito: contratos públicos tipados, IDs y DTOs inmutables, sin objetos ORM compartidos. Eventos para hechos ya confirmados. Worker: `{ job_id, execution_id, stage_id, attempt, correlation_id, schema_version }`; recarga estado y valida permisos/contexto guardados, entradas e idempotencia. Nunca secretos ni tablas completas en la cola.
