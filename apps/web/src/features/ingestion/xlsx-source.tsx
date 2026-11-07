"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, LoaderCircle, UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import { number } from "@/lib/utils";
import { useApp } from "@/lib/providers";
import {
  useInspectXlsx,
  useUploadXlsx,
  type XlsxInspection,
  type XlsxSelection,
} from "./api";

/** Fase 12A: elegir hoja o tabla con nombre, revisar la vista previa y sólo entonces importar. */
export function XlsxSource({
  projectId,
  file,
  onUploaded,
}: {
  projectId: string;
  file: File;
  onUploaded: () => void;
}) {
  const inspect = useInspectXlsx(projectId);
  const upload = useUploadXlsx(projectId);
  const { notify } = useApp();
  const [selection, setSelection] = useState<XlsxSelection>({
    header_row: 1,
  });
  const [result, setResult] = useState<XlsxInspection | null>(null);
  const { mutate } = inspect;

  useEffect(() => {
    mutate(
      { file, selection },
      { onSuccess: (inspection) => setResult(inspection) },
    );
  }, [file, selection, mutate]);

  const busy = inspect.isPending || upload.isPending;
  const choices =
    result?.sheets.flatMap((sheet) => [
      {
        value: `sheet:${sheet.name}`,
        label: `Hoja «${sheet.name}»${sheet.hidden ? " (oculta)" : ""}`,
      },
      ...sheet.tables.map((table) => ({
        value: `table:${table}`,
        label: `Tabla «${table}» · hoja ${sheet.name}`,
      })),
    ]) ?? [];
  const current = result
    ? result.table
      ? `table:${result.table}`
      : `sheet:${result.sheet}`
    : "";

  function choose(value: string) {
    const [kind, ...rest] = value.split(":");
    const name = rest.join(":");
    setSelection(
      kind === "table"
        ? { table: name, header_row: 1 }
        : { sheet: name, table: null, header_row: 1 },
    );
  }

  return (
    <div className="xlsx-source">
      <label htmlFor={`xlsx-choice-${projectId}`}>Hoja o tabla</label>
      <select
        id={`xlsx-choice-${projectId}`}
        disabled={busy || !result}
        value={current}
        onChange={(e) => choose(e.target.value)}
      >
        {choices.map((choice) => (
          <option key={choice.value} value={choice.value}>
            {choice.label}
          </option>
        ))}
      </select>
      {!result?.table && (
        <>
          <label htmlFor={`xlsx-header-${projectId}`}>Fila de cabecera</label>
          <input
            id={`xlsx-header-${projectId}`}
            type="number"
            min={1}
            disabled={busy || !result}
            value={selection.header_row}
            onChange={(e) => {
              const row = Number(e.target.value);
              if (Number.isInteger(row) && row >= 1)
                setSelection({
                  sheet: result?.sheet,
                  table: null,
                  header_row: row,
                });
            }}
          />
        </>
      )}
      {inspect.isPending && (
        <p className="muted">
          <LoaderCircle className="spin" size={14} /> Leyendo el libro…
        </p>
      )}
      {inspect.isError && (
        <p className="auth-error" role="alert">
          {errorMessage(inspect.error)}
        </p>
      )}
      {result?.problem && (
        <p className="auth-error" role="alert">
          {result.problem.message}
        </p>
      )}
      {result && !result.problem && (
        <>
          <p className="muted">
            Vista previa: {number(result.row_count)} registros ·{" "}
            {result.columns.length} columnas. Las fórmulas se leen con su
            resultado guardado y las fechas en formato ISO.
          </p>
          <div className="table-scroll bordered xlsx-preview">
            <table>
              <thead>
                <tr>
                  {result.columns.map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, index) => (
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
          {result.warning_count > 0 && (
            <div className="warning-banner">
              <AlertTriangle size={16} />
              <span>
                {result.warning_count} número(s) con más de 15 cifras
                significativas (p. ej. {result.warnings[0]?.cell}): Excel no los
                guarda de forma exacta.
              </span>
            </div>
          )}
        </>
      )}
      {upload.isError && (
        <p className="auth-error" role="alert">
          {errorMessage(upload.error)}
        </p>
      )}
      <Button
        disabled={busy || !result || !!result.problem}
        onClick={async () => {
          if (!result) return;
          try {
            await upload.mutateAsync({
              file,
              selection: {
                sheet: result.sheet,
                table: result.table ?? null,
                header_row: result.header_row,
              },
            });
            notify("Libro original conservado. Procesamiento encolado.");
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
        {upload.isPending ? "Enviando libro…" : "Importar esta tabla"}
      </Button>
    </div>
  );
}
