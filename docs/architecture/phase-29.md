# Fase 29 — Analista con objetivo

Estado: **implementada** (API 0.37.0, migración 0028, catálogo de carga `analysis-v13`).
Decisión: [ADR-047](../adr/047-analysis-target-factors-and-significance.md). Parte de la
[Fase 28](phase-28.md) (criterio analítico), la [Fase 24](phase-24.md) (comprensión) y la
[Fase 25](phase-25.md) (investigación).

## Objetivo

Que el análisis se pregunte qué importa en el archivo, qué factores lo explican y si esos
factores son reales: con su prueba estadística, corregida por comparaciones múltiples, y
comprobados con otras variables. La IA aporta el razonamiento de negocio y el motor lo comprueba.

## Recorrido

```
comprensión v5 ─▶ objetivo (usuario › IA › reglas) + variables derivadas (antigüedad, cuartiles)
investigación v4 (explore-v4)
  ├─ tasa del objetivo
  ├─ factor por cada dimensión y variable derivada ─▶ intervalo 95 % + prueba (chi² / Kruskal-Wallis)
  │     └─ si es interesante: stratified con hasta 2 variables de control ─▶ se mantiene / se atenúa / se explica
  └─ resto del plan (rankings, cohortes, atípicos…)
fin ─▶ Benjamini-Hochberg sobre todas las pruebas (relevance-v3) ─▶ dashboard e informe
elegir objetivo (POST …/comprehension/target) ─▶ comprensión ─▶ investigación ─▶ dashboard ─▶ informe
```

## Piezas

| Pieza                                                     | Dónde                                                   |
| --------------------------------------------------------- | ------------------------------------------------------- |
| Estadística en Python puro                                | `modules/exploration/statistics.py`                     |
| Objetivo, candidatos y variables derivadas (reglas puras) | `modules/comprehension/domain.py`                       |
| Comprensión v5 y elección del usuario                     | `bootstrap/comprehension_job.py`                        |
| Objetivo elegido (migración 0028)                         | `modules/comprehension/infrastructure.py`               |
| Catálogo con objetivo, validación de factor y control     | `modules/exploration/domain.py`                         |
| Variables derivadas, factor y comprobación (motor)        | `modules/exploration/engine.py`                         |
| Plan con objetivo, `relevance-v3` y Benjamini-Hochberg    | `modules/exploration/plan.py`, `investigator.py`        |
| Operación `exploration.explore@4`                         | `bootstrap/exploration_job.py`, `services.py`           |
| Prompts de la IA (comprensión v4, propuestas v3)          | `modules/copilot/comprehension.py`, `exploration.py`    |
| IA obligatoria                                            | `platform/config.py` (`require_ai`), `app.py`, `worker` |
| Objetivo y aviso de IA (interfaz)                         | `apps/web/src/features/comprehension/`                  |

## Reglas

- **Objetivo**: el del usuario si sigue siendo válido; si no, el de la IA si es válido; si no, una
  columna de dos valores con nombre de resultado; si no, la medida principal (monetaria, aditiva).
- **Factor relevante**: ≥ 10 puntos (tasa) o ≥ 30 % de diferencia relativa (promedio) entre los
  grupos con al menos 10 registros, con p < 0,05 y, al final, q < 0,05.
- **Control**: diferencia residual / observada ≥ 2/3 «se mantiene», ≥ 1/3 «se atenúa», menos «se
  explica por la variable de control».
- **Antigüedad**: años hasta la fecha más reciente de la columna, en cuatro tramos.

## API

- `POST /versions/{id}/comprehension/target` (`chooseTarget`): `{column, value?}`; sin columna
  vuelve al propuesto. Errores: `TARGET_INVALID` (422), `TARGET_NOT_SUPPORTED` (409, versiones
  anteriores a la Fase 29).
- `GET /versions/{id}/comprehension` añade `target`, `target_candidates` y `derived`.
- Los resultados de la investigación añaden `test` (prueba, valor p y q, tamaño del efecto) y
  `control` (variable, diferencias y veredicto); los criterios, `significance` y `control`.

## Interfaz

- Comprensión › Resumen: «Qué intenta explicar el análisis», con su origen, motivo, variables
  derivadas y un selector para cambiarlo o volver al propuesto.
- Todas las pestañas: aviso «Este análisis se hizo sin IA» con su motivo cuando la IA no participó.
- Investigación: los criterios «Significancia estadística» y «Comprobación con otra variable» en
  cada evidencia; las tablas muestran los intervalos.

## Pruebas

- `apps/api/tests/test_phase29_target.py`: distribuciones contra valores de referencia, pruebas y
  Benjamini-Hochberg; objetivo y variables derivadas; factor con intervalos y prueba; diferencia
  explicada por la antigüedad y diferencia que se mantiene; recorrido completo con una plantilla
  de 300 personas (antigüedad y área relevantes, comprobación, cambio de objetivo heredado por la
  siguiente carga); IA obligatoria.
- `apps/api/tests/test_migration_0028.py`.
- `apps/web/tests/e2e/analyst.spec.ts`; la prueba E2E de la Fase 28 ya no espera la tasa por área
  (no es significativa).

## Limitaciones

- Con muestras pequeñas casi todo es «no concluyente»: el sistema lo dice en vez de inventar.
- La comprobación usa estandarización indirecta con una sola variable de control a la vez.
- La categoría contada de una tasa se puede fijar por la API; la interfaz sólo elige la columna.
- Las versiones ya analizadas no se recalculan: hay que volver a cargar el archivo.
