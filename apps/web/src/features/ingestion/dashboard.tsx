"use client";

import {
  LayoutDashboard,
  LoaderCircle,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import {
  Chart,
  heatmapOption,
  pieOption,
  seriesOption,
} from "@/components/ui/chart";
import { exactNumber } from "./automatic-analysis";
import { useJudgeFinding } from "./api";
import type { DashboardView, FindingVerdict } from "./api";

type Ready = NonNullable<DashboardView["dashboard"]>;
type Widget = Ready["sections"][number]["widgets"][number];
type Insight = NonNullable<DashboardView["insights"]>[number];
type Result = NonNullable<DashboardView["results"]>[number];

const ROWS = 10;
const TYPES: Record<string, string> = {
  kpi: "Indicador",
  bar: "Barras",
  line: "Líneas",
  heatmap: "Mapa de calor",
  pie: "Circular",
  table: "Tabla",
};

// Las etiquetas vienen del archivo: los tooltips de ECharts nunca se tratan como HTML.
const SAFE = { tooltip: { trigger: "axis", renderMode: "richText" } } as const;

function series(insight?: Insight, result?: Result) {
  if (insight?.chart)
    return insight.chart.points.map((p) => ({
      label: p.label,
      value: Number(p.value ?? 0),
    }));
  return (result?.rows ?? []).map((row) => ({
    label: row.groups[0] ?? "",
    value: Number(row.figures[0]?.value ?? 0),
  }));
}

function Figure({ widget, data }: { widget: Widget; data: Data }) {
  const figure = [
    ...(data.insight?.figures ?? []),
    ...(data.result?.rows.flatMap((row) => row.figures) ?? []),
  ].find((item) => item.evidence_id === widget.evidence_id);
  const unit =
    figure && "unit" in figure && figure.unit === "percent" ? " %" : "";
  return (
    <div className="dashboard-kpi" title={`Evidencia ${widget.evidence_id}`}>
      <span>{widget.title}</span>
      <strong>{figure ? `${exactNumber(figure.value)}${unit}` : "—"}</strong>
    </div>
  );
}

type Data = { insight?: Insight; result?: Result };

function Visual({ widget, data }: { widget: Widget; data: Data }) {
  const { insight, result } = data;
  if (widget.type === "bar" || widget.type === "line") {
    const points = series(insight, result).slice(0, 24);
    return (
      <Chart
        label={widget.title}
        height={220}
        option={{
          ...seriesOption(
            points.map((p) => p.label),
            points.map((p) => p.value),
            widget.type,
          ),
          ...SAFE,
        }}
      />
    );
  }
  if (widget.type === "pie") {
    const points = series(insight, result);
    return (
      <Chart
        label={widget.title}
        height={240}
        option={pieOption(
          points.map((p) => p.label),
          points.map((p) => p.value),
        )}
      />
    );
  }
  if (widget.type === "heatmap" && result) {
    const xs = [...new Set(result.rows.map((row) => row.groups[0]))];
    const ys = [...new Set(result.rows.map((row) => row.groups[1]))];
    return (
      <Chart
        label={widget.title}
        height={Math.max(200, ys.length * 28 + 90)}
        option={heatmapOption(
          xs,
          ys,
          result.rows.map((row) => [
            xs.indexOf(row.groups[0]),
            ys.indexOf(row.groups[1]),
            Number(row.figures[0]?.value ?? 0),
          ]),
        )}
      />
    );
  }
  if (result)
    return (
      <table className="comprehension-table">
        <thead>
          <tr>
            {result.columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.slice(0, ROWS).map((row) => (
            <tr key={row.groups.join("|") || "total"}>
              {row.groups.map((group, index) => (
                <td key={index}>{group}</td>
              ))}
              {row.figures.map((figure) => (
                <td key={figure.evidence_id}>{exactNumber(figure.value)}</td>
              ))}
              <td>{exactNumber(String(row.rows))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  return (
    <dl className="insight-figures">
      {(insight?.figures ?? []).map((figure) => (
        <div key={figure.evidence_id}>
          <dt>{figure.label}</dt>
          <dd>
            {exactNumber(figure.value)}
            {figure.unit === "percent" ? " %" : ""}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Marks({
  item,
  verdict,
  versionId,
  title,
}: {
  item: string;
  verdict?: FindingVerdict;
  versionId: string;
  title: string;
}) {
  const judge = useJudgeFinding(versionId);
  const mark = (next: FindingVerdict) =>
    judge.mutate({ item, verdict: verdict === next ? "none" : next });
  return (
    <div
      className="dashboard-marks"
      role="group"
      aria-label={`Valorar ${title}`}
    >
      <button
        type="button"
        className="btn btn-sm btn-outline"
        aria-pressed={verdict === "keep"}
        disabled={judge.isPending}
        onClick={() => mark("keep")}
      >
        <ThumbsUp size={13} aria-hidden /> Sí va
      </button>
      <button
        type="button"
        className="btn btn-sm btn-outline"
        aria-pressed={verdict === "drop"}
        disabled={judge.isPending}
        onClick={() => mark("drop")}
      >
        <ThumbsDown size={13} aria-hidden /> No va
      </button>
    </div>
  );
}

/** Fase 21: dashboard que la IA (o las reglas) diseñó para estos datos; las cifras son las
 * publicadas por el motor y cada una conserva su evidencia. */
export function DashboardPanel({
  view,
  versionId,
}: {
  view: DashboardView;
  versionId: string;
}) {
  if (view.state === "queued" || view.state === "running")
    return (
      <section className="dashboard-adapted" aria-label="Dashboard adaptado">
        <p className="muted" role="status">
          <LoaderCircle className="spin" size={14} /> Diseñando el dashboard
          para estos datos…
        </p>
      </section>
    );
  const dashboard = view.dashboard;
  const arrangement = view.arrangement;
  if (!dashboard || !arrangement) return null;
  const insights = new Map(
    (view.insights ?? []).map((i) => [`insight:${i.id}`, i]),
  );
  const results = new Map(
    (view.results ?? []).map((r) => [`exploration:${r.key}`, r]),
  );
  const verdicts = new Map(
    (view.feedback ?? []).map((f) => [f.item, f.verdict]),
  );
  const data = (item: string): Data => ({
    insight: insights.get(item),
    result: results.get(item),
  });
  const title = (item: string) =>
    insights.get(item)?.title ?? results.get(item)?.title ?? item;
  const rejected = (dashboard.decisions ?? []).filter(
    (d) => d.status === "rejected",
  );
  return (
    <section className="dashboard-adapted" aria-label="Dashboard adaptado">
      <header className="section-heading">
        <div>
          <h2>
            <LayoutDashboard size={18} aria-hidden /> {dashboard.title}
          </h2>
          <p>
            {dashboard.designed_by === "ai"
              ? "La IA eligió las secciones, el orden y el tipo de gráfico sin ver cifras; Python validó cada elección."
              : "Diseñado por reglas a partir de la forma de cada resultado."}{" "}
            Marca «Sí va» para fijar un hallazgo arriba o «No va» para
            apartarlo; el informe en PDF sigue ese orden.
          </p>
        </div>
        <span className="badge neutral">
          {dashboard.designed_by === "ai"
            ? "Diseñado por la IA"
            : "Diseñado por reglas"}
        </span>
      </header>
      {arrangement.sections.map((section, index) => (
        <div
          key={`${section.title}-${index}`}
          className="dashboard-section"
          role="group"
          aria-label={section.title}
        >
          <h3>{section.title}</h3>
          {section.intro && <p className="muted">{section.intro}</p>}
          <div className="dashboard-kpis">
            {section.widgets
              .filter((w) => w.type === "kpi")
              .map((widget) => (
                <Figure
                  key={`${widget.item}-${widget.evidence_id}`}
                  widget={widget}
                  data={data(widget.item)}
                />
              ))}
          </div>
          <div className="dashboard-grid">
            {section.widgets
              .filter((w) => w.type !== "kpi")
              .map((widget) => {
                const found = data(widget.item);
                return (
                  <article
                    key={`${widget.item}-${widget.type}`}
                    className={`dashboard-card ${widget.type === "heatmap" || widget.type === "table" ? "wide" : ""}`}
                    aria-label={widget.title}
                  >
                    <header>
                      <h4>{widget.title}</h4>
                      <span className="badge neutral">
                        {TYPES[widget.type]}
                      </span>
                    </header>
                    {found.insight && <p>{found.insight.statement}</p>}
                    {found.result?.reason && <p>{found.result.reason}</p>}
                    <Visual widget={widget} data={found} />
                    <footer>
                      <small className="muted">
                        {found.insight?.coverage ?? found.result?.method}
                      </small>
                      <Marks
                        item={widget.item}
                        verdict={verdicts.get(widget.item)}
                        versionId={versionId}
                        title={widget.title}
                      />
                    </footer>
                  </article>
                );
              })}
          </div>
        </div>
      ))}
      {arrangement.hidden.length > 0 && (
        <details>
          <summary>Descartados por ti ({arrangement.hidden.length})</summary>
          <ul className="dashboard-hidden">
            {arrangement.hidden.map((item) => (
              <li key={item}>
                <span>{title(item)}</span>
                <Marks
                  item={item}
                  verdict="drop"
                  versionId={versionId}
                  title={title(item)}
                />
              </li>
            ))}
          </ul>
        </details>
      )}
      {rejected.length > 0 && (
        <details>
          <summary>
            Elecciones de diseño rechazadas por la validación ({rejected.length}
            )
          </summary>
          <ul>
            {rejected.map((decision, index) => (
              <li key={index}>
                {TYPES[decision.type] ?? decision.type} · {title(decision.item)}{" "}
                — {decision.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
