"use client";
import { useState, type ReactNode } from "react";
import { Info, ShieldCheck } from "lucide-react";
import type { components } from "@dataflow/api-client";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import { number } from "@/lib/utils";
import { useEvidence, type AnalysisResult } from "./api";
import { CsvExport } from "@/features/reports/csv-export";
import {
  aggregationLabel,
  BASE_STATUS,
  BASE_STATUS_HELP,
  CELL_LABELS,
  comparisonLabel,
  GRAINS,
  OPERATORS,
  SHARE_STATUS,
  TIE_HELP,
} from "./labels";

type Row = AnalysisResult["rows"][number];
type RowV2 = components["schemas"]["ResultRowV2"];
type Definition = AnalysisResult["metrics"][number];

const CHANGE_HELP: Record<string, string> = {
  base_missing: "Sin base: no hay variación.",
  current_missing: "El grupo no tiene filas para esta métrica en el periodo.",
  base_zero: "La base es 0: hay variación absoluta, pero no porcentual.",
};

function Cell({
  label,
  text,
  help,
  onOpen,
}: {
  label: string;
  text: ReactNode;
  help?: string;
  onOpen: () => void;
}) {
  return (
    <td className="metric-cell">
      <button
        className="text-link"
        aria-label={label}
        title={help || undefined}
        onClick={onOpen}
      >
        {text}
      </button>
    </td>
  );
}

export function Results({
  result,
  runId,
}: {
  result: AnalysisResult;
  runId: string;
}) {
  const [cell, setCell] = useState<string | null>(null);
  // @3 tiene las mismas columnas derivadas que @2.
  const v2 = result.operation === "analytics.query@1" ? null : result;
  const unit = (m: Definition) => m.currency ?? m.unit ?? null;
  const shared = new Set(v2?.shares.map((s) => s.metric) ?? []);
  const ranking = v2?.ranking ?? null;
  const rankedBy = ranking
    ? result.metrics.find((m) => m.key === ranking.metric)
    : undefined;
  const group = (row: Row) =>
    result.dimensions.map((d) => row.labels[d.key]).join(" ");
  const tolerance = v2?.shares.reduce(
    (max, s) => (Number(s.tolerance) > Number(max) ? s.tolerance : max),
    "0",
  );
  return (
    <div className="analysis-results">
      <div className="table-scroll bordered">
        <table aria-label="Resultado del análisis">
          <thead>
            <tr>
              {ranking && <th>Posición</th>}
              {result.dimensions.map((d) => (
                <th key={d.key}>
                  {d.name}
                  {d.time_grain
                    ? ` (${GRAINS.find((g) => g.value === d.time_grain)?.label.toLowerCase()})`
                    : ""}
                </th>
              ))}
              {result.metrics.map((m) => (
                <MetricHeaders
                  key={m.key}
                  label={`${m.label}${unit(m) ? ` (${unit(m)})` : ""}`}
                  prefix={result.metrics.length > 1 ? `${m.label} · ` : ""}
                  comparisons={v2?.comparisons ?? []}
                  share={shared.has(m.key)}
                />
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, index) => {
              const extended = v2 ? (row as RowV2) : null;
              return (
                <tr key={index}>
                  {extended?.rank && (
                    <Cell
                      label={`Posición de ${group(row)}`}
                      help={
                        extended.rank.tied_with_previous ? TIE_HELP : undefined
                      }
                      text={
                        <>
                          {extended.rank.position}
                          {extended.rank.tied_with_previous && (
                            <span className="tie-mark" aria-hidden="true">
                              {" "}
                              =
                            </span>
                          )}
                        </>
                      }
                      onOpen={() => setCell(extended.rank!.evidence)}
                    />
                  )}
                  {result.dimensions.map((d) => (
                    <td key={d.key}>{row.labels[d.key]}</td>
                  ))}
                  {result.metrics.map((m) => (
                    <MetricCells
                      key={m.key}
                      metric={m}
                      row={row}
                      extended={extended}
                      comparisons={v2?.comparisons ?? []}
                      share={shared.has(m.key)}
                      group={group(row)}
                      onOpen={setCell}
                    />
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="results-footer">
        <p className="fine-print muted">
          {result.row_count} fila(s) · selecciona una cifra para ver de dónde
          sale.
        </p>
        <CsvExport
          href={`/api/v1/executions/${runId}/analysis.csv`}
          label="Exportar resultado"
        />
      </div>
      {ranking && rankedBy && (
        <p className="fine-print muted" data-testid="ranking-note">
          Top {ranking.top_n} por {rankedBy.label} (
          {ranking.direction === "desc"
            ? "de mayor a menor"
            : "de menor a mayor"}
          {result.dimensions.some((d) => d.key === "period")
            ? ", en cada periodo"
            : ""}
          ) · {ranking.hidden_groups} grupo(s) oculto(s). Un «=» indica el mismo
          valor que la posición anterior: el orden lo decide el desempate por
          dimensiones.
        </p>
      )}
      {v2 && v2.shares.length > 0 && (
        <p className="fine-print muted" data-testid="share-note">
          El % del total se calcula sobre todos los grupos de cada periodo,
          incluidos los que no se muestran. Cada porcentaje se redondea por
          separado: la suma puede desviarse hasta {tolerance} puntos.
          {v2.shares.some((s) => s.mixed_signs)
            ? " Hay valores negativos: un porcentaje puede ser negativo o superar 100."
            : ""}
        </p>
      )}
      {cell && (
        <Provenance
          runId={runId}
          evidenceId={cell}
          onClose={() => setCell(null)}
        />
      )}
    </div>
  );
}

/** Con varias métricas, las columnas derivadas llevan el nombre de su métrica. */
function MetricHeaders({
  label,
  prefix,
  comparisons,
  share,
}: {
  label: string;
  prefix: string;
  comparisons: string[];
  share: boolean;
}) {
  return (
    <>
      <th>{label}</th>
      {comparisons.map((kind) => (
        <ComparisonHeaders key={kind} kind={kind} prefix={prefix} />
      ))}
      {share && <th>{prefix}% del total</th>}
    </>
  );
}

function ComparisonHeaders({ kind, prefix }: { kind: string; prefix: string }) {
  const name = comparisonLabel(kind);
  return (
    <>
      <th>
        {prefix}
        {prefix ? name.toLowerCase() : name}
      </th>
      <th>{prefix}Variación</th>
      <th>{prefix}Variación %</th>
    </>
  );
}

function MetricCells({
  metric,
  row,
  extended,
  comparisons,
  share,
  group,
  onOpen,
}: {
  metric: Definition;
  row: Row;
  extended: RowV2 | null;
  comparisons: string[];
  share: boolean;
  group: string;
  onOpen: (evidence: string) => void;
}) {
  const key = metric.key;
  const shareCell = extended?.share?.[key];
  return (
    <>
      <Cell
        label={`De dónde sale ${metric.label} ${group}`}
        text={row.values[key] ?? "sin filas"}
        onOpen={() => onOpen(row.evidence[key])}
      />
      {comparisons.map((kind) => {
        const c = extended?.comparisons?.[key]?.[kind as "previous_period"];
        if (!c) return null;
        const name = comparisonLabel(kind).toLowerCase();
        return [
          <Cell
            key={`${kind}-base`}
            label={`${metric.label} ${name} ${group}`}
            help={BASE_STATUS_HELP[c.base_status]}
            text={c.base ?? BASE_STATUS[c.base_status] ?? c.base_status}
            onOpen={() => onOpen(c.evidence.base)}
          />,
          <Cell
            key={`${kind}-change`}
            label={`Variación de ${metric.label} frente al ${name} ${group}`}
            help={CHANGE_HELP[c.change_status]}
            text={c.change ?? "—"}
            onOpen={() => onOpen(c.evidence.change)}
          />,
          <Cell
            key={`${kind}-pct`}
            label={`Variación % de ${metric.label} frente al ${name} ${group}`}
            help={CHANGE_HELP[c.change_status]}
            text={c.change_pct !== null ? `${c.change_pct} %` : "—"}
            onOpen={() => onOpen(c.evidence.change_pct)}
          />,
        ];
      })}
      {share && shareCell && (
        <Cell
          label={`% del total de ${metric.label} ${group}`}
          text={
            shareCell.value !== null
              ? `${shareCell.value} %`
              : SHARE_STATUS[shareCell.status]
          }
          onOpen={() => onOpen(shareCell.evidence)}
        />
      )}
      {share && !shareCell && <td />}
    </>
  );
}

export function Provenance({
  runId,
  evidenceId,
  onClose,
}: {
  runId: string;
  evidenceId: string;
  onClose: () => void;
}) {
  const evidence = useEvidence(runId, evidenceId);
  const data = evidence.data;
  const reference = data?.reference;
  const cell = reference?.cell ?? "value";
  const definition = data?.definition;
  const unit = definition?.currency ?? definition?.unit ?? "";
  const suffix =
    cell === "rank"
      ? ""
      : cell === "change_pct" || cell === "share_of_total"
        ? "%"
        : unit;
  const detail = (reference?.detail ?? {}) as Record<string, unknown>;
  const kind = typeof detail.comparison === "string" ? detail.comparison : null;
  const baseCounts =
    kind && definition && "base_counts" in definition
      ? definition.base_counts?.[kind as "previous_period"]
      : undefined;
  return (
    <Dialog title="De dónde sale este número" onClose={onClose}>
      {evidence.isPending ? (
        <p className="empty-copy">Cargando la evidencia…</p>
      ) : evidence.isError || !data || !reference || !definition ? (
        <p className="auth-error" role="alert">
          {errorMessage(evidence.error)}
        </p>
      ) : (
        <dl className="definition-list" aria-label="Procedencia de la cifra">
          <dt>Cifra</dt>
          <dd data-testid="evidence-value">
            {data.value ?? "sin filas"} {data.value !== null ? suffix : ""}
          </dd>
          {cell !== "value" && (
            <>
              <dt>Qué es</dt>
              <dd data-testid="evidence-cell">
                {CELL_LABELS[cell] ?? cell}
                {kind && cell.startsWith("change")
                  ? ` frente al ${comparisonLabel(kind).toLowerCase()}`
                  : ""}{" "}
                · valor del grupo {data.metric_value ?? "sin filas"} {unit}
              </dd>
            </>
          )}
          <dt>Métrica</dt>
          <dd>
            {definition.label} · {aggregationLabel(definition.aggregation)} de{" "}
            {definition.measure_column} · revisión {definition.revision}
          </dd>
          <dt>Grupo</dt>
          <dd>
            {Object.values(data.labels).filter(Boolean).join(" · ") || "Total"}
          </dd>
          {data.comparison && (
            <>
              <dt>Periodo base</dt>
              <dd data-testid="evidence-base">
                {data.comparison.base_label ??
                  BASE_STATUS[data.comparison.base_status]}{" "}
                · base {data.comparison.base ?? "sin valor"}
                {data.comparison.base_status !== "available"
                  ? ` (${BASE_STATUS_HELP[data.comparison.base_status]})`
                  : ""}
              </dd>
              {cell === "change_pct" && (
                <>
                  <dt>Cálculo</dt>
                  <dd>
                    (valor − base) / |base| × 100, redondeo HALF_EVEN a{" "}
                    {String(detail.change_scale)} decimales
                  </dd>
                </>
              )}
            </>
          )}
          {data.share && data.share_total && (
            <>
              <dt>Total</dt>
              <dd data-testid="evidence-share-total">
                {data.share_total.total} {unit} en {data.share_total.groups}{" "}
                grupo(s), incluidos los no visibles · redondeo HALF_EVEN a{" "}
                {String(detail.share_scale)} decimales; la suma puede desviarse
                hasta {data.share_total.tolerance} puntos
              </dd>
            </>
          )}
          {data.rank && data.ranking && (
            <>
              <dt>Ranking</dt>
              <dd data-testid="evidence-rank">
                Top {data.ranking.top_n} ·{" "}
                {data.ranking.direction === "desc"
                  ? "de mayor a menor"
                  : "de menor a mayor"}{" "}
                · {data.ranking.hidden_groups} grupo(s) oculto(s)
                {data.rank.tied_with_previous ? `. ${TIE_HELP}` : ""}
              </dd>
            </>
          )}
          <dt>Filtros</dt>
          <dd>
            {[...reference.metric_filters, ...reference.query_filters]
              .map(
                (f) =>
                  `${f.column_id.slice(0, 8)} ${OPERATORS[f.operator as keyof typeof OPERATORS] ?? f.operator} ${(f.values ?? []).join(", ")}`,
              )
              .join("; ") || "Ninguno"}
            {reference.time_range
              ? ` · periodo ${reference.time_range.start ?? "…"} – ${reference.time_range.end ?? "…"}`
              : ""}
          </dd>
          <dt>Nulos</dt>
          <dd>Excluidos (no cuentan como cero)</dd>
          <dt>Filas</dt>
          <dd data-testid="evidence-counts">
            {number(definition.counts.input_rows)} de entrada ·{" "}
            {number(definition.counts.excluded_by_filters)} excluidas por
            filtros · {number(definition.counts.excluded_by_nulls)} excluidas
            por nulos · {number(definition.counts.included_rows)} incluidas
          </dd>
          {baseCounts && (
            <>
              <dt>Filas de la base</dt>
              <dd data-testid="evidence-base-counts">
                {number(baseCounts.input_rows)} de entrada ·{" "}
                {number(baseCounts.excluded_by_filters)} excluidas por filtros ·{" "}
                {number(baseCounts.outside_base_periods)} fuera de los periodos
                base · {number(baseCounts.excluded_by_nulls)} excluidas por
                nulos · {number(baseCounts.included_rows)} incluidas
              </dd>
            </>
          )}
          <dt>Versión de datos</dt>
          <dd className="mono">
            versión {reference.input.version_id.slice(0, 8)} · tabla{" "}
            {reference.input.artifact_sha256.slice(0, 16)}…
          </dd>
          <dt>Revisión semántica</dt>
          <dd>
            {reference.semantic_ref
              ? `Revisión ${String(reference.semantic_ref.revision)}`
              : "Ninguna"}
          </dd>
          <dt>Evidencia</dt>
          <dd className="mono" title={reference.evidence_id}>
            {reference.evidence_id.slice(0, 24)}…
          </dd>
        </dl>
      )}
      <p className="fine-print muted">
        <Info size={13} /> El identificador de evidencia es estable: el mismo
        cálculo sobre los mismos datos produce la misma referencia.
      </p>
      <div className="form-footer">
        <span className="badge calculated">
          <ShieldCheck size={13} /> Calculado, no estimado
        </span>
      </div>
    </Dialog>
  );
}
