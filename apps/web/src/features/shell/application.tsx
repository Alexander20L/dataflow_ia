"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  ArrowUpRight,
  Bell,
  ChevronDown,
  ChevronRight,
  Command,
  Database,
  FileText,
  FolderKanban,
  HelpCircle,
  History,
  House,
  LayoutDashboard,
  Menu,
  Moon,
  Plus,
  Search,
  Settings,
  Sparkles,
  Sun,
  Workflow,
} from "lucide-react";
import { useApp } from "@/lib/providers";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Home } from "@/features/projects/home";
import { ImportProject } from "@/features/ingestion/import-project";
import { Workspace } from "@/features/workspace/workspace";
import { Overview } from "@/features/projects/overview";
import { useAuth } from "@/features/identity/auth-provider";

const navigation = [
  { href: "/", label: "Inicio", icon: House },
  { href: "/projects", label: "Proyectos", icon: FolderKanban },
  { href: "/sources", label: "Fuentes de datos", icon: Database },
  { href: "/analysis", label: "Análisis", icon: Activity },
  { href: "/dashboards", label: "Dashboards", icon: LayoutDashboard },
  { href: "/reports", label: "Informes", icon: FileText },
  { href: "/history", label: "Historial de ejecuciones", icon: History },
];
export function Application() {
  const path = usePathname();
  const router = useRouter();
  const { projects, projectTotal, dark, toggleTheme, ready } = useApp();
  const { session } = useAuth();
  const name = session?.user.name ?? "Usuario";
  const initials = name
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  const [mobile, setMobile] = useState(false);
  const [modal, setModal] = useState<
    "search" | "notifications" | "help" | null
  >(null);
  const [search, setSearch] = useState("");
  const active = navigation.find((n) => n.href === path);
  const title =
    path === "/new"
      ? "Nuevo análisis"
      : path.startsWith("/workspace")
        ? "Workspace de análisis"
        : path === "/settings"
          ? "Configuración"
          : (active?.label ?? "Página no encontrada");
  return (
    <div className="app-layout">
      <a className="skip-link" href="#main-content">
        Saltar al contenido
      </a>
      {mobile && (
        <button
          className="mobile-overlay"
          onClick={() => setMobile(false)}
          aria-label="Cerrar navegación"
        />
      )}
      <aside className={`sidebar ${mobile ? "sidebar-open" : ""}`}>
        <Link href="/" className="brand" onClick={() => setMobile(false)}>
          <span className="brand-icon">
            <Workflow size={23} />
          </span>
          <span>
            DataFlow<span className="brand-ai">AI</span>
          </span>
        </Link>
        <div className="workspace-switch">
          <span className="workspace-avatar">D</span>
          <div>
            <strong>Mi espacio de trabajo</strong>
            <small>Cuenta personal</small>
          </div>
          <ChevronDown size={15} />
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Navegación principal">
          {navigation.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setMobile(false)}
              className={`nav-link ${path === item.href || (item.href === "/analysis" && path.startsWith("/workspace")) ? "active" : ""}`}
            >
              <item.icon size={18} />
              <span>{item.label}</span>
              {item.href === "/projects" && (
                <span className="nav-count">{projectTotal}</span>
              )}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="copilot-card">
            <div className="copilot-title">
              <Sparkles size={17} />
              Tu copiloto de datos
            </div>
            <p>De los datos a las decisiones, con evidencia en cada paso.</p>
            <button onClick={() => setModal("help")}>
              Conoce DataFlow AI <ArrowUpRight size={14} />
            </button>
          </div>
          <Link
            href="/settings"
            className={`nav-link ${path === "/settings" ? "active" : ""}`}
          >
            <Settings size={18} />
            Configuración
          </Link>
          <button className="nav-link" onClick={toggleTheme}>
            {dark ? <Sun size={18} /> : <Moon size={18} />}
            {dark ? "Modo claro" : "Modo oscuro"}
          </button>
          <button className="profile" onClick={() => router.push("/settings")}>
            <span className="avatar">{initials}</span>
            <span>
              <strong>{name}</strong>
              <small>{session?.user.email}</small>
            </span>
            <ChevronDown size={15} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="icon-button mobile-menu"
              onClick={() => setMobile(true)}
              aria-label="Abrir navegación"
            >
              <Menu size={21} />
            </button>
            <span className="muted">Workspace</span>
            <ChevronRight size={14} />
            <strong>{title}</strong>
          </div>
          <div className="topbar-actions">
            <span className="demo-chip">
              <span /> Proyectos conectados
            </span>
            <button
              className="search-trigger"
              onClick={() => setModal("search")}
            >
              <Search size={16} />
              <span>Buscar proyectos…</span>
              <Command size={12} />
            </button>
            <button
              className="icon-button notification-button"
              aria-label="Notificaciones"
              onClick={() => setModal("notifications")}
            >
              <Bell size={19} />
              <i />
            </button>
            <button
              className="avatar small-avatar"
              aria-label="Ver perfil"
              onClick={() => router.push("/settings")}
            >
              {initials}
            </button>
          </div>
        </header>
        <main
          id="main-content"
          className={`main-content ${path.startsWith("/workspace") ? "workspace-page" : ""}`}
        >
          {!ready ? (
            <div className="loading-screen" aria-label="Cargando datos locales">
              <div className="skeleton" />
              <div className="skeleton" />
            </div>
          ) : path === "/" ? (
            <Home />
          ) : path === "/new" ? (
            <ImportProject />
          ) : path.startsWith("/workspace/") ? (
            <Workspace projectId={path.split("/")[2]} />
          ) : [
              "/projects",
              "/sources",
              "/analysis",
              "/dashboards",
              "/reports",
              "/history",
              "/settings",
            ].includes(path) ? (
            <Overview path={path} />
          ) : (
            <div className="empty-state">
              <HelpCircle size={36} />
              <h1>Página no encontrada</h1>
              <p>Vuelve al inicio para continuar con tus proyectos.</p>
              <Button asChild>
                <Link href="/">Ir al inicio</Link>
              </Button>
            </div>
          )}
        </main>
        <footer className="footer">
          <span>
            DataFlow AI <span className="footer-dot">·</span> Cada hallazgo,
            respaldado por datos.
          </span>
          <span>
            <span className="status-dot" /> DataFlow v0.5 · contexto semántico
          </span>
        </footer>
      </div>
      {modal && (
        <Dialog
          title={
            modal === "search"
              ? "Buscar proyectos"
              : modal === "notifications"
                ? "Notificaciones"
                : "Un flujo claro. Decisiones informadas."
          }
          onClose={() => setModal(null)}
        >
          {modal === "search" ? (
            <>
              <div className="input-icon">
                <Search size={17} />
                <input
                  autoFocus
                  placeholder="Nombre del proyecto…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <div className="search-results">
                {projects
                  .filter((p) =>
                    p.name.toLowerCase().includes(search.toLowerCase()),
                  )
                  .map((p) => (
                    <Link
                      onClick={() => setModal(null)}
                      key={p.id}
                      href={`/workspace/${p.id}`}
                    >
                      <FolderKanban size={18} />
                      <span>
                        {p.name}
                        <small>{p.file}</small>
                      </span>
                      <ChevronRight size={15} />
                    </Link>
                  ))}
                {!projects.some((p) =>
                  p.name.toLowerCase().includes(search.toLowerCase()),
                ) && (
                  <p className="empty-copy">No hay proyectos que coincidan.</p>
                )}
              </div>
            </>
          ) : modal === "notifications" ? (
            <div className="notice-list">
              <Sparkles size={22} />
              <div>
                <strong>Tu espacio de demostración está listo</strong>
                <p>
                  Explora el proyecto de ventas para revisar calidad, aprobar
                  una limpieza y obtener un informe.
                </p>
                <Button
                  size="sm"
                  onClick={() => {
                    setModal(null);
                    router.push("/workspace/ventas-2026");
                  }}
                >
                  Abrir ejemplo
                </Button>
              </div>
            </div>
          ) : (
            <>
              <p className="dialog-copy">
                DataFlow AI acompaña las nueve etapas del análisis. Conserva los
                originales y separa los resultados calculados de las sugerencias
                de IA.
              </p>
              <div className="info-banner">
                <Sparkles size={18} />
                <span>
                  Tus CSV se conservan y procesan en el backend. El ejemplo de
                  ventas y el copiloto son demostraciones; no se realizan
                  llamadas a un proveedor de IA.
                </span>
              </div>
              <Button
                className="mt-5"
                onClick={() => {
                  setModal(null);
                  router.push("/new");
                }}
              >
                <Plus size={16} />
                Comenzar un análisis
              </Button>
            </>
          )}
        </Dialog>
      )}
    </div>
  );
}
