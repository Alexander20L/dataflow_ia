"use client";

import { Chart, seriesOption } from "@/components/ui/chart";
import { capDecimals, capDecimalsInText } from "@/lib/numbers";
import type { AutomaticAnalysis } from "./api";

export type Insight = AutomaticAnalysis["insights"][number];

/** Cifra del servidor con 3 decimales como mucho (`capDecimals`), sin ceros finales. */
export function exactNumber(raw: string | null | undefined) {
  if (raw == null) return "—";
  const value = capDecimals(raw);
  const negative = value.startsWith("-");
  const [integer, fraction] = (negative ? value.slice(1) : value).split(".");
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const decimal = fraction?.replace(/0+$/, "");
  return `${negative ? "-" : ""}${decimal ? `${grouped},${decimal}` : grouped}`;
}

export function InsightCard({
  insight,
  badge,
}: {
  insight: Insight;
  badge?: string;
}) {
  return (
    <article className="automatic-insight" aria-label={insight.title}>
      {badge && <span className="insight-badge">{badge}</span>}
      <h3>{insight.title}</h3>
      <p>{capDecimalsInText(insight.statement)}</p>
      {insight.figures.length > 0 && (
        <dl className="insight-figures">
          {insight.figures.map((figure) => (
            <div key={figure.evidence_id}>
              <dt>{figure.label}</dt>
              <dd>
                {exactNumber(figure.value)}
                {figure.unit === "percent" ? " %" : ""}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {insight.chart && insight.chart.points.length > 0 && (
        <Chart
          label={insight.chart.title}
          option={{
            ...seriesOption(
              insight.chart.points.map((point) => point.label),
              insight.chart.points.map((point) => Number(point.value ?? 0)),
              insight.chart.type,
            ),
            // Las etiquetas proceden del archivo: nunca tratarlas como HTML.
            tooltip: { trigger: "axis", renderMode: "richText" },
          }}
        />
      )}
      <p className="muted">{insight.coverage}</p>
      {(insight.notes ?? []).length > 0 && (
        <ul className="muted">
          {(insight.notes ?? []).map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </article>
  );
}

export function AutomaticAnalysisView({
  analysis,
}: {
  analysis: AutomaticAnalysis;
}) {
  const { plan } = analysis;
  return (
    <section
      className="automatic-analysis"
      aria-label="Hallazgos del análisis automático"
    >
      <header className="section-heading">
        <div>
          <h2>Hallazgos</h2>
          <p>
            Análisis elegidos automáticamente según los datos, con cifras
            exactas y su evidencia. Ninguna cifra sale de la IA.
          </p>
        </div>
      </header>
      {analysis.insights.length ? (
        <div className="automatic-insights">
          {analysis.insights.map((insight) => (
            <InsightCard key={insight.id} insight={insight} />
          ))}
        </div>
      ) : (
        <p>
          No hay hallazgos sustentables con estos datos: se muestra sólo la
          descripción del archivo.
        </p>
      )}
      {plan.omitted.length > 0 && (
        <details aria-label="Análisis omitidos">
          <summary>Análisis omitidos · {plan.omitted.length}</summary>
          <ul>
            {plan.omitted.map((item) => (
              <li key={item.id}>
                <strong>{item.title}</strong>: {item.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
      <details>
        <summary>Cómo se eligieron los análisis</summary>
        <ul>
          {plan.accepted.map((item) => (
            <li key={item.id}>
              <strong>{item.title}</strong>: {item.reason}
            </li>
          ))}
        </ul>
        <ul>
          {analysis.limitations.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
        <p className="mono">
          Reglas: {plan.rules_version} · {analysis.rules_version} · como máximo{" "}
          {plan.max_analyses} análisis por carga.
        </p>
      </details>
    </section>
  );
}
