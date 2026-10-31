import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import Ajv from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { canonical, digest, sha256 } from "./canonical.mjs";
import { buildExamples } from "./fixtures.mjs";
import { schema } from "./schema.mjs";

const ajv = new Ajv({ strict: true, allErrors: true });
addFormats(ajv);
const structurallyValid = ajv.compile(schema);
const requireCondition = (condition, code) => {
  if (!condition) throw new Error(code);
};
const same = (a, b) => canonical(a) === canonical(b);
const reference = (value) => ({
  id: value.id,
  revision: value.revision,
  content_sha256: value.content_sha256,
});
const transform = (plan) =>
  plan.content.steps.some((step) => step.operation.startsWith("cleaning."));

/** Verifica el corpus de diseño; no es el validador/autorizador del backend futuro. */
function validate(data) {
  requireCondition(
    structurallyValid(data),
    `SCHEMA: ${ajv.errorsText(structurallyValid.errors)}`,
  );
  const collections = [
    data.versions,
    data.semantic_contracts,
    data.plans,
    data.executions,
    data.attempts,
    data.artifacts,
    data.approvals,
    data.revocations,
    data.evidence,
  ];
  const ids = collections.flat().map((value) => value.id);
  requireCondition(new Set(ids).size === ids.length, "DUPLICATE_ENTITY_ID");
  const index = (entries) => new Map(entries.map((entry) => [entry.id, entry]));
  const versions = index(data.versions),
    artifacts = index(data.artifacts),
    semantics = index(data.semantic_contracts),
    plans = index(data.plans),
    runs = index(data.executions),
    attempts = index(data.attempts),
    approvals = index(data.approvals);
  const payloads = new Map(
    data.artifact_payloads.map((payload) => [payload.artifact_id, payload]),
  );
  requireCondition(
    payloads.size === data.artifact_payloads.length,
    "DUPLICATE_PAYLOAD",
  );
  const lookup = (map, id, code) => {
    const value = map.get(id);
    requireCondition(value, code);
    return value;
  };
  const table = (value) => {
    const version = lookup(
      versions,
      value.version_id,
      "VERSION_REFERENCE_MISSING",
    );
    const artifact = lookup(
      artifacts,
      value.artifact_id,
      "TABLE_REFERENCE_MISSING",
    );
    requireCondition(
      version.content.sha256 === value.version_content_sha256 &&
        artifact.content.sha256 === value.artifact_sha256,
      "TABLE_HASH_MISMATCH",
    );
    requireCondition(
      artifact.kind === "table" && artifact.version_id === version.id,
      "TABLE_SCOPE_MISMATCH",
    );
    requireCondition(
      lookup(runs, artifact.execution_id, "TABLE_RUN_MISSING").state ===
        "succeeded",
      "TABLE_NOT_PUBLISHED",
    );
    return artifact;
  };
  const revisionRef = (map, value) => {
    const target = lookup(map, value.id, "REVISION_REFERENCE_MISSING");
    requireCondition(
      same(reference(target), value),
      "REVISION_REFERENCE_MISMATCH",
    );
    return target;
  };
  const review = (value) => {
    if (value.state === "confirmed" || value.state === "rejected")
      requireCondition(
        value.origin === "user" &&
          value.actor_id === data.dataset.owner_id &&
          value.reviewed_at !== null,
        "HUMAN_REVIEW_REQUIRED",
      );
  };

  const numbers = new Set();
  for (const version of data.versions) {
    requireCondition(
      version.dataset_id === data.dataset.id && !numbers.has(version.number),
      "VERSION_NUMBER_OR_DATASET_MISMATCH",
    );
    numbers.add(version.number);
    if (version.kind === "imported") {
      requireCondition(
        version.parent_table_ref === null &&
          version.produced_by_execution_id === null &&
          version.row_lineage_artifact_id === null &&
          version.original_filename !== null,
        "IMPORTED_PROVENANCE_INVALID",
      );
    } else {
      requireCondition(
        version.parent_table_ref !== null &&
          version.produced_by_execution_id !== null &&
          version.row_lineage_artifact_id !== null &&
          version.original_filename === null,
        "DERIVED_PROVENANCE_REQUIRED",
      );
      table(version.parent_table_ref);
      requireCondition(
        version.parent_table_ref.version_id !== version.id,
        "VERSION_LINEAGE_CYCLE",
      );
      const run = lookup(
        runs,
        version.produced_by_execution_id,
        "PRODUCING_RUN_MISSING",
      );
      requireCondition(
        run.state === "succeeded" &&
          run.mode === "apply" &&
          run.output_version_ids.includes(version.id),
        "DERIVED_NOT_PUBLISHED",
      );
      const lineage = lookup(
        artifacts,
        version.row_lineage_artifact_id,
        "LINEAGE_REQUIRED",
      );
      requireCondition(
        lineage.kind === "row_lineage" &&
          lineage.version_id === version.id &&
          lineage.execution_id === run.id,
        "LINEAGE_SCOPE_MISMATCH",
      );
      const ancestors = new Set([version.id]);
      let parent = versions.get(version.parent_table_ref.version_id);
      while (parent) {
        requireCondition(!ancestors.has(parent.id), "VERSION_LINEAGE_CYCLE");
        ancestors.add(parent.id);
        parent = parent.parent_table_ref
          ? versions.get(parent.parent_table_ref.version_id)
          : null;
      }
    }
  }
  if (data.dataset.default_table_ref) table(data.dataset.default_table_ref);
  for (const source of data.source_fixtures) {
    const version = lookup(
      versions,
      source.version_id,
      "SOURCE_FIXTURE_MISSING",
    );
    requireCondition(
      version.content.sha256 === sha256(source.utf8) &&
        version.content.byte_size === Buffer.byteLength(source.utf8),
      "SOURCE_BYTES_MISMATCH",
    );
  }
  for (const [entries, domain] of [
    [data.semantic_contracts, "semantic"],
    [data.plans, "plan"],
  ]) {
    const revisions = new Set();
    for (const value of entries) {
      const key = `${value.family_id}:${value.revision}`;
      requireCondition(!revisions.has(key), "DUPLICATE_REVISION");
      revisions.add(key);
      requireCondition(
        value.content_sha256 === digest(domain, value.content),
        "REVISION_HASH_MISMATCH",
      );
      if (value.revision === 1)
        requireCondition(
          value.previous_revision_id === null,
          "REVISION_CHAIN_INVALID",
        );
      else {
        const previous = entries.find(
          (entry) => entry.id === value.previous_revision_id,
        );
        requireCondition(
          previous &&
            previous.family_id === value.family_id &&
            previous.revision + 1 === value.revision,
          "REVISION_CHAIN_INVALID",
        );
      }
    }
  }
  for (const contract of data.semantic_contracts) {
    const representation = table(contract.content.table_ref);
    const cols = contract.content.columns;
    requireCondition(
      new Set(cols.map((c) => c.id)).size === cols.length,
      "DUPLICATE_COLUMN_ID",
    );
    requireCondition(
      same(
        cols.map(
          ({
            id,
            name,
            ordinal,
            technical_type,
            type_parameters,
            nullable,
          }) => ({
            id,
            name,
            ordinal,
            technical_type,
            type_parameters,
            nullable,
          }),
        ),
        representation.columns,
      ),
      "SEMANTIC_SCHEMA_MISMATCH",
    );
    review(contract.content.row_grain.review);
    review(contract.content.key.review);
    if (contract.content.row_grain.review.state === "confirmed")
      requireCondition(
        contract.content.row_grain.description !== null,
        "ROW_GRAIN_REQUIRED",
      );
    if (contract.content.key.review.state === "confirmed")
      requireCondition(
        contract.content.key.column_ids.length > 0,
        "KEY_COLUMNS_REQUIRED",
      );
    for (const key of contract.content.key.column_ids)
      requireCondition(
        cols.some((c) => c.id === key),
        "KEY_COLUMN_MISSING",
      );
    for (const column of cols) {
      review(column.review);
      requireCondition(
        (column.null_policy.mode === "explicit_tokens") ===
          column.null_policy.tokens.length > 0,
        "NULL_POLICY_INVALID",
      );
    }
  }
  for (const plan of data.plans) {
    const input = plan.content.input;
    const source = lookup(versions, input.version_id, "PLAN_INPUT_MISSING");
    requireCondition(
      source.content.sha256 === input.version_content_sha256,
      "PLAN_INPUT_HASH_MISMATCH",
    );
    const base = input.kind === "table" ? table(input) : null;
    let contract = null;
    if (plan.content.semantic_ref) {
      contract = revisionRef(semantics, plan.content.semantic_ref);
      requireCondition(
        base &&
          same(contract.content.table_ref, {
            version_id: input.version_id,
            version_content_sha256: input.version_content_sha256,
            artifact_id: input.artifact_id,
            artifact_sha256: input.artifact_sha256,
          }),
        "SEMANTIC_INPUT_MISMATCH",
      );
    }
    requireCondition(
      !transform(plan) || contract,
      "SEMANTIC_CONTRACT_REQUIRED",
    );
    requireCondition(
      plan.content.config.lease_seconds >=
        plan.content.config.timeout_seconds + 30,
      "LEASE_BUDGET_INVALID",
    );
    const outputs = new Map();
    for (const step of plan.content.steps) {
      requireCondition(!outputs.has(step.id), "DUPLICATE_STEP_ID");
      const inputKind =
        step.input.kind === "input"
          ? input.kind
          : outputs.get(step.input.step_id);
      requireCondition(
        inputKind && inputKind !== "diagnostic",
        "INVALID_STEP_REFERENCE",
      );
      if (step.operation === "ingestion.read_csv")
        requireCondition(inputKind === "source", "READER_INPUT_INVALID");
      else requireCondition(inputKind === "table", "TABULAR_INPUT_REQUIRED");
      const columnIds =
        step.parameters.column_ids ??
        (step.parameters.column_id ? [step.parameters.column_id] : []);
      for (const columnId of columnIds)
        requireCondition(
          base?.columns.some((c) => c.id === columnId),
          "OPERATION_COLUMN_MISSING",
        );
      if (step.operation === "cleaning.cast") {
        const formats = {
          integer: "integer_ascii",
          decimal: "decimal_dot",
          date: "iso_date",
          boolean: "boolean_lowercase",
        };
        requireCondition(
          formats[step.parameters.target_type] === step.parameters.format,
          "CAST_FORMAT_MISMATCH",
        );
        requireCondition(
          (step.parameters.target_type === "decimal") ===
            (step.parameters.decimal_scale !== null),
          "CAST_SCALE_INVALID",
        );
        const column = contract.content.columns.find(
          (c) => c.id === step.parameters.column_id,
        );
        requireCondition(
          column.review.state === "confirmed",
          "CAST_REVIEW_REQUIRED",
        );
        requireCondition(
          !(
            column.role === "identifier" &&
            ["integer", "decimal"].includes(step.parameters.target_type)
          ),
          "IDENTIFIER_CAST_FORBIDDEN",
        );
      }
      outputs.set(
        step.id,
        step.operation.startsWith("cleaning.") ||
          step.operation === "ingestion.read_csv"
          ? "table"
          : "diagnostic",
      );
    }
  }
  const requestKeys = new Set();
  for (const run of data.executions) {
    requireCondition(
      run.project_id === data.dataset.project_id &&
        run.requested_by === data.dataset.owner_id,
      "RUN_SCOPE_MISMATCH",
    );
    const key = `${run.project_id}:${run.idempotency_key}`;
    requireCondition(!requestKeys.has(key), "DUPLICATE_REQUEST_KEY");
    requestKeys.add(key);
    if (run.reproducibility === "legacy_partial") {
      requireCondition(
        run.legacy !== null &&
          ["succeeded", "failed", "cancelled"].includes(run.state),
        "LEGACY_EXECUTION_NOT_TERMINAL",
      );
      continue;
    }
    requireCondition(
      run.legacy === null &&
        run.plan_ref !== null &&
        run.effective_config !== null,
      "COMPLETE_PROVENANCE_REQUIRED",
    );
    const plan = revisionRef(plans, run.plan_ref);
    requireCondition(
      same(run.effective_config, plan.content.config),
      "EFFECTIVE_CONFIG_MISMATCH",
    );
    requireCondition(
      !["succeeded", "failed", "cancelled"].includes(run.state) ||
        (run.finished_at !== null && run.active_attempt_id === null),
      "TERMINAL_RUN_INVALID",
    );
    requireCondition(
      run.mode !== "preview" ||
        (run.output_version_ids.length === 0 && run.approval_id === null),
      "PREVIEW_PUBLISHED_VERSION",
    );
    if (run.mode === "apply" && transform(plan)) {
      const approval = lookup(approvals, run.approval_id, "APPROVAL_REQUIRED");
      requireCondition(
        same(approval.plan_ref, run.plan_ref) &&
          run.required_environment_sha256 === approval.environment_sha256,
        "APPROVAL_SCOPE_MISMATCH",
      );
      requireCondition(
        Date.parse(run.created_at) >= Date.parse(approval.granted_at),
        "APPROVAL_TOO_LATE",
      );
      const publicationTime = run.finished_at ?? run.created_at;
      requireCondition(
        approval.expires_at === null ||
          Date.parse(approval.expires_at) > Date.parse(publicationTime),
        "APPROVAL_EXPIRED",
      );
      requireCondition(
        !data.revocations.some(
          (r) =>
            r.approval_id === approval.id &&
            Date.parse(r.revoked_at) <= Date.parse(publicationTime),
        ),
        "APPROVAL_REVOKED",
      );
      if (run.state === "succeeded")
        requireCondition(
          run.output_version_ids.length === 1,
          "DERIVED_OUTPUT_REQUIRED",
        );
    }
  }
  const attemptNumbers = new Set();
  for (const attempt of data.attempts) {
    const run = lookup(runs, attempt.execution_id, "ATTEMPT_RUN_MISSING");
    const key = `${run.id}:${attempt.number}`;
    requireCondition(!attemptNumbers.has(key), "DUPLICATE_ATTEMPT");
    attemptNumbers.add(key);
    requireCondition(
      attempt.environment_sha256 === digest("environment", attempt.environment),
      "ENVIRONMENT_HASH_MISMATCH",
    );
    requireCondition(
      attempt.environment.config_sha256 ===
        digest("config", run.effective_config),
      "ATTEMPT_CONFIG_MISMATCH",
    );
    requireCondition(
      attempt.number <= run.effective_config.max_attempts,
      "ATTEMPT_LIMIT_EXCEEDED",
    );
    requireCondition(
      run.required_environment_sha256 === null ||
        run.required_environment_sha256 === attempt.environment_sha256,
      "ENVIRONMENT_MISMATCH",
    );
    if (attempt.state === "running")
      requireCondition(
        attempt.finished_at === null &&
          attempt.lease_until !== null &&
          run.active_attempt_id === attempt.id,
        "ACTIVE_ATTEMPT_INVALID",
      );
    else
      requireCondition(
        attempt.finished_at !== null &&
          Date.parse(attempt.finished_at) >= Date.parse(attempt.started_at),
        "ATTEMPT_TIMESTAMPS_INVALID",
      );
  }
  for (const run of data.executions.filter(
    (r) => r.reproducibility === "complete",
  )) {
    const history = data.attempts
      .filter((a) => a.execution_id === run.id)
      .sort((a, b) => a.number - b.number);
    requireCondition(
      history.every((attempt, index) => attempt.number === index + 1),
      "ATTEMPT_SEQUENCE_INVALID",
    );
    const successful = history.filter((a) => a.state === "succeeded");
    requireCondition(successful.length <= 1, "MULTIPLE_SUCCESSFUL_ATTEMPTS");
    if (run.state === "succeeded")
      requireCondition(
        successful.length === 1 && history.at(-1).id === successful[0].id,
        "SUCCESSFUL_ATTEMPT_REQUIRED",
      );
    for (let i = 0; i < history.length; i++) {
      requireCondition(
        Date.parse(history[i].started_at) >=
          Date.parse(i ? history[i - 1].finished_at : run.created_at),
        "ATTEMPT_ORDER_INVALID",
      );
      if (run.finished_at && history[i].finished_at)
        requireCondition(
          Date.parse(run.finished_at) >= Date.parse(history[i].finished_at),
          "RUN_FINISHED_BEFORE_ATTEMPT",
        );
    }
  }
  const slots = new Set();
  for (const artifact of data.artifacts) {
    const run = lookup(runs, artifact.execution_id, "ARTIFACT_RUN_MISSING");
    requireCondition(
      artifact.project_id === run.project_id && run.state === "succeeded",
      "ARTIFACT_SCOPE_OR_PUBLICATION_INVALID",
    );
    const slot = `${run.id}:${artifact.step_id}:${artifact.slot}`;
    requireCondition(!slots.has(slot), "DUPLICATE_PUBLISHED_SLOT");
    slots.add(slot);
    if (run.reproducibility === "complete") {
      const attempt = lookup(
        attempts,
        artifact.attempt_id,
        "ARTIFACT_ATTEMPT_REQUIRED",
      );
      requireCondition(
        attempt.execution_id === run.id && attempt.state === "succeeded",
        "STALE_OR_FAILED_ATTEMPT_PUBLISHED",
      );
      requireCondition(
        revisionRef(plans, run.plan_ref).content.steps.some(
          (s) => s.id === artifact.step_id,
        ),
        "ARTIFACT_STEP_MISSING",
      );
    }
    if (artifact.version_id !== null)
      lookup(versions, artifact.version_id, "ARTIFACT_VERSION_MISSING");
    const payload = payloads.get(artifact.id);
    if (payload)
      requireCondition(payload.kind === artifact.kind, "PAYLOAD_KIND_MISMATCH");
    if (artifact.kind === "table") {
      requireCondition(
        payload?.kind === "table" &&
          artifact.columns !== null &&
          artifact.version_id !== null &&
          artifact.row_count === payload.rows.length,
        "TABLE_METADATA_MISMATCH",
      );
      requireCondition(
        payload.rows.every((row) => row.length === artifact.columns.length),
        "TABLE_ROW_SHAPE_INVALID",
      );
      requireCondition(
        artifact.logical_content_sha256 ===
          digest("table", { columns: artifact.columns, rows: payload.rows }),
        "TABLE_LOGICAL_HASH_MISMATCH",
      );
    }
    if (artifact.kind === "row_lineage") {
      requireCondition(
        payload?.kind === "row_lineage",
        "LINEAGE_PAYLOAD_REQUIRED",
      );
      const parent = table(payload.input_ref);
      const target = versions.get(artifact.version_id);
      requireCondition(
        target && same(target.parent_table_ref, payload.input_ref),
        "LINEAGE_PARENT_MISMATCH",
      );
      requireCondition(
        payload.rows.every(
          (row, i) =>
            row.output_record_number === i + 1 &&
            row.input_record_number <= parent.row_count &&
            (i === 0 ||
              row.input_record_number >
                payload.rows[i - 1].input_record_number),
        ),
        "ROW_LINEAGE_INVALID",
      );
    }
  }
  for (const approval of data.approvals) {
    requireCondition(
      approval.project_id === data.dataset.project_id &&
        approval.approved_by === data.dataset.owner_id,
      "APPROVAL_ACTOR_SCOPE_MISMATCH",
    );
    const plan = revisionRef(plans, approval.plan_ref);
    requireCondition(
      transform(plan) && plan.content.input.kind === "table",
      "APPROVAL_PLAN_INVALID",
    );
    table(approval.input_ref);
    revisionRef(semantics, approval.semantic_ref);
    const preview = lookup(
      artifacts,
      approval.preview_artifact_id,
      "PREVIEW_REQUIRED",
    );
    const run = lookup(runs, preview.execution_id, "PREVIEW_RUN_REQUIRED");
    requireCondition(
      preview.kind === "cleaning_preview" &&
        run.mode === "preview" &&
        same(run.plan_ref, approval.plan_ref),
      "PREVIEW_PLAN_MISMATCH",
    );
    const effect = payloads.get(preview.id)?.effect;
    requireCondition(
      effect && digest("effect", effect) === approval.effect_sha256,
      "APPROVAL_EFFECT_MISMATCH",
    );
    requireCondition(
      same(effect.input_ref, approval.input_ref) &&
        same(effect.semantic_ref, approval.semantic_ref) &&
        same(effect.plan_ref, approval.plan_ref),
      "APPROVAL_INPUT_MISMATCH",
    );
    const { kind: _kind, alias: _alias, ...planInput } = plan.content.input;
    requireCondition(
      same(planInput, approval.input_ref) &&
        same(plan.content.semantic_ref, approval.semantic_ref),
      "APPROVAL_SCOPE_MISMATCH",
    );
    requireCondition(
      effect.config_sha256 === approval.effective_config_sha256 &&
        effect.environment_sha256 === approval.environment_sha256,
      "APPROVAL_CONFIG_MISMATCH",
    );
    requireCondition(
      digest("config", run.effective_config) ===
        approval.effective_config_sha256 &&
        attempts.get(preview.attempt_id).environment_sha256 ===
          approval.environment_sha256,
      "PREVIEW_ENVIRONMENT_MISMATCH",
    );
    requireCondition(
      preview.logical_content_sha256 === effect.output_logical_sha256 &&
        same(preview.columns, effect.output_columns) &&
        preview.row_count === effect.output_rows,
      "PREVIEW_METADATA_MISMATCH",
    );
    requireCondition(
      effect.conversion_errors === 0 &&
        effect.input_rows - effect.excluded_rows === effect.output_rows,
      "PREVIEW_EFFECT_INVALID",
    );
    requireCondition(
      Date.parse(approval.granted_at) >= Date.parse(run.finished_at),
      "APPROVAL_BEFORE_PREVIEW",
    );
    const appliedRuns = data.executions.filter(
      (r) => r.approval_id === approval.id && r.state === "succeeded",
    );
    for (const applied of appliedRuns) {
      const finalVersion = versions.get(applied.output_version_ids[0]);
      const output = data.artifacts.find(
        (a) =>
          a.kind === "table" &&
          a.execution_id === applied.id &&
          a.version_id === finalVersion.id,
      );
      const lineage = payloads.get(finalVersion.row_lineage_artifact_id);
      requireCondition(
        output &&
          output.logical_content_sha256 === effect.output_logical_sha256 &&
          same(output.columns, effect.output_columns) &&
          output.row_count === effect.output_rows,
        "PREVIEW_EFFECT_MISMATCH",
      );
      requireCondition(
        lineage &&
          digest("row_lineage", {
            input_ref: lineage.input_ref,
            rows: lineage.rows,
          }) === effect.row_lineage_sha256,
        "PREVIEW_LINEAGE_MISMATCH",
      );
      const sourceTable = table(approval.input_ref);
      const sourceRows = payloads.get(sourceTable.id).rows;
      const outputRows = payloads.get(output.id).rows;
      let changedRows = 0,
        changedCells = 0,
        createdNulls = 0;
      requireCondition(
        lineage.rows.length === outputRows.length,
        "LINEAGE_ROW_COUNT_MISMATCH",
      );
      for (const mapping of lineage.rows) {
        const before = sourceRows[mapping.input_record_number - 1];
        const after = outputRows[mapping.output_record_number - 1];
        let changed = false;
        for (let i = 0; i < output.columns.length; i++) {
          const sourceIndex = sourceTable.columns.findIndex(
            (c) => c.id === output.columns[i].id,
          );
          requireCondition(
            sourceIndex >= 0,
            "UNSUPPORTED_FIXTURE_COLUMN_PROVENANCE",
          );
          const sourceColumn = sourceTable.columns[sourceIndex];
          const typeChanged =
            sourceColumn.technical_type !== output.columns[i].technical_type ||
            !same(
              sourceColumn.type_parameters,
              output.columns[i].type_parameters,
            );
          if (
            before[sourceIndex] !== after[i] ||
            (after[i] !== null && typeChanged)
          ) {
            changedCells++;
            changed = true;
          }
          if (before[sourceIndex] !== null && after[i] === null) createdNulls++;
        }
        if (changed) changedRows++;
      }
      requireCondition(
        effect.input_rows === sourceRows.length &&
          effect.output_rows === outputRows.length &&
          effect.changed_rows === changedRows &&
          effect.changed_cells === changedCells &&
          effect.created_nulls === createdNulls,
        "PREVIEW_IMPACT_MISMATCH",
      );
    }
  }
  for (const revocation of data.revocations) {
    const approval = lookup(
      approvals,
      revocation.approval_id,
      "REVOCATION_APPROVAL_MISSING",
    );
    requireCondition(
      revocation.project_id === approval.project_id &&
        revocation.revoked_by === data.dataset.owner_id &&
        Date.parse(revocation.revoked_at) >= Date.parse(approval.granted_at),
      "REVOCATION_SCOPE_INVALID",
    );
  }
  for (const evidence of data.evidence) {
    const artifact = lookup(
      artifacts,
      evidence.artifact_id,
      "EVIDENCE_ARTIFACT_MISSING",
    );
    requireCondition(
      evidence.project_id === artifact.project_id &&
        evidence.artifact_sha256 === artifact.content.sha256,
      "EVIDENCE_SCOPE_MISMATCH",
    );
    if (evidence.selector.kind === "metric") {
      const metrics = payloads.get(artifact.id)?.metrics;
      requireCondition(
        artifact.kind === "quality" &&
          metrics &&
          String(metrics[evidence.selector.key]) === evidence.expected_value,
        "EVIDENCE_VALUE_MISMATCH",
      );
    }
  }
  return true;
}

const json = (name) => readFile(new URL(name, import.meta.url), "utf8");
requireCondition(
  (await json("schema.json")) === JSON.stringify(schema, null, 2) + "\n",
  "GENERATED_SCHEMA_DRIFT",
);
const rawCorpus = await json("examples.json");
const corpus = JSON.parse(rawCorpus);
requireCondition(
  rawCorpus === JSON.stringify(corpus, null, 2) + "\n",
  "GENERATED_EXAMPLES_SERIALIZATION_DRIFT",
);
requireCondition(same(corpus, buildExamples()), "GENERATED_EXAMPLES_DRIFT");
validate(corpus);
assert.equal(
  canonical({ z: [null, "001"], b: "á", a: 1 }),
  '{"a":1,"b":"á","z":[null,"001"]}',
);
for (const value of [
  0.1,
  -0,
  Infinity,
  { a: undefined },
  { "columna ñ": 1 },
  new Array(1),
  "\ud800",
])
  assert.throws(() => canonical(value));

const negative = [
  [
    "hash de plan modificado",
    (d) => {
      d.plans[2].content.objective = "Otro objetivo";
    },
    /REVISION_HASH_MISMATCH/,
  ],
  [
    "tabla de otra interpretación",
    (d) => {
      d.semantic_contracts[0].content.table_ref.artifact_sha256 = "0".repeat(
        64,
      );
      d.semantic_contracts[0].content_sha256 = digest(
        "semantic",
        d.semantic_contracts[0].content,
      );
    },
    /TABLE_HASH_MISMATCH/,
  ],
  [
    "confirmación atribuida a IA",
    (d) => {
      d.semantic_contracts[1].content.columns[0].review.origin = "ai";
      d.semantic_contracts[1].content_sha256 = digest(
        "semantic",
        d.semantic_contracts[1].content,
      );
    },
    /HUMAN_REVIEW_REQUIRED/,
  ],
  [
    "paso adelantado/ciclo",
    (d) => {
      d.plans[2].content.steps[0].input = { kind: "step", step_id: "trim" };
      d.plans[2].content_sha256 = digest("plan", d.plans[2].content);
    },
    /INVALID_STEP_REFERENCE/,
  ],
  [
    "apply sin aprobación",
    (d) => {
      d.executions[3].approval_id = null;
    },
    /APPROVAL_REQUIRED/,
  ],
  [
    "aprobación revocada antes de aplicar",
    (d) => {
      d.revocations.push({
        schema_version: 1,
        id: "ffffffff-ffff-4fff-8fff-ffffffffffff",
        project_id: d.dataset.project_id,
        approval_id: d.approvals[0].id,
        revoked_by: d.dataset.owner_id,
        revoked_at: "2026-10-27T09:06:30Z",
        reason: "Prueba negativa",
      });
    },
    /APPROVAL_REVOKED/,
  ],
  [
    "dos salidas publicadas para un slot",
    (d) => {
      const copy = structuredClone(d.artifacts[0]);
      copy.id = "ffffffff-ffff-4fff-8fff-ffffffffffff";
      d.artifacts.push(copy);
    },
    /DUPLICATE_PUBLISHED_SLOT/,
  ],
  [
    "publicación desde intento fallido",
    (d) => {
      d.artifacts.find(
        (a) => a.kind === "table" && a.version_id === d.versions[1].id,
      ).attempt_id = d.attempts[3].id;
    },
    /STALE_OR_FAILED_ATTEMPT_PUBLISHED/,
  ],
  [
    "evidencia con cifra inventada",
    (d) => {
      d.evidence[0].expected_value = "999";
    },
    /EVIDENCE_VALUE_MISMATCH/,
  ],
  [
    "origen de fila fuera de rango",
    (d) => {
      d.artifact_payloads.find(
        (p) => p.kind === "row_lineage",
      ).rows[0].input_record_number = 999;
    },
    /ROW_LINEAGE_INVALID/,
  ],
  [
    "impacto inventado con hash recalculado",
    (d) => {
      const effect = d.artifact_payloads.find(
        (p) => p.kind === "cleaning_preview",
      ).effect;
      effect.changed_cells = 999;
      d.approvals[0].effect_sha256 = digest("effect", effect);
    },
    /PREVIEW_IMPACT_MISMATCH/,
  ],
  [
    "historia incompleta reenviada a cola",
    (d) => {
      const run = d.executions[1];
      run.reproducibility = "legacy_partial";
      run.legacy = {
        source_table: "import_executions",
        source_id: run.id,
        historical_attempt_count: 1,
      };
      run.state = "queued";
      run.plan_ref = null;
      run.effective_config = null;
    },
    /LEGACY_EXECUTION_NOT_TERMINAL/,
  ],
];
for (const [name, mutate, code] of negative) {
  const invalid = structuredClone(corpus);
  mutate(invalid);
  assert.throws(() => validate(invalid), code, name);
}
console.log(
  `Contratos de diseño v1: esquema y escenario válidos; ${negative.length} casos negativos y 8 comprobaciones canónicas aprobados.`,
);
console.log(
  "Sin llamadas HTTP, PostgreSQL, migraciones ni cambios de datos de aplicación.",
);
