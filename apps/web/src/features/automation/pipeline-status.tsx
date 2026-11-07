"use client";
import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bot, CheckCircle2, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import { InterpretationEditor } from "@/features/templates/interpretation-editor";
import {
  useCancelRun,
  useNotifications,
  useResumeRun,
  useVersionRun,
  type AutomationRun,
} from "./api";

const STEPS: Record<string, string> = {
  propose: "Proponiendo la limpieza",
  preview: "Calculando la vista previa",
  approve: "Evaluando la política",
  apply: "Aplicando la limpieza",
  diagnose: "Diagnosticando la versión derivada",
  quality_rules: "Evaluando reglas de calidad",
  select: "Activando la fuente",
  done: "Terminado",
};

/** Estado del pipeline automático de la versión que se ve (Fase 11C). */
export function PipelineStatus({
  projectId,
  versionId,
  onShowVersion,
  onShowDashboard,
}: {
  projectId: string;
  versionId: string;
  onShowVersion: (versionId: string) => void;
  onShowDashboard?: () => void;
}) {
  const run = useVersionRun(versionId);
  const cancel = useCancelRun(versionId);
  const resume = useResumeRun(versionId);
  const client = useQueryClient();
  const state = run.data?.state;
  const previous = useRef(state);
  useEffect(() => {
    // Al terminar, la fuente activa y las versiones cambian: se recargan.
    if (previous.current === "running" && state && state !== "running") {
      void client.invalidateQueries({ queryKey: ["analysis-session"] });
      void client.invalidateQueries({ queryKey: ["versions"] });
      void client.invalidateQueries({ queryKey: ["automation-notifications"] });
    }
    previous.current = state;
  }, [state, client]);
  const current: AutomationRun | null | undefined = run.data;
  if (!current) return null;
  return (
    <div
      className={`automation-status ${current.state}`}
      role="status"
      aria-label="Pipeline automático"
    >
      {current.state === "running" ? (
        <>
          <LoaderCircle size={14} className="spin" />
          <span>Automático: {STEPS[current.step] ?? current.step}…</span>
          <Button
            size="sm"
            variant="ghost"
            disabled={cancel.isPending}
            onClick={() => void cancel.mutateAsync(current.id).catch(() => {})}
          >
            Cancelar
          </Button>
        </>
      ) : current.state === "completed" ? (
        <>
          <CheckCircle2 size={14} />
          <span>
            Automático: listo.{" "}
            {current.result_version_id === versionId
              ? "No hacía falta limpiar; esta versión es la fuente activa."
              : "Se creó y activó la versión limpia."}
          </span>
          {current.result_version_id &&
            current.result_version_id !== versionId && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => onShowVersion(current.result_version_id!)}
              >
                Ver la versión limpia
              </Button>
            )}
          {current.dashboard_family_id && onShowDashboard && (
            <Button size="sm" variant="outline" onClick={onShowDashboard}>
              Ver dashboard
            </Button>
          )}
        </>
      ) : current.state === "cancelled" ? (
        <>
          <Bot size={14} />
          <span>Automático: cancelado. Puedes seguir a mano.</span>
        </>
      ) : (
        <div className="automation-review">
          <span>
            <AlertTriangle size={14} /> <strong>Revisión necesaria</strong> en «
            {STEPS[current.step] ?? current.step}». Puedes continuar a mano en
            la etapa correspondiente.
          </span>
          <ul>
            {current.reasons.map((reason, index) => (
              <li key={`${reason.code}-${index}`}>
                {reason.message}
                {reason.column ? ` Columna «${reason.column}».` : ""}
                {reason.measured
                  ? ` Medido: ${reason.measured}${reason.limit ? `; límite: ${reason.limit}` : ""}.`
                  : ""}{" "}
                <code>{reason.code}</code>
              </li>
            ))}
          </ul>
          {current.reasons.length > 0 &&
            current.reasons.every((r) => r.code.startsWith("MAPPING_")) && (
              <InterpretationEditor
                projectId={projectId}
                versionId={current.result_version_id ?? current.version_id}
                onSaved={() =>
                  void resume.mutateAsync(current.id).catch(() => {})
                }
              />
            )}
          {resume.isError && <p role="alert">{errorMessage(resume.error)}</p>}
        </div>
      )}
      {cancel.isError && <p role="alert">{errorMessage(cancel.error)}</p>}
    </div>
  );
}

/** Bandeja de avisos: pipelines del proyecto que esperan a una persona. */
export function AutomationNotices({
  projectId,
  onShowVersion,
}: {
  projectId: string;
  onShowVersion: (versionId: string) => void;
}) {
  const notices = useNotifications();
  const items = (notices.data ?? []).filter(
    (run) => run.project_id === projectId,
  );
  if (!items.length) return null;
  return (
    <details className="automation-notices" open>
      <summary>
        <AlertTriangle size={14} /> {items.length} carga(s) automáticas esperan
        revisión
      </summary>
      <ul>
        {items.map((run) => (
          <li key={run.id}>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onShowVersion(run.version_id)}
            >
              Ver la versión
            </Button>{" "}
            {run.reasons[0]?.message ?? "Revisión necesaria."}
          </li>
        ))}
      </ul>
    </details>
  );
}
