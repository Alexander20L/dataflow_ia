# ADR-038 — Dashboard adaptado a los datos y valoración «sí va / no va» de los hallazgos

Estado: aceptado e implementado en la Fase 21 (API 0.28.0, migración 0021; el catálogo de carga
sigue en `analysis-v13`). Documentación: [Fase 21](../architecture/phase-21.md). Se apoya en
[ADR-034](034-automatic-report-and-stage-progress.md) (informe automático), [ADR-036](036-business-comprehension-and-optional-feedback.md)
(valoración opcional) y [ADR-037](037-guided-exploration.md) (exploración guiada).

## Contexto

El dashboard descriptivo sigue una plantilla fija por medidas. La conversación con el profesor
propone que el dashboard se adapte a cada conjunto de datos (no por plantilla) y que el usuario
pueda decir qué hallazgos le sirven, sin que la IA genere código que se ejecute en el navegador.

## Decisión

1. **Trabajo de fondo `dashboard`** (operación interna `delivery.dashboard@1`, reglas
   `dashboard-design-v1`), encolado al publicarse la exploración. Fija la exploración, el
   análisis automático y la comprensión.
2. **Formato cerrado, sin cifras ni código**: secciones (hasta 6) con gráficos de un catálogo
   (`kpi`, `bar`, `line`, `heatmap`, `pie`, `table`), cada uno apuntando a un elemento publicado
   (`insight:<id>` o `exploration:<clave>`); un indicador apunta además a una de sus evidencias.
   La interfaz pone los datos publicados y los dibuja con ECharts (tooltips en texto plano). No
   hay iframe ni HTML del modelo.
3. **Compatibilidad por la forma de cada elemento**: líneas sólo con serie temporal; mapa de calor
   sólo con dos dimensiones y una cifra; circular sólo con partes de un total que se puede sumar
   (de 2 a 6, sin negativos); barras con una cifra por grupo; indicador sólo con una cifra
   publicada del elemento. Se descartan dispersión y caja del plan inicial: necesitan filas
   individuales que no se publican ni ve la IA.
4. **IA y validación**: la IA (`copilot/dashboard.py`, prompt `dashboard-design` v1) ve sólo la
   forma de cada elemento (id, título, tipo, gráficos compatibles, ids de evidencia) y la
   comprensión del negocio. Python valida cada elección y registra cada rechazo con su motivo;
   los títulos con números que no salen de lo publicado se sustituyen. **La IA no puede ocultar
   hallazgos**: lo que no coloca va a «Otros hallazgos». Sin IA o sin ninguna elección válida, el
   diseño lo hacen las reglas (indicadores clave, hallazgos por importancia, exploración).
5. **Valoración opcional** (módulo `curation`, tabla `finding_feedback`, migración 0021,
   inmutable y sólo de añadir, vale la última marca): «keep» fija el elemento en «Fijados por
   ti», «drop» lo aparta a «Descartados por ti» y «none» retira la marca. El dashboard publicado
   no cambia: las marcas se aplican al leerlo (`arrangement`). Nunca bloquea nada.
6. **El informe sigue la valoración**: el informe se genera el último de la cola y lee el dashboard
   y las marcas vigentes (sus hashes quedan en la procedencia). Tras una marca se encola **una
   versión nueva** del informe (si ya hay una esperando, no otra); la anterior se conserva y se
   sigue sirviendo con `updating: true` hasta que la nueva termina. El informe nuevo sólo
   reordena: fijados primero, después el orden del dashboard, y los descartados en un anexo con
   sus evidencias intactas.
7. **API**: `GET /versions/{id}/dashboard` y `POST /versions/{id}/dashboard/feedback`. El progreso
   añade la etapa «Diseño del dashboard».

## Decisiones tomadas durante la implementación

- El informe pasa a reclamarse después de cualquier otro trabajo de fondo (antes, sólo por orden de
  llegada), para incluir el dashboard de su carga; si aun así se generó sin él, publicar el
  dashboard encola otra versión.
- Las marcas se guardan por versión (ordenan el dashboard y el informe de esa carga); a diferencia
  de la Fase 19, no se arrastran a la siguiente carga.
- Mientras la cadena comprensión → exploración → dashboard sigue en marcha, `GET` de la
  exploración y del dashboard responden `queued` con `execution_id` nulo en lugar de 404: la
  interfaz dejaba de preguntar y no mostraba la exploración (defecto latente de la Fase 20).

## Consecuencias

- Cada carga hace una llamada más a la IA (diseño), con presupuesto y registro.
- Una carga puede tener varias versiones del informe; la procedencia de cada una dice con qué
  dashboard y marcas se generó.
- La IA sigue sin producir cifras ni código ejecutable.
