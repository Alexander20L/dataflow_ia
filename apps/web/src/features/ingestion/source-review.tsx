"use client";

import { FileSearch, GitCompare } from "lucide-react";
import type { SourceReview } from "./api";

const ENCODINGS: Record<string, string> = {
  "utf-8-sig": "UTF-8",
  cp1252: "Windows-1252 (ANSI)",
};
const SEPARATORS: Record<string, string> = {
  ",": "coma",
  ";": "punto y coma",
  "\t": "tabulador",
};

/** Fase 18: lectura del archivo y cambios de estructura. Sólo informa: no hay nada que elegir. */
export function SourceReviewPanel({
  review,
  structureOnly = false,
}: {
  review: SourceReview;
  /** Fase 28: en Dataset › Archivo sólo los cambios de estructura (la lectura ya está allí). */
  structureOnly?: boolean;
}) {
  const reading = review.reading;
  const structure = review.structure;
  const notable =
    !structureOnly &&
    reading &&
    (reading.encoding === "cp1252" ||
      (reading.converted?.length ?? 0) > 0 ||
      (reading.kept_as_text?.length ?? 0) > 0);
  if (!notable && !structure) return null;
  return (
    <section
      className="source-review"
      aria-label={
        structureOnly ? "Cambios de estructura" : "Lectura del archivo"
      }
    >
      {notable && reading && (
        <div className="source-review-block">
          <h3>
            <FileSearch size={16} aria-hidden /> Lectura del archivo
          </h3>
          {reading.format === "csv" && (
            <p className="muted">
              Codificación{" "}
              {ENCODINGS[reading.encoding ?? ""] ?? reading.encoding}
              {reading.separator
                ? ` · separador ${SEPARATORS[reading.separator] ?? reading.separator}`
                : ""}
              .
            </p>
          )}
          <ul>
            {(reading.converted ?? []).map((item) => (
              <li key={`c-${item.column}`}>
                <strong>{item.column}:</strong> {item.explanation}
              </li>
            ))}
            {(reading.kept_as_text ?? []).map((item) => (
              <li key={`k-${item.column}`}>
                <strong>{item.column}</strong> se dejó como texto. {item.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {structure && (
        <div className="source-review-block">
          <h3>
            <GitCompare size={16} aria-hidden /> Cambios respecto de la versión{" "}
            {structure.previous_version_number}
          </h3>
          {structure.changes.length === 0 ? (
            <p className="muted">
              Mismas columnas, tipos y papeles que la versión anterior.
            </p>
          ) : (
            <ul>
              {structure.changes.map((change) => (
                <li key={`${change.change}-${change.column}`}>
                  {change.description}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
