# Fase 16 — Investigar de forma autónoma

Estado: **implementada** (16A y 16B, API 0.23.0, sin migración; catálogo de carga `analysis-v12`).
Decisión: [ADR-033](../adr/033-bounded-investigation-and-ai-proposals.md). Plan general en
[Fase 14](phase-14.md) (D1 y D2).

## Objetivo

Seguir los hallazgos de la Fase 15 sin intervención: preguntar «¿qué hay detrás?» de un mes
atípico, de una variación interanual o de un grupo dominante, con un ciclo acotado en el que la IA
propone y Python valida y calcula.

## Recorrido

```
carga (analysis-v12) ─▶ hallazgos (analytics.automatic@1)
        │ publicado
        ▼
trabajo «investigation» (cola, 1 intento)
  iteración 1  reglas ───────────────▶ analytics.followup@1 ─┐
  iteración 2–3 IA propone ▶ Python valida ▶ analytics.followup@1 ─┤
  final        IA explica (sólo {{evidence:id}}) ◀────────────────┘
```

## Catálogo de seguimientos (`investigation-followup-v1`)

| Tipo              | Pregunta                                                        | Requiere         |
| ----------------- | --------------------------------------------------------------- | ---------------- |
| `month_by_group`  | En un mes, qué grupos se apartan de su mediana mensual          | dimensión, mes   |
| `change_by_group` | Qué grupos explican la variación interanual (meses comparables) | dimensión, año   |
| `group_evolution` | Cómo evolucionó un grupo y cuánto pesa en el total              | dimensión, grupo |

La medida es siempre la del plan. Las dimensiones son las agrupaciones aceptadas por el plan; una
omitida (p. ej. `Customer` con dos nombres) se rechaza con el motivo del plan.

## Reglas (iteración 1)

- Mes atípico → `month_by_group` por las dos primeras agrupaciones.
- Comparación interanual → `change_by_group` por las dos primeras agrupaciones.
- Grupo principal de la primera agrupación → `group_evolution`.

## Límites (`InvestigationLimits`, guardados con cada investigación)

| Límite                 | Por defecto | Variable                                |
| ---------------------- | ----------- | --------------------------------------- |
| Iteraciones            | 3           | `DATAFLOW_INVESTIGATION_MAX_ITERATIONS` |
| Llamadas a la IA       | 4           | `DATAFLOW_INVESTIGATION_MAX_AI_CALLS`   |
| Tiempo                 | 60 s        | `DATAFLOW_INVESTIGATION_MAX_SECONDS`    |
| Costo                  | US$ 0,05    | `DATAFLOW_INVESTIGATION_MAX_COST_USD`   |
| Consultas              | 12          | —                                       |
| Propuestas por llamada | 4           | —                                       |

El motivo de parada queda en `stopped`. Cada llamada se registra en el consumo de IA (cuenta para
los límites diarios y mensuales existentes).

## Cola

El trabajo `investigation` tiene un solo intento y la cola lo reclama después de cualquier otro
trabajo pendiente (orden: no-fondo primero, luego llegada). Respeta el límite de tres trabajos en
marcha por propietario de la Fase 13C.

## API

`GET /versions/{id}/investigation` (estado `queued`, `running`, `ready` o `failed`, con la
investigación) y `GET /versions/{id}/investigation/evidence/{evidence_id}` (cifras de los
seguimientos y de los hallazgos que cita la explicación). Versiones anteriores: 404
`INVESTIGATION_NOT_AVAILABLE`; siguen con la explicación del dashboard (C2).

## Interfaz

«Investigación» aparece bajo «Hallazgos»: la explicación de la IA con cifras enlazadas, cada
seguimiento marcado «Regla» o «Propuesto por la IA», las propuestas rechazadas con su motivo y
«Cómo se investigó» (motivos, iteraciones, llamadas, costo, límites). Sin botones.

## Aceptación con el dataset sintético

- 2024-10: el mayor desvío por `Product` es Monitor (+85.524,02 frente a su mediana).
- Variación 2024 frente a 2023 (11 meses comparables, +132.714,89): Norte aporta el 75,6 %.
- Laptop reúne el 62,0 % de Revenue del periodo.
- Con el proveedor falso, la IA propone la evolución del segundo producto (aceptada) y repite la
  del principal (rechazada: «Ya se investigó»).

Las cifras se recalculan de forma independiente en `tests/test_phase16_investigation.py`.

## Pendiente

- Fase 17: informe automático con hallazgos e investigación primero.
- Las propuestas de interpretación (D1, hipótesis sobre columnas) no se implementan aún.
