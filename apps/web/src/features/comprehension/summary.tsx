"use client";

import { createElement } from "react";
import {
  Banknote,
  Briefcase,
  Calendar,
  CalendarX,
  ChartColumn,
  ChevronDown,
  CircleHelp,
  Clock,
  LoaderCircle,
  Package,
  Percent,
  Rows3,
  Sparkles,
  Star,
  Tag,
  UserMinus,
  type LucideIcon,
} from "lucide-react";
import { errorMessage } from "@/lib/api";
import { capDecimalsInText } from "@/lib/numbers";
import { useChooseTarget, type Comprehension } from "./api";
import { AI_REASONS } from "./labels";

/** Fase 30 (ADR-048): el icono de una columna por reglas sobre su nombre y su papel. */
export function columnIcon(
  name: string,
  kind: "rate" | "measure" | "dimension" | "date",
  monetary = false,
): LucideIcon {
  const n = name.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  if (kind === "rate")
    return /activo|baja|abandon|churn|retir|renunc/.test(n)
      ? UserMinus
      : Percent;
  if (kind === "date" || /fecha|date/.test(n)) return Calendar;
  if (
    monetary ||
    /salari|precio|costo|coste|venta|ingreso|revenue|price|cost|monto|importe|sueldo/.test(
      n,
    )
  )
    return Banknote;
  if (/hora/.test(n)) return Clock;
  if (/ausencia|falta|inasist/.test(n)) return CalendarX;
  if (/evaluac|desempen|nota|puntaj|score|rating|calific|satisfacc/.test(n))
    return Star;
  if (/stock|inventari|unidad|cantidad|existenc/.test(n)) return Package;
  return kind === "measure" ? ChartColumn : Tag;
}

const ORIGIN: Record<string, string> = {
  rules: "Por reglas",
  ai: "Sugerido por la IA",
  user: "Elegido por ti",
};

/** El nombre corto de negocio de una columna (de la IA) o, sin él, la columna. */
function labelOf(result: Comprehension, column: string): string {
  return result.labels?.[column] ?? column;
}

function TargetHero({
  result,
  versionId,
}: {
  result: Comprehension;
  versionId: string;
}) {
  const target = result.target;
  const choose = useChooseTarget(versionId);
  const candidates = result.target_candidates ?? [];
  if (!target && candidates.length === 0) return null;
  const binary = new Set(
    (result.dimensions ?? [])
      .filter((d) => d.distinct === 2)
      .map((d) => d.column),
  );
  const monetary = new Set(
    (result.measures ?? []).filter((m) => m.monetary).map((m) => m.column),
  );
  const explainers = [
    ...(result.dimensions ?? [])
      .filter((d) => d.groupable && d.column !== target?.column)
      .map((d) => ({
        key: d.column,
        label: labelOf(result, d.column),
        icon: columnIcon(d.column, "dimension"),
      })),
    ...(result.derived ?? []).map((d) => ({
      key: d.name,
      label:
        d.kind === "tenure"
          ? "Antigüedad"
          : `${labelOf(result, d.base)} por cuartiles`,
      icon: d.kind === "tenure" ? Clock : ChartColumn,
    })),
  ];
  const counted = target?.counted ?? target?.value;
  const icon = target
    ? columnIcon(target.column, target.kind, monetary.has(target.column))
    : CircleHelp;
  return (
    <section aria-label="Objetivo del análisis" className="cmp-block">
      <p className="cmp-label">¿Qué quieres entender?</p>
      <div className="cmp-hero">
        <span className="cmp-hero-icon" aria-hidden>
          {createElement(icon, { size: 26 })}
        </span>
        <div className="cmp-hero-text">
          {target ? (
            <>
              <strong>
                {target.label ??
                  (target.kind === "rate"
                    ? `% de ${labelOf(result, target.column)}${counted ? ` = ${counted}` : ""}`
                    : `${labelOf(result, target.column)} promedio`)}
              </strong>
              <span>
                {target.kind === "rate"
                  ? `% de registros con ${target.column}${counted ? ` = ${counted}` : ""}`
                  : `Promedio de ${target.column}`}
              </span>
            </>
          ) : (
            <strong>Elige qué quieres entender</strong>
          )}
        </div>
        {target && (
          <span
            className={`badge ${target.origin === "user" ? "completed" : "ai"}`}
            title={target.reason}
          >
            {target.origin === "ai" && <Sparkles size={12} aria-hidden />}
            {ORIGIN[target.origin] ?? target.origin}
          </span>
        )}
      </div>
      {target && explainers.length > 0 && (
        <div className="cmp-chips" aria-label="Se explica con">
          <span className="cmp-chips-lead">Se explica con</span>
          {explainers.map(({ key, label, icon: chip }) => (
            <span key={key} className="cmp-chip" title={key}>
              {createElement(chip, { size: 14, "aria-hidden": true })}
              {label}
            </span>
          ))}
        </div>
      )}
      {candidates.length > 0 && (
        <>
          <p className="cmp-label">Cambiar a</p>
          <div
            role="radiogroup"
            aria-label="Cambiar el objetivo"
            className="cmp-tiles"
          >
            {candidates.map((column) => {
              const rate = binary.has(column);
              const tile = columnIcon(
                column,
                rate ? "rate" : "measure",
                monetary.has(column),
              );
              const selected = target?.column === column;
              return (
                <button
                  key={column}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  aria-label={`${labelOf(result, column)} (${rate ? "porcentaje" : "promedio"})`}
                  className={`cmp-tile${selected ? " selected" : ""}`}
                  disabled={choose.isPending}
                  onClick={() => {
                    if (!selected) choose.mutate(column);
                  }}
                >
                  {createElement(tile, { size: 20, "aria-hidden": true })}
                  <span>
                    <strong>{labelOf(result, column)}</strong>
                    <small>{rate ? `% · ${column}` : "promedio"}</small>
                  </span>
                </button>
              );
            })}
          </div>
          <div className="cmp-actions">
            {target?.origin === "user" && (
              <button
                type="button"
                className="cmp-link"
                disabled={choose.isPending}
                onClick={() => choose.mutate(null)}
              >
                Volver al sugerido
              </button>
            )}
            {choose.isPending && (
              <span role="status" className="cmp-status">
                <LoaderCircle size={14} className="spin" aria-hidden />
                Recalculando el análisis…
              </span>
            )}
            {choose.isError && (
              <span role="alert">{errorMessage(choose.error)}</span>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function Fact({
  icon: Icon,
  label,
  value,
  badge,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  badge?: string;
}) {
  return (
    <div className="cmp-fact">
      <span className="cmp-fact-label">
        <Icon size={14} aria-hidden />
        {label}
      </span>
      <strong>{value}</strong>
      {badge && <span className="badge ai">{badge}</span>}
    </div>
  );
}

function years(
  first: string | null | undefined,
  last: string | null | undefined,
) {
  const a = first?.slice(0, 4);
  const b = last?.slice(0, 4);
  return a && b ? (a === b ? a : `${a} – ${b}`) : (a ?? b ?? "—");
}

/** Fase 30 (ADR-048): el resumen se entiende sin leer. El objetivo y lo básico en tarjetas;
 * los motivos, el método y las reglas, plegados en «Ver detalle técnico». */
export function Summary({
  result,
  versionId,
}: {
  result: Comprehension;
  versionId: string;
}) {
  const formulas = result.formulas ?? [];
  const dated = result.dated_attributes ?? [];
  const grain = result.grain;
  const questions = result.questions ?? [];
  return (
    <div className="dataset-summary cmp-summary">
      <TargetHero result={result} versionId={versionId} />
      <div className="cmp-facts" aria-label="Lo básico">
        <Fact
          icon={Rows3}
          label="Cada fila"
          value={
            grain?.unique && grain.entity
              ? `1 ${grain.entity}`
              : grain
                ? "Sin clave única"
                : "—"
          }
        />
        {(result.theme || result.domain) && (
          <Fact
            icon={Briefcase}
            label="Tema"
            value={result.theme ?? "Ver detalle"}
            badge="Hipótesis de la IA"
          />
        )}
        {result.period ? (
          <Fact
            icon={Calendar}
            label="Periodo"
            value={years(result.period.first, result.period.last)}
          />
        ) : (
          dated[0] && (
            <Fact
              icon={Calendar}
              label={labelOf(result, dated[0].column)}
              value={years(dated[0].first, dated[0].last)}
            />
          )
        )}
        {formulas.length > 0 && (
          <Fact
            icon={ChartColumn}
            label="Columnas calculadas"
            value={String(formulas.length)}
          />
        )}
      </div>
      {questions.length > 0 && (
        <section
          aria-label="Preguntas de negocio sugeridas"
          className="cmp-block"
        >
          <p className="cmp-label">Preguntas que responde</p>
          <ul className="cmp-questions">
            {questions.map((q) => (
              <li key={q}>
                <CircleHelp size={15} aria-hidden />
                {q}
              </li>
            ))}
          </ul>
        </section>
      )}
      <details className="cmp-details">
        <summary>
          <ChevronDown size={14} aria-hidden /> Ver detalle técnico
        </summary>
        <section aria-label="Grano del dataset">
          <h3>Qué representa cada fila</h3>
          {grain ? (
            <>
              <p>{grain.sentence}</p>
              <p className="muted">{grain.reason}</p>
            </>
          ) : (
            <p className="muted">
              Esta versión se calculó antes de la Fase 24: súbela de nuevo para
              ver el grano y las fórmulas.
            </p>
          )}
        </section>
        {result.target && (
          <section aria-label="Motivo del objetivo">
            <h3>Por qué este objetivo</h3>
            <p>{result.target.reason}</p>
            {(result.derived ?? []).map((d) => (
              <p key={d.name} className="muted">
                {d.name}: {d.reason}
              </p>
            ))}
          </section>
        )}
        <section aria-label="Dominio del negocio">
          <h3>De qué trata</h3>
          {result.domain ? (
            <>
              <p>{result.domain}</p>
              {(result.entities ?? []).length > 0 && (
                <p className="muted">
                  {(result.entities ?? [])
                    .map((e) => `${e.name}: ${e.columns.join(", ")}`)
                    .join(" · ")}
                </p>
              )}
            </>
          ) : (
            <p className="muted">
              Sin hipótesis de la IA (
              {AI_REASONS[result.ai_reason ?? ""] ??
                result.ai_reason ??
                result.ai_state}
              ): el grano, las fórmulas, las relaciones y el periodo se calculan
              igual con los datos.
            </p>
          )}
        </section>
        <section aria-label="Columnas calculadas">
          <h3>Columnas calculadas a partir de otras</h3>
          {formulas.length === 0 ? (
            <p className="muted">Ninguna.</p>
          ) : (
            <ul className="dataset-notes">
              {formulas.map((f) => (
                <li key={f.column}>
                  <strong>{capDecimalsInText(f.expression)}</strong>
                  <br />
                  <small className="muted">
                    Se cumple en {f.matching_rows} de {f.rows} filas. {f.method}
                  </small>
                </li>
              ))}
            </ul>
          )}
        </section>
        {result.period && (
          <section aria-label="Periodo">
            <h3>Periodo</h3>
            <p>
              {result.period.note} {result.period.periods} periodos
              {result.period.first
                ? `, de ${result.period.first} a ${result.period.last}`
                : ""}
              .
            </p>
          </section>
        )}
        {dated.length > 0 && (
          <section aria-label="Fechas que describen al registro">
            <h3>Fechas que describen al registro</h3>
            <ul className="dataset-notes">
              {dated.map((d) => (
                <li key={d.column}>
                  <strong>{d.column}</strong> (de {d.first} a {d.last}):{" "}
                  {d.reason} Registros por año:{" "}
                  {d.per_year
                    .map(([year, count]) => `${year}: ${count}`)
                    .join(", ")}
                  .
                </li>
              ))}
            </ul>
          </section>
        )}
        <section aria-label="Cómo se calculó">
          <h3>Cómo se calculó</h3>
          <ul className="dataset-notes">
            {result.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
            <li>Reglas: {result.rules_version}.</li>
          </ul>
        </section>
      </details>
    </div>
  );
}
