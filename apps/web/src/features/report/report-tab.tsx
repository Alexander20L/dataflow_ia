"use client";

import { useState, type KeyboardEvent } from "react";
import {
  Check,
  CircleAlert,
  Download,
  FileText,
  LoaderCircle,
  RotateCcw,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Chart, seriesOption } from "@/components/ui/chart";
import { errorMessage } from "@/lib/api";
import { capDecimalsInText } from "@/lib/numbers";
import {
  useGenerateReport,
  useReportHistory,
  useReportReview,
  useReportView,
  useReviewFinding,
  type ReportBlock,
  type ReportDocument,
  type ReviewItem,
  type ReviewStatus,
} from "./api";

const SUBVIEWS = [
  { id: "preview", label: "Informe" },
  { id: "review", label: "Revisión de hallazgos" },
  { id: "history", label: "Historial" },
] as const;
type Subview = (typeof SUBVIEWS)[number]["id"];

const STATUS: Record<ReviewStatus, string> = {
  pending: "Pendiente de revisión",
  approved: "Aprobado",
  rejected: "Rechazado",
};
const STATUS_BADGE: Record<ReviewStatus, string> = {
  pending: "review",
  approved: "completed",
  rejected: "draft",
};
const CLASSES: Record<string, string> = {
  relevant: "Hallazgo relevante",
  secondary: "Hallazgo secundario",
};
const TRIGGERS: Record<string, string> = {
  load: "Al cargar el archivo",
  selection: "Con tu selección",
  dashboard: "Dashboard actualizado",
  feedback: "Tras tus marcas",
  meaning: "Tras tus significados",
  update: "Actualización",
};
const STATES: Record<string, string> = {
  queued: "En cola",
  running: "Generándose",
  succeeded: "Lista",
  failed: "Falló",
  cancelled: "Cancelada",
};

function when(value?: string | null) {
  return value ? new Date(value).toLocaleString("es-ES") : "—";
}

function Block({ block }: { block: ReportBlock }) {
  const chart = block.chart;
  return (
    <div className="report-block">
      {(block.title || block.badge) && (
        <header>
          {block.title && <h4>{block.title}</h4>}
          {block.badge && <span className="badge neutral">{block.badge}</span>}
        </header>
      )}
      {(block.paragraphs ?? []).map((text, index) => (
        <p key={index}>{capDecimalsInText(text)}</p>
      ))}
      {chart && chart.labels.length > 1 && (
        <Chart
          label={chart.title}
          height={200}
          option={{
            ...seriesOption(
              chart.labels,
              chart.values.map((v) => Number(v)),
              chart.type,
            ),
            tooltip: { trigger: "axis", renderMode: "richText" },
          }}
        />
      )}
      {block.table && (
        <div className="table-scroll">
          <table className="comprehension-table">
            <thead>
              <tr>
                {block.table.headers.map((header) => (
                  <th key={header}>{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.table.rows.map((row, index) => (
                <tr key={index}>
                  {row.map((cell, position) => (
                    <td key={position}>{capDecimalsInText(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** Vista previa del documento: las mismas secciones que el PDF. */
function Preview({ document }: { document: ReportDocument }) {
  return (
    <article className="report-preview" aria-label="Vista previa del informe">
      <header className="report-cover">
        <h3>{document.title}</h3>
        <p className="muted">
          {document.source.file_name} · versión del dataset{" "}
          {document.source.version_number} · generado{" "}
          {when(document.generated_at)} · reglas {document.rules_version}
        </p>
        {document.source.execution_id && (
          <small className="muted">
            Ejecución {document.source.execution_id}
          </small>
        )}
      </header>
      <nav aria-label="Índice del informe" className="report-index">
        <ol>
          {document.sections.map((section) => (
            <li key={section.id}>
              <a href={`#report-${section.id}`}>{section.title}</a>
            </li>
          ))}
        </ol>
      </nav>
      {document.sections.map((section) => (
        <section
          key={section.id}
          id={`report-${section.id}`}
          className="report-section"
          aria-label={section.title}
        >
          <h3>{section.title}</h3>
          {section.intro && <p className="muted">{section.intro}</p>}
          {section.blocks.map((block, index) => (
            <Block key={index} block={block} />
          ))}
        </section>
      ))}
    </article>
  );
}

function Review({ versionId }: { versionId: string }) {
  const review = useReportReview(versionId, true);
  const mark = useReviewFinding(versionId);
  const generate = useGenerateReport(versionId);
  if (review.isPending)
    return (
      <p className="muted" role="status">
        Cargando la revisión…
      </p>
    );
  if (review.isError) return <p role="alert">{errorMessage(review.error)}</p>;
  if (!review.data)
    return (
      <p className="muted">
        Este informe es anterior a la revisión de hallazgos: vuelve a investigar
        la versión para revisarlos.
      </p>
    );
  const items = review.data.items;
  const approved = items.some((i) => i.status === "approved");
  const set = (item: ReviewItem, status: ReviewStatus) =>
    mark.mutate({
      item: item.item,
      status: item.status === status ? "pending" : status,
    });
  return (
    <div className="report-review">
      <p className="muted">
        {approved
          ? "Sólo los hallazgos aprobados aparecerán como principales."
          : "Aún no aprobaste ninguno: el informe usa como principales los relevantes de la investigación, marcados «Sin revisar»."}{" "}
        Un rechazado nunca es principal. Los cambios se aplican al generar una
        versión nueva; la anterior se conserva.
      </p>
      <div className="report-review-actions">
        <Button
          size="sm"
          disabled={!review.data.changed || generate.isPending}
          onClick={() => generate.mutate()}
        >
          {generate.isPending ? (
            <LoaderCircle className="spin" size={14} aria-hidden />
          ) : (
            <RotateCcw size={14} aria-hidden />
          )}{" "}
          Generar versión con mi selección
        </Button>
        {!review.data.changed && (
          <small className="muted">
            El último informe ya usa esta selección.
          </small>
        )}
      </div>
      {(mark.isError || generate.isError) && (
        <p className="auth-error" role="alert">
          {errorMessage(mark.error ?? generate.error)}
        </p>
      )}
      {generate.isSuccess && (
        <p className="info-banner" role="status">
          Se está generando la versión nueva; mírala en «Informe» o en el
          historial.
        </p>
      )}
      <ul className="report-candidates" aria-label="Hallazgos candidatos">
        {items.map((item) => (
          <li key={item.item} aria-label={item.title}>
            <div>
              <strong>{item.title}</strong>
              <span>
                {item.classification && CLASSES[item.classification] && (
                  <span className="badge calculated">
                    {CLASSES[item.classification]}
                  </span>
                )}{" "}
                <span className={`badge ${STATUS_BADGE[item.status]}`}>
                  {STATUS[item.status]}
                </span>{" "}
                {item.principal && (
                  <span className="badge neutral">Principal</span>
                )}
              </span>
            </div>
            <div
              className="dashboard-marks"
              role="group"
              aria-label={`Revisar ${item.title}`}
            >
              <button
                type="button"
                className="btn btn-sm btn-outline"
                aria-pressed={item.status === "approved"}
                disabled={mark.isPending}
                onClick={() => set(item, "approved")}
              >
                <Check size={13} aria-hidden /> Aprobar
              </button>
              <button
                type="button"
                className="btn btn-sm btn-outline"
                aria-pressed={item.status === "rejected"}
                disabled={mark.isPending}
                onClick={() => set(item, "rejected")}
              >
                <X size={13} aria-hidden /> Rechazar
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function History({
  versionId,
  current,
  onOpen,
}: {
  versionId: string;
  current?: string;
  onOpen: (executionId: string) => void;
}) {
  const history = useReportHistory(versionId);
  if (history.isPending)
    return (
      <p className="muted" role="status">
        Cargando el historial…
      </p>
    );
  if (history.isError) return <p role="alert">{errorMessage(history.error)}</p>;
  const items = history.data?.items ?? [];
  return (
    <div className="table-scroll">
      <table className="comprehension-table" aria-label="Versiones del informe">
        <thead>
          <tr>
            <th>Versión</th>
            <th>Motivo</th>
            <th>Estado</th>
            <th>Generada</th>
            <th>Aprobados</th>
            <th>Principales</th>
            <th>
              <span className="sr-only">Acciones</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.execution_id}>
              <td>
                v{item.number}
                {item.execution_id === current ? " (viendo)" : ""}
              </td>
              <td>{TRIGGERS[item.trigger] ?? item.trigger}</td>
              <td>{STATES[item.state] ?? item.state}</td>
              <td>{when(item.finished_at ?? item.created_at)}</td>
              <td>{item.approved ?? "—"}</td>
              <td>{item.principal ?? "—"}</td>
              <td>
                {item.state === "succeeded" && (
                  <span className="report-history-actions">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onOpen(item.execution_id)}
                    >
                      Ver
                    </Button>
                    <a
                      className="btn btn-sm btn-outline"
                      href={`/api/v1/versions/${versionId}/report.pdf?execution_id=${item.execution_id}`}
                    >
                      PDF
                    </a>
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Fase 27: pestaña Informe. Vista previa del documento (las mismas secciones que el PDF),
 * revisión humana de los hallazgos, versiones nuevas a petición e historial. */
export function ReportTab({ versionId }: { versionId: string }) {
  const [subview, setSubview] = useState<Subview>("preview");
  const [executionId, setExecutionId] = useState<string>();
  const query = useReportView(versionId, executionId);
  const onKey = (event: KeyboardEvent, index: number) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    const delta = event.key === "ArrowRight" ? 1 : -1;
    const next = SUBVIEWS[(index + delta + SUBVIEWS.length) % SUBVIEWS.length];
    setSubview(next.id);
    document.getElementById(`report-tab-${next.id}`)?.focus();
  };
  if (query.isPending)
    return (
      <p className="empty-copy" role="status">
        Cargando el informe…
      </p>
    );
  if (query.isError)
    return (
      <div className="empty-state">
        <p role="alert">{errorMessage(query.error)}</p>
        <Button onClick={() => void query.refetch()}>Reintentar</Button>
      </div>
    );
  const view = query.data;
  const pdf = `/api/v1/versions/${versionId}/report.pdf${executionId ? `?execution_id=${executionId}` : ""}`;
  return (
    <section className="report-tab" aria-label="Informe" role="region">
      <div className="investigation-status">
        <div>
          <FileText size={16} aria-hidden />{" "}
          {!view ? (
            "Esta versión no tiene informe: se procesó antes del informe automático."
          ) : view.state === "queued" || view.state === "running" ? (
            <span role="status">
              <LoaderCircle className="spin" size={14} aria-hidden />{" "}
              {view.reason ?? "Generando el informe…"}
            </span>
          ) : view.state === "failed" ? (
            <span role="alert">
              <CircleAlert size={16} aria-hidden /> El informe falló (
              {view.reason ?? "sin detalle"}).
            </span>
          ) : (
            <>
              Versión {view.number ?? 1} del informe · generada{" "}
              {when(view.generated_at)}
              {view.updating && (
                <small className="muted">
                  {" "}
                  · se está generando una versión nueva
                </small>
              )}
            </>
          )}
        </div>
        {view?.state === "ready" && (
          <a className="btn btn-sm" href={pdf}>
            <Download size={14} aria-hidden /> Descargar PDF
          </a>
        )}
      </div>
      {executionId && (
        <p className="info-banner" role="status">
          Estás viendo una versión anterior del informe.{" "}
          <button
            type="button"
            className="link-button"
            onClick={() => setExecutionId(undefined)}
          >
            Volver a la actual
          </button>
        </p>
      )}
      <div
        className="dataset-subnav"
        role="tablist"
        aria-label="Secciones del informe"
      >
        {SUBVIEWS.map((item, index) => (
          <button
            key={item.id}
            id={`report-tab-${item.id}`}
            type="button"
            role="tab"
            aria-selected={subview === item.id}
            aria-controls={`report-panel-${item.id}`}
            tabIndex={subview === item.id ? 0 : -1}
            onClick={() => setSubview(item.id)}
            onKeyDown={(event) => onKey(event, index)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div
        id={`report-panel-${subview}`}
        role="tabpanel"
        aria-labelledby={`report-tab-${subview}`}
      >
        {subview === "review" ? (
          <Review versionId={versionId} />
        ) : subview === "history" ? (
          <History
            versionId={versionId}
            current={executionId ?? view?.execution_id ?? undefined}
            onOpen={(id) => {
              setExecutionId(id);
              setSubview("preview");
            }}
          />
        ) : view?.document ? (
          <Preview document={view.document} />
        ) : view?.state === "ready" ? (
          <p className="muted">
            Este informe es anterior a la vista previa: descarga el PDF.
          </p>
        ) : null}
      </div>
    </section>
  );
}
