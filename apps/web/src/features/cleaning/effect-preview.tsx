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
import {
  ApprovalOriginNote,
  PolicyApproveButton,
} from "@/features/automation/policy-approval";
import { ApprovalDialog } from "./approval-dialog";
import { BeforeAfter } from "./before-after";
import {
  cell,
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
  if (data.state === "failed" && data.failure)
    return <Failure preview={data} onRepeat={onRepeat} />;
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

const REASONS: Record<string, string> = {
  whitespace: "Espacios en los bordes",
  exponent: "Notación exponencial",
  leading_zero: "Ceros a la izquierda",
  invalid_format: "Formato no válido",
  out_of_range: "Fuera de rango (int64)",
  precision_exceeded: "Más de 38 dígitos",
  invalid_date: "Fecha inexistente",
  invalid_boolean: "No es true/false",
  null_key: "Clave nula",
};

/** Política estricta: un solo valor que no convierte impide publicar. Se listan todos los
 * motivos con el conteo exacto y hasta 50 casos. */
function Failure({
  preview,
  onRepeat,
}: {
  preview: CleaningPreview;
  onRepeat: () => void;
}) {
  const failure = preview.failure!;
  const title =
    failure.code === "NULL_KEY_REJECTED"
      ? `${failure.total} registro(s) tienen nulos en la clave de deduplicación`
      : `${failure.total} valor(es) no se pueden convertir`;
  return (
    <section
      className="effect-preview failure-list"
      aria-label="Valores que impiden la limpieza"
    >
      <div className="warning-banner" role="alert">
        <AlertTriangle size={16} />
        <span>
          <strong>{title}.</strong> No se publica ninguna versión ni se puede
          aprobar este efecto. Corrige el plan (por ejemplo, añade «Recortar
          espacios» o cambia el formato) o los datos y genera otra vista previa.
        </span>
      </div>
      <div className="table-scroll bordered">
        <table aria-label="Valores que no convierten">
          <thead>
            <tr>
              <th>Columna</th>
              <th>Registro</th>
              <th>Valor</th>
              <th>Motivo</th>
            </tr>
          </thead>
          <tbody>
            {failure.samples.map((sample) => (
              <tr key={`${sample.column_id}-${sample.source_row}`}>
                <td>{sample.column}</td>
                <td>{sample.source_row}</td>
                <td className="csv-value">{cell(sample.value)}</td>
                <td title={sample.message}>
                  {REASONS[sample.reason] ?? sample.reason}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="fine-print muted" data-testid="failure-total">
        Se muestran {failure.samples.length} de {failure.total}. Los conteos
        salen del dataset completo.
      </p>
      <div className="form-footer">
        <Button variant="outline" onClick={onRepeat}>
          <RotateCcw size={15} /> Repetir vista previa
        </Button>
      </div>
    </section>
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
  const rounded = preview.manifest!.rounded_cells ?? 0;
  const converted = (
    preview.manifest!.output.columns as {
      name: string;
      technical_type?: string;
      type_parameters?: { scale?: number };
    }[]
  ).filter((column) => (column.technical_type ?? "string") !== "string");
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
        <div className={rounded ? "attention" : undefined}>
          <small>Redondeadas</small>
          <strong data-testid="rounded-cells">{rounded}</strong>
        </div>
      </div>
      {converted.length > 0 && (
        <p className="fine-print" data-testid="output-types">
          Tipos de la nueva versión:{" "}
          {converted
            .map(
              (column) =>
                `${column.name} → ${column.technical_type}${
                  column.type_parameters?.scale !== undefined
                    ? ` (${column.type_parameters.scale} decimales)`
                    : ""
                }`,
            )
            .join(" · ")}
        </p>
      )}
      {rounded > 0 && (
        <div className="warning-banner" role="status">
          <AlertTriangle size={16} />
          <span>
            {rounded} valor(es) se redondean a la escala elegida (mitad al par).
            Revisa los ejemplos antes de aprobar.
          </span>
        </div>
      )}
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
          {approval && <ApprovalOriginNote approvalId={approval.id} />}
        </span>
        {!approval ? (
          <>
            <PolicyApproveButton
              executionId={preview.execution_id}
              disabled={archived}
            />
            <Button disabled={archived} onClick={() => setApproving(true)}>
              <Wand2 size={16} /> Aprobar efecto…
            </Button>
          </>
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
