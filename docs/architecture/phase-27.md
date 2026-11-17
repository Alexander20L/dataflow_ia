# Fase 27 — Pestaña Informe

Estado: **implementada** (API 0.35.0, sin migración, catálogo de carga `analysis-v13`).
Decisión: [ADR-045](../adr/045-report-tab-review-history-and-narrative.md). Parte de la
[Fase 17](phase-17.md) (informe automático), la [Fase 25](phase-25.md) (investigación) y la
[Fase 26](phase-26.md) (dashboard).

## Objetivo

Entregar conclusiones comprensibles y verificables: un documento analítico que explique qué se
investigó, qué se encontró, por qué importa y qué limitaciones hay, revisado por el usuario y
con historial de versiones.

## Recorrido

```
… investigación ─▶ dashboard ─▶ informe v2 (delivery.report@2, automatic-report-v2)
                                  documento (report_document) ─▶ PDF al descargar
revisión (aprobar / rechazar) ─▶ finding_feedback
«Generar versión con mi selección» ─▶ otra ejecución del informe (la anterior se conserva)
```

Las cargas nuevas ya no ejecutan el seguimiento de hallazgos de la Fase 16.

## Piezas

| Pieza                                                | Dónde                           |
| ---------------------------------------------------- | ------------------------------- |
| Contratos (documento v2, revisión, historial)        | `modules/delivery/contracts.py` |
| Secciones, revisión y conclusiones por reglas (puro) | `modules/delivery/report.py`    |
| Narrativa de la IA verificada (prompt v1)            | `modules/copilot/report.py`     |
| Trabajo, cadena, historial, revisión y generación    | `bootstrap/delivery_job.py`     |
| Cadena sin seguimiento                               | `bootstrap/services.py`         |
| Pestaña Informe                                      | `apps/web/src/features/report/` |

## Secciones del documento

1. **Resumen ejecutivo**: análisis, archivo, fecha, objetivo, de qué trata (hipótesis de la IA),
   principales descubrimientos, indicadores del dashboard y conclusiones generales.
2. **Descripción del dataset**: formato, registros, columnas, periodo, dimensiones, medidas,
   grano, variables con su escala y significado, y limitaciones.
3. **Calidad de los datos y metodología**: completitud, problemas, criterios, variables con
   vacíos, métodos y, por investigación, registros considerados, filtros y exclusiones.
4. **Hallazgos principales**: título, pregunta e hipótesis, evidencia (tabla con sus
   evidencias), gráfico, interpretación, importancia, método y limitaciones; después los otros
   resultados y los rechazados.
5. **Investigaciones realizadas**: plan, secundarias, hipótesis descartadas y no concluyentes.
6. **Conclusiones y recomendaciones**, separadas, con el aviso de que no hay causalidad
   demostrada.
7. Lectura del archivo y **anexo de evidencias**.

## API

- `GET /api/v1/versions/{id}/report` añade `number` y `document`.
- `GET /api/v1/versions/{id}/report.pdf?execution_id=` descarga una versión del historial.
- `GET /api/v1/versions/{id}/report/history` (`getReportHistory`).
- `GET /api/v1/versions/{id}/report/versions/{execution_id}` (`getReportVersion`).
- `GET` y `POST /api/v1/versions/{id}/report/review` (`getReportReview`,
  `reviewReportFinding`): candidatos con su estado; aprobar, rechazar o dejar pendiente.
- `POST /api/v1/versions/{id}/report/versions` (`generateReportVersion`): 409
  `REPORT_UP_TO_DATE` sin cambios y `REPORT_GENERATING` si ya hay una en marcha.

## Interfaz

La pestaña **Informe** va tras Dashboard:

- arriba, la versión, la fecha y «Descargar PDF»;
- **Informe**: vista previa con índice y las mismas secciones que el PDF;
- **Revisión de hallazgos**: cada candidato con su clase, estado y si es principal; «Aprobar» y
  «Rechazar», y «Generar versión con mi selección»;
- **Historial**: versiones con su motivo, aprobados y principales; «Ver» y «PDF».

## Pruebas

- `tests/test_phase27_report.py`: sólo aprobados como principales y rechazados nunca; informe
  honesto sin hallazgos; cifras del anexo iguales a sus evidencias, metodología y PDF
  reproducible; narrativa sin números libres ni causas; recorrido por la API (secciones,
  narrativa de la IA falsa, revisión, versión nueva, historial y PDF de una versión anterior).
- Adaptadas a la cadena nueva: Fases 16, 17, 21, 23 y 24B.
- E2E `report.spec.ts`; `analysis.spec.ts` y `automatic-overview.spec.ts` buscan la explicación
  en el informe.

## Limitaciones

- La pestaña Análisis sigue con lo anterior; su reorganización queda para una fase de limpieza.
- La personalización del dashboard no cambia el informe.
