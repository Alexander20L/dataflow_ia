# Anexo C — Diccionario de datos y esquema de base de datos

PostgreSQL 17. **30 migraciones** Alembic (`apps/api/migrations/versions/0001_…` a
`0030_database_copies.py`), **57 tablas** de aplicación más `alembic_version` (comprobado contra la base y
contra `Base.metadata`). Las migraciones son aditivas salvo 0019 (ADR-026, retiro explícito del pipeline
por políticas); 22 de ellas (0003–0012 y 0018–0029) tienen su prueba `tests/test_migration_NNNN.py` (ida y vuelta, `compare_metadata`,
inmutabilidad y bloqueo del _downgrade_ con datos nuevos).

Convención: `*` clave primaria, `→` clave foránea. Casi todas las tablas de negocio llevan `owner_id →
identity_users`, `project_id → projects` y `version_id → dataset_version_records`.

## C.1 Identidad, proyectos y auditoría

| Tabla                 | Columnas principales                                                                                   | Notas                                     |
| --------------------- | ------------------------------------------------------------------------------------------------------ | ----------------------------------------- |
| `identity_users`      | id*, email, name, password_hash                                                                        | Argon2id                                  |
| `identity_sessions`   | token_hash*, user_id → identity_users, csrf_token, expires_at                                          | Sólo el SHA-256 del token                 |
| `identity_attempts`   | id*, email_key, ip_key, created_at                                                                     | Claves SHA-256 para el límite de intentos |
| `projects`            | id*, owner_id → identity_users, name, description, file_name, status, revision, created_at, updated_at | Revisión optimista                        |
| `audit_events`        | id*, actor_id, entity_id, action, correlation_id, created_at                                           |                                           |
| `runtime_transitions` | id*, state, verified_at, manifest                                                                      | Corte de versión del runtime              |

## C.2 Datasets, versiones y objetos

| Tabla                                                         | Columnas principales                                                                                 | Notas                             |
| ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | --------------------------------- |
| `datasets`                                                    | id*, project_id → projects, owner_id → identity_users                                                |                                   |
| `dataset_objects`                                             | id*, owner_id, object_key, sha256, byte_size, media_type                                             | Inmutable                         |
| `dataset_version_records`                                     | id*, dataset_id → datasets, number, kind, file_name, content_object_id → dataset_objects, created_at | Inmutable                         |
| `dataset_version_lineage`                                     | version_id* → dataset_version_records, parent_version_id, producer_execution_id → execution_runs     | Inmutable; linaje de derivadas    |
| `dataset_import_bindings`                                     | version_id*, execution_id, table/diagnostic/profile/quality_artifact_id → execution_artifacts        | Deuda de nombre (ADR-015)         |
| `dataset_defaults`                                            | dataset_id*, version_id, table_artifact_id, revision                                                 |                                   |
| `dataset_versions`, `import_executions`, `analysis_artifacts` | —                                                                                                    | Históricas, valla de sólo lectura |

## C.3 Ejecuciones (cola) y planes

| Tabla                                              | Columnas principales                                                                                                                                                                                                                                                                                | Notas                              |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| `execution_runs`                                   | id*, version_id, project_id, owner_id, plan_id, kind, request_key, request_fingerprint, input_artifact_id, input_artifact_sha256, state, attempt_count, active_attempt_id, row_count, column_count, error_code, error_message, reproducibility, correlation_id, created_at, updated_at, finished_at | La cola: `state = queued`          |
| `execution_attempts`                               | id*, execution_id → execution_runs, number, state, fencing_token, lease_until, environment, environment_sha256, started_at, finished_at, error_code, error_message                                                                                                                                  | _Lease_ 120 s, máx. 3              |
| `execution_artifacts`                              | id*, version_id, execution_id, attempt_id, step_id, slot, kind, object_id → dataset_objects, row_count, column_count, column_schema, logical_content_sha256                                                                                                                                         | Inmutable                          |
| `execution_error_details`                          | attempt_id*, execution_id, code, details, created_at                                                                                                                                                                                                                                                | Inmutable                          |
| `execution_plan_revisions`                         | id*, family_id, revision, content, content_sha256, created_by, created_at                                                                                                                                                                                                                           | Inmutable; incluye `source_origin` |
| `execution_plan_bindings`                          | plan_revision_id*, project_id, input_artifact_id, input_artifact_sha256, semantic_revision_id                                                                                                                                                                                                       | Inmutable                          |
| `planning_create_requests`, `planning_validations` | —                                                                                                                                                                                                                                                                                                   | Inmutables                         |

Valores de `kind`: `csv_import`, `table_analysis`, `plan`, `cleaning_preview`, `cleaning_apply`,
`report_render`, `overview_audit`, `investigation`, `automatic_report`, `comprehension`, `exploration`,
`dashboard`, `inspection`, `null_cleaning`. Estados: `queued`, `running`, `succeeded`, `failed`,
`cancelled` (y el intento `deferred` por presupuesto de IA).

## C.4 Decisiones del usuario sobre el recorrido automático (Fases 19–33)

| Tabla (migración)                  | Columnas principales                                                                                                                                                                                           |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `comprehension_feedback` (0020)    | id*, owner_id, project_id, version_id, source_key, relationship_key, verdict, created_at                                                                                                                       |
| `finding_feedback` (0021)          | id*, owner_id, project_id, version_id, item_key, verdict, created_at                                                                                                                                           |
| `column_annotations` (0022)        | id*, owner_id, project_id, version_id, source_key, column_name, role, nature, time_format, notes, confirmed, created_at                                                                                        |
| `column_annotation_details` (0023) | annotation_id* → column_annotations, null_tokens, personal                                                                                                                                                     |
| `column_meanings` (0024)           | id*, owner_id, project_id, version_id, source_key, column_name, meaning, confirmed, created_at                                                                                                                 |
| `column_meaning_marks` (0025)      | meaning_id* → column_meanings, unknown                                                                                                                                                                         |
| `investigation_controls` (0026)    | id*, owner_id, execution_id → execution_runs, action, created_at                                                                                                                                               |
| `dashboard_customizations` (0027)  | id*, owner_id, project_id, version_id, dashboard_execution_id → execution_runs, revision, layout, layout_sha256, created_at                                                                                    |
| `analysis_targets` (0028)          | id*, owner_id, project_id, version_id, source_key, column_name, value, created_at                                                                                                                              |
| `database_attempts` (0029)         | id*, user_key, client_key, target_key, succeeded, created_at (huellas SHA-256)                                                                                                                                 |
| `database_copies` (0030)           | id*, owner_id, project_id, engine, kind, state, server, database_name, schema_name, tables, omitted, version_id, model, error_code, error_message, created_at, heartbeat_at, finished_at (nunca la contraseña) |

Todas son inmutables (una corrección es un registro nuevo) salvo `database_attempts` y `database_copies`.

## C.5 IA

| Tabla                                                                                                          | Columnas principales                                                                                                                                                                                                                                            |
| -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `copilot_ai_calls`                                                                                             | id*, owner_id, project_id, conversation_id, task, provider, model, parameters, prompt_id, prompt_version, context_sha256, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd, latency_ms, outcome, validation, error_code, created_at |
| `copilot_conversations`, `copilot_messages`, `copilot_requests`, `copilot_action_links`, `copilot_text_audits` | Históricas de la Fase 10 (inmutables)                                                                                                                                                                                                                           |

## C.6 Históricas de las Fases 3–10 (conservadas, ADR-034)

`semantic_families/revisions/save_requests`, `cleaning_approvals` (incluye `effect_sha256`),
`quality_ruleset_*`, `analytics_metric_*`, `dashboard_*`, `report_*` (familias, revisiones, solicitudes y
renders). Se conservan como archivo de sólo lectura.

## C.7 Inmutabilidad

- **35 tablas** con el trigger `immutable_record` → función `dataflow_immutable_record()` (creada en
  0003): impide `UPDATE` y `DELETE`.
- `legacy_read_only` → `dataflow_legacy_fence()` en `analysis_artifacts`, `dataset_versions` e
  `import_executions`; `approval_guard` en `cleaning_approvals`; `semantic_binding` en
  `semantic_families`.

## C.8 Almacenamiento de objetos

Volumen `objects_data` (local: `DATAFLOW_STORAGE_PATH`): originales byte a byte, tablas canónicas en
Parquet (con metadatos `dataflow:source_reading`) y artefactos JSON. La base guarda referencias con
SHA-256 y hash lógico del contenido (`platform/tabular.py`).
