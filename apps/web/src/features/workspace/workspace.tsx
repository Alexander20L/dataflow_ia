"use client";
import { useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronRight,
  Columns3,
  Database,
  Download,
  GitBranch,
  History,
  PanelRightClose,
  Send,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useApp } from "@/lib/providers";
import { cleanSales, originalSales, steps } from "@/lib/demo";
import { downloadText, number } from "@/lib/utils";
import {
  DataTable,
  Understanding,
  Quality,
  Cleaning,
  Exploration,
  Analysis,
  DashboardEditor,
} from "./stages";
import { Report } from "@/features/reports/report";
import { ProjectDetail } from "@/features/projects/project-detail";

export function Workspace({ projectId }: { projectId: string }) {
  if (projectId !== "ventas-2026")
    return <ProjectDetail key={projectId} id={projectId} />;
  return <DemoWorkspace />;
}
function DemoWorkspace() {
  const projectId = "ventas-2026";
  const { projects, cleaned } = useApp();
  const project = projects.find((p) => p.id === projectId);
  const [stage, setStage] = useState(0);
  const [version, setVersion] = useState("latest");
  const [assistant, setAssistant] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<{ text: string; user: boolean }[]>(
    [],
  );
  const isV2 = cleaned && version !== "v1";
  const sales = isV2 ? cleanSales : originalSales;
  if (!project)
    return (
      <div className="empty-state">
        <Database size={32} />
        <h1>Proyecto no encontrado</h1>
        <p>Este proyecto no está guardado en este navegador.</p>
        <Button asChild>
          <Link href="/projects">Ver proyectos</Link>
        </Button>
      </div>
    );
  function ask(text: string) {
    if (!text.trim()) return;
    const answer = /limpi|nulo|calidad|falt/i.test(text)
      ? "El fixture original tiene 8 importes nulos entre 240 registros (3,33 %). La propuesta de demostración excluye esas filas: requiere aprobación y crea v2 sin modificar v1. No equivale a afirmar que excluir sea la mejor decisión para datos reales."
      : /ingreso|total|venta/i.test(text)
        ? "Los ingresos se calculan sumando los importes válidos del fixture. Los nulos se excluyen explícitamente del cálculo; no se imputan. Consulta Análisis para ver fórmula, filtros y cifras verificables."
        : `Estás en ${steps[stage]}. Puedes revisar las tablas y artefactos de esta etapa. Esta respuesta está guionizada para la demostración; no se ha consultado a ningún modelo de IA.`;
    setMessages((previous) => [
      ...previous,
      { text, user: true },
      { text: answer, user: false },
    ]);
    setQuestion("");
  }
  return (
    <>
      <div className="workspace-heading">
        <div>
          <Link className="back-link" href="/projects">
            <ArrowLeft size={14} />
            Proyectos
          </Link>
          <h1>{project.name}</h1>
          <p>
            <span className="status-dot" /> Dataset sintético <span>·</span>{" "}
            {number(sales.length)} registros <span>·</span> 6 columnas
          </p>
        </div>
        <div className="heading-actions">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              downloadText(
                `ventas-demo-${isV2 ? "v2" : "v1"}.csv`,
                "id,fecha,region,categoria,importe,unidades\n" +
                  sales
                    .map((s) =>
                      [
                        s.id,
                        s.date,
                        s.region,
                        s.category,
                        s.revenue ?? "",
                        s.units,
                      ].join(","),
                    )
                    .join("\n"),
              )
            }
          >
            <Download size={15} />
            CSV demo
          </Button>
          <Button
            variant={assistant ? "default" : "outline"}
            size="sm"
            onClick={() => setAssistant((v) => !v)}
          >
            <Sparkles size={15} />
            Copiloto
          </Button>
        </div>
      </div>
      <div className="workspace-layout">
        <aside className="dataset-panel">
          <div className="dataset-panel-title">
            EXPLORADOR <Columns3 size={14} />
          </div>
          <div className="dataset-file">
            <Database size={17} />
            <strong>ventas_2026</strong>
            <ChevronRight size={13} />
          </div>
          <label className="version-label" htmlFor="dataset-version">
            <GitBranch size={14} /> Versión del dataset
          </label>
          <select
            id="dataset-version"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
          >
            <option value="latest">
              {cleaned ? "v2 · última" : "v1 · original"}
            </option>
            {cleaned && <option value="v1">v1 · original</option>}
          </select>
          <p className="dataset-label">
            COLUMNAS <span>6</span>
          </p>
          {[
            ["#", "id", "string"],
            ["◷", "fecha", "date"],
            ["Aa", "region", "string"],
            ["Aa", "categoria", "string"],
            ["#", "importe", "float"],
            ["#", "unidades", "int"],
          ].map(([icon, name, type]) => (
            <div className="column-row" key={name}>
              <span>{icon}</span>
              <strong>{name}</strong>
              <small>{type}</small>
            </div>
          ))}
          <div className="dataset-version-note">
            <ShieldCheck size={16} />
            <span>
              Original protegido
              <br />
              <small>Las versiones son independientes.</small>
            </span>
          </div>
          <button className="history-link" onClick={() => setStage(3)}>
            <History size={15} />
            Transformaciones <span>{cleaned ? 1 : 0}</span>
          </button>
        </aside>
        <section className="stage-container">
          <nav className="stepper" aria-label="Etapas del análisis">
            {steps.map((step, i) => (
              <button
                key={step}
                className={`step ${stage === i ? "current" : ""}`}
                aria-current={stage === i ? "step" : undefined}
                onClick={() => setStage(i)}
              >
                <span
                  className={`step-number ${i < 3 || (i === 3 && cleaned) ? "done" : ""}`}
                >
                  {i < 3 || (i === 3 && cleaned) ? <Check size={13} /> : i + 1}
                </span>
                <span>{step}</span>
              </button>
            ))}
          </nav>
          <div className="stage-content">
            <div className="stage-title">
              <div>
                <span className="eyebrow">
                  ETAPA {String(stage + 1).padStart(2, "0")} / 09
                </span>
                <h2>{steps[stage]}</h2>
              </div>
              <span className="badge neutral">
                {isV2 ? "v2 · procesado" : "v1 · original"}
              </span>
            </div>
            {stage === 0 && (
              <>
                <div className="info-banner">
                  <ShieldCheck size={19} />
                  <span>
                    Ejemplo cargado desde un fixture local. El archivo original
                    de referencia no se modifica.
                  </span>
                </div>
                <div className="mini-metrics">
                  <div>
                    <small>Registros</small>
                    <strong>{number(sales.length)}</strong>
                  </div>
                  <div>
                    <small>Columnas</small>
                    <strong>6</strong>
                  </div>
                  <div>
                    <small>Fuente</small>
                    <strong>Fixture CSV</strong>
                  </div>
                </div>
                <div className="section-heading">
                  <h3>Vista previa de los datos</h3>
                  <span className="badge calculated">Datos sintéticos</span>
                </div>
                <DataTable sales={sales} />
              </>
            )}
            {stage === 1 && <Understanding sales={sales} />}
            {stage === 2 && (
              <Quality sales={sales} onClean={() => setStage(3)} />
            )}
            {stage === 3 && <Cleaning />}
            {stage === 4 && <Exploration sales={sales} />}
            {stage === 5 && <Analysis sales={sales} />}
            {stage === 6 && <DashboardEditor sales={sales} />}
            {stage === 7 && (
              <Report sales={sales} version={isV2 ? "v2" : "v1"} />
            )}
            {stage === 8 && (
              <Report
                sales={sales}
                version={isV2 ? "v2" : "v1"}
                recommendationsOnly
              />
            )}
            <div className="stage-footer">
              <Button
                variant="ghost"
                size="sm"
                disabled={stage === 0}
                onClick={() => setStage((s) => s - 1)}
              >
                <ArrowLeft size={15} />
                Anterior
              </Button>
              <span>Revisión supervisada · resultados de demostración</span>
              <Button
                size="sm"
                disabled={stage === 8}
                onClick={() => setStage((s) => s + 1)}
              >
                Siguiente etapa <ArrowRight size={15} />
              </Button>
            </div>
          </div>
        </section>
        {assistant && (
          <aside className="assistant-panel">
            <div className="assistant-heading">
              <span>
                <Sparkles size={18} />
                Copiloto de análisis
              </span>
              <button
                className="icon-button"
                aria-label="Cerrar copiloto"
                onClick={() => setAssistant(false)}
              >
                <PanelRightClose size={17} />
              </button>
            </div>
            <span className="badge ai">Respuestas simuladas</span>
            <h3>Un poco de contexto, mucha claridad.</h3>
            <p>
              Consulta los datos, entiende una incidencia o revisa el siguiente
              paso.
            </p>
            <div className="assistant-suggestions">
              {[
                "¿Qué problemas de calidad hay?",
                "¿Cómo se calculan los ingresos?",
              ].map((q) => (
                <button key={q} onClick={() => ask(q)}>
                  {q}
                  <ArrowRight size={14} />
                </button>
              ))}
            </div>
            <div className="assistant-messages" aria-live="polite">
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={`message ${m.user ? "user-message" : "ai-message"}`}
                >
                  <small>{m.user ? "Tú" : "Copiloto · guion de demo"}</small>
                  {m.text}
                </div>
              ))}
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                ask(question);
              }}
            >
              <label className="sr-only" htmlFor="question">
                Pregunta al copiloto
              </label>
              <input
                id="question"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Pregunta sobre tus datos…"
                maxLength={500}
              />
              <button aria-label="Enviar pregunta" disabled={!question.trim()}>
                <Send size={17} />
              </button>
            </form>
            <small className="assistant-disclaimer">
              No ejecuta cambios ni consulta un proveedor de IA.
            </small>
          </aside>
        )}
      </div>
    </>
  );
}
