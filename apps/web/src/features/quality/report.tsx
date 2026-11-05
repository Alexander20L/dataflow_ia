"use client";
import { ShieldCheck } from "lucide-react";
import { number } from "@/lib/utils";
import type { QualityRulesReport } from "./api";

const KINDS: Record<string, string> = {
  required: "Obligatoria",
  unique_key: "Clave única",
  range: "Rango",
  allowed_values: "Catálogo de valores",
  convertible: "Formato convertible",
};
const SEVERITY: Record<string, string> = {
  low: "baja",
  medium: "media",
  high: "alta",
};

/** Informe csv-quality-v2: completitud técnica y reglas de negocio, siempre por separado. */
export function RulesReport({ report }: { report: QualityRulesReport }) {
  const technical = report.issues.filter((i) => i.origin === "technical");
  const user = report.issues.filter((i) => i.origin === "user");
  return (
    <div className="rules-report">
      <section aria-label="Calidad técnica">
        <h4>Calidad técnica · Q-001 a Q-003</h4>
        <div className="mini-metrics">
          <div>
            <small>Completitud de celdas</small>
            <strong data-testid="technical-completeness">
              {report.technical.completeness_percent.toLocaleString("es-ES")} %
            </strong>
          </div>
          <div>
            <small>Celdas vacías</small>
            <strong>{number(report.technical.missing_cells)}</strong>
          </div>
          <div>
            <small>Incidencias técnicas</small>
            <strong>{technical.length}</strong>
          </div>
        </div>
      </section>
      <section aria-label="Reglas de negocio">
        <h4>
          Reglas de negocio · {report.user.rules_failed} de{" "}
          {report.user.rules_evaluated} con incidencias
        </h4>
        {user.length ? (
          <div className="table-scroll bordered">
            <table aria-label="Incidencias de reglas de negocio">
              <thead>
                <tr>
                  <th>Regla</th>
                  <th>Tipo</th>
                  <th>Columnas</th>
                  <th>Registros</th>
                  <th>Gravedad</th>
                  <th>Ejemplos</th>
                </tr>
              </thead>
              <tbody>
                {user.map((issue) => (
                  <tr key={issue.id}>
                    <td>
                      <strong>{issue.rule_id}</strong>
                      <br />
                      <small className="muted">{issue.description}</small>
                    </td>
                    <td>{KINDS[issue.rule] ?? issue.rule}</td>
                    <td>{issue.columns.join(", ")}</td>
                    <td data-testid={`violations-${issue.rule_id}`}>
                      {number(issue.affected_rows)}
                    </td>
                    <td>{SEVERITY[issue.severity] ?? issue.severity}</td>
                    <td className="mono">
                      {issue.sample_row_numbers.join(", ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="success-banner">
            <ShieldCheck size={18} /> Todas las reglas de negocio se cumplen.
          </div>
        )}
      </section>
      <p className="fine-print muted mono">
        {report.rule_version} · revisión {report.ruleset.revision} ·{" "}
        {report.ruleset.content_sha256.slice(0, 16)}…
      </p>
    </div>
  );
}
