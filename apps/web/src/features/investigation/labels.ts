import type { Investigation, InvestigationNode, InvestigationRun } from "./api";

type Classification = NonNullable<InvestigationNode["classification"]>;

export const CLASSES: Record<Classification, string> = {
  relevant: "Hallazgo relevante",
  secondary: "Hallazgo secundario",
  descriptive: "Resultado descriptivo",
  inconclusive: "No concluyente",
  discarded: "Hipótesis descartada",
};

export const CLASS_BADGE: Record<Classification, string> = {
  relevant: "completed",
  secondary: "calculated",
  descriptive: "neutral",
  inconclusive: "review",
  discarded: "draft",
};

export const STOPPED: Record<NonNullable<Investigation["stopped"]>, string> = {
  completed: "Terminó el plan y sus investigaciones secundarias.",
  max_nodes: "Se detuvo al llegar al límite de investigaciones.",
  max_seconds: "Se detuvo al llegar al límite de tiempo.",
  paused: "La pausaste: lo calculado se conserva y se puede reanudar.",
  cancelled: "La cancelaste: lo calculado se conserva.",
};

export const TRIGGERS: Record<
  NonNullable<InvestigationRun["trigger"]>,
  string
> = {
  load: "Al cargar el archivo",
  feedback: "Tras validar relaciones",
  restart: "Volver a investigar",
  resume: "Reanudación",
};

export const RUN_STATES: Record<InvestigationRun["state"], string> = {
  queued: "En cola",
  running: "En marcha",
  succeeded: "Terminada",
  failed: "Falló",
  cancelled: "Cancelada antes de empezar",
};

export const CRITERIA: Record<string, string> = {
  magnitude: "Magnitud del efecto",
  business: "Relevancia para el negocio",
  quality: "Calidad de los datos",
  consistency: "Consistencia",
  evidence: "Evidencia y método",
  limitations: "Limitaciones",
};

export const PRIORITIES: Record<number, string> = {
  1: "Alta",
  2: "Media",
  3: "Baja",
};
