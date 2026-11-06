# Fase 7 — Análisis de negocio determinista

Se entrega en dos partes: **7A** (API 0.10, esta entrega) añade métricas definidas por el usuario, consultas estructuradas y evidencia direccionable por cifra; **7B** (pendiente) añadirá comparaciones, ranking y participación. [ADR-018](../adr/018-deterministic-business-analysis.md).

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

## Pendiente: 7B

Traspaso para el chat que implementará la 7B, en esta misma rama (`feat/fase-7-analisis`, sin merge a `develop` hasta terminarla).

### Decisiones ya aprobadas que le aplican

- **D7 · participación**: `share_scale` por defecto **2** (porcentaje), HALF_EVEN, fijado en el plan como `avg_scale`. Cada porcentaje se redondea por separado (sin método del mayor resto); la suma puede desviarse hasta **n × 0,005** puntos y esa tolerancia se declara en el resultado.
- **D9 · evidencia**: `evidence_id` = hash canónico de la dirección completa; dimensiones con la celda canónica de la Fase 6 y `{"missing": true}` para el grupo sin valor. Las cifras nuevas (comparación, participación, posición) deben ser direccionables igual.
- **Desempate estable**: por todas las dimensiones en el orden declarado, después el periodo, con valores tipados y nulos al final (el orden actual de `run_query`).
- D1 (Polars + aritmética exacta en Python), D4/D5 (requisitos y unidades), D6 (nulos excluidos, grupo «(sin valor)»), D8 (semanas ISO, fecha de negocio) y D10 (presupuesto) siguen vigentes.

### Plan de etapas

| Etapa                           | Contenido                                                                                                                                                                | Archivos                                                                 |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| **B1. Comparaciones**           | Periodo anterior y mismo periodo del año anterior, por grupo temporal. Un periodo sin datos da un valor nulo con indicador, no 0. Variación nula si la base es 0 o nula. | `analytics/{contracts,engine}.py`, `tests/test_analytics_comparisons.py` |
| **B2. Ranking y participación** | Top N con desempate estable por las dimensiones. `share_of_total` dentro de cada grupo temporal (o del total si no hay tiempo) con la escala y la tolerancia declaradas. | `analytics/engine.py`, `tests/test_analytics_ranking.py`                 |
| **B3. API e interfaz**          | Parámetros nuevos (versión de la operación según el cambio), API 0.11.0, columnas de comparación y participación en la tabla y en el panel de evidencia; E2E.            | `features/analytics/*`, `tests/e2e/analytics-compare.spec.ts`            |
| **B4. Documentación**           | Esta sección convertida en «7B», ADR-019.                                                                                                                                | —                                                                        |

### Lo descubierto en 7A que afecta a 7B

1. **Versión de la operación**: `QueryParameters` usa `extra="forbid"` y los planes guardan los parámetros completos. Añadir `comparison`, `ranking` o `share_of_total` cambia lo que hace la operación: lo coherente con el versionado es `analytics.query@2` (con `analytics.query@1` intacta y sus resultados reproducibles), no ampliar `@1`.
2. **El periodo filtra antes de agrupar**: `time_range` se convierte en filtros `gte`/`lte` sobre la columna temporal y excluye esas filas (contadas en `excluded_by_filters`). Las comparaciones necesitan filas **fuera** del rango (periodo anterior, año anterior): habrá que calcular la base de comparación sin ese filtro y documentar qué cuenta cada métrica.
3. **Grupos**: un grupo sólo existe si alguna métrica tiene filas incluidas. Comparar con un periodo que no existe como grupo debe dar nulo con indicador; la participación debe usar el total **antes** de recortar por ranking o por presupuesto.
4. **Celdas de evidencia**: `EvidenceReference.cell` es hoy `Literal["value"]`. Para comparación y participación conviene añadir valores (`previous_period`, `same_period_last_year`, `change`, `share_of_total`, `rank`) sin cambiar el `evidence_id` de `value`.
5. **Media en float de Polars**: cualquier cociente (variación, participación) debe hacerse en `Decimal` con la escala del plan.
6. **Presupuesto**: `RESULT_TOO_LARGE` cuenta todos los grupos antes de cualquier recorte; con ranking, decidir si el límite se aplica antes o después del top N (recomendación: después, y declararlo).
7. **Interfaz**: el historial de ejecuciones (`execution-panel.tsx`) todavía no muestra resultados `analysis_result`; sólo la etapa Análisis los muestra. Los gráficos siguen en la Fase 8.
