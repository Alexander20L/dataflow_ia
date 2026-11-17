# ADR-045 — Pestaña Informe: documento v2, revisión humana, historial y narrativa

Estado: aceptado e implementado en la Fase 27 (API 0.35.0, sin migración; el catálogo de carga
sigue en `analysis-v13`). Documentación: [Fase 27](../architecture/phase-27.md). Modifica
[ADR-034](034-automatic-report-and-stage-progress.md) (informe automático) y
[ADR-038](038-adapted-dashboard-and-finding-feedback.md) (las marcas pasan a ser la revisión del
informe); retira de las cargas nuevas la investigación de
[ADR-033](033-bounded-investigation-and-ai-proposals.md).

## Contexto

La especificación de la pestaña Informe pide un documento analítico entregable, no una
exportación de gráficos:

- resumen ejecutivo, descripción del dataset, calidad y metodología, hallazgos principales
  (título, descripción, evidencia, visualización, interpretación, importancia y limitaciones),
  investigaciones realizadas, y conclusiones y recomendaciones separadas;
- que diga cuándo una investigación excluyó registros;
- revisión humana (pendiente, aprobado, rechazado): sólo los aprobados alimentan la versión
  final, y un cambio de selección crea otra versión sin sobrescribir la anterior;
- vista previa en la aplicación, PDF, historial, fecha e identificación del dataset y de la
  ejecución.

El informe de la Fase 17 dependía de la investigación de la Fase 16 (su entrada y la fuente
del resumen y las recomendaciones de la IA), sólo existía en PDF y las marcas «sí va / no va»
sólo ordenaban.

## Decisión

1. **`delivery.report@2` (`automatic-report-v2`)**: el informe parte del dashboard publicado (Fase 26) y lee lo ya calculado por Dataset (inspección), Comprensión, Investigación y Dashboard; no
   recalcula. Su artefacto es el documento (`report_document`); el PDF se dibuja de él al
   descargarlo (ReportLab con `invariant=1`: mismo documento, mismo PDF). `delivery.report@1`
   sigue registrado para los informes anteriores.
2. **Secciones**: resumen ejecutivo (análisis, archivo, fecha, objetivo, descubrimientos,
   indicadores del dashboard, conclusiones generales), descripción del dataset, calidad y
   metodología (completitud, problemas, criterios, variables con vacíos, métodos y, por
   investigación, registros considerados, filtros y exclusiones), hallazgos principales,
   investigaciones realizadas (plan, secundarias, descartadas, no concluyentes), conclusiones y
   recomendaciones, lectura del archivo y anexo de evidencias.
3. **Revisión humana**: las marcas del dashboard son la revisión (`keep` = aprobado, `drop` =
   rechazado, sin marca = pendiente), así que no hay tabla nueva. Si hay alguno aprobado, sólo
   los aprobados son principales; sin revisión, los relevantes de la investigación (o, si no
   hay, los hallazgos del análisis con importancia ≥ 50) marcados «Sin revisar». Un rechazado
   nunca es principal. Sin hallazgos, el informe lo dice y no inventa conclusiones.
4. **Versiones a petición**: revisar no genera el informe; «Generar versión con mi selección»
   (`POST /report/versions`) crea otra versión si la selección cambió (409
   `REPORT_UP_TO_DATE` si no). El historial lista todas con su motivo y se puede ver y
   descargar cualquiera.
5. **Narrativa de la IA** (prompt `report-narrative` v1): resumen, conclusiones y
   recomendaciones de los hallazgos principales. Cifras sólo como `{{evidence:id}}` (un número
   libre se retira y una referencia ajena anula la narrativa); una frase que afirma una causa
   se retira. Sin IA, las reglas escriben conclusiones (con la cifra principal y su evidencia)
   y recomendaciones según el tipo de resultado. Siempre se añade el aviso de que no hay
   causalidad demostrada.
6. **Cadena**: las cargas nuevas ya no encolan el seguimiento de la Fase 16; el informe se
   encola al publicarse el dashboard y su etapa de progreso desaparece. Las versiones
   anteriores conservan su seguimiento y su informe v1. No se borra nada.

## Decisiones tomadas sin consulta

- La revisión reutiliza `finding_feedback` (0021) en vez de una tabla nueva.
- El informe v2 no se regenera con cada marca; sí cuando cambia el dashboard (p. ej. tras
  volver a investigar), como antes.
- La pestaña Análisis no cambia en esta fase, salvo que su explicación C2 deja de mostrarse en
  las cargas con análisis automático (su explicación está ahora en el informe).
- La personalización del dashboard (ADR-044) sigue sin afectar al informe.

## Consecuencias

- Una llamada a la IA por versión del informe (en vez de las del seguimiento de la Fase 16).
- `GET /report` añade `number` y `document`; rutas nuevas de historial, versión, revisión y
  generación; `GET /report.pdf` admite `execution_id`.
