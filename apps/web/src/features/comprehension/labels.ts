export const SCALES: Record<string, string> = {
  nominal: "Nominal",
  ordinal: "Ordinal",
  interval: "De intervalo",
  ratio: "De razón",
  identifier: "Identificador",
  text: "Texto libre",
  empty: "Vacía",
};
export const ORIGINS: Record<string, string> = {
  ai: "Hipótesis de la IA",
  data: "Detectada en los datos",
  declared: "Declarada en la base",
};
export const STATUS: Record<string, string> = {
  confirmed: "Confirmada por los datos",
  not_supported: "Los datos no la respaldan",
  not_testable: "No comprobable",
};
export const STATES: Record<string, string> = {
  pending: "Pendiente",
  validated: "Validada",
  rejected: "Rechazada",
  ambiguous: "Ambigua",
};
export const STATE_BADGE: Record<string, string> = {
  pending: "neutral",
  validated: "completed",
  rejected: "blocking",
  ambiguous: "warning",
};
export const FAMILIES: Record<string, string> = {
  structural: "Estructurales",
  statistical: "Estadísticas",
  temporal: "Temporales",
};
export const KINDS: Record<string, string> = {
  association: "Asociación",
  dependency: "Dependencia",
  declared: "Clave declarada",
  derived: "Columna calculada",
  same_entity: "Misma entidad",
  period: "Periodo",
};
export const CONFIDENCES: Record<string, string> = {
  high: "Confianza alta",
  medium: "Confianza media",
  low: "Confianza baja",
};
export const AGGREGATIONS: Record<string, string> = {
  sum: "Suma",
  mean: "Promedio",
  weighted_mean: "Promedio ponderado",
};
export const ADDITIVITY: Record<string, string> = {
  additive: "Sumable",
  semi_additive: "Sumable por periodo",
  non_additive: "No sumable",
  unknown: "Sumabilidad no comprobada",
};
export const AI_REASONS: Record<string, string> = {
  disabled: "la IA no está configurada",
  missing_key: "falta la clave de la IA",
  AI_BUDGET_EXCEEDED: "se alcanzó el límite de uso de la IA",
};
