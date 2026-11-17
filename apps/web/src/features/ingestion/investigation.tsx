"use client";

import type { components } from "@dataflow/api-client";
import { capDecimals, capDecimalsInText } from "@/lib/numbers";
import { InsightCard } from "./automatic-analysis";
import type { InvestigationView as View } from "./api";

type Segment = components["schemas"]["Segment"];

const STOPPED: Record<string, string> = {
  max_iterations: "se completaron las iteraciones permitidas",
  no_new_proposals: "la IA no propuso nada nuevo y válido",
  ai_unavailable: "la IA no está disponible: sólo se aplicaron las reglas",
  ai_error:
    "el proveedor de IA falló; se conservan los resultados ya calculados",
  max_ai_calls: "se alcanzó el máximo de llamadas a la IA",
  max_cost: "se alcanzó el presupuesto de IA de la investigación",
  max_seconds: "se alcanzó el tiempo máximo",
  max_queries: "se alcanzó el máximo de consultas",
  nothing_to_investigate: "no hay medida, agrupación o meses que seguir",
};

function Segments({
  segments,
  versionId,
}: {
  segments: Segment[];
  versionId: string;
}) {
  return (
    <>
      {segments.map((segment, index) =>
        segment.kind === "evidence" && segment.evidence_id ? (
          <a
            key={index}
            className="text-link copilot-figure"
            href={`/api/v1/versions/${versionId}/investigation/evidence/${segment.evidence_id}`}
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
      )}
    </>
  );
}

function target(item: {
  dimension?: string | null;
  month?: string | null;
  year?: number | null;
  group?: string | null;
}) {
  return [item.dimension, item.month ?? item.year ?? item.group]
    .filter((part) => part != null && part !== "")
    .join(" · ");
}

export function InvestigationPanel({
  view,
  versionId,
}: {
  view: View;
  versionId: string;
}) {
  const pending = ["queued", "running"].includes(view.state);
  const result = view.investigation;
  const origin = new Map(
    (result?.proposals ?? [])
      .filter((proposal) => proposal.key)
      .map((proposal) => [proposal.key!, proposal]),
  );
  const rejected = (result?.proposals ?? []).filter(
    (proposal) => proposal.status === "rejected",
  );
  const content = result?.explanation;
  return (
    <section
      className="automatic-analysis investigation"
      aria-label="Investigación automática"
      aria-busy={pending}
    >
      <header className="section-heading">
        <div>
          <h2>Seguimiento de los hallazgos</h2>
          <p>
            Seguimientos de los hallazgos: primero por reglas y después
            propuestos por la IA. Python valida cada propuesta y calcula las
            cifras.
          </p>
        </div>
      </header>
      {pending ? (
        <p role="status">
          Investigando los hallazgos… Puedes seguir usando el dashboard.
        </p>
      ) : view.state === "failed" || !result ? (
        <p className="muted">
          La investigación no pudo completarse ({view.reason ?? "error"}). Los
          hallazgos siguen disponibles.
        </p>
      ) : (
        <>
          <section
            className="text-audit"
            aria-label="Explicación automática IA"
          >
            <h3>Explicación (IA)</h3>
            {content ? (
              <>
                <p>
                  <Segments
                    segments={content.resumen_ejecutivo}
                    versionId={versionId}
                  />
                </p>
                {content.alertas_criticas.length > 0 && (
                  <ul>
                    {content.alertas_criticas.map((alert, index) => (
                      <li key={index}>
                        <strong>
                          <Segments
                            segments={alert.titulo}
                            versionId={versionId}
                          />
                        </strong>{" "}
                        <Segments
                          segments={alert.detalle}
                          versionId={versionId}
                        />
                      </li>
                    ))}
                  </ul>
                )}
                <h4>Recomendaciones</h4>
                <ul>
                  {content.recomendaciones.map((recommendation, index) => (
                    <li key={index}>
                      <Segments
                        segments={recommendation}
                        versionId={versionId}
                      />
                    </li>
                  ))}
                </ul>
                <p className="muted">
                  Las cifras enlazan a su evidencia; la IA no escribe cifras ni
                  modifica los datos.
                </p>
              </>
            ) : (
              <p className="muted">
                {result.ai === "unavailable"
                  ? "La IA no está configurada: se muestran sólo los seguimientos por reglas."
                  : "La explicación no está disponible para esta investigación."}
              </p>
            )}
          </section>
          {result.results.some((item) => item.insight) ? (
            <div className="automatic-insights">
              {result.results.map((item) =>
                item.insight ? (
                  <InsightCard
                    key={item.key}
                    insight={item.insight}
                    badge={
                      origin.get(item.key)?.origin === "ai"
                        ? "Propuesto por la IA"
                        : "Regla"
                    }
                  />
                ) : null,
              )}
            </div>
          ) : (
            <p>No hubo seguimientos con datos suficientes.</p>
          )}
          {result.results.some((item) => item.status === "empty") && (
            <ul className="muted">
              {result.results
                .filter((item) => item.status === "empty")
                .map((item) => (
                  <li key={item.key}>{item.reason}</li>
                ))}
            </ul>
          )}
          {rejected.length > 0 && (
            <details aria-label="Propuestas rechazadas">
              <summary>Propuestas rechazadas · {rejected.length}</summary>
              <ul>
                {rejected.map((proposal, index) => (
                  <li key={index}>
                    <strong>
                      {proposal.kind}
                      {target(proposal) ? ` (${target(proposal)})` : ""}
                    </strong>
                    : {proposal.reason}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <details>
            <summary>Cómo se investigó</summary>
            <ul>
              {result.proposals
                .filter((proposal) => proposal.status === "accepted")
                .map((proposal) => (
                  <li key={proposal.key}>
                    {proposal.origin === "ai" ? "IA" : "Regla"}, iteración{" "}
                    {proposal.iteration}: {proposal.motive}
                  </li>
                ))}
            </ul>
            <p>
              Terminó porque {STOPPED[result.stopped] ?? result.stopped}.{" "}
              {result.iterations} iteraciones · {result.consumption.ai_calls}{" "}
              llamadas a la IA · US$ {capDecimals(result.consumption.cost_usd)}.
            </p>
            <ul>
              {result.limitations.map((text) => (
                <li key={text}>{text}</li>
              ))}
            </ul>
            <p className="mono">
              Reglas: {result.rules_version} · límites:{" "}
              {result.limits.max_iterations} iteraciones,{" "}
              {result.limits.max_ai_calls} llamadas, US${" "}
              {result.limits.max_cost_usd}, {result.limits.max_seconds} s.
            </p>
          </details>
        </>
      )}
    </section>
  );
}
