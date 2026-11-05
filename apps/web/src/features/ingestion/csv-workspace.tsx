"use client";
import { useRef, useState } from "react";
import {
  Check,
  Database,
  Download,
  FileSpreadsheet,
  GitBranch,
  LoaderCircle,
  ShieldCheck,
  UploadCloud,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import { number } from "@/lib/utils";
import { steps } from "@/lib/demo";
import { useApp } from "@/lib/providers";
import { ExecutionPanel } from "@/features/executions/execution-panel";
import { SemanticUnderstanding } from "@/features/understanding/semantic-editor";
import { CleaningStage } from "@/features/cleaning/proposal";
import {
  useCancelImport,
  useDiagnostic,
  usePreview,
  useUploadCsv,
  useVersion,
  useVersions,
  type DatasetVersion,
  type Diagnostic,
  type Separator,
} from "./api";

const states = {
  queued: "En cola",
  processing: "Procesando",
  succeeded: "Procesado",
  failed: "Error",
  cancelled: "Cancelado",
};
export function CsvWorkspace({
  projectId,
  archived,
}: {
  projectId: string;
  archived: boolean;
}) {
  const [offset, setOffset] = useState(0);
  const versions = useVersions(projectId, offset);
  const [selected, setSelected] = useState<string | null>(null);
  const [stage, setStage] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [semanticDirty, setSemanticDirty] = useState(false);
  const [semanticEpoch, setSemanticEpoch] = useState(0);
  const [planDirty, setPlanDirty] = useState(false);
  const [planEpoch, setPlanEpoch] = useState(0);
  const [cleaningDirty, setCleaningDirty] = useState(false);
  const [cleaningEpoch, setCleaningEpoch] = useState(0);
  const [pendingChange, setPendingChange] = useState<{
    kind: "stage" | "version" | "offset" | "upload";
    value?: string | number;
  } | null>(null);
  function applyChange(change: NonNullable<typeof pendingChange>) {
    if (change.kind === "stage") setStage(Number(change.value));
    else if (change.kind === "version") setSelected(String(change.value));
    else if (change.kind === "offset") {
      setOffset(Number(change.value));
      setSelected(null);
    } else setUploading(true);
  }
  function requestChange(change: NonNullable<typeof pendingChange>) {
    // El editor de planes no depende de la etapa: sólo versión/página/carga lo descartan.
    // Los borradores semántico y de limpieza viven en su etapa: cualquier cambio los descarta.
    if (
      semanticDirty ||
      cleaningDirty ||
      (planDirty && change.kind !== "stage")
    )
      setPendingChange(change);
    else applyChange(change);
  }
  const cancel = useCancelImport(projectId);
  const items = versions.data?.items ?? [];
  // La versión elegida puede no estar en la página cargada (p. ej. «Ver v1» con más de 20
  // versiones): se carga por ID y se añade al selector.
  const selectedInPage = items.find((v) => v.id === selected);
  const outside = useVersion(
    selected && !selectedInPage && versions.isSuccess ? selected : undefined,
  );
  const outsideVersion =
    outside.data?.id === selected ? outside.data : undefined;
  const loadingOutside = Boolean(
    selected && !selectedInPage && versions.isSuccess && outside.isPending,
  );
  const version = selectedInPage ?? outsideVersion ?? items[0];
  const parentId = version?.parent_version_id ?? undefined;
  const parentInPage = items.find((v) => v.id === parentId);
  const parentLookup = useVersion(
    parentId && !parentInPage ? parentId : undefined,
  );
  const parent =
    parentInPage ??
    (parentLookup.data?.id === parentId ? parentLookup.data : undefined);
  const options =
    version && !items.some((v) => v.id === version.id)
      ? [version, ...items]
      : items;
  const label = (v: DatasetVersion) => {
    const origin = v.parent_version_id
      ? (items.find((item) => item.id === v.parent_version_id) ??
        (parent?.id === v.parent_version_id ? parent : undefined))
      : undefined;
    return v.kind === "derived"
      ? `v${v.number} · derivada de ${origin ? `v${origin.number}` : "otra versión"}`
      : `v${v.number} · ${v.file_name}`;
  };
  async function showDerived(parentVersionId: string) {
    // La derivada aparece al terminar la aplicación: se recarga el listado antes de elegirla.
    const latest = (await versions.refetch()).data?.items ?? items;
    const derived = latest
      .filter((v) => v.parent_version_id === parentVersionId)
      .sort((a, b) => b.number - a.number)[0];
    if (derived) requestChange({ kind: "version", value: derived.id });
  }
  const diagnostic = useDiagnostic(version);
  if (versions.isPending || loadingOutside)
    return (
      <div className="loading-screen" aria-label="Cargando versiones">
        <div className="skeleton" />
      </div>
    );
  if (versions.isError)
    return (
      <section className="panel empty-state">
        <p role="alert">{errorMessage(versions.error)}</p>
        <Button onClick={() => void versions.refetch()}>Reintentar</Button>
      </section>
    );
  return (
    <section className="panel real-dataset">
      <div className="panel-heading">
        <div>
          <h2>
            <Database size={18} /> Datos del proyecto
          </h2>
          <p>
            Archivos propios · originales inmutables · resultados calculados
          </p>
        </div>
        {!archived && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => requestChange({ kind: "upload" })}
          >
            <UploadCloud size={16} />
            {items.length ? "Subir nueva versión" : "Subir CSV"}
          </Button>
        )}
      </div>
      {!version ? (
        <div className="empty-state">
          <FileSpreadsheet size={40} />
          <h3>Tu primer dataset empieza aquí</h3>
          <p>
            Sube un CSV en UTF-8 de hasta 5 MB. El worker comprobará su
            estructura y calculará el perfil y las reglas de calidad.
          </p>
          {!archived && (
            <CsvUpload
              projectId={projectId}
              onUploaded={() => {
                setSelected(null);
                setOffset(0);
              }}
            />
          )}
        </div>
      ) : (
        <>
          <div className="dataset-controls">
            <label htmlFor="real-version">
              <GitBranch size={15} />
              Versión
            </label>
            <select
              id="real-version"
              value={version.id}
              onChange={(e) =>
                requestChange({ kind: "version", value: e.target.value })
              }
            >
              {options.map((v) => (
                <option key={v.id} value={v.id}>
                  {label(v)} · {states[v.state]}
                  {items.includes(v) ? "" : " · fuera de esta página"}
                </option>
              ))}
            </select>
            <span
              className={`badge ${version.state === "succeeded" ? "completed" : version.state === "failed" ? "review" : "neutral"}`}
            >
              {states[version.state]}
            </span>
            {version.kind === "derived" && version.parent_version_id ? (
              <a
                className="btn btn-outline btn-sm"
                href={`/api/v1/versions/${version.parent_version_id}/original`}
                title="Una versión derivada no tiene original propio."
              >
                <Download size={14} />
                Descargar original de{" "}
                {parent ? `v${parent.number}` : "la versión de origen"}
              </a>
            ) : (
              <a
                className="btn btn-outline btn-sm"
                href={`/api/v1/versions/${version.id}/original`}
              >
                <Download size={14} />
                Descargar original
              </a>
            )}
            {(versions.data?.total ?? 0) > 20 && (
              <div className="pagination">
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={offset === 0}
                  onClick={() => {
                    requestChange({ kind: "offset", value: offset - 20 });
                  }}
                >
                  Más recientes
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={offset + 20 >= (versions.data?.total ?? 0)}
                  onClick={() => {
                    requestChange({ kind: "offset", value: offset + 20 });
                  }}
                >
                  Anteriores
                </Button>
              </div>
            )}
          </div>
          <div
            className={`version-lineage ${version.kind === "derived" ? "derived" : ""}`}
            role="status"
            aria-label="Versión que estás viendo"
          >
            <GitBranch size={14} />
            {version.kind === "derived" ? (
              <>
                <span>
                  Estás viendo <strong>v{version.number}</strong>, versión{" "}
                  <strong>derivada</strong> por limpieza de{" "}
                  <strong>
                    {parent ? `v${parent.number}` : "una versión anterior"}
                  </strong>
                  . No es la versión predeterminada.
                </span>
                {version.parent_version_id && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      requestChange({
                        kind: "version",
                        value: version.parent_version_id!,
                      })
                    }
                  >
                    Ver {parent ? `v${parent.number}` : "versión de origen"}
                  </Button>
                )}
              </>
            ) : (
              <span>
                Estás viendo <strong>v{version.number}</strong>, importada desde{" "}
                {version.file_name}.
              </span>
            )}
          </div>
          <div className="original-meta">
            <span>
              {number(version.byte_size)} bytes
              {version.kind === "derived" ? " · Parquet" : ""}
            </span>
            <span className="mono" title={version.sha256}>
              SHA-256 {version.sha256}
            </span>
          </div>
          <nav className="stepper" aria-label="Etapas del CSV real">
            {steps.map((step, i) => (
              <button
                key={step}
                className={`step ${stage === i ? "current" : ""}`}
                disabled={i > 3}
                title={
                  i > 3 ? "Se integrará en el siguiente incremento" : undefined
                }
                onClick={() => {
                  if (i !== stage) requestChange({ kind: "stage", value: i });
                }}
              >
                <span
                  className={`step-number ${version.state === "succeeded" && i <= 2 ? "done" : ""}`}
                >
                  {version.state === "succeeded" && i <= 2 ? (
                    <Check size={13} />
                  ) : (
                    i + 1
                  )}
                </span>
                <span>{step}</span>
              </button>
            ))}
          </nav>
          <div className="stage-content">
            <div className="stage-title">
              <div>
                <p className="eyebrow">ETAPA {stage + 1} · DATOS REALES</p>
                <h2>{steps[stage]}</h2>
              </div>
              <span className="badge calculated">v{version.number}</span>
            </div>
            {["queued", "processing"].includes(version.state) ? (
              <div className="processing-state" role="status">
                <LoaderCircle className="spin" size={30} />
                <h3>
                  {version.state === "queued"
                    ? "Esperando al worker"
                    : "Analizando el CSV"}
                </h3>
                <p>
                  El original ya está guardado. Puedes salir y volver; la
                  ejecución permanece en PostgreSQL.
                </p>
                <small>
                  Intento {version.attempts} de 3 · no se publican resultados
                  parciales
                </small>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCancelling(true)}
                >
                  Cancelar procesamiento
                </Button>
              </div>
            ) : version.state === "failed" ? (
              <div className="empty-state">
                <h3>No se pudo procesar este CSV</h3>
                <p role="alert">{version.error_message}</p>
                <code>{version.error_code}</code>
                <p>
                  El original sigue disponible. Corrige el archivo y súbelo como
                  una nueva versión.
                </p>
              </div>
            ) : version.state === "cancelled" ? (
              <div className="empty-state">
                <h3>Procesamiento cancelado</h3>
                <p>No se publicaron resultados. El original se conserva.</p>
              </div>
            ) : diagnostic.isPending ? (
              <p className="empty-copy" role="status">
                Cargando diagnóstico…
              </p>
            ) : diagnostic.isError ? (
              <div className="empty-state">
                <p role="alert">{errorMessage(diagnostic.error)}</p>
                <Button onClick={() => void diagnostic.refetch()}>
                  Reintentar
                </Button>
              </div>
            ) : diagnostic.data ? (
              <>
                <RealResults
                  key={`${version.id}-${stage}`}
                  version={version}
                  diagnostic={diagnostic.data}
                  stage={stage}
                />
                {stage === 3 && (
                  <CleaningStage
                    key={`${version.id}-${cleaningEpoch}`}
                    projectId={projectId}
                    version={version}
                    diagnostic={diagnostic.data}
                    archived={archived}
                    onShowDerived={(id) => void showDerived(id)}
                    onDirtyChange={setCleaningDirty}
                  />
                )}
                {stage === 1 && (
                  <SemanticUnderstanding
                    key={`${version.id}-${semanticEpoch}`}
                    versionId={version.id}
                    baselineExecutionId={version.execution_id}
                    archived={archived}
                    onDirtyChange={setSemanticDirty}
                  />
                )}
              </>
            ) : null}
          </div>
          {version.state === "succeeded" && (
            <ExecutionPanel
              key={`${version.id}-${planEpoch}`}
              projectId={projectId}
              versionId={version.id}
              archived={archived}
              onDirtyChange={setPlanDirty}
              onOpenUnderstanding={() =>
                requestChange({ kind: "stage", value: 1 })
              }
            />
          )}
        </>
      )}
      {uploading && (
        <Dialog
          title={items.length ? "Añadir una versión del CSV" : "Subir CSV"}
          onClose={() => setUploading(false)}
        >
          <CsvUpload
            projectId={projectId}
            onUploaded={() => {
              setUploading(false);
              setOffset(0);
              setSelected(null);
            }}
          />
        </Dialog>
      )}
      {pendingChange && (
        <Dialog
          title={
            semanticDirty
              ? "Hay cambios semánticos sin guardar"
              : cleaningDirty
                ? "Hay cambios sin guardar en la propuesta de limpieza"
                : "Hay cambios sin guardar en el plan"
          }
          onClose={() => setPendingChange(null)}
        >
          <p className="dialog-copy">
            Puedes seguir editando o descartar el borrador antes de cambiar de
            etapa, versión o carga. Las revisiones guardadas no se alteran.
          </p>
          <div className="form-footer">
            <Button variant="ghost" onClick={() => setPendingChange(null)}>
              Seguir editando
            </Button>
            <Button
              onClick={() => {
                if (semanticDirty) {
                  setSemanticDirty(false);
                  setSemanticEpoch((epoch) => epoch + 1);
                }
                if (cleaningDirty) {
                  setCleaningDirty(false);
                  setCleaningEpoch((epoch) => epoch + 1);
                }
                if (planDirty && pendingChange.kind !== "stage") {
                  setPlanDirty(false);
                  setPlanEpoch((epoch) => epoch + 1);
                }
                applyChange(pendingChange);
                setPendingChange(null);
              }}
            >
              Descartar y continuar
            </Button>
          </div>
        </Dialog>
      )}
      {cancelling && version && (
        <Dialog
          title="¿Cancelar el procesamiento?"
          onClose={() => setCancelling(false)}
        >
          <p className="dialog-copy">
            El worker descartará los resultados de esta ejecución. El archivo
            original seguirá conservado.
          </p>
          {cancel.isError && (
            <p className="auth-error" role="alert">
              {errorMessage(cancel.error)}
            </p>
          )}
          <div className="form-footer">
            <Button variant="ghost" onClick={() => setCancelling(false)}>
              Volver
            </Button>
            <Button
              disabled={cancel.isPending}
              onClick={async () => {
                try {
                  await cancel.mutateAsync(version.execution_id);
                  setCancelling(false);
                } catch {
                  /* Error visible. */
                }
              }}
            >
              Confirmar cancelación
            </Button>
          </div>
        </Dialog>
      )}
    </section>
  );
}

export function CsvUpload({
  projectId,
  onUploaded,
}: {
  projectId: string;
  onUploaded: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [separator, setSeparator] = useState<Separator>("auto");
  const [error, setError] = useState("");
  const upload = useUploadCsv(projectId);
  const { notify } = useApp();
  function select(value?: File) {
    if (!value || upload.isPending) return;
    setFile(null);
    setError("");
    if (!value.name.toLowerCase().endsWith(".csv")) {
      setError(
        "Selecciona un archivo CSV. XLSX y Parquet se integrarán después.",
      );
      return;
    }
    if (!value.size || value.size > 5 * 1024 * 1024) {
      setError("Selecciona un CSV no vacío de hasta 5 MB.");
      return;
    }
    setFile(value);
  }
  return (
    <div className="csv-upload">
      <input
        hidden
        ref={input}
        type="file"
        accept=".csv,text/csv"
        aria-label="Archivo CSV"
        onChange={(e) => select(e.target.files?.[0])}
      />
      <div
        className="dropzone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          select(e.dataTransfer.files[0]);
        }}
      >
        <UploadCloud size={25} />
        <h3>{file?.name ?? "Arrastra tu CSV aquí"}</h3>
        <p>UTF-8 · hasta 5 MB · el original se conserva sin cambios</p>
        <Button
          variant="outline"
          disabled={upload.isPending}
          onClick={() => input.current?.click()}
        >
          Seleccionar CSV
        </Button>
      </div>
      <label htmlFor={`separator-${projectId}`}>Separador de columnas</label>
      <select
        id={`separator-${projectId}`}
        disabled={upload.isPending}
        value={separator}
        onChange={(e) => setSeparator(e.target.value as Separator)}
      >
        <option value="auto">Detectar automáticamente</option>
        <option value=",">Coma (,)</option>
        <option value=";">Punto y coma (;)</option>
        <option value="tab">Tabulador</option>
      </select>
      {(error || upload.isError) && (
        <p className="auth-error" role="alert">
          {error || errorMessage(upload.error)}
        </p>
      )}
      <Button
        disabled={!file || upload.isPending}
        onClick={async () => {
          if (!file) return;
          try {
            await upload.mutateAsync({ file, separator });
            setFile(null);
            if (input.current) input.current.value = "";
            notify("Original conservado. Procesamiento encolado.");
            onUploaded();
          } catch {
            /* Error visible y clave de reintento conservada. */
          }
        }}
      >
        {upload.isPending ? (
          <LoaderCircle className="spin" size={16} />
        ) : (
          <UploadCloud size={16} />
        )}
        {upload.isPending ? "Enviando CSV…" : "Subir y analizar CSV"}
      </Button>
    </div>
  );
}

function RealResults({
  version,
  diagnostic,
  stage,
}: {
  version: DatasetVersion;
  diagnostic: Diagnostic;
  stage: number;
}) {
  const [page, setPage] = useState(0);
  const [issue, setIssue] = useState<string | undefined>();
  const preview = usePreview(version, page, issue);
  const { profile, quality } = diagnostic;
  return (
    <>
      <div className="mini-metrics">
        <div>
          <small>Registros</small>
          <strong>{number(profile.row_count)}</strong>
        </div>
        <div>
          <small>Columnas</small>
          <strong>{profile.column_count}</strong>
        </div>
        <div>
          <small>Completitud de celdas</small>
          <strong>
            {quality.completeness_percent.toLocaleString("es-ES")} %
          </strong>
        </div>
      </div>
      {stage === 1 ? (
        <>
          <div className="info-banner">
            <ShieldCheck size={18} />
            <span>
              {profile.columns.some((c) => c.technical_type !== "string")
                ? "Esta versión tiene columnas convertidas por una limpieza aprobada (tipo técnico distinto de texto); el resto se conserva como texto. "
                : "Los valores se conservan como texto en Parquet. "}
              Los tipos sugeridos son heurísticas deterministas, no decisiones
              aprobadas ni sugerencias de IA.
            </span>
          </div>
          <div className="table-scroll bordered">
            <table>
              <thead>
                <tr>
                  <th>Columna</th>
                  <th>Tipo técnico</th>
                  <th>Tipo sugerido</th>
                  <th>Nulos</th>
                  <th>Únicos</th>
                  <th>Ejemplos</th>
                </tr>
              </thead>
              <tbody>
                {profile.columns.map((column) => (
                  <tr key={column.name}>
                    <td>
                      <strong>{column.name}</strong>
                    </td>
                    <td className="mono">{column.technical_type}</td>
                    <td>
                      <span className="badge neutral">
                        {column.suggested_type}
                      </span>
                    </td>
                    <td>
                      {column.null_count} (
                      {((column.null_count / profile.row_count) * 100).toFixed(
                        2,
                      )}{" "}
                      %)
                    </td>
                    <td>{number(column.unique_count)}</td>
                    <td className="sample-cell">
                      {column.examples.join(" · ") || "Sin valores"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="section-heading">
            <h3>Estadísticas numéricas sugeridas</h3>
            <span className="badge calculated">
              Decimal · sin convertir el dataset
            </span>
          </div>
          {profile.columns
            .filter((c) => c.numeric)
            .map((c) => (
              <div className="finding-card" key={c.name}>
                <strong>{c.name}</strong>
                <p>
                  Suma: <code>{c.numeric!.total}</code> · media:{" "}
                  <code>{c.numeric!.mean}</code>
                </p>
                <small>
                  {c.numeric!.count} valores válidos · nulos excluidos ·
                  precisión de cálculo de 50 dígitos.
                </small>
              </div>
            ))}
        </>
      ) : (
        <>
          {stage === 2 && (
            <>
              <div className="info-banner">
                <ShieldCheck size={18} />
                <span>
                  Completitud = celdas no vacías / total de celdas × 100. Se
                  evalúan vacíos, filas duplicadas y valores compuestos sólo de
                  espacios. No es una puntuación universal de calidad.
                </span>
              </div>
              <div className="mini-metrics">
                <div>
                  <small>Celdas vacías</small>
                  <strong>{number(quality.missing_cells)}</strong>
                </div>
                <div>
                  <small>Filas duplicadas adicionales</small>
                  <strong>{number(quality.duplicate_rows)}</strong>
                </div>
                <div>
                  <small>Celdas sólo con espacios</small>
                  <strong>{number(quality.whitespace_cells)}</strong>
                </div>
              </div>
              <div className="section-heading">
                <h3>Incidencias · {quality.issues.length}</h3>
                {issue && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setIssue(undefined);
                      setPage(0);
                    }}
                  >
                    <X size={14} />
                    Quitar filtro
                  </Button>
                )}
              </div>
              {quality.issues.map((item) => (
                <div
                  className={`issue-card ${issue === item.id ? "issue-selected" : ""}`}
                  key={item.id}
                >
                  <div>
                    <strong>
                      {item.rule} · {item.column ?? "Todas las columnas"}
                    </strong>
                    <p>{item.description}</p>
                    <small>
                      {item.affected_rows} registros · gravedad{" "}
                      {item.severity === "medium" ? "media" : "baja"}
                    </small>
                    <small>{item.proposed_action}</small>
                    <button
                      className="text-link"
                      onClick={() => {
                        setIssue(item.id);
                        setPage(0);
                      }}
                    >
                      Ver registros afectados
                    </button>
                  </div>
                  <span className="badge review">
                    {number(item.affected_rows)}
                  </span>
                </div>
              ))}
              {!quality.issues.length && (
                <div className="success-banner">
                  <ShieldCheck size={20} />
                  No se detectaron incidencias en las tres reglas evaluadas.
                </div>
              )}
            </>
          )}
          <div className="section-heading">
            <h3>
              {issue
                ? `Registros afectados · ${issue}`
                : "Vista previa del CSV"}
            </h3>
            <span className="badge calculated">Datos reales</span>
          </div>
          {preview.isPending ? (
            <p className="empty-copy" role="status">
              Cargando registros…
            </p>
          ) : preview.isError ? (
            <div className="empty-state">
              <p role="alert">{errorMessage(preview.error)}</p>
              <Button onClick={() => void preview.refetch()}>Reintentar</Button>
            </div>
          ) : (
            preview.data && (
              <div className="data-table">
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Registro</th>
                        {preview.data.columns.map((name) => (
                          <th key={name}>{name}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.data.rows.map((row) => (
                        <tr key={row.row_number}>
                          <td>{row.row_number}</td>
                          {preview.data!.columns.map((name) => (
                            <td
                              key={name}
                              className="csv-value"
                              title={row.values[name] ?? "nulo"}
                            >
                              {row.values[name] === null ? (
                                <span className="null-value">nulo</span>
                              ) : (
                                row.values[name]
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="table-footer">
                  <span>
                    {preview.data.rows.length} de {number(preview.data.total)}{" "}
                    registros · página {page + 1}
                  </span>
                  <div className="pagination">
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={page === 0}
                      onClick={() => setPage((p) => p - 1)}
                    >
                      Anterior
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={(page + 1) * 10 >= preview.data.total}
                      onClick={() => setPage((p) => p + 1)}
                    >
                      Siguiente
                    </Button>
                  </div>
                </div>
              </div>
            )
          )}
        </>
      )}
      <div className="dataset-provenance">
        <span>
          {profile.engine_version} · Polars {profile.polars_version}
        </span>
        <span>
          UTF-8 · separador{" "}
          {profile.separator === "\t" ? "tabulador" : `«${profile.separator}»`}{" "}
          · {quality.rule_version}
        </span>
      </div>
      <p className="muted fine-print">
        El original se conserva íntegro. Las celdas vacías se representan como
        nulos en la copia analítica; los espacios y los ceros iniciales
        permanecen. Las etapas posteriores todavía no procesan este dataset.
      </p>
    </>
  );
}
