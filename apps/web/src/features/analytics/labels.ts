import type { components } from "@dataflow/api-client";

type Schemas = components["schemas"];
export type Aggregation = Schemas["MetricContent"]["aggregation"];
export type Grain = "day" | "week" | "month" | "quarter" | "year";
export type ComparisonKind = Schemas["AnalysisResultV2"]["comparisons"][number];

export const AGGREGATIONS: {
  value: Aggregation;
  label: string;
  measured: boolean;
  additive: boolean;
}[] = [
  { value: "sum", label: "Suma", measured: true, additive: true },
  { value: "avg", label: "Media", measured: true, additive: false },
  { value: "min", label: "Mínimo", measured: true, additive: false },
  { value: "max", label: "Máximo", measured: true, additive: false },
  {
    value: "count",
    label: "Número de valores",
    measured: false,
    additive: true,
  },
  {
    value: "count_distinct",
    label: "Valores distintos",
    measured: false,
    additive: false,
  },
];

export const GRAINS: { value: Grain; label: string }[] = [
  { value: "day", label: "Día" },
  { value: "week", label: "Semana ISO" },
  { value: "month", label: "Mes" },
  { value: "quarter", label: "Trimestre" },
  { value: "year", label: "Año" },
];

export const OPERATORS = {
  eq: "igual a",
  neq: "distinto de",
  in: "en la lista",
  gt: "mayor que",
  gte: "mayor o igual que",
  lt: "menor que",
  lte: "menor o igual que",
  is_null: "es nulo",
  is_not_null: "no es nulo",
} as const;

export const COMPARISONS: { value: ComparisonKind; label: string }[] = [
  { value: "previous_period", label: "Periodo anterior" },
  { value: "same_period_last_year", label: "Mismo periodo del año anterior" },
];

export const comparisonLabel = (kind: string) =>
  COMPARISONS.find((c) => c.value === kind)?.label ?? kind;

export const aggregationLabel = (value: string) =>
  AGGREGATIONS.find((a) => a.value === value)?.label ?? value;

/** Por qué una base no tiene valor: nunca se muestra 0 en su lugar. */
export const BASE_STATUS: Record<string, string> = {
  available: "",
  no_base_data: "sin datos",
  no_counterpart: "sin equivalente",
  missing_period: "sin fecha",
};

export const BASE_STATUS_HELP: Record<string, string> = {
  no_base_data: "El periodo base no tiene filas para esta métrica.",
  no_counterpart:
    "El periodo no tiene equivalente (29 de febrero, semana 53 o fuera del calendario).",
  missing_period:
    "La fila agrupa los registros sin fecha: no hay periodo base.",
};

export const SHARE_STATUS: Record<string, string> = {
  available: "",
  total_zero: "total 0",
  value_missing: "sin filas",
};

export const CELL_LABELS: Record<string, string> = {
  value: "Valor",
  previous_period: "Periodo anterior",
  same_period_last_year: "Mismo periodo del año anterior",
  change: "Variación",
  change_pct: "Variación %",
  share_of_total: "% del total",
  rank: "Posición",
};

export const TIE_HELP =
  "Mismo valor que la posición anterior: el orden lo decide el desempate por dimensiones.";
