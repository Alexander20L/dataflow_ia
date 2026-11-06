# ADR-021 — Informes con procedencia, CSV con perfiles fijos y PDF en el worker con ReportLab

Estado: implementado en Fase 9 / API 0.13. Documentación: [Fase 9](../architecture/phase-9.md). Se apoya en [ADR-018](018-deterministic-business-analysis.md) y [ADR-020](020-persisted-dashboards.md).

## Contexto

El usuario necesita presentar sus resultados fuera de la aplicación sin perder la trazabilidad: un informe con texto propio y cifras exactas, un PDF reproducible y CSV que otras herramientas (y Excel en configuración regional española) lean bien.

## Decisión

- **Informes** con revisiones inmutables. Los bloques de datos apuntan a una ejecución exacta de `analytics.query` o a una tarjeta exacta de una revisión de dashboard; su procedencia se calcula siempre a partir de esas referencias. «Actualizar bloques» es explícito y crea una revisión nueva, con la misma regla de planes que los dashboards.
- **CSV con dos perfiles fijos**: `standard` (UTF-8, `,`, LF, nulos vacíos, punto decimal; garantiza la ida y vuelta con la ingesta y nunca cambia) y `excel_regional` (BOM, `;`, CRLF, coma decimal). Elige el usuario. Los resultados llevan un `evidence_id` por cifra.
- **PDF en el worker con ReportLab** (decisión bloqueante aprobada): ejecución `report_render` sobre una revisión exacta, entrada `report` preparada por bootstrap, operación interna fuera del catálogo y artefacto con hash. Frente a WeasyPrint (GTK/Pango nativos, problemáticos en Windows; +60–80 MB) y Playwright con Chromium (+300–400 MB, navegador en el worker), ReportLab es Python puro, ~5 MB, rápido e idéntico en Windows y en la imagen del worker.
- **Gráficos en el PDF** (opción A aprobada): KPI y tablas siempre; barras y líneas con los gráficos vectoriales de ReportLab a partir de las mismas filas, **siempre seguidos de su tabla de cifras exactas con `evidence_id`**. El gráfico ilustra; la trazabilidad está en la tabla.

### Decisiones tomadas en la implementación

- La ida y vuelta compara el hash lógico recalculado con los descriptores de columna de la original: el hash incluye IDs de columna, que cada versión genera de nuevo.
- En `excel_regional` las celdas de texto que empiezan por `= + - @` (o tabulador) llevan un `'` delante para que Excel no las ejecute; el perfil estándar no toca el contenido.
- Un informe se ancla a una versión (la que se ve al crearlo); el PDF es una ejecución de esa versión. «Actualizar bloques» cambia esa versión.
- La tabla `report_renders` vincula cada PDF con su revisión en lugar de buscarla dentro del plan de la ejecución.
- Hasta 200 cifras por bloque en el PDF; el CSV del resultado las incluye todas.
- En los gráficos del PDF el eje parte de 0 (o del valor más negativo) y un nulo no se dibuja.
- Una solicitud sin cambios no registra su clave de idempotencia (no crea revisión), como en los demás editores.
- ReportLab no publica tipos: mypy ignora sus importaciones (acotadas a `reports/pdf.py`) en lugar de añadir `types-reportlab`.
- Los bloques de análisis admiten `analytics.query@1` y `@2`; las tarjetas, sólo `@2` (Fase 8).

## Alternativas

- **`window.print()`** del navegador: no es reproducible ni queda como artefacto con hash.
- **Exportar el CSV original** de una derivada: no existe; la tabla publicada es la fuente.
- **Un solo perfil CSV** («estándar» con coma decimal): rompería la ida y vuelta o a Excel.
- **SVG de ECharts en el servidor**: exigiría un motor JavaScript en el worker.

## Consecuencias

- Un PDF se reproduce por su revisión: mismas referencias, mismas cifras y evidencias; su hash queda registrado.
- Dependencia nueva `reportlab` (con `pillow` y `charset-normalizer`).
- Desplegar API y worker juntos desde 0.12.
