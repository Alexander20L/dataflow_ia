# Fase 28 — Criterio analítico

Estado: **implementada** (API 0.36.0, sin migración, catálogo de carga `analysis-v13`).
Decisión: [ADR-046](../adr/046-analytic-criteria-date-role-and-rates.md). Parte de la
[Fase 23](phase-23.md) (inspección), la [Fase 24](phase-24.md) (comprensión), la
[Fase 25](phase-25.md) (investigación) y la [Fase 26](phase-26.md) (dashboard).

## Objetivo

Que el análisis automático razone como un analista: no leer una fecha descriptiva como línea de
tiempo, no comparar grupos de pocos registros, analizar como tasa las columnas de dos valores y
no repetir el mismo hallazgo.

## Recorrido

```
carga ─▶ inspección v3 (date_role, escalas de valoración)
      ─▶ comprensión v4 (periodo o fechas que describen al registro)
      ─▶ investigación v3 (explore-v3: rate, cohort; relevance-v2: mínimo de 10 por grupo)
      ─▶ dashboard (tasa como indicador en %, tasa por grupo en barras, cohorte)
      ─▶ informe (conclusión y recomendación de la tasa)
```

## Piezas

| Pieza                                              | Dónde                                         |
| -------------------------------------------------- | --------------------------------------------- |
| Regla `date-role-v1` (pura, compartida)            | `platform/timing.py`                          |
| Registros por mes y por año                        | `modules/comprehension/measures.py`           |
| Comprensión v4 (`dated_attributes`)                | `bootstrap/comprehension_job.py`, `contracts` |
| Inspección v3 (`date_role`, escalas, no negativas) | `modules/inspection/domain.py`, `engine.py`   |
| Consultas `rate` y `cohort`                        | `modules/exploration/domain.py`, `engine.py`  |
| Plan sin repetidos y `relevance-v2`                | `modules/exploration/plan.py`                 |
| Operación `exploration.explore@3`                  | `bootstrap/exploration_job.py`, `services.py` |
| Indicador de tasa y gráficos                       | `modules/delivery/dashboard.py`               |
| Conclusión de la tasa                              | `modules/delivery/report.py`                  |
| Fechas que describen al registro (Comprensión)     | `apps/web/src/features/comprehension/`        |
| Papel de la fecha (Dataset › Columnas)             | `apps/web/src/features/dataset/columns.tsx`   |

## Reglas

- **Papel de la fecha**: atributo si hay una clave única que no incluye las columnas del periodo y
  la mediana de registros por mes observado es menor que 2; si no, eventos.
- **Mínimo por grupo**: 10 registros en promedios, medianas y tasas; las sumas y los conteos no
  lo necesitan.
- **Tasa**: la categoría menos frecuente de una columna de dos valores; por grupo, relevante con
  10 puntos o más de diferencia, secundaria con 5 o más, descartada por debajo.
- **Cohorte**: registros por año de la fecha atributo, en orden de año.

## API

Sin rutas nuevas. `GET /versions/{id}/comprehension` añade `dated_attributes`;
`GET /versions/{id}/inspection` añade `date_role` y `date_role_reason` a cada columna y el tipo
de rango `rating`; las consultas de la investigación admiten `kind` `rate` y `cohort` con
`target` y `target_value`.

## Interfaz

- Comprensión › Resumen: sección «Fechas que describen al registro» con su motivo y los
  registros por año (en lugar de «Periodo»).
- Dataset › Columnas: el papel de cada fecha bajo su rango temporal; el rango esperado de una
  escala de valoración.
- Investigación y Dashboard: los resultados nuevos se muestran con los componentes existentes
  (clase «No concluyente» con su motivo, barras, líneas e indicador con unidad «%»).

## Pruebas

- `apps/api/tests/test_phase28_criteria.py`: reglas puras (papel de la fecha, escalas, mínimo
  por grupo, tasas, firmas equivalentes) y un padrón de 100 empleados con cifras conocidas (9 %
  de bajas; 25 % en un área y 5 % en las demás), más una serie mensual de ventas que sigue siendo
  serie.
- `apps/web/tests/e2e/criteria.spec.ts`: Comprensión muestra la fecha que describe al registro
  y el Dashboard la tasa por área.
- Pruebas de las Fases 23–25 actualizadas a las nuevas versiones de reglas.

## Limitaciones

- La tasa sólo se calcula para columnas de dos valores (no para categorías con más valores).
- Con la IA de pruebas el dashboard destaca una sola cifra; con la IA real o sin IA, la tasa
  total aparece entre los indicadores.
- Las versiones ya analizadas no se recalculan: hay que volver a cargar el archivo.
