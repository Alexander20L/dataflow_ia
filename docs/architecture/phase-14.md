# Fase 14 — De dashboard descriptivo a analista autónomo

Estado: **Fase 14 implementada** (14A y 14B, API 0.21.0, catálogo `analysis-v11`, sin migración).
Decisión: [ADR-031](../adr/031-analytical-interpretation-and-quality.md). Plan de las Fases 15–18 y
decisiones D1–D4 aceptadas con la opción recomendada. Parte del análisis previo a la Fase 13 «DataFlow AI: de dashboard descriptivo a analista
autónomo», contrastado con el código de `develop` tras las Fases 13–13C.

## Diagnóstico confirmado en el código (API 0.20)

- `understanding.profile@3` (`automatic-interpretation-v1`) asigna roles por nombre y tipo:
  identificadores sólo por tokens del nombre (`id`, `code`, `sku`…), así que `Customer` no lo es.
- El dashboard (`understanding/overview.py`) calcula promedio, mínimo y máximo de las **tres primeras
  columnas numéricas por posición**: `Year` se promedia.
- Un `Month` textual se trata como categoría ordenada por frecuencia, no cronológicamente; no hay
  periodos compuestos (`Year` + `Month`).
- Los gráficos cuentan **registros**; no hay volumen, claves de negocio, relaciones entre columnas ni
  aditividad. La calidad (`csv-quality-v1`) cuenta vacíos, duplicados exactos y espacios.

Reutilizable: `analytics.query@1..3` (por mes, top N, % del total, variación, semiaditivas, cortes,
evidencia por cifra), los motores de cleaning, `csv-quality-v2`, la cola con fencing y reintentos
(13C) y la explicación IA verificada (C2, ADR-029).

## Ya resuelto (no se repite)

| Del análisis                                         | Resuelto en                                          |
| ---------------------------------------------------- | ---------------------------------------------------- |
| Informar qué tablas se procesaron y cuáles no        | 13B para Excel (`source_selection`)                  |
| Trabajos antiguos no sustituyen resultados recientes | Cada versión tiene su dashboard; cola en orden (13C) |
| Reutilizar la cola y el fencing                      | 13C: tres en marcha por propietario, sin rechazos    |
| Resultados útiles con la IA desactivada              | IA `auto`; su fallo no bloquea (13B, ADR-029)        |
| Rechazar referencias falsas de la IA                 | Verificador de C2                                    |
| Sin configuración obligatoria                        | Fase 13 (ADR-026)                                    |

## Decisiones (aceptadas con la opción recomendada)

- **D1 · Papel de la IA.** Podrá **proponer** hipótesis de interpretación e investigaciones con un
  esquema cerrado, siempre validadas por Python contra el catálogo y la evidencia calculada, sin
  cifras propias y sin activar nada fuera del catálogo. **No antes de la Fase 16**; las Fases 14–15
  usan sólo reglas. Requiere un ADR que modifique el principio 6 de ADR-026 y `CLAUDE.md`.
- **D2 · Coordinador.** No se recrea `automation` (prueba AST). En la Fase 16 se crea el módulo
  `investigation`, sobre la cola y el fencing actuales, sin otro sistema de ejecución.
- **D3 · Nada destructivo ni ambiguo se aplica.** Lo que alteraría registros (rellenar,
  deduplicar, excluir, convertir valores ambiguos) sólo se informa con su evidencia. No hay
  «herramientas avanzadas»; el historial y la evidencia son vistas de sólo lectura.
- **D4 · Informes.** Se reintroducen como informe automático en la Fase 17; `reportlab` se mantiene
  hasta entonces.

## Plan por fases (orden del análisis)

| Fase | Objetivo                                                     | Módulos                               | Resultado                                                                                     |
| ---- | ------------------------------------------------------------ | ------------------------------------- | --------------------------------------------------------------------------------------------- |
| 14   | Comprender y comprobar                                       | understanding, quality, prep. técnica | Interpretación útil y advertencias relevantes; dashboard sin errores de criterio evidentes    |
| 15   | Analizar con criterio (hecha, [Fase 15](phase-15.md))        | planning, analytics, dashboard        | Plan automático: indicadores por relevancia, comparaciones válidas, análisis omitidos         |
| 16   | Investigar de forma autónoma (hecha, [Fase 16](phase-16.md)) | `investigation`, copilot, executions  | Ciclo acotado (iteraciones, tiempo, llamadas, presupuesto durable); propuestas IA según D1    |
| 17   | Consolidar la entrega (hecha, [Fase 17](phase-17.md))        | `delivery`, frontend, executions      | Informe automático, progreso y hallazgos primero; destino de tablas sin uso de las Fases 4–10 |
| 18   | Ampliar fuentes                                              | ingestion, adaptadores                | CSV/Excel regionales, varias tablas, cambios de estructura, SQL Server y PDF sin elección     |

Se retira (sin borrar datos): la elección de las tres primeras columnas numéricas, las frecuencias
presentadas como medidas y `drop_nulls` en la propuesta de limpieza de 11A.

Validación transversal: datasets de referencia con resultados esperados, casos donde lo correcto es
abstenerse, monedas mezcladas, periodos incompletos, identidades contradictorias; IA con proveedor
falso y evaluaciones reales presupuestadas.

## Dataset de aceptación

El archivo real aún no está disponible. Mientras tanto se usa uno **sintético** con su misma forma
(`apps/api/tests/fixtures/ventas_mensuales.csv` y el mismo contenido en `.xlsx` para E2E):

- `Year` (2023–2024) y `Month` (nombre del mes en inglés), `Customer` (código), `Customer_Name`,
  `Product`, `Region`, `Units_Sold`, `Price_per_Unit`, `Revenue` = `Units_Sold` × `Price_per_Unit`.
- Ambigüedad deliberada: un `Customer` con dos `Customer_Name` distintos.
- Un mes faltante en 2024 y un atípico de `Units_Sold`.
- Sin columna de moneda.

Cuando llegue el archivo real se añade (anonimizado si hace falta) como segunda referencia; los
resultados esperados del sintético no cambian.

## Etapa 14A — backend (implementada)

1. **`understanding.profile@4`** (catálogo `analysis-v11`, regla `automatic-interpretation-v2`):
   - Roles `identifier`, `dimension`, `measure`, `time`, `text`, `empty` con evidencia. Identificador
     también por unicidad y forma de código, no sólo por nombre.
   - **Tiempo compuesto**: `Year` (enteros 1900–2100) + `Month` (1–12 o nombre en español/inglés)
     forman un periodo mensual; `Year` y `Month` nunca son medidas.
   - Hipótesis de grano de fila y claves candidatas (unicidad comprobada sobre todo el dataset).
   - Relaciones entre medidas (`A ≈ B × C`) con tolerancia explícita y cobertura.
   - Moneda, unidad y aditividad como `known` / `unknown` / `ambiguous`; nunca se inventan.
   - La derivación del periodo vive en la representación analítica (perfil), no crea versión
     derivada ni aprobación: no se toca la tabla ni el original.
2. **`quality.evaluate@3`** (`automatic-quality-v1`), que juzga la evidencia de la interpretación
   (importa sólo `understanding.contracts`; dependencia nueva y acíclica):
   - Duplicados por clave candidata; identificador con atributos contradictorios
     (`Customer` → varios `Customer_Name`); periodos faltantes o incompletos; valores imposibles
     (unidades negativas, relación rota); atípicos por IQR como observación.
   - Severidad `info` / `warning` / `blocking` y **análisis afectados** (p. ej. limita clientes sin
     bloquear productos).
3. **Dashboard v3** a partir de la interpretación: medidas en vez de columnas por posición, meses en
   orden cronológico, «Registros» sólo para conteos, calidad separada de resultados.
4. `profile@1..3` y `quality.evaluate@1/@2` no cambian (referencias doradas intactas); las nuevas
   cargas usan `@4`/`@3`. Sin migración prevista: los resultados son artefactos de ejecución.

Aceptación 14A con el dataset sintético: contexto comercial y periodo mensual reconocidos; `Year`
no se promedia; ambigüedad de clientes detectada, análisis de clientes limitados y de productos
intactos; relación `Revenue ≈ Units_Sold × Price_per_Unit` registrada; moneda `unknown`.

## Etapa 14B — interfaz (implementada)

- El dashboard muestra «Lectura automática de los datos» (contexto, significado de la fila, periodo
  con meses faltantes, análisis posibles y **análisis limitados** con su motivo) y, aparte de los
  resultados, «Calidad de los datos» con cada hallazgo, su severidad, evidencia, filas de ejemplo y
  análisis afectados. Sin botones ni confirmaciones.
- Los gráficos de una medida dibujan la suma exacta (`amount`) y lo indican; los de conteo dicen
  «registros». Las versiones anteriores siguen mostrando su interpretación v1.
- E2E `analysis.spec.ts` con `fixtures/ventas_mensuales.csv` (el mismo dataset sintético).

## Implementación

| Pieza                      | Dónde                                                                                  |
| -------------------------- | -------------------------------------------------------------------------------------- |
| Interpretación v2          | `understanding/analysis.py` (pura) y contratos en `understanding/contracts.py`         |
| Dashboard v3               | `understanding/overview.py` (`analytical_overview`)                                    |
| Calidad analítica          | `quality/automatic.py` (`assess`) y `AnalyticalQuality` en `QualityReport.analytical`  |
| Pasos                      | `understanding.profile@4`, `quality.evaluate@3` (subproceso de ingesta, modos nuevos)  |
| Serialización de versiones | `profile_json` y `QualityReport.serialized`: `@1–@3` y `quality@1` no cambian de bytes |
| Explicación IA (C2)        | Cifras de los gráficos de medida por `/charts/i/points/j/amount`; prompt sin cambios   |
| Pruebas                    | `tests/test_phase14_analysis.py`, `tests/reference_sales.py`, E2E `analysis.spec.ts`   |

Comprobaciones de `automatic-quality-v1`: AQ-001 clave casi única con repeticiones, AQ-002 código con
varios atributos (bloquea sólo esos análisis), AQ-003 meses faltantes, AQ-004 meses posiblemente
incompletos, AQ-005 periodos no reconocidos, AQ-006 valores imposibles o relación rota, AQ-007
atípicos (Q1 − 3·IQR, Q3 + 3·IQR; observación), AQ-008 varias monedas (bloquea totales).

Limitaciones conocidas: la detección de papeles usa nombres en español e inglés y formas de valor;
un nombre de columna sin pistas deja la medida con aditividad desconocida (no se suma). El periodo se
deriva en el perfil, no como columna de una tabla: las operaciones de `analytics` lo necesitarán como
columna en la Fase 15.
