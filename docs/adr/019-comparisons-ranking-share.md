# ADR-019 — Comparaciones, ranking y participación como `analytics.query@2`

Estado: implementado en Fase 7B / API 0.11. Documentación: [Fase 7](../architecture/phase-7.md). Amplía [ADR-018](018-deterministic-business-analysis.md).

> **Vigencia (Fase 13, [ADR-026](026-fully-automatic-single-path.md))**: `analytics.query@2` sigue vigente como motor; ya no hay interfaz para pedir comparaciones, rankings o participaciones.

## Contexto

La 7A responde «importe total por región y mes» con cifras exactas y evidencia por cifra. Las preguntas siguientes son comparativas: cuánto cambió frente al mes anterior o al mismo mes del año pasado, qué regiones están arriba y qué parte del total aporta cada una. Responderlas exige filas fuera del periodo consultado, cocientes exactos y un orden reproducible, sin cambiar ni una cifra de los planes de la 7A.

## Decisión

- **Versión nueva de la operación**: `analytics.query@2` amplía los parámetros de `@1` con `comparisons`, `change_scale`, `ranking`, `share_of_total` y `share_scale`. `@1` (modelo, motor y resultado) no cambia y sus planes guardados se ejecutan igual; una referencia congelada de su JSON exacto lo protege. Sin opciones nuevas, `@2` calcula las mismas cifras, conteos y `evidence_id` de `value` que `@1`. Catálogo `analysis-v6`. La interfaz crea siempre `@2`.
- **Comparaciones** (periodo anterior y mismo periodo del año anterior) por grupo temporal. El periodo consultado se calcula como en `@1`; la base es una **segunda pasada sin el filtro de periodo**, con los filtros de la consulta que no son de periodo y los de la métrica, limitada a los periodos base que necesita algún grupo. Sus conteos se declaran aparte (`base_counts`, con `outside_base_periods`). Con comparaciones, el periodo debe estar **alineado a la granularidad** (7B-1): nunca se compara medio mes con un mes completo. Un periodo sin datos da nulo con indicador (`no_base_data`, `no_counterpart`, `missing_period`), nunca 0; el 29 de febrero y la semana 53 no se sustituyen por un vecino. Variación absoluta sobre las cifras mostradas y porcentual sobre |base| (7B-5), en `Decimal` con HALF_EVEN; con base 0 hay variación absoluta y no porcentual.
- **Ranking**: top N por una métrica, dentro de cada periodo o de todo el resultado. Posiciones 1, 2, 3 sin empates compartidos: dos valores iguales se ordenan por las dimensiones (desempate estable) y la fila lo declara con `tied_with_previous`, que forma parte de la evidencia de su posición. Los grupos sin valor no tienen posición; se declara cuántos se ocultan. El presupuesto de filas se aplica **después** del top N (7B-3).
- **Participación** sólo para `sum` y `count` (7B-2), sobre el total de la partición calculado **antes** del top N y del presupuesto; cada porcentaje se redondea por separado (D7) y se declaran la tolerancia de la suma (n × media unidad de `share_scale`) y si hay valores negativos. Planning lo valida con `SHARE_NOT_ADDITIVE` mediante el descriptor (`additive_metrics`), sin importar analytics.
- **Evidencia** (D9): la dirección de `value` no cambia (misma fórmula que `@1`); las cifras derivadas añaden `cell` (`previous_period`, `same_period_last_year`, `change`, `change_pct`, `share_of_total`, `rank`) y su `detail`. La ruta de evidencia recalcula la dirección con las mismas funciones que la generaron.

## Alternativas

- **Ampliar `@1`**: cambiaría el significado de planes guardados con `extra="forbid"`; descartada.
- **Calcular la base quitando sólo el rango del filtro** (todas las filas fuera del periodo): mezclaría periodos que nadie compara y haría ilegibles los conteos.
- **Periodos parciales comparados con el tramo equivalente** (7B-1 B): más flexible pero difícil de explicar y auditar.
- **Posiciones compartidas en los empates** (1, 1, 3): contradice el desempate estable aprobado; el indicador de empate conserva la información sin romper el orden.
- **Método del mayor resto** para que los porcentajes sumen 100: altera cifras individuales; se prefiere declarar la tolerancia (D7).
- **Participación de cualquier agregación**: un «% de una media» o de valores distintos no suma 100 y engaña.

## Consecuencias

- API 0.11 con cambios aditivos: `GET /analysis` devuelve una unión distinguida por `operation`, `EvidenceReference` admite `cell` y `detail`, y `EvidenceView` añade contexto opcional. Sin migración: todo vive en el artefacto `analysis_result`.
- Desplegar API y worker juntos: un worker 0.10 no tiene ejecutor para `analytics.query@2`.
- El historial de ejecuciones sigue sin mostrar resultados de análisis y los gráficos llegan en la Fase 8.
