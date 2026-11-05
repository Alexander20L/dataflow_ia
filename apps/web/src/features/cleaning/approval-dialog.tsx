"use client";
import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import { useApprove, type CleaningPreview } from "./api";

export function ApprovalDialog({
  preview,
  onClose,
}: {
  preview: CleaningPreview;
  onClose: () => void;
}) {
  const approve = useApprove(preview.execution_id);
  const counts = preview.manifest!.counts;
  return (
    <Dialog title="Aprobar el efecto de la limpieza" onClose={onClose}>
      <div className="dialog-copy">
        <p>
          Apruebas exactamente este efecto, calculado sobre todo el dataset. Si
          los datos, el plan o el sistema cambian, la aplicación se detendrá sin
          publicar nada.
        </p>
        <ul className="approval-summary">
          <li>
            {counts.input_rows} registros de entrada → {counts.output_rows} de
            salida ({counts.excluded_rows} excluidos)
          </li>
          <li>
            {counts.modified_cells} celda(s) modificada(s) en{" "}
            {counts.modified_rows} registro(s)
          </li>
          <li className={counts.created_nulls ? "attention" : undefined}>
            {counts.created_nulls} nulo(s) creado(s)
          </li>
        </ul>
        <p className="mono fine-print" title={preview.effect_sha256 ?? ""}>
          Efecto SHA-256 {preview.effect_sha256}
        </p>
      </div>
      {approve.isError && (
        <p className="auth-error" role="alert">
          {errorMessage(approve.error)}
        </p>
      )}
      <div className="form-footer">
        <Button variant="ghost" onClick={onClose}>
          Volver
        </Button>
        <Button
          disabled={approve.isPending}
          onClick={async () => {
            try {
              await approve.mutateAsync(preview.effect_sha256!);
              onClose();
            } catch {
              /* Error visible. */
            }
          }}
        >
          <ShieldCheck size={16} />
          Aprobar este efecto
        </Button>
      </div>
    </Dialog>
  );
}
