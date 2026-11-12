import type { components } from "@dataflow/api-client";

type Schemas = components["schemas"];
export type TechnicalType = Schemas["ColumnInspection"]["technical_type"];
export type Nature = Schemas["ColumnInspection"]["nature"];
export type Role = Schemas["ColumnInspection"]["role"];
export type Group = Schemas["ColumnInspection"]["group"];
export type Dimension = Schemas["Finding"]["dimension"];
export type Severity = Schemas["Finding"]["severity"];
export type TimeFormat = NonNullable<Schemas["DictionaryEntry"]["time_format"]>;
export type Status = Schemas["DictionaryEntry"]["status"];

export const TYPES: Record<TechnicalType, string> = {
  string: "Texto",
  integer: "Entero",
  decimal: "Decimal",
  boolean: "Booleano",
  date: "Fecha",
  datetime: "Fecha y hora",
  empty: "Vacía",
};
export const NATURES: Record<Nature, string> = {
  nominal: "Cualitativa nominal",
  ordinal: "Cualitativa ordinal",
  discrete: "Cuantitativa discreta",
  continuous: "Cuantitativa continua",
  temporal: "Temporal",
  unknown: "Desconocida",
};
export const ROLES: Record<Role, string> = {
  identifier: "Identificador",
  dimension: "Dimensión",
  measure: "Medida",
  time: "Fecha o periodo",
  category: "Categoría",
  text: "Texto descriptivo",
  unknown: "Desconocido",
};
export const GROUPS: Record<Group, string> = {
  numeric: "Numéricas",
  categorical: "Categóricas",
  temporal: "Temporales",
  identifier: "Identificadores",
  other: "Otras o desconocidas",
};
export const DIMENSIONS: Record<Dimension, string> = {
  completeness: "Completitud",
  uniqueness: "Unicidad",
  validity: "Validez",
  consistency: "Consistencia",
  format: "Formato",
  integrity: "Integridad",
};
export const SEVERITIES: Record<Severity, string> = {
  high: "Alta",
  medium: "Media",
  low: "Baja",
  info: "Informativa",
};
export const SEVERITY_BADGE: Record<Severity, string> = {
  high: "blocking",
  medium: "warning",
  low: "info",
  info: "neutral",
};
export const TIME_FORMATS: Record<TimeFormat, string> = {
  day_month_year: "Día/mes/año",
  month_day_year: "Mes/día/año",
  year_month_day: "Año-mes-día",
  year: "Año",
  month: "Mes",
  year_month: "Año y mes (periodo)",
};
export const STATUSES: Record<Status, string> = {
  automatic: "Automática",
  corrected: "Corrección manual",
  confirmed: "Confirmada",
};
export const FREQUENCIES: Record<string, string> = {
  daily: "Diaria",
  weekly: "Semanal",
  monthly: "Mensual",
  quarterly: "Trimestral",
  yearly: "Anual",
  irregular: "Irregular",
};
export const FORMATS: Record<string, string> = {
  csv: "CSV",
  xlsx: "Excel (.xlsx)",
  pdf: "PDF",
  sqlserver: "SQL Server",
  other: "Otro",
};

/** Número con separador de miles español; los textos exactos del servidor no se redondean. */
export function formatNumber(value: string | number | null | undefined) {
  if (value == null) return "—";
  const text = String(value);
  const negative = text.startsWith("-");
  const [integer, fraction] = (negative ? text.slice(1) : text).split(".");
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${negative ? "-" : ""}${fraction ? `${grouped},${fraction}` : grouped}`;
}

export function formatPercent(value: string) {
  return `${formatNumber(value)} %`;
}

export function formatBytes(bytes: number | null | undefined) {
  if (bytes == null) return "No disponible";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024)
    return `${formatNumber((bytes / 1024).toFixed(1))} KB`;
  return `${formatNumber((bytes / 1024 / 1024).toFixed(2))} MB`;
}

export function separatorLabel(value: string | null | undefined) {
  if (value == null) return "No aplica";
  if (value === "\t") return "Tabulador";
  if (value === ";") return "Punto y coma (;)";
  if (value === ",") return "Coma (,)";
  return value;
}

export function encodingLabel(value: string | null | undefined) {
  if (value == null) return "No aplica";
  if (value === "utf-8-sig") return "UTF-8";
  if (value === "cp1252") return "Windows-1252";
  return value;
}
