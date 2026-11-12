"use client";

import type { components } from "@dataflow/api-client";
import { Chart, seriesOption } from "@/components/ui/chart";
import { capDecimals, localeNumber } from "@/lib/numbers";

type Overview = components["schemas"]["AutomaticOverview"];
type Analysis = components["schemas"]["AnalyticalInterpretation"];
type Quality = components["schemas"]["QualityReport"];
type Finding = components["schemas"]["AnalyticalFinding"];

const columnRoles = {
  identifier: "Identificador probable (sin agregación)",
  date: "Fecha reconocible",
  numeric: "Valor numérico",
  category: "Categoría para frecuencias",
  text: "Texto sin interpretación suficiente",
  empty: "Sin valores para interpretar",
};
const analyticalRoles = {
  identifier: "Identificador (no se suma)",
  dimension: "Dimensión para agrupar",
  measure: "Medida",
  time: "Tiempo",
  text: "Texto",
  empty: "Sin valores",
};
const additivity = {
  additive: "se puede sumar",
  semi_additive: "no se suma entre fechas",
  non_additive: "no se suma",
  unknown: "aditividad desconocida: no se suma",
};
const severities = {
  blocking: "Limita análisis",
  warning: "Advertencia",
  info: "Observación",
};

function exactNumber(raw: string) {
  const value = capDecimals(raw);
  const negative = value.startsWith("-");
  const [integer, fraction] = (negative ? value.slice(1) : value).split(".");
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const decimal = fraction?.replace(/0+$/, "");
  return `${negative ? "-" : ""}${decimal ? `${grouped},${decimal}` : grouped}`;
}

function AnalysisSummary({ analysis }: { analysis: Analysis }) {
  const time = analysis.time;
  return (
    <section
      className="automatic-interpretation"
      aria-label="Lectura automática de los datos"
    >
      <h3>{analysis.label}</h3>
      <p>{analysis.row_meaning}</p>
      {time && (
        <p>
          Periodo mensual ({time.columns.join(" + ")}): {time.first} a{" "}
          {time.last} · {time.periods} meses con datos
          {time.missing_count > 0
            ? ` · faltan ${time.missing_count}: ${time.missing.join(", ")}`
            : ""}
          .
        </p>
      )}
      <h4>Qué se puede analizar</h4>
      <ul>
        {analysis.available_analyses.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      {analysis.limited_analyses.length > 0 && (
        <div
          className="limited-analyses"
          role="note"
          aria-label="Análisis limitados"
        >
          <h4>Análisis limitados</h4>
          <ul>
            {analysis.limited_analyses.map((item) => (
              <li key={item.subject}>
                <strong>{item.subject}</strong>: {item.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      <details>
        <summary>Interpretación de columnas, claves y relaciones</summary>
        <ul>
          {analysis.columns.map((column) => (
            <li key={column.ordinal}>
              <strong>{column.name}</strong>: {analyticalRoles[column.role]}
              {column.additivity ? `, ${additivity[column.additivity]}` : ""}
              {column.monetary
                ? column.currency_code
                  ? ` · moneda ${column.currency_code}`
                  : column.currency === "ambiguous"
                    ? " · varias monedas"
                    : " · moneda desconocida"
                : ""}
              . {column.evidence.join(" ")}
            </li>
          ))}
        </ul>
        {analysis.keys.length > 0 && (
          <ul>
            {analysis.keys.map((key) => (
              <li key={key.columns.join("|")}>{key.evidence}</li>
            ))}
          </ul>
        )}
        {analysis.relationships.length > 0 && (
          <ul>
            {analysis.relationships.map((item) => (
              <li key={item.target}>
                {item.target} ≈ {item.factors.join(" × ")} en{" "}
                {item.matching_rows} de {item.compared_rows} filas (tolerancia{" "}
                {capDecimals(item.tolerance)}).
              </li>
            ))}
          </ul>
        )}
        <ul>
          {analysis.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
        <p>
          Reglas: {analysis.rules_version}. Son hipótesis con evidencia, no
          confirmaciones; no hace falta responder nada.
        </p>
      </details>
    </section>
  );
}

function FindingItem({ finding }: { finding: Finding }) {
  return (
    <li className={`quality-finding ${finding.severity}`}>
      <span className={`badge ${finding.severity}`}>
        <i />
        {severities[finding.severity]}
      </span>
      <strong>{finding.title}</strong>
      <ul>
        {finding.evidence.map((text) => (
          <li key={text}>{text}</li>
        ))}
      </ul>
      {finding.affected_analyses.length > 0 && (
        <p className="muted">
          Afecta a: {finding.affected_analyses.join(", ")}
        </p>
      )}
      {finding.sample_row_numbers.length > 0 && (
        <p className="muted">
          Filas de ejemplo: {finding.sample_row_numbers.join(", ")}
        </p>
      )}
    </li>
  );
}

function DataQuality({ quality }: { quality: Quality }) {
  const analytical = quality.analytical;
  if (!analytical) return null;
  return (
    <section className="data-quality" aria-label="Calidad de los datos">
      <h3>Calidad de los datos</h3>
      <p>
        {analytical.blocking} limitan análisis · {analytical.warnings}{" "}
        advertencias · {analytical.observations} observaciones · completitud{" "}
        {localeNumber(quality.completeness_percent)} %. Nada se corrigió
        automáticamente.
      </p>
      {analytical.findings.length ? (
        <ul className="quality-findings">
          {analytical.findings.map((finding) => (
            <FindingItem key={finding.id} finding={finding} />
          ))}
        </ul>
      ) : (
        <p>No se encontraron problemas que cambien las conclusiones.</p>
      )}
      <p className="muted">Reglas: {analytical.rules_version}.</p>
    </section>
  );
}

export function AutomaticOverview({
  overview,
  versionNumber,
  quality,
}: {
  overview: Overview;
  versionNumber: number;
  quality?: Quality;
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
      {overview.analysis && <AnalysisSummary analysis={overview.analysis} />}
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
                  chart.points.map((p) =>
                    chart.measure ? Number(p.amount ?? 0) : p.value,
                  ),
                  chart.type,
                ),
                // Los nombres y categorías proceden del archivo: nunca tratarlos como HTML.
                tooltip: { trigger: "axis", renderMode: "richText" },
              }}
            />
            <p className="muted">
              {chart.measure
                ? `Suma exacta de ${chart.measure} · ${chart.valid_rows} registros · ${chart.excluded_rows} fuera de esta vista`
                : `${chart.valid_rows} registros cubiertos · ${chart.excluded_rows} fuera de esta vista`}
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
      {quality && <DataQuality quality={quality} />}
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
          {overview.analysis
            ? "Las sumas son exactas sobre todas las filas; los promedios simples se redondean a seis decimales. Los meses se ordenan cronológicamente y los vacíos no cuentan como cero."
            : "Promedios redondeados a seis decimales. Las fechas se agrupan por su formato reconocido, sin atribuirles significado de negocio."}
        </p>
        <p className="mono">
          Algoritmo: {overview.algorithm} · SHA-256 del original:{" "}
          {overview.source_sha256}
        </p>
      </details>
    </section>
  );
}
