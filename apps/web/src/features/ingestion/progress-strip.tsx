"use client";

import { CheckCircle2, Circle, LoaderCircle, XCircle } from "lucide-react";
import type { VersionProgress } from "./api";

function StageIcon({ state }: { state: string }) {
  if (state === "done") return <CheckCircle2 size={14} aria-hidden />;
  if (state === "running" || state === "queued")
    return <LoaderCircle className="spin" size={14} aria-hidden />;
  if (state === "failed") return <XCircle size={14} aria-hidden />;
  return <Circle size={14} aria-hidden />;
}

const STATES: Record<string, string> = {
  pending: "Pendiente",
  queued: "En cola",
  running: "En curso",
  done: "Listo",
  failed: "No terminó",
  skipped: "No aplica",
};

/** Fase 28: el progreso de la carga por etapas, encima de las pestañas y visible desde todas
 * (antes estaba en el resumen de la pestaña Análisis). El informe se descarga en su pestaña. */
export function ProgressStrip({ progress }: { progress?: VersionProgress }) {
  if (!progress) return null;
  return (
    <ol
      className={`progress-strip ${progress.complete ? "complete" : ""}`}
      aria-label="Progreso de la carga"
    >
      {progress.stages.map((stage) => (
        <li
          key={stage.id}
          className={`delivery-stage ${stage.state}`}
          title={stage.detail}
        >
          <StageIcon state={stage.state} />
          <span>
            {stage.title} · {STATES[stage.state]}
          </span>
        </li>
      ))}
    </ol>
  );
}
