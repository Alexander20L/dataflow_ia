# Fase 24 — Pestaña Comprensión

Estado: **implementada** (API 0.31.0, migración 0024, catálogo de carga `analysis-v13`).
Decisión: [ADR-041](../adr/041-comprehension-tab-grain-formulas-and-validations.md) (modifica
ADR-036).

## Objetivo

Que la comprensión diga, con evidencia y en su propia pestaña:

- **qué representa cada fila** (grano y entidad);
- **qué columnas son fórmulas de otras** (sumas ponderadas, productos y umbrales), para no
  presentarlas como hallazgos;
- **cómo se relacionan las columnas**, separadas en estructurales, estadísticas y temporales, con
  estado (pendiente, validada, rechazada o ambigua);
- **qué significa cada columna**, con la confianza de la IA y la posibilidad de escribirlo;
- y que todo eso siga siendo útil sin IA.

## Recorrido

```
carga ─▶ comprensión v3 (grano, fórmulas, misma entidad, periodo, medidas) ─▶ exploración ─▶ dashboard ─▶ informe
validar / rechazar una relación ─▶ otra exploración (con las valoraciones) ─▶ dashboard ─▶ informe
significado escrito por el usuario ─▶ column_meanings (metadato; lo heredan las versiones siguientes)
```

## Piezas

| Pieza                                               | Dónde                                                                   |
| --------------------------------------------------- | ----------------------------------------------------------------------- |
| Contratos v3                                        | `modules/comprehension/contracts.py`                                    |
| Grano, medidas, estados, confianza (reglas puras)   | `modules/comprehension/domain.py`                                       |
| Sumas ponderadas, umbrales y misma entidad (Polars) | `modules/comprehension/measures.py`                                     |
| Significados del usuario (0024)                     | `modules/comprehension/infrastructure.py`, migración 0024               |
| Comprensión v3, vista y significados                | `bootstrap/comprehension_job.py`                                        |
| Exploración con las valoraciones vigentes           | `bootstrap/exploration_job.py` (`request_exploration_update`)           |
| Prompt con confianza (v2)                           | `modules/copilot/comprehension.py`, `copilot/contracts.py`              |
| Interfaz                                            | `apps/web/src/features/comprehension/*`, pestaña en `csv-workspace.tsx` |

## API

- `GET /api/v1/versions/{id}/comprehension` (`getComprehension`): `business-comprehension-v3`
  añade `grain`, `formulas`, `measures`, `dimensions` y `period`; cada relación, su `family` y su
  `state`; cada significado, su `confidence`, `source` y `confirmed`. La vista añade
  `recalculating` mientras se rehacen la exploración y el dashboard.
- `POST /api/v1/versions/{id}/comprehension/feedback` (`judgeRelationship`): sin cambios en la
  petición; desde esta fase rehace la exploración, el dashboard y el informe.
- `POST /api/v1/versions/{id}/comprehension/meanings` (`describeColumn`), nuevo: significado
  escrito o confirmado por el usuario.

## Pruebas

- `tests/test_phase24_comprehension.py`:
  - reglas puras: grano, nombres de código, estados, fuentes heredadas de una fórmula, medidas
    nunca sumadas sin demostrar, confianza limitada y significados del usuario;
  - cifras conocidas con 30 estudiantes: la fórmula exacta de `promedio`, el umbral de
    `aprobado`, `tutor_id` ↔ `tutor` como misma entidad y ninguna fórmula en la exploración;
  - rechazar una relación rehace la exploración y el dashboard y se hereda; los significados del
    usuario se heredan y no recalculan nada;
  - con la IA falsa, cada significado lleva su confianza.
- `test_migration_0024.py`: ida y vuelta, `compare_metadata`, inmutabilidad y downgrade
  bloqueado con datos.
- E2E: `comprehension.spec.ts` (grano, fórmulas, relaciones estructurales y significado propio) y
  `analysis.spec.ts` (la comprensión en su pestaña y una relación rechazada).

## Limitaciones

- Las versiones anteriores a la fase conservan su comprensión v1 o v2.
- No se detectan fórmulas no lineales (cocientes, porcentajes, sumas con constante).
- El grano sale de la clave única; con varias claves candidatas se usa la primera.
- Un significado escrito por el usuario no cambia ningún cálculo.
