# Fase 19 — Comprender el negocio

Estado: **implementada** (API 0.26.0, migración 0020, catálogo de carga `analysis-v13`).
Decisión: [ADR-036](../adr/036-business-comprehension-and-optional-feedback.md).

## Objetivo

Entender de qué trata cada dataset antes de analizarlo: la IA interpreta la estructura (nombres y
perfil agregado, nunca filas) y los datos confirman o no cada hipótesis. El usuario puede valorar
las relaciones, pero no tiene que hacerlo.

## Recorrido

```
carga ─▶ comprensión (IA + medidas) ─▶ investigación ─▶ informe
```

Los dos trabajos intermedios son de fondo; la comprensión se encola primero.

## Qué se calcula

| Parte                 | Cómo                                                                           |
| --------------------- | ------------------------------------------------------------------------------ |
| Escala de medida      | Reglas `measurement-scale-v1`; orden ordinal sólo si se demuestra              |
| Asociaciones          | Pearson/Spearman, V de Cramér, eta, sobre todas las filas (máx. 10 + 10 cols.) |
| Dependencias          | A → B: proporción de valores de A con un único B                               |
| Hipótesis de negocio  | IA: dominio, entidades, significado (también de nombres codificados), órdenes  |
| Relaciones            | IA, datos (fuertes), interpretación y claves foráneas de SQL Server            |
| Estado de la relación | Confirmada (≥ 0,3 o ≥ 98 %), no respaldada o no comprobable                    |

## API

| Ruta                                         | Respuesta                                           |
| -------------------------------------------- | --------------------------------------------------- |
| `GET /versions/{id}/comprehension`           | `queued`, `running`, `ready` o `failed`             |
| `POST /versions/{id}/comprehension/feedback` | Guarda «Relevante» / «No relevante»; vale la última |

Versiones anteriores: 404 `COMPREHENSION_NOT_AVAILABLE` y la etapa como «No aplica».

## Interfaz

Panel «Entendimiento del negocio»: hipótesis de la IA (marcadas como tales), tabla de columnas con
escala y significado, mapa de calor de asociaciones (ECharts) y relaciones con su evidencia y los
botones opcionales de valoración. Preguntas de negocio sugeridas. El progreso tiene cuatro etapas.

## Pruebas

`tests/test_phase19_comprehension.py`: escalas ordinales demostrables, orden de la IA aceptado sólo
si coincide, textos con cifras retirados, umbrales, medidas sobre datos conocidos, estados de las
relaciones y orden por valoración, claves foráneas de SQL Server, recorrido con IA falsa (relación
inventada descartada, dependencia ambigua no respaldada, valoración que pasa a la siguiente carga),
sin IA e informe. `tests/test_migration_0020.py`: ida y vuelta, inmutabilidad y última valoración.
E2E `analysis.spec.ts`: panel, mapa de calor y valoración.
