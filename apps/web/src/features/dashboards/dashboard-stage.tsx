"use client";
import { useState } from "react";
import { LayoutDashboard, Plus, RefreshCw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import { useRepresentations } from "@/features/executions/api";
import {
  draftOf,
  useCreateDashboard,
  useDashboard,
  useDashboards,
  useRefreshDashboard,
  useReviseDashboard,
  type Card,
  type DashboardDraft,
  type DashboardView,
} from "./api";
import { DashboardCard } from "./card";

export function DashboardStage({
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
  const dashboards = useDashboards(projectId);
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const familyId = selected ?? dashboards.data?.[0]?.family_id ?? null;
  const view = useDashboard(familyId);
  return (
    <section className="dashboard-stage" aria-label="Dashboards">
      <div className="section-heading">
        <div>
          <h3>
            <LayoutDashboard size={17} /> Dashboards
          </h3>
          <p>
            Cada tarjeta muestra un análisis y la ejecución exacta que lo
            calculó. El dashboard no cambia solo al subir datos: «Actualizar»
            vuelve a calcular sus tarjetas sobre la versión que elijas.
          </p>
        </div>
        {!archived && (
          <Button size="sm" variant="outline" onClick={() => setCreating(true)}>
            <Plus size={14} /> Nuevo dashboard
          </Button>
        )}
      </div>
      {dashboards.isPending ? (
        <p className="empty-copy" role="status">
          Cargando dashboards…
        </p>
      ) : dashboards.isError ? (
        <p className="auth-error" role="alert">
          {errorMessage(dashboards.error)}
        </p>
      ) : dashboards.data.length === 0 ? (
        <p className="empty-copy">
          Todavía no hay dashboards. Calcula un análisis en Análisis y usa
          «Añadir a un dashboard», o crea uno vacío.
        </p>
      ) : (
        <>
          <label className="dashboard-picker">
            Dashboard
            <select
              aria-label="Dashboard"
              value={familyId ?? ""}
              onChange={(e) => setSelected(e.target.value)}
            >
              {dashboards.data.map((d) => (
                <option key={d.family_id} value={d.family_id}>
                  {d.head.content.title} · revisión {d.head.revision}
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
            <Board
              key={view.data.head.id}
              view={view.data}
              versionId={versionId}
              versionNumber={versionNumber}
              editable={!archived}
            />
          )}
        </>
      )}
      {creating && (
        <CreateDialog
          projectId={projectId}
          onClose={() => setCreating(false)}
          onCreated={(id) => {
            setSelected(id);
            setCreating(false);
          }}
        />
      )}
    </section>
  );
}

function Board({
  view,
  versionId,
  versionNumber,
  editable,
}: {
  view: DashboardView;
  versionId: string;
  versionNumber: number;
  editable: boolean;
}) {
  const revise = useReviseDashboard();
  const refresh = useRefreshDashboard();
  const [confirmRefresh, setConfirmRefresh] = useState(false);
  const [filterColumn, setFilterColumn] = useState("");
  const [filterValues, setFilterValues] = useState("");
  const tables = useRepresentations(versionId);
  const columnNames = new Map(
    (tables.data?.[0]?.columns ?? []).map((c) => [
      String(c.id),
      String(c.name),
    ]),
  );
  const draft = draftOf(view.head);
  const cards = draft.cards ?? [];
  const filters = draft.filters ?? [];
  const states = new Map(view.cards.map((s) => [s.card_id, s]));
  const dimensions = [
    ...new Set(view.cards.flatMap((s) => s.dimensions.map(String))),
  ];

  async function save(next: DashboardDraft) {
    try {
      await revise.mutateAsync({
        familyId: view.family_id,
        expected: view.head.revision,
        draft: next,
      });
    } catch {
      /* Error visible. */
    }
  }
  const replace = (next: Card[]) => void save({ ...draft, cards: next });
  function move(index: number, delta: -1 | 1) {
    const next = [...cards];
    [next[index], next[index + delta]] = [next[index + delta], next[index]];
    replace(next);
  }

  return (
    <div className="dashboard-board">
      <div className="dashboard-toolbar">
        <div>
          <h4 data-testid="dashboard-title">{view.head.content.title}</h4>
          <small className="muted">
            Revisión {view.head.revision} de {view.revision_count}
            {view.head.cause === "refresh" ? " · actualizada" : ""}
          </small>
        </div>
        {editable && cards.length > 0 && (
          <Button
            size="sm"
            variant="outline"
            disabled={refresh.isPending}
            onClick={() => setConfirmRefresh(true)}
          >
            <RefreshCw size={14} /> Actualizar sobre v{versionNumber}
          </Button>
        )}
      </div>
      {(revise.isError || refresh.isError) && (
        <p className="auth-error" role="alert">
          {errorMessage(revise.error ?? refresh.error)}
        </p>
      )}
      <fieldset className="dashboard-filters" aria-label="Filtros globales">
        <legend>Filtros globales</legend>
        {filters.map((f) => (
          <span key={f.column_id} className="filter-chip">
            {columnNames.get(f.column_id) ?? "dimensión"} ={" "}
            {f.values.join(", ")}
            {editable && (
              <button
                className="text-link"
                aria-label={`Quitar filtro ${columnNames.get(f.column_id) ?? ""}`}
                onClick={() =>
                  void save({
                    ...draft,
                    filters: filters.filter((x) => x.column_id !== f.column_id),
                  })
                }
              >
                <X size={12} />
              </button>
            )}
          </span>
        ))}
        {editable && dimensions.length > 0 && (
          <div className="filter-form">
            <select
              aria-label="Dimensión del filtro"
              value={filterColumn}
              onChange={(e) => setFilterColumn(e.target.value)}
            >
              <option value="">Elige una dimensión</option>
              {dimensions
                .filter((d) => !filters.some((f) => f.column_id === d))
                .map((d) => (
                  <option key={d} value={d}>
                    {columnNames.get(d) ?? d.slice(0, 8)}
                  </option>
                ))}
            </select>
            <input
              aria-label="Valores del filtro"
              placeholder="p. ej. Norte, Sur"
              value={filterValues}
              onChange={(e) => setFilterValues(e.target.value)}
            />
            <Button
              size="sm"
              variant="outline"
              disabled={!filterColumn || !filterValues.trim()}
              onClick={() => {
                const values = filterValues
                  .split(",")
                  .map((v) => v.trim())
                  .filter(Boolean);
                void save({
                  ...draft,
                  filters: [...filters, { column_id: filterColumn, values }],
                });
                setFilterColumn("");
                setFilterValues("");
              }}
            >
              Aplicar filtro
            </Button>
          </div>
        )}
        {filters.length === 0 && dimensions.length === 0 && (
          <small className="muted">
            Las tarjetas no agrupan por ninguna dimensión.
          </small>
        )}
      </fieldset>
      {cards.length === 0 ? (
        <p className="empty-copy">
          Este dashboard no tiene tarjetas. Añádelas desde Análisis.
        </p>
      ) : (
        <div className="dashboard-grid">
          {cards.map((card, index) => (
            <DashboardCard
              key={card.id}
              card={card}
              state={states.get(card.id)}
              filters={filters}
              columnNames={columnNames}
              editable={editable && !revise.isPending}
              first={index === 0}
              last={index === cards.length - 1}
              onMove={(delta) => move(index, delta)}
              onResize={(size) =>
                replace(
                  cards.map((c) => (c.id === card.id ? { ...c, size } : c)),
                )
              }
              onRemove={() => replace(cards.filter((c) => c.id !== card.id))}
            />
          ))}
        </div>
      )}
      {confirmRefresh && (
        <Dialog
          title="Actualizar el dashboard"
          onClose={() => setConfirmRefresh(false)}
        >
          <p className="dialog-copy">
            Se volverán a calcular las {cards.length} tarjeta(s) sobre la
            versión {versionNumber} y se guardará una revisión nueva. La
            revisión actual se conserva. Si un análisis no se puede calcular
            sobre esa versión (por ejemplo, falta confirmar la semántica), su
            tarjeta lo indicará sin afectar a las demás.
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
                    expected: view.head.revision,
                    versionId,
                  });
                  setConfirmRefresh(false);
                } catch {
                  /* Error visible. */
                }
              }}
            >
              Actualizar
            </Button>
          </div>
        </Dialog>
      )}
    </div>
  );
}

function CreateDialog({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: string;
  onClose: () => void;
  onCreated: (familyId: string) => void;
}) {
  const create = useCreateDashboard(projectId);
  const [title, setTitle] = useState("");
  return (
    <Dialog title="Nuevo dashboard" onClose={onClose}>
      <div className="metric-form">
        <label>
          Nombre del dashboard
          <input
            aria-label="Nombre del dashboard"
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
                  title: title.trim(),
                  cards: [],
                  filters: [],
                });
                onCreated(saved.revision.family_id);
              } catch {
                /* Error visible. */
              }
            }}
          >
            Crear dashboard
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
