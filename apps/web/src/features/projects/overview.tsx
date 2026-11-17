"use client";
import Link from "next/link";
import { useState } from "react";
import {
  ArrowRight,
  Database,
  FileSpreadsheet,
  Plus,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useApp } from "@/lib/providers";
import { ProjectTable } from "./home";
import { useAuth } from "@/features/identity/auth-provider";
import { errorMessage } from "@/lib/api";

export const overviewPaths = ["/projects", "/sources", "/settings"];

export function Overview({ path }: { path: string }) {
  const { projects, dark, toggleTheme } = useApp();
  const { session, logout } = useAuth();
  const [logoutError, setLogoutError] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);
  const titles: Record<string, [string, string]> = {
    "/projects": [
      "Tus proyectos",
      "Un espacio para cada pregunta que quieres responder.",
    ],
    "/sources": ["Fuentes de datos", "El punto de partida de cada hallazgo."],
    "/settings": ["Configuración", "Personaliza tu espacio de trabajo."],
  };
  const [title, subtitle] = titles[path];
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">TU ESPACIO DE TRABAJO</p>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        {["/projects", "/sources"].includes(path) && (
          <Button asChild>
            <Link href="/new">
              <Plus size={17} />
              Nuevo análisis
            </Link>
          </Button>
        )}
      </div>
      {path === "/projects" && <ProjectTable />}
      {path === "/sources" && (
        <div className="source-grid">
          <section className="panel source-card">
            <span className="metric-icon cyan">
              <FileSpreadsheet size={23} />
            </span>
            <h2>Archivos por proyecto</h2>
            <p>
              Abre un proyecto para consultar sus originales, versiones y
              resultados automáticos. Se admiten CSV y Excel (.xlsx).
            </p>
            {projects.map((p) => (
              <Link
                className="source-file"
                key={p.id}
                href={`/workspace/${p.id}`}
              >
                <FileSpreadsheet size={18} />
                <span>
                  <strong>{p.name}</strong>
                  <small>Abrir versiones y archivos originales</small>
                </span>
                <ArrowRight size={16} />
              </Link>
            ))}
          </section>
          <section className="panel source-card">
            <span className="metric-icon indigo">
              <Database size={23} />
            </span>
            <h2>Conexiones externas</h2>
            <p>Se habilitarán tras estabilizar el flujo con archivos.</p>
            {["SQL Server", "PDF con tablas"].map((name) => (
              <div className="connection" key={name}>
                <Database size={19} />
                <strong>{name}</strong>
                <span className="badge neutral">Próximamente</span>
              </div>
            ))}
            <div className="info-banner">
              <ShieldCheck size={17} />
              <span>
                Las conexiones usarán permisos mínimos de lectura y credenciales
                gestionadas en el backend.
              </span>
            </div>
          </section>
        </div>
      )}
      {path === "/settings" && (
        <div className="settings-grid">
          <section className="panel settings-panel">
            <h2>Preferencias</h2>
            <div className="setting-row">
              <div>
                <strong>Apariencia</strong>
                <p>
                  Actualmente estás usando el modo {dark ? "oscuro" : "claro"}.
                </p>
              </div>
              <Button variant="outline" size="sm" onClick={toggleTheme}>
                Cambiar tema
              </Button>
            </div>
            <div className="setting-row">
              <div>
                <strong>Idioma</strong>
                <p>Español · formatos regionales es-ES</p>
              </div>
              <span className="badge neutral">Español</span>
            </div>
            <div className="setting-row">
              <div>
                <strong>Perfil</strong>
                <p>
                  {session?.user.name} · {session?.user.email}
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                disabled={loggingOut}
                onClick={async () => {
                  setLoggingOut(true);
                  setLogoutError("");
                  try {
                    await logout();
                  } catch (error) {
                    setLogoutError(errorMessage(error));
                  } finally {
                    setLoggingOut(false);
                  }
                }}
              >
                Cerrar sesión
              </Button>
            </div>
            {logoutError && (
              <p className="auth-error" role="alert">
                {logoutError}
              </p>
            )}
          </section>
          <section className="panel settings-panel">
            <h2>Acerca de DataFlow AI</h2>
            <p className="muted">
              PostgreSQL conserva tus proyectos y archivos. El navegador sólo
              guarda el tema.
            </p>
            <div className="info-banner">
              <Sparkles size={18} />
              <span>
                Análisis automático: al subir un archivo el sistema lo perfila,
                evalúa su calidad, lo interpreta y publica el dashboard sin
                pasos manuales. La explicación con IA sólo aparece si el
                servidor la tiene activada.
              </span>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
