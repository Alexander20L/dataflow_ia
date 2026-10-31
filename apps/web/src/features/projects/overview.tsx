"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  CheckCircle2,
  Database,
  FileSpreadsheet,
  GitCompareArrows,
  History,
  Plus,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { useApp } from "@/lib/providers";
import { cleanSales, originalSales } from "@/lib/demo";
import { ProjectTable } from "./home";
import { DashboardEditor } from "@/features/workspace/stages";
import { Report } from "@/features/reports/report";
import { useAuth } from "@/features/identity/auth-provider";
import { errorMessage } from "@/lib/api";

export function Overview({ path }: { path: string }) {
  const { projects, cleaned, dark, toggleTheme, notify, resetDemo } = useApp();
  const { session, logout } = useAuth();
  const [logoutError, setLogoutError] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);
  const router = useRouter();
  const [reset, setReset] = useState(false);
  const [compare, setCompare] = useState(false);
  const titles: Record<string, [string, string]> = {
    "/projects": [
      "Tus proyectos",
      "Un espacio para cada pregunta que quieres responder.",
    ],
    "/sources": ["Fuentes de datos", "El punto de partida de cada hallazgo."],
    "/analysis": ["Tus análisis", "Retoma tu recorrido, una etapa a la vez."],
    "/dashboards": ["Dashboards", "Dale forma a la información que importa."],
    "/reports": ["Informes", "Resultados, contexto y próximos pasos."],
    "/history": [
      "Historial y trazabilidad",
      "Cada versión y cada decisión tienen su lugar.",
    ],
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
        {["/projects", "/sources", "/analysis"].includes(path) && (
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
            <h2>Datasets por proyecto</h2>
            <p>
              Abre un proyecto para consultar sus originales, versiones y
              diagnósticos CSV.
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
                  <small>
                    {p.id === "ventas-2026"
                      ? "Dataset sintético disponible"
                      : "Abrir versiones y archivos originales"}
                  </small>
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
            {["PostgreSQL", "MySQL"].map((name) => (
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
      {path === "/analysis" && (
        <>
          <div className="info-banner">
            <ShieldCheck size={18} />
            <span>
              El análisis disponible pertenece al dataset de ventas sintético.
              Los demás proyectos están en preparación.
            </span>
          </div>
          <ProjectTable />
        </>
      )}
      {path === "/dashboards" && (
        <section className="panel standalone-panel">
          <div className="section-heading">
            <div>
              <h2>Rendimiento de ventas</h2>
              <p className="muted">
                Ejemplo · {cleaned ? "v2" : "v1"} · enero a junio 2026
              </p>
            </div>
            <span className="badge calculated">Calculado · demo</span>
          </div>
          <DashboardEditor sales={cleaned ? cleanSales : originalSales} />
        </section>
      )}
      {path === "/reports" && (
        <section className="panel standalone-panel">
          <Report
            sales={cleaned ? cleanSales : originalSales}
            version={cleaned ? "v2" : "v1"}
          />
        </section>
      )}
      {path === "/history" && (
        <>
          <div className="info-banner">
            <History size={18} />
            <span>
              Esta vista corresponde al ejemplo de ventas. Las versiones y
              estados de tus cargas reales se consultan en cada proyecto; sus
              eventos quedan registrados en la auditoría del backend.
            </span>
          </div>
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Ejecuciones del ejemplo</h2>
                <p>Dataset ventas_2026 · reglas explícitas</p>
              </div>
              <Button
                size="sm"
                variant="outline"
                disabled={!cleaned}
                onClick={() => setCompare(true)}
              >
                <GitCompareArrows size={16} />
                Comparar versiones
              </Button>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Ejecución</th>
                    <th>Versión</th>
                    <th>Regla / operación</th>
                    <th>Aprobación</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {cleaned && (
                    <tr>
                      <td>
                        <strong>Limpieza demostrativa</strong>
                        <small className="cell-subtitle">
                          Guardada en este navegador
                        </small>
                      </td>
                      <td>v1 → v2</td>
                      <td>Excluir importe nulo</td>
                      <td>Confirmación local</td>
                      <td>
                        <span className="badge completed">
                          <CheckCircle2 size={12} />
                          Completada
                        </span>
                      </td>
                    </tr>
                  )}
                  <tr>
                    <td>
                      <strong>Perfilado de ejemplo</strong>
                      <small className="cell-subtitle">
                        Fixture incluido · sin fecha real
                      </small>
                    </td>
                    <td>v1</td>
                    <td>Q-001 · importe no nulo</td>
                    <td>No aplica</td>
                    <td>
                      <span className="badge completed">
                        Calculado localmente
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
          {compare && (
            <Dialog
              title="Comparar versiones del dataset"
              onClose={() => setCompare(false)}
            >
              <div className="before-after">
                <div>
                  <small>v1 · ORIGINAL</small>
                  <strong>240 filas</strong>
                  <p>8 importes nulos</p>
                </div>
                <ArrowRight size={21} />
                <div>
                  <small>v2 · DERIVADA</small>
                  <strong>232 filas</strong>
                  <p>0 importes nulos</p>
                </div>
              </div>
              <p className="dialog-copy">
                Operación: excluir filas con importe nulo. Sin cambios en las
                otras 232 filas. Los totales de importes válidos permanecen
                iguales; el conteo de filas cambia.
              </p>
            </Dialog>
          )}
        </>
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
            <h2>Datos de demostración</h2>
            <p className="muted">
              PostgreSQL conserva tus proyectos. El navegador sólo guarda el
              tema y la limpieza del ejemplo. No almacena el contenido de tus
              archivos.
            </p>
            <div className="info-banner">
              <ShieldCheck size={18} />
              <span>
                Identidad, proyectos, ingesta CSV, perfilado y calidad
                conectados a la API. El copiloto y las etapas posteriores siguen
                en demostración.
              </span>
            </div>
            <Button variant="outline" onClick={() => setReset(true)}>
              <RotateCcw size={16} />
              Restablecer demostración
            </Button>
            <Button
              variant="ghost"
              onClick={() =>
                notify(
                  "Versión 0.5 · revisión semántica e historial persistidos. Consulta README.md para el alcance y los próximos incrementos.",
                )
              }
            >
              Acerca de esta versión
            </Button>
          </section>
        </div>
      )}
      {reset && (
        <Dialog
          title="¿Restablecer la demostración?"
          onClose={() => setReset(false)}
        >
          <p className="dialog-copy">
            Se restablecerán el tema y la limpieza del ejemplo. Tus proyectos
            guardados en PostgreSQL no se eliminarán. No se modifica ningún
            archivo de tu equipo.
          </p>
          <div className="form-footer">
            <Button variant="ghost" onClick={() => setReset(false)}>
              Cancelar
            </Button>
            <Button
              onClick={() => {
                resetDemo();
                setReset(false);
                notify("Demostración restablecida.");
                router.push("/");
              }}
            >
              Restablecer
            </Button>
          </div>
        </Dialog>
      )}
    </>
  );
}
