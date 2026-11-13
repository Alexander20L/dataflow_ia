# Fase 28 — Limpieza: se retira la pestaña Análisis

Estado: **implementada** (sólo interfaz: API 0.35.0, sin migración).
Decisión: [ADR-046](../adr/046-retire-analysis-tab.md).

## Objetivo

Que cada resultado viva en la pestaña de su etapa y nada se muestre dos veces: con las cinco
pestañas del documento de visión (Fases 22 a 27), la pestaña Análisis sobra.

## Dónde queda cada pieza

| Antes, en Análisis                                 | Ahora                                                |
| -------------------------------------------------- | ---------------------------------------------------- |
| Progreso por etapas                                | Franja «Progreso de la carga» encima de las pestañas |
| Descargar informe y hallazgos principales          | Informe                                              |
| Lectura del archivo                                | Dataset › Archivo (ya estaba)                        |
| Cambios de estructura frente a la versión anterior | Dataset › Archivo                                    |
| Hallazgos del análisis automático (Fase 15)        | Investigación › Hallazgos del análisis               |
| Panorama descriptivo «Tu análisis automático»      | Retirado (Dataset, Comprensión y Dashboard)          |
| Seguimiento de hallazgos (Fase 16), antiguas       | Investigación › Seguimiento anterior                 |
| Explicación automática C2, antiguas                | Informe                                              |

## Cambios

- `features/ingestion/csv-workspace.tsx`: cinco pestañas y la franja de progreso
  (`progress-strip.tsx`); se borran `automatic-overview.tsx` y `delivery-summary.tsx`.
- `features/investigation/investigation-tab.tsx`: vistas opcionales «Hallazgos del análisis» y
  «Seguimiento anterior».
- `features/dataset/dataset-tab.tsx`: contenido extra en Archivo (cambios de estructura).
- `features/report/report-tab.tsx`: explicación C2 de versiones antiguas.

## Pruebas

E2E adaptadas: `analysis`, `automatic-overview`, `csv`, `regional` y `xlsx` comprueban lo mismo
en su pestaña nueva (`helpers.ts`: `openTab`, `openFindings`, `openRecords`, `openFile`). El
backend no cambia.
