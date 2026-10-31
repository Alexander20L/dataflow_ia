export type Sale = {
  id: string;
  date: string;
  region: string;
  category: string;
  revenue: number | null;
  units: number;
};
export type Project = {
  id: string;
  name: string;
  description: string;
  file: string;
  updated: string;
  status: "completed" | "review" | "draft" | "archived";
  rows: number;
  columns: number;
};
export const steps = [
  "Ingesta",
  "Entendimiento",
  "Calidad",
  "Limpieza",
  "Exploración",
  "Análisis",
  "Visualización",
  "Explicación",
  "Recomendaciones",
];
export const initialProjects: Project[] = [
  {
    id: "ventas-2026",
    name: "Análisis de ventas 2026",
    description: "Rendimiento comercial por región y categoría",
    file: "ventas_2026.csv",
    updated: "Proyecto de ejemplo",
    status: "review",
    rows: 240,
    columns: 6,
  },
  {
    id: "clientes",
    name: "Segmentación de clientes",
    description: "Exploración de la cartera de clientes",
    file: "clientes.parquet",
    updated: "Proyecto de ejemplo",
    status: "draft",
    rows: 0,
    columns: 0,
  },
  {
    id: "inventario",
    name: "Control de inventario",
    description: "Calidad del catálogo de productos",
    file: "inventario.xlsx",
    updated: "Proyecto de ejemplo",
    status: "draft",
    rows: 0,
    columns: 0,
  },
];
// Fixture determinista: sin fechas relativas ni generación aleatoria.
export const originalSales: Sale[] = Array.from({ length: 240 }, (_, i) => ({
  id: `V-${String(i + 1).padStart(4, "0")}`,
  date: `2026-${String(Math.floor(i / 40) + 1).padStart(2, "0")}-${String((i % 28) + 1).padStart(2, "0")}`,
  region: ["Norte", "Sur", "Este", "Oeste"][i % 4],
  category: ["Tecnología", "Hogar", "Oficina"][i % 3],
  revenue:
    i % 30 === 0 ? null : 140 + ((i * 137) % 1700) + Math.floor(i / 40) * 90,
  units: 1 + (i % 12),
}));
export const missingCount = originalSales.filter(
  (s) => s.revenue === null,
).length;
export const cleanSales = originalSales.filter(
  (s): s is Sale & { revenue: number } => s.revenue !== null,
);
export function summarize(sales: Sale[]) {
  const values = sales
    .flatMap((s) => (s.revenue === null ? [] : [s.revenue]))
    .sort((a, b) => a - b);
  const total = values.reduce((a, b) => a + b, 0);
  return {
    total,
    count: sales.length,
    valid: values.length,
    mean: values.length ? total / values.length : 0,
    median: values.length
      ? (values[Math.floor((values.length - 1) / 2)] +
          values[Math.ceil((values.length - 1) / 2)]) /
        2
      : 0,
    min: values[0] ?? 0,
    max: values.at(-1) ?? 0,
  };
}
export function monthlyTotals(sales: Sale[]) {
  return Array.from({ length: 6 }, (_, i) =>
    sales
      .filter((s) => Number(s.date.slice(5, 7)) === i + 1)
      .reduce((a, s) => a + (s.revenue ?? 0), 0),
  );
}
export const statusLabels = {
  archived: "Archivado",
  completed: "Completado",
  review: "Requiere revisión",
  draft: "Borrador",
};
