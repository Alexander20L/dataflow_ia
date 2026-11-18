"use client";

import { LockKeyhole } from "lucide-react";
import type { DatabaseEngine } from "./api";

export type DatabaseForm = {
  engine: DatabaseEngine;
  server: string;
  port: string;
  database: string;
  schema: string;
  user: string;
  password: string;
};

export const EMPTY_DATABASE: DatabaseForm = {
  engine: "sqlserver",
  server: "",
  port: "1433",
  database: "",
  schema: "",
  user: "",
  password: "",
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
  return null;
}

/** Fases 18B y 31: datos de conexión de un solo uso a SQL Server o PostgreSQL. Campos
 * controlados (van dentro del formulario de la pantalla de carga). La contraseña se envía una
 * vez y no se guarda. */
export function DatabaseFields({
  value,
  onChange,
}: {
  value: DatabaseForm;
  onChange: (next: DatabaseForm) => void;
}) {
  const set =
    (name: keyof DatabaseForm) => (e: React.ChangeEvent<HTMLInputElement>) =>
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
      <p className="security-note">
        <LockKeyhole size={14} />
        Conexión de un solo uso y de sólo lectura; la contraseña no se guarda.
        Sólo servidores permitidos por el administrador.
      </p>
    </fieldset>
  );
}
