"use client";
import { useState } from "react";
import { LayoutDashboard } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import {
  allowedViews,
  draftOf,
  SIZE_LABELS,
  useCreateDashboard,
  useDashboard,
  useDashboards,
  useReviseDashboard,
  VIEW_LABELS,
  type Card,
  type CardSize,
  type CardView,
} from "./api";

/** «Añadir a un dashboard»: la tarjeta apunta a esta revisión del análisis y a esta ejecución. */
export function AddToDashboard({
  projectId,
  planRevisionId,
  executionId,
  dimensions,
  grain,
  metrics,
  suggestedTitle,
}: {
  projectId: string;
  planRevisionId: string;
  executionId: string;
  dimensions: number;
  grain: boolean;
  metrics: { key: string; label: string }[];
  suggestedTitle: string;
}) {
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  return (
    <>
      <div className="form-footer">
        {done && (
          <span className="badge completed" role="status">
            Añadida a «{done}»
          </span>
        )}
        <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
          <LayoutDashboard size={14} /> Añadir a un dashboard
        </Button>
      </div>
      {open && (
        <AddDialog
          projectId={projectId}
          planRevisionId={planRevisionId}
          executionId={executionId}
          views={allowedViews(dimensions, grain)}
          metrics={metrics}
          suggestedTitle={suggestedTitle}
          onClose={() => setOpen(false)}
          onAdded={(title) => {
            setDone(title);
            setOpen(false);
          }}
        />
      )}
    </>
  );
}

function AddDialog({
  projectId,
  planRevisionId,
  executionId,
  views,
  metrics,
  suggestedTitle,
  onClose,
  onAdded,
}: {
  projectId: string;
  planRevisionId: string;
  executionId: string;
  views: CardView[];
  metrics: { key: string; label: string }[];
  suggestedTitle: string;
  onClose: () => void;
  onAdded: (dashboardTitle: string) => void;
}) {
  const dashboards = useDashboards(projectId);
  const [target, setTarget] = useState<string>("");
  const [newTitle, setNewTitle] = useState("");
  const [title, setTitle] = useState(suggestedTitle);
  const [view, setView] = useState<CardView>(views[0]);
  const [size, setSize] = useState<CardSize>("medium");
  const [metric, setMetric] = useState(metrics[0]?.key ?? "m0");
  const [cardId] = useState(() => crypto.randomUUID());
  const existing = target && target !== "new" ? target : null;
  const head = useDashboard(existing);
  const create = useCreateDashboard(projectId);
  const revise = useReviseDashboard();
  const card: Card = {
    id: cardId,
    title: title.trim(),
    plan_revision_id: planRevisionId,
    execution_id: executionId,
    view,
    size,
    metric,
  };
  const choice = target || (dashboards.data?.length ? "" : "new");
  const pending = create.isPending || revise.isPending;
  async function add() {
    try {
      if (choice === "new") {
        await create.mutateAsync({
          title: newTitle.trim(),
          cards: [card],
          filters: [],
        });
        onAdded(newTitle.trim());
      } else if (head.data) {
        const draft = draftOf(head.data.head);
        await revise.mutateAsync({
          familyId: head.data.family_id,
          expected: head.data.head.revision,
          draft: { ...draft, cards: [...(draft.cards ?? []), card] },
        });
        onAdded(head.data.head.content.title);
      }
    } catch {
      /* Error visible. */
    }
  }
  return (
    <Dialog title="Añadir a un dashboard" onClose={onClose}>
      <div className="metric-form">
        <label>
          Dashboard
          <select
            aria-label="Dashboard de destino"
            value={choice}
            onChange={(e) => setTarget(e.target.value)}
          >
            <option value="" disabled>
              Elige un dashboard
            </option>
            {dashboards.data?.map((d) => (
              <option key={d.family_id} value={d.family_id}>
                {d.head.content.title}
              </option>
            ))}
            <option value="new">Nuevo dashboard…</option>
          </select>
        </label>
        {choice === "new" && (
          <label>
            Nombre del dashboard nuevo
            <input
              aria-label="Nombre del dashboard nuevo"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
            />
          </label>
        )}
        <label>
          Título de la tarjeta
          <input
            aria-label="Título de la tarjeta"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label>
          Forma
          <select
            aria-label="Forma de la tarjeta"
            value={view}
            onChange={(e) => setView(e.target.value as CardView)}
          >
            {views.map((v) => (
              <option key={v} value={v}>
                {VIEW_LABELS[v]}
              </option>
            ))}
          </select>
        </label>
        {metrics.length > 1 && view !== "table" && (
          <label>
            Métrica
            <select
              aria-label="Métrica de la tarjeta"
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
            >
              {metrics.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Tamaño
          <select
            aria-label="Tamaño de la tarjeta"
            value={size}
            onChange={(e) => setSize(e.target.value as CardSize)}
          >
            {Object.entries(SIZE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <p className="fine-print muted">
          La tarjeta muestra esta ejecución exacta; no cambia sola al subir
          datos nuevos.
        </p>
        {(create.isError || revise.isError) && (
          <p className="auth-error" role="alert">
            {errorMessage(create.error ?? revise.error)}
          </p>
        )}
        <div className="form-footer">
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            disabled={
              pending ||
              !title.trim() ||
              (choice === "new" ? !newTitle.trim() : !head.data)
            }
            onClick={() => void add()}
          >
            Añadir tarjeta
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
