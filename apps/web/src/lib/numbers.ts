/** Máximo de decimales con que la interfaz muestra un resultado. Sólo presentación: los valores
 * enviados a la API, guardados o descargados no se tocan. */
export const MAX_DECIMALS = 3;

const DECIMAL = /^([+-]?)(\d*)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/;

/** Cadena decimal con notación científica pasada a notación fija («1e-7» → «0.0000001»). */
function expand(
  sign: string,
  integer: string,
  fraction: string,
  exponent: number,
) {
  const digits = integer + fraction;
  const point = integer.length + exponent;
  if (point <= 0) return `${sign}0.${"0".repeat(-point)}${digits}`;
  if (point >= digits.length)
    return `${sign}${digits}${"0".repeat(point - digits.length)}`;
  return `${sign}${digits.slice(0, point)}.${digits.slice(point)}`;
}

/** Suma uno a una cadena de dígitos («199» → «200», «99» → «100»). */
function increment(digits: string) {
  const chars = digits.split("");
  let i = chars.length - 1;
  while (i >= 0 && chars[i] === "9") {
    chars[i] = "0";
    i -= 1;
  }
  if (i < 0) return `1${chars.join("")}`;
  chars[i] = String(Number(chars[i]) + 1);
  return chars.join("");
}

/**
 * Limita un número a `max` decimales con aritmética de cadenas (sin pasar por coma flotante):
 * redondeo «half-up» (un 5 se aleja del cero). Devuelve la cadena con punto decimal y sin
 * separador de miles. Si ya tiene `max` decimales o menos se devuelve tal cual (conserva sus
 * ceros: «12.50» sigue «12.50»); si se redondeó, se quitan los ceros finales que deja el
 * redondeo («1.29999» → «1.3», «2.0004» → «2», «-0.0001» → «0», nunca «-0»). Lo que no es un
 * número se devuelve sin cambios.
 */
export function capDecimals(value: string | number, max = MAX_DECIMALS) {
  const text = String(value);
  const match = DECIMAL.exec(text);
  if (!match || (!match[2] && !match[3])) return text;
  const [, sign, integer = "", rawFraction = "", exponent] = match;
  if (exponent !== undefined)
    return capDecimals(
      expand(sign === "-" ? "-" : "", integer, rawFraction, Number(exponent)),
      max,
    );
  if (rawFraction.length <= max) return text;
  const kept = (integer || "0") + rawFraction.slice(0, max);
  const digits = rawFraction[max] >= "5" ? increment(kept) : kept;
  const whole = digits.slice(0, digits.length - max).replace(/^0+(?=\d)/, "");
  const fraction = digits.slice(digits.length - max).replace(/0+$/, "");
  const zero = /^0*$/.test(whole) && !fraction;
  return `${sign === "-" && !zero ? "-" : ""}${whole}${fraction ? `.${fraction}` : ""}`;
}

/** Número de JavaScript con el formato regional «es-ES» de siempre, con 3 decimales como mucho. */
export function localeNumber(value: number) {
  if (!Number.isFinite(value)) return value.toLocaleString("es-ES");
  return Number(capDecimals(value)).toLocaleString("es-ES", {
    maximumFractionDigits: MAX_DECIMALS,
  });
}

/** Cifras con coma decimal dentro de un texto del servidor («0,123456·Base», «1.234,56789 €»):
 * se limitan a 3 decimales conservando la agrupación de miles que traían. */
const LOCALIZED = /(?<![\w.,])(-?)(\d{1,3}(?:\.\d{3})+|\d+),(\d{4,})(?!\w)/g;
/** Cifras con punto decimal y sin miles dentro de un texto («[1.234567, 2.5)»). */
const PLAIN = /(?<![\w.,])(-?)(\d+)\.(\d{4,})(?![\w.])/g;

export function capDecimalsInText(text: string, separator: "," | "." = ",") {
  const comma = separator === ",";
  return text.replace(
    comma ? LOCALIZED : PLAIN,
    (_all, sign: string, integer: string, fraction: string) => {
      const grouped = comma && integer.includes(".");
      const capped = capDecimals(
        `${sign}${integer.replace(/\./g, "")}.${fraction}`,
      );
      if (!comma) return capped;
      const negative = capped.startsWith("-");
      const [whole, decimals] = (negative ? capped.slice(1) : capped).split(
        ".",
      );
      const shown = grouped
        ? whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".")
        : whole;
      return `${negative ? "-" : ""}${shown}${decimals ? `,${decimals}` : ""}`;
    },
  );
}
