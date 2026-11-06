"use client";
import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  LoaderCircle,
  Trash2,
} from "lucide-react";
import type { EChartsCoreOption } from "echarts/core";
import { Button } from "@/components/ui/button";
import { Chart, seriesOption } from "@/components/ui/chart";
import { errorMessage } from "@/lib/api";
import {
  useAnalysisResult,
  type AnalysisResult,
} from "@/features/analytics/api";
import { Provenance, Results } from "@/features/analytics/results";
import {
  SIZE_LABELS,
  VIEW_LABELS,
  type Card,
  type CardSize,
  type CardState,
  type GlobalFilter,
} from "./api";

const STATUS_LABELS: Record<CardState["status"], string> = {
  ready: "",
  pending: "Calculando…",
  failed: "Ejecución fallida",
  not_executed: "Sin calcular",
  insufficient_data: "Datos insuficientes",
  semantic_requirement_missing: "Requisito semántico pendiente",
  invalid_plan: "Análisis no válido para esta versión",
};

type Row = AnalysisResult["rows"][number];

/** Filas visibles: los filtros aplicables ocultan filas; no recalculan nada. */
export function visibleRows(
  result: AnalysisResult,
  filters: GlobalFilter[],
  state: CardState,
): Row[] {
  const applicable = filters.filter(
    (f) => state.filters.find((a) => a.column_id === f.column_id)?.applicable,
  );
  return result.rows.filter((row) =>
    applicable.every((f) => {
      const dimension = row.key.dimensions as {
        column_id: string;
        value: unknown;
      }[];
      const value = dimension.find((d) => d.column_id === f.column_id)?.value;
      return typeof value === "string" && f.values.includes(value);
    }),
  );
}

export function DashboardCard({
  card,
  state,
  filters,
  columnNames,
  editable,
  first,
  last,
  onMove,
  onResize,
  onRemove,
}: {
  card: Card;
  state: CardState | undefined;
  filters: GlobalFilter[];
  columnNames: Map<string, string>;
  editable: boolean;
  first: boolean;
  last: boolean;
  onMove: (delta: -1 | 1) => void;
  onResize: (size: CardSize) => void;
  onRemove: () => void;
}) {
  const ready = state?.status === "ready";
  const result = useAnalysisResult(card.execution_id ?? null, ready);
  const size = card.size ?? "medium";
  const notApplicable = state
    ? filters.filter(
        (f) =>
          !state.filters.find((a) => a.column_id === f.column_id)?.applicable,
      )
    : [];
  return (
    <article
      className={`dashboard-card size-${size}`}
      aria-label={`Tarjeta ${card.title}`}
    >
      <header className="dashboard-card-head">
        <div>
          <h4>{card.title}</h4>
          {state && (
            <small className="muted" data-testid="card-meta">
              v{state.version_number}
              {state.executed_at
                ? ` · ${new Date(state.executed_at).toLocaleString("es-ES")}`
                : ""}{" "}
              · {VIEW_LABELS[card.view]}
            </small>
          )}
        </div>
        {editable && (
          <div className="card-tools">
            <Button
              size="sm"
              variant="ghost"
              aria-label={`Mover ${card.title} antes`}
              disabled={first}
              onClick={() => onMove(-1)}
            >
              <ArrowLeft size={14} />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              aria-label={`Mover ${card.title} después`}
              disabled={last}
              onClick={() => onMove(1)}
            >
              <ArrowRight size={14} />
            </Button>
            <select
              aria-label={`Tamaño de ${card.title}`}
              value={size}
              onChange={(e) => onResize(e.target.value as CardSize)}
            >
              {Object.entries(SIZE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              variant="ghost"
              aria-label={`Quitar ${card.title}`}
              onClick={onRemove}
            >
              <Trash2 size={14} />
            </Button>
          </div>
        )}
      </header>
      {notApplicable.length > 0 && (
        <p className="fine-print muted" data-testid="filter-not-applicable">
          Filtro no aplicable:{" "}
          {notApplicable
            .map((f) => columnNames.get(f.column_id) ?? "dimensión")
            .join(", ")}{" "}
          (la consulta no agrupa por esa dimensión).
        </p>
      )}
      {!state ? (
        <p className="empty-copy">Cargando…</p>
      ) : state.status === "pending" ? (
        <p className="empty-copy" role="status">
          <LoaderCircle className="spin" size={14} /> Calculando sobre la
          versión {state.version_number}…
        </p>
      ) : state.status !== "ready" ? (
        <div className="card-problem" role="alert">
          <AlertTriangle size={15} />
          <div>
            <strong>{STATUS_LABELS[state.status]}</strong>
            {state.message && <p className="fine-print">{state.message}</p>}
          </div>
        </div>
      ) : result.isError ? (
        <p className="auth-error" role="alert">
          {errorMessage(result.error)}
        </p>
      ) : !result.data || !card.execution_id ? (
        <p className="empty-copy">Cargando el resultado…</p>
      ) : (
        <CardBody
          card={card}
          result={result.data}
          runId={card.execution_id}
          rows={visibleRows(result.data, filters, state)}
        />
      )}
    </article>
  );
}

function CardBody({
  card,
  result,
  runId,
  rows,
}: {
  card: Card;
  result: AnalysisResult;
  runId: string;
  rows: Row[];
}) {
  const [evidence, setEvidence] = useState<string | null>(null);
  const key = card.metric ?? "m0";
  const metric = result.metrics.find((m) => m.key === key);
  const unit = metric?.currency ?? metric?.unit ?? "";
  const label = (row: Row) =>
    result.dimensions.map((d) => row.labels[d.key]).join(" · ") || "Total";
  const option = useMemo(
    () => chartOption(card, result, rows, key),
    [card, result, rows, key],
  );
  if (rows.length === 0)
    return (
      <p className="empty-copy">
        Ninguna fila cumple los filtros del dashboard.
      </p>
    );
  return (
    <>
      {card.view === "kpi" && (
        <button
          className="kpi-value text-link"
          aria-label={`De dónde sale ${card.title}`}
          onClick={() => setEvidence(rows[0].evidence[key])}
        >
          {rows[0].values[key] ?? "sin filas"} <small>{unit}</small>
        </button>
      )}
      {card.view === "table" && (
        <Results
          result={{ ...result, rows, row_count: rows.length } as AnalysisResult}
          runId={runId}
        />
      )}
      {(card.view === "bar" || card.view === "line") && option && (
        <>
          <Chart
            option={option}
            label={`${card.title}: ${metric?.label ?? ""}`}
            height={card.size === "small" ? 180 : 240}
          />
          <details className="chart-figures">
            <summary>Ver cifras y su procedencia</summary>
            <ul>
              {rows.map((row, index) => (
                <li key={index}>
                  <button
                    className="text-link"
                    aria-label={`De dónde sale ${card.title} ${label(row)}`}
                    onClick={() => setEvidence(row.evidence[key])}
                  >
                    {label(row)}: {row.values[key] ?? "sin filas"} {unit}
                  </button>
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
      {evidence && (
        <Provenance
          runId={runId}
          evidenceId={evidence}
          onClose={() => setEvidence(null)}
        />
      )}
    </>
  );
}

/** Gráfico de sólo lectura: las cifras exactas están en la lista y en su procedencia. */
function chartOption(
  card: Card,
  result: AnalysisResult,
  rows: Row[],
  key: string,
): EChartsCoreOption | null {
  if (card.view !== "bar" && card.view !== "line") return null;
  const value = (row: Row) => Number(row.values[key] ?? Number.NaN);
  const dims = result.dimensions.filter((d) => d.key !== "period");
  const hasPeriod = result.dimensions.some((d) => d.key === "period");
  if (card.view === "bar" || dims.length === 0) {
    const axis = hasPeriod ? "period" : (dims[0]?.key ?? "period");
    return seriesOption(
      rows.map((row) => row.labels[axis] ?? ""),
      rows.map(value),
      card.view,
    );
  }
  // Líneas con dimensiones: una serie por combinación de dimensiones.
  const periods = [...new Set(rows.map((row) => row.labels.period ?? ""))];
  const series = new Map<string, Map<string, number>>();
  for (const row of rows) {
    const name = dims.map((d) => row.labels[d.key]).join(" · ");
    if (!series.has(name)) series.set(name, new Map());
    series.get(name)!.set(row.labels.period ?? "", value(row));
  }
  const base = seriesOption(periods, [], "line") as Record<string, unknown>;
  return {
    ...base,
    legend: { bottom: 0, textStyle: { color: "#94a3b8" } },
    series: [...series.entries()].map(([name, points]) => ({
      name,
      type: "line",
      smooth: true,
      data: periods.map((p) => points.get(p) ?? null),
    })),
  };
}
