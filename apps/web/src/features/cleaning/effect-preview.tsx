"use client";
import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  LoaderCircle,
  RotateCcw,
  Wand2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import { ApprovalDialog } from "./approval-dialog";
import { BeforeAfter } from "./before-after";
import {
  useApply,
  useCleaningPreview,
  useRevoke,
  type CleaningPreview,
} from "./api";

const MISMATCH =
  "Los datos, el plan o el sistema cambiaron desde la vista previa. Genera una vista previa nueva y vuelve a aprobar.";

export function EffectPreview({
  executionId,
  projectId,
  archived,
  onRepeat,
  onShowDerived,
}: {
  executionId: string;
  projectId: string;
  archived: boolean;
  onRepeat: () => void;
  onShowDerived: (parentVersionId: string) => void;
}) {
  const preview = useCleaningPreview(executionId);
  if (preview.isPending)
    return (
      <p className="empty-copy" role="status">
        Cargando la vista previa…
      </p>
    );
  if (preview.isError)
    return (
      <p className="auth-error" role="alert">
        {errorMessage(preview.error)}
      </p>
    );
  const data = preview.data;
  if (data.state === "queued" || data.state === "running")
    return (
      <div className="processing-state" role="status">
        <LoaderCircle className="spin" size={26} />
        <h3>Calculando el efecto sobre todo el dataset…</h3>
        <p>La vista previa no crea versiones ni modifica tus datos.</p>
      </div>
    );
  if (data.state !== "succeeded" || !data.manifest)
    return (
      <div className="empty-state compact">
        <p role="alert">
          {data.error_code}: {data.error_message ?? "La vista previa falló."}
        </p>
        <Button variant="outline" onClick={onRepeat}>
          <RotateCcw size={15} /> Repetir vista previa
        </Button>
      </div>
    );
  return (
    <Effect
      preview={data}
      projectId={projectId}
      archived={archived}
      onRepeat={onRepeat}
      onShowDerived={onShowDerived}
    />
  );
}

function Effect({
  preview,
  projectId,
  archived,
  onRepeat,
  onShowDerived,
}: {
  preview: CleaningPreview;
  projectId: string;
  archived: boolean;
  onRepeat: () => void;
  onShowDerived: (parentVersionId: string) => void;
}) {
  const [approving, setApproving] = useState(false);
  const apply = useApply(preview.execution_id, projectId);
  const revoke = useRevoke(preview.execution_id);
  const counts = preview.manifest!.counts;
  const names = Object.fromEntries(
    (preview.manifest!.output.columns as { id: string; name: string }[]).map(
      (column) => [column.id, column.name],
    ),
  );
  const approval = preview.approval;
  const applied = preview.apply;
  const affected = counts.modified_rows + counts.excluded_rows;
  return (
    <section className="effect-preview" aria-label="Vista previa del efecto">
      <div className="mini-metrics effect-counts">
        <div>
          <small>Registros de entrada</small>
          <strong>{counts.input_rows}</strong>
        </div>
        <div>
          <small>Registros de salida</small>
          <strong>{counts.output_rows}</strong>
        </div>
        <div>
          <small>Excluidos</small>
          <strong>{counts.excluded_rows}</strong>
        </div>
        <div>
          <small>Celdas modificadas</small>
          <strong>{counts.modified_cells}</strong>
        </div>
        <div className={counts.created_nulls ? "attention" : undefined}>
          <small>Nulos creados</small>
          <strong data-testid="created-nulls">{counts.created_nulls}</strong>
        </div>
      </div>
      {counts.created_nulls > 0 && (
        <div className="warning-banner" role="status">
          <AlertTriangle size={16} />
          <span>
            Esta limpieza convierte {counts.created_nulls} celda(s) en nulo. La
            completitud de la nueva versión puede bajar: limpiar no equivale a
            más datos completos.
          </span>
        </div>
      )}
      <BeforeAfter samples={preview.samples} names={names} total={affected} />
      <p className="mono fine-print" title={preview.effect_sha256 ?? ""}>
        Efecto SHA-256 {preview.effect_sha256?.slice(0, 24)}… · plan{" "}
        {preview.plan_revision_id.slice(0, 8)}
      </p>
      {applied?.state === "succeeded" ? (
        <div className="success-banner" role="status">
          <CheckCircle2 size={16} />
          <span>
            Versión derivada creada. El original y la versión de origen no
            cambian; la nueva versión no pasa a ser la predeterminada.
          </span>
          <Button size="sm" onClick={() => onShowDerived(preview.version_id)}>
            Ver la versión derivada
          </Button>
        </div>
      ) : applied?.state === "queued" || applied?.state === "running" ? (
        <div className="processing-state compact" role="status">
          <LoaderCircle className="spin" size={20} />
          <span>Aplicando la limpieza y publicando la versión derivada…</span>
        </div>
      ) : applied?.state === "failed" ? (
        <div className="warning-banner" role="alert">
          <AlertTriangle size={16} />
          <span>
            {applied.error_code === "PREVIEW_EFFECT_MISMATCH"
              ? MISMATCH
              : `${applied.error_code}: ${applied.error_message}`}
          </span>
          <Button size="sm" variant="outline" onClick={onRepeat}>
            <RotateCcw size={15} /> Repetir vista previa
          </Button>
        </div>
      ) : null}
      {(apply.isError || revoke.isError) && (
        <p className="auth-error" role="alert">
          {errorMessage(apply.error ?? revoke.error)}
        </p>
      )}
      <div className="form-footer">
        <span className="fine-print muted">
          {approval
            ? `Aprobada el ${new Date(approval.approved_at).toLocaleString("es-ES")}`
            : "Revisa el efecto antes de aprobarlo."}
        </span>
        {!approval ? (
          <Button disabled={archived} onClick={() => setApproving(true)}>
            <Wand2 size={16} /> Aprobar efecto…
          </Button>
        ) : (
          <>
            {(!applied || applied.state === "queued") && (
              <Button
                variant="outline"
                disabled={archived || revoke.isPending}
                onClick={() =>
                  void revoke.mutateAsync(approval.id).catch(() => {})
                }
              >
                Revocar aprobación
              </Button>
            )}
            {!applied && (
              <Button
                disabled={archived || apply.isPending}
                onClick={() =>
                  void apply.mutateAsync(approval.id).catch(() => {})
                }
              >
                Aplicar limpieza
              </Button>
            )}
          </>
        )}
      </div>
      {approving && (
        <ApprovalDialog preview={preview} onClose={() => setApproving(false)} />
      )}
    </section>
  );
}
