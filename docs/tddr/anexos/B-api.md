# Anexo B — Especificación de la API

La especificación completa y normativa es el contrato **OpenAPI 3.1**
[`contracts/openapi/dataflow.json`](../../../contracts/openapi/dataflow.json) (API **0.42.0**: 66 rutas,
69 operaciones, 220 esquemas), generado desde el código con `apps/api/scripts/export_openapi.py` y
verificado en CI con `--check`. El cliente TypeScript (`packages/api-client/src/schema.ts`) se genera desde
él. La documentación interactiva está en `/docs` de la API en marcha.

## B.1 Convenciones

- Prefijo `/api/v1`; JSON en UTF-8 salvo cargas (`text/csv`, `.xlsx`, `application/pdf`).
- Autenticación por cookie de sesión `dataflow_session` (HttpOnly). Los métodos no seguros exigen
  cabecera `X-CSRF-Token` (de `GET /auth/me`) y un `Origin` permitido.
- Cargas con cabecera `Idempotency-Key` (UUID): repetir la petición devuelve la misma versión.
- Revisiones inmutables con `expected_revision` (409 si cambió).
- Errores: cuerpo `{"code", "message", "correlation_id", ...}`; `code` es estable.
- Operaciones asíncronas: 202 con la versión y su `execution_id`; el progreso se consulta en
  `GET /versions/{id}/progress`.

## B.2 Operaciones por área

| Área           | Método y ruta                                                                         | operationId                                                                    | Propósito                                                               |
| -------------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------------------------- |
| Identidad      | POST `/auth/register`                                                                 | register                                                                       | Crear cuenta (201)                                                      |
|                | POST `/auth/login`                                                                    | login                                                                          | Iniciar sesión (cookie)                                                 |
|                | POST `/auth/logout`                                                                   | logout                                                                         | Cerrar sesión                                                           |
|                | GET `/auth/me`                                                                        | getSession                                                                     | Sesión actual y `csrf_token`                                            |
| Proyectos      | GET, POST `/projects`                                                                 | listProjects, createProject                                                    | Listar (paginado) y crear                                               |
|                | GET, PATCH `/projects/{project_id}`                                                   | getProject, updateProject                                                      | Leer y editar (con revisión)                                            |
|                | POST `/projects/{project_id}/archive`                                                 | archiveProject                                                                 | Archivar                                                                |
| Cargas         | POST `/projects/{id}/imports?file_name=`                                              | uploadCsv                                                                      | Subir CSV (`text/csv`, ≤ 5 MiB) → 202                                   |
|                | POST `/projects/{id}/imports/xlsx`, `/xlsx/inspect`                                   | uploadXlsx, inspectXlsx                                                        | Subir / inspeccionar Excel                                              |
|                | POST `/projects/{id}/imports/pdf`                                                     | uploadPdf                                                                      | Subir PDF con tablas                                                    |
|                | POST `/projects/{id}/imports/related`                                                 | uploadRelatedFiles                                                             | `{"files":[{"name","content_base64"}]}`, 2–5 archivos → vista principal |
|                | POST `/projects/{id}/imports/related/inspect`                                         | inspectRelatedFiles                                                            | Foto del esquema (`DataModel`), no guarda nada                          |
|                | POST `/projects/{id}/imports/postgresql`, `/postgresql/inspect`                       | importPostgresql, inspectPostgresql                                            | Copia de un esquema (202 `DatabaseCopy`) / foto                         |
|                | POST `/projects/{id}/imports/sqlserver`, `/sqlserver/inspect`                         | importSqlServer, inspectSqlServer                                              | Ídem para SQL Server                                                    |
|                | GET `/database-access`                                                                | getDatabaseAccess                                                              | Modo de acceso a bases e IP de salida                                   |
|                | GET `/database-copies/{copy_id}`                                                      | getDatabaseCopy                                                                | Estado de una copia en segundo plano                                    |
|                | GET `/datasets/summary`                                                               | getIngestionSummary                                                            | Resumen de cargas                                                       |
|                | POST `/executions/{id}/cancel`                                                        | cancelImport                                                                   | Cancelar una carga en cola                                              |
| Versiones      | GET `/projects/{id}/versions`                                                         | listVersions                                                                   | Versiones del proyecto                                                  |
|                | GET `/versions/{id}`                                                                  | getVersion                                                                     | Versión con `source_origin`                                             |
|                | GET `/versions/{id}/preview`                                                          | previewVersion                                                                 | Registros paginados (orden por columna, búsqueda literal)               |
|                | GET `/versions/{id}/reading`                                                          | getSourceReview                                                                | Decisiones de lectura                                                   |
|                | GET `/versions/{id}/diagnostic`                                                       | getDiagnostic                                                                  | Diagnóstico técnico                                                     |
|                | GET `/versions/{id}/lineage`                                                          | getVersionLineage                                                              | Linaje de la versión                                                    |
|                | GET `/versions/{id}/export.csv`                                                       | exportVersionCsv                                                               | CSV estándar o Excel regional                                           |
|                | GET `/versions/{id}/original`                                                         | downloadOriginal                                                               | Original byte a byte                                                    |
|                | GET `/versions/{id}/progress`                                                         | getVersionProgress                                                             | Etapas y estado                                                         |
| Ejecuciones    | GET `/executions/{id}`, `/artifacts`, `/profile`, `/quality`                          | getExecution, listExecutionArtifacts, getExecutionProfile, getExecutionQuality | Estado y artefactos                                                     |
|                | GET `/versions/{id}/executions`, `/representations`                                   | listVersionExecutions, listVersionRepresentations                              | Ejecuciones y representaciones                                          |
| Analítica      | GET `/executions/{id}/analysis`, `/analysis.csv`, `/evidence/{evidence_id}`           | getExecutionAnalysis, exportAnalysisCsv, getEvidence                           | Resultado y evidencia de cada cifra                                     |
|                | GET `/versions/{id}/automatic-analysis` (+ `/evidence/{evidence_id}`)                 | getAutomaticAnalysis, getAutomaticEvidence                                     | Hallazgos automáticos                                                   |
| Dataset        | GET `/versions/{id}/inspection`                                                       | getInspection                                                                  | Inspección completa                                                     |
|                | POST `/versions/{id}/dictionary`                                                      | annotateColumn                                                                 | Corregir el diccionario                                                 |
| Comprensión    | GET `/versions/{id}/comprehension`                                                    | getComprehension                                                               | Comprensión del negocio                                                 |
|                | POST `…/comprehension/feedback`, `…/meanings`, `…/target`                             | judgeRelationship, describeColumn, chooseTarget                                | Validar relaciones, significados, objetivo                              |
| Investigación  | GET `/versions/{id}/exploration`, `/exploration/history`                              | getExploration, getInvestigationHistory                                        | Plan, árbol, resultados, historial                                      |
|                | POST `/versions/{id}/exploration/control`                                             | controlInvestigation                                                           | Pausar, reanudar, cancelar, volver a investigar                         |
|                | GET `/versions/{id}/investigation` (+ evidencia)                                      | getInvestigation, getInvestigationEvidence                                     | Seguimiento de hallazgos (v1)                                           |
| Dashboard      | GET `/versions/{id}/dashboard`                                                        | getDashboard                                                                   | Dashboard publicado (automático o personalizado)                        |
|                | POST `/versions/{id}/dashboard/filter`                                                | filterDashboard                                                                | Filtros al momento (no se guardan)                                      |
|                | POST `/versions/{id}/dashboard/custom`                                                | saveDashboardCustomization                                                     | Versión personalizada (`expected_revision`)                             |
|                | POST `/versions/{id}/dashboard/feedback`                                              | judgeFinding                                                                   | Marca «sí va / no va»                                                   |
| Informe        | GET `/versions/{id}/report`, `/report.pdf`                                            | getReport, downloadReport                                                      | Informe y PDF                                                           |
|                | GET, POST `/versions/{id}/report/review`                                              | getReportReview, reviewReportFinding                                           | Revisión de hallazgos                                                   |
|                | GET `/report/history`; POST `/report/versions`; GET `/report/versions/{execution_id}` | getReportHistory, generateReportVersion, getReportVersion                      | Versiones del informe                                                   |
| Explicación IA | GET `/versions/{id}/overview-audit` (+ evidencia)                                     | getOverviewAudit, getOverviewAuditEvidence                                     | Explicación automática (C2)                                             |
| Salud          | GET `/health/live`, `/health/ready`                                                   | liveness, readiness                                                            | Vida y disponibilidad (sin prefijo)                                     |

## B.3 Ejemplo: subir archivos relacionados

```http
POST /api/v1/projects/7f0c…/imports/related
Content-Type: application/json
Idempotency-Key: 3c1d0d0e-…
X-CSRF-Token: …
Origin: http://localhost:3002

{"files": [
  {"name": "estudiantes.csv", "content_base64": "ZXN0dWRpYW50ZV9pZCxjYXJyZXJh…"},
  {"name": "notas.csv", "content_base64": "bm90YV9pZCxlc3R1ZGlhbnRlX2lk…"}
]}
```

Respuesta `202 Accepted`: `VersionResponse` (`id`, `dataset_id`, `project_id`, `number`, `file_name`,
`sha256`, `byte_size`, `created_at`, `execution_id`) de la vista principal; el modelo de datos completo
(tablas, relaciones, vistas) se lee en `GET /versions/{id}` → `source_origin`.

## B.4 Códigos de error estables más relevantes

| Grupo                 | Códigos                                                                                                                                                                                                                              |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Identidad y seguridad | `UNAUTHENTICATED` (401), `INVALID_CREDENTIALS` (401), `RATE_LIMITED` (429), `CSRF_INVALID` (403), `ORIGIN_FORBIDDEN` (403), `REGISTRATION_DISABLED`                                                                                  |
| Cola y recursos       | `QUEUE_LIMIT` (409), `STORAGE_QUOTA`, `FILE_TOO_LARGE` (413), `IDEMPOTENCY_CONFLICT`, `REVISION_CONFLICT`, `PROCESSING_TIMEOUT`, `ATTEMPTS_EXHAUSTED`, `VALIDATION_ERROR`                                                            |
| CSV, Excel y PDF      | `CSV_ENCODING`, `CSV_MALFORMED`, `CSV_HEADERS`, `CSV_DUPLICATE_HEADERS`, `CSV_ROW_LIMIT`, `CSV_NO_ROWS`, `CSV_CONTENT_TYPE` (415), `XLSX_CONTENT_TYPE`, `PDF_MALFORMED`, `EMPTY_FILE`                                                |
| Archivos relacionados | `RELATED_INVALID`, `RELATED_FORMAT`, `RELATED_DUPLICATE_NAMES`, `RELATED_FILE_INVALID` (422), `RELATED_TOO_LARGE`, `RELATED_JOINED_TOO_LARGE` (413), `RELATED_CONTENT_TYPE` (415)                                                    |
| Bases de datos        | `POSTGRESQL_DISABLED` (503), `POSTGRESQL_HOST_NOT_ALLOWED`, `DATABASE_HOST_PRIVATE`, `DATABASE_HOST_UNKNOWN`, `DATABASE_TLS_UNVERIFIED`, `DATABASE_TOO_LARGE`, `DATABASE_RATE_LIMITED` (429), `DATABASE_CONNECTOR_UNAVAILABLE` (503) |
| IA                    | `AI_BUDGET_EXCEEDED`, `AI_BUDGET_WAITING`, `COPILOT_UNAVAILABLE`, `INVALID_EVIDENCE_REFERENCE`                                                                                                                                       |
| Pestañas              | `INSPECTION_NOT_READY`, `COMPREHENSION_NOT_READY`, `DASHBOARD_NOT_READY`, `DASHBOARD_FILTER_INVALID`, `REPORT_NOT_READY`, `INVESTIGATION_RUNNING`, `TARGET_INVALID`                                                                  |
| Proxy web             | `BODY_TOO_LARGE` (413)                                                                                                                                                                                                               |
