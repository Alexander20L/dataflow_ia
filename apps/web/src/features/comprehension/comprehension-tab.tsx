"use client";

import { useMemo, useState, type FormEvent, type KeyboardEvent } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { Check, LoaderCircle, Pencil, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Chart } from "@/components/ui/chart";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import {
  useComprehensionView,
  useDescribe,
  useJudge,
  type ColumnMeaning,
  type Comprehension,
  type ComprehensionView,
  type Relationship,
} from "./api";
import {
  ADDITIVITY,
  AGGREGATIONS,
  AI_REASONS,
  CONFIDENCES,
  FAMILIES,
  KINDS,
  ORIGINS,
  SCALES,
  STATE_BADGE,
  STATES,
  STATUS,
} from "./labels";

const SUBVIEWS = [
  { id: "summary", label: "Resumen" },
  { id: "columns", label: "Columnas" },
  { id: "relations", label: "Relaciones" },
] as const;
type Subview = (typeof SUBVIEWS)[number]["id"];

/** Fase 24: pestaña Comprensión. Qué representa cada fila, qué columnas son fórmulas de otras,
 * cómo se relacionan y qué significa cada una. Las reglas calculan sobre todas las filas; la IA
 * sólo propone nombres y significados con su confianza. */
export function ComprehensionTab({ versionId }: { versionId: string }) {
  const query = useComprehensionView(versionId);
  const [subview, setSubview] = useState<Subview>("summary");
  if (query.isPending)
    return (
      <p className="empty-copy" role="status">
        Cargando la comprensión…
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
  if (!view)
    return (
      <div className="empty-state">
        <h3>Comprensión no disponible</h3>
        <p>
          Esta versión se procesó antes de la comprensión del negocio: sube el
          archivo de nuevo para obtenerla.
        </p>
      </div>
    );
  if (view.state === "queued" || view.state === "running")
    return (
      <div className="processing-state" role="status">
        <LoaderCircle className="spin" size={26} />
        <h3>Entendiendo los datos</h3>
        <p>
          Se calculan el grano, las fórmulas y las relaciones sobre todas las
          filas.
        </p>
      </div>
    );
  if (view.state === "failed" || !view.comprehension)
    return (
      <div className="empty-state">
        <h3>No se pudo calcular la comprensión</h3>
        <p role="alert">{view.reason ?? "Sin detalle."}</p>
      </div>
    );
  const onKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step =
      event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = SUBVIEWS[(index + step + SUBVIEWS.length) % SUBVIEWS.length];
    setSubview(next.id);
    document.getElementById(`comprehension-tab-${next.id}`)?.focus();
  };
  const result = view.comprehension;
  return (
    <section className="dataset-tab" aria-label="Comprensión">
      {view.recalculating && (
        <p className="info-banner recalculation-banner" role="status">
          <LoaderCircle className="spin" size={16} aria-hidden />
          Rehaciendo la exploración, el dashboard y el informe con tus
          validaciones…
        </p>
      )}
      <div
        className="dataset-subnav"
        role="tablist"
        aria-label="Secciones de la comprensión"
      >
        {SUBVIEWS.map((item, index) => (
          <button
            key={item.id}
            id={`comprehension-tab-${item.id}`}
            type="button"
            role="tab"
            aria-selected={subview === item.id}
            aria-controls={`comprehension-panel-${item.id}`}
            tabIndex={subview === item.id ? 0 : -1}
            onClick={() => setSubview(item.id)}
            onKeyDown={(event) => onKey(event, index)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div
        id={`comprehension-panel-${subview}`}
        role="tabpanel"
        aria-labelledby={`comprehension-tab-${subview}`}
        className="inspection-panel"
      >
        {subview === "summary" ? (
          <Summary result={result} />
        ) : subview === "columns" ? (
          <Columns result={result} versionId={versionId} />
        ) : (
          <Relations view={view} result={result} versionId={versionId} />
        )}
      </div>
    </section>
  );
}

function Summary({ result }: { result: Comprehension }) {
  const formulas = result.formulas ?? [];
  return (
    <div className="dataset-summary">
      <section aria-label="Grano del dataset">
        <h3>Qué representa cada fila</h3>
        {result.grain ? (
          <>
            <p className="comprehension-grain">{result.grain.sentence}</p>
            <p className="muted">{result.grain.reason}</p>
          </>
        ) : (
          <p className="muted">
            Esta versión se calculó antes de la Fase 24: súbela de nuevo para
            ver el grano y las fórmulas.
          </p>
        )}
      </section>
      <section aria-label="Dominio del negocio">
        <h3>De qué trata</h3>
        {result.domain ? (
          <>
            <span className="badge neutral">Hipótesis de la IA</span>
            <p>{result.domain}</p>
            {(result.entities ?? []).length > 0 && (
              <p className="muted">
                {(result.entities ?? [])
                  .map((e) => `${e.name}: ${e.columns.join(", ")}`)
                  .join(" · ")}
              </p>
            )}
          </>
        ) : (
          <p className="muted">
            Sin hipótesis de la IA (
            {AI_REASONS[result.ai_reason ?? ""] ??
              result.ai_reason ??
              result.ai_state}
            ): el grano, las fórmulas, las relaciones y el periodo se calculan
            igual con los datos.
          </p>
        )}
      </section>
      <section aria-label="Columnas calculadas">
        <h3>Columnas calculadas a partir de otras</h3>
        {formulas.length === 0 ? (
          <p className="muted">
            Ninguna columna es una suma ponderada, un producto o un umbral de
            otras.
          </p>
        ) : (
          <ul className="dataset-notes">
            {formulas.map((f) => (
              <li key={f.column}>
                <strong>{f.expression}</strong>
                <br />
                <small className="muted">
                  Se cumple en {f.matching_rows} de {f.rows} filas. {f.method}
                </small>
              </li>
            ))}
          </ul>
        )}
        {formulas.length > 0 && (
          <p className="muted">
            Son fórmulas, no hallazgos: sus asociaciones con sus propias fuentes
            no se proponen en la exploración ni en el dashboard.
          </p>
        )}
      </section>
      {result.period && (
        <section aria-label="Periodo">
          <h3>Periodo</h3>
          <p>
            {result.period.note} {result.period.periods} periodos
            {result.period.first
              ? `, de ${result.period.first} a ${result.period.last}`
              : ""}
            .
          </p>
        </section>
      )}
      {(result.questions ?? []).length > 0 && (
        <section aria-label="Preguntas de negocio sugeridas">
          <h3>Preguntas de negocio sugeridas</h3>
          <ul className="dataset-notes">
            {(result.questions ?? []).map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </section>
      )}
      <details>
        <summary>Cómo se calculó</summary>
        <ul className="dataset-notes">
          {result.limitations.map((item) => (
            <li key={item}>{item}</li>
          ))}
          <li>Reglas: {result.rules_version}.</li>
        </ul>
      </details>
    </div>
  );
}

function Columns({
  result,
  versionId,
}: {
  result: Comprehension;
  versionId: string;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const meanings = new Map<string, ColumnMeaning>(
    (result.meanings ?? []).map((m) => [m.column, m]),
  );
  const measures = new Map((result.measures ?? []).map((m) => [m.column, m]));
  const dimensions = new Map(
    (result.dimensions ?? []).map((d) => [d.column, d]),
  );
  return (
    <div>
      <p className="muted">
        La escala y el uso de cada columna salen de las reglas (con tus
        correcciones del Diccionario). El significado es una hipótesis de la IA
        con su confianza; puedes escribirlo o confirmarlo: no cambia ningún
        cálculo y lo heredan las versiones siguientes.
      </p>
      <div className="table-scroll">
        <table className="data-table comprehension-columns">
          <thead>
            <tr>
              <th scope="col">Columna</th>
              <th scope="col">Escala</th>
              <th scope="col">Uso en el análisis</th>
              <th scope="col">Significado</th>
              <th scope="col" aria-label="Acciones" />
            </tr>
          </thead>
          <tbody>
            {result.scales.map((s) => {
              const meaning = meanings.get(s.column);
              const measure = measures.get(s.column);
              const dimension = dimensions.get(s.column);
              return (
                <tr key={s.column}>
                  <th scope="row">{s.column}</th>
                  <td title={s.reason}>
                    {SCALES[s.scale]}
                    {(s.order ?? []).length > 0 && (
                      <small>
                        {" "}
                        ({(s.order ?? []).slice(0, 6).join(" < ")})
                      </small>
                    )}
                  </td>
                  <td>
                    {measure ? (
                      <>
                        Medida · {AGGREGATIONS[measure.aggregation]}
                        {measure.unit ? ` · ${measure.unit}` : ""}
                        <br />
                        <small className="muted">
                          {ADDITIVITY[measure.additivity]}. {measure.reason}
                        </small>
                      </>
                    ) : dimension ? (
                      <>
                        Dimensión · {dimension.distinct} categorías
                        <br />
                        <small className="muted">{dimension.reason}</small>
                      </>
                    ) : (
                      <span className="muted">No se agrega</span>
                    )}
                  </td>
                  <td>
                    {meaning ? (
                      <>
                        {meaning.meaning}
                        <br />
                        <span
                          className={`badge ${meaning.source === "user" ? "completed" : meaning.confidence === "low" ? "warning" : "neutral"}`}
                        >
                          {meaning.source === "user"
                            ? "Escrito por ti"
                            : meaning.confirmed
                              ? "Confirmado por ti"
                              : (CONFIDENCES[meaning.confidence ?? ""] ??
                                "Hipótesis de la IA")}
                        </span>
                      </>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td>
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Editar el significado de ${s.column}`}
                      onClick={() => setEditing(s.column)}
                    >
                      <Pencil size={14} aria-hidden /> Editar
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {editing && (
        <Dialog
          title={`Significado de «${editing}»`}
          onClose={() => setEditing(null)}
        >
          <MeaningEditor
            column={editing}
            meaning={meanings.get(editing)}
            versionId={versionId}
            onDone={() => setEditing(null)}
          />
        </Dialog>
      )}
    </div>
  );
}

function MeaningEditor({
  column,
  meaning,
  versionId,
  onDone,
}: {
  column: string;
  meaning?: ColumnMeaning;
  versionId: string;
  onDone: () => void;
}) {
  const describe = useDescribe(versionId);
  const [text, setText] = useState(
    meaning?.source === "user" ? meaning.meaning : "",
  );
  const save = (event: FormEvent) => {
    event.preventDefault();
    describe.mutate(
      { column, meaning: text.trim() || null, confirmed: false },
      { onSuccess: onDone },
    );
  };
  return (
    <form className="dictionary-editor" onSubmit={save}>
      {meaning && meaning.source === "ai" && (
        <p className="muted">
          IA: {meaning.meaning} ({CONFIDENCES[meaning.confidence ?? ""] ?? "—"})
        </p>
      )}
      <label htmlFor="meaning-text">
        Significado
        <textarea
          id="meaning-text"
          maxLength={300}
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </label>
      {describe.isError && (
        <p role="alert" className="form-error">
          {errorMessage(describe.error)}
        </p>
      )}
      <div className="dialog-actions">
        <Button type="submit" disabled={describe.isPending || !text.trim()}>
          Guardar significado
        </Button>
        {meaning?.source === "ai" && !meaning.confirmed && (
          <Button
            type="button"
            variant="outline"
            disabled={describe.isPending}
            onClick={() =>
              describe.mutate(
                { column, meaning: null, confirmed: true },
                { onSuccess: onDone },
              )
            }
          >
            Confirmar el de la IA
          </Button>
        )}
        {(meaning?.source === "user" || meaning?.confirmed) && (
          <Button
            type="button"
            variant="ghost"
            disabled={describe.isPending}
            onClick={() =>
              describe.mutate(
                { column, meaning: null, confirmed: false },
                { onSuccess: onDone },
              )
            }
          >
            Volver al de la IA
          </Button>
        )}
      </div>
    </form>
  );
}

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
        const [j, i] = p.value;
        const info = best.get(`${columns[i]}|${columns[j]}`);
        return `${columns[i]} – ${columns[j]}<br/>${
          i === j ? "misma columna" : (info?.label ?? "sin medida")
        }`;
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

const FAMILY_ORDER = ["structural", "statistical", "temporal"] as const;

function Relations({
  view,
  result,
  versionId,
}: {
  view: ComprehensionView;
  result: Comprehension;
  versionId: string;
}) {
  const judge = useJudge(versionId);
  const option = useMemo(() => heatmap(result), [result]);
  const [family, setFamily] = useState<string>("all");
  const shown = result.relationships.filter(
    (r) => family === "all" || (r.family ?? "statistical") === family,
  );
  const count = (f: string) =>
    result.relationships.filter((r) => (r.family ?? "statistical") === f)
      .length;
  return (
    <div className="comprehension-relations">
      <p className="muted">
        Estructurales: una columna calculada, una misma entidad o una
        dependencia, comprobadas fila a fila. Estadísticas: asociaciones medidas
        sobre todas las filas (una asociación no es una causa). Temporales: el
        periodo. Validar o rechazar cuenta ya: se rehacen la exploración, el
        dashboard y el informe.
      </p>
      <div
        className="chip-options"
        role="group"
        aria-label="Filtrar relaciones"
      >
        <button
          type="button"
          aria-pressed={family === "all"}
          onClick={() => setFamily("all")}
        >
          Todas ({result.relationships.length})
        </button>
        {FAMILY_ORDER.map((f) => (
          <button
            key={f}
            type="button"
            aria-pressed={family === f}
            onClick={() => setFamily(f)}
          >
            {FAMILIES[f]} ({count(f)})
          </button>
        ))}
      </div>
      {shown.length === 0 ? (
        <p className="empty-copy">No hay relaciones de este tipo.</p>
      ) : (
        <ul>
          {shown.map((r) => (
            <RelationItem
              key={r.key}
              relation={r}
              disabled={judge.isPending || view.recalculating === true}
              onJudge={(verdict) => judge.mutate({ key: r.key, verdict })}
            />
          ))}
        </ul>
      )}
      {judge.isError && (
        <p className="field-error" role="alert">
          {errorMessage(judge.error)}
        </p>
      )}
      {option && (
        <section aria-label="Mapa de asociaciones">
          <h3>Mapa de asociaciones</h3>
          <Chart
            option={option}
            label="Mapa de calor de asociaciones entre columnas"
            height={Math.max(260, result.matrix_columns.length * 34 + 100)}
          />
        </section>
      )}
    </div>
  );
}

function RelationItem({
  relation: r,
  disabled,
  onJudge,
}: {
  relation: Relationship;
  disabled: boolean;
  onJudge: (verdict: "relevant" | "not_relevant") => void;
}) {
  const state = r.state ?? "pending";
  return (
    <li
      className={`relation ${r.status} ${r.verdict ?? ""}`}
      aria-label={`Relación ${r.columns[0]} – ${r.columns[1]}`}
    >
      <div>
        <strong>
          {r.columns[0]} – {r.columns[1]}
        </strong>{" "}
        <span className={`badge ${STATE_BADGE[state]}`}>{STATES[state]}</span>{" "}
        <span className="badge neutral">{KINDS[r.kind]}</span>{" "}
        <span className="badge neutral">{ORIGINS[r.origin]}</span>{" "}
        <span className="relation-status">{STATUS[r.status]}</span>
        {r.hypothesis && <p>{r.hypothesis}</p>}
        <small>{r.detail}</small>
      </div>
      <div className="relation-actions" role="group" aria-label="Validación">
        <button
          type="button"
          className="btn btn-sm btn-outline"
          aria-pressed={r.verdict === "relevant"}
          disabled={disabled}
          onClick={() => onJudge("relevant")}
        >
          <Check size={13} /> Validar
        </button>
        <button
          type="button"
          className="btn btn-sm btn-outline"
          aria-pressed={r.verdict === "not_relevant"}
          disabled={disabled}
          onClick={() => onJudge("not_relevant")}
        >
          <X size={13} /> Rechazar
        </button>
      </div>
    </li>
  );
}
