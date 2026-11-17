# Fase 21 — Dashboard adaptado a los datos

Estado: **implementada** (API 0.28.0, migración 0021, catálogo de carga `analysis-v13`).
Decisión: [ADR-038](../adr/038-adapted-dashboard-and-finding-feedback.md).

## Objetivo

Que el dashboard se adapte a cada conjunto de datos y que el usuario pueda decir qué hallazgos le
sirven, sin que la IA escriba cifras ni código: la IA elige secciones, orden y tipo de gráfico de
un catálogo cerrado; Python valida cada elección según la forma del elemento; la interfaz pone los
datos publicados.

## Recorrido

```
carga ─▶ comprensión ─▶ exploración ─▶ dashboard ─┐
      └▶ investigación ─────────────────────────────┴▶ informe (el último)
marca «sí va / no va» ─▶ informe nuevo (el anterior se conserva)
```

## Catálogo de gráficos (`dashboard-design-v1`)

| Gráfico   | Cuándo es compatible                                             |
| --------- | ---------------------------------------------------------------- |
| `kpi`     | Una cifra publicada del elemento (por su evidencia)              |
| `bar`     | Una cifra por grupo, al menos dos grupos                         |
| `line`    | Una serie en el tiempo (hallazgos con serie mensual)             |
| `heatmap` | Dos dimensiones y una sola cifra (tablas cruzadas)               |
| `pie`     | Partes de un total que se puede sumar: de 2 a 6, sin negativos   |
| `table`   | Siempre (texto del hallazgo y sus cifras, o filas del resultado) |

La IA no puede ocultar hallazgos: lo que no coloca va a «Otros hallazgos». Sin IA, las reglas
diseñan «Indicadores clave», «Hallazgos principales» y «Exploración guiada».

## Valoración

`POST /versions/{id}/dashboard/feedback` con `item` y `verdict` (`keep`, `drop` o `none`). Tabla
`finding_feedback` (inmutable, vale la última marca). El dashboard publicado no cambia: la vista
trae `arrangement` (fijados arriba, descartados aparte) y cada marca encola una versión nueva del
informe; mientras se genera, `GET /report` sirve la anterior con `updating: true`.

## API e interfaz

`GET /versions/{id}/dashboard`: `queued`, `running`, `ready` (diseño, decisiones, `arrangement`, y
los hallazgos y resultados que cita) o `failed`. Panel «Dashboard adaptado» arriba, después del
resumen: indicadores, gráficos ECharts, botones «Sí va» / «No va», descartados recuperables y
elecciones de diseño rechazadas. Etapa «Diseño del dashboard» en el progreso.

## Pruebas

`tests/test_phase21_dashboard.py`: compatibilidad de gráficos por forma, validación del diseño de
la IA (repetidos, incompatibles, inventados, fuera de catálogo, evidencias ajenas, completado),
textos sin cifras propias, marcas que fijan y apartan, informe que sigue el dashboard y las
marcas, recorrido con IA falsa (informe único, marcas que encolan una sola versión nueva, retirar
marcas) y sin IA. `tests/test_migration_0021.py`. E2E `analysis.spec.ts`.
