/** Fuente del esquema de DISEÑO; no se importa desde apps/web ni apps/api. */
const str = (minLength = 1, maxLength = 500) => ({
  type: "string",
  minLength,
  maxLength,
});
const integer = (minimum = 0, maximum = Number.MAX_SAFE_INTEGER) => ({
  type: "integer",
  minimum,
  maximum,
});
const enumeration = (...values) => ({ type: "string", enum: values });
const literal = (value) => ({ type: typeof value, const: value });
const nullable = (value) => ({ anyOf: [value, { type: "null" }] });
const array = (items, minItems = 0, maxItems = 10000) => ({
  type: "array",
  items,
  minItems,
  maxItems,
});
const object = (properties, required = Object.keys(properties)) => ({
  type: "object",
  properties,
  required,
  additionalProperties: false,
});
const ref = (name) => ({ $ref: `#/$defs/${name}` });
const uuid = { type: "string", format: "uuid", pattern: "^[0-9a-f-]+$" };
const hash = { type: "string", pattern: "^[0-9a-f]{64}$" };
const timestamp = { type: "string", format: "date-time", pattern: "Z$" };
const idList = { ...array(uuid, 0, 128), uniqueItems: true };
const columnList = { ...idList, minItems: 1 };
const decimal = { type: "string", pattern: "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$" };

const BlobRef = object({
  object_id: uuid,
  sha256: hash,
  byte_size: integer(),
  media_type: str(),
});
const TableRef = object({
  version_id: uuid,
  version_content_sha256: hash,
  artifact_id: uuid,
  artifact_sha256: hash,
});
const RevisionRef = object({
  id: uuid,
  revision: integer(1),
  content_sha256: hash,
});
const InputRef = {
  oneOf: [
    object({
      kind: literal("source"),
      alias: literal("source"),
      version_id: uuid,
      version_content_sha256: hash,
    }),
    object({
      kind: literal("table"),
      alias: literal("source"),
      ...TableRef.properties,
    }),
  ],
};
const StepInput = {
  oneOf: [
    object({ kind: literal("input"), alias: literal("source") }),
    object({ kind: literal("step"), step_id: str(1, 80) }),
  ],
};
const Column = object({
  id: uuid,
  name: str(1, 200),
  ordinal: integer(0, 127),
  technical_type: enumeration(
    "string",
    "integer",
    "decimal",
    "date",
    "boolean",
  ),
  type_parameters: object(
    { precision: integer(1, 50), scale: integer(0, 12) },
    [],
  ),
  nullable: { type: "boolean" },
});
const Review = object({
  state: enumeration("pending", "confirmed", "rejected"),
  origin: enumeration("heuristic", "user", "ai", "migration"),
  actor_id: nullable(uuid),
  reviewed_at: nullable(timestamp),
});
const SemanticColumn = object({
  ...Column.properties,
  suggested_type: nullable(
    enumeration("string", "integer", "decimal", "date", "boolean"),
  ),
  role: enumeration(
    "unknown",
    "identifier",
    "dimension",
    "measure",
    "business_date",
  ),
  unit: nullable(str(1, 80)),
  currency: nullable({ type: "string", pattern: "^[A-Z]{3}$" }),
  parse_format: nullable(str(1, 100)),
  null_policy: object({
    mode: enumeration("preserve", "empty_is_null", "explicit_tokens"),
    tokens: { ...array(str(0, 100), 0, 20), uniqueItems: true },
  }),
  review: Review,
});
const Config = object({
  operation_catalog: literal("analysis-v1"),
  rule_catalog: literal("csv-quality-v1"),
  max_rows: integer(1, 100000),
  max_columns: integer(1, 128),
  max_field_chars: integer(1, 10000),
  max_attempts: integer(1, 3),
  timeout_seconds: integer(5, 60),
  lease_seconds: integer(120, 300),
  decimal_precision: literal(50),
  rounding: literal("HALF_EVEN"),
  order: literal("preserve_input"),
});
// Campos semánticos aditivos de Fase 3; no se exigen al corpus de diseño anterior.
SemanticColumn.properties.description = nullable(str(1, 1000));
SemanticColumn.properties.interpretation_type = nullable(
  enumeration("string", "integer", "decimal", "date", "boolean"),
);

const operations = {
  "ingestion.read_csv": object({
    requested_separator: enumeration("auto", ",", ";", "\t"),
    separator: enumeration(",", ";", "\t"),
    encoding: literal("utf-8-sig"),
    strict: literal(true),
    empty_cells: literal("null"),
    blank_lines: literal("skip"),
  }),
  "understanding.profile": object({ algorithm: literal("column-profile-v1") }),
  "quality.evaluate": object({
    rule_set: literal("csv-quality-v1"),
    rules: {
      ...array(enumeration("Q-001", "Q-002", "Q-003"), 3, 3),
      uniqueItems: true,
    },
    score: literal("cell_completeness_v1"),
  }),
  "cleaning.trim_whitespace": object({
    column_ids: columnList,
    whitespace: literal(" \t\r\n"),
    empty_result: literal("null"),
    nulls: literal("preserve"),
  }),
  "cleaning.filter_rows": object({
    column_id: uuid,
    predicate: enumeration("is_null", "is_whitespace_only"),
    action: literal("exclude"),
  }),
  "cleaning.deduplicate": object({
    column_ids: columnList,
    keep: literal("first"),
    null_keys: enumeration("reject", "group_nulls"),
  }),
  "cleaning.cast": object({
    column_id: uuid,
    target_type: enumeration("integer", "decimal", "date", "boolean"),
    format: enumeration(
      "integer_ascii",
      "decimal_dot",
      "iso_date",
      "boolean_lowercase",
    ),
    decimal_scale: nullable(integer(0, 12)),
    rounding: literal("HALF_EVEN"),
    nulls: literal("preserve"),
    on_error: literal("fail"),
  }),
};
const Step = {
  oneOf: Object.entries(operations).map(([key, parameters]) =>
    object({
      id: str(1, 80),
      operation: literal(key),
      version: literal(1),
      input: StepInput,
      parameters,
    }),
  ),
};
const PlanContent = object({
  objective: nullable(str(1, 2000)),
  input: InputRef,
  semantic_ref: nullable(RevisionRef),
  steps: array(Step, 1, 16),
  config: Config,
});
const SemanticContent = object({
  table_ref: TableRef,
  row_grain: object({ description: nullable(str(1, 500)), review: Review }),
  columns: array(SemanticColumn, 1, 128),
  key: object({
    column_ids: idList,
    null_policy: enumeration("reject", "group_nulls"),
    review: Review,
  }),
});
const revision = (content) =>
  object({
    schema_version: literal(1),
    id: uuid,
    family_id: uuid,
    revision: integer(1),
    previous_revision_id: nullable(uuid),
    content,
    content_sha256: hash,
    created_by: uuid,
    created_at: timestamp,
  });
SemanticContent.properties.dataset_description = nullable(str(1, 2000));
SemanticContent.properties.suggestion_rules_version = str(1, 80);
const Environment = object({
  engine_version: str(1, 80),
  source_sha256: hash,
  python_version: str(1, 80),
  polars_version: str(1, 80),
  dependency_lock_sha256: hash,
  platform: str(1, 120),
  image_digest: nullable(hash),
  config_sha256: hash,
});
const Effect = object({
  plan_ref: RevisionRef,
  input_ref: TableRef,
  semantic_ref: RevisionRef,
  config_sha256: hash,
  environment_sha256: hash,
  output_columns: array(Column, 1, 128),
  output_logical_sha256: hash,
  row_lineage_sha256: hash,
  input_rows: integer(),
  output_rows: integer(),
  excluded_rows: integer(),
  changed_rows: integer(),
  changed_cells: integer(),
  created_nulls: integer(),
  conversion_errors: integer(),
});
const Mapping = object({
  output_record_number: integer(1),
  input_record_number: integer(1),
});

export const schema = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  $id: "https://dataflow.local/contracts/analysis/v1",
  title: "DataFlow analysis contracts — design v1 (not implemented HTTP)",
  $comment:
    "El contenedor Scenario sólo sirve al corpus de diseño; los $defs son contratos individuales. Las invariantes entre entidades se describen en docs y se comprueban parcialmente en verify.mjs.",
  ...object({
    schema_version: literal(1),
    description: str(1, 1000),
    dataset: ref("Dataset"),
    versions: array(ref("DatasetVersion"), 1),
    semantic_contracts: array(ref("SemanticContract")),
    plans: array(ref("AnalysisPlan"), 1),
    executions: array(ref("AnalysisExecution"), 1),
    attempts: array(ref("ExecutionAttempt")),
    artifacts: array(ref("AnalysisArtifact")),
    approvals: array(ref("Approval")),
    revocations: array(ref("ApprovalRevocation")),
    evidence: array(ref("EvidenceReference")),
    artifact_payloads: array(ref("FixturePayload")),
    source_fixtures: array(object({ version_id: uuid, utf8: str(1, 10000) })),
  }),
  $defs: {
    BlobRef,
    TableRef,
    RevisionRef,
    InputRef,
    Config,
    Environment,
    Effect,
    Column,
    Dataset: object({
      schema_version: literal(1),
      id: uuid,
      project_id: uuid,
      owner_id: uuid,
      name: str(1, 80),
      revision: integer(1),
      default_table_ref: nullable(TableRef),
      created_at: timestamp,
    }),
    DatasetVersion: object({
      schema_version: literal(1),
      id: uuid,
      dataset_id: uuid,
      number: integer(1),
      kind: enumeration("imported", "derived"),
      content: BlobRef,
      original_filename: nullable(str(1, 255)),
      parent_table_ref: nullable(TableRef),
      produced_by_execution_id: nullable(uuid),
      row_lineage_artifact_id: nullable(uuid),
      created_at: timestamp,
    }),
    SemanticContract: revision(SemanticContent),
    AnalysisPlan: revision(PlanContent),
    AnalysisExecution: object({
      schema_version: literal(1),
      id: uuid,
      project_id: uuid,
      requested_by: uuid,
      plan_ref: nullable(RevisionRef),
      mode: enumeration("preview", "apply"),
      state: enumeration(
        "queued",
        "running",
        "succeeded",
        "failed",
        "cancelled",
      ),
      idempotency_key: uuid,
      effective_config: nullable(Config),
      required_environment_sha256: nullable(hash),
      reproducibility: enumeration("complete", "legacy_partial"),
      approval_id: nullable(uuid),
      output_version_ids: { ...array(uuid, 0, 1), uniqueItems: true },
      active_attempt_id: nullable(uuid),
      legacy: nullable(
        object({
          source_table: literal("import_executions"),
          source_id: uuid,
          historical_attempt_count: integer(),
        }),
      ),
      created_at: timestamp,
      finished_at: nullable(timestamp),
    }),
    ExecutionAttempt: object({
      schema_version: literal(1),
      id: uuid,
      execution_id: uuid,
      number: integer(1),
      state: enumeration(
        "running",
        "succeeded",
        "failed",
        "expired",
        "cancelled",
      ),
      lease_until: nullable(timestamp),
      fencing_token: uuid,
      environment: Environment,
      environment_sha256: hash,
      started_at: timestamp,
      finished_at: nullable(timestamp),
      error: nullable(object({ code: str(1, 80), message: str(1, 300) })),
    }),
    AnalysisArtifact: object({
      schema_version: literal(1),
      id: uuid,
      project_id: uuid,
      execution_id: uuid,
      attempt_id: nullable(uuid),
      step_id: str(1, 80),
      slot: str(1, 80),
      kind: enumeration(
        "table",
        "profile",
        "quality",
        "cleaning_preview",
        "row_lineage",
        "legacy_diagnostic",
      ),
      version_id: nullable(uuid),
      content: BlobRef,
      row_count: nullable(integer()),
      columns: nullable(array(Column, 1, 128)),
      logical_content_sha256: nullable(hash),
    }),
    Approval: object({
      schema_version: literal(1),
      id: uuid,
      project_id: uuid,
      approved_by: uuid,
      plan_ref: RevisionRef,
      input_ref: TableRef,
      semantic_ref: RevisionRef,
      preview_artifact_id: uuid,
      effect_sha256: hash,
      effective_config_sha256: hash,
      environment_sha256: hash,
      granted_at: timestamp,
      expires_at: nullable(timestamp),
    }),
    ApprovalRevocation: object({
      schema_version: literal(1),
      id: uuid,
      project_id: uuid,
      approval_id: uuid,
      revoked_by: uuid,
      revoked_at: timestamp,
      reason: str(1, 300),
    }),
    EvidenceReference: object({
      schema_version: literal(1),
      id: uuid,
      project_id: uuid,
      artifact_id: uuid,
      artifact_sha256: hash,
      selector: {
        oneOf: [
          object({
            kind: literal("metric"),
            key: enumeration(
              "missing_cells",
              "duplicate_rows",
              "whitespace_cells",
              "completeness_percent",
            ),
          }),
          object({
            kind: literal("issue"),
            issue_id: str(),
            rule: enumeration("Q-001", "Q-002", "Q-003"),
          }),
          object({
            kind: literal("row"),
            record_number: integer(1),
            column_id: uuid,
          }),
        ],
      },
      expected_value: nullable(decimal),
      unit: nullable(str(1, 80)),
      created_at: timestamp,
    }),
    FixturePayload: {
      oneOf: [
        object({
          artifact_id: uuid,
          kind: literal("table"),
          rows: array(
            array(
              {
                anyOf: [
                  { type: "string" },
                  { type: "boolean" },
                  { type: "null" },
                ],
              },
              1,
              128,
            ),
          ),
        }),
        object({
          artifact_id: uuid,
          kind: literal("quality"),
          metrics: object({
            missing_cells: integer(),
            duplicate_rows: integer(),
            whitespace_cells: integer(),
            completeness_percent: decimal,
          }),
        }),
        object({
          artifact_id: uuid,
          kind: literal("cleaning_preview"),
          effect: Effect,
        }),
        object({
          artifact_id: uuid,
          kind: literal("row_lineage"),
          input_ref: TableRef,
          rows: array(Mapping),
        }),
      ],
    },
  },
};
