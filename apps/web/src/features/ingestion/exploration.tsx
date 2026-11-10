"use client";

import { Compass, LoaderCircle } from "lucide-react";
import { Chart, seriesOption } from "@/components/ui/chart";
import type { ExplorationView } from "./api";

type Result = NonNullable<ExplorationView["exploration"]>["results"][number];

const ROWS = 10;

function number(value?: string | null) {
  if (value == null) return "—";
  const [whole, fraction] = value.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return fraction ? `${grouped},${fraction}` : grouped;
}

function ResultCard({ result }: { result: Result }) {
  const dimensions = result.query.dimensions ?? [];
  const single =
    dimensions.length === 1 && result.rows[0]?.figures.length === 1;
  const shown = result.rows.slice(0, ROWS);
  return (
    <article className="exploration-result" aria-label={result.title}>
      <header>
        <h3>{result.title}</h3>
        <span className="badge neutral">
          {result.judged_by === "ai" ? "Juzgada por la IA" : "Por reglas"}
        </span>
      </header>
      {result.reason && <p>{result.reason}</p>}
      {single && shown.length > 1 && (
        <Chart
          option={seriesOption(
            shown.map((row) => row.groups[0]),
            shown.map((row) => Number(row.figures[0].value ?? 0)),
            "bar",
          )}
          label={result.title}
          height={220}
        />
      )}
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
      <small className="muted">
        {result.method}
        {result.total_groups > ROWS &&
          ` Se muestran ${ROWS} de ${result.total_groups} grupos.`}
      </small>
    </article>
  );
}

/** Fase 20: consultas propuestas por reglas y por la IA, calculadas sobre todas las filas. */
export function ExplorationPanel({ view }: { view: ExplorationView }) {
  if (view.state === "queued" || view.state === "running")
    return (
      <section className="comprehension" aria-label="Exploración guiada">
        <p className="muted" role="status">
          <LoaderCircle className="spin" size={14} /> Explorando las relaciones
          del negocio…
        </p>
      </section>
    );
  const exploration = view.exploration;
  if (!exploration) return null;
  const relevant = exploration.results.filter((r) => r.relevant);
  const discarded = exploration.results.filter((r) => r.relevant === false);
  const rejected = exploration.proposals.filter((p) => p.status === "rejected");
  return (
    <section className="comprehension" aria-label="Exploración guiada">
      <header className="section-heading">
        <div>
          <h2>
            <Compass size={18} aria-hidden /> Exploración guiada
          </h2>
          <p>
            Consultas propuestas por las reglas
            {exploration.ai_state === "ready" ? " y por la IA" : ""}, validadas
            y calculadas sobre todas las filas. La IA sólo vio hasta{" "}
            {exploration.limits.ai_rows} filas de cada resultado para juzgar su
            relevancia.
          </p>
        </div>
      </header>
      {relevant.length === 0 ? (
        <p className="muted">Ninguna consulta resultó relevante.</p>
      ) : (
        <div className="exploration-grid">
          {relevant.map((result) => (
            <ResultCard key={result.key} result={result} />
          ))}
        </div>
      )}
      {discarded.length > 0 && (
        <details>
          <summary>
            Descartadas por poco relevantes ({discarded.length})
          </summary>
          <ul>
            {discarded.map((r) => (
              <li key={r.key}>
                <strong>{r.title}:</strong> {r.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
      {rejected.length > 0 && (
        <details>
          <summary>
            Propuestas rechazadas por la validación ({rejected.length})
          </summary>
          <ul>
            {rejected.map((p, index) => (
              <li key={index}>
                {p.motive} — {p.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
