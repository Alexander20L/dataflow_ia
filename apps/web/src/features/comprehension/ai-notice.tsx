"use client";

import { Sparkles } from "lucide-react";
import { useComprehensionView } from "./api";
import { AI_REASONS } from "./labels";

/** Fase 29 (ADR-047): aviso visible en todas las pestañas cuando el análisis se hizo sin IA. Los
 * cálculos son los mismos; faltan los significados, el objetivo propuesto por la IA, sus
 * propuestas de investigación y la narrativa del informe. */
export function AiNotice({ versionId }: { versionId: string }) {
  const query = useComprehensionView(versionId);
  const result = query.data?.comprehension;
  if (!result || result.ai_state === "ready") return null;
  const reason =
    AI_REASONS[result.ai_reason ?? ""] ??
    (result.ai_state === "failed"
      ? "la IA no respondió"
      : (result.ai_reason ?? "la IA no está disponible"));
  return (
    <p className="info-banner ai-notice" role="status">
      <Sparkles size={16} aria-hidden />
      <span>
        <strong>Este análisis se hizo sin IA</strong> ({reason}). Las cifras,
        las pruebas y las clasificaciones son las mismas; faltan los
        significados de las columnas, las propuestas de la IA y la narrativa del
        informe.
      </span>
    </p>
  );
}
