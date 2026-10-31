import { createHash } from "node:crypto";

/** Algoritmo restringido de diseño v1; no es una implementación general de JCS. */
export function canonical(value) {
  if (typeof value === "string") {
    for (let i = 0; i < value.length; i++) {
      const code = value.charCodeAt(i);
      if (code >= 0xd800 && code <= 0xdbff) {
        const next = value.charCodeAt(++i);
        if (!(next >= 0xdc00 && next <= 0xdfff))
          throw new Error("CANONICAL_INVALID_UNICODE");
      } else if (code >= 0xdc00 && code <= 0xdfff)
        throw new Error("CANONICAL_INVALID_UNICODE");
    }
    return JSON.stringify(value);
  }
  if (value === null || typeof value === "boolean")
    return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value) || Object.is(value, -0))
      throw new Error("CANONICAL_INTEGER_REQUIRED");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i++)
      if (!(i in value)) throw new Error("CANONICAL_SPARSE_ARRAY");
    return `[${value.map(canonical).join(",")}]`;
  }
  if (value && Object.getPrototypeOf(value) === Object.prototype) {
    const keys = Object.keys(value).sort();
    if (keys.some((key) => !/^[a-z][a-z0-9_]*$/.test(key)))
      throw new Error("CANONICAL_ASCII_KEY_REQUIRED");
    return `{${keys.map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  }
  throw new Error("CANONICAL_UNSUPPORTED_VALUE");
}

export const sha256 = (value) =>
  createHash("sha256").update(value).digest("hex");
export const digest = (domain, payload) =>
  sha256(`dataflow:${domain}:v1\n${canonical(payload)}`);
