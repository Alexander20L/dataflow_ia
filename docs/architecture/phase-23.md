# Fase 23 — Cierre de la pestaña Dataset

Estado: **implementada** (API 0.30.0, migración 0023, catálogo de carga `analysis-v13`).
Decisión: [ADR-040](../adr/040-dataset-tab-closure-and-corrections-that-count.md) (modifica el
punto 7 de ADR-039).

## Objetivo

Que la pestaña Dataset diagnostique de verdad, sin IA, y que lo que el usuario corrige en el
Diccionario lo usen las demás etapas:

- **Validez:** valores fuera del rango evidente (porcentajes de 0 a 100, cantidades no
  negativas).
- **Atípicos:** vallas de Tukey (1,5·IQR y 3·IQR), como aviso.
- **Unicidad:** filas repetidas sin contar los identificadores.
- **Clasificación:** columnas dicotómicas, escalas ordinales candidatas y datos personales.
- **Correcciones que cuentan:** la comprensión, la exploración y el dashboard se recalculan con
  ellas; los datos personales no llegan a la IA; los textos «sin dato» declarados crean una
  versión derivada.

## Recorrido

```
carga ─▶ inspección v2 ─▶ GET /versions/{id}/inspection
      └▶ comprensión v2 (clasificación de Dataset + correcciones) ─▶ exploración ─▶ dashboard ─▶ informe
corrección (rol, naturaleza, datos personales) ─▶ otra comprensión ─▶ exploración ─▶ dashboard ─▶ informe
textos «sin dato» declarados ─▶ null_cleaning ─▶ versión derivada ─▶ table_analysis (como una carga)
                                                                  └▶ inspección, comprensión, investigación…
```

## Piezas

| Pieza                                          | Dónde                                                            |
| ---------------------------------------------- | ---------------------------------------------------------------- |
| Reglas puras (`dataset-inspection-v2`)         | `modules/inspection/domain.py`                                   |
| Cálculo con Polars y `classify_table`          | `modules/inspection/engine.py`                                   |
| Detalle de las correcciones (0023)             | `modules/inspection/infrastructure.py`, migración 0023           |
| Roles y escalas con correcciones               | `modules/comprehension/domain.py` (`classified_roles`, `scales`) |
| Comprensión v2 y recálculo                     | `bootstrap/comprehension_job.py`                                 |
| Textos nulos → versión derivada                | `bootstrap/null_cleaning_job.py`, `cleaning/steps.py`            |
| Análisis de la versión derivada como una carga | `bootstrap/services.py`, `ingestion/plans.py`                    |
| Procedencia de una carga derivada              | `bootstrap/loads.py`                                             |
| Interfaz                                       | `apps/web/src/features/dataset/*`                                |

## API

- `GET /api/v1/versions/{id}/inspection` (`getInspection`): la inspección v2 añade, por columna,
  `dichotomous`, `domain`, `ordinal_candidate`, `personal` y `numeric.outliers`; en el resumen,
  `duplicate_rows_without_ids`, `identifier_columns` y `personal_columns`; y, en los textos de
  «sin dato», sus `variants`. El diccionario añade la decisión sobre datos personales y los
  textos declarados. La vista añade `recalculation` (último recálculo provocado por el
  Diccionario: estado, tipo y, si creó una versión derivada, su identificador).
- `POST /api/v1/versions/{id}/dictionary` (`annotateColumn`) admite además `null_tokens` y
  `personal`. Devuelve la vista con el recálculo encolado.
- `GET /api/v1/versions/{id}/comprehension`: `business-comprehension-v2` añade
  `corrected_columns` y `personal_columns`; una escala indicada por el usuario lleva
  `order_source: "user"`.

## Pruebas

- `tests/test_phase23_dataset.py`:
  - reglas puras de nombres, rangos, escalas y datos personales;
  - roles y escalas de la comprensión con correcciones, y datos personales fuera del contexto
    de la IA;
  - cifras conocidas con 40 estudiantes (porcentaje fuera de rango, horas negativas, un atípico,
    «N/A» en dos escrituras y una fila repetida salvo el identificador);
  - recálculo tras corregir `ciclo` y descartar los datos personales de `nombre`, y versión
    derivada al declarar «N/A», analizada entera y con las correcciones heredadas.
- `test_migration_0023.py`: ida y vuelta, `compare_metadata`, inmutabilidad y downgrade
  bloqueado con datos.
- La E2E `dataset.spec.ts` añade el recorrido de la Fase 23: avisos, fila enlazada desde
  Calidad, escala ordinal confirmada con recálculo y versión derivada abierta desde el
  Diccionario.

## Limitaciones

- Las versiones anteriores a la fase conservan su inspección v1 y su comprensión v1.
- Los rangos esperados sólo se deducen del nombre de la columna.
- Los datos personales se reconocen por reglas: el usuario puede confirmarlos o descartarlos.
- El análisis automático de la carga (`analytics.automatic@1`) se calcula antes de la
  inspección y no usa las correcciones; las usan la comprensión y lo que depende de ella
  (exploración, dashboard e informe).
- Las columnas calculadas a partir de otras se detectarán en la pestaña Comprensión.
