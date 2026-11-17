"use client";

import { useState, type FormEvent } from "react";
import { LoaderCircle, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import {
  useAnnotate,
  type ColumnInspection,
  type DictionaryEntry,
  type InspectionView,
  type Recalculation,
} from "./api";
import {
  NATURES,
  PERSONAL_KINDS,
  PERSONAL_STATUSES,
  ROLES,
  STATUSES,
  TIME_FORMATS,
  TYPES,
  formatNumber,
  type Nature,
  type Role,
  type TimeFormat,
} from "./labels";

type Personal = "auto" | "yes" | "no";

function personalChoice(entry: DictionaryEntry): Personal {
  if (entry.personal_status === "rejected") return "no";
  if (
    entry.personal_status === "confirmed" ||
    entry.personal_status === "marked"
  )
    return "yes";
  return "auto";
}

function personalValue(choice: Personal) {
  return choice === "auto" ? null : choice === "yes";
}

/** Diccionario: clasificación inicial y explicable con correcciones opcionales que se guardan
 * como metadatos (nunca cambian el archivo). Desde la Fase 23 las correcciones cuentan: la
 * comprensión, la exploración y el dashboard se recalculan con ellas, las columnas con datos
 * personales no se envían a la IA y los textos declarados como «sin dato» crean una versión
 * derivada. */
export function DictionaryView({
  view,
  versionId,
  onOpenVersion,
  onKeepVersion,
}: {
  view: InspectionView;
  versionId: string;
  onOpenVersion?: (versionId: string) => void;
  onKeepVersion?: () => void;
}) {
  const [editing, setEditing] = useState<DictionaryEntry | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const entries = view.dictionary ?? [];
  const columns = new Map(
    (view.inspection?.columns ?? []).map((c) => [c.id, c] as const),
  );
  return (
    <div className="dataset-dictionary">
      <p className="muted">
        Clasificación automática con su procedencia. Tus correcciones nunca
        cambian el archivo: la comprensión, la exploración y el dashboard se
        recalculan con ellas, y las versiones siguientes del mismo archivo las
        heredan. Los textos que declares como «sin dato» crean una versión
        derivada; el original no cambia.
      </p>
      {view.recalculation && (
        <RecalculationBanner
          recalculation={view.recalculation}
          onOpenVersion={onOpenVersion}
        />
      )}
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
                <th scope="row">
                  {entry.name}
                  <Flags entry={entry} />
                </th>
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
                  {(entry.null_tokens?.length ?? 0) > 0 && (
                    <>
                      <br />
                      <small>
                        Textos «sin dato» declarados:{" "}
                        {entry.null_tokens!.map((t) => `«${t}»`).join(", ")}
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
            column={columns.get(editing.column_id)}
            versionId={versionId}
            onKeepVersion={onKeepVersion}
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

function Flags({ entry }: { entry: DictionaryEntry }) {
  const flags: { label: string; title: string; tone: string }[] = [];
  if (entry.dichotomous)
    flags.push({
      label: "Dicotómica",
      title: "Exactamente dos valores distintos.",
      tone: "neutral",
    });
  if (entry.ordinal_candidate)
    flags.push({
      label: "¿Escala ordinal?",
      title: entry.ordinal_candidate.reason,
      tone: "review",
    });
  if (entry.personal)
    flags.push({
      label: "Datos personales",
      title: `${entry.personal_kind ? PERSONAL_KINDS[entry.personal_kind] : "dato personal"} · ${entry.personal_status ? PERSONAL_STATUSES[entry.personal_status] : ""}. No se envía a la IA.`,
      tone: "warning",
    });
  if (!flags.length) return null;
  return (
    <span className="dictionary-flags">
      {flags.map((flag) => (
        <span
          key={flag.label}
          className={`badge ${flag.tone}`}
          title={flag.title}
        >
          {flag.label}
        </span>
      ))}
    </span>
  );
}

function RecalculationBanner({
  recalculation,
  onOpenVersion,
}: {
  recalculation: Recalculation;
  onOpenVersion?: (versionId: string) => void;
}) {
  const working = ["queued", "running"].includes(recalculation.state);
  const cleaning = recalculation.kind === "null_cleaning";
  if (working)
    return (
      <p className="info-banner recalculation-banner" role="status">
        <LoaderCircle className="spin" size={16} aria-hidden />
        {cleaning
          ? "Creando una versión derivada con los textos «sin dato» como nulos…"
          : "Recalculando la comprensión, la exploración y el dashboard con tus correcciones…"}
      </p>
    );
  if (recalculation.state !== "succeeded")
    return (
      <p className="form-error" role="alert">
        {cleaning
          ? "No se pudo crear la versión derivada"
          : "No se pudo recalcular el análisis"}{" "}
        ({recalculation.reason ?? "cancelado"}). Tus correcciones están
        guardadas.
      </p>
    );
  if (cleaning && recalculation.derived_version_id)
    return (
      <p className="success-banner recalculation-banner" role="status">
        Versión derivada lista: los textos declarados ya son nulos y se analizó
        entera. El original no cambia.
        {onOpenVersion && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => onOpenVersion(recalculation.derived_version_id!)}
          >
            Ver la versión derivada
          </Button>
        )}
      </p>
    );
  return (
    <p className="success-banner" role="status">
      Análisis actualizado con tus correcciones: la comprensión, la exploración
      y el dashboard ya las usan.
    </p>
  );
}

function Editor({
  entry,
  column,
  versionId,
  onKeepVersion,
  onDone,
}: {
  entry: DictionaryEntry;
  column?: ColumnInspection;
  versionId: string;
  onKeepVersion?: () => void;
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
  const [personal, setPersonal] = useState<Personal>(personalChoice(entry));
  const declared = entry.null_tokens ?? [];
  const [tokens, setTokens] = useState<string[]>(declared);
  const found = new Map<string, number>();
  for (const token of column?.missing.tokens ?? [])
    for (const variant of token.variants ?? []) found.set(variant, token.count);
  const options = [...new Set([...found.keys(), ...declared])];
  const changeNature = (value: Nature) => {
    setNature(value);
    // Una medida es cuantitativa: una escala o unas categorías pasan a dimensión.
    if ((value === "ordinal" || value === "nominal") && role === "measure")
      setRole("dimension");
  };
  const send = (body: Parameters<typeof annotate.mutate>[0], message: string) =>
    annotate.mutate(body, { onSuccess: () => onDone(message) });
  const save = (event: FormEvent) => {
    event.preventDefault();
    const added = tokens.filter((t) => !declared.includes(t));
    // La versión derivada será la más reciente: se sigue viendo ésta hasta que el usuario la abra.
    if (added.length) onKeepVersion?.();
    const reclassified =
      role !== entry.role ||
      nature !== entry.nature ||
      personal !== personalChoice(entry);
    send(
      {
        column_id: entry.column_id,
        role: role !== entry.automatic_role ? role : null,
        nature: nature !== entry.automatic_nature ? nature : null,
        time_format: time || null,
        notes: notes.trim() || null,
        confirmed: false,
        null_tokens: tokens,
        personal: personalValue(personal),
      },
      added.length
        ? `Corrección de «${entry.name}» guardada. Se crea una versión derivada con ${added.map((t) => `«${t}»`).join(", ")} como nulos; el original no cambia.`
        : reclassified
          ? `Corrección de «${entry.name}» guardada. Se recalculan la comprensión, la exploración y el dashboard.`
          : `Corrección de «${entry.name}» guardada. El archivo no cambia.`,
    );
  };
  return (
    <form className="dictionary-editor" onSubmit={save}>
      <p className="muted">
        Automático: {ROLES[entry.automatic_role]} ·{" "}
        {NATURES[entry.automatic_nature]}. {entry.origin}
      </p>
      {entry.ordinal_candidate && nature !== "ordinal" && (
        <div className="info-banner recalculation-banner">
          <span>
            {entry.ordinal_candidate.reason} Orden:{" "}
            {entry.ordinal_candidate.order.join(" < ")}.
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              setRole("dimension");
              setNature("ordinal");
            }}
          >
            Usar como escala ordinal
          </Button>
        </div>
      )}
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
          onChange={(e) => changeNature(e.target.value as Nature)}
        >
          {Object.entries(NATURES).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label htmlFor="annotation-personal">
        Datos personales
        <select
          id="annotation-personal"
          value={personal}
          onChange={(e) => setPersonal(e.target.value as Personal)}
        >
          <option value="auto">
            Detección automática (
            {entry.personal_kind && entry.personal_status !== "marked"
              ? `sí: ${PERSONAL_KINDS[entry.personal_kind]}`
              : "no detectados"}
            )
          </option>
          <option value="yes">Sí, contiene datos personales</option>
          <option value="no">No contiene datos personales</option>
        </select>
      </label>
      {options.length > 0 && (
        <fieldset>
          <legend>Textos que significan «sin dato»</legend>
          <small className="muted">
            Los marcados pasan a nulos en una versión derivada que se analiza
            entera; el original y esta versión no cambian.
          </small>
          {options.map((token) => (
            <label key={token} className="check-row">
              <input
                type="checkbox"
                checked={tokens.includes(token)}
                onChange={(e) =>
                  setTokens(
                    e.target.checked
                      ? [...tokens, token]
                      : tokens.filter((t) => t !== token),
                  )
                }
              />
              «{token}»
              {found.has(token)
                ? ` (${formatNumber(found.get(token))} con esta forma o similar)`
                : " (ya aplicado)"}
            </label>
          ))}
        </fieldset>
      )}
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
                {
                  column_id: entry.column_id,
                  confirmed: true,
                  null_tokens: declared,
                  personal: personalValue(personalChoice(entry)),
                },
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
