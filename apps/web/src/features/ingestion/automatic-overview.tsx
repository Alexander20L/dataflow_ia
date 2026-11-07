"use client";

import type { components } from "@dataflow/api-client";
import { Chart, seriesOption } from "@/components/ui/chart";

type Overview = components["schemas"]["AutomaticOverview"];
const columnRoles = {
  identifier: "Identificador probable (sin agregación)",
  date: "Fecha reconocible",
  numeric: "Valor numérico",
  category: "Categoría para frecuencias",
  text: "Texto sin interpretación suficiente",
  empty: "Sin valores para interpretar",
};

function exactNumber(value: string) {
  const [integer, fraction] = value.split(".");
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const decimal = fraction?.replace(/0+$/, "");
  return decimal ? `${grouped},${decimal}` : grouped;
}

export function AutomaticOverview({
  overview,
  versionNumber,
}: {
  overview: Overview;
  versionNumber: number;
}) {
  return (
    <section className="automatic-overview" aria-label="Dashboard automático">
      <header className="section-heading">
        <div>
          <h2>Tu análisis automático</h2>
          <p>
            v{versionNumber} · calculado y guardado al procesar el archivo, sin
            configuración.
          </p>
        </div>
        <span className="badge completed">Listo</span>
      </header>
      {overview.interpretation && (
        <section
          className="automatic-interpretation"
          aria-label="Lectura automática de los datos"
        >
          <h3>{overview.interpretation.label}</h3>
          <p>{overview.interpretation.summary}</p>
          <ul>
            {overview.interpretation.available_analyses.map((analysis) => (
              <li key={analysis}>{analysis}</li>
            ))}
          </ul>
          <details>
            <summary>Interpretación de columnas y límites</summary>
            <ul>
              {overview.interpretation.columns.map((column) => (
                <li key={column.ordinal}>
                  <strong>{column.name}</strong>: {columnRoles[column.role]}.{" "}
                  {column.evidence.join(" ")}
                </li>
              ))}
            </ul>
            <ul>
              {overview.interpretation.limitations.map((limitation) => (
                <li key={limitation}>{limitation}</li>
              ))}
            </ul>
            <p>
              Reglas: {overview.interpretation.rules_version}. No requiere
              confirmación ni crea revisiones semánticas.
            </p>
          </details>
        </section>
      )}
      <div className="automatic-kpis">
        {overview.kpis.map((kpi) => (
          <article className="automatic-kpi" key={kpi.id}>
            <h3>{kpi.label}</h3>
            <strong>
              {exactNumber(kpi.value)}
              {kpi.unit === "percent" ? " %" : ""}
            </strong>
            {kpi.valid_rows != null && (
              <small>
                {kpi.valid_rows} valores utilizados · {kpi.excluded_rows ?? 0}{" "}
                vacíos excluidos
              </small>
            )}
          </article>
        ))}
      </div>
      <div className="automatic-charts">
        {overview.charts.map((chart) => (
          <article className="automatic-chart" key={chart.id}>
            <h3>{chart.title}</h3>
            <Chart
              label={chart.title}
              option={{
                ...seriesOption(
                  chart.points.map((p) => p.label),
                  chart.points.map((p) => p.value),
                  chart.type,
                ),
                // Los nombres y categorías proceden del archivo: nunca tratarlos como HTML.
                tooltip: { trigger: "axis", renderMode: "richText" },
              }}
            />
            <p className="muted">
              {chart.valid_rows} registros cubiertos · {chart.excluded_rows}{" "}
              fuera de esta vista
            </p>
            {chart.omitted_groups > 0 && (
              <p className="muted">
                {chart.omitted_groups} grupos no mostrados por el límite de
                visualización.
              </p>
            )}
          </article>
        ))}
      </div>
      <details aria-label="Detalle del análisis automático">
        <summary>Detalle de los datos</summary>
        <p>
          Primeros {overview.table_detail.rows.length} de{" "}
          {overview.table_detail.total_rows} registros, en su orden original.
        </p>
        <div className="table-scroll">
          <table>
            <caption className="sr-only">
              Detalle automático de la versión {versionNumber}
            </caption>
            <thead>
              <tr>
                {overview.table_detail.columns.map((name, index) => (
                  <th key={index}>{name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {overview.table_detail.rows.map((row, index) => (
                <tr key={index}>
                  {row.map((cell, column) => (
                    <td key={column}>
                      {cell === null ? (
                        <span className="muted">Sin dato</span>
                      ) : (
                        cell
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {overview.table_detail.cells_truncated && (
          <p className="muted">
            Los textos largos se abrevian sólo en esta vista; el archivo
            original permanece completo.
          </p>
        )}
      </details>
      <details>
        <summary>Cómo se calculó y limitaciones</summary>
        <ul>
          {overview.limitations.map((text, index) => (
            <li key={index}>{text}</li>
          ))}
        </ul>
        <p>
          Promedios redondeados a seis decimales. Las fechas se agrupan por su
          formato reconocido, sin atribuirles significado de negocio.
        </p>
        <p className="mono">
          Algoritmo: {overview.algorithm} · SHA-256 del original:{" "}
          {overview.source_sha256}
        </p>
      </details>
    </section>
  );
}
