"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, LoaderCircle, UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import { useApp } from "@/lib/providers";
import { useInspectPdf, useUploadPdf, type PdfInspection } from "./api";

/** Fase 12C: la persona elige la tabla (nunca se elige sola) y, si continúa en otras
 * páginas, confirma la unión marcando también sus continuaciones. */
export function PdfSource({
  projectId,
  file,
  onUploaded,
}: {
  projectId: string;
  file: File;
  onUploaded: () => void;
}) {
  const inspect = useInspectPdf(projectId);
  const upload = useUploadPdf(projectId);
  const { notify } = useApp();
  const [result, setResult] = useState<PdfInspection | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const { mutate } = inspect;

  useEffect(() => {
    mutate(file, { onSuccess: (inspection) => setResult(inspection) });
  }, [file, mutate]);

  const tables = result?.tables ?? [];
  const first = tables.find((t) => t.id === chosen[0]);
  const blocked = !!first?.issues.length;
  const busy = inspect.isPending || upload.isPending;

  return (
    <div className="xlsx-source">
      {inspect.isPending && (
        <p className="muted">
          <LoaderCircle className="spin" size={14} /> Buscando tablas en el PDF…
        </p>
      )}
      {inspect.isError && (
        <p className="auth-error" role="alert">
          {errorMessage(inspect.error)}
        </p>
      )}
      {result && !tables.length && (
        <p className="auth-error" role="alert">
          No se encontraron tablas con rejilla en este PDF.
        </p>
      )}
      {tables.length > 0 && (
        <p className="muted">
          {tables.length} tabla(s) candidata(s) en {result?.pages} página(s).
          Elige una; marca varias sólo si es la misma tabla que continúa en
          otras páginas (se unirán en ese orden).
        </p>
      )}
      {tables.map((table) => {
        const position = chosen.indexOf(table.id);
        return (
          <div key={table.id} className="pdf-candidate">
            <label className="check">
              <input
                type="checkbox"
                checked={position >= 0}
                disabled={busy}
                onChange={(e) =>
                  setChosen(
                    e.target.checked
                      ? [...chosen, table.id]
                      : chosen.filter((id) => id !== table.id),
                  )
                }
              />
              <strong>
                Página {table.page} · tabla {table.index}
              </strong>
              <span className="muted">
                {table.row_count} filas · {table.columns.length} columnas
                {position >= 0 && chosen.length > 1
                  ? ` · parte ${position + 1}`
                  : ""}
              </span>
            </label>
            {table.issues.length > 0 && (
              <div className="warning-banner">
                <AlertTriangle size={16} />
                <span>{table.issues.join(" ")}</span>
              </div>
            )}
            <div className="table-scroll bordered xlsx-preview">
              <table>
                <thead>
                  <tr>
                    {table.columns.map((column, index) => (
                      <th key={index}>{column ?? "(vacía)"}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.rows.map((row, index) => (
                    <tr key={index}>
                      {row.map((cell, position) => (
                        <td
                          key={position}
                          className={cell === null ? "muted" : ""}
                        >
                          {cell ?? "nulo"}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
      {chosen.length > 1 && (
        <p className="muted">
          Confirmas que {chosen.length} tablas son una sola tabla que continúa
          en varias páginas.
        </p>
      )}
      {upload.isError && (
        <p className="auth-error" role="alert">
          {errorMessage(upload.error)}
        </p>
      )}
      <Button
        disabled={!chosen.length || blocked || busy}
        onClick={async () => {
          try {
            await upload.mutateAsync({ file, tables: chosen });
            notify("PDF original conservado. Procesamiento encolado.");
            onUploaded();
          } catch {
            /* Error visible y clave de reintento conservada. */
          }
        }}
      >
        {upload.isPending ? (
          <LoaderCircle className="spin" size={16} />
        ) : (
          <UploadCloud size={16} />
        )}
        {upload.isPending ? "Enviando PDF…" : "Importar tabla elegida"}
      </Button>
    </div>
  );
}
