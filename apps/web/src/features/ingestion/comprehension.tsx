"use client";

import { useMemo } from "react";
import { Brain, Check, LoaderCircle, X } from "lucide-react";
import type { EChartsCoreOption } from "echarts/core";
import { Chart } from "@/components/ui/chart";
import { errorMessage } from "@/lib/api";
import {
  useJudgeRelationship,
  type ComprehensionView,
  type Verdict,
} from "./api";

type Comprehension = NonNullable<ComprehensionView["comprehension"]>;

const SCALES: Record<string, string> = {
  nominal: "Nominal",
  ordinal: "Ordinal",
  interval: "De intervalo",
  ratio: "De razón",
  identifier: "Identificador",
  text: "Texto libre",
  empty: "Vacía",
};
const ORIGINS: Record<string, string> = {
  ai: "Hipótesis de la IA",
  data: "Detectada en los datos",
  declared: "Declarada en la base",
};
const STATUS: Record<string, string> = {
  confirmed: "Confirmada por los datos",
  not_supported: "Los datos no la respaldan",
  not_testable: "No comprobable",
};
const AI_REASONS: Record<string, string> = {
  disabled: "la IA no está configurada",
  missing_key: "falta la clave de la IA",
  AI_BUDGET_EXCEEDED: "se alcanzó el límite de uso de la IA",
};

/** Matriz simétrica |valor| de la medida principal de cada par (Spearman entre números). */
function heatmap(result: Comprehension): EChartsCoreOption | null {
  const columns = result.matrix_columns;
  if (columns.length < 2) return null;
  const best = new Map<string, { value: number; label: string }>();
  for (const item of result.associations) {
    if (item.measure === "pearson") continue;
    const [a, b] = item.columns;
    const entry = {
      value: Math.abs(Number(item.value)),
      label: `${item.measure} ${item.value}`,
    };
    best.set(`${a}|${b}`, entry);
    best.set(`${b}|${a}`, entry);
  }
  const data: [number, number, number | "-"][] = [];
  columns.forEach((a, i) =>
    columns.forEach((b, j) => {
      const found = i === j ? { value: 1 } : best.get(`${a}|${b}`);
      data.push([j, i, found ? found.value : "-"]);
    }),
  );
  return {
    tooltip: {
      formatter: (p: { value: [number, number, number | "-"] }) => {
        const [j, i, v] = p.value;
        const info = best.get(`${columns[i]}|${columns[j]}`);
        return `${columns[i]} – ${columns[j]}<br/>${
          i === j ? "misma columna" : (info?.label ?? "sin medida")
        }${v === "-" ? "" : ""}`;
      },
    },
    grid: { left: 110, right: 20, top: 10, bottom: 90 },
    xAxis: {
      type: "category",
      data: columns,
      axisLabel: { rotate: 40, fontSize: 11, color: "#94a3b8" },
    },
    yAxis: {
      type: "category",
      data: columns,
      axisLabel: { fontSize: 11, color: "#94a3b8" },
    },
    visualMap: {
      min: 0,
      max: 1,
      show: false,
      inRange: { color: ["#f1f5f9", "#a5b4fc", "#4338ca"] },
    },
    series: [{ type: "heatmap", data, label: { show: false } }],
  };
}

/** Fase 19: entendimiento del negocio con la valoración opcional del usuario. */
export function ComprehensionPanel({
  view,
  versionId,
}: {
  view: ComprehensionView;
  versionId: string;
}) {
  const judge = useJudgeRelationship(versionId);
  const result = view.comprehension;
  const option = useMemo(() => (result ? heatmap(result) : null), [result]);
  if (view.state === "queued" || view.state === "running")
    return (
      <section className="comprehension" aria-label="Entendimiento del negocio">
        <p className="muted" role="status">
          <LoaderCircle className="spin" size={14} /> Entendiendo el negocio
          detrás de los datos…
        </p>
      </section>
    );
  if (!result) return null;
  const verdicts = new Map<string, Verdict>(
    (view.feedback ?? []).map((item) => [item.relationship_key, item.verdict]),
  );
  const meanings = new Map(
    (result.meanings ?? []).map((m) => [m.column, m.meaning]),
  );
  return (
    <section className="comprehension" aria-label="Entendimiento del negocio">
      <header className="section-heading">
        <div>
          <h2>
            <Brain size={18} aria-hidden /> Entendimiento del negocio
          </h2>
          <p>
            La IA sólo vio los nombres de las columnas y un perfil agregado.
            Cada relación se midió sobre todas las filas; una asociación no es
            una causa.
          </p>
        </div>
      </header>
      {result.domain ? (
        <div className="comprehension-domain">
          <span className="badge neutral">Hipótesis de la IA</span>
          <p>{result.domain}</p>
          {(result.entities ?? []).length > 0 && (
            <p className="muted">
              {(result.entities ?? [])
                .map((e) => `${e.name}: ${e.columns.join(", ")}`)
                .join(" · ")}
            </p>
          )}
        </div>
      ) : (
        <p className="muted">
          Sin hipótesis de la IA (
          {AI_REASONS[result.ai_reason ?? ""] ??
            result.ai_reason ??
            result.ai_state}
          ): escalas y relaciones calculadas sólo con los datos.
        </p>
      )}
      <div className="comprehension-grid">
        <div>
          <h3>Columnas y escala de medida</h3>
          <table className="comprehension-table">
            <thead>
              <tr>
                <th>Columna</th>
                <th>Escala</th>
                <th>Significado (IA)</th>
              </tr>
            </thead>
            <tbody>
              {result.scales.map((s) => (
                <tr key={s.column}>
                  <td>{s.column}</td>
                  <td title={s.reason}>
                    {SCALES[s.scale]}
                    {(s.order ?? []).length > 0 && (
                      <small>
                        {" "}
                        ({(s.order ?? []).slice(0, 6).join(" < ")})
                      </small>
                    )}
                  </td>
                  <td>{meanings.get(s.column) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {option && (
          <div>
            <h3>Mapa de asociaciones</h3>
            <Chart
              option={option}
              label="Mapa de calor de asociaciones entre columnas"
              height={Math.max(260, result.matrix_columns.length * 34 + 100)}
            />
          </div>
        )}
      </div>
      {result.relationships.length > 0 && (
        <div className="comprehension-relations">
          <h3>Relaciones</h3>
          <p className="muted">
            Opcional: marca si cada relación te sirve. No cambia los resultados;
            la próxima carga del mismo archivo lo tiene en cuenta.
          </p>
          <ul>
            {result.relationships.map((r) => {
              const verdict = verdicts.get(r.key) ?? r.verdict ?? null;
              return (
                <li
                  key={r.key}
                  className={`relation ${r.status} ${verdict ?? ""}`}
                  aria-label={`Relación ${r.columns[0]} – ${r.columns[1]}`}
                >
                  <div>
                    <strong>
                      {r.columns[0]} – {r.columns[1]}
                    </strong>{" "}
                    <span className="badge neutral">{ORIGINS[r.origin]}</span>{" "}
                    <span className="relation-status">{STATUS[r.status]}</span>
                    {r.hypothesis && <p>{r.hypothesis}</p>}
                    <small>{r.detail}</small>
                  </div>
                  <div
                    className="relation-actions"
                    role="group"
                    aria-label="Valoración"
                  >
                    <button
                      type="button"
                      className="btn btn-sm btn-outline"
                      aria-pressed={verdict === "relevant"}
                      disabled={judge.isPending}
                      onClick={() =>
                        judge.mutate({ key: r.key, verdict: "relevant" })
                      }
                    >
                      <Check size={13} /> Relevante
                    </button>
                    <button
                      type="button"
                      className="btn btn-sm btn-outline"
                      aria-pressed={verdict === "not_relevant"}
                      disabled={judge.isPending}
                      onClick={() =>
                        judge.mutate({ key: r.key, verdict: "not_relevant" })
                      }
                    >
                      <X size={13} /> No relevante
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
          {judge.isError && (
            <p className="field-error" role="alert">
              {errorMessage(judge.error)}
            </p>
          )}
        </div>
      )}
      {(result.questions ?? []).length > 0 && (
        <div className="comprehension-questions">
          <h3>Preguntas de negocio sugeridas</h3>
          <ul>
            {(result.questions ?? []).map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
