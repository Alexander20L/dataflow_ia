"use client";
import { useState } from "react";
import Link from "next/link";
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  Clock3,
  Database,
  Ellipsis,
  FileSpreadsheet,
  FolderKanban,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
  Workflow,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Chart, seriesOption } from "@/components/ui/chart";
import { useApp } from "@/lib/providers";
import {
  cleanSales,
  monthlyTotals,
  originalSales,
  statusLabels,
  summarize,
} from "@/lib/demo";
import { currency, number } from "@/lib/utils";
import { projectView, useProjects } from "./api";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/features/identity/auth-provider";
import { useIngestionSummary } from "@/features/ingestion/api";

export function ProjectTable({ limit }: { limit?: number }) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(0);
  const pageSize = limit ?? 10;
  const query = useProjects(
    search,
    filter === "all" ? undefined : (filter as "draft" | "archived"),
    pageSize,
    page * pageSize,
  );
  const filtered = query.data?.items.map(projectView) ?? [];
  const total = query.data?.total ?? 0;
  return (
    <section className="panel project-panel">
      <div className="panel-heading">
        <div>
          <h2>{limit ? "Proyectos recientes" : "Todos los proyectos"}</h2>
          <p>Continúa donde lo dejaste.</p>
        </div>
        {limit && (
          <Link className="text-link" href="/projects">
            Ver todos <ArrowUpRight size={15} />
          </Link>
        )}
      </div>
      <div className="table-toolbar">
        <div className="input-icon search-input">
          <Search size={16} />
          <input
            aria-label="Buscar en proyectos"
            placeholder="Buscar un proyecto…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
          />
        </div>
        <select
          aria-label="Filtrar estado"
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value);
            setPage(0);
          }}
        >
          <option value="all">Todos los estados</option>
          <option value="draft">Borrador</option>
          <option value="archived">Archivado</option>
        </select>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Nombre del proyecto</th>
              <th>Archivo de referencia</th>
              <th>Estado</th>
              <th>Registros</th>
              <th aria-label="Acciones" />
            </tr>
          </thead>
          <tbody>
            {filtered.map((p, index) => (
              <tr key={p.id}>
                <td>
                  <Link href={`/workspace/${p.id}`} className="project-name">
                    <span className={`project-icon project-color-${index % 3}`}>
                      <FolderKanban size={19} />
                    </span>
                    <span>
                      <strong>{p.name}</strong>
                      <small>{p.description || "Sin descripción"}</small>
                    </span>
                  </Link>
                </td>
                <td>
                  <span className="file-cell">
                    <FileSpreadsheet size={15} />
                    {p.file}
                  </span>
                </td>
                <td>
                  <span className={`badge ${p.status}`}>
                    <i />
                    {statusLabels[p.status]}
                  </span>
                </td>
                <td className="numeric">
                  {p.rows ? (
                    number(p.rows)
                  ) : (
                    <Link className="text-link" href={`/workspace/${p.id}`}>
                      Ver datos
                    </Link>
                  )}
                </td>
                <td>
                  <Link
                    className="icon-button"
                    href={`/workspace/${p.id}`}
                    aria-label={`Abrir ${p.name}`}
                  >
                    <ArrowUpRight size={17} />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {query.isPending && (
          <p className="empty-copy" role="status">
            Cargando proyectos…
          </p>
        )}
        {query.isError && (
          <div className="empty-state compact">
            <p role="alert">{errorMessage(query.error)}</p>
            <Button variant="outline" onClick={() => void query.refetch()}>
              Reintentar
            </Button>
          </div>
        )}
        {!query.isPending && !query.isError && filtered.length === 0 && (
          <div className="empty-state compact">
            <Search size={25} />
            <h3>
              {search
                ? "No encontramos proyectos"
                : "Tu próximo proyecto empieza aquí"}
            </h3>
            <p>
              {search
                ? "Prueba con otro nombre o estado."
                : "Crea un proyecto para guardarlo en tu cuenta."}
            </p>
          </div>
        )}
      </div>
      <div className="table-footer">
        <span>
          {filtered.length} de {total} proyectos
        </span>
        {!limit && (
          <div className="pagination">
            <Button
              variant="ghost"
              size="sm"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
            >
              Anterior
            </Button>
            <span>Página {page + 1}</span>
            <Button
              variant="ghost"
              size="sm"
              disabled={(page + 1) * pageSize >= total}
              onClick={() => setPage((p) => p + 1)}
            >
              Siguiente
            </Button>
          </div>
        )}
        <span>Guardados en PostgreSQL</span>
      </div>
      <Link className="activity-link" href="/workspace/ventas-2026">
        Explorar ventas 2026 · dataset de demostración <ArrowRight size={14} />
      </Link>
    </section>
  );
}

export function Home() {
  const { projectTotal, cleaned } = useApp();
  const { session } = useAuth();
  const summary = useIngestionSummary();
  const totals = summarize(cleaned ? cleanSales : originalSales);
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            <span className="status-dot" /> TU CENTRO DE ANÁLISIS
          </p>
          <h1>
            Hola, {session?.user.name.split(" ")[0] ?? "Usuario"}{" "}
            <span className="wave">✦</span>
          </h1>
          <p>Convierte tus datos en tu próxima buena decisión.</p>
        </div>
        <Button asChild>
          <Link href="/new">
            <Plus size={18} />
            Nuevo análisis
          </Link>
        </Button>
      </div>
      <section className="welcome-banner">
        <div className="welcome-content">
          <span className="small-label">
            <Sparkles size={14} /> MENOS FRICCIÓN. MÁS HALLAZGOS.
          </span>
          <h2>Tus datos tienen algo que contar.</h2>
          <p>
            Un flujo de trabajo inteligente, desde el primer archivo
            <br className="desktop-break" /> hasta una decisión respaldada por
            evidencia.
          </p>
          <Button asChild variant="outline">
            <Link href="/new">
              Explorar mis datos <ArrowRight size={16} />
            </Link>
          </Button>
        </div>
        <div className="pipeline-art" aria-hidden="true">
          <div className="art-orbit orbit-one" />
          <div className="art-orbit orbit-two" />
          <div className="art-node node-a">
            <Database size={25} />
            <span>Datos</span>
          </div>
          <div className="art-connector" />
          <div className="art-node node-b">
            <Workflow size={32} />
            <span>DataFlow AI</span>
          </div>
          <div className="art-node node-c">
            <ShieldCheck size={25} />
            <span>Evidencia</span>
          </div>
          <div className="art-spark spark-a">✦</div>
          <div className="art-spark spark-b">+</div>
          <span className="art-caption">
            <span className="status-dot" /> Claridad en cada etapa
          </span>
        </div>
      </section>
      <div className="metric-grid">
        {[
          {
            label: "Total de proyectos",
            value: projectTotal,
            icon: FolderKanban,
            detail: "Tu espacio de trabajo",
            className: "indigo",
          },
          {
            label: "Datasets propios",
            value: summary.data?.datasets,
            icon: Database,
            detail: "Originales conservados",
            className: "cyan",
          },
          {
            label: "Versiones procesadas",
            value: summary.data?.processed,
            icon: CheckCircle2,
            detail: "Perfil y calidad calculados",
            className: "green",
          },
          {
            label: "Ejecuciones pendientes",
            value: summary.data?.pending,
            icon: Clock3,
            detail: "Cola persistida en PostgreSQL",
            className: "amber",
          },
        ].map((m) => (
          <section className="metric-card" key={m.label}>
            <div className="metric-top">
              <span>{m.label}</span>
              <span className={`metric-icon ${m.className}`}>
                <m.icon size={18} />
              </span>
            </div>
            <strong className="metric-value">
              {m.value === undefined ? "—" : number(m.value)}
            </strong>
            <small>{m.detail}</small>
          </section>
        ))}
      </div>
      {summary.isError && (
        <div className="info-banner">
          <span>No se pudo cargar el resumen de datasets.</span>
          <button className="text-link" onClick={() => void summary.refetch()}>
            Reintentar
          </button>
        </div>
      )}
      <div className="home-grid">
        <div className="home-main">
          <ProjectTable limit={4} />
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Explora el ejemplo de ventas</h2>
                <p>Ingresos de ventas · enero a junio de 2026</p>
              </div>
              <span className="badge calculated">Calculado · demo</span>
            </div>
            <div className="chart-summary">
              <strong>{currency(totals.total)}</strong>
              <span>Importes válidos · los nulos no se imputan</span>
            </div>
            <Chart
              option={seriesOption(
                ["Ene", "Feb", "Mar", "Abr", "May", "Jun"],
                monthlyTotals(originalSales),
              )}
              label="Ingresos por mes del dataset sintético de ventas"
            />
          </section>
        </div>
        <aside className="home-side">
          <section className="panel quick-import">
            <span className="upload-icon">
              <Upload size={23} />
            </span>
            <h2>Todo empieza con tus datos</h2>
            <p>Importa un archivo y descubre qué puedes hacer con él.</p>
            <div className="format-tags">
              <span>CSV</span>
              <span>XLSX</span>
              <span>PARQUET</span>
            </div>
            <Button asChild variant="outline">
              <Link href="/new">
                <Plus size={16} />
                Importar datos
              </Link>
            </Button>
            <small>
              <ShieldCheck size={12} /> Tus originales se conservan
            </small>
          </section>
          <section className="panel activity-panel">
            <div className="panel-heading">
              <h2>Actividad del ejemplo</h2>
              <Link
                className="icon-button"
                href="/history"
                aria-label="Ver historial"
              >
                <Ellipsis size={19} />
              </Link>
            </div>
            <div className="timeline">
              {cleaned && (
                <div className="timeline-item">
                  <span className="timeline-icon green">
                    <Check size={14} />
                  </span>
                  <div>
                    <strong>Limpieza aprobada</strong>
                    <p>Ventas · versión v2</p>
                    <small>En esta demostración</small>
                  </div>
                </div>
              )}
              <div className="timeline-item">
                <span className="timeline-icon amber">
                  <ShieldCheck size={14} />
                </span>
                <div>
                  <strong>Diagnóstico disponible</strong>
                  <p>8 importes faltantes detectados</p>
                  <small>Dataset sintético</small>
                </div>
              </div>
              <div className="timeline-item">
                <span className="timeline-icon indigo">
                  <ArrowDownToLine size={14} />
                </span>
                <div>
                  <strong>Proyecto de ejemplo listo</strong>
                  <p>240 registros · 6 columnas</p>
                  <small>Fixture incluido</small>
                </div>
              </div>
            </div>
            <Link className="activity-link" href="/workspace/ventas-2026">
              Explorar el ejemplo <ArrowRight size={14} />
            </Link>
          </section>
        </aside>
      </div>
      <div className="trust-strip">
        <ShieldCheck size={16} />
        <span>Originales intactos</span>
        <i />
        <span>Limpieza supervisada</span>
        <i />
        <span>Resultados con evidencia</span>
      </div>
    </>
  );
}
