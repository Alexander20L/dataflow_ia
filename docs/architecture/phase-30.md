# Fase 30 — Interfaz que se entiende sin leer

Estado: **implementada** (API 0.38.0, sin migración, catálogo de carga `analysis-v13`).
Decisión: [ADR-048](../adr/048-clear-interface-business-names.md). Parte de la
[Fase 29](phase-29.md).

## Objetivo

Que cada pestaña se entienda de un vistazo: lo importante en tarjetas con iconos, nombres de
negocio y cifras grandes; lo técnico plegado. Los cálculos no cambian.

## Piezas

| Pieza                                                   | Dónde                                                  |
| ------------------------------------------------------- | ------------------------------------------------------ |
| Tema y nombres cortos de la IA (prompt v5)              | `modules/copilot/comprehension.py`, `contracts.py`     |
| Validación de los nombres (`SHORT_WORDS`)               | `modules/comprehension/domain.py` (`accept_ai`)        |
| Categoría contada de una tasa (`least_frequent`)        | `modules/comprehension/measures.py`                    |
| Comprensión v6 (`theme`, `labels`, `label`, `counted`)  | `bootstrap/comprehension_job.py`                       |
| Resumen de Comprensión en tarjetas e iconos por reglas  | `apps/web/src/features/comprehension/summary.tsx`      |
| Plan de investigación en tarjetas y textos de negocio   | `apps/web/src/features/investigation/` (`humanize.ts`) |
| Evidencia discreta y cabecera técnica plegada (Informe) | `apps/web/src/features/report/report-tab.tsx`          |

## API

- `GET /versions/{id}/comprehension` añade `theme` y `labels` (columna → nombre corto), y el
  objetivo añade `label` y `counted`.
- Sin rutas nuevas; `POST /versions/{id}/comprehension/target` acepta las versiones v5 y v6.

## Pruebas

- `apps/api/tests/test_phase30_clear_names.py`: validación de los nombres (cifras, palabras,
  columnas inventadas), categoría contada con la regla de la investigación y recorrido con la IA
  falsa.
- E2E: `analyst.spec.ts` (tarjetas del objetivo y cambio con un clic), `investigation.spec.ts` y
  `analysis.spec.ts` (plan en tarjetas).

## Limitaciones

- Sin IA no hay tema ni nombres cortos: las tarjetas usan los nombres de columna.
- Los iconos se eligen por reglas sobre el nombre de la columna.
- El PDF del informe no cambia.
