import { createContext, useContext } from "react";

/** Fase 30 (ADR-048): textos de la investigación en lenguaje de negocio. Las reglas escriben
 * «la tasa de la categoría menos frecuente en activo» cuando la tasa no fija la categoría; la
 * comprensión v6 sabe cuál es (`target.counted`), así que se lee «el % de activo = No». Sólo
 * cambia la lectura: las consultas y los resultados no cambian. */
export function humanizer(column?: string | null, counted?: string | null) {
  if (!column || !counted) return (text: string) => text;
  const escaped = column.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const rate = new RegExp(
    `la tasa de la categoría menos frecuente (?:en|de) ${escaped}(?![\\w])`,
    "gi",
  );
  const share = new RegExp(
    `el porcentaje de la categoría menos frecuente (?:en|de) ${escaped}(?![\\w])`,
    "gi",
  );
  const category = new RegExp(
    `la categoría menos frecuente (?:en|de) ${escaped}(?![\\w])`,
    "gi",
  );
  const percent = `el % de ${column} = ${counted}`;
  // Conserva la mayúscula inicial de la frase.
  const keep = (found: string, value: string) =>
    found[0] === found[0].toUpperCase()
      ? value[0].toUpperCase() + value.slice(1)
      : value;
  return (text: string) =>
    text
      .replace(rate, (found) => keep(found, percent))
      .replace(share, (found) => keep(found, percent))
      .replace(category, `${column} = ${counted}`);
}

export const SayContext = createContext<(text: string) => string>(
  (text) => text,
);

export function useSay() {
  return useContext(SayContext);
}
