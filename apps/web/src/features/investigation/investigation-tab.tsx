"use client";

import { useState, type KeyboardEvent } from "react";
import {
  CircleAlert,
  LoaderCircle,
  Pause,
  Play,
  RotateCcw,
  Square,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Chart, seriesOption } from "@/components/ui/chart";
import { errorMessage } from "@/lib/api";
import { capDecimals, capDecimalsInText } from "@/lib/numbers";
import {
  useInvestigationControl,
  useInvestigationHistory,
  useInvestigationView,
  type Investigation,
  type InvestigationNode,
  type InvestigationResult,
} from "./api";
import {
  CLASS_BADGE,
  CLASSES,
  CRITERIA,
  PRIORITIES,
  RUN_STATES,
  STOPPED,
  TRIGGERS,
} from "./labels";

const SUBVIEWS = [
  { id: "plan", label: "Plan" },
  { id: "tree", label: "Árbol" },
  { id: "evidence", label: "Evidencias" },
  { id: "history", label: "Historial" },
] as const;
type Subview = (typeof SUBVIEWS)[number]["id"];
type Filter = "all" | NonNullable<InvestigationNode["classification"]>;
const ROWS = 12;

function number(value?: string | null) {
  if (value == null) return "—";
  const [whole, fraction] = capDecimals(value).split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return fraction ? `${grouped},${fraction}` : grouped;
}

function when(value?: string | null) {
  return value ? new Date(value).toLocaleString("es") : "—";
}

function ClassBadge({ node }: { node: InvestigationNode }) {
  if (node.status === "pending")
    return <span className="badge neutral">Pendiente</span>;
  if (node.status === "failed")
    return <span className="badge blocking">Error de ejecución</span>;
  if (!node.classification) return null;
  return (
    <span className={`badge ${CLASS_BADGE[node.classification]}`}>
      {CLASSES[node.classification]}
    </span>
  );
}

function Origin({ node }: { node: InvestigationNode }) {
  return (
    <span className={`badge ${node.origin === "ai" ? "ai" : "neutral"}`}>
      {node.origin === "ai" ? "Propuesta por la IA" : "Por reglas"}
    </span>
  );
}

/** El plan: las investigaciones iniciales con su pregunta, motivo, columnas, método, resultado
 * esperado, prioridad y dependencias. */
function PlanView({ result }: { result: Investigation }) {
  const roots = (result.nodes ?? []).filter((node) => !node.parent);
  return (
    <div className="investigation-plan">
      <p className="muted">
        {roots.length} investigaciones en el plan, en orden de prioridad. Las
        propone
        {result.ai_state === "ready"
          ? "n las reglas y la IA"
          : "n las reglas"}{" "}
        a partir de la comprensión; Python valida cada una antes de calcularla.
      </p>
      <div className="table-scroll">
        <table
          className="comprehension-table"
          aria-label="Plan de investigación"
        >
          <thead>
            <tr>
              <th>#</th>
              <th>Investigación</th>
              <th>Motivo</th>
              <th>Columnas</th>
              <th>Método</th>
              <th>Resultado esperado</th>
              <th>Prioridad</th>
              <th>Depende de</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {[...roots]
              .sort((a, b) => a.priority - b.priority)
              .map((node) => (
                <tr key={node.id} aria-label={`Investigación ${node.id}`}>
                  <td>{node.id}</td>
                  <td>
                    <strong>{node.question}</strong>
                    <br />
                    <small className="muted">
                      Hipótesis: {node.hypothesis}
                    </small>
                    <br />
                    <Origin node={node} />
                  </td>
                  <td>{node.motive}</td>
                  <td>{node.columns.join(", ")}</td>
                  <td>{node.method}</td>
                  <td>{node.expected}</td>
                  <td>{PRIORITIES[node.priority]}</td>
                  <td>{(node.depends_on ?? []).join(", ") || "—"}</td>
                  <td>
                    <ClassBadge node={node} />
                    {node.reason && node.status !== "computed" && (
                      <small className="muted"> {node.reason}</small>
                    )}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** El árbol: cada investigación con su clase y la decisión de profundizar o terminar. */
function TreeView({
  result,
  onEvidence,
}: {
  result: Investigation;
  onEvidence: (id: string) => void;
}) {
  const children = (parent: string | null) =>
    (result.nodes ?? []).filter((node) => (node.parent ?? null) === parent);
  const branch = (parent: string | null) => {
    const items = children(parent);
    if (!items.length) return null;
    return (
      <ul className="investigation-tree">
        {items.map((node) => (
          <li key={node.id} aria-label={`Investigación ${node.id}`}>
            <div className="investigation-node">
              <span className="investigation-id">{node.id}</span>
              <strong>{node.question}</strong>
              <ClassBadge node={node} />
              <Origin node={node} />
              {node.status === "computed" && node.key && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onEvidence(node.id)}
                >
                  Ver evidencia
                </Button>
              )}
            </div>
            {(node.decision_reason || node.reason) && (
              <p className="muted">
                {node.decision === "deepen" ? "↳ " : ""}
                {capDecimalsInText(node.decision_reason ?? node.reason ?? "")}
              </p>
            )}
            {branch(node.id)}
          </li>
        ))}
      </ul>
    );
  };
  return (
    <div>
      <p className="muted">
        Cuando un resultado es interesante, la investigación abre preguntas
        secundarias (hasta {result.limits.max_depth} niveles y{" "}
        {result.limits.max_nodes} investigaciones).
      </p>
      {branch(null)}
    </div>
  );
}

function ResultTable({ result }: { result: InvestigationResult }) {
  const shown = result.rows.slice(0, ROWS);
  const single = shown.length > 1 && shown.every((r) => r.figures.length === 1);
  const temporal = result.query.kind === "evolution";
  return (
    <>
      {single && (
        <Chart
          option={seriesOption(
            shown.map((row) => row.groups.join(" · ")),
            shown.map((row) => Number(row.figures[0].value ?? 0)),
            temporal ? "line" : "bar",
          )}
          label={result.title}
          height={200}
        />
      )}
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
            {shown.map((row) => (
              <tr key={row.groups.join("|") || "total"}>
                {row.groups.map((group, index) => (
                  <td key={index}>{group}</td>
                ))}
                {row.figures.map((figure) => (
                  <td
                    key={figure.evidence_id}
                    title={`Evidencia ${figure.evidence_id}`}
                  >
                    {number(figure.value)}
                  </td>
                ))}
                <td>{number(String(row.rows))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {result.total_groups > ROWS && (
        <small className="muted">
          Se muestran {ROWS} de {result.total_groups} grupos.
        </small>
      )}
    </>
  );
}

/** Una evidencia: pregunta, hipótesis, columnas, filtros, operación, registros, resultado,
 * método, evaluación, limitaciones y ejecución que lo produjo. */
function EvidenceCard({
  node,
  result,
}: {
  node: InvestigationNode;
  result?: InvestigationResult;
}) {
  return (
    <article
      className="exploration-result investigation-evidence"
      aria-label={`Evidencia ${node.id}`}
      id={`evidence-${node.id}`}
    >
      <header>
        <h3>
          {node.id}. {node.question}
        </h3>
        <ClassBadge node={node} />
      </header>
      <dl className="investigation-facts">
        <dt>Hipótesis</dt>
        <dd>{node.hypothesis}</dd>
        <dt>Columnas</dt>
        <dd>{node.columns.join(", ")}</dd>
        <dt>Filtros</dt>
        <dd>
          {(node.filters ?? []).join("; ") || "Ninguno: todos los registros"}
        </dd>
        <dt>Operación</dt>
        <dd>
          {result?.title ?? node.method} · {node.method}
        </dd>
        {node.rows_considered != null && (
          <>
            <dt>Registros considerados</dt>
            <dd>
              {number(String(node.rows_considered))}
              {node.total_rows != null &&
                ` de ${number(String(node.total_rows))}`}
            </dd>
          </>
        )}
        <dt>Ejecución</dt>
        <dd>
          <code>{node.execution_id ?? "—"}</code>
        </dd>
      </dl>
      {node.interpretation && (
        <p>
          <strong>Interpretación de la IA:</strong> {node.interpretation}
        </p>
      )}
      {node.reason && node.status !== "pending" && !result && (
        <p role={node.status === "failed" ? "alert" : undefined}>
          {node.reason}
        </p>
      )}
      {result && <ResultTable result={result} />}
      {result && <small className="muted">{result.method}</small>}
      {(node.criteria ?? []).length > 0 && (
        <ul className="investigation-criteria" aria-label="Evaluación">
          {(node.criteria ?? []).map((criterion, index) => (
            <li key={index}>
              <strong>{CRITERIA[criterion.name]}:</strong>{" "}
              {capDecimalsInText(criterion.assessment)}
            </li>
          ))}
        </ul>
      )}
      {(node.limitations ?? []).length > 0 && (
        <ul className="investigation-limitations" aria-label="Limitaciones">
          {(node.limitations ?? []).map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      )}
      {node.decision_reason && (
        <p className="muted">Decisión: {node.decision_reason}</p>
      )}
    </article>
  );
}

function EvidenceView({ result }: { result: Investigation }) {
  const [filter, setFilter] = useState<Filter>("all");
  const results = new Map(result.results.map((r) => [r.key, r]));
  const nodes = (result.nodes ?? []).filter(
    (node) =>
      node.status !== "pending" &&
      (filter === "all" || node.classification === filter),
  );
  return (
    <div>
      <label className="investigation-filter">
        Mostrar{" "}
        <select
          value={filter}
          onChange={(event) => setFilter(event.target.value as Filter)}
        >
          <option value="all">Todas</option>
          {Object.entries(CLASSES).map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {nodes.length === 0 ? (
        <p className="muted">No hay investigaciones con esa clase.</p>
      ) : (
        <div className="exploration-grid">
          {nodes.map((node) => (
            <EvidenceCard
              key={node.id}
              node={node}
              result={node.key ? results.get(node.key) : undefined}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** Versiones exploradas antes de la Fase 25 (`explore-v1`): sin plan ni árbol. */
function LegacyEvidence({ result }: { result: Investigation }) {
  return (
    <div>
      <p className="info-banner" role="note">
        Esta versión se exploró antes de la pestaña Investigación: tiene
        resultados, pero no plan ni árbol. Usa «Volver a investigar» para
        obtenerlos.
      </p>
      <div className="exploration-grid">
        {result.results.map((item) => (
          <article
            key={item.key}
            className="exploration-result"
            aria-label={item.title}
          >
            <header>
              <h3>{item.title}</h3>
            </header>
            {item.reason && <p>{item.reason}</p>}
            <ResultTable result={item} />
          </article>
        ))}
      </div>
    </div>
  );
}

function HistoryView({
  versionId,
  current,
  onOpen,
}: {
  versionId: string;
  current?: string | null;
  onOpen: (id: string) => void;
}) {
  const history = useInvestigationHistory(versionId);
  if (history.isPending) return <p className="muted">Cargando el historial…</p>;
  if (history.isError) return <p role="alert">{errorMessage(history.error)}</p>;
  const items = history.data?.items ?? [];
  return (
    <div className="table-scroll">
      <table
        className="comprehension-table"
        aria-label="Investigaciones anteriores"
      >
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Origen</th>
            <th>Estado</th>
            <th>Investigaciones</th>
            <th>Hallazgos</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.map((run) => (
            <tr key={run.execution_id}>
              <td>{when(run.created_at)}</td>
              <td>{run.trigger ? TRIGGERS[run.trigger] : "—"}</td>
              <td>
                {run.stopped
                  ? STOPPED[run.stopped].split(":")[0].replace(/\.$/, "")
                  : RUN_STATES[run.state]}
                {run.error_code && (
                  <small className="muted"> ({run.error_code})</small>
                )}
              </td>
              <td>
                {run.computed ?? "—"}
                {run.nodes != null && ` de ${run.nodes}`}
              </td>
              <td>{run.relevant ?? "—"}</td>
              <td>
                {run.execution_id === current ? (
                  <span className="badge neutral">Viendo</span>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onOpen(run.execution_id)}
                  >
                    Ver
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Fase 25: pestaña Investigación. El plan, el árbol de investigaciones secundarias y la
 * evidencia de cada resultado, con su clasificación. El usuario puede pausar, cancelar,
 * reanudar y volver a investigar, y consultar las investigaciones anteriores. */
export function InvestigationTab({ versionId }: { versionId: string }) {
  const [subview, setSubview] = useState<Subview>("plan");
  const [executionId, setExecutionId] = useState<string>();
  const query = useInvestigationView(versionId, executionId);
  const control = useInvestigationControl(versionId);
  if (query.isPending)
    return (
      <p className="empty-copy" role="status">
        Cargando la investigación…
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
        <h3>Investigación no disponible</h3>
        <p>
          Esta versión se procesó antes de la investigación automática: sube el
          archivo de nuevo para obtenerla.
        </p>
      </div>
    );
  const running = view.state === "queued" || view.state === "running";
  const result = view.exploration;
  const latest = !executionId;
  const act = (action: "pause" | "cancel" | "resume" | "restart") => {
    setExecutionId(undefined);
    control.mutate(action);
  };
  const onKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step =
      event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = SUBVIEWS[(index + step + SUBVIEWS.length) % SUBVIEWS.length];
    setSubview(next.id);
    document.getElementById(`investigation-tab-${next.id}`)?.focus();
  };
  const legacy = result && (result.nodes ?? []).length === 0;
  const computed =
    (result?.nodes ?? []).filter((n) => n.status === "computed") ?? [];
  const failed =
    (result?.nodes ?? []).filter((n) => n.status === "failed") ?? [];
  return (
    <section className="dataset-tab" aria-label="Investigación">
      {!latest && (
        <p className="info-banner" role="status">
          Estás viendo una investigación anterior.{" "}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setExecutionId(undefined)}
          >
            Volver a la actual
          </Button>
        </p>
      )}
      <div
        className="investigation-status"
        aria-label="Estado de la investigación"
      >
        <div role="status">
          {running ? (
            <>
              <LoaderCircle className="spin" size={16} aria-hidden />{" "}
              {view.state === "queued"
                ? "Investigación en cola."
                : "Investigando: se calcula cada pregunta sobre todas las filas."}
              {view.control === "pause" &&
                " Se pausará al terminar la investigación en curso."}
              {view.control === "cancel" &&
                " Se cancelará al terminar la investigación en curso."}
            </>
          ) : view.state === "failed" ? (
            <span role="alert">
              <CircleAlert size={16} aria-hidden /> La investigación falló (
              {view.reason ?? "sin detalle"}).
            </span>
          ) : result?.stopped ? (
            STOPPED[result.stopped]
          ) : (
            "Investigación terminada."
          )}
          {result?.consumption && (
            <small className="muted">
              {" "}
              · {result.consumption.nodes} calculadas en esta ejecución ·{" "}
              {result.consumption.ai_calls} llamadas a la IA ·{" "}
              {number(String(result.consumption.elapsed_ms / 1000))} s
            </small>
          )}
        </div>
        {latest && (
          <div className="investigation-actions">
            {running ? (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={control.isPending || !!view.control}
                  onClick={() => act("pause")}
                >
                  <Pause size={14} aria-hidden /> Pausar
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={control.isPending || !!view.control}
                  onClick={() => act("cancel")}
                >
                  <Square size={14} aria-hidden /> Cancelar
                </Button>
              </>
            ) : (
              <>
                {view.resumable && (
                  <Button
                    size="sm"
                    disabled={control.isPending}
                    onClick={() => act("resume")}
                  >
                    <Play size={14} aria-hidden /> Reanudar
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  disabled={control.isPending}
                  onClick={() => act("restart")}
                >
                  <RotateCcw size={14} aria-hidden /> Volver a investigar
                </Button>
              </>
            )}
          </div>
        )}
      </div>
      {control.isError && (
        <p className="auth-error" role="alert">
          {errorMessage(control.error)}
        </p>
      )}
      {failed.length > 0 && (
        <p className="info-banner" role="alert">
          {failed.length} investigaciones fallaron al ejecutarse; el resto
          siguió. Mira su detalle en Evidencias.
        </p>
      )}
      <div
        className="dataset-subnav"
        role="tablist"
        aria-label="Secciones de la investigación"
      >
        {SUBVIEWS.map((item, index) => (
          <button
            key={item.id}
            id={`investigation-tab-${item.id}`}
            type="button"
            role="tab"
            aria-selected={subview === item.id}
            aria-controls={`investigation-panel-${item.id}`}
            tabIndex={subview === item.id ? 0 : -1}
            onClick={() => setSubview(item.id)}
            onKeyDown={(event) => onKey(event, index)}
          >
            {item.label}
            {item.id === "evidence" && result && !legacy
              ? ` (${computed.length})`
              : ""}
          </button>
        ))}
      </div>
      <div
        id={`investigation-panel-${subview}`}
        role="tabpanel"
        aria-labelledby={`investigation-tab-${subview}`}
      >
        {subview === "history" ? (
          <HistoryView
            versionId={versionId}
            current={executionId ?? view.execution_id}
            onOpen={(id) => {
              setExecutionId(id);
              setSubview("plan");
            }}
          />
        ) : !result ? (
          <p className="muted">
            {running
              ? "El plan aparecerá cuando termine esta ejecución."
              : "No hay resultados en esta ejecución."}
          </p>
        ) : legacy ? (
          <LegacyEvidence result={result} />
        ) : subview === "plan" ? (
          <PlanView result={result} />
        ) : subview === "tree" ? (
          <TreeView
            result={result}
            onEvidence={(id) => {
              setSubview("evidence");
              requestAnimationFrame(() =>
                document
                  .getElementById(`evidence-${id}`)
                  ?.scrollIntoView({ block: "start" }),
              );
            }}
          />
        ) : (
          <EvidenceView result={result} />
        )}
      </div>
      {result && result.limitations.length > 0 && subview !== "history" && (
        <details className="investigation-notes">
          <summary>
            Limitaciones y criterios ({result.limitations.length})
          </summary>
          <ul>
            {result.limitations.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
