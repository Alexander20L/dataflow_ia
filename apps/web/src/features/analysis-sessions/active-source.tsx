"use client";
import { useState } from "react";
import { History, LoaderCircle, Target } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import type { DatasetVersion } from "@/features/ingestion/api";
import {
  useProjectSession,
  useSelectSource,
  useSessionHistory,
  type SessionInput,
} from "./api";

const describe = (input: SessionInput) =>
  `v${input.version_number} · ${input.file_name}${input.version_kind === "derived" ? " (derivada)" : ""}`;

/**
 * Fuente activa del proyecto (Fase 11A): una sola tabla a la vez. Sustituirla es explícito y
 * no cambia planes ni resultados de la fuente anterior.
 */
export function ActiveSource({
  projectId,
  viewed,
  archived,
  onShowVersion,
}: {
  projectId: string;
  viewed: DatasetVersion;
  archived: boolean;
  onShowVersion: (versionId: string) => void;
}) {
  const session = useProjectSession(projectId);
  const select = useSelectSource(projectId);
  const [confirming, setConfirming] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const current = session.data ?? null;
  const history = useSessionHistory(current?.id ?? null, showHistory);
  const active = current?.active ?? null;
  const viewedIsActive = active?.version_id === viewed.id;
  const canSelect =
    !archived && viewed.state === "succeeded" && !viewedIsActive;

  if (session.isPending)
    return (
      <p className="active-source" role="status">
        Cargando la fuente activa…
      </p>
    );
  return (
    <div className="active-source" role="region" aria-label="Fuente activa">
      <span className="active-source-label">
        <Target size={14} />
        Fuente activa:{" "}
        {active ? (
          <strong data-testid="active-source">{describe(active)}</strong>
        ) : (
          <strong data-testid="active-source">ninguna</strong>
        )}
        {viewedIsActive && (
          <span className="badge completed">Es la que estás viendo</span>
        )}
      </span>
      {active && !viewedIsActive && (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onShowVersion(active.version_id)}
        >
          Ver fuente activa
        </Button>
      )}
      {canSelect && (
        <Button
          size="sm"
          variant="outline"
          disabled={select.isPending}
          onClick={() => {
            select.reset();
            setConfirming(true);
          }}
        >
          Usar v{viewed.number} como fuente activa
        </Button>
      )}
      {current && current.revision > 0 && (
        <Button
          size="sm"
          variant="ghost"
          aria-expanded={showHistory}
          onClick={() => setShowHistory(!showHistory)}
        >
          <History size={14} />
          Historial ({current.revision})
        </Button>
      )}
      {session.isError && <p role="alert">{errorMessage(session.error)}</p>}
      {showHistory && (
        <ol className="active-source-history" aria-label="Historial de fuentes">
          {history.isPending ? (
            <li>Cargando…</li>
          ) : history.isError ? (
            <li role="alert">{errorMessage(history.error)}</li>
          ) : (
            history.data.items.map((item) => (
              <li key={item.revision}>
                <span className="mono">#{item.revision}</span> {describe(item)}{" "}
                · {new Date(item.selected_at).toLocaleString()}
              </li>
            ))
          )}
        </ol>
      )}
      {confirming && (
        <Dialog
          title="¿Cambiar la fuente activa?"
          onClose={() => setConfirming(false)}
        >
          <p className="dialog-copy">
            {active
              ? `La fuente activa pasará de ${describe(active)} a v${viewed.number}. `
              : `v${viewed.number} pasará a ser la fuente activa del proyecto. `}
            Los planes, análisis y resultados existentes no cambian: cada uno
            conserva la tabla con la que se calculó.
          </p>
          {select.isError && (
            <p className="auth-error" role="alert">
              {errorMessage(select.error)}
            </p>
          )}
          <div className="form-footer">
            <Button variant="ghost" onClick={() => setConfirming(false)}>
              Cancelar
            </Button>
            <Button
              disabled={select.isPending}
              onClick={() =>
                select.mutate(
                  { session: current, versionId: viewed.id },
                  { onSuccess: () => setConfirming(false) },
                )
              }
            >
              {select.isPending && <LoaderCircle size={14} className="spin" />}
              Usar como fuente activa
            </Button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
