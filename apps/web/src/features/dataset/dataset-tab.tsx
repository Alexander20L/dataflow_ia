"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import {
  recalculating,
  useInspection,
  useRefreshAfterRecalculation,
  type InspectionView,
} from "./api";
import { ColumnsView } from "./columns";
import { DictionaryView } from "./dictionary";
import { FileView } from "./file";
import { QualityView } from "./quality";
import { RecordsView } from "./records";
import { SummaryView } from "./summary";

const SUBVIEWS = [
  { id: "summary", label: "Resumen" },
  { id: "records", label: "Registros" },
  { id: "columns", label: "Columnas" },
  { id: "dictionary", label: "Diccionario" },
  { id: "quality", label: "Calidad" },
  { id: "file", label: "Archivo" },
] as const;
export type DatasetSubview = (typeof SUBVIEWS)[number]["id"];
type Subview = DatasetSubview;

/** Fase 22: inspección del dataset. Todo viene del servidor (calculado una vez sobre la tabla
 * completa); cambiar de subvista no recalcula nada. Fase 23: las correcciones del Diccionario
 * recalculan el análisis; al terminar, las demás pestañas vuelven a pedir sus resultados. */
export function DatasetTab({
  versionId,
  onOpenVersion,
  onKeepVersion,
  initialSubview,
}: {
  versionId: string;
  /** Fase 24B: subvista con la que se abre (p. ej. el Diccionario desde Comprensión). */
  initialSubview?: DatasetSubview;
  onOpenVersion?: (versionId: string) => void;
  /** Fija la versión que se está viendo: la derivada no la sustituye sin que el usuario lo pida. */
  onKeepVersion?: () => void;
}) {
  const inspection = useInspection(versionId);
  const [subview, setSubview] = useState<Subview>(initialSubview ?? "summary");
  const [focusRow, setFocusRow] = useState<number | undefined>();
  const refresh = useRefreshAfterRecalculation(versionId);
  const busy = recalculating(inspection.data);
  const wasBusy = useRef(busy);
  useEffect(() => {
    if (wasBusy.current && !busy) refresh();
    wasBusy.current = busy;
  }, [busy, refresh]);
  if (inspection.isPending)
    return (
      <p className="empty-copy" role="status">
        Cargando la inspección del dataset…
      </p>
    );
  if (inspection.isError)
    return (
      <div className="empty-state">
        <p role="alert">{errorMessage(inspection.error)}</p>
        <Button onClick={() => void inspection.refetch()}>Reintentar</Button>
      </div>
    );
  const view = inspection.data;
  if (view.state === "queued" || view.state === "running")
    return (
      <div className="processing-state" role="status">
        <LoaderCircle className="spin" size={26} />
        <h3>Inspeccionando el dataset</h3>
        <p>
          Se calcula una sola vez sobre todos los registros: perfil de cada
          columna, calidad y lectura del archivo.
        </p>
      </div>
    );
  if (view.state === "failed")
    return (
      <div className="empty-state">
        <h3>No se pudo inspeccionar esta versión</h3>
        <p role="alert">
          La inspección terminó con error ({view.reason ?? "sin detalle"}). El
          resto del análisis no se ve afectado.
        </p>
      </div>
    );
  if (view.state === "unavailable" || !view.inspection)
    return (
      <div className="empty-state">
        <h3>Inspección no disponible</h3>
        <p>{view.reason ?? "Esta versión no tiene inspección."}</p>
      </div>
    );
  const onKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step =
      event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = SUBVIEWS[(index + step + SUBVIEWS.length) % SUBVIEWS.length];
    setSubview(next.id);
    document.getElementById(`dataset-tab-${next.id}`)?.focus();
  };
  return (
    <section className="dataset-tab" aria-label="Dataset">
      <div
        className="dataset-subnav"
        role="tablist"
        aria-label="Secciones del dataset"
      >
        {SUBVIEWS.map((item, index) => (
          <button
            key={item.id}
            id={`dataset-tab-${item.id}`}
            type="button"
            role="tab"
            aria-selected={subview === item.id}
            aria-controls={`dataset-panel-${item.id}`}
            tabIndex={subview === item.id ? 0 : -1}
            onClick={() => setSubview(item.id)}
            onKeyDown={(event) => onKey(event, index)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div
        id={`dataset-panel-${subview}`}
        role="tabpanel"
        aria-labelledby={`dataset-tab-${subview}`}
        className="inspection-panel"
      >
        <Subview
          view={view}
          subview={subview}
          versionId={versionId}
          focusRow={focusRow}
          onShowRow={(row) => {
            setFocusRow(row);
            setSubview("records");
          }}
          onOpenVersion={onOpenVersion}
          onKeepVersion={onKeepVersion}
        />
      </div>
    </section>
  );
}

function Subview({
  view,
  subview,
  versionId,
  focusRow,
  onShowRow,
  onOpenVersion,
  onKeepVersion,
}: {
  view: InspectionView;
  subview: Subview;
  versionId: string;
  focusRow?: number;
  onShowRow: (row: number) => void;
  onOpenVersion?: (versionId: string) => void;
  onKeepVersion?: () => void;
}) {
  const inspection = view.inspection!;
  switch (subview) {
    case "summary":
      return <SummaryView view={view} />;
    case "records":
      return (
        <RecordsView
          key={focusRow ?? "records"}
          versionId={versionId}
          inspection={inspection}
          focusRow={focusRow}
        />
      );
    case "columns":
      return <ColumnsView inspection={inspection} />;
    case "dictionary":
      return (
        <DictionaryView
          view={view}
          versionId={versionId}
          onOpenVersion={onOpenVersion}
          onKeepVersion={onKeepVersion}
        />
      );
    case "quality":
      return <QualityView inspection={inspection} onShowRow={onShowRow} />;
    case "file":
      return <FileView inspection={inspection} versionId={versionId} />;
  }
}
