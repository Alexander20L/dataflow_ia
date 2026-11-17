# Fase 24B — Mejoras de la pestaña Comprensión y cifras con tres decimales

Estado: **implementada** (API 0.32.0, migración 0025, catálogo de carga `analysis-v13`).
Decisión: [ADR-042](../adr/042-comprehension-improvements-and-display-decimals.md). Completa la
[Fase 24](phase-24.md).

## Objetivo

Cerrar los huecos de la pestaña Comprensión frente a su especificación y hacer legibles las
cifras de todas las presentaciones:

- que la corrección del usuario se conserve **y se use** en las etapas posteriores (el informe);
- que cada interpretación muestre tipo técnico, naturaleza, confianza, justificación y
  procedencia;
- que el usuario pueda marcar una columna como desconocida y llegar al Diccionario para cambiar
  su rol;
- que ninguna presentación muestre más de tres decimales, sin tocar las cifras calculadas.

## Recorrido

```
significado escrito / confirmado / desconocida ─▶ column_meanings (+ column_meaning_marks)
                                               └▶ otra versión del informe (con esos significados)
```

## Piezas

| Pieza                                         | Dónde                                                         |
| --------------------------------------------- | ------------------------------------------------------------- |
| Marca «desconocida» (0025)                    | `modules/comprehension/infrastructure.py`, migración 0025     |
| Significados vigentes (`UserMeaning`)         | `modules/comprehension/domain.py` (`with_user_meanings`)      |
| Justificación de la IA (prompt v3)            | `modules/copilot/comprehension.py`, `copilot/contracts.py`    |
| Significados en el informe                    | `bootstrap/delivery_job.py` (`ReportStep.described`)          |
| Tres decimales en el PDF                      | `modules/delivery/numbers.py`, `modules/delivery/pdf.py`      |
| Tres decimales en la interfaz                 | `apps/web/src/lib/numbers.ts` y los formateadores que lo usan |
| Columnas con tipo, naturaleza y justificación | `apps/web/src/features/comprehension/comprehension-tab.tsx`   |

## API

- `POST /api/v1/versions/{id}/comprehension/meanings` (`describeColumn`) admite `unknown`. Con
  texto o confirmación a la vez responde 422 `MEANING_INVALID`. Desde esta fase pide otra versión
  del informe.
- Cada significado de `GET /api/v1/versions/{id}/comprehension` añade `reason` (justificación de
  la IA) y `unknown`.

## Pruebas

- `tests/test_phase24b_meanings.py`: la marca sustituye al significado de la IA; la justificación
  con cifras se retira; marcar, escribir y heredar por API; el informe se genera con los
  significados del usuario sin recalcular la exploración; la IA falsa justifica cada significado;
  la regla de tres decimales (canónica y española, mitad lejos de cero, sin «-0») y su uso en el
  texto y en el eje del PDF.
- `test_migration_0025.py`: ida y vuelta, `compare_metadata`, último valor, inmutabilidad y
  downgrade bloqueado con datos.
- E2E: `comprehension.spec.ts` (tipo y naturaleza, marcar como desconocida y abrir el
  Diccionario).

## Limitaciones

- Las versiones anteriores a la fase no tienen justificación en sus significados.
- Los valores de la subvista Registros se muestran tal como están en el archivo.
