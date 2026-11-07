"use client";
import { useState } from "react";
import { AlertTriangle, Database, LoaderCircle, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import { useApp } from "@/lib/providers";
import {
  useConnections,
  useCreateConnection,
  useDiscoverConnection,
  useExtract,
  usePreviewExtraction,
  useRevokeConnection,
  type ConnectionDraft,
  type Discovery,
  type ExtractionPreview,
  type SqlObject,
} from "./api";

const CONSISTENCY: Record<string, string> = {
  snapshot: "Instantánea consistente (SNAPSHOT)",
  read_committed_snapshot: "READ COMMITTED SNAPSHOT",
  none: "Sin garantía de consistencia: la tabla podía cambiar durante la lectura",
};

const key = (o: SqlObject) => `${o.schema_name}.${o.name}`;

/** Fase 12B: conexión de sólo lectura, lista blanca de objetos, vista previa y extracción. */
export function SqlServerSource({
  projectId,
  onUploaded,
}: {
  projectId: string;
  onUploaded: () => void;
}) {
  const connections = useConnections(projectId);
  const [creating, setCreating] = useState(false);
  if (connections.isPending)
    return (
      <p className="muted">
        <LoaderCircle className="spin" size={14} /> Cargando conexiones…
      </p>
    );
  const items = connections.data ?? [];
  if (creating || !items.length)
    return (
      <NewConnection
        projectId={projectId}
        onCancel={items.length ? () => setCreating(false) : undefined}
        onCreated={() => setCreating(false)}
      />
    );
  return (
    <ExtractFrom
      projectId={projectId}
      onNew={() => setCreating(true)}
      onUploaded={onUploaded}
    />
  );
}

function NewConnection({
  projectId,
  onCancel,
  onCreated,
}: {
  projectId: string;
  onCancel?: () => void;
  onCreated: () => void;
}) {
  const discover = useDiscoverConnection(projectId);
  const create = useCreateConnection(projectId);
  const [draft, setDraft] = useState<ConnectionDraft>({
    name: "",
    host: "",
    port: 1433,
    database: "",
    username: "",
    password: "",
    encrypt: true,
    trust_server_certificate: false,
  });
  const [found, setFound] = useState<Discovery | null>(null);
  const [allowed, setAllowed] = useState<Set<string>>(new Set());
  const set = (change: Partial<ConnectionDraft>) => {
    setDraft({ ...draft, ...change });
    setFound(null);
  };
  const field = (
    label: string,
    name: "name" | "host" | "database" | "username" | "password",
    type = "text",
  ) => (
    <>
      <label htmlFor={`sql-${name}-${projectId}`}>{label}</label>
      <input
        id={`sql-${name}-${projectId}`}
        type={type}
        autoComplete={type === "password" ? "new-password" : "off"}
        value={draft[name] as string}
        onChange={(e) => set({ [name]: e.target.value })}
      />
    </>
  );
  const complete =
    draft.name &&
    draft.host &&
    draft.database &&
    draft.username &&
    draft.password;
  return (
    <div className="sql-source">
      <p className="muted">
        Usa un usuario de <strong>sólo lectura</strong>. La contraseña se guarda
        cifrada y nunca se vuelve a mostrar.
      </p>
      {field("Nombre de la conexión", "name")}
      {field("Servidor", "host")}
      <label htmlFor={`sql-port-${projectId}`}>Puerto</label>
      <input
        id={`sql-port-${projectId}`}
        type="number"
        min={1}
        max={65535}
        value={draft.port}
        onChange={(e) => set({ port: Number(e.target.value) || 1433 })}
      />
      {field("Base de datos", "database")}
      {field("Usuario", "username")}
      {field("Contraseña", "password", "password")}
      <label className="check">
        <input
          type="checkbox"
          checked={draft.trust_server_certificate}
          onChange={(e) => set({ trust_server_certificate: e.target.checked })}
        />
        Confiar en el certificado del servidor (sólo entornos internos)
      </label>
      {(discover.isError || create.isError) && (
        <p className="auth-error" role="alert">
          {errorMessage(discover.error ?? create.error)}
        </p>
      )}
      {!found ? (
        <Button
          disabled={!complete || discover.isPending}
          onClick={async () => {
            try {
              setFound(await discover.mutateAsync(draft));
              setAllowed(new Set());
            } catch {
              /* Error visible. */
            }
          }}
        >
          {discover.isPending ? (
            <LoaderCircle className="spin" size={16} />
          ) : (
            <Database size={16} />
          )}
          Probar conexión y listar objetos
        </Button>
      ) : (
        <>
          {found.can_write && (
            <div className="warning-banner">
              <AlertTriangle size={16} />
              <span>
                Este usuario tiene permisos de escritura. DataFlow sólo lee,
                pero se recomienda un usuario de sólo lectura.
              </span>
            </div>
          )}
          <p className="muted">
            Elige las tablas o vistas que se podrán extraer (lista blanca).
          </p>
          <div className="sql-objects">
            {found.objects.map((object) => (
              <label key={key(object)} className="check">
                <input
                  type="checkbox"
                  checked={allowed.has(key(object))}
                  onChange={(e) => {
                    const next = new Set(allowed);
                    if (e.target.checked) next.add(key(object));
                    else next.delete(key(object));
                    setAllowed(next);
                  }}
                />
                {key(object)} {object.kind === "view" ? "(vista)" : ""}
              </label>
            ))}
          </div>
          <Button
            disabled={!allowed.size || create.isPending}
            onClick={async () => {
              try {
                await create.mutateAsync({
                  ...draft,
                  allowed_objects: found.objects
                    .filter((o) => allowed.has(key(o)))
                    .map((o) => ({ schema_name: o.schema_name, name: o.name })),
                });
                onCreated();
              } catch {
                /* Error visible. */
              }
            }}
          >
            Guardar conexión
          </Button>
        </>
      )}
      {onCancel && (
        <Button variant="outline" onClick={onCancel}>
          Volver a mis conexiones
        </Button>
      )}
    </div>
  );
}

function ExtractFrom({
  projectId,
  onNew,
  onUploaded,
}: {
  projectId: string;
  onNew: () => void;
  onUploaded: () => void;
}) {
  const { notify } = useApp();
  const connections = useConnections(projectId).data ?? [];
  const revoke = useRevokeConnection(projectId);
  const preview = usePreviewExtraction();
  const extract = useExtract(projectId);
  const [connectionId, setConnectionId] = useState(connections[0]?.id ?? "");
  const connection =
    connections.find((c) => c.id === connectionId) ?? connections[0];
  const [target, setTarget] = useState(
    connection?.allowed_objects[0] ? key(connection.allowed_objects[0]) : "",
  );
  const [rows, setRows] = useState<ExtractionPreview | null>(null);
  const selected = connection?.allowed_objects.find((o) => key(o) === target);
  const busy = preview.isPending || extract.isPending;
  if (!connection) return null;
  return (
    <div className="sql-source">
      <label htmlFor={`sql-connection-${projectId}`}>Conexión</label>
      <select
        id={`sql-connection-${projectId}`}
        value={connection.id}
        disabled={busy}
        onChange={(e) => {
          const next = connections.find((c) => c.id === e.target.value);
          setConnectionId(e.target.value);
          setTarget(
            next?.allowed_objects[0] ? key(next.allowed_objects[0]) : "",
          );
          setRows(null);
        }}
      >
        {connections.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name} · {c.host}/{c.database}
          </option>
        ))}
      </select>
      <label htmlFor={`sql-object-${projectId}`}>
        Tabla o vista autorizada
      </label>
      <select
        id={`sql-object-${projectId}`}
        value={target}
        disabled={busy}
        onChange={(e) => {
          setTarget(e.target.value);
          setRows(null);
        }}
      >
        {connection.allowed_objects.map((o) => (
          <option key={key(o)} value={key(o)}>
            {key(o)}
          </option>
        ))}
      </select>
      {connection.can_write && (
        <p className="muted fine-print">
          Aviso: el usuario de esta conexión tiene permisos de escritura.
        </p>
      )}
      {(preview.isError || extract.isError || revoke.isError) && (
        <p className="auth-error" role="alert">
          {errorMessage(preview.error ?? extract.error ?? revoke.error)}
        </p>
      )}
      <Button
        variant="outline"
        disabled={!selected || busy}
        onClick={async () => {
          if (!selected) return;
          try {
            setRows(
              await preview.mutateAsync({
                connectionId: connection.id,
                target: selected,
              }),
            );
          } catch {
            /* Error visible. */
          }
        }}
      >
        {preview.isPending && <LoaderCircle className="spin" size={16} />}
        Vista previa (20 filas)
      </Button>
      {rows && (
        <>
          <p className="muted">{CONSISTENCY[rows.consistency]}</p>
          <div className="table-scroll bordered xlsx-preview">
            <table>
              <thead>
                <tr>
                  {rows.columns.map((c) => (
                    <th key={c.name} title={c.sql_type}>
                      {c.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.rows.map((row, index) => (
                  <tr key={index}>
                    {row.map((cell, position) => (
                      <td
                        key={position}
                        className={cell === null ? "muted" : ""}
                      >
                        {cell ?? "nulo"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <Button
        disabled={!selected || !rows || busy}
        onClick={async () => {
          if (!selected) return;
          try {
            await extract.mutateAsync({
              connectionId: connection.id,
              target: selected,
            });
            notify("Extracción materializada. Procesamiento encolado.");
            onUploaded();
          } catch {
            /* Error visible y clave de reintento conservada. */
          }
        }}
      >
        {extract.isPending ? (
          <LoaderCircle className="spin" size={16} />
        ) : (
          <Database size={16} />
        )}
        {extract.isPending ? "Extrayendo…" : "Extraer e importar"}
      </Button>
      <div className="sql-actions">
        <Button variant="outline" onClick={onNew} disabled={busy}>
          Nueva conexión
        </Button>
        <Button
          variant="outline"
          disabled={busy || revoke.isPending}
          onClick={async () => {
            try {
              await revoke.mutateAsync(connection.id);
              notify("Conexión revocada; su contraseña se ha borrado.");
            } catch {
              /* Error visible. */
            }
          }}
        >
          <Trash2 size={16} /> Revocar conexión
        </Button>
      </div>
    </div>
  );
}
