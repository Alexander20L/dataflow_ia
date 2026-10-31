"use client";
import { useState } from "react";
import { Check, Download, ExternalLink, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { monthlyTotals, summarize, type Sale } from "@/lib/demo";
import { currency } from "@/lib/utils";

export function Report({
  sales,
  version,
  recommendationsOnly = false,
}: {
  sales: Sale[];
  version: string;
  recommendationsOnly?: boolean;
}) {
  const [reviewed, setReviewed] = useState(false);
  const [evidence, setEvidence] = useState(false);
  const stats = summarize(sales);
  const months = monthlyTotals(sales);
  const growth = months[0] ? ((months[5] - months[0]) / months[0]) * 100 : 0;
  return (
    <article className="report-content">
      <div className="report-toolbar">
        <div>
          <span className="badge calculated">Ventas 2026 · {version}</span>
          <span className="badge ai">Interpretación de demostración</span>
        </div>
        <Button size="sm" variant="outline" onClick={() => window.print()}>
          <Download size={15} />
          Imprimir / PDF
        </Button>
      </div>
      {!recommendationsOnly && (
        <>
          <section className="report-section">
            <p className="eyebrow">RESUMEN EJECUTIVO</p>
            <h3>Una visión de tus ventas, con contexto.</h3>
            <p>
              El dataset sintético contiene {sales.length} operaciones, de las
              cuales {stats.valid} tienen importe válido. Los ingresos
              registrados suman <strong>{currency(stats.total)}</strong> entre
              enero y junio de 2026.
            </p>
          </section>
          <section className="report-section">
            <h3>Hallazgos principales</h3>
            <div className="finding-card">
              <span className="badge calculated">Resultado calculado</span>
              <p>
                Junio presenta una variación de{" "}
                <strong>{growth.toFixed(1)} %</strong> respecto a enero en la
                suma de importes válidos.
              </p>
              <button
                className="text-link"
                onClick={() => setEvidence((v) => !v)}
              >
                {evidence ? "Ocultar evidencia" : "Consultar evidencia"}
                <ExternalLink size={13} />
              </button>
              {evidence && (
                <dl className="definition-list">
                  <dt>Origen</dt>
                  <dd>Fixture ventas_2026 · {version}</dd>
                  <dt>Enero / Junio</dt>
                  <dd>
                    {currency(months[0])} / {currency(months[5])}
                  </dd>
                  <dt>Fórmula</dt>
                  <dd>(junio − enero) / enero × 100</dd>
                  <dt>Condición</dt>
                  <dd>Importes no nulos; sin imputación</dd>
                </dl>
              )}
            </div>
          </section>
          <section className="report-section">
            <h3>Interpretación</h3>
            <p>
              La variación describe los datos de ejemplo. No demuestra una causa
              comercial ni permite proyectar el comportamiento de ventas reales.
              El fixture incorpora una estructura temporal deliberada.
            </p>
          </section>
        </>
      )}
      <section className="report-section">
        <p className="eyebrow">PRÓXIMOS PASOS CON CRITERIO</p>
        <h3>Recomendaciones para revisar</h3>
        <div className="recommendation-card">
          <div className="section-heading">
            <strong>Revisar los importes faltantes en la fuente</strong>
            <span className="badge review">Prioridad media</span>
          </div>
          <p>
            En v1 hay 8 operaciones sin importe. Antes de excluirlas, comprueba
            si es posible recuperar el dato original.
          </p>
          <dl className="recommendation-meta">
            <div>
              <dt>Hallazgo</dt>
              <dd>Completitud de importe · Q-001</dd>
            </div>
            <div>
              <dt>Evidencia</dt>
              <dd>8 / 240 registros originales</dd>
            </div>
            <div>
              <dt>Impacto posible</dt>
              <dd>Reducir pérdida de información; no cuantificado</dd>
            </div>
            <div>
              <dt>Incertidumbre</dt>
              <dd>No sabemos si los importes son recuperables</dd>
            </div>
          </dl>
          <Button
            variant={reviewed ? "outline" : "default"}
            size="sm"
            onClick={() => setReviewed((v) => !v)}
          >
            <Check size={15} />
            {reviewed ? "Revisada · deshacer" : "Marcar como revisada"}
          </Button>
          <small className="muted"> Revisión temporal de esta vista</small>
        </div>
      </section>
      <section className="report-section limitations">
        <ShieldCheck size={20} />
        <div>
          <h3>Limitaciones y supuestos</h3>
          <p>
            Datos sintéticos, moneda EUR, importes nulos excluidos de las sumas
            y sin validación externa. No se ha utilizado IA real. La exclusión
            de filas puede introducir sesgo. Este informe no debe utilizarse
            para decisiones comerciales reales.
          </p>
        </div>
      </section>
    </article>
  );
}
