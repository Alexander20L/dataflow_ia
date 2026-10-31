"use client";
import { useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Filter,
  GitBranch,
  Plus,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Chart, seriesOption } from "@/components/ui/chart";
import { Dialog } from "@/components/ui/dialog";
import { useApp } from "@/lib/providers";
import { missingCount, monthlyTotals, summarize, type Sale } from "@/lib/demo";
import { currency, number } from "@/lib/utils";

export function DataTable({ sales }: { sales: Sale[] }) {
  const [page, setPage] = useState(0);
  const totalPages = Math.max(1, Math.ceil(sales.length / 8));
  const safePage = Math.min(page, totalPages - 1);
  return (
    <div className="data-table">
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Fecha</th>
              <th>Región</th>
              <th>Categoría</th>
              <th>Importe (€)</th>
              <th>Unidades</th>
            </tr>
          </thead>
          <tbody>
            {sales.slice(safePage * 8, safePage * 8 + 8).map((s) => (
              <tr key={s.id}>
                <td className="mono">{s.id}</td>
                <td>{s.date}</td>
                <td>{s.region}</td>
                <td>{s.category}</td>
                <td className="numeric">
                  {s.revenue === null ? (
                    <span className="null-value">nulo</span>
                  ) : (
                    number(s.revenue)
                  )}
                </td>
                <td className="numeric">{s.units}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {sales.length === 0 && (
          <p className="empty-copy">No hay registros con estos filtros.</p>
        )}
      </div>
      <div className="table-footer">
        <span>
          {sales.length ? safePage * 8 + 1 : 0}–
          {Math.min((safePage + 1) * 8, sales.length)} de {number(sales.length)}{" "}
          registros
        </span>
        <div className="pagination">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Página anterior"
            disabled={safePage === 0}
            onClick={() => setPage(safePage - 1)}
          >
            <ChevronLeft size={16} />
          </Button>
          <span>
            {safePage + 1} / {totalPages}
          </span>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Página siguiente"
            disabled={safePage + 1 >= totalPages}
            onClick={() => setPage(safePage + 1)}
          >
            <ChevronRight size={16} />
          </Button>
        </div>
      </div>
    </div>
  );
}

export function Understanding({ sales }: { sales: Sale[] }) {
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<string | null>(null);
  const [semantic, setSemantic] = useState("Categoría");
  const nulls = sales.filter((s) => s.revenue === null).length;
  const cols = [
    {
      name: "id",
      type: "string",
      semantic: "Identificador",
      unique: sales.length,
      example: "V-0001",
      nulls: 0,
    },
    {
      name: "fecha",
      type: "date",
      semantic: "Fecha",
      unique: new Set(sales.map((s) => s.date)).size,
      example: "2026-01-01",
      nulls: 0,
    },
    {
      name: "region",
      type: "string",
      semantic: "Categoría",
      unique: 4,
      example: "Norte",
      nulls: 0,
    },
    {
      name: "categoria",
      type: "string",
      semantic: "Categoría",
      unique: 3,
      example: "Tecnología",
      nulls: 0,
    },
    {
      name: "importe",
      type: "float",
      semantic: "Importe",
      unique: new Set(
        sales.flatMap((s) => (s.revenue === null ? [] : [s.revenue])),
      ).size,
      example: "277",
      nulls,
    },
    {
      name: "unidades",
      type: "integer",
      semantic: "Medida",
      unique: new Set(sales.map((s) => s.units)).size,
      example: "2",
      nulls: 0,
    },
  ];
  return (
    <>
      <div className="info-banner">
        <Sparkles size={18} />
        <span>
          Las etiquetas semánticas son propuestas de demostración. Revísalas
          antes de utilizarlas en un plan.
        </span>
      </div>
      <div className="table-scroll bordered">
        <table>
          <thead>
            <tr>
              <th>Columna / tipo</th>
              <th>Semántica propuesta</th>
              <th>Nulos</th>
              <th>Únicos</th>
              <th>Ejemplo</th>
              <th>Revisión</th>
            </tr>
          </thead>
          <tbody>
            {cols.map((c) => (
              <tr key={c.name}>
                <td>
                  <strong>{c.name}</strong>
                  <small className="cell-subtitle mono">{c.type}</small>
                </td>
                <td>
                  <span className="badge ai">
                    {decisions[c.name]?.startsWith("Corregido:")
                      ? decisions[c.name].slice(10)
                      : c.semantic}
                  </span>
                </td>
                <td>{((c.nulls / sales.length) * 100).toFixed(2)} %</td>
                <td>{c.unique}</td>
                <td className="mono">{c.example}</td>
                <td>
                  {decisions[c.name] ? (
                    <button
                      className="text-link"
                      onClick={() =>
                        setDecisions((d) => {
                          const copy = { ...d };
                          delete copy[c.name];
                          return copy;
                        })
                      }
                    >
                      {decisions[c.name]} · deshacer
                    </button>
                  ) : (
                    <div className="row-actions">
                      <button
                        title="Aceptar sugerencia"
                        aria-label={`Aceptar ${c.name}`}
                        onClick={() =>
                          setDecisions((d) => ({ ...d, [c.name]: "Aceptado" }))
                        }
                      >
                        <Check size={16} />
                      </button>
                      <button
                        className="text-link"
                        onClick={() => {
                          setEditing(c.name);
                          setSemantic(c.semantic);
                        }}
                      >
                        Corregir
                      </button>
                      <button
                        title="Rechazar sugerencia"
                        aria-label={`Rechazar ${c.name}`}
                        onClick={() =>
                          setDecisions((d) => ({ ...d, [c.name]: "Rechazado" }))
                        }
                      >
                        <X size={16} />
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted fine-print">
        Las decisiones de esta pantalla duran mientras permanezcas en la etapa.
        La revisión persistente llegará con la API.
      </p>
      {editing && (
        <Dialog
          title={`Corregir semántica: ${editing}`}
          onClose={() => setEditing(null)}
        >
          <label htmlFor="semantic">Tipo semántico</label>
          <select
            id="semantic"
            value={semantic}
            onChange={(e) => setSemantic(e.target.value)}
          >
            {["Identificador", "Fecha", "Categoría", "Importe", "Medida"].map(
              (s) => (
                <option key={s}>{s}</option>
              ),
            )}
          </select>
          <Button
            className="mt-5"
            onClick={() => {
              setDecisions((d) => ({
                ...d,
                [editing]: `Corregido: ${semantic}`,
              }));
              setEditing(null);
            }}
          >
            Guardar corrección
          </Button>
        </Dialog>
      )}
    </>
  );
}

export function Quality({
  sales,
  onClean,
}: {
  sales: Sale[];
  onClean: () => void;
}) {
  const nulls = sales.filter((s) => s.revenue === null).length;
  const score = (1 - nulls / sales.length) * 100;
  const [showRows, setShowRows] = useState(false);
  return (
    <>
      <div className="quality-hero">
        <div
          className="quality-ring"
          style={{
            background: `conic-gradient(#6366f1 ${score}%, var(--border) 0)`,
          }}
        >
          <div>
            <strong>
              {score.toFixed(1)}
              <small>%</small>
            </strong>
            <span>Completitud</span>
          </div>
        </div>
        <div>
          <span className={`badge ${nulls ? "review" : "completed"}`}>
            {nulls ? "Requiere revisión" : "Regla superada"}
          </span>
          <h3>
            {nulls
              ? "Una base sólida, con algo por revisar."
              : "No hay importes faltantes en esta versión."}
          </h3>
          <p>
            Regla Q-001: importe no nulo. El indicador mide esta regla, no una
            calidad universal del dataset.
          </p>
        </div>
      </div>
      <div className="mini-metrics">
        <div>
          <small>Total de registros</small>
          <strong>{sales.length}</strong>
        </div>
        <div>
          <small>Importes faltantes</small>
          <strong className={nulls ? "text-amber" : ""}>{nulls}</strong>
        </div>
        <div>
          <small>Duplicados por ID</small>
          <strong>{sales.length - new Set(sales.map((s) => s.id)).size}</strong>
        </div>
      </div>
      <div className="section-heading">
        <h3>Incidencias detectadas</h3>
        <span className="badge neutral">1 regla evaluada</span>
      </div>
      {nulls ? (
        <div className="issue-card">
          <div className="issue-icon">
            <AlertTriangle size={21} />
          </div>
          <div>
            <strong>Importes sin valor</strong>
            <p>Q-001 · {nulls} registros · columna importe</p>
            <small>
              Gravedad: media. Antes de excluir, revisa si el valor puede
              recuperarse de la fuente.
            </small>
            <button
              className="text-link"
              onClick={() => setShowRows((v) => !v)}
            >
              {showRows ? "Ocultar registros" : "Consultar registros afectados"}
              <ChevronRight size={14} />
            </button>
          </div>
          <span className="badge review">
            {((nulls / sales.length) * 100).toFixed(2)} %
          </span>
        </div>
      ) : (
        <div className="success-banner">
          <CheckCircle2 size={21} />
          Todos los registros cumplen la regla de completitud de importe.
        </div>
      )}
      {showRows && (
        <DataTable sales={sales.filter((s) => s.revenue === null)} />
      )}
      <div className="info-banner">
        <ShieldCheck size={18} />
        <span>
          Las reglas de rangos, formatos y consistencia se incorporarán al motor
          real. No se presentan como comprobaciones ya realizadas.
        </span>
      </div>
      <Button onClick={onClean}>
        <Sparkles size={16} />
        Revisar propuesta de limpieza <ArrowRight size={16} />
      </Button>
    </>
  );
}

export function Cleaning() {
  const { cleaned, setCleaned, notify } = useApp();
  const [decision, setDecision] = useState<"pending" | "approved" | "rejected">(
    "pending",
  );
  const [confirm, setConfirm] = useState(false);
  return (
    <>
      <div className="info-banner">
        <ShieldCheck size={19} />
        <span>
          Esta propuesta actúa sobre v1. Excluir filas crea v2 y conserva el
          dataset original.
        </span>
      </div>
      <div className="proposal-card">
        <div className="section-heading">
          <div>
            <span className="badge ai">Propuesta de demostración</span>
            <h3>Excluir registros sin importe</h3>
          </div>
          <span
            className={`badge ${cleaned ? "completed" : decision === "approved" ? "completed" : "review"}`}
          >
            {cleaned
              ? "Ejecutada"
              : decision === "approved"
                ? "Aprobada"
                : decision === "rejected"
                  ? "Rechazada"
                  : "Requiere aprobación"}
          </span>
        </div>
        <p>
          Filtrar las filas en las que <code>importe IS NULL</code>. Es una
          opción de demostración, no una recomendación universal.
        </p>
        <div className="before-after">
          <div>
            <small>ANTES · v1</small>
            <strong>
              240 <span>registros</span>
            </strong>
            <p>8 importes faltantes</p>
          </div>
          <ArrowRight size={21} />
          <div>
            <small>DESPUÉS · v2</small>
            <strong>
              232 <span>registros</span>
            </strong>
            <p>0 importes faltantes</p>
          </div>
        </div>
        <div className="warning-banner">
          <AlertTriangle size={19} />
          <span>
            Se excluye el 3,33 % de las filas de la versión derivada. Esto puede
            sesgar el análisis. No se imputan importes ni se corrige la fuente.
          </span>
        </div>
        <div className="row-actions proposal-actions">
          <Button
            variant="outline"
            disabled={cleaned}
            onClick={() => setDecision("rejected")}
          >
            <X size={16} />
            Rechazar
          </Button>
          <Button
            variant="outline"
            disabled={cleaned}
            onClick={() =>
              notify(
                "La edición de operaciones se incorporará con el motor de limpieza. Esta demo incluye únicamente la exclusión de importes nulos.",
              )
            }
          >
            Editar propuesta
          </Button>
          <Button
            disabled={cleaned || decision === "approved"}
            onClick={() => setDecision("approved")}
          >
            <Check size={16} />
            Aprobar
          </Button>
        </div>
      </div>
      <div className="section-heading">
        <h3>Historial de operaciones</h3>
        <GitBranch size={17} />
      </div>
      {cleaned ? (
        <div className="success-banner">
          <CheckCircle2 size={20} />
          <span>
            <strong>Limpieza demostrativa completada · v1 → v2</strong>
            <br />
            {missingCount} filas excluidas. Original intacto. Estado guardado en
            este navegador.
          </span>
        </div>
      ) : (
        <p className="empty-copy">
          Todavía no se ha ejecutado ninguna transformación.
        </p>
      )}
      <Button
        disabled={cleaned || decision !== "approved"}
        onClick={() => setConfirm(true)}
      >
        Ejecutar limpieza aprobada <ArrowRight size={16} />
      </Button>
      {confirm && (
        <Dialog
          title="Confirmar limpieza de demostración"
          onClose={() => setConfirm(false)}
        >
          <p className="dialog-copy">
            Se creará la vista v2 con 232 registros. La versión original de 240
            registros seguirá disponible en el selector.
          </p>
          <div className="warning-banner">
            <AlertTriangle size={19} />
            <span>
              8 filas no se incluirán en v2. La aprobación sólo cubre esta
              operación sobre el ejemplo v1.
            </span>
          </div>
          <div className="form-footer">
            <Button variant="ghost" onClick={() => setConfirm(false)}>
              Cancelar
            </Button>
            <Button
              onClick={() => {
                setCleaned(true);
                setConfirm(false);
                notify(
                  "Versión v2 creada: 232 registros. El original sigue intacto.",
                );
              }}
            >
              Confirmar y crear v2
            </Button>
          </div>
        </Dialog>
      )}
    </>
  );
}

export function Exploration({ sales }: { sales: Sale[] }) {
  const stats = summarize(sales);
  const [view, setView] = useState("temporal");
  const histogram = [0, 500, 1000, 1500, 2000].map(
    (min) =>
      sales.filter(
        (s) => s.revenue !== null && s.revenue >= min && s.revenue < min + 500,
      ).length,
  );
  return (
    <>
      <div className="info-banner">
        <ShieldCheck size={18} />
        <span>
          Estadísticas calculadas sobre importes válidos del fixture. Los
          valores nulos se excluyen explícitamente.
        </span>
      </div>
      <div className="mini-metrics">
        <div>
          <small>Media de importe</small>
          <strong>{currency(stats.mean)}</strong>
        </div>
        <div>
          <small>Mediana</small>
          <strong>{currency(stats.median)}</strong>
        </div>
        <div>
          <small>Rango</small>
          <strong className="small-value">
            {currency(stats.min)} – {currency(stats.max)}
          </strong>
        </div>
      </div>
      <div className="section-heading">
        <h3>Explora la distribución</h3>
        <select
          aria-label="Tipo de exploración"
          value={view}
          onChange={(e) => setView(e.target.value)}
        >
          <option value="temporal">Ingresos por mes</option>
          <option value="histogram">Histograma de importes</option>
          <option value="category">Frecuencia por categoría</option>
        </select>
      </div>
      <div className="panel chart-panel">
        <Chart
          label={
            view === "histogram"
              ? "Frecuencia de importes por intervalo de 500 euros"
              : view === "category"
                ? "Registros por categoría"
                : "Ingresos por mes"
          }
          option={
            view === "histogram"
              ? seriesOption(
                  ["0–499", "500–999", "1k–1,5k", "1,5k–2k", "2k–2,5k"],
                  histogram,
                  "bar",
                )
              : view === "category"
                ? seriesOption(
                    ["Tecnología", "Hogar", "Oficina"],
                    ["Tecnología", "Hogar", "Oficina"].map(
                      (c) => sales.filter((s) => s.category === c).length,
                    ),
                    "bar",
                  )
                : seriesOption(
                    ["Ene", "Feb", "Mar", "Abr", "May", "Jun"],
                    monthlyTotals(sales),
                  )
          }
        />
      </div>
      <div className="section-heading">
        <h3>Hallazgos detectados</h3>
      </div>
      <div className="finding-card">
        <span className="badge calculated">Resultado calculado</span>
        <p>
          {stats.valid} importes válidos. Media de {currency(stats.mean)} y
          mediana de {currency(stats.median)}.
        </p>
        <small>
          Evidencia: dataset de ejemplo · columna importe · versión
          seleccionada.
        </small>
      </div>
      <div className="finding-card">
        <span className="badge ai">Hipótesis · no verificada</span>
        <p>
          Las diferencias entre regiones podrían relacionarse con la composición
          de categorías. Harían falta datos adicionales para explicar la causa.
        </p>
      </div>
    </>
  );
}

export function Analysis({ sales }: { sales: Sale[] }) {
  const [region, setRegion] = useState("all");
  const [definition, setDefinition] = useState(false);
  const filtered = sales.filter((s) => region === "all" || s.region === region);
  const stats = summarize(filtered);
  return (
    <>
      <div className="filter-bar">
        <span>
          <Filter size={16} />
          Segmentación
        </span>
        <select
          aria-label="Filtrar región"
          value={region}
          onChange={(e) => setRegion(e.target.value)}
        >
          <option value="all">Todas las regiones</option>
          {["Norte", "Sur", "Este", "Oeste"].map((r) => (
            <option key={r}>{r}</option>
          ))}
        </select>
        <span className="badge neutral">Ene – Jun 2026</span>
      </div>
      <div className="mini-metrics">
        <div>
          <small>Ingresos válidos</small>
          <strong>{currency(stats.total)}</strong>
        </div>
        <div>
          <small>Importe medio</small>
          <strong>{currency(stats.mean)}</strong>
        </div>
        <div>
          <small>Operaciones con importe</small>
          <strong>{stats.valid}</strong>
        </div>
      </div>
      <div className="section-heading">
        <h3>Evolución de ingresos</h3>
        <button className="text-link" onClick={() => setDefinition(true)}>
          Ver definición del KPI <ArrowRight size={14} />
        </button>
      </div>
      <Chart
        option={seriesOption(
          ["Ene", "Feb", "Mar", "Abr", "May", "Jun"],
          monthlyTotals(filtered),
        )}
        label={`Ingresos mensuales: ${region === "all" ? "todas las regiones" : region}`}
      />
      <DataTable sales={filtered} />
      {definition && (
        <Dialog
          title="Definición verificable: ingresos válidos"
          onClose={() => setDefinition(false)}
        >
          <dl className="definition-list">
            <dt>Fórmula</dt>
            <dd>
              <code>SUM(importe) WHERE importe IS NOT NULL</code>
            </dd>
            <dt>Columnas</dt>
            <dd>importe, fecha, region</dd>
            <dt>Filtros</dt>
            <dd>
              Región: {region === "all" ? "todas" : region}; enero – junio 2026
            </dd>
            <dt>Unidad</dt>
            <dd>EUR · importes enteros del fixture</dd>
            <dt>Granularidad</dt>
            <dd>Mes para gráfico; total para tarjeta</dd>
            <dt>Nulos</dt>
            <dd>
              Excluidos, no imputados. {filtered.length - stats.valid} en la
              selección.
            </dd>
            <dt>Versión de definición</dt>
            <dd>demo-kpi-001 / revisión 1</dd>
          </dl>
        </Dialog>
      )}
    </>
  );
}

export function DashboardEditor({ sales }: { sales: Sale[] }) {
  const nextCard = useRef(3);
  const [cards, setCards] = useState([
    "Ingresos mensuales",
    "Ingresos por región",
  ]);
  const [type, setType] = useState<"bar" | "line">("bar");
  const { notify } = useApp();
  function move(index: number, offset: number) {
    setCards((old) => {
      const copy = [...old];
      [copy[index], copy[index + offset]] = [copy[index + offset], copy[index]];
      return copy;
    });
  }
  return (
    <>
      <div className="editor-toolbar">
        <p className="muted">Editor inicial · cambios en esta vista</p>
        <div className="row-actions">
          <select
            aria-label="Tipo de gráfico"
            value={type}
            onChange={(e) => setType(e.target.value as "bar" | "line")}
          >
            <option value="bar">Barras</option>
            <option value="line">Líneas</option>
          </select>
          <Button
            size="sm"
            onClick={() => {
              const id = nextCard.current++;
              setCards((c) => [...c, `Ingresos mensuales ${id}`]);
            }}
          >
            <Plus size={16} />
            Añadir gráfico
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              notify(
                "Vista preparada. La persistencia de dashboards se incorporará en el siguiente incremento del editor.",
              )
            }
          >
            Guardar vista
          </Button>
        </div>
      </div>
      <div className="editor-grid">
        {cards.map((card, index) => (
          <section className="panel editor-card" key={card}>
            <div className="panel-heading">
              <h3>{card}</h3>
              <div className="row-actions">
                <button
                  className="icon-button"
                  disabled={index === 0}
                  aria-label={`Subir ${card}`}
                  onClick={() => move(index, -1)}
                >
                  <ArrowUp size={14} />
                </button>
                <button
                  className="icon-button"
                  disabled={index === cards.length - 1}
                  aria-label={`Bajar ${card}`}
                  onClick={() => move(index, 1)}
                >
                  <ArrowDown size={14} />
                </button>
                <button
                  className="icon-button"
                  aria-label={`Eliminar ${card}`}
                  onClick={() =>
                    setCards((c) => c.filter((_, i) => i !== index))
                  }
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
            <Chart
              height={220}
              label={card}
              option={
                card === "Ingresos por región"
                  ? seriesOption(
                      ["Norte", "Sur", "Este", "Oeste"],
                      ["Norte", "Sur", "Este", "Oeste"].map(
                        (r) =>
                          summarize(sales.filter((s) => s.region === r)).total,
                      ),
                      type,
                    )
                  : seriesOption(
                      ["Ene", "Feb", "Mar", "Abr", "May", "Jun"],
                      monthlyTotals(sales),
                      type,
                    )
              }
            />
          </section>
        ))}
      </div>
      {!cards.length && (
        <div className="empty-state">
          <h3>Tu dashboard empieza aquí</h3>
          <p>Añade un gráfico para explorar tus métricas.</p>
        </div>
      )}
      <p className="muted fine-print">
        El redimensionamiento, los filtros compartidos y el guardado persistente
        se incorporarán al módulo BI.
      </p>
    </>
  );
}
