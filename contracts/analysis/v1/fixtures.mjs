import { canonical, digest, sha256 } from "./canonical.mjs";

const id = (n) => `00000000-0000-4000-8000-${n.toString(16).padStart(12, "0")}`;
const time = (clock) => `2026-10-27T${clock}Z`;
const owner = id(1),
  project = id(2),
  dataset = id(3),
  sourceVersion = id(4),
  derivedVersion = id(5);
const csv = "id,importe\n001,10.50\n002, \n001,10.50\n";
const blob = (n, content, media_type) => ({
  object_id: id(n),
  sha256: sha256(content),
  byte_size: Buffer.byteLength(content),
  media_type,
});
const source = blob(100, csv, "text/csv");
// Estos dos blobs son referencias simbólicas de fixtures, NO archivos Parquet ejecutables.
const originalTable = blob(
  101,
  "fixture:source-parquet",
  "application/vnd.apache.parquet",
);
const cleanTable = blob(
  102,
  "fixture:trimmed-parquet",
  "application/vnd.apache.parquet",
);
const columns = ["id", "importe"].map((name, ordinal) => ({
  id: id(80 + ordinal),
  name,
  ordinal,
  technical_type: "string",
  type_parameters: {},
  nullable: true,
}));
const inputRows = [
  ["001", "10.50"],
  ["002", " "],
  ["001", "10.50"],
];
const outputRows = [
  ["001", "10.50"],
  ["002", null],
  ["001", "10.50"],
];
const tableRef = (version, content, artifact, representation) => ({
  version_id: version,
  version_content_sha256: content.sha256,
  artifact_id: id(artifact),
  artifact_sha256: representation.sha256,
});
const input = tableRef(sourceVersion, source, 6, originalTable);
const output = tableRef(derivedVersion, cleanTable, 11, cleanTable);
const reference = (revision) => ({
  id: revision.id,
  revision: revision.revision,
  content_sha256: revision.content_sha256,
});
const revision = (n, family, number, previous, content, domain, clock) => ({
  schema_version: 1,
  id: id(n),
  family_id: id(family),
  revision: number,
  previous_revision_id: previous === null ? null : id(previous),
  content,
  content_sha256: digest(domain, content),
  created_by: owner,
  created_at: time(clock),
});
const pending = () => ({
  state: "pending",
  origin: "heuristic",
  actor_id: null,
  reviewed_at: null,
});
const confirmed = () => ({
  state: "confirmed",
  origin: "user",
  actor_id: owner,
  reviewed_at: time("09:02:00"),
});
const config = {
  operation_catalog: "analysis-v1",
  rule_catalog: "csv-quality-v1",
  max_rows: 100000,
  max_columns: 128,
  max_field_chars: 10000,
  max_attempts: 3,
  timeout_seconds: 45,
  lease_seconds: 120,
  decimal_precision: 50,
  rounding: "HALF_EVEN",
  order: "preserve_input",
};
const environment = {
  engine_version: "analysis-design-1",
  source_sha256: sha256("fixture:engine-source"),
  python_version: "3.12.5",
  polars_version: "1.44.2",
  dependency_lock_sha256: sha256("fixture:dependency-lock"),
  platform: "fixture-linux-x86_64",
  image_digest: null,
  config_sha256: digest("config", config),
};
const environmentHash = digest("environment", environment);
const step = (name, operation, parameters, from = null) => ({
  id: name,
  operation,
  version: 1,
  input: from
    ? { kind: "step", step_id: from }
    : { kind: "input", alias: "source" },
  parameters,
});
const profile = (name) =>
  step(
    name,
    "understanding.profile",
    { algorithm: "column-profile-v1" },
    name === "profile_ingest" ? "read" : "trim",
  );
const quality = (name, from = null) =>
  step(
    name,
    "quality.evaluate",
    {
      rule_set: "csv-quality-v1",
      rules: ["Q-001", "Q-002", "Q-003"],
      score: "cell_completeness_v1",
    },
    from,
  );
const version = (
  n,
  number,
  kind,
  content,
  parent,
  produced,
  lineage,
  clock,
) => ({
  schema_version: 1,
  id: id(n),
  dataset_id: dataset,
  number,
  kind,
  content,
  original_filename: kind === "imported" ? "contract_fixture.csv" : null,
  parent_table_ref: parent,
  produced_by_execution_id: produced,
  row_lineage_artifact_id: lineage,
  created_at: time(clock),
});

export function buildExamples() {
  const semanticContent = {
    table_ref: input,
    row_grain: { description: null, review: pending() },
    columns: columns.map((column) => ({
      ...column,
      suggested_type: "string",
      role: "unknown",
      unit: null,
      currency: null,
      parse_format: null,
      null_policy: { mode: "preserve", tokens: [] },
      review: pending(),
    })),
    key: { column_ids: [], null_policy: "reject", review: pending() },
  };
  const semantics1 = revision(
    41,
    40,
    1,
    null,
    semanticContent,
    "semantic",
    "09:01:00",
  );
  const confirmedContent = structuredClone(semanticContent);
  confirmedContent.row_grain = {
    description:
      "Una operación de venta (contexto confirmado sólo para este ejemplo).",
    review: confirmed(),
  };
  confirmedContent.columns[0] = {
    ...confirmedContent.columns[0],
    role: "identifier",
    review: confirmed(),
  };
  confirmedContent.columns[1] = {
    ...confirmedContent.columns[1],
    role: "measure",
    unit: "EUR",
    currency: "EUR",
    review: confirmed(),
  };
  const semantics2 = revision(
    42,
    40,
    2,
    41,
    confirmedContent,
    "semantic",
    "09:02:00",
  );
  const ingest = revision(
    20,
    30,
    1,
    null,
    {
      objective: null,
      input: {
        kind: "source",
        alias: "source",
        version_id: sourceVersion,
        version_content_sha256: source.sha256,
      },
      semantic_ref: null,
      steps: [
        step("read", "ingestion.read_csv", {
          requested_separator: "auto",
          separator: ",",
          encoding: "utf-8-sig",
          strict: true,
          empty_cells: "null",
          blank_lines: "skip",
        }),
        profile("profile_ingest"),
        quality("quality_ingest", "read"),
      ],
      config,
    },
    "plan",
    "09:00:01",
  );
  const readonly = revision(
    21,
    31,
    1,
    null,
    {
      objective: null,
      input: { kind: "table", alias: "source", ...input },
      semantic_ref: reference(semantics2),
      steps: [quality("quality_again")],
      config,
    },
    "plan",
    "09:03:00",
  );
  const cleaning = revision(
    22,
    32,
    1,
    null,
    {
      objective: null,
      input: { kind: "table", alias: "source", ...input },
      semantic_ref: reference(semantics2),
      steps: [
        step("trim", "cleaning.trim_whitespace", {
          column_ids: [id(81)],
          whitespace: " \t\r\n",
          empty_result: "null",
          nulls: "preserve",
        }),
        profile("profile_clean"),
        quality("quality_clean", "trim"),
      ],
      config,
    },
    "plan",
    "09:04:00",
  );
  const mapping = inputRows.map((_, index) => ({
    output_record_number: index + 1,
    input_record_number: index + 1,
  }));
  const effect = {
    plan_ref: reference(cleaning),
    input_ref: input,
    semantic_ref: reference(semantics2),
    config_sha256: digest("config", config),
    environment_sha256: environmentHash,
    output_columns: columns,
    output_logical_sha256: digest("table", { columns, rows: outputRows }),
    row_lineage_sha256: digest("row_lineage", {
      input_ref: input,
      rows: mapping,
    }),
    input_rows: 3,
    output_rows: 3,
    excluded_rows: 0,
    changed_rows: 1,
    changed_cells: 1,
    created_nulls: 1,
    conversion_errors: 0,
  };
  const approval = {
    schema_version: 1,
    id: id(70),
    project_id: project,
    approved_by: owner,
    plan_ref: reference(cleaning),
    input_ref: input,
    semantic_ref: reference(semantics2),
    preview_artifact_id: id(10),
    effect_sha256: digest("effect", effect),
    effective_config_sha256: digest("config", config),
    environment_sha256: environmentHash,
    granted_at: time("09:06:00"),
    expires_at: null,
  };
  const execution = (n, plan, mode, approvalId, versions, clock, finish) => ({
    schema_version: 1,
    id: id(n),
    project_id: project,
    requested_by: owner,
    plan_ref: reference(plan),
    mode,
    state: "succeeded",
    idempotency_key: id(200 + n),
    effective_config: config,
    required_environment_sha256:
      mode === "apply" && approvalId ? environmentHash : null,
    reproducibility: "complete",
    approval_id: approvalId,
    output_version_ids: versions,
    active_attempt_id: null,
    legacy: null,
    created_at: time(clock),
    finished_at: time(finish),
  });
  const executions = [
    execution(50, ingest, "apply", null, [], "09:00:02", "09:00:04"),
    execution(51, readonly, "apply", null, [], "09:03:01", "09:03:03"),
    execution(52, cleaning, "preview", null, [], "09:05:00", "09:05:02"),
    execution(
      53,
      cleaning,
      "apply",
      id(70),
      [derivedVersion],
      "09:07:00",
      "09:07:04",
    ),
  ];
  const attempt = (n, run, number, state, start, end) => ({
    schema_version: 1,
    id: id(n),
    execution_id: id(run),
    number,
    state,
    lease_until: null,
    fencing_token: id(300 + n),
    environment,
    environment_sha256: environmentHash,
    started_at: time(start),
    finished_at: time(end),
    error:
      state === "failed"
        ? {
            code: "STORAGE_UNAVAILABLE",
            message:
              "Fallo transitorio sintético; no se publicaron salidas del intento.",
          }
        : null,
  });
  const attempts = [
    attempt(60, 50, 1, "succeeded", "09:00:03", "09:00:04"),
    attempt(61, 51, 1, "succeeded", "09:03:02", "09:03:03"),
    attempt(62, 52, 1, "succeeded", "09:05:01", "09:05:02"),
    attempt(63, 53, 1, "failed", "09:07:01", "09:07:02"),
    attempt(64, 53, 2, "succeeded", "09:07:03", "09:07:04"),
  ];
  const metrics = {
    missing_cells: 0,
    duplicate_rows: 1,
    whitespace_cells: 1,
    completeness_percent: "100.00",
  };
  const payloads = [
    { artifact_id: id(6), kind: "table", rows: inputRows },
    { artifact_id: id(8), kind: "quality", metrics },
    { artifact_id: id(9), kind: "quality", metrics },
    { artifact_id: id(10), kind: "cleaning_preview", effect },
    { artifact_id: id(11), kind: "table", rows: outputRows },
    {
      artifact_id: id(13),
      kind: "quality",
      metrics: {
        missing_cells: 1,
        duplicate_rows: 1,
        whitespace_cells: 0,
        completeness_percent: "83.33",
      },
    },
    {
      artifact_id: id(14),
      kind: "row_lineage",
      input_ref: input,
      rows: mapping,
    },
  ];
  const artifact = (
    n,
    run,
    attemptId,
    stepId,
    slot,
    kind,
    targetVersion,
    content = null,
  ) => {
    const payload = payloads.find((item) => item.artifact_id === id(n));
    const tabular = kind === "table" || kind === "cleaning_preview";
    return {
      schema_version: 1,
      id: id(n),
      project_id: project,
      execution_id: id(run),
      attempt_id: id(attemptId),
      step_id: stepId,
      slot,
      kind,
      version_id: targetVersion,
      content:
        content ??
        blob(
          100 + n,
          canonical(payload ?? { fixture: "profile" }),
          "application/json",
        ),
      row_count: 3,
      columns: tabular ? columns : null,
      logical_content_sha256:
        kind === "table"
          ? digest("table", { columns, rows: payload.rows })
          : kind === "cleaning_preview"
            ? effect.output_logical_sha256
            : null,
    };
  };
  const artifacts = [
    artifact(6, 50, 60, "read", "table", "table", sourceVersion, originalTable),
    artifact(7, 50, 60, "profile_ingest", "profile", "profile", sourceVersion),
    artifact(8, 50, 60, "quality_ingest", "quality", "quality", sourceVersion),
    artifact(9, 51, 61, "quality_again", "quality", "quality", sourceVersion),
    artifact(10, 52, 62, "trim", "preview", "cleaning_preview", null),
    artifact(11, 53, 64, "trim", "table", "table", derivedVersion, cleanTable),
    artifact(12, 53, 64, "profile_clean", "profile", "profile", derivedVersion),
    artifact(13, 53, 64, "quality_clean", "quality", "quality", derivedVersion),
    artifact(14, 53, 64, "trim", "lineage", "row_lineage", derivedVersion),
  ];
  return structuredClone({
    schema_version: 1,
    description:
      "Corpus sintético de diseño, no una respuesta de API ni archivos Parquet reales. Muestra objetivo opcional, dos análisis sobre una versión, preview/aprobación y limpieza con reintento sin doble publicación.",
    dataset: {
      schema_version: 1,
      id: dataset,
      project_id: project,
      owner_id: owner,
      name: "Ejemplo de contratos",
      revision: 2,
      default_table_ref: output,
      created_at: time("09:00:00"),
    },
    versions: [
      version(4, 1, "imported", source, null, null, null, "09:00:00"),
      version(5, 2, "derived", cleanTable, input, id(53), id(14), "09:07:04"),
    ],
    semantic_contracts: [semantics1, semantics2],
    plans: [ingest, readonly, cleaning],
    executions,
    attempts,
    artifacts,
    approvals: [approval],
    revocations: [],
    evidence: [
      {
        schema_version: 1,
        id: id(71),
        project_id: project,
        artifact_id: id(13),
        artifact_sha256: artifacts.find((a) => a.id === id(13)).content.sha256,
        selector: { kind: "metric", key: "missing_cells" },
        expected_value: "1",
        unit: "cells",
        created_at: time("09:08:00"),
      },
    ],
    artifact_payloads: payloads,
    source_fixtures: [{ version_id: sourceVersion, utf8: csv }],
  });
}
