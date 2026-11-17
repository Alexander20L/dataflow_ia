"use client";

import { Download } from "lucide-react";
import type { Inspection } from "./api";
import {
  FORMATS,
  encodingLabel,
  formatBytes,
  formatNumber,
  separatorLabel,
} from "./labels";

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

const missing = "No disponible";

/** Archivo: cómo se leyó el original y con qué reglas. Nada de esto cambia el archivo. */
export function FileView({
  inspection,
  versionId,
}: {
  inspection: Inspection;
  versionId: string;
}) {
  const file = inspection.file;
  const isCsv = file.format === "csv" || file.format === "sqlserver";
  return (
    <div className="inspection-file">
      <div className="dataset-columns-2">
        <section aria-label="Lectura del original">
          <h3>{FORMATS[file.format] ?? file.format}</h3>
          <dl className="dataset-facts">
            <Fact label="Archivo" value={file.file_name} />
            <Fact label="Tamaño" value={formatBytes(file.size_bytes)} />
            {isCsv && (
              <>
                <Fact
                  label="Codificación"
                  value={encodingLabel(file.encoding)}
                />
                <Fact
                  label="Delimitador"
                  value={separatorLabel(file.separator)}
                />
                <Fact
                  label="Separador decimal"
                  value={
                    file.decimal_convention ??
                    "Punto (no hizo falta convertir números)"
                  }
                />
                <Fact
                  label="Líneas en blanco omitidas"
                  value={
                    file.blank_lines == null
                      ? missing
                      : formatNumber(file.blank_lines)
                  }
                />
              </>
            )}
            <Fact
              label="Convención de fechas"
              value={
                file.date_convention ?? "Sin fechas regionales convertidas"
              }
            />
            <Fact label="Encabezados" value={file.header} />
            {file.format === "xlsx" && (
              <>
                <Fact
                  label="Hoja seleccionada"
                  value={`${file.sheet ?? missing}${file.table ? ` · tabla ${file.table}` : ""}`}
                />
                <Fact
                  label="Rango utilizado"
                  value={file.used_range ?? missing}
                />
                <Fact
                  label="Filas vacías en el rango"
                  value={
                    file.empty_rows == null
                      ? missing
                      : formatNumber(file.empty_rows)
                  }
                />
                <Fact
                  label="Columnas vacías"
                  value={
                    file.empty_columns?.length
                      ? file.empty_columns.join(", ")
                      : "Ninguna"
                  }
                />
                <Fact
                  label="Celdas con fórmula"
                  value={
                    file.formula_cells == null
                      ? missing
                      : `${formatNumber(file.formula_cells)} (se lee el resultado guardado)`
                  }
                />
                <Fact
                  label="Celdas con formato de fecha"
                  value={
                    file.date_cells == null
                      ? missing
                      : formatNumber(file.date_cells)
                  }
                />
                {Boolean(file.inexact_numbers) && (
                  <Fact
                    label="Números con más de 15 cifras"
                    value={formatNumber(file.inexact_numbers ?? 0)}
                  />
                )}
              </>
            )}
          </dl>
          <a
            className="btn btn-outline btn-sm"
            href={`/api/v1/versions/${versionId}/original`}
          >
            <Download size={14} aria-hidden /> Descargar original sin cambios
          </a>
        </section>
        <section aria-label="Reglas de lectura">
          <h3>Reglas aplicadas</h3>
          <ul className="dataset-notes">
            {file.rules.map((rule) => (
              <li key={rule}>{rule}</li>
            ))}
          </ul>
          {file.format === "xlsx" && (file.sheets?.length ?? 0) > 0 && (
            <>
              <h3>Hojas del libro</h3>
              <ul className="dataset-notes" aria-label="Hojas del libro">
                {file.sheets!.map((sheet) => (
                  <li key={sheet.name}>
                    {sheet.name}
                    {sheet.selected ? " · esta versión" : ""}
                    {sheet.hidden ? " · oculta" : ""}
                    {sheet.tables.length
                      ? ` · tablas: ${sheet.tables.join(", ")}`
                      : ""}
                  </li>
                ))}
              </ul>
              <p className="muted">
                Cada hoja con datos se analiza como una versión propia; las
                hojas nunca se combinan.
              </p>
            </>
          )}
        </section>
      </div>
      {((file.converted?.length ?? 0) > 0 ||
        (file.kept_as_text?.length ?? 0) > 0 ||
        (file.problems?.length ?? 0) > 0) && (
        <section aria-label="Interpretación de valores">
          <h3>Interpretación de valores</h3>
          <ul className="dataset-notes">
            {file.converted?.map((item) => (
              <li key={`c-${item.column}`}>
                <strong>{item.column}</strong>: {item.explanation}
              </li>
            ))}
            {file.kept_as_text?.map((item) => (
              <li key={`k-${item.column}`}>
                <strong>{item.column}</strong>: se dejó como texto.{" "}
                {item.reason}
              </li>
            ))}
            {file.problems?.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      )}
      <p className="muted">
        SHA-256 del original: <code>{file.sha256}</code>
      </p>
    </div>
  );
}
