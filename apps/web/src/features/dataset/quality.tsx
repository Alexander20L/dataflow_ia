"use client";

import { useState } from "react";
import type { Inspection } from "./api";
import {
  DIMENSIONS,
  SEVERITIES,
  SEVERITY_BADGE,
  formatNumber,
  formatPercent,
  type Dimension,
} from "./labels";

const ORDER: Dimension[] = [
  "completeness",
  "uniqueness",
  "validity",
  "consistency",
  "format",
  "integrity",
];

/** Calidad: diagnóstico verificable por dimensión. No elimina, corrige ni descarta nada. */
export function QualityView({ inspection }: { inspection: Inspection }) {
  const [dimension, setDimension] = useState<Dimension | "all">("all");
  const findings = inspection.findings.filter(
    (f) => dimension === "all" || f.dimension === dimension,
  );
  const counts = Object.fromEntries(
    ORDER.map((d) => [
      d,
      inspection.findings.filter((f) => f.dimension === d).length,
    ]),
  ) as Record<Dimension, number>;
  return (
    <div className="dataset-quality">
      <p className="info-banner">
        Completitud: {formatPercent(inspection.summary.completeness_percent)} ·{" "}
        {formatNumber(inspection.summary.duplicate_rows)} filas duplicadas. El
        diagnóstico informa; no elimina duplicados, no corrige valores y no
        descarta valores extremos.
      </p>
      <div
        className="chip-options"
        role="group"
        aria-label="Filtrar por dimensión"
      >
        <button
          type="button"
          aria-pressed={dimension === "all"}
          onClick={() => setDimension("all")}
        >
          Todas ({inspection.findings.length})
        </button>
        {ORDER.map((d) => (
          <button
            key={d}
            type="button"
            aria-pressed={dimension === d}
            onClick={() => setDimension(d)}
          >
            {DIMENSIONS[d]} ({counts[d]})
          </button>
        ))}
      </div>
      {findings.length === 0 ? (
        <p className="empty-copy">
          {dimension === "all"
            ? "No se detectaron incidencias con las reglas de esta versión."
            : `Sin incidencias de ${DIMENSIONS[dimension].toLowerCase()}.`}
        </p>
      ) : (
        <ul className="dataset-findings" aria-label="Incidencias de calidad">
          {findings.map((finding) => (
            <li key={finding.id} className="dataset-finding">
              <header>
                <span className={`badge ${SEVERITY_BADGE[finding.severity]}`}>
                  {SEVERITIES[finding.severity]}
                </span>
                <span className="badge neutral">
                  {DIMENSIONS[finding.dimension]}
                </span>
                <h4>{finding.title}</h4>
              </header>
              <p>{finding.description}</p>
              <dl className="dataset-facts">
                <div>
                  <dt>Columnas</dt>
                  <dd>
                    {finding.columns.length
                      ? finding.columns.join(", ")
                      : "Todas"}
                  </dd>
                </div>
                <div>
                  <dt>Registros afectados</dt>
                  <dd>
                    {formatNumber(finding.affected_rows)} (
                    {formatPercent(finding.percent)})
                  </dd>
                </div>
                {finding.examples.length > 0 && (
                  <div>
                    <dt>Ejemplos</dt>
                    <dd>{finding.examples.map((e) => `«${e}»`).join(", ")}</dd>
                  </div>
                )}
                {finding.sample_rows.length > 0 && (
                  <div>
                    <dt>Filas de ejemplo</dt>
                    <dd>{finding.sample_rows.join(", ")}</dd>
                  </div>
                )}
              </dl>
              <small className="muted">Regla: {finding.source}</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
