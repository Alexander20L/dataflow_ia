"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ListChecks,
  LoaderCircle,
  Play,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import { useUnsavedGuard } from "@/lib/use-unsaved-guard";
import { useRepresentations } from "@/features/executions/api";
import { useCreatePlan, useExecutePlan } from "@/features/planning/api";
import { useUnderstanding } from "@/features/understanding/api";
import { RulesReport } from "./report";
import {
  useQualityRulesReport,
  useQualityRulesets,
  useRun,
  useSaveRuleset,
  type Rule,
  type RulesetDraft,
  type RulesetRevision,
} from "./api";

type Column = { id: string; name: string; type: string };
type Kind = Rule["kind"];
type Table = { id: string; sha256: string; columns: Column[] };

const KINDS: { kind: Kind; label: string; types: string[] | null }[] = [
  { kind: "required", label: "Obligatoria (sin nulos)", types: null },
  { kind: "unique_key", label: "Clave única", types: null },
  { kind: "range", label: "Rango", types: ["integer", "decimal", "date"] },
  {
    kind: "allowed_values",
    label: "Catálogo de valores",
    types: ["string", "integer", "boolean"],
  },
  { kind: "convertible", label: "Formato convertible", types: ["string"] },
];
const CAST_TYPES = ["integer", "decimal", "date", "boolean"] as const;

function slug(value: string) {
  const base = value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return (/^[a-z]/.test(base) ? base : `r_${base}`).slice(0, 34) || "regla";
}

export function ruleSummary(rule: Rule, names: Map<string, string>) {
  const column = (id: string) => names.get(id) ?? id.slice(0, 8);
  switch (rule.kind) {
    case "required":
      return column(rule.column_id);
    case "unique_key":
      return `${rule.column_ids.map(column).join(" + ")}${rule.source === "semantic_key" ? " (clave declarada)" : ""}`;
    case "range":
      return `${column(rule.column_id)} ∈ [${rule.minimum ?? "−∞"}, ${rule.maximum ?? "+∞"}]`;
    case "allowed_values":
      return `${column(rule.column_id)} ∈ {${rule.values.join(", ")}}`;
    case "convertible":
      return `${column(rule.column_id)} → ${rule.type}${rule.scale !== null && rule.scale !== undefined ? ` (${rule.scale})` : ""}`;
  }
}

export function QualityRules({
  projectId,
  versionId,
  archived,
  onDirtyChange,
}: {
  projectId: string;
  versionId: string;
  archived: boolean;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const tables = useRepresentations(versionId);
  const raw = tables.data?.[0];
  const context = useQualityRulesets(raw?.id);
  if (tables.isPending || (raw && context.isPending))
    return (
      <p className="empty-copy" role="status">
        Cargando las reglas de calidad…
      </p>
    );
  if (!raw?.columns || !context.data)
    return context.isError ? (
      <p className="auth-error" role="alert">
        {errorMessage(context.error)}
      </p>
    ) : null;
  const table: Table = {
    id: raw.id,
    sha256: raw.sha256,
    columns: raw.columns.map((c) => ({
      id: String(c.id),
      name: String(c.name),
      type: String(c.technical_type ?? "string"),
    })),
  };
  const own = context.data.own;
  return (
    <Editor
      key={own?.head.id ?? "new"}
      projectId={projectId}
      versionId={versionId}
      table={table}
      head={own?.head ?? null}
      others={context.data.others}
      archived={archived}
      onDirtyChange={onDirtyChange}
    />
  );
}

function Editor({
  projectId,
  versionId,
  table,
  head,
  others,
  archived,
  onDirtyChange,
}: {
  projectId: string;
  versionId: string;
  table: Table;
  head: RulesetRevision | null;
  others: NonNullable<ReturnType<typeof useQualityRulesets>["data"]>["others"];
  archived: boolean;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const baseline: RulesetDraft = head
    ? { name: head.content.name, rules: head.content.rules }
    : { name: "Reglas de calidad", rules: [] };
  const [draft, setDraft] = useState<RulesetDraft>(baseline);
  const [kind, setKind] = useState<Kind>("required");
  const [columnIds, setColumnIds] = useState<string[]>([]);
  const [severity, setSeverity] = useState<"low" | "medium" | "high">("medium");
  const [minimum, setMinimum] = useState("");
  const [maximum, setMaximum] = useState("");
  const [values, setValues] = useState("");
  const [castType, setCastType] =
    useState<(typeof CAST_TYPES)[number]>("integer");
  const [scale, setScale] = useState(2);
  const [runId, setRunId] = useState<string | null>(null);
  const [formError, setFormError] = useState("");
  const router = useRouter();
  const save = useSaveRuleset(table.id);
  const createPlan = useCreatePlan(projectId);
  const execute = useExecutePlan(versionId);
  const understanding = useUnderstanding(table.id);
  const run = useRun(runId);
  const report = useQualityRulesReport(run.data);
  const rules = draft.rules ?? [];
  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline);
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  const [route, setRoute] = useUnsavedGuard(dirty);
  const names = new Map(table.columns.map((c) => [c.id, c.name]));
  const allowed = KINDS.find((k) => k.kind === kind)!.types;
  const choices = table.columns.filter(
    (c) => !allowed || allowed.includes(c.type),
  );
  const key = understanding.data?.head?.content.key;
  const semanticHead = understanding.data?.head;
  const busy = save.isPending || createPlan.isPending || execute.isPending;

  function uniqueId(base: string) {
    let id = slug(base);
    let n = 2;
    while (rules.some((r) => r.id === id)) id = `${slug(base)}_${n++}`;
    return id;
  }
  function add(rule: Rule) {
    setDraft({ ...draft, rules: [...rules, rule] });
    setColumnIds([]);
    setFormError("");
  }
  function addFromForm() {
    const columns = columnIds.filter((id) => choices.some((c) => c.id === id));
    if (!columns.length) return setFormError("Elige al menos una columna.");
    const first = columns[0];
    const id = uniqueId(
      `${kind}_${columns.map((c) => names.get(c)).join("_")}`,
    );
    if (kind === "unique_key")
      return add({ id, kind, column_ids: columns, severity, source: "user" });
    if (kind === "required")
      return add({ id, kind, column_id: first, severity });
    if (kind === "range") {
      if (!minimum && !maximum)
        return setFormError("Indica un mínimo, un máximo o ambos.");
      return add({
        id,
        kind,
        column_id: first,
        severity,
        minimum: minimum || null,
        maximum: maximum || null,
      });
    }
    if (kind === "allowed_values") {
      const list = [
        ...new Set(
          values
            .split(",")
            .map((v) => v.trim())
            .filter(Boolean),
        ),
      ];
      if (!list.length) return setFormError("Indica los valores permitidos.");
      return add({ id, kind, column_id: first, severity, values: list });
    }
    return add({
      id,
      kind: "convertible",
      column_id: first,
      severity,
      type: castType,
      scale: castType === "decimal" ? scale : null,
    });
  }
  async function evaluate(revision: RulesetRevision) {
    setRunId(null);
    try {
      const plan = await createPlan.mutateAsync({
        table_artifact_id: table.id,
        table_sha256: table.sha256,
        semantic_ref: null,
        steps: [
          {
            id: "rules",
            operation: "quality.evaluate",
            version: 2,
            input: { kind: "input", alias: "source" },
            parameters: {
              rule_set: "csv-quality-v2",
              ruleset_revision_id: revision.id,
              ruleset_sha256: revision.content_sha256,
            },
          },
        ],
      });
      const started = await execute.mutateAsync(plan.id);
      setRunId(started.id);
    } catch {
      /* Error visible. */
    }
  }

  return (
    <section className="quality-rules" aria-label="Reglas de calidad">
      <div className="section-heading">
        <div>
          <h3>
            <ListChecks size={17} /> Reglas de calidad del proyecto
          </h3>
          <p>
            Reglas de negocio (csv-quality-v2) guardadas como revisiones
            inmutables. Se evalúan aparte de la completitud técnica: no cambian
            Q-001 a Q-003 ni el diagnóstico de esta versión.
          </p>
        </div>
        {dirty ? (
          <span className="badge review">Cambios sin guardar</span>
        ) : head ? (
          <span className="badge calculated">Revisión {head.revision}</span>
        ) : null}
      </div>
      <label className="rules-name">
        Nombre del conjunto
        <input
          aria-label="Nombre del conjunto"
          value={draft.name}
          disabled={archived}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        />
      </label>
      {rules.length ? (
        <div className="table-scroll bordered">
          <table aria-label="Reglas del conjunto">
            <thead>
              <tr>
                <th>Regla</th>
                <th>Tipo</th>
                <th>Definición</th>
                <th>Gravedad</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.id}>
                  <td className="mono">{rule.id}</td>
                  <td>{KINDS.find((k) => k.kind === rule.kind)?.label}</td>
                  <td>{ruleSummary(rule, names)}</td>
                  <td>
                    {
                      { low: "Baja", medium: "Media", high: "Alta" }[
                        rule.severity ?? "medium"
                      ]
                    }
                  </td>
                  <td>
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Quitar ${rule.id}`}
                      disabled={archived}
                      onClick={() =>
                        setDraft({
                          ...draft,
                          rules: rules.filter((r) => r.id !== rule.id),
                        })
                      }
                    >
                      <Trash2 size={14} />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="empty-copy">Todavía no hay reglas en este conjunto.</p>
      )}
      {!archived && (
        <fieldset className="rule-form">
          <legend>Añadir regla</legend>
          <label>
            Tipo de regla
            <select
              aria-label="Tipo de regla"
              value={kind}
              onChange={(e) => {
                setKind(e.target.value as Kind);
                setColumnIds([]);
              }}
            >
              {KINDS.map((k) => (
                <option key={k.kind} value={k.kind}>
                  {k.label}
                </option>
              ))}
            </select>
          </label>
          {kind === "unique_key" ? (
            <div className="chip-options" aria-label="Columnas de la clave">
              {choices.map((c) => (
                <label key={c.id} className="check-option">
                  <input
                    type="checkbox"
                    aria-label={`Columna de la clave: ${c.name}`}
                    checked={columnIds.includes(c.id)}
                    onChange={(e) =>
                      setColumnIds(
                        e.target.checked
                          ? [...columnIds, c.id]
                          : columnIds.filter((id) => id !== c.id),
                      )
                    }
                  />
                  {c.name}
                </label>
              ))}
            </div>
          ) : (
            <label>
              Columna
              <select
                aria-label="Columna de la regla"
                value={columnIds[0] ?? ""}
                onChange={(e) =>
                  setColumnIds(e.target.value ? [e.target.value] : [])
                }
              >
                <option value="">Elige una columna</option>
                {choices.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} · {c.type}
                  </option>
                ))}
              </select>
            </label>
          )}
          {kind === "range" && (
            <>
              <label>
                Mínimo
                <input
                  aria-label="Mínimo"
                  value={minimum}
                  placeholder="0 o 2026-01-01"
                  onChange={(e) => setMinimum(e.target.value)}
                />
              </label>
              <label>
                Máximo
                <input
                  aria-label="Máximo"
                  value={maximum}
                  onChange={(e) => setMaximum(e.target.value)}
                />
              </label>
            </>
          )}
          {kind === "allowed_values" && (
            <label>
              Valores permitidos (separados por comas)
              <input
                aria-label="Valores permitidos"
                value={values}
                onChange={(e) => setValues(e.target.value)}
              />
            </label>
          )}
          {kind === "convertible" && (
            <label>
              Formato
              <select
                aria-label="Formato convertible"
                value={castType}
                onChange={(e) =>
                  setCastType(e.target.value as (typeof CAST_TYPES)[number])
                }
              >
                {CAST_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              {castType === "decimal" && (
                <input
                  type="number"
                  className="scale-input"
                  aria-label="Escala del formato"
                  min={0}
                  max={12}
                  value={scale}
                  onChange={(e) =>
                    setScale(
                      Math.min(12, Math.max(0, Number(e.target.value) || 0)),
                    )
                  }
                />
              )}
            </label>
          )}
          <label>
            Gravedad
            <select
              aria-label="Gravedad"
              value={severity}
              onChange={(e) =>
                setSeverity(e.target.value as "low" | "medium" | "high")
              }
            >
              <option value="low">Baja</option>
              <option value="medium">Media</option>
              <option value="high">Alta</option>
            </select>
          </label>
          <div className="form-footer">
            {formError && (
              <span className="auth-error" role="alert">
                {formError}
              </span>
            )}
            {semanticHead &&
              key?.review.state === "confirmed" &&
              key.column_ids.length > 0 && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    add({
                      id: uniqueId("clave_declarada"),
                      kind: "unique_key",
                      column_ids: key.column_ids,
                      severity,
                      source: "semantic_key",
                      semantic_ref: {
                        id: semanticHead.id,
                        revision: semanticHead.revision,
                        content_sha256: semanticHead.content_sha256,
                      },
                    })
                  }
                >
                  Activar unicidad de la clave declarada
                </Button>
              )}
            <Button size="sm" variant="outline" onClick={addFromForm}>
              <Plus size={14} /> Añadir regla
            </Button>
          </div>
        </fieldset>
      )}
      {(save.isError || createPlan.isError || execute.isError) && (
        <p className="auth-error" role="alert">
          {errorMessage(save.error ?? createPlan.error ?? execute.error)}
        </p>
      )}
      <div className="form-footer">
        <Button
          variant="outline"
          disabled={archived || busy || !dirty}
          onClick={() =>
            void save
              .mutateAsync({
                table_sha256: table.sha256,
                expected_revision: head?.revision ?? 0,
                draft,
              })
              .catch(() => {})
          }
        >
          <Save size={15} /> Guardar reglas
        </Button>
        <Button
          disabled={
            busy || dirty || !head || !(head.content.rules ?? []).length
          }
          title={dirty ? "Guarda las reglas antes de evaluarlas." : undefined}
          onClick={() => head && void evaluate(head)}
        >
          {busy ? (
            <LoaderCircle className="spin" size={15} />
          ) : (
            <Play size={15} />
          )}
          Evaluar reglas
        </Button>
      </div>
      {others.length > 0 && (
        <div className="other-rulesets">
          <h4>Conjuntos de otras versiones del proyecto</h4>
          {others.map((other) => (
            <div key={other.family_id} className="finding-card">
              <strong>
                {other.head.content.name} · revisión {other.head.revision}
              </strong>
              {other.applicable ? (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() => void evaluate(other.head)}
                >
                  <Play size={14} /> Evaluar aquí
                </Button>
              ) : (
                <small className="muted">
                  No aplicable a esta versión:{" "}
                  {other.problems.map((p) => p.message).join(" ")}
                </small>
              )}
            </div>
          ))}
        </div>
      )}
      {runId && (
        <div className="rules-result" role="status">
          {run.data?.state === "failed" ? (
            <p className="auth-error" role="alert">
              {run.data.error_code}: {run.data.error_message}
            </p>
          ) : report.data ? (
            <RulesReport report={report.data} />
          ) : (
            <p className="empty-copy">
              <LoaderCircle className="spin" size={15} /> Evaluando las reglas
              sobre todo el dataset…
            </p>
          )}
        </div>
      )}
      {route && (
        <Dialog title="Hay cambios sin guardar" onClose={() => setRoute(null)}>
          <p className="dialog-copy">
            Puedes seguir editando o descartar estas reglas para salir. Las
            revisiones guardadas se conservan.
          </p>
          <div className="form-footer">
            <Button variant="ghost" onClick={() => setRoute(null)}>
              Seguir editando
            </Button>
            <Button
              onClick={() => {
                onDirtyChange(false);
                router.push(route);
                setRoute(null);
              }}
            >
              Descartar y salir
            </Button>
          </div>
        </Dialog>
      )}
    </section>
  );
}
