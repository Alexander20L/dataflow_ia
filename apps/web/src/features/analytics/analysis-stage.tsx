"use client";
import { useState } from "react";
import { BarChart3, Calculator, LoaderCircle, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import { useRepresentations } from "@/features/executions/api";
import {
  problemLabels,
  useCreatePlan,
  useExecutePlan,
  type Plan,
} from "@/features/planning/api";
import { useUnderstanding } from "@/features/understanding/api";
import {
  useAnalysisResult,
  useAnalysisRun,
  useMetrics,
  useSaveMetric,
  type MetricRevision,
} from "./api";
import {
  AGGREGATIONS,
  COMPARISONS,
  GRAINS,
  OPERATORS,
  type Aggregation,
  type ComparisonKind,
  type Grain,
} from "./labels";
import { Results } from "./results";
import { AddToDashboard } from "@/features/dashboards/add-to-dashboard";

type Column = { id: string; name: string; type: string };

export function AnalysisStage({
  projectId,
  versionId,
  archived,
  onOpenUnderstanding,
}: {
  projectId: string;
  versionId: string;
  archived: boolean;
  onOpenUnderstanding: () => void;
}) {
  const tables = useRepresentations(versionId);
  const raw = tables.data?.[0];
  const metrics = useMetrics(raw?.id);
  const understanding = useUnderstanding(raw?.id ?? "");
  if (
    tables.isPending ||
    (raw && (metrics.isPending || understanding.isPending))
  )
    return (
      <p className="empty-copy" role="status">
        Cargando el análisis…
      </p>
    );
  if (!raw?.columns || !metrics.data)
    return metrics.isError ? (
      <p className="auth-error" role="alert">
        {errorMessage(metrics.error)}
      </p>
    ) : null;
  const columns: Column[] = raw.columns.map((c) => ({
    id: String(c.id),
    name: String(c.name),
    type: String(c.technical_type ?? "string"),
  }));
  const head = understanding.data?.head ?? null;
  return (
    <Builder
      projectId={projectId}
      versionId={versionId}
      table={{ id: raw.id, sha256: raw.sha256 }}
      columns={columns}
      metrics={metrics.data.metrics}
      semantic={
        head
          ? {
              id: head.id,
              revision: head.revision,
              content_sha256: head.content_sha256,
            }
          : null
      }
      archived={archived}
      onOpenUnderstanding={onOpenUnderstanding}
    />
  );
}

function Builder({
  projectId,
  versionId,
  table,
  columns,
  metrics,
  semantic,
  archived,
  onOpenUnderstanding,
}: {
  projectId: string;
  versionId: string;
  table: { id: string; sha256: string };
  columns: Column[];
  metrics: NonNullable<ReturnType<typeof useMetrics>["data"]>["metrics"];
  semantic: { id: string; revision: number; content_sha256: string } | null;
  archived: boolean;
  onOpenUnderstanding: () => void;
}) {
  const names = new Map(columns.map((c) => [c.id, c.name]));
  const [selected, setSelected] = useState<string[]>([]);
  const [dimensions, setDimensions] = useState<string[]>([]);
  const [grain, setGrain] = useState<Grain | "">("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [avgScale, setAvgScale] = useState(4);
  const [comparisons, setComparisons] = useState<ComparisonKind[]>([]);
  const [rankBy, setRankBy] = useState("");
  const [direction, setDirection] = useState<"desc" | "asc">("desc");
  const [topN, setTopN] = useState(10);
  const [shares, setShares] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const createPlan = useCreatePlan(projectId);
  const execute = useExecutePlan(versionId);
  const run = useAnalysisRun(runId);
  const result = useAnalysisResult(runId, run.data?.state === "succeeded");
  const applicable = metrics.filter((m) => m.applicable);
  const chosen = applicable.filter((m) => selected.includes(m.head.id));
  const busy = createPlan.isPending || execute.isPending;
  const additive = chosen.filter(
    (m) =>
      AGGREGATIONS.find((a) => a.value === m.head.content.aggregation)
        ?.additive,
  );
  const ranked = chosen.find((m) => m.head.id === rankBy);

  async function calculate() {
    setRunId(null);
    setPlan(null);
    try {
      const saved = await createPlan.mutateAsync({
        table_artifact_id: table.id,
        table_sha256: table.sha256,
        semantic_ref: semantic,
        steps: [
          {
            id: "query",
            operation: "analytics.query",
            version: 2,
            input: { kind: "input", alias: "source" },
            parameters: {
              metrics: chosen.map((m) => ({
                revision_id: m.head.id,
                content_sha256: m.head.content_sha256,
              })),
              dimensions,
              filters: [],
              time_grain: grain || null,
              time_range:
                start || end
                  ? { start: start || null, end: end || null }
                  : null,
              avg_scale: avgScale,
              max_result_rows: 1000,
              comparisons: grain ? comparisons : [],
              change_scale: 2,
              ranking:
                ranked && dimensions.length > 0
                  ? {
                      metric_revision_id: ranked.head.id,
                      direction,
                      top_n: topN,
                    }
                  : null,
              share_of_total: additive
                .filter((m) => shares.includes(m.head.id))
                .map((m) => m.head.id),
              share_scale: 2,
            },
          },
        ],
      });
      setPlan(saved);
      if (saved.validation.valid) {
        const started = await execute.mutateAsync(saved.id);
        setRunId(started.id);
      }
    } catch {
      /* Error visible. */
    }
  }

  const problems = plan?.validation.valid
    ? []
    : (plan?.validation.problems ?? []);
  return (
    <section className="analysis-stage" aria-label="Análisis de negocio">
      <div className="section-heading">
        <div>
          <h3>
            <BarChart3 size={17} /> Análisis con métricas definidas
          </h3>
          <p>
            Cada cifra sale de una métrica que tú defines (columna, agregación,
            filtros y fecha de negocio) sobre esta versión exacta. Nada se
            deduce: una suma no es «ingresos» hasta que la nombras así.
          </p>
        </div>
        <span className="badge neutral">
          {semantic
            ? `Revisión semántica ${semantic.revision}`
            : "Sin revisión semántica"}
        </span>
      </div>

      <div className="metric-list" aria-label="Métricas">
        {metrics.length === 0 && (
          <p className="empty-copy">
            Todavía no hay métricas en este proyecto.
          </p>
        )}
        {metrics.map((metric) => {
          const content = metric.head.content;
          return (
            <label
              key={metric.family_id}
              className={`metric-option ${metric.applicable ? "" : "unavailable"}`}
            >
              <input
                type="checkbox"
                aria-label={`Usar ${content.label}`}
                disabled={!metric.applicable}
                checked={selected.includes(metric.head.id)}
                onChange={(e) =>
                  setSelected(
                    e.target.checked
                      ? [...selected, metric.head.id]
                      : selected.filter((id) => id !== metric.head.id),
                  )
                }
              />
              <span>
                <strong>{content.label}</strong>
                <small className="muted">
                  {
                    AGGREGATIONS.find((a) => a.value === content.aggregation)
                      ?.label
                  }{" "}
                  de{" "}
                  {names.get(content.measure_column_id) ??
                    "columna de otra versión"}
                  {content.time_column_id
                    ? ` · fecha: ${names.get(content.time_column_id) ?? "?"}`
                    : ""}
                  {content.filters?.length
                    ? ` · ${content.filters.length} filtro(s)`
                    : ""}{" "}
                  · revisión {metric.head.revision}
                </small>
                {!metric.applicable && (
                  <small className="muted">
                    No aplicable:{" "}
                    {metric.problems.map((p) => p.message).join(" ")}
                  </small>
                )}
              </span>
            </label>
          );
        })}
        {!archived && (
          <Button size="sm" variant="ghost" onClick={() => setCreating(true)}>
            <Plus size={14} /> Nueva métrica
          </Button>
        )}
      </div>

      <fieldset className="query-options">
        <legend>Consulta</legend>
        <div className="chip-options" aria-label="Dimensiones">
          {columns.map((c) => (
            <label key={c.id} className="check-option">
              <input
                type="checkbox"
                aria-label={`Agrupar por ${c.name}`}
                checked={dimensions.includes(c.id)}
                disabled={!dimensions.includes(c.id) && dimensions.length >= 4}
                onChange={(e) =>
                  setDimensions(
                    e.target.checked
                      ? [...dimensions, c.id]
                      : dimensions.filter((id) => id !== c.id),
                  )
                }
              />
              {c.name}
            </label>
          ))}
        </div>
        <label>
          Agrupar por tiempo
          <select
            aria-label="Agrupar por tiempo"
            value={grain}
            onChange={(e) => setGrain(e.target.value as Grain | "")}
          >
            <option value="">Sin agrupar por tiempo</option>
            {GRAINS.map((g) => (
              <option key={g.value} value={g.value}>
                {g.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Desde
          <input
            type="date"
            aria-label="Desde"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
        <label>
          Hasta
          <input
            type="date"
            aria-label="Hasta"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </label>
        {chosen.some((m) => m.head.content.aggregation === "avg") && (
          <label>
            Decimales de la media
            <input
              type="number"
              aria-label="Decimales de la media"
              className="scale-input"
              min={0}
              max={12}
              value={avgScale}
              onChange={(e) =>
                setAvgScale(
                  Math.min(12, Math.max(0, Number(e.target.value) || 0)),
                )
              }
            />
          </label>
        )}
        <fieldset className="compare-options" aria-label="Comparar y ordenar">
          <legend>Comparar y ordenar</legend>
          <div className="chip-options" aria-label="Comparaciones">
            {COMPARISONS.map((c) => (
              <label key={c.value} className="check-option">
                <input
                  type="checkbox"
                  aria-label={`Comparar con ${c.label.toLowerCase()}`}
                  disabled={!grain}
                  checked={!!grain && comparisons.includes(c.value)}
                  onChange={(e) =>
                    setComparisons(
                      e.target.checked
                        ? [...comparisons, c.value]
                        : comparisons.filter((k) => k !== c.value),
                    )
                  }
                />
                {c.label}
              </label>
            ))}
          </div>
          <small className="muted">
            {grain
              ? "Con comparaciones, el periodo debe empezar y terminar en límites completos (p. ej. del 1 de febrero al 31 de marzo por mes)."
              : "Para comparar periodos, agrupa por tiempo."}
          </small>
          <label>
            Top N por
            <select
              aria-label="Ordenar por"
              value={ranked && dimensions.length > 0 ? rankBy : ""}
              disabled={dimensions.length === 0 || chosen.length === 0}
              onChange={(e) => setRankBy(e.target.value)}
            >
              <option value="">Sin ranking</option>
              {chosen.map((m) => (
                <option key={m.head.id} value={m.head.id}>
                  {m.head.content.label}
                </option>
              ))}
            </select>
          </label>
          {ranked && dimensions.length > 0 && (
            <>
              <label>
                Orden
                <select
                  aria-label="Orden del ranking"
                  value={direction}
                  onChange={(e) =>
                    setDirection(e.target.value as "desc" | "asc")
                  }
                >
                  <option value="desc">De mayor a menor</option>
                  <option value="asc">De menor a mayor</option>
                </select>
              </label>
              <label>
                Cuántos
                <input
                  type="number"
                  aria-label="Top N"
                  className="scale-input"
                  min={1}
                  max={1000}
                  value={topN}
                  onChange={(e) =>
                    setTopN(
                      Math.min(1000, Math.max(1, Number(e.target.value) || 1)),
                    )
                  }
                />
              </label>
            </>
          )}
          {dimensions.length === 0 && (
            <small className="muted">
              Para un top N, agrupa por al menos una dimensión.
            </small>
          )}
          {additive.length > 0 && (
            <div className="chip-options" aria-label="Participación">
              {additive.map((m) => (
                <label key={m.head.id} className="check-option">
                  <input
                    type="checkbox"
                    aria-label={`% del total de ${m.head.content.label}`}
                    checked={shares.includes(m.head.id)}
                    onChange={(e) =>
                      setShares(
                        e.target.checked
                          ? [...shares, m.head.id]
                          : shares.filter((id) => id !== m.head.id),
                      )
                    }
                  />
                  % del total de {m.head.content.label}
                </label>
              ))}
            </div>
          )}
        </fieldset>
        <div className="form-footer">
          <Button
            disabled={archived || busy || chosen.length === 0}
            onClick={() => void calculate()}
          >
            {busy ? (
              <LoaderCircle className="spin" size={15} />
            ) : (
              <Calculator size={15} />
            )}
            Calcular
          </Button>
        </div>
      </fieldset>

      {(createPlan.isError || execute.isError) && (
        <p className="auth-error" role="alert">
          {errorMessage(createPlan.error ?? execute.error)}
        </p>
      )}
      {problems.length > 0 && (
        <div
          className="warning-banner"
          role="alert"
          aria-label="Requisitos pendientes"
        >
          <div>
            <strong>El análisis tiene requisitos pendientes</strong>
            <ul>
              {problems.map((problem, index) => (
                <li key={index}>
                  {problemLabels[problem.code]}: {problem.message}
                </li>
              ))}
            </ul>
          </div>
          {problems.some((p) => p.resolve_in === "understanding") && (
            <Button size="sm" variant="outline" onClick={onOpenUnderstanding}>
              Ir a Entendimiento
            </Button>
          )}
        </div>
      )}
      {runId &&
        (run.data?.state === "failed" ? (
          <p className="auth-error" role="alert">
            {run.data.error_code}: {run.data.error_message}
          </p>
        ) : result.data ? (
          <>
            <Results result={result.data} runId={runId} />
            {plan && !archived && (
              <AddToDashboard
                projectId={projectId}
                planRevisionId={plan.id}
                executionId={runId}
                dimensions={dimensions.length}
                grain={!!grain}
                metrics={result.data.metrics.map((m) => ({
                  key: m.key,
                  label: m.label,
                }))}
                suggestedTitle={result.data.metrics
                  .map((m) => m.label)
                  .join(" y ")}
              />
            )}
          </>
        ) : (
          <p className="empty-copy" role="status">
            <LoaderCircle className="spin" size={15} /> Calculando sobre todo el
            dataset…
          </p>
        ))}
      {creating && (
        <MetricDialog
          table={table}
          columns={columns}
          onClose={() => setCreating(false)}
          onSaved={(revision) => {
            setSelected((current) => [...current, revision.id]);
            setCreating(false);
          }}
        />
      )}
    </section>
  );
}

function MetricDialog({
  table,
  columns,
  onClose,
  onSaved,
}: {
  table: { id: string; sha256: string };
  columns: Column[];
  onClose: () => void;
  onSaved: (revision: MetricRevision) => void;
}) {
  const save = useSaveMetric(table.id);
  const [label, setLabel] = useState("");
  const [aggregation, setAggregation] = useState<Aggregation>("sum");
  const [measure, setMeasure] = useState("");
  const [time, setTime] = useState("");
  const [filterColumn, setFilterColumn] = useState("");
  const [operator, setOperator] = useState<keyof typeof OPERATORS>("eq");
  const [values, setValues] = useState("");
  const measured = AGGREGATIONS.find((a) => a.value === aggregation)!.measured;
  const measures = columns.filter(
    (c) => !measured || c.type === "integer" || c.type === "decimal",
  );
  const dates = columns.filter((c) => c.type === "date");
  return (
    <Dialog title="Nueva métrica" onClose={onClose}>
      <div className="metric-form">
        <label>
          Nombre de negocio
          <input
            aria-label="Nombre de negocio"
            value={label}
            placeholder="p. ej. Ingresos"
            onChange={(e) => setLabel(e.target.value)}
          />
        </label>
        <label>
          Agregación
          <select
            aria-label="Agregación"
            value={aggregation}
            onChange={(e) => {
              setAggregation(e.target.value as Aggregation);
              setMeasure("");
            }}
          >
            {AGGREGATIONS.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Columna medida
          <select
            aria-label="Columna medida"
            value={measure}
            onChange={(e) => setMeasure(e.target.value)}
          >
            <option value="">Elige una columna</option>
            {measures.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} · {c.type}
              </option>
            ))}
          </select>
        </label>
        {measured && measures.length === 0 && (
          <small className="muted">
            No hay columnas numéricas: convierte el importe en Limpieza primero.
          </small>
        )}
        <label>
          Fecha de negocio (opcional)
          <select
            aria-label="Fecha de negocio"
            value={time}
            onChange={(e) => setTime(e.target.value)}
          >
            <option value="">Sin fecha</option>
            {dates.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="metric-filter">
          <legend>Filtro de la definición (opcional)</legend>
          <select
            aria-label="Columna del filtro"
            value={filterColumn}
            onChange={(e) => setFilterColumn(e.target.value)}
          >
            <option value="">Sin filtro</option>
            {columns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          {filterColumn && (
            <>
              <select
                aria-label="Operador del filtro"
                value={operator}
                onChange={(e) =>
                  setOperator(e.target.value as keyof typeof OPERATORS)
                }
              >
                {Object.entries(OPERATORS).map(([value, text]) => (
                  <option key={value} value={value}>
                    {text}
                  </option>
                ))}
              </select>
              {!operator.startsWith("is_") && (
                <input
                  aria-label="Valor del filtro"
                  value={values}
                  placeholder={operator === "in" ? "a, b, c" : "valor"}
                  onChange={(e) => setValues(e.target.value)}
                />
              )}
            </>
          )}
        </fieldset>
        <p className="fine-print muted">
          Los nulos de la columna medida se excluyen y se cuentan; nunca se
          tratan como cero.
        </p>
        {save.isError && (
          <p className="auth-error" role="alert">
            {errorMessage(save.error)}
          </p>
        )}
        <div className="form-footer">
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            disabled={!label.trim() || !measure || save.isPending}
            onClick={async () => {
              try {
                const saved = await save.mutateAsync({
                  table_sha256: table.sha256,
                  family_id: null,
                  expected_revision: 0,
                  draft: {
                    label: label.trim(),
                    measure_column_id: measure,
                    aggregation,
                    time_column_id: time || null,
                    null_policy: "exclude",
                    filters: filterColumn
                      ? [
                          {
                            column_id: filterColumn,
                            operator,
                            values: operator.startsWith("is_")
                              ? []
                              : operator === "in"
                                ? values
                                    .split(",")
                                    .map((v) => v.trim())
                                    .filter(Boolean)
                                : [values.trim()],
                          },
                        ]
                      : [],
                  },
                });
                onSaved(saved.revision);
              } catch {
                /* Error visible. */
              }
            }}
          >
            Guardar métrica
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
