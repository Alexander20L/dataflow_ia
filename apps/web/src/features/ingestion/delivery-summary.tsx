"use client";

import {
  CheckCircle2,
  Circle,
  Download,
  LoaderCircle,
  XCircle,
} from "lucide-react";
import { capDecimalsInText } from "@/lib/numbers";
import { useReport } from "./api";
import type { AutomaticAnalysis, VersionProgress } from "./api";

const TOP = 3;

function StageIcon({ state }: { state: string }) {
  if (state === "done") return <CheckCircle2 size={16} aria-hidden />;
  if (state === "running" || state === "queued")
    return <LoaderCircle className="spin" size={16} aria-hidden />;
  if (state === "failed") return <XCircle size={16} aria-hidden />;
  return <Circle size={16} aria-hidden />;
}

const STATES: Record<string, string> = {
  pending: "Pendiente",
  queued: "En cola",
  running: "En curso",
  done: "Listo",
  failed: "No terminó",
  skipped: "No aplica",
};

/** Fase 17: lo primero que se ve de una carga terminada. */
export function DeliverySummary({
  versionId,
  progress,
  analysis,
}: {
  versionId: string;
  progress?: VersionProgress;
  analysis?: AutomaticAnalysis;
}) {
  const report = progress?.stages.find((stage) => stage.id === "report");
  // Fase 21: el informe anterior sigue disponible mientras se genera otro con tus marcas.
  const view = useReport(
    versionId,
    report !== undefined && report.state !== "pending",
  ).data;
  const ready = report?.state === "done" || view?.state === "ready";
  const key = [...(analysis?.insights ?? [])]
    .sort((a, b) => b.importance - a.importance)
    .slice(0, TOP);
  return (
    <section className="delivery-summary" aria-label="Resumen">
      <header className="section-heading">
        <div>
          <h2>Resumen</h2>
          <p>
            Todo se hace automáticamente al subir el archivo: análisis,
            investigación de los hallazgos e informe en PDF.
          </p>
        </div>
        {ready ? (
          <div className="delivery-download">
            <a
              className="btn btn-sm"
              href={`/api/v1/versions/${versionId}/report.pdf`}
            >
              <Download size={14} />
              Descargar informe (PDF)
            </a>
            {view?.updating && (
              <small className="muted" role="status">
                Generando una versión con tus marcas…
              </small>
            )}
          </div>
        ) : null}
      </header>
      {progress && (
        <ol className="delivery-stages" aria-label="Progreso de la carga">
          {progress.stages.map((stage) => (
            <li key={stage.id} className={`delivery-stage ${stage.state}`}>
              <StageIcon state={stage.state} />
              <span>
                <strong>{stage.title}</strong> · {STATES[stage.state]}
                <small>{stage.detail}</small>
              </span>
            </li>
          ))}
        </ol>
      )}
      {key.length > 0 && (
        <div className="delivery-findings">
          <h3>Hallazgos principales</h3>
          <ul>
            {key.map((insight) => (
              <li key={insight.id}>
                <strong>{insight.title}.</strong>{" "}
                {capDecimalsInText(insight.statement)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {report && !ready && (
        <p className="muted" role="status">
          {report.state === "pending" ||
          report.state === "queued" ||
          report.state === "running"
            ? "El informe en PDF estará disponible al terminar la investigación."
            : `Informe no disponible: ${report.detail}`}
        </p>
      )}
    </section>
  );
}
