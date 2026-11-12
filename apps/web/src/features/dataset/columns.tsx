"use client";

import { useMemo, useState } from "react";
import { Chart, seriesOption } from "@/components/ui/chart";
import type { ColumnInspection, Inspection } from "./api";
import {
  FREQUENCIES,
  NATURES,
  ROLES,
  TYPES,
  formatNumber,
  formatPercent,
} from "./labels";

function Facts({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <dl className="dataset-facts">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Columnas: perfil individual calculado sobre todos los registros. Sólo se muestran las
 * estadísticas que tienen sentido para la naturaleza de cada variable. */
export function ColumnsView({ inspection }: { inspection: Inspection }) {
  const [selected, setSelected] = useState(inspection.columns[0]?.id);
  const column =
    inspection.columns.find((c) => c.id === selected) ?? inspection.columns[0];
  if (!column) return <p className="empty-copy">La tabla no tiene columnas.</p>;
  return (
    <div className="dataset-columns">
      <nav aria-label="Columnas del dataset" className="dataset-column-list">
        <ul>
          {inspection.columns.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                aria-current={item.id === column.id ? "true" : undefined}
                onClick={() => setSelected(item.id)}
              >
                <span>{item.name}</span>
                <small>
                  {TYPES[item.technical_type]} · {NATURES[item.nature]}
                </small>
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <ColumnDetail column={column} rows={inspection.summary.rows} />
    </div>
  );
}

function ColumnDetail({
  column,
  rows,
}: {
  column: ColumnInspection;
  rows: number;
}) {
  const histogram = column.numeric?.histogram;
  const option = useMemo(
    () =>
      seriesOption(
        (histogram ?? []).map((bin) => bin.label),
        (histogram ?? []).map((bin) => bin.count),
        "bar",
      ),
    [histogram],
  );
  const tokens = column.missing.tokens
    .map((t) => `«${t.token}» × ${t.count}`)
    .join(", ");
  return (
    <section
      className="dataset-column-detail"
      aria-label={`Columna ${column.name}`}
    >
      <header>
        <h3>{column.name}</h3>
        <div className="badge-row">
          <span className="badge neutral" title="Tipo técnico">
            {TYPES[column.technical_type]}
          </span>
          <span className="badge calculated" title="Naturaleza estadística">
            {NATURES[column.nature]}
          </span>
          <span className="badge neutral" title="Rol analítico sugerido">
            {ROLES[column.role]}
          </span>
        </div>
        <p className="muted">{column.nature_reason}</p>
      </header>
      <Facts
        items={[
          ["Valores", formatNumber(column.count)],
          [
            "Nulos",
            `${formatNumber(column.nulls)} (${formatPercent(column.null_percent)})`,
          ],
          [
            "Valores únicos",
            `${formatNumber(column.distinct)} (${formatPercent(column.distinct_percent)} de ${formatNumber(rows)})`,
          ],
          [
            "Ejemplos",
            column.examples.length ? column.examples.join(" · ") : "—",
          ],
          ...(column.missing.whitespace || column.missing.empty_strings
            ? ([
                [
                  "Texto en blanco",
                  formatNumber(
                    column.missing.whitespace + column.missing.empty_strings,
                  ),
                ],
              ] as [string, React.ReactNode][])
            : []),
          ...(tokens
            ? ([["Posibles faltantes escritos", tokens]] as [
                string,
                React.ReactNode,
              ][])
            : []),
          ...(column.leading_zeros
            ? ([
                [
                  "Con ceros iniciales",
                  `${formatNumber(column.leading_zeros)} (se conservan como texto)`,
                ],
              ] as [string, React.ReactNode][])
            : []),
        ]}
      />
      {column.reading && <p className="info-banner">{column.reading}</p>}
      {column.mixed && (
        <p className="info-banner">
          Tipos mixtos: {formatNumber(column.mixed.numeric)} valores numéricos y{" "}
          {formatNumber(column.mixed.text)} de texto (por ejemplo:{" "}
          {column.mixed.examples.join(", ")}). La columna se conserva como texto
          para no perder información.
        </p>
      )}
      {column.numeric && (
        <section aria-label="Estadísticas numéricas">
          <h4>Estadísticas</h4>
          <Facts
            items={[
              ["Mínimo", formatNumber(column.numeric.minimum)],
              ["Primer cuartil", formatNumber(column.numeric.q1)],
              ["Mediana", formatNumber(column.numeric.median)],
              ["Media", formatNumber(column.numeric.mean)],
              ["Tercer cuartil", formatNumber(column.numeric.q3)],
              ["Máximo", formatNumber(column.numeric.maximum)],
              [
                "Desviación estándar",
                column.numeric.std == null
                  ? "No aplica (un solo valor)"
                  : formatNumber(column.numeric.std),
              ],
            ]}
          />
          <Chart
            label={`Distribución de frecuencias de ${column.name}`}
            height={220}
            option={option}
          />
          <p className="muted">{column.numeric.method}</p>
        </section>
      )}
      {column.temporal && (
        <section aria-label="Rango temporal">
          <h4>Rango temporal</h4>
          <Facts
            items={[
              ["Desde", column.temporal.minimum],
              ["Hasta", column.temporal.maximum],
              [
                "Intervalo",
                column.temporal.span_days == null
                  ? "—"
                  : `${formatNumber(column.temporal.span_days)} días`,
              ],
              [
                "Frecuencia observada",
                column.temporal.frequency
                  ? FREQUENCIES[column.temporal.frequency]
                  : "No se puede determinar",
              ],
              [
                "Periodos distintos",
                formatNumber(column.temporal.distinct_periods),
              ],
              [
                "Periodos faltantes",
                column.temporal.missing_periods == null
                  ? "No se puede determinar"
                  : `${formatNumber(column.temporal.missing_periods)}${column.temporal.missing_sample.length ? ` (${column.temporal.missing_sample.join(", ")}${column.temporal.missing_periods > column.temporal.missing_sample.length ? "…" : ""})` : ""}`,
              ],
            ]}
          />
          <p className="muted">{column.temporal.method}</p>
        </section>
      )}
      {column.categorical && (
        <section aria-label="Frecuencias">
          <h4>Valores más frecuentes</h4>
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Valor</th>
                <th scope="col">Frecuencia absoluta</th>
                <th scope="col">Frecuencia relativa</th>
              </tr>
            </thead>
            <tbody>
              {column.categorical.top.map((item) => (
                <tr key={item.value}>
                  <td>{item.value}</td>
                  <td>{formatNumber(item.count)}</td>
                  <td>{formatPercent(item.percent)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">
            Cardinalidad: {formatNumber(column.categorical.distinct)} valores
            distintos
            {column.categorical.others
              ? `; ${formatNumber(column.categorical.others)} registros en otros valores`
              : ""}
            . Porcentajes sobre los {formatNumber(rows)} registros.
          </p>
        </section>
      )}
      {column.role_evidence.length > 0 && (
        <details>
          <summary>Por qué se clasificó así</summary>
          <ul className="dataset-notes">
            {column.role_evidence.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
