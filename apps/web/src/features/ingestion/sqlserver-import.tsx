"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Database, LockKeyhole } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCreateProject } from "@/features/projects/api";
import { errorMessage } from "@/lib/api";
import { useApp } from "@/lib/providers";
import { useImportSqlServer } from "./api";

/** Fase 18B: copia de un solo uso de las tablas de una base de SQL Server. El sistema elige
 * las tablas; la contraseña se envía una vez y no se guarda. */
export function SqlServerImport({
  projectName,
}: {
  projectName: () => string;
}) {
  const { notify } = useApp();
  const router = useRouter();
  const createProject = useCreateProject();
  const importSql = useImportSqlServer();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [fields, setFields] = useState({
    server: "",
    port: "1433",
    database: "",
    user: "",
    password: "",
  });
  const set =
    (name: keyof typeof fields) => (e: React.ChangeEvent<HTMLInputElement>) =>
      setFields((current) => ({ ...current, [name]: e.target.value }));
  const busy = createProject.isPending || importSql.isPending;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const port = Number(fields.port);
    if (
      !fields.server.trim() ||
      !fields.database.trim() ||
      !fields.user.trim() ||
      !fields.password ||
      !Number.isInteger(port)
    ) {
      setError("Completa servidor, puerto, base, usuario y contraseña.");
      return;
    }
    try {
      const name = projectName().trim();
      const project =
        createProject.data ??
        (await createProject.mutateAsync({
          name: name.length >= 3 ? name : `Base ${fields.database.trim()}`,
          description: "",
          file_name: null,
        }));
      await importSql.mutateAsync({
        projectId: project.id,
        connection: {
          server: fields.server.trim(),
          port,
          database: fields.database.trim(),
          user: fields.user.trim(),
          password: fields.password,
        },
      });
      setFields((current) => ({ ...current, password: "" }));
      notify("Tablas copiadas. Análisis encolado.");
      router.push(`/workspace/${project.id}`);
    } catch (problem) {
      setFields((current) => ({ ...current, password: "" }));
      setError(errorMessage(problem));
    }
  }

  return (
    <section
      className="panel connections-panel"
      aria-label="Conectar SQL Server"
    >
      <h3>¿Tus datos están en SQL Server?</h3>
      <p>
        Se copian las tablas principales con una cuenta de sólo lectura y se
        analizan como si fueran archivos. La contraseña no se guarda.
      </p>
      {!open ? (
        <div className="connection">
          <Database size={18} />
          <strong>SQL Server</strong>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setOpen(true)}
          >
            Conectar
          </Button>
        </div>
      ) : (
        <form className="sqlserver-form" onSubmit={submit}>
          <label htmlFor="sql-server">Servidor</label>
          <input
            id="sql-server"
            placeholder="sql.empresa.com"
            value={fields.server}
            onChange={set("server")}
            autoComplete="off"
          />
          <label htmlFor="sql-port">Puerto</label>
          <input
            id="sql-port"
            inputMode="numeric"
            value={fields.port}
            onChange={set("port")}
          />
          <label htmlFor="sql-database">Base de datos</label>
          <input
            id="sql-database"
            value={fields.database}
            onChange={set("database")}
            autoComplete="off"
          />
          <label htmlFor="sql-user">Usuario</label>
          <input
            id="sql-user"
            value={fields.user}
            onChange={set("user")}
            autoComplete="off"
          />
          <label htmlFor="sql-password">Contraseña</label>
          <input
            id="sql-password"
            type="password"
            value={fields.password}
            onChange={set("password")}
            autoComplete="off"
          />
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <p className="security-note">
            <LockKeyhole size={14} />
            Conexión cifrada y de un solo uso; sólo servidores permitidos por el
            administrador.
          </p>
          <Button type="submit" disabled={busy}>
            {busy ? "Copiando tablas…" : "Copiar tablas y analizar"}
          </Button>
        </form>
      )}
    </section>
  );
}
