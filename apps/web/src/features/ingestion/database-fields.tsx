"use client";

import { Globe, LockKeyhole } from "lucide-react";
import { useDatabaseAccess, type DatabaseEngine } from "./api";

export type DatabaseForm = {
  engine: DatabaseEngine;
  server: string;
  port: string;
  database: string;
  schema: string;
  user: string;
  password: string;
  /** Fase 32: certificado de la autoridad del proveedor (PEM), opcional. */
  certificate: string;
};

export const EMPTY_DATABASE: DatabaseForm = {
  engine: "sqlserver",
  server: "",
  port: "1433",
  database: "",
  schema: "",
  user: "",
  password: "",
  certificate: "",
};

const PORTS: Record<DatabaseEngine, string> = {
  sqlserver: "1433",
  postgresql: "5432",
};

/** Problema de los datos de conexión, o null si están completos. */
export function databaseProblem(form: DatabaseForm) {
  const port = Number(form.port);
  if (
    !form.server.trim() ||
    !form.database.trim() ||
    !form.user.trim() ||
    !form.password ||
    !Number.isInteger(port) ||
    port < 1 ||
    port > 65535 ||
    (form.engine === "postgresql" && !form.schema.trim())
  )
    return form.engine === "postgresql"
      ? "Completa servidor, puerto, base, esquema, usuario y contraseña."
      : "Completa servidor, puerto, base, usuario y contraseña.";
  if (
    form.engine === "postgresql" &&
    form.certificate.trim() &&
    !form.certificate.includes("-----BEGIN CERTIFICATE-----")
  )
    return "El certificado debe estar en formato PEM (-----BEGIN CERTIFICATE-----).";
  return null;
}

/** Fases 18B, 31 y 32: datos de conexión de un solo uso a SQL Server o PostgreSQL. Campos
 * controlados (van dentro del formulario de la pantalla de carga). La contraseña se envía una
 * vez y no se guarda. En el modo público (sólo PostgreSQL) se indica desde qué direcciones sale
 * DataFlow y se puede pegar el certificado del proveedor. */
export function DatabaseFields({
  value,
  onChange,
}: {
  value: DatabaseForm;
  onChange: (next: DatabaseForm) => void;
}) {
  const access = useDatabaseAccess().data;
  const mode = access?.[value.engine];
  const isPublic = value.engine === "postgresql" && mode === "public";
  const egress = access?.egress_ips ?? [];
  const set =
    (name: keyof DatabaseForm) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      onChange({ ...value, [name]: e.target.value });
  const engine = (next: DatabaseEngine) =>
    onChange({
      ...value,
      engine: next,
      port: value.port === PORTS[value.engine] ? PORTS[next] : value.port,
      schema:
        next === "postgresql" && !value.schema.trim()
          ? "public"
          : next === "sqlserver" && value.schema === "public"
            ? ""
            : value.schema,
    });
  return (
    <fieldset className="database-fields">
      <legend>Motor de base de datos</legend>
      <div className="engine-choice" role="radiogroup" aria-label="Motor">
        {(
          [
            ["sqlserver", "SQL Server"],
            ["postgresql", "PostgreSQL"],
          ] as const
        ).map(([id, label]) => (
          <label key={id} className={value.engine === id ? "selected" : ""}>
            <input
              type="radio"
              name="database-engine"
              checked={value.engine === id}
              onChange={() => engine(id)}
            />
            {label}
          </label>
        ))}
      </div>
      {mode === "disabled" && (
        <p className="database-note" role="status">
          La conexión a{" "}
          {value.engine === "sqlserver" ? "SQL Server" : "PostgreSQL"} no está
          activada en este entorno.
        </p>
      )}
      {isPublic && (
        <div className="database-note" role="note">
          <Globe size={14} aria-hidden />
          <div>
            <p>
              Usa un usuario con permiso <strong>sólo de lectura</strong>.
            </p>
            {egress.length ? (
              <p>
                Tu base debe aceptar conexiones desde{" "}
                {egress.length === 1 ? "esta dirección" : "estas direcciones"}:{" "}
                <code>{egress.join(", ")}</code>
              </p>
            ) : null}
          </div>
        </div>
      )}
      <div className="database-grid">
        <label htmlFor="db-server">Servidor</label>
        <input
          id="db-server"
          placeholder={
            value.engine === "sqlserver" ? "sql.empresa.com" : "db.empresa.com"
          }
          value={value.server}
          onChange={set("server")}
          autoComplete="off"
        />
        <label htmlFor="db-port">Puerto</label>
        <input
          id="db-port"
          inputMode="numeric"
          value={value.port}
          onChange={set("port")}
        />
        <label htmlFor="db-database">Base de datos</label>
        <input
          id="db-database"
          value={value.database}
          onChange={set("database")}
          autoComplete="off"
        />
        <label htmlFor="db-schema">Esquema</label>
        <input
          id="db-schema"
          placeholder={
            value.engine === "sqlserver" ? "dbo (opcional: todos)" : "public"
          }
          value={value.schema}
          onChange={set("schema")}
          autoComplete="off"
        />
        <label htmlFor="db-user">Usuario</label>
        <input
          id="db-user"
          value={value.user}
          onChange={set("user")}
          autoComplete="off"
        />
        <label htmlFor="db-password">Contraseña</label>
        <input
          id="db-password"
          type="password"
          value={value.password}
          onChange={set("password")}
          autoComplete="off"
        />
      </div>
      {isPublic && (
        <details className="database-advanced">
          <summary>Opciones avanzadas</summary>
          <label htmlFor="db-certificate">
            Certificado del servidor (opcional)
          </label>
          <textarea
            id="db-certificate"
            rows={4}
            spellCheck={false}
            placeholder="-----BEGIN CERTIFICATE-----"
            value={value.certificate}
            onChange={set("certificate")}
          />
          <p className="database-hint">
            Sólo si tu proveedor firma con su propia autoridad (por ejemplo,
            Amazon RDS o Azure). Se usa en esta conexión y no se guarda.
          </p>
        </details>
      )}
      <p className="security-note">
        <LockKeyhole size={14} />
        {isPublic
          ? "Conexión cifrada y verificada, de un solo uso y de sólo lectura; la contraseña no se guarda."
          : "Conexión de un solo uso y de sólo lectura; la contraseña no se guarda. Sólo servidores permitidos por el administrador."}
      </p>
    </fieldset>
  );
}
