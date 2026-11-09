# Fase 15 — Analizar con criterio

Estado: **implementada** (15A y 15B, API 0.22.0, catálogo `analysis-v12`, sin migración).
Decisión: [ADR-032](../adr/032-automatic-analysis-plan.md). Plan general en [Fase 14](phase-14.md).

## Objetivo

Pasar de describir el archivo a analizarlo: elegir los indicadores y comparaciones relevantes,
calcularlos con evidencia y explicar qué se omitió y por qué, sin ninguna configuración.

## Recorrido

```
Subida ─▶ read ─▶ understanding.profile@4 ─▶ quality.evaluate@3 ─▶ analytics.automatic@1
                                                                     │
                     interpretación v2 ─▶ plan automatic-plan-v1 ─▶ motor de analytics.query@2
                                                                     │ (métricas virtuales)
                                                                     ▼
                                    hallazgos con evidencia (automatic-analysis-v1)
```

## Plan analítico automático (`planning/automatic.py`, `automatic-plan-v1`)

Puro: recibe la interpretación, los valores distintos por columna y el número de filas.

| Análisis           | Requisito                                                     | Si no se cumple                   |
| ------------------ | ------------------------------------------------------------- | --------------------------------- |
| Evolución mensual  | Eje temporal y medida sumable (importes antes que cantidades) | Omitido con motivo                |
| Interanual         | Meses presentes en dos años consecutivos                      | «No hay meses presentes…»         |
| Desglose           | Dimensión con 2–50 grupos e identidad única (máx. 4)          | Identidad contradictoria o límite |
| Promedio ponderado | `importe = cantidad × precio` comprobado                      | Sólo promedio simple              |
| Estacionalidad     | 24 meses seguidos                                             | «Hacen falta 24 meses seguidos»   |
| Anomalías          | Al menos 6 meses                                              | «No bastan para distinguir…»      |

Como máximo 12 análisis por carga; el plan registra aceptados y omitidos con su motivo y un costo
estimado (`filas × análisis`).

## Ejecución (`analytics.automatic@1`, `automatic-analysis-v1`)

- El subproceso de analytics interpreta la tabla, planifica y prepara una representación tipada en
  memoria (medidas decimales y el periodo como fecha del primer día del mes).
- Evolución, comparación con el mes anterior e interanual, participación y ranking usan el **motor
  de `analytics.query@2`** con métricas virtuales (identificador determinista, sin revisiones
  guardadas). La consulta completa se guarda en `queries`.
- Concentración (3 mayores, HHI), promedio ponderado (Σ importe ÷ Σ cantidad), estacionalidad
  (media del mes ÷ media mensual × 100) y anomalías (|valor − mediana| > 3 × 1,4826 × MAD, con la
  dimensión **asociada** de mayor desvío) se calculan con Decimal exacto.
- La comparación interanual suma sólo los meses con dato en ambos años.
- Cada cifra tiene una evidencia (`evidence`) con método y entradas; los textos usan formato
  español y nunca afirman causas.

API: `GET /versions/{id}/automatic-analysis` y `GET /versions/{id}/automatic-analysis/evidence/{evidence_id}`
(404 `AUTOMATIC_ANALYSIS_NOT_AVAILABLE` en versiones anteriores; no se recalculan).

## Interfaz

«Hallazgos» aparece antes del dashboard descriptivo: cada hallazgo con su texto, cifras exactas,
gráfico, cobertura y notas; «Análisis omitidos» y «Cómo se eligieron los análisis» en desplegables.
Sin botones.

## Aceptación con el dataset sintético

Evolución mensual y desglose por producto priorizados; interanual con 11 meses comparables
(+39,2 %); Laptop concentra el 62 % de Revenue (concentración alta); precio medio ponderado
267,26 frente a un promedio simple de 286,18; 2024-10 como mes atípico asociado a
Product = Monitor y Region = Norte; clientes y estacionalidad omitidos con su motivo. Las cifras se
recalculan de forma independiente en `tests/test_phase15_automatic_analysis.py`.

## Pendiente

- La explicación IA (C2) sigue explicando el dashboard; usar los hallazgos es parte de la Fase 16.
- El periodo derivado vive en memoria: las métricas guardadas de `analytics.query@*` no lo usan.
