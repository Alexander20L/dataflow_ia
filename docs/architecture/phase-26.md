# Fase 26 — Pestaña Dashboard

Estado: **implementada** (API 0.34.0, migración 0027, catálogo de carga `analysis-v13`).
Decisión: [ADR-044](../adr/044-dashboard-tab-indicators-filters-and-customization.md). Parte de
la [Fase 21](phase-21.md) (dashboard adaptado) y de la [Fase 25](phase-25.md) (investigación).

## Objetivo

Comunicar visualmente los descubrimientos:

- un resumen ejecutivo de indicadores verificables;
- gráficos adaptados a cada resultado y ordenados por importancia;
- filtros que recalculan lo que depende de ellos;
- el origen de cada gráfico;
- una versión personalizada que no destruye la automática.

## Recorrido

```
investigación ─▶ dashboard (delivery.dashboard@2, dashboard-design-v2)
                   consultas por reglas ─▶ motor exacto (todas las filas)
                   indicadores + elementos con origen ─▶ diseño (IA o reglas) ─▶ validación
               ─▶ informe
filtros ─▶ POST /dashboard/filter ─▶ tabla filtrada ─▶ motor exacto (no se guarda)
versión personalizada ─▶ POST /dashboard/custom ─▶ dashboard_customizations (revisiones)
```

## Piezas

| Pieza                                             | Dónde                                    |
| ------------------------------------------------- | ---------------------------------------- |
| Contratos (indicador, origen, filtros)            | `modules/delivery/contracts.py`          |
| Consultas, indicadores, catálogo, orden y filtros | `modules/delivery/dashboard.py` (puro)   |
| Histograma, dispersión y subconjunto filtrado     | `modules/exploration/engine.py` (Polars) |
| Versión personalizada (contratos, tabla 0027)     | `modules/curation/`                      |
| Prompt de diseño v2 (clase de cada resultado)     | `modules/copilot/dashboard.py`           |
| Trabajo, filtros y personalización                | `bootstrap/dashboard_job.py`             |
| Pestaña Dashboard                                 | `apps/web/src/features/dashboard/`       |

## Catálogo de gráficos (`dashboard-design-v2`)

Son los de la Fase 21 más dos nuevos:

| Gráfico     | Cuándo es compatible                                      |
| ----------- | --------------------------------------------------------- |
| `histogram` | La distribución de una medida (intervalos de igual ancho) |
| `scatter`   | Pares de dos medidas con asociación moderada o fuerte     |

Reglas de legibilidad:

- el circular admite de 2 a 6 partes;
- el mapa de calor admite como mucho 200 celdas;
- las barras dibujan los 12 primeros grupos y el resto queda en la tabla.

## API

- `GET /api/v1/versions/{id}/dashboard`:
  - el dashboard v2 añade `items` (cada uno con `trace`), `indicators`, `computed`, `filters`,
    `total_rows`, `partial` y `notice`;
  - la vista añade `custom` (revisión vigente) y `custom_dropped`.
- `POST /api/v1/versions/{id}/dashboard/filter` (`filterDashboard`):
  - recibe `period_from` y `period_to` (meses «AAAA-MM») y `categories` (hasta 3 dimensiones);
  - devuelve los elementos recalculados (o el motivo por el que no se recalculan), los
    indicadores y los registros que quedan;
  - responde 422 `DASHBOARD_FILTER_INVALID`.
- `POST /api/v1/versions/{id}/dashboard/custom` (`saveDashboardCustomization`):
  - recibe `expected_revision` y `sections`;
  - responde 409 `DASHBOARD_REVISION_CONFLICT` y 422 `DASHBOARD_LAYOUT_INVALID`.
- Un dashboard anterior a la fase responde 409 `DASHBOARD_V2_REQUIRED` al filtrar o
  personalizar.

## Interfaz

La pestaña **Dashboard** va después de Investigación. De arriba abajo:

- el diseño (IA o reglas) y los avisos de resultados parciales o de hallazgos insuficientes;
- el selector entre la versión **Automática** y la **Personalizada**, y el botón **Personalizar**;
- los filtros (periodo desde/hasta y valores de cada dimensión);
- la línea que dice si se ve el dataset completo o un subconjunto filtrado (con los registros);
- los indicadores (valor, unidad, grupo o mes destacado, periodo, comparación, Origen y «Ver los
  registros»);
- los gráficos (con su clase, su Origen y, si hay filtros, si se recalcularon).

Las marcas «Sí va / No va» siguen en la versión automática.

## Pruebas

- `tests/test_phase26_dashboard.py` cubre los criterios del apartado 4.7:
  - visualizaciones temporales, categóricas y numéricas;
  - pocas y muchas categorías;
  - indicadores verificables y sin unidades inventadas;
  - sin hallazgos suficientes y resultados parciales;
  - filtros exactos sobre el subconjunto;
  - versión personalizada validada y que sobrevive a un dashboard nuevo;
  - el recorrido por la API (origen, filtros, revisiones y aislamiento).
- `test_migration_0027.py`: ida y vuelta, `compare_metadata`, revisiones, conflicto,
  inmutabilidad y downgrade bloqueado con datos.
- E2E:
  - `dashboard.spec.ts`: origen, filtro, personalizar y volver a la automática;
  - `analysis.spec.ts`: las marcas, ahora en la pestaña Dashboard.

## Limitaciones

- «Ver los registros» abre los Registros sin aplicar el filtro del indicador.
- Los hallazgos del análisis automático (Fase 15) no se recalculan con filtros: lo dicen.
- La personalización no cambia el informe; las marcas «sí va / no va» sí.
