# ADR-034 — Informe automático y progreso por etapas

Estado: aceptado e implementado en la Fase 17 (API 0.24.0, sin migración; el catálogo de carga
sigue en `analysis-v12`). Documentación: [Fase 17](../architecture/phase-17.md). Resuelve la
decisión D4 de la [Fase 14](../architecture/phase-14.md) (los informes vuelven como informe
automático) y el pendiente «dependencia `reportlab` sin uso». Se apoya en
[ADR-032](032-automatic-analysis-plan.md) y [ADR-033](033-bounded-investigation-and-ai-proposals.md).

## Contexto

Tras la Fase 16 una carga produce hallazgos, investigación y explicación, pero no hay un
entregable que se pueda compartir, y la interfaz sólo sabe si la carga está «en cola» o
«procesando»: no indica qué etapa falta. Los informes editables de la Fase 9 se retiraron en la
Fase 13 y `reportlab` quedó como dependencia sin uso.

## Decisión

1. **Módulo `delivery`** (nuevo; `reports` y `dashboards` siguen conservando sólo sus tablas):
   - `domain.build_report` (`automatic-report-v1`) arma un `ReportDocument` puro con resumen,
     explicación de la IA, hallazgos, investigación, calidad, análisis omitidos, limitaciones y un
     anexo de evidencias. **No calcula**: copia las cifras canónicas publicadas (sólo cambia el
     formato de lectura, sin redondear) y cada cifra conserva su `evidence_id`.
   - `pdf.render_pdf` dibuja el documento con ReportLab (`invariant=1`: mismo documento, mismos
     bytes). Es el único archivo que importa ReportLab (prueba AST).
   - `domain.progress` deriva las etapas de los trabajos de la cola (sin datos nuevos).
2. **Trabajo `automatic_report`** (operación interna `delivery.report@1`, fuera del catálogo de
   carga): se encola al publicarse una investigación; su input fija la investigación, el análisis
   y la calidad de la carga (id, clave, hash y tamaño) y se comprueban todos al empezar. Es trabajo
   de fondo como la investigación (se reclama después de cualquier carga). Produce un artefacto
   `report_pdf` (tipo ya existente). Sin IA ni red.
3. **Progreso por etapas** — análisis del archivo, investigación e informe — con estado
   `pending | queued | running | done | failed | skipped`. Una etapa sin trabajo tras otra
   terminada «no aplica» (versiones anteriores o cargas sin hallazgos); tras una que falló, se
   omite. **Sin migración**: no se registra progreso dentro de un trabajo.
4. **API**: `GET /versions/{id}/progress`, `GET /versions/{id}/report` (estado) y
   `GET /versions/{id}/report.pdf` (descarga; 409 `REPORT_NOT_READY` hasta que esté listo). Las
   versiones sin informe responden 404 `REPORT_NOT_AVAILABLE`.
5. **Interfaz**: «Resumen» arriba (etapas, tres hallazgos principales y descarga del PDF), luego
   hallazgos, investigación y dashboard. Sin botones de decisión.
6. **Tablas sin uso de las Fases 4–10** (dashboards e informes editables, conversaciones del
   copiloto y servicios conservados sin rutas): se **conservan como archivo histórico de sólo
   lectura**; no hay migración ni borrado (decisión del usuario).

## Consecuencias

- Toda carga con hallazgos termina en un PDF trazable sin intervención; regenerar el informe de
  la misma investigación da los mismos bytes salvo la fecha de generación.
- Si la investigación falla no hay informe (la etapa queda «omitida»); los hallazgos siguen
  publicados.
- El PDF se dibuja en el proceso del worker: el contenido está acotado (hallazgos, ≤ 12
  seguimientos, ≤ 24 puntos por gráfico) y no incluye filas de datos.
- `reportlab` deja de ser una dependencia sin uso.
