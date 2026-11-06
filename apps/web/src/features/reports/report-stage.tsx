"use client";
import { useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  FileDown,
  FileText,
  LoaderCircle,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import {
  useRepresentations,
  useVersionExecutions,
} from "@/features/executions/api";
import { runHasStep } from "@/features/quality/api";
import { useAnalysisResult } from "@/features/analytics/api";
import { Results } from "@/features/analytics/results";
import { useDashboards } from "@/features/dashboards/api";
import {
  BLOCK_LABELS,
  useCreateReport,
  useRefreshReport,
  useRenderPdf,
  useReport,
  useReportPdfs,
  useReportRevisions,
  useReports,
  useReviseReport,
  type Block,
  type Provenance,
  type ReportView,
} from "./api";

const STATUS: Record<Provenance["status"], string> = {
  ready: "",
  pending: "Calculando…",
  failed: "Ejecución fallida",
  not_executed: "Sin calcular",
  insufficient_data: "Datos insuficientes",
  semantic_requirement_missing: "Requisito semántico pendiente",
  invalid_plan: "Análisis no válido para esta versión",
};

export function ReportStage({
  projectId,
  versionId,
  versionNumber,
  archived,
}: {
  projectId: string;
  versionId: string;
  versionNumber: number;
  archived: boolean;
}) {
  const reports = useReports(projectId);
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const familyId = selected ?? reports.data?.[0]?.family_id ?? null;
  const view = useReport(familyId, revision);
  return (
    <section className="report-stage" aria-label="Informes">
      <div className="section-heading">
        <div>
          <h3>
            <FileText size={17} /> Informes
          </h3>
          <p>
            Un informe reúne tus textos y resultados exactos. Cada bloque de
            datos muestra de dónde sale (dataset, versión, ejecución, filtros y
            fecha) y nunca se recalcula solo: «Actualizar bloques» es una acción
            explícita que guarda una revisión nueva.
          </p>
        </div>
        {!archived && (
          <Button size="sm" variant="outline" onClick={() => setCreating(true)}>
            <Plus size={14} /> Nuevo informe
          </Button>
        )}
      </div>
      {reports.isPending ? (
        <p className="empty-copy" role="status">
          Cargando informes…
        </p>
      ) : reports.isError ? (
        <p className="auth-error" role="alert">
          {errorMessage(reports.error)}
        </p>
      ) : reports.data.length === 0 ? (
        <p className="empty-copy">Todavía no hay informes en este proyecto.</p>
      ) : (
        <>
          <label className="dashboard-picker">
            Informe
            <select
              aria-label="Informe"
              value={familyId ?? ""}
              onChange={(e) => {
                setSelected(e.target.value);
                setRevision(null);
              }}
            >
              {reports.data.map((r) => (
                <option key={r.family_id} value={r.family_id}>
                  {r.head.content.title} · revisión {r.head.revision}
                </option>
              ))}
            </select>
          </label>
          {view.isError && (
            <p className="auth-error" role="alert">
              {errorMessage(view.error)}
            </p>
          )}
          {view.data && (
            <Editor
              key={view.data.head.id}
              view={view.data}
              projectId={projectId}
              versionId={versionId}
              versionNumber={versionNumber}
              editable={!archived && !revision}
              onRevision={setRevision}
            />
          )}
        </>
      )}
      {creating && (
        <CreateDialog
          projectId={projectId}
          versionId={versionId}
          onClose={() => setCreating(false)}
          onCreated={(id) => {
            setSelected(id);
            setRevision(null);
            setCreating(false);
          }}
        />
      )}
    </section>
  );
}

function Editor({
  view,
  projectId,
  versionId,
  versionNumber,
  editable,
  onRevision,
}: {
  view: ReportView;
  projectId: string;
  versionId: string;
  versionNumber: number;
  editable: boolean;
  onRevision: (id: string | null) => void;
}) {
  const head = view.head;
  const [title, setTitle] = useState(head.content.title);
  const [blocks, setBlocks] = useState<Block[]>(head.content.blocks ?? []);
  const [adding, setAdding] = useState<"analysis" | "dashboard_card" | null>(
    null,
  );
  const [confirmRefresh, setConfirmRefresh] = useState(false);
  const revise = useReviseReport();
  const refresh = useRefreshReport();
  const render = useRenderPdf();
  const revisions = useReportRevisions(view.family_id);
  const pdfs = useReportPdfs(view.family_id);
  const tables = useRepresentations(versionId);
  const names = new Map(
    (tables.data?.[0]?.columns ?? []).map((c) => [
      String(c.id),
      String(c.name),
    ]),
  );
  const provenance = new Map(view.provenance.map((p) => [p.block_id, p]));
  const dirty =
    JSON.stringify({ title, blocks }) !==
    JSON.stringify({ title: head.content.title, blocks: head.content.blocks });
  const isHead = head.revision === view.revision_count;

  function update(index: number, block: Block) {
    setBlocks(blocks.map((b, i) => (i === index ? block : b)));
  }
  function move(index: number, delta: -1 | 1) {
    const next = [...blocks];
    [next[index], next[index + delta]] = [next[index + delta], next[index]];
    setBlocks(next);
  }
  function addText(kind: "text" | "conclusion" | "limitations") {
    setBlocks([...blocks, { id: crypto.randomUUID(), kind, text: "" }]);
  }
  async function save() {
    try {
      await revise.mutateAsync({
        familyId: view.family_id,
        expected: head.revision,
        draft: { title, blocks },
      });
    } catch {
      /* Error visible. */
    }
  }

  return (
    <div className="report-editor">
      <div className="dashboard-toolbar">
        <label className="dashboard-picker">
          Revisión
          <select
            aria-label="Revisión del informe"
            value={isHead ? "" : head.id}
            onChange={(e) => onRevision(e.target.value || null)}
          >
            <option value="">Vigente · revisión {view.revision_count}</option>
            {revisions.data
              ?.filter((r) => r.revision !== view.revision_count)
              .map((r) => (
                <option key={r.id} value={r.id}>
                  Revisión {r.revision} ·{" "}
                  {r.cause === "refresh"
                    ? "actualizada"
                    : r.cause === "create"
                      ? "creada"
                      : "editada"}{" "}
                  · {new Date(r.created_at).toLocaleString("es-ES")}
                </option>
              ))}
          </select>
        </label>
        <div className="report-actions">
          {editable && (
            <Button
              size="sm"
              variant="outline"
              disabled={refresh.isPending || dirty}
              title={
                dirty ? "Guarda los cambios antes de actualizar." : undefined
              }
              onClick={() => setConfirmRefresh(true)}
            >
              <RefreshCw size={14} /> Actualizar bloques sobre v{versionNumber}
            </Button>
          )}
          <Button
            size="sm"
            disabled={render.isPending || dirty}
            title={dirty ? "Guarda los cambios antes de exportar." : undefined}
            onClick={() => void render.mutateAsync(head.id).catch(() => {})}
          >
            <FileDown size={14} /> Exportar PDF (revisión {head.revision})
          </Button>
        </div>
      </div>
      {!isHead && (
        <p className="info-banner" role="status">
          Estás viendo la revisión {head.revision} (sólo lectura). Exportarla
          genera el PDF de esa revisión exacta.
        </p>
      )}
      {(revise.isError || refresh.isError || render.isError) && (
        <p className="auth-error" role="alert">
          {errorMessage(revise.error ?? refresh.error ?? render.error)}
        </p>
      )}
      <PdfList renders={pdfs.data ?? []} revisions={revisions.data ?? []} />
      {editable ? (
        <label className="report-title">
          Título del informe
          <input
            aria-label="Título del informe"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
      ) : (
        <h4 data-testid="report-title">{head.content.title}</h4>
      )}
      <ol className="report-blocks">
        {blocks.map((block, index) => (
          <li key={block.id} className={`report-block kind-${block.kind}`}>
            <div className="report-block-head">
              <span className="badge neutral">
                {BLOCK_LABELS[block.kind ?? "analysis"]}
              </span>
              {editable && (
                <span className="card-tools">
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Subir bloque ${index + 1}`}
                    disabled={index === 0}
                    onClick={() => move(index, -1)}
                  >
                    <ArrowUp size={14} />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Bajar bloque ${index + 1}`}
                    disabled={index === blocks.length - 1}
                    onClick={() => move(index, 1)}
                  >
                    <ArrowDown size={14} />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Quitar bloque ${index + 1}`}
                    onClick={() =>
                      setBlocks(blocks.filter((b) => b.id !== block.id))
                    }
                  >
                    <Trash2 size={14} />
                  </Button>
                </span>
              )}
            </div>
            {"text" in block ? (
              editable ? (
                <textarea
                  aria-label={`${BLOCK_LABELS[block.kind ?? "text"]} ${index + 1}`}
                  value={block.text}
                  rows={3}
                  onChange={(e) =>
                    update(index, { ...block, text: e.target.value })
                  }
                />
              ) : (
                <p className="report-text">{block.text}</p>
              )
            ) : (
              <DataBlock
                title={block.title}
                provenance={provenance.get(block.id)}
                names={names}
              />
            )}
          </li>
        ))}
      </ol>
      {editable && (
        <div className="report-add" aria-label="Añadir bloque">
          <Button size="sm" variant="ghost" onClick={() => addText("text")}>
            <Plus size={14} /> Texto
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setAdding("analysis")}
          >
            <Plus size={14} /> Resultado de análisis
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setAdding("dashboard_card")}
          >
            <Plus size={14} /> Tarjeta de dashboard
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => addText("conclusion")}
          >
            <Plus size={14} /> Conclusión
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => addText("limitations")}
          >
            <Plus size={14} /> Limitaciones
          </Button>
          <Button
            disabled={!dirty || revise.isPending || !title.trim()}
            onClick={() => void save()}
          >
            Guardar revisión
          </Button>
        </div>
      )}
      {adding && (
        <AddDataBlock
          kind={adding}
          projectId={projectId}
          versionId={versionId}
          onClose={() => setAdding(null)}
          onAdd={(block) => {
            setBlocks([...blocks, block]);
            setAdding(null);
          }}
        />
      )}
      {confirmRefresh && (
        <Dialog
          title="Actualizar los bloques del informe"
          onClose={() => setConfirmRefresh(false)}
        >
          <p className="dialog-copy">
            Los resultados de análisis se volverán a calcular sobre la versión{" "}
            {versionNumber} y las tarjetas pasarán a la revisión vigente de su
            dashboard. Se guardará una revisión nueva; la actual se conserva.
          </p>
          <div className="form-footer">
            <Button variant="ghost" onClick={() => setConfirmRefresh(false)}>
              Cancelar
            </Button>
            <Button
              disabled={refresh.isPending}
              onClick={async () => {
                try {
                  await refresh.mutateAsync({
                    familyId: view.family_id,
                    expected: head.revision,
                    versionId,
                  });
                  setConfirmRefresh(false);
                } catch {
                  /* Error visible. */
                }
              }}
            >
              Actualizar bloques
            </Button>
          </div>
        </Dialog>
      )}
    </div>
  );
}

function PdfList({
  renders,
  revisions,
}: {
  renders: NonNullable<ReturnType<typeof useReportPdfs>["data"]>;
  revisions: NonNullable<ReturnType<typeof useReportRevisions>["data"]>;
}) {
  if (renders.length === 0) return null;
  const number = new Map(revisions.map((r) => [r.id, r.revision]));
  return (
    <ul className="pdf-list" aria-label="PDF generados">
      {renders.slice(0, 5).map((r) => (
        <li key={r.execution_id}>
          {r.state === "succeeded" ? (
            <a
              className="text-link"
              href={`/api/v1/report-pdfs/${r.execution_id}`}
              title={`SHA-256 ${r.sha256}`}
            >
              <FileDown size={13} /> Descargar PDF (revisión{" "}
              {number.get(r.report_revision_id) ?? "?"})
            </a>
          ) : r.state === "failed" ? (
            <span className="auth-error">
              PDF fallido: {r.error_message ?? "error"}
            </span>
          ) : (
            <span role="status">
              <LoaderCircle className="spin" size={13} /> Generando PDF…
            </span>
          )}
          {r.sha256 && (
            <small className="mono muted">
              {" "}
              · SHA-256 {r.sha256.slice(0, 12)}…
            </small>
          )}
        </li>
      ))}
    </ul>
  );
}

function DataBlock({
  title,
  provenance,
  names,
}: {
  title: string;
  provenance: Provenance | undefined;
  names: Map<string, string>;
}) {
  const ready = provenance?.status === "ready";
  const result = useAnalysisResult(provenance?.execution_id ?? null, ready);
  return (
    <div className="data-block">
      <h5>{title}</h5>
      {!provenance ? (
        <p className="empty-copy">
          Guarda la revisión para ver su procedencia.
        </p>
      ) : !ready ? (
        <div className="card-problem" role="alert">
          <AlertTriangle size={15} />
          <div>
            <strong>{STATUS[provenance.status]}</strong>
            {provenance.message && (
              <p className="fine-print">{provenance.message}</p>
            )}
          </div>
        </div>
      ) : result.data && provenance.execution_id ? (
        <Results result={result.data} runId={provenance.execution_id} />
      ) : (
        <p className="empty-copy">Cargando el resultado…</p>
      )}
      {provenance && (
        <p
          className="fine-print muted provenance"
          data-testid="block-provenance"
        >
          Procedencia: {provenance.dataset} · v{provenance.version_number} ·
          ejecución {provenance.execution_id?.slice(0, 8) ?? "—"}
          {provenance.dashboard_revision_id ? " · tarjeta de dashboard" : ""} ·
          filtros:{" "}
          {provenance.filters.length
            ? provenance.filters
                .map(
                  (f) =>
                    `${names.get(String(f.column_id)) ?? String(f.column_id).slice(0, 8)} ${String(f.operator)} ${((f.values as string[] | undefined) ?? []).join(", ")}`,
                )
                .join("; ")
            : "ninguno"}
          {provenance.time_range
            ? ` · periodo ${String(provenance.time_range.start ?? "…")} – ${String(provenance.time_range.end ?? "…")}`
            : ""}{" "}
          · calculado{" "}
          {provenance.executed_at
            ? new Date(provenance.executed_at).toLocaleString("es-ES")
            : "—"}
        </p>
      )}
    </div>
  );
}

function AddDataBlock({
  kind,
  projectId,
  versionId,
  onClose,
  onAdd,
}: {
  kind: "analysis" | "dashboard_card";
  projectId: string;
  versionId: string;
  onClose: () => void;
  onAdd: (block: Block) => void;
}) {
  const runs = useVersionExecutions(versionId);
  const dashboards = useDashboards(projectId);
  const [blockId] = useState(() => crypto.randomUUID());
  const [title, setTitle] = useState("");
  const [choice, setChoice] = useState("");
  const analyses = (runs.data ?? []).filter(
    (r) =>
      r.kind === "plan" &&
      r.state === "succeeded" &&
      (runHasStep(r, "analytics.query@1") ||
        runHasStep(r, "analytics.query@2")),
  );
  const cards = (dashboards.data ?? []).flatMap((d) =>
    (d.head.content.cards ?? []).map((c) => ({
      value: `${d.head.id}|${c.id}`,
      label: `${d.head.content.title} · ${c.title}`,
      title: c.title,
    })),
  );
  function add() {
    if (kind === "analysis") {
      const run = analyses.find((r) => r.id === choice);
      if (!run?.plan) return;
      onAdd({
        id: blockId,
        kind: "analysis",
        title: title.trim(),
        plan_revision_id: run.plan.id,
        execution_id: run.id,
      });
    } else {
      const [revision, card] = choice.split("|");
      onAdd({
        id: blockId,
        kind: "dashboard_card",
        title: title.trim(),
        dashboard_revision_id: revision,
        card_id: card,
      });
    }
  }
  return (
    <Dialog
      title={`Añadir ${BLOCK_LABELS[kind].toLowerCase()}`}
      onClose={onClose}
    >
      <div className="metric-form">
        <label>
          {kind === "analysis" ? "Ejecución del análisis" : "Tarjeta"}
          <select
            aria-label={
              kind === "analysis" ? "Ejecución del análisis" : "Tarjeta"
            }
            value={choice}
            onChange={(e) => {
              setChoice(e.target.value);
              if (!title && kind === "dashboard_card")
                setTitle(
                  cards.find((c) => c.value === e.target.value)?.title ?? "",
                );
            }}
          >
            <option value="">Elige…</option>
            {kind === "analysis"
              ? analyses.map((r) => (
                  <option key={r.id} value={r.id}>
                    Plan revisión {r.plan?.revision ?? "?"} · {r.id.slice(0, 8)}{" "}
                    ·{" "}
                    {r.finished_at
                      ? new Date(r.finished_at).toLocaleString("es-ES")
                      : ""}
                  </option>
                ))
              : cards.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
          </select>
        </label>
        {kind === "analysis" && analyses.length === 0 && (
          <small className="muted">
            No hay análisis calculados en esta versión: calcula uno en Análisis.
          </small>
        )}
        <label>
          Título del bloque
          <input
            aria-label="Título del bloque"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <p className="fine-print muted">
          El bloque muestra esta ejecución exacta y su procedencia; no cambia
          sola al subir datos nuevos.
        </p>
        <div className="form-footer">
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button disabled={!choice || !title.trim()} onClick={add}>
            Añadir bloque
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function CreateDialog({
  projectId,
  versionId,
  onClose,
  onCreated,
}: {
  projectId: string;
  versionId: string;
  onClose: () => void;
  onCreated: (familyId: string) => void;
}) {
  const create = useCreateReport(projectId);
  const [title, setTitle] = useState("");
  return (
    <Dialog title="Nuevo informe" onClose={onClose}>
      <div className="metric-form">
        <label>
          Nombre del informe
          <input
            aria-label="Nombre del informe"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        {create.isError && (
          <p className="auth-error" role="alert">
            {errorMessage(create.error)}
          </p>
        )}
        <div className="form-footer">
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            disabled={!title.trim() || create.isPending}
            onClick={async () => {
              try {
                const saved = await create.mutateAsync({
                  version_id: versionId,
                  draft: { title: title.trim(), blocks: [] },
                });
                onCreated(saved.revision.family_id);
              } catch {
                /* Error visible. */
              }
            }}
          >
            Crear informe
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
