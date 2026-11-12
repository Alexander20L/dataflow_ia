"use client";

import { useState, type FormEvent } from "react";
import { Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import { useAnnotate, type DictionaryEntry, type InspectionView } from "./api";
import {
  NATURES,
  ROLES,
  STATUSES,
  TIME_FORMATS,
  TYPES,
  formatNumber,
  type Nature,
  type Role,
  type TimeFormat,
} from "./labels";

/** Diccionario: clasificación inicial y explicable, con correcciones opcionales que se guardan
 * como metadatos (nunca cambian el archivo ni los cálculos). */
export function DictionaryView({
  view,
  versionId,
}: {
  view: InspectionView;
  versionId: string;
}) {
  const [editing, setEditing] = useState<DictionaryEntry | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const entries = view.dictionary ?? [];
  return (
    <div className="dataset-dictionary">
      <p className="muted">
        Clasificación automática con su procedencia. Puedes corregirla o
        confirmarla: se guarda como metadato, no modifica el archivo, y las
        versiones siguientes del mismo archivo la heredan.
      </p>
      {saved && (
        <p className="success-banner" role="status">
          {saved}
        </p>
      )}
      <div className="table-scroll">
        <table className="data-table dictionary-table">
          <thead>
            <tr>
              <th scope="col">Columna</th>
              <th scope="col">Tipo técnico</th>
              <th scope="col">Naturaleza</th>
              <th scope="col">Rol</th>
              <th scope="col">Descripción</th>
              <th scope="col">Únicos</th>
              <th scope="col">Nulos</th>
              <th scope="col">Estado</th>
              <th scope="col" aria-label="Acciones" />
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.column_id}>
                <th scope="row">{entry.name}</th>
                <td>{TYPES[entry.technical_type]}</td>
                <td>{NATURES[entry.nature]}</td>
                <td>{ROLES[entry.role]}</td>
                <td>
                  {entry.description}
                  {entry.notes && (
                    <>
                      <br />
                      <small>Observación: {entry.notes}</small>
                    </>
                  )}
                  {entry.time_format && (
                    <>
                      <br />
                      <small>
                        Interpretación temporal:{" "}
                        {TIME_FORMATS[entry.time_format as TimeFormat]}
                      </small>
                    </>
                  )}
                </td>
                <td>{formatNumber(entry.distinct)}</td>
                <td>{formatNumber(entry.nulls)}</td>
                <td>
                  <span
                    className={`badge ${entry.status === "corrected" ? "review" : entry.status === "confirmed" ? "completed" : "neutral"}`}
                    title={entry.origin}
                  >
                    {STATUSES[entry.status]}
                  </span>
                  <br />
                  <small className="muted">{entry.origin}</small>
                </td>
                <td>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Editar la clasificación de ${entry.name}`}
                    onClick={() => {
                      setSaved(null);
                      setEditing(entry);
                    }}
                  >
                    <Pencil size={14} aria-hidden /> Editar
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && (
        <Dialog
          title={`Clasificación de «${editing.name}»`}
          onClose={() => setEditing(null)}
        >
          <Editor
            entry={editing}
            versionId={versionId}
            onDone={(message) => {
              setSaved(message);
              setEditing(null);
            }}
          />
        </Dialog>
      )}
    </div>
  );
}

function Editor({
  entry,
  versionId,
  onDone,
}: {
  entry: DictionaryEntry;
  versionId: string;
  onDone: (message: string) => void;
}) {
  const annotate = useAnnotate(versionId);
  const corrected = entry.status === "corrected";
  const [role, setRole] = useState<Role>(entry.role);
  const [nature, setNature] = useState<Nature>(entry.nature);
  const [time, setTime] = useState<TimeFormat | "">(
    (entry.time_format as TimeFormat | null) ?? "",
  );
  const [notes, setNotes] = useState(entry.notes ?? "");
  const send = (body: Parameters<typeof annotate.mutate>[0], message: string) =>
    annotate.mutate(body, { onSuccess: () => onDone(message) });
  const save = (event: FormEvent) => {
    event.preventDefault();
    send(
      {
        column_id: entry.column_id,
        role: role !== entry.automatic_role ? role : null,
        nature: nature !== entry.automatic_nature ? nature : null,
        time_format: time || null,
        notes: notes.trim() || null,
        confirmed: false,
      },
      `Corrección de «${entry.name}» guardada. El archivo y los cálculos no cambian.`,
    );
  };
  return (
    <form className="dictionary-editor" onSubmit={save}>
      <p className="muted">
        Automático: {ROLES[entry.automatic_role]} ·{" "}
        {NATURES[entry.automatic_nature]}. {entry.origin}
      </p>
      <label htmlFor="annotation-role">
        Rol analítico
        <select
          id="annotation-role"
          value={role}
          onChange={(e) => setRole(e.target.value as Role)}
        >
          {Object.entries(ROLES).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label htmlFor="annotation-nature">
        Naturaleza estadística
        <select
          id="annotation-nature"
          value={nature}
          onChange={(e) => setNature(e.target.value as Nature)}
        >
          {Object.entries(NATURES).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label htmlFor="annotation-time">
        Interpretación temporal
        <select
          id="annotation-time"
          value={time}
          onChange={(e) => setTime(e.target.value as TimeFormat | "")}
        >
          <option value="">Sin indicar</option>
          {Object.entries(TIME_FORMATS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label htmlFor="annotation-notes">
        Observación
        <textarea
          id="annotation-notes"
          maxLength={500}
          rows={3}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </label>
      {annotate.isError && (
        <p role="alert" className="form-error">
          {errorMessage(annotate.error)}
        </p>
      )}
      <div className="dialog-actions">
        <Button type="submit" disabled={annotate.isPending}>
          Guardar corrección
        </Button>
        {!corrected && entry.status !== "confirmed" && (
          <Button
            type="button"
            variant="outline"
            disabled={annotate.isPending}
            onClick={() =>
              send(
                { column_id: entry.column_id, confirmed: true },
                `Clasificación automática de «${entry.name}» confirmada.`,
              )
            }
          >
            Confirmar la automática
          </Button>
        )}
        {entry.status !== "automatic" && (
          <Button
            type="button"
            variant="ghost"
            disabled={annotate.isPending}
            onClick={() =>
              send(
                { column_id: entry.column_id, confirmed: false },
                `«${entry.name}» vuelve a la clasificación automática.`,
              )
            }
          >
            Volver a la automática
          </Button>
        )}
      </div>
    </form>
  );
}
