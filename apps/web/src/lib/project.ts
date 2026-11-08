// Vista de un proyecto en la interfaz (derivada de la API de proyectos).
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
export const statusLabels = {
  archived: "Archivado",
  completed: "Completado",
  review: "Requiere revisión",
  draft: "Borrador",
};
