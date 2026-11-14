# Fase 7 — Análisis de negocio determinista

Se entregó en dos partes: **7A** (API 0.10) añade métricas definidas por el usuario, consultas estructuradas y evidencia direccionable por cifra ([ADR-018](../adr/018-deterministic-business-analysis.md)); **7B** (API 0.11) añade comparaciones entre periodos, ranking y participación sobre el total como `analytics.query@2` ([ADR-019](../adr/019-comparisons-ranking-share.md)).

Objetivo: responder preguntas reales sobre los datasets del usuario con métricas definidas explícitamente y poder rastrear cada cifra hasta su definición, filtros, versión de datos, revisión semántica y filas excluidas. El sistema nunca deduce que una suma son «ingresos»: el nombre de negocio es una etiqueta del usuario sobre una métrica definida.

## 7A · Recorrido e interfaz

CSV procesado → (Limpieza: convertir la medida y la fecha) → **Análisis** → «Nueva métrica» → elegir métricas, dimensiones, agrupación temporal y periodo → «Calcular» → tabla de resultados → seleccionar una cifra → «De dónde sale este número».

- La etapa **Análisis** se activa para CSV propios; Exploración sigue desactivada y la demostración del fixture (`features/workspace/stages.tsx`) no cambia y sigue etiquetada.
- Si falta un requisito semántico, el análisis muestra «Requisito semántico pendiente» con el botón «Ir a Entendimiento». Al volver, «Calcular» guarda otra revisión del plan con la revisión semántica vigente.
- Panel de procedencia: cifra con su moneda o unidad, métrica (etiqueta, agregación, columna, revisión), grupo, filtros de la definición y de la consulta, periodo, política de nulos, filas de entrada, excluidas por filtros, excluidas por nulos e incluidas, versión de datos, revisión semántica y `evidence_id`.
- Entendimiento en una versión derivada ofrece «Partir de la revisión de vN»: carga en el borrador las decisiones de la versión de origen (mismos IDs de columna). No se confirma nada hasta guardar.

## Métricas

Revisiones inmutables como las semánticas y las reglas de calidad (`expected_revision`, `Idempotency-Key`, sin revisión si no hay cambios). Una familia por métrica, anclada a la tabla base donde se definió; las versiones derivadas la usan si los tipos son compatibles y se edita sólo desde su tabla base (`METRIC_ANCHOR_MISMATCH`).

| Campo               | Contenido                                                                                                         |
| ------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `label`             | nombre de negocio («Ingresos»)                                                                                    |
| `measure_column_id` | columna medida (por ID)                                                                                           |
| `aggregation`       | `sum`, `avg`, `min`, `max` (numérica) · `count`, `count_distinct` (cualquier tipo)                                |
| `filters`           | filtros estructurados: `eq`, `neq`, `in`, `not_in`, `gt`, `gte`, `lt`, `lte`, `between`, `is_null`, `is_not_null` |
| `time_column_id`    | fecha de negocio opcional                                                                                         |
| `null_policy`       | sólo `exclude`: los nulos de la medida se excluyen y se cuentan; nunca «nulo = 0»                                 |

La unidad o la moneda no se guardan en la métrica: salen de la revisión semántica fijada para la columna medida (una sola fuente de verdad). Los valores de filtro se escriben con la representación canónica de la Fase 6 (decimal con punto, fecha ISO, `true`/`false`); un nulo sólo cumple `is_null`.

## Requisito semántico positivo

Primer requisito semántico real del catálogo (pendiente desde la [Fase 4](phase-4.md)):

- `sum`, `avg`, `min` y `max` exigen una columna entero o decimal **confirmada como `measure`** en la revisión semántica fijada al plan.
- Si la consulta agrupa por tiempo o filtra un periodo, la columna temporal de cada métrica debe ser una fecha **confirmada como `business_date`** y ser la misma para todas.
- `count` y `count_distinct` no exigen rol ni unidad (contar operaciones o clientes por un identificador es legítimo).
- Las métricas medidas de una consulta deben compartir moneda o unidad; los conteos se combinan con cualquiera.

| Código                         | Se produce cuando                                                             | Se resuelve en |
| ------------------------------ | ----------------------------------------------------------------------------- | -------------- |
| `SEMANTIC_REQUIREMENT_MISSING` | falta revisión fijada o la medida/fecha no está confirmada con su rol         | Entendimiento  |
| `METRIC_REFERENCE_MISMATCH`    | la métrica no existe, es ajena, su hash no coincide o usa una columna ausente | paso           |
| `UNIT_MISMATCH`                | métricas medidas con monedas o unidades distintas                             | paso           |
| `TIME_COLUMN_MISMATCH`         | agrupación temporal o periodo con métricas sin la misma columna temporal      | paso           |
| `COLUMN_TYPE_MISMATCH`         | medida no numérica (conviértela en Limpieza) o fecha que no es fecha          | paso           |

## Consulta `analytics.query@1`

De sólo lectura: se ejecuta como plan normal, sin vista previa ni aprobación. Nada de expresiones ni SQL del usuario.

| Parámetro         | Contenido                                                                        |
| ----------------- | -------------------------------------------------------------------------------- |
| `metrics`         | 1–10 referencias exactas `{revision_id, content_sha256}`                         |
| `dimensions`      | 0–4 columnas (por ID)                                                            |
| `filters`         | filtros estructurados de la consulta                                             |
| `time_grain`      | `day`, `week` (ISO 8601: lunes, año ISO, `2026-W01`), `month`, `quarter`, `year` |
| `time_range`      | `{start, end}` inclusivo en fechas ISO                                           |
| `avg_scale`       | decimales de la media (por defecto 4, 0–12), HALF_EVEN, fijado en el plan        |
| `max_result_rows` | presupuesto de filas de salida (por defecto 1.000, máximo 10.000)                |

### Motor y determinismo

- Polars lee la tabla; la agregación se calcula en Python con aritmética exacta (`int` y `Decimal`). La media de Polars sobre decimales devuelve un float (0,15 → 0.15000000000000002), por eso `avg` = suma exacta / conteo, cuantizada a `avg_scale` con HALF_EVEN.
- Sumas con la escala de la columna; más de 38 dígitos → `RESULT_PRECISION_EXCEEDED`.
- Un nulo en una dimensión (o en la fecha, si se agrupa por tiempo) forma su propio grupo «(sin valor)», contado y nunca descartado.
- Un grupo existe si alguna métrica tiene filas incluidas en él. Una métrica sin filas en ese grupo vale `null` («sin filas»), no 0; los conteos valen `0`.
- Orden estable: por las dimensiones en el orden declarado y después el periodo, comparando valores tipados, con los nulos al final. No depende del orden de las filas de entrada.
- Agrupación temporal por la fecha de negocio. No hay columnas de instante con zona horaria en el catálogo: la zona horaria queda fuera de esta fase.
- Presupuesto: más grupos que `max_result_rows` → `RESULT_TOO_LARGE` con el número de filas que tendría el resultado; tiempo: el plazo del plan. Nada se publica si falla.

## Resultado y evidencia

Artefacto `analysis_result` (`GET /executions/{id}/analysis`): alcance (ejecución, paso, tabla de entrada, revisión semántica, filtros, periodo), definiciones usadas (revisión, hash, etiqueta, agregación, columna, filtros, moneda o unidad, escala) con sus conteos por métrica (`input_rows`, `excluded_by_filters`, `excluded_by_nulls`, `included_rows`) y filas con clave, etiquetas, valores en cadena canónica y un `evidence_id` por cifra.

**EvidenceReference**: ejecución, paso, artefacto (`slot`), tabla de entrada, revisión semántica, métrica `{revision_id, content_sha256}`, filtros de la métrica y de la consulta, granularidad, periodo, clave de fila y `cell: "value"`. `evidence_id` = hash canónico (dominio `evidence`) de todo lo anterior. La clave de fila es `{"dimensions": [{"column_id", "value"}], "period": {"grain", "start"} | null}` y sus valores usan la **celda canónica de la Fase 6**: `10.5` y `10.50` en una columna de escala 2 son el mismo valor y la misma evidencia; las fechas van en ISO; el grupo sin valor es la marca explícita `{"missing": true}` y nunca la cadena «(sin valor)». `GET /executions/{id}/evidence/{evidence_id}` recalcula la dirección y la compara antes de devolverla (Fase 10 la usará para validar lo que diga la IA).

## API 0.10

| Ruta                                                 | Función                                                                                                 |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| GET `/api/v1/representations/{id}/metrics`           | Métricas del proyecto con aplicabilidad a la tabla                                                      |
| POST `/api/v1/representations/{id}/metrics`          | Alta (`family_id: null`) o nueva revisión; `expected_revision`, `Idempotency-Key`; 422 `METRIC_INVALID` |
| GET `/api/v1/metrics/{revision_id}`                  | Revisión exacta                                                                                         |
| GET `/api/v1/executions/{id}/analysis`               | Resultado `analysis_result`                                                                             |
| GET `/api/v1/executions/{id}/evidence/{evidence_id}` | Una cifra con su referencia completa y su definición                                                    |

Sesión y propietario en todas (ajeno: 404); Origin y CSRF en la mutación. `UnderstandingContext.origin` (derivadas). Operación `analytics.query@1` en `analysis-v5`; artefacto y salida `analysis_result`. Cambios aditivos.

## Persistencia

Migración **0009**, sólo aditiva: `analytics_metric_families`, `analytics_metric_revisions` y `analytics_metric_save_requests` (las dos últimas inmutables por trigger). Downgrade bloqueado si hay métricas. **Actualizar desde 0.9 / esquema 0008**: desplegar API y worker juntos (un worker anterior no tiene ejecutor para `analytics.query@1`).

## Correcciones de fases anteriores

- `canonical_decimal` (Fase 6) cuantizaba con el contexto por defecto de Python (28 dígitos): un `Decimal(38, s)` de 29 a 38 dígitos hacía fallar el hash y la vista previa. Ahora usa un contexto amplio; ningún resultado existente cambia (esos valores antes fallaban). Prueba en `test_tabular_types.py`.
- Entendimiento no abría la revisión semántica de una **versión derivada** desde la interfaz («No hay una representación baseline publicada»): buscaba la tabla de la ejecución de referencia, que en una derivada no publica tabla. Ahora usa su única tabla publicada.
- El editor de planes mostraba los parámetros estructurados (listas de objetos) como «[object Object]» y permitía corromperlos: ahora los muestra en JSON de sólo lectura.

## Pruebas

- Motor (`test_analytics_engine.py`): sumas decimales exactas, media HALF_EVEN, enteros por encima de 2^53, nulos excluidos y contados, grupos sin valor, conteos en grupos sin filas, semanas ISO y trimestres en los bordes de año, rango inclusivo, determinismo con filas desordenadas, presupuesto, precisión, columna temporal distinta y **claves de evidencia canónicas** (10.5/10.50, marca de grupo sin valor frente al texto «(sin valor)»).
- Métricas (`test_analytics_metrics.py`): revisiones, conflicto, idempotencia, tipos, aplicabilidad en derivadas, anclaje y privacidad. Migración 0009.
- Planning (`test_planning_domain.py`): requisito semántico positivo, conteos sin rol, referencia, tipos, monedas distintas rechazadas y columna temporal.
- Ejecución (`test_analytics_runner.py`): «importe total por región y mes» sobre una v2 tipada, conteos, evidencia resuelta por ID, determinismo entre ejecuciones, filtros y privacidad. Origen semántico (`test_semantic_origin.py`).
- Navegador (`analytics.spec.ts`): análisis sin medida confirmada → requisito pendiente → confirmar en Entendimiento → volver y calcular → importe por región y mes → panel de procedencia; sin desbordamiento a 390 px.

### Verificación local de 7A — 2026-11-05

Python 3.12.10. Backend: 292 pruebas, Ruff y mypy strict sin errores, contrato exportado sin diferencias. Web: typecheck, lint, format y build correctos. E2E en serie: 16/16.

## 7B · Comparaciones, ranking y participación (API 0.11)

Recorrido: Análisis → elegir métricas, dimensiones y agrupación temporal → «Comparar y ordenar» (periodo anterior, mismo periodo del año anterior, top N por una métrica, % del total) → «Calcular» → columnas de base, variación, variación %, % del total y posición → cualquier cifra abre «De dónde sale este número».

### Versión de la operación

`analytics.query@2` amplía los parámetros de `@1`; `@1` no cambia (modelo, motor y resultado) y sus planes guardados se ejecutan igual. Catálogo **`analysis-v6`** con los dos descriptores; la interfaz crea siempre `@2`, que sin opciones nuevas calcula las mismas cifras, conteos y `evidence_id` de `value` que `@1`. Una referencia congelada del JSON exacto de `@1`, capturada antes de tocar el motor (`tests/fixtures/phase7_query_v1_golden/`), protege esa equivalencia y no se regenera para hacer pasar una prueba.

| Parámetro nuevo  | Contenido                                                                                  |
| ---------------- | ------------------------------------------------------------------------------------------ |
| `comparisons`    | 0–2 de `previous_period`, `same_period_last_year`; exige `time_grain` y periodo alineado   |
| `change_scale`   | decimales de la variación % (por defecto 2, 0–12), HALF_EVEN                               |
| `ranking`        | `metric_revision_id`, `direction` (`desc` o `asc`) y `top_n` (1–1000); exige una dimensión |
| `share_of_total` | revisiones (de entre las métricas) con % del total; sólo `sum` y `count`                   |
| `share_scale`    | decimales del % del total (por defecto 2, D7), HALF_EVEN                                   |

### Comparaciones

- **El periodo consultado se calcula como en `@1`**: `time_range` filtra antes de agrupar y `counts` significa lo mismo.
- **La base es una segunda pasada sin el filtro de periodo**: aplica los filtros de la consulta que no son de periodo y los de la métrica, y sólo acepta filas de los periodos base que necesita algún grupo (periodo anterior: día −1, semana −7 días, mes, trimestre o año anterior; mismo periodo del año anterior: misma semana ISO del año ISO anterior, mismo mes, trimestre o día).
- **`base_counts`** por métrica y comparación: `input_rows = excluded_by_filters + outside_base_periods + excluded_by_nulls + included_rows` (las filas sin fecha cuentan como fuera de los periodos base).
- **Periodo alineado** (decisión 7B-1): con comparaciones, `time_range` empieza el primer día y termina el último día de un periodo de la granularidad; si no, el plan no es válido (`INVALID_PARAMETERS`, «debe empezar el primer día de un mes»). Sin comparaciones, el periodo parcial sigue permitido.
- **Nunca 0 en lugar de un nulo**: `no_base_data` (el periodo base no tiene filas para la métrica; si el grupo base existe, un conteo vale 0, como en `@1`), `no_counterpart` (29 de febrero, semana 53 o fuera del calendario: no se sustituye por un vecino) y `missing_period` (grupo sin fecha).
- **Variación** (7B-5): absoluta sobre las cifras mostradas (ya cuantizadas, también la media) y porcentual sobre |base|, en `Decimal` con HALF_EVEN. Con base 0 hay variación absoluta, no porcentual (`base_zero`).

### Ranking y participación

- **Top N** dentro de cada periodo (o de todo el resultado). Posiciones 1, 2, 3 sin empates compartidos: dos valores iguales se ordenan por las dimensiones (desempate estable) y la segunda fila lleva **`tied_with_previous: true`**, que forma parte de la evidencia de su posición. Los grupos sin valor en la métrica del ranking no tienen posición. `RankingSummary` declara por periodo los grupos, los que tienen posición, los visibles y los ocultos. Con ranking, las filas se ordenan por periodo y posición.
- **Presupuesto** (7B-3): `RESULT_TOO_LARGE` se aplica después del top N; sin ranking, como en `@1`. La evidencia sólo se calcula para las filas visibles.
- **% del total** (7B-2): sólo `sum` y `count` (planning: `SHARE_NOT_ADDITIVE`; el motor lo comprueba también). El total de cada periodo incluye todos los grupos, **antes** del top N y del presupuesto; cada porcentaje se redondea por separado (D7). `ShareTotal` declara total, grupos, tolerancia (n × media unidad de `share_scale`: 0.025 con 5 grupos a escala 2) y `mixed_signs`. Total 0 o grupo sin valor: nulo (`total_zero`, `value_missing`).

### Evidencia

La dirección de `value` no cambia (misma fórmula que `@1`, sin `detail`). Las cifras derivadas añaden `cell` y su `detail`:

| `cell`                                     | `detail`                                    |
| ------------------------------------------ | ------------------------------------------- |
| `previous_period`, `same_period_last_year` | `comparison`, `base_period`                 |
| `change`                                   | `comparison`, `base_period`                 |
| `change_pct`                               | `comparison`, `base_period`, `change_scale` |
| `share_of_total`                           | `share_scale`                               |
| `rank`                                     | `direction`, `top_n`, `tied_with_previous`  |

`GET /executions/{id}/evidence/{evidence_id}` resuelve cualquier celda y recalcula su dirección con las mismas funciones del motor. `EvidenceView` añade `operation`, `metric_value` y, según la celda, `comparison`, `share`, `share_total`, `rank` y `ranking`.

### API 0.11

Cambios aditivos: `GET /executions/{id}/analysis` devuelve una unión distinguida por `operation` (`AnalysisResult` para `@1`, `AnalysisResultV2` para `@2`); `EvidenceReference` admite `cell` y `detail`; código de problema `SHARE_NOT_ADDITIVE`; `ProcessingConfig.operation_catalog` admite `analysis-v6`. **Sin migración**: todo vive en el artefacto `analysis_result`. **Actualizar desde 0.10 / esquema 0009**: desplegar API y worker juntos (un worker 0.10 no tiene ejecutor para `analytics.query@2`).

### Interfaz

Bloque «Comparar y ordenar» en Análisis. La tabla añade «Posición» (un «=» marca el empate, con la explicación), base, variación, variación % y % del total; con varias métricas, cada columna derivada lleva el nombre de su métrica. Las bases sin valor dicen «sin datos», «sin equivalente» o «sin fecha». Notas bajo la tabla: grupos ocultos por el top N y que el % del total incluye los grupos no visibles, con su tolerancia. El panel de procedencia muestra qué es la cifra, el valor del grupo, el periodo base y sus filas, la fórmula de la variación %, el total y el redondeo de la participación y el ranking con el empate.

### Pruebas de 7B

- Referencia congelada de `@1` (`test_analytics_query_v1_golden.py`): 8 consultas con IDs y ámbito fijos, JSON exacto del artefacto.
- Comparaciones (`test_analytics_comparisons.py`): `@2` sin opciones igual a `@1` en los 8 casos; base fuera del rango; conteos de la base que suman la entrada; filtros de consulta y de métrica en la base; base sin datos nula y conteo 0 si el grupo base existe; 29 de febrero, semana 53 y grupo sin fecha; trimestres, años y ambas comparaciones; HALF_EVEN, base negativa y media cuantizada; alineación; evidencia y determinismo.
- Ranking y participación (`test_analytics_ranking.py`): top N global y por periodo, ascendente y descendente; empates con posiciones distintas e indicador también en la evidencia; grupos sin valor ocultos y contados; total antes del recorte, tolerancia, escala y conteos; total cero, negativos y valores ausentes; sólo métricas sumables; presupuesto antes y después del top N; combinación determinista.
- De punta a punta (`test_analytics_runner.py`) y planning (`test_planning_domain.py`): ranking y participación sobre la v2 tipada con evidencia de cada celda, comparación por día, `SHARE_NOT_ADDITIVE`, periodo no alineado y `@1` que rechaza los parámetros nuevos.
- Navegador (`analytics-compare.spec.ts`): top 3 con «3 =» y grupo oculto, % del total con su procedencia, periodo no alineado rechazado, comparación por día con las filas de la base y sin desbordamiento a 390 px. Las dos E2E de Limpieza (`cleaning.spec.ts`, `cleaning-cast.spec.ts`) tienen ahora 60 s: rondaban el límite de 30 s en un equipo cargado.

### Verificación local de 7B

2026-11-06, Python 3.12.10. Backend: 352 pruebas (60 nuevas en 7B), Ruff y mypy strict sin errores, contrato exportado sin diferencias y `contracts:check` correcto. Web: typecheck, lint, format y build correctos. E2E en serie: 17/17. En la línea base, recién reiniciado el equipo, las dos E2E de Limpieza agotaban su límite de 30 s mientras el servidor terminaba con éxito segundos después; con 60 s pasan (23,6 s y 19,5 s en esta verificación).

## Pendientes para la Fase 8 (resueltos)

Resueltos en la [Fase 8](phase-8.md): el historial de ejecuciones muestra los resultados `analysis_result` con su procedencia, y los gráficos llegan con los dashboards persistidos.
