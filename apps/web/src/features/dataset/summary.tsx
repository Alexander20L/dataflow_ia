"use client";

import type { InspectionView } from "./api";
import {
  FORMATS,
  GROUPS,
  encodingLabel,
  formatBytes,
  formatNumber,
  formatPercent,
  separatorLabel,
  type Group,
} from "./labels";

const ORDER: Group[] = [
  "numeric",
  "categorical",
  "temporal",
  "identifier",
  "other",
];

/** Resumen: indicadores y metadatos tal como los calculó el servidor sobre todos los registros. */
export function SummaryView({ view }: { view: InspectionView }) {
  const inspection = view.inspection!;
  const { summary, file } = inspection;
  const groups = view.groups ?? summary.groups;
  const total = summary.columns || 1;
  const metrics: [string, string][] = [
    ["Registros", formatNumber(summary.rows)],
    ["Columnas", formatNumber(summary.columns)],
    ["Celdas", formatNumber(summary.cells)],
    ["Completitud", formatPercent(summary.completeness_percent)],
    ["Valores faltantes", formatNumber(summary.missing_cells)],
    ["Filas duplicadas", formatNumber(summary.duplicate_rows)],
    ["Memoria estimada", formatBytes(summary.memory_bytes)],
  ];
  return (
    <div className="dataset-summary">
      <dl className="dataset-metrics" aria-label="Indicadores del dataset">
        {metrics.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <div className="dataset-columns-2">
        <section aria-label="Metadatos del archivo">
          <h3>Archivo</h3>
          <dl className="dataset-facts">
            <div>
              <dt>Nombre</dt>
              <dd>{file.file_name}</dd>
            </div>
            <div>
              <dt>Formato</dt>
              <dd>{FORMATS[file.format] ?? file.format}</dd>
            </div>
            <div>
              <dt>Fecha de carga</dt>
              <dd>{new Date(file.uploaded_at).toLocaleString("es-ES")}</dd>
            </div>
            {file.format === "xlsx" && (
              <div>
                <dt>Hoja seleccionada</dt>
                <dd>
                  {file.sheet ?? "No disponible"}
                  {file.table ? ` · tabla ${file.table}` : ""}
                </dd>
              </div>
            )}
            <div>
              <dt>Filas × columnas</dt>
              <dd>
                {formatNumber(summary.rows)} × {formatNumber(summary.columns)}
              </dd>
            </div>
            {file.format === "csv" && (
              <div>
                <dt>Lectura</dt>
                <dd>
                  {encodingLabel(file.encoding)} ·{" "}
                  {separatorLabel(file.separator)}
                  {file.decimal_convention
                    ? ` · ${file.decimal_convention}`
                    : ""}
                </dd>
              </div>
            )}
          </dl>
        </section>
        <section aria-label="Columnas por clasificación">
          <h3>Columnas por clasificación</h3>
          <ul className="dataset-bars">
            {ORDER.map((group) => (
              <li key={group}>
                <span>{GROUPS[group]}</span>
                <span className="dataset-bar" aria-hidden>
                  <span
                    style={{
                      width: `${((groups[group] ?? 0) / total) * 100}%`,
                    }}
                  />
                </span>
                <strong>{groups[group] ?? 0}</strong>
              </li>
            ))}
          </ul>
          <p className="muted">
            Clasificación vigente: la automática con tus correcciones del
            Diccionario.
          </p>
        </section>
      </div>
      {inspection.periods.map((period) => (
        <p key={period.columns.join("|")} className="info-banner">
          {period.columns.join(" + ")}: {period.note} ({period.periods} periodos
          {period.first ? `, de ${period.first} a ${period.last}` : ""}
          {period.unparsed_rows
            ? `; ${period.unparsed_rows} registros sin interpretar`
            : ""}
          ).
        </p>
      ))}
      <details>
        <summary>Cómo se calculó</summary>
        <ul className="dataset-notes">
          {inspection.limitations.map((item) => (
            <li key={item}>{item}</li>
          ))}
          <li>
            Reglas: {inspection.scope.rules} · calculado el{" "}
            {new Date(inspection.scope.computed_at).toLocaleString("es-ES")}.
          </li>
        </ul>
      </details>
    </div>
  );
}
