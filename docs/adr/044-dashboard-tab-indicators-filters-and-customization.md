# ADR-044 — Pestaña Dashboard: indicadores, filtros, origen y versión personalizada

Estado: aceptado e implementado en la Fase 26 (API 0.34.0, migración 0027; el catálogo de carga
sigue en `analysis-v13`). Documentación: [Fase 26](../architecture/phase-26.md). Modifica
[ADR-038](038-adapted-dashboard-and-finding-feedback.md) (dashboard adaptado).

## Contexto

La especificación de la pestaña Dashboard pide:

- un resumen ejecutivo con indicadores que tengan nombre, valor, unidad (cuando esté definida),
  periodo de referencia, comparación (cuando exista una base válida) y procedencia, sin inventar
  monedas, porcentajes ni unidades;
- gráficos elegidos según el tipo de información (también histograma y dispersión) y legibles
  con muchas categorías;
- un orden que responda a la importancia de los descubrimientos;
- filtros por periodo y por categoría que actualicen lo que depende de ellos, dejando claro
  cuándo se ve el dataset completo y cuándo un subconjunto;
- el origen reproducible de cada gráfico;
- una versión personalizada (ocultar, reordenar, elegir indicadores, renombrar) que conviva con
  la automática sin destruirla;
- no inventar visualizaciones si no hay hallazgos suficientes y señalar los resultados parciales.

El dashboard de la Fase 21 ya diseñaba secciones y gráficos (IA o reglas, validados por Python)
y tenía las marcas «sí va / no va», pero sus indicadores eran la primera cifra de cada hallazgo,
no tenía filtros, origen ni versión personalizada, y estaba dentro de Análisis.

## Decisión

1. **`delivery.dashboard@2` (`dashboard-design-v2`)**. Además de diseñar, el trabajo del
   dashboard calcula en el worker, con el motor exacto de la exploración y sobre todas las filas
   de la tabla que leyó la investigación, un conjunto de consultas por reglas: registros, total
   (o promedio si no es aditiva) de hasta tres medidas, el grupo con mayor valor de la primera
   dimensión agrupable, la evolución mensual de la medida principal y la comparación del último
   mes con el anterior (sólo si hay periodo), un histograma por medida y la dispersión de los
   pares de medidas con asociación moderada o fuerte. `delivery.dashboard@1` sigue registrado.
2. **Tipos internos `distribution` y `scatter`** en el motor de la exploración. La validación de
   la investigación no los acepta. El histograma usa la regla de Sturges (máximo 20 intervalos)
   y la dispersión muestra hasta 300 puntos a intervalos regulares del orden de las filas.
3. **Indicadores**: valor con su evidencia; unidad sólo si la comprensión la declaró; periodo de
   referencia (primer y último mes o «todo el dataset»); comparación con el mes anterior sólo con
   dos meses con datos; y su origen.
4. **Origen** (`Trace`) en cada elemento: investigación relacionada (nodo y pregunta), operación,
   columnas, columna temporal, medida, agrupación, agregación, registros utilizados de los
   totales, filtros y método.
5. **Orden por importancia**. Sin IA: indicadores, evolución, hallazgos principales (relevantes de
   la investigación y después los del análisis por importancia), secundarios y distribuciones y
   relaciones. Con IA: el prompt de diseño v2 recibe la clase de cada resultado y pide ese orden.
   La validación de la Fase 21 no cambia; lo que calcula el dashboard no es obligatorio.
6. **Legibilidad**: circular sólo de 2 a 6 partes; mapa de calor como mucho con 200 celdas; las
   barras dibujan los 12 primeros grupos y el resto queda en la tabla.
7. **Filtros calculados al momento en la API y sin guardar** (`POST /dashboard/filter`). Se
   filtra la tabla publicada (meses y valores de hasta tres dimensiones) y se vuelve a calcular
   cada elemento de la investigación y del dashboard. Los hallazgos del análisis automático
   indican que muestran el dataset completo. Las evidencias se derivan de los filtros, así que
   se pueden reproducir.
8. **Versión personalizada** (migración 0027, tabla nueva `dashboard_customizations`,
   inmutable): cada guardado es una revisión con `expected_revision` (409 si cambió). Si no hay
   cambios, no se crea revisión. Sólo puede señalar elementos del dashboard automático con un
   gráfico compatible. Si el dashboard se rehace, los gráficos que ya no existen no se muestran y
   se cuentan.
9. **Pestaña Dashboard** propia, tras Investigación. El panel sale de Análisis.

## Decisiones tomadas sin consulta

- Los filtros se calculan en la API, como la vista de registros de la Fase 22, y no pasan por
  la cola.
- La personalización no cambia el informe: las marcas «sí va / no va» siguen siendo la
  validación que lo ordena. Unificarlas es trabajo de la fase del Informe.
- La pausa o cancelación de la investigación y su detención por tiempo se señalan como
  «resultados parciales». El límite de investigaciones no se señala, porque es el tamaño previsto
  del árbol.
- «Explorar los registros» abre la pestaña Dataset en Registros, sin aplicar el filtro del
  indicador.
- Los dashboards anteriores se siguen leyendo, sin filtros ni personalización (409
  `DASHBOARD_V2_REQUIRED`).
- El número de grupos de cada elemento no se envía a la IA: sólo forma, clase e ids.

## Consecuencias

- El trabajo del dashboard lee la tabla publicada y hace hasta unas quince consultas exactas
  más por carga; ninguna llamada nueva a la IA.
- `GET /dashboard` trae todos los elementos que la versión personalizada puede mostrar.
