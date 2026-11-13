# ADR-046 — Se retira la pestaña Análisis

Estado: aceptado e implementado en la Fase 28 (sin cambios de backend: API 0.35.0, sin
migración). Documentación: [Fase 28](../architecture/phase-28.md). Completa
[ADR-039](039-dataset-tab-inspection-and-dictionary.md) a
[ADR-045](045-report-tab-review-history-and-narrative.md): las cinco pestañas del documento de
visión sustituyen a la pestaña Análisis.

## Contexto

Tras las Fases 22 a 27, la pestaña Análisis conservaba piezas de fases anteriores:

- el resumen (progreso por etapas, PDF y hallazgos principales);
- la lectura del archivo y los cambios de estructura;
- los hallazgos del análisis automático (Fase 15);
- el panorama descriptivo «Tu análisis automático»;
- el seguimiento de hallazgos (Fase 16) y la explicación automática C2 de versiones antiguas.

Casi todo ya estaba en otra pestaña, y algunas cosas, dos veces.

## Decisión

1. **Se retira la pestaña Análisis.** La versión tiene cinco pestañas: Dataset, Comprensión,
   Investigación, Dashboard e Informe.
2. **Progreso**: una franja compacta encima de las pestañas, visible desde todas. El PDF y los
   hallazgos principales ya están en Informe.
3. **Lectura del archivo**: ya estaba en Dataset › Archivo; allí se añaden los cambios de
   estructura frente a la versión anterior.
4. **Hallazgos del análisis automático (Fase 15)**: vista «Hallazgos del análisis» en
   Investigación, con los análisis omitidos.
5. **Panorama descriptivo**: se retira de la interfaz; sus indicadores, gráficos, lectura,
   calidad y detalle están en Dataset (perfil, calidad, registros), Comprensión (de qué trata y
   periodo) y Dashboard (indicadores y gráficos). El backend lo sigue calculando (`profile@4`
   alimenta la comprensión y el análisis).
6. **Versiones antiguas**, sólo de lectura y sólo cuando existen: el seguimiento de la Fase 16
   en Investigación («Seguimiento anterior») y la explicación C2 en Informe.

## Decisiones tomadas sin consulta

- No se borra código ni datos del backend: las rutas de los trabajos antiguos siguen para leer
  versiones anteriores.
- Las pruebas E2E que miraban la pestaña Análisis comprueban lo mismo donde vive ahora (registros
  en Dataset, lectura en Archivo, hallazgos en Investigación, PDF en Informe); las del panorama
  descriptivo se retiran con él.

## Consecuencias

- Ningún dato se muestra dos veces; cada resultado vive en la pestaña de su etapa.
- El panorama descriptivo deja de verse; si hace falta, vuelve como vista de Dataset.
