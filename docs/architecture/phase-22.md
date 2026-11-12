# Fase 22 — Pestaña Dataset

Estado: **implementada** (API 0.29.0, migración 0022, catálogo de carga `analysis-v13`).
Decisión: [ADR-039](../adr/039-dataset-tab-inspection-and-dictionary.md).

## Objetivo

Inspeccionar, perfilar y diagnosticar el archivo en una pestaña propia con seis subvistas:

- **Resumen:** indicadores, metadatos y distribución de las columnas por clasificación.
- **Registros:** filas paginadas, ordenadas y buscadas en el servidor.
- **Columnas:** perfil de cada columna.
- **Diccionario:** clasificación con correcciones opcionales.
- **Calidad:** diagnóstico por dimensiones.
- **Archivo:** cómo se leyó el original.

Todo se calcula sobre el dataset completo y nada modifica el original.

## Recorrido

```
carga ─▶ inspección (primer trabajo de fondo) ─▶ GET /versions/{id}/inspection
      └▶ comprensión ─▶ exploración ─▶ dashboard … (sin cambios)
corrección del diccionario ─▶ column_annotations (metadato; la heredan las versiones siguientes)
```

## Piezas

| Pieza                                              | Dónde                                                                        |
| -------------------------------------------------- | ---------------------------------------------------------------------------- |
| Contratos y reglas puras (`dataset-inspection-v1`) | `modules/inspection/contracts.py`, `domain.py`                               |
| Cálculo con Polars                                 | `modules/inspection/engine.py`                                               |
| Correcciones (tabla `column_annotations`)          | `modules/inspection/infrastructure.py`, migración 0022                       |
| HTTP                                               | `modules/inspection/presentation.py`                                         |
| Cola, entrada fijada y acceso                      | `bootstrap/inspection_job.py`                                                |
| Datos del original (`source-facts-v1`)             | `ingestion/processor.py` (modo `source_facts`), `xlsx_reader.workbook_facts` |
| Registros con orden y búsqueda                     | `ingestion/analytical.py` (`PolarsPreview.read`)                             |
| Interfaz                                           | `apps/web/src/features/dataset/*`, pestañas en `csv-workspace.tsx`           |

## API

- `GET /api/v1/versions/{id}/inspection` (`getInspection`) devuelve `InspectionView`:
  - `state`: `queued`, `running`, `ready`, `failed` o `unavailable`;
  - la inspección;
  - el diccionario vigente;
  - la distribución por clasificación con las correcciones.
- `POST /api/v1/versions/{id}/dictionary` (`annotateColumn`): corrección de una columna (rol,
  naturaleza, interpretación temporal, observación o confirmación). Devuelve la vista
  actualizada.
- `GET /api/v1/versions/{id}/preview` admite además `sort` (identificador de columna),
  `descending` y `search`. Responde con `RecordsPage`: los campos de `PreviewPage` más
  `column_ids`, `sort`, `descending` y `search`. Los parámetros anteriores no cambian.

## Pruebas

`tests/test_phase22_dataset.py` cubre los 16 casos pedidos:

- CSV en UTF-8, en Windows-1252 con `;`, coma decimal y una línea en blanco, y Excel con varias
  hojas.
- Nulos, faltantes escritos como texto y texto en blanco.
- Tipos mixtos, fechas ambiguas e inválidas, ceros iniciales y filas duplicadas.
- Año y Mes como periodo posible.
- 100.000 registros, y archivo vacío o inválido.
- Paginación, orden y búsqueda.
- Correcciones heredadas y validadas, y una sola inspección por versión.
- Consistencia de nulos y valores únicos con los registros paginados.
- Cifras conocidas: 6 × 5 = 30 celdas, con un nulo → 96,67 %.

Además:

- `test_migration_0022.py` prueba la migración.
- `test_architecture.py` comprueba que la inspección no usa IA ni base de datos en su cálculo.
- La E2E `dataset.spec.ts` recorre las seis subvistas y una corrección que persiste.

## Limitaciones

- Las versiones anteriores a la fase no tienen inspección (`unavailable`).
- Las columnas reescritas por la lectura regional se muestran en su celda canónica.
- No hay nivel de confianza; se muestra la procedencia de cada clasificación.
- `.xls` no se admite.
- Las correcciones todavía no alimentan la comprensión ni el dashboard.
