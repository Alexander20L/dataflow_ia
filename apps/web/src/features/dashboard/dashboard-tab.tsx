"use client";

import { useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Eye,
  Filter,
  LayoutDashboard,
  LoaderCircle,
  Pencil,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Chart,
  heatmapOption,
  pieOption,
  scatterOption,
  seriesOption,
} from "@/components/ui/chart";
import { errorMessage } from "@/lib/api";
import { capDecimalsInText } from "@/lib/numbers";
import { exactNumber } from "@/features/ingestion/automatic-analysis";
import {
  useDashboardFilter,
  useDashboardView,
  useJudgeFinding,
  useSaveCustomization,
  type CustomSection,
  type Dashboard,
  type DashboardItem,
  type DashboardView,
  type FilterRequest,
  type FilterResult,
  type FindingVerdict,
  type Indicator,
  type Insight,
  type Result,
  type Trace,
} from "./api";

const ROWS = 10;
const BARS = 12;
const TYPES: Record<string, string> = {
  kpi: "Indicador",
  bar: "Barras",
  line: "Líneas",
  heatmap: "Mapa de calor",
  pie: "Circular",
  table: "Tabla",
  histogram: "Histograma",
  scatter: "Dispersión",
};
const SOURCES: Record<Trace["source"], string> = {
  investigation: "Investigación",
  analysis: "Análisis automático",
  dashboard: "Cálculo del dashboard",
};
const CLASSES: Record<string, string> = {
  relevant: "Hallazgo relevante",
  secondary: "Hallazgo secundario",
};
// Las etiquetas vienen del archivo: los tooltips de ECharts nunca se tratan como HTML.
const SAFE = { tooltip: { trigger: "axis", renderMode: "richText" } } as const;

type Widget = {
  type: string;
  item: string;
  title: string;
  evidence_id?: string | null;
};
type Section = { title: string; intro?: string | null; widgets: Widget[] };
type Data = { insight?: Insight; result?: Result; reason?: string | null };

function number(value: string | null | undefined, unit?: string | null) {
  return `${exactNumber(value)}${unit ? ` ${unit}` : ""}`;
}

function points(data: Data) {
  if (data.insight?.chart)
    return data.insight.chart.points.map((p) => ({
      label: p.label,
      value: Number(p.value ?? 0),
    }));
  return (data.result?.rows ?? []).map((row) => ({
    label: row.groups[0] ?? "",
    value: Number(row.figures[0]?.value ?? 0),
  }));
}

/** El origen reproducible de un gráfico o indicador: de qué investigación o cálculo sale y
 * con qué parámetros. */
export function Origin({ trace }: { trace?: Trace | null }) {
  if (!trace) return null;
  const rows =
    trace.rows == null
      ? null
      : trace.total_rows
        ? `${exactNumber(String(trace.rows))} de ${exactNumber(String(trace.total_rows))}`
        : exactNumber(String(trace.rows));
  const entries: [string, string | null | undefined][] = [
    ["Procedencia", SOURCES[trace.source]],
    [
      "Investigación relacionada",
      trace.investigation
        ? `${trace.investigation} · ${trace.question ?? ""}`
        : null,
    ],
    ["Operación", trace.operation],
    ["Columnas", (trace.columns ?? []).join(", ") || null],
    ["Columna temporal", (trace.period_columns ?? []).join(" y ") || null],
    ["Medida", trace.measure],
    ["Agrupación", (trace.grouping ?? []).join(" y ") || null],
    ["Agregación", trace.aggregation],
    ["Registros utilizados", rows],
    ["Filtros aplicados", (trace.filters ?? []).join(" · ") || "ninguno"],
    ["Método", trace.method],
  ];
  return (
    <details className="dashboard-origin">
      <summary>Origen</summary>
      <dl>
        {entries
          .filter(([, value]) => value)
          .map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
      </dl>
    </details>
  );
}

function KpiCard({
  indicator,
  title,
  onOpenRecords,
}: {
  indicator: Indicator;
  title: string;
  onOpenRecords?: () => void;
}) {
  const compared = indicator.comparison;
  const change = compared?.change ? Number(compared.change) : null;
  return (
    <article
      className="dashboard-kpi"
      aria-label={title}
      title={`Evidencia ${indicator.evidence_id}`}
    >
      <span>{title}</span>
      <strong>{number(indicator.value, indicator.unit)}</strong>
      {indicator.highlight && (
        <em className="dashboard-highlight">{indicator.highlight}</em>
      )}
      <small className="muted">{indicator.reference}</small>
      {compared && (
        <small
          className={
            change == null ? "muted" : change >= 0 ? "kpi-up" : "kpi-down"
          }
        >
          {compared.label}: {change != null && change > 0 ? "+" : ""}
          {number(compared.change, indicator.unit)}
          {compared.change_percent
            ? ` (${Number(compared.change_percent) > 0 ? "+" : ""}${exactNumber(compared.change_percent)} %)`
            : ""}
        </small>
      )}
      <Origin trace={indicator.trace} />
      {onOpenRecords && (
        <button type="button" className="link-button" onClick={onOpenRecords}>
          Ver los registros
        </button>
      )}
    </article>
  );
}

function FigureCard({ widget, data }: { widget: Widget; data: Data }) {
  const figure = [
    ...(data.insight?.figures ?? []),
    ...(data.result?.rows.flatMap((row) => row.figures) ?? []),
  ].find((item) => item.evidence_id === widget.evidence_id);
  const unit =
    figure && "unit" in figure && figure.unit === "percent" ? " %" : "";
  return (
    <article
      className="dashboard-kpi"
      aria-label={widget.title}
      title={`Evidencia ${widget.evidence_id}`}
    >
      <span>{widget.title}</span>
      <strong>{figure ? `${exactNumber(figure.value)}${unit}` : "—"}</strong>
    </article>
  );
}

function Visual({ widget, data }: { widget: Widget; data: Data }) {
  const { insight, result } = data;
  if (widget.type === "bar" || widget.type === "line") {
    const all = points(data);
    // Con muchos grupos se dibujan los mayores (los resultados vienen ordenados) y el resto
    // queda en la tabla; una serie temporal se dibuja entera.
    const temporal =
      widget.type === "line" || result?.query.kind === "evolution";
    const shown = temporal ? all.slice(0, 60) : all.slice(0, BARS);
    return (
      <>
        <Chart
          label={widget.title}
          height={220}
          option={{
            ...seriesOption(
              shown.map((p) => p.label),
              shown.map((p) => p.value),
              widget.type === "line" ? "line" : "bar",
            ),
            ...SAFE,
          }}
        />
        {shown.length < (result?.total_groups ?? all.length) && (
          <small className="muted">
            Se muestran los {shown.length} primeros de{" "}
            {result?.total_groups ?? all.length} grupos; el resto está en la
            tabla del resultado.
          </small>
        )}
      </>
    );
  }
  if (widget.type === "histogram" && result) {
    const bins = result.rows.map((row) => ({
      label: row.groups[0] ?? "",
      value: Number(row.figures[0]?.value ?? 0),
    }));
    return (
      <Chart
        label={widget.title}
        height={220}
        option={{
          ...seriesOption(
            bins.map((b) => b.label),
            bins.map((b) => b.value),
            "bar",
          ),
          ...SAFE,
        }}
      />
    );
  }
  if (widget.type === "scatter" && result) {
    const pairs = result.rows.map(
      (row) =>
        [
          Number(row.figures[0]?.value ?? 0),
          Number(row.figures[1]?.value ?? 0),
        ] as [number, number],
    );
    return (
      <>
        <Chart
          label={widget.title}
          height={260}
          option={scatterOption(
            result.query.measure ?? "",
            result.query.measure_b ?? "",
            pairs,
          )}
        />
        {result.truncated && (
          <small className="muted">
            {pairs.length} de {result.total_groups} filas, a intervalos
            regulares.
          </small>
        )}
      </>
    );
  }
  if (widget.type === "pie") {
    const all = points(data);
    return (
      <Chart
        label={widget.title}
        height={240}
        option={pieOption(
          all.map((p) => p.label),
          all.map((p) => p.value),
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
      <div className="table-scroll">
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
      </div>
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

/** Filtros por periodo y por categoría: se aplican a todo lo que depende de ellos. */
function FilterBar({
  dashboard,
  applied,
  pending,
  onApply,
  onClear,
}: {
  dashboard: Dashboard;
  applied: FilterResult | null;
  pending: boolean;
  onApply: (request: FilterRequest) => void;
  onClear: () => void;
}) {
  const options = dashboard.filters;
  const months = options?.months ?? [];
  const dimensions = options?.dimensions ?? [];
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [chosen, setChosen] = useState<Record<string, string[]>>({});
  if (!options || (months.length === 0 && dimensions.length === 0)) return null;
  const toggle = (column: string, value: string) =>
    setChosen((current) => {
      const values = current[column] ?? [];
      return {
        ...current,
        [column]: values.includes(value)
          ? values.filter((v) => v !== value)
          : [...values, value],
      };
    });
  const request: FilterRequest = {
    period_from: from || null,
    period_to: to || null,
    categories: Object.entries(chosen)
      .filter(([, values]) => values.length > 0)
      .map(([column, values]) => ({ column, values })),
  };
  const empty =
    !request.period_from &&
    !request.period_to &&
    (request.categories ?? []).length === 0;
  return (
    <form
      className="dashboard-filterbar"
      aria-label="Filtros del dashboard"
      onSubmit={(event) => {
        event.preventDefault();
        if (!empty) onApply(request);
      }}
    >
      {months.length > 0 && (
        <fieldset>
          <legend>Periodo</legend>
          <label>
            Desde
            <select value={from} onChange={(e) => setFrom(e.target.value)}>
              <option value="">Inicio</option>
              {months.map((month) => (
                <option key={month} value={month}>
                  {month}
                </option>
              ))}
            </select>
          </label>
          <label>
            Hasta
            <select value={to} onChange={(e) => setTo(e.target.value)}>
              <option value="">Último mes</option>
              {months.map((month) => (
                <option key={month} value={month}>
                  {month}
                </option>
              ))}
            </select>
          </label>
        </fieldset>
      )}
      {dimensions.map((dimension) => (
        <details key={dimension.column} className="dashboard-filter-values">
          <summary>
            {dimension.column}
            {(chosen[dimension.column] ?? []).length > 0
              ? ` (${chosen[dimension.column].length})`
              : ""}
          </summary>
          <div role="group" aria-label={`Valores de ${dimension.column}`}>
            {dimension.values.map((value) => (
              <label key={value}>
                <input
                  type="checkbox"
                  checked={(chosen[dimension.column] ?? []).includes(value)}
                  onChange={() => toggle(dimension.column, value)}
                />
                {value}
              </label>
            ))}
            {(dimension.more ?? 0) > 0 && (
              <small className="muted">
                y {dimension.more} valores más (con menos registros).
              </small>
            )}
          </div>
        </details>
      ))}
      <div className="dashboard-filter-actions">
        <Button type="submit" size="sm" disabled={empty || pending}>
          {pending ? (
            <LoaderCircle className="spin" size={14} aria-hidden />
          ) : (
            <Filter size={14} aria-hidden />
          )}{" "}
          Aplicar filtros
        </Button>
        {applied && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              setFrom("");
              setTo("");
              setChosen({});
              onClear();
            }}
          >
            <X size={14} aria-hidden /> Quitar filtros
          </Button>
        )}
      </div>
    </form>
  );
}

function moved<T>(list: T[], index: number, delta: number): T[] {
  const next = [...list];
  const target = index + delta;
  if (target < 0 || target >= next.length) return next;
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

/** Personalizar: ocultar gráficos, reordenar secciones y gráficos, elegir los indicadores
 * destacados y cambiar títulos. Se guarda como una versión aparte. */
function Editor({
  sections,
  items,
  titleOf,
  pending,
  error,
  onSave,
  onCancel,
}: {
  sections: Section[];
  items: DashboardItem[];
  titleOf: (widget: Widget) => string;
  pending: boolean;
  error?: string;
  onSave: (sections: CustomSection[]) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<Section[]>(sections);
  const used = new Set(draft.flatMap((s) => s.widgets.map((w) => w.item)));
  const available = items.filter((item) => !used.has(item.id));
  const update = (index: number, section: Section) =>
    setDraft(draft.map((s, i) => (i === index ? section : s)));
  return (
    <section
      className="dashboard-editor"
      aria-label="Personalizar el dashboard"
    >
      <p className="muted">
        Oculta, ordena y renombra. La versión automática no cambia: puedes
        volver a ella cuando quieras.
      </p>
      {draft.map((section, index) => (
        <fieldset key={index} className="dashboard-editor-section">
          <legend>Sección {index + 1}</legend>
          <div className="dashboard-editor-row">
            <input
              aria-label={`Título de la sección ${index + 1}`}
              value={section.title}
              maxLength={200}
              onChange={(e) =>
                update(index, { ...section, title: e.target.value })
              }
            />
            <Button
              type="button"
              size="sm"
              variant="outline"
              aria-label={`Subir la sección ${section.title}`}
              disabled={index === 0}
              onClick={() => setDraft(moved(draft, index, -1))}
            >
              <ArrowUp size={14} aria-hidden />
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              aria-label={`Bajar la sección ${section.title}`}
              disabled={index === draft.length - 1}
              onClick={() => setDraft(moved(draft, index, 1))}
            >
              <ArrowDown size={14} aria-hidden />
            </Button>
          </div>
          <ul>
            {section.widgets.map((widget, position) => (
              <li
                key={`${widget.item}-${widget.type}-${widget.evidence_id ?? ""}`}
              >
                <span className="badge neutral">{TYPES[widget.type]}</span>
                <input
                  aria-label={`Título de ${titleOf(widget)}`}
                  value={widget.title}
                  maxLength={200}
                  onChange={(e) =>
                    update(index, {
                      ...section,
                      widgets: section.widgets.map((w, i) =>
                        i === position ? { ...w, title: e.target.value } : w,
                      ),
                    })
                  }
                />
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  aria-label={`Subir ${titleOf(widget)}`}
                  disabled={position === 0}
                  onClick={() =>
                    update(index, {
                      ...section,
                      widgets: moved(section.widgets, position, -1),
                    })
                  }
                >
                  <ArrowUp size={14} aria-hidden />
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  aria-label={`Ocultar ${titleOf(widget)}`}
                  onClick={() =>
                    update(index, {
                      ...section,
                      widgets: section.widgets.filter((_, i) => i !== position),
                    })
                  }
                >
                  <X size={14} aria-hidden /> Ocultar
                </Button>
              </li>
            ))}
          </ul>
        </fieldset>
      ))}
      {available.length > 0 && (
        <label className="dashboard-editor-add">
          Añadir a la última sección
          <select
            value=""
            onChange={(e) => {
              const item = available.find((i) => i.id === e.target.value);
              if (!item || draft.length === 0) return;
              const type =
                item.widgets.find((w) => w !== "kpi" && w !== "table") ??
                item.widgets[0];
              const last = draft.length - 1;
              update(last, {
                ...draft[last],
                widgets: [
                  ...draft[last].widgets,
                  {
                    item: item.id,
                    type,
                    title: item.title,
                    evidence_id: type === "kpi" ? item.figures[0] : null,
                  },
                ],
              });
            }}
          >
            <option value="">Elige un elemento…</option>
            {available.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </label>
      )}
      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
      <div className="dashboard-filter-actions">
        <Button
          type="button"
          size="sm"
          disabled={pending}
          onClick={() =>
            onSave(
              draft
                .filter((s) => s.widgets.length > 0)
                .map((s) => ({
                  title: s.title.trim() || "Sección",
                  widgets: s.widgets.map((w) => ({
                    item: w.item,
                    type: w.type,
                    evidence_id: w.evidence_id ?? null,
                    title: w.title.trim() || null,
                  })),
                })),
            )
          }
        >
          Guardar mi versión
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onCancel}>
          Cancelar
        </Button>
      </div>
    </section>
  );
}

function Board({
  view,
  versionId,
  onOpenRecords,
}: {
  view: DashboardView;
  versionId: string;
  onOpenRecords?: () => void;
}) {
  const dashboard = view.dashboard!;
  const arrangement = view.arrangement!;
  const custom = view.custom;
  const v2 = dashboard.rules_version === "dashboard-design-v2";
  const [mode, setMode] = useState<"automatic" | "custom">(
    custom ? "custom" : "automatic",
  );
  const [editing, setEditing] = useState(false);
  const [applied, setApplied] = useState<FilterResult | null>(null);
  const filter = useDashboardFilter(versionId);
  const save = useSaveCustomization(versionId);
  const items = useMemo(
    () => new Map((dashboard.items ?? []).map((i) => [i.id, i])),
    [dashboard.items],
  );
  const insights = new Map(
    (view.insights ?? []).map((i) => [`insight:${i.id}`, i]),
  );
  const results = new Map<string, Result>([
    ...(view.results ?? []).map(
      (r) => [`exploration:${r.key}`, r] as [string, Result],
    ),
    ...(dashboard.computed ?? []).map(
      (r) => [`computed:${r.key}`, r] as [string, Result],
    ),
  ]);
  const filtered = new Map(
    (applied?.items ?? []).map((entry) => [entry.item, entry]),
  );
  const indicators = new Map(
    (dashboard.indicators ?? []).map((i) => [i.evidence_id, i]),
  );
  const filteredIndicators = new Map(
    (applied?.indicators ?? []).map((i) => [i.id, i]),
  );
  const verdicts = new Map(
    (view.feedback ?? []).map((f) => [f.item, f.verdict]),
  );
  const data = (item: string): Data => {
    const entry = filtered.get(item);
    if (entry)
      return {
        insight: insights.get(item),
        result: entry.result ?? (entry.reason ? undefined : results.get(item)),
        reason: entry.reason,
      };
    return { insight: insights.get(item), result: results.get(item) };
  };
  const titleOf = (widget: Widget) =>
    items.get(widget.item)?.title ?? widget.title;
  const sections: Section[] =
    mode === "custom" && custom
      ? custom.sections.map((s) => ({
          title: s.title,
          widgets: s.widgets.map((w) => ({
            item: w.item,
            type: w.type,
            evidence_id: w.evidence_id,
            title:
              w.title ??
              (w.type === "kpi" && w.evidence_id
                ? (indicators.get(w.evidence_id)?.name ?? "")
                : ""),
          })),
        }))
      : arrangement.sections;
  const display = sections.map((s) => ({
    ...s,
    widgets: s.widgets.map((w) => ({
      ...w,
      title: w.title || titleOf(w),
    })),
  }));
  const rejected = (dashboard.decisions ?? []).filter(
    (d) => d.status === "rejected",
  );
  const filterError = filter.isError ? errorMessage(filter.error) : null;
  return (
    <>
      <header className="section-heading">
        <div>
          <h2>
            <LayoutDashboard size={18} aria-hidden /> {dashboard.title}
          </h2>
          <p>
            {dashboard.designed_by === "ai"
              ? "La IA eligió las secciones, el orden y el tipo de gráfico sin ver cifras; Python validó cada elección."
              : "Diseñado por reglas a partir de la forma de cada resultado."}{" "}
            Cada cifra sale del motor y tiene su origen.
          </p>
        </div>
        <span className="badge neutral">
          {dashboard.designed_by === "ai"
            ? "Diseñado por la IA"
            : "Diseñado por reglas"}
        </span>
      </header>
      {dashboard.partial && (
        <p className="info-banner" role="status">
          {dashboard.partial}
        </p>
      )}
      {dashboard.notice && (
        <p className="info-banner" role="status">
          {dashboard.notice}
        </p>
      )}
      {!v2 && (
        <p className="info-banner" role="status">
          Este dashboard es anterior a la Fase 26: no tiene filtros ni versión
          personalizada. Vuelve a investigar la versión para obtenerlos.
        </p>
      )}
      {v2 && (
        <div className="dashboard-toolbar-v2">
          <div
            className="dataset-subnav"
            role="tablist"
            aria-label="Versión del dashboard"
          >
            <button
              type="button"
              role="tab"
              aria-selected={mode === "automatic"}
              onClick={() => {
                setMode("automatic");
                setEditing(false);
              }}
            >
              Automático
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "custom"}
              disabled={!custom}
              onClick={() => setMode("custom")}
            >
              Personalizado
              {custom ? ` (revisión ${custom.revision})` : ""}
            </button>
          </div>
          {!editing && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                save.reset();
                setEditing(true);
              }}
            >
              <Pencil size={14} aria-hidden /> Personalizar
            </Button>
          )}
        </div>
      )}
      {(view.custom_dropped ?? 0) > 0 && mode === "custom" && (
        <p className="muted">
          {view.custom_dropped} gráficos de tu versión ya no están en el
          dashboard actual y no se muestran.
        </p>
      )}
      {editing ? (
        <Editor
          sections={display}
          items={dashboard.items ?? []}
          titleOf={titleOf}
          pending={save.isPending}
          error={save.isError ? errorMessage(save.error) : undefined}
          onCancel={() => setEditing(false)}
          onSave={(next) =>
            save.mutate(
              { expected_revision: custom?.revision ?? 0, sections: next },
              {
                onSuccess: () => {
                  setEditing(false);
                  setMode("custom");
                },
              },
            )
          }
        />
      ) : (
        <>
          {v2 && (
            <FilterBar
              dashboard={dashboard}
              applied={applied}
              pending={filter.isPending}
              onApply={(request) =>
                filter.mutate(request, { onSuccess: setApplied })
              }
              onClear={() => {
                filter.reset();
                setApplied(null);
              }}
            />
          )}
          {filterError && (
            <p className="auth-error" role="alert">
              {filterError}
            </p>
          )}
          <p className="dashboard-scope" role="status">
            <Eye size={14} aria-hidden />{" "}
            {applied
              ? `Subconjunto filtrado: ${exactNumber(String(applied.rows))} de ${exactNumber(String(applied.total_rows))} registros · ${applied.filters.join(" · ")}`
              : dashboard.total_rows
                ? `Dataset completo: ${exactNumber(String(dashboard.total_rows))} registros`
                : "Dataset completo"}
          </p>
          {display.map((section, index) => (
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
                  .map((widget) => {
                    const base = widget.evidence_id
                      ? indicators.get(widget.evidence_id)
                      : undefined;
                    const key = `${widget.item}-${widget.evidence_id}`;
                    if (!base)
                      return (
                        <FigureCard
                          key={key}
                          widget={widget}
                          data={data(widget.item)}
                        />
                      );
                    const shown = applied
                      ? filteredIndicators.get(base.id)
                      : base;
                    if (!shown)
                      return (
                        <article
                          key={key}
                          className="dashboard-kpi"
                          aria-label={widget.title}
                        >
                          <span>{widget.title}</span>
                          <strong>—</strong>
                          <small className="muted">
                            Sin datos con estos filtros.
                          </small>
                        </article>
                      );
                    return (
                      <KpiCard
                        key={key}
                        indicator={shown}
                        title={widget.title}
                        onOpenRecords={onOpenRecords}
                      />
                    );
                  })}
              </div>
              <div className="dashboard-grid">
                {section.widgets
                  .filter((w) => w.type !== "kpi")
                  .map((widget) => {
                    const found = data(widget.item);
                    const item = items.get(widget.item);
                    const trace =
                      found.result && applied && item?.trace
                        ? {
                            ...item.trace,
                            rows: found.result.covered_rows,
                            total_rows: applied.total_rows,
                            filters: [
                              ...(item.trace.filters ?? []),
                              ...applied.filters,
                            ],
                            method: found.result.method,
                          }
                        : item?.trace;
                    return (
                      <article
                        key={`${widget.item}-${widget.type}`}
                        className={`dashboard-card ${widget.type === "heatmap" || widget.type === "table" ? "wide" : ""}`}
                        aria-label={widget.title}
                      >
                        <header>
                          <h4>{widget.title}</h4>
                          <span>
                            {item?.classification &&
                              CLASSES[item.classification] && (
                                <span className="badge calculated">
                                  {CLASSES[item.classification]}
                                </span>
                              )}{" "}
                            <span className="badge neutral">
                              {TYPES[widget.type]}
                            </span>
                          </span>
                        </header>
                        {applied && (
                          <small
                            className={
                              found.reason ? "muted" : "dashboard-filtered"
                            }
                          >
                            {found.reason ??
                              `Subconjunto filtrado · ${applied.filters.join(" · ")}`}
                          </small>
                        )}
                        {found.insight && (
                          <p>{capDecimalsInText(found.insight.statement)}</p>
                        )}
                        {!applied && found.result?.reason && (
                          <p>{found.result.reason}</p>
                        )}
                        {found.result || found.insight ? (
                          <Visual widget={widget} data={found} />
                        ) : null}
                        <Origin trace={trace} />
                        {mode === "automatic" && (
                          <footer>
                            <small className="muted">
                              {found.insight?.coverage ?? found.result?.method}
                            </small>
                            {item?.origin !== "computed" && (
                              <Marks
                                item={widget.item}
                                verdict={verdicts.get(widget.item)}
                                versionId={versionId}
                                title={widget.title}
                              />
                            )}
                          </footer>
                        )}
                      </article>
                    );
                  })}
              </div>
            </div>
          ))}
          {mode === "automatic" && arrangement.hidden.length > 0 && (
            <details>
              <summary>
                Descartados por ti ({arrangement.hidden.length})
              </summary>
              <ul className="dashboard-hidden">
                {arrangement.hidden.map((item) => {
                  const title =
                    items.get(item)?.title ??
                    insights.get(item)?.title ??
                    results.get(item)?.title ??
                    item;
                  return (
                    <li key={item}>
                      <span>{title}</span>
                      <Marks
                        item={item}
                        verdict="drop"
                        versionId={versionId}
                        title={title}
                      />
                    </li>
                  );
                })}
              </ul>
            </details>
          )}
          {rejected.length > 0 && (
            <details>
              <summary>
                Elecciones de diseño rechazadas por la validación (
                {rejected.length})
              </summary>
              <ul>
                {rejected.map((decision, index) => (
                  <li key={index}>
                    {TYPES[decision.type] ?? decision.type} ·{" "}
                    {items.get(decision.item)?.title ?? decision.item} —{" "}
                    {decision.reason}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </>
  );
}

/** Fase 26: pestaña Dashboard. Indicadores con unidad, periodo, comparación y origen; gráficos
 * adaptados a la forma de cada resultado y ordenados por importancia; filtros que recalculan
 * lo que depende de ellos; y una versión personalizada que no destruye la automática. */
export function DashboardTab({
  versionId,
  onOpenRecords,
}: {
  versionId: string;
  onOpenRecords?: () => void;
}) {
  const query = useDashboardView(versionId);
  if (query.isPending)
    return (
      <p className="empty-copy" role="status">
        Cargando el dashboard…
      </p>
    );
  if (query.isError)
    return (
      <div className="empty-state">
        <p role="alert">{errorMessage(query.error)}</p>
        <Button onClick={() => void query.refetch()}>Reintentar</Button>
      </div>
    );
  const view = query.data;
  return (
    <section className="dashboard-adapted" aria-label="Dashboard" role="region">
      {!view ? (
        <p className="muted">
          Esta versión se procesó antes del dashboard adaptado: no tiene
          dashboard.
        </p>
      ) : view.state === "queued" || view.state === "running" ? (
        <p className="muted" role="status">
          <LoaderCircle className="spin" size={14} aria-hidden />{" "}
          {view.reason ?? "Diseñando el dashboard para estos datos…"}
        </p>
      ) : view.state === "failed" ? (
        <p role="alert">El dashboard falló ({view.reason ?? "sin detalle"}).</p>
      ) : view.dashboard && view.arrangement ? (
        <Board
          key={view.execution_id ?? "dashboard"}
          view={view}
          versionId={versionId}
          onOpenRecords={onOpenRecords}
        />
      ) : null}
    </section>
  );
}
