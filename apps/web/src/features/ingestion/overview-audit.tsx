"use client";

import { useQuery } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";
import { capDecimalsInText } from "@/lib/numbers";

type Segment = components["schemas"]["Segment"];

export function OverviewAudit({ versionId }: { versionId: string }) {
  const query = useQuery({
    queryKey: ["overview-audit", versionId],
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/versions/{version_id}/overview-audit", {
          signal,
          params: { path: { version_id: versionId } },
        }),
      ),
    refetchInterval: (q) =>
      ["queued", "running"].includes(q.state.data?.state ?? "") ? 1000 : false,
  });
  function render(segments: Segment[]) {
    return segments.map((segment, index) =>
      segment.kind === "evidence" && segment.evidence_id ? (
        <a
          key={index}
          className="text-link copilot-figure"
          href={`/api/v1/versions/${versionId}/overview-audit/evidence/${segment.evidence_id}`}
          target="_blank"
          rel="noreferrer"
          aria-label={`De dónde sale ${capDecimalsInText(segment.text)}`}
        >
          {capDecimalsInText(segment.text)}
        </a>
      ) : segment.kind === "unverified" ? (
        <mark
          key={index}
          title="Cifra del modelo retirada por falta de evidencia."
        >
          {segment.text}
        </mark>
      ) : (
        <span key={index}>{segment.text}</span>
      ),
    );
  }
  const content = query.data?.audit?.content;
  const pending =
    query.isPending || ["queued", "running"].includes(query.data?.state ?? "");
  return (
    <section
      className="text-audit"
      aria-label="Explicación automática IA"
      aria-busy={pending}
    >
      <h3>Explicación automática (IA)</h3>
      {pending ? (
        <p role="status">
          Preparando la explicación de los resultados guardados… Puedes seguir
          usando el dashboard.
        </p>
      ) : content ? (
        <>
          <p>{render(content.resumen_ejecutivo)}</p>
          {content.alertas_criticas.length > 0 && (
            <>
              <h4>Alertas</h4>
              <ul>
                {content.alertas_criticas.map((alert, index) => (
                  <li key={index}>
                    <strong>{render(alert.titulo)}</strong>{" "}
                    {render(alert.detalle)}
                  </li>
                ))}
              </ul>
            </>
          )}
          <h4>Recomendaciones</h4>
          <ul>
            {content.recomendaciones.map((recommendation, index) => (
              <li key={index}>{render(recommendation)}</li>
            ))}
          </ul>
          <p className="muted">
            Explicación guardada de esta versión. Las cifras enlazan a su
            evidencia; la IA no modifica los datos ni el dashboard.
          </p>
        </>
      ) : (
        <p className="muted">
          {query.data?.reason === "disabled" ||
          query.data?.reason === "missing_key"
            ? "La IA no está configurada."
            : "La explicación no está disponible para esta versión."}{" "}
          Los indicadores y gráficos siguen disponibles.
        </p>
      )}
    </section>
  );
}
