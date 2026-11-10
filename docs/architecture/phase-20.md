# Fase 20 — Exploración guiada

Estado: **implementada** (API 0.27.0, sin migración, catálogo de carga `analysis-v13`).
Decisión: [ADR-037](../adr/037-guided-exploration.md).

## Objetivo

Que la IA proponga qué mirar en los datos (no sólo seguir hallazgos) sin producir cifras: propone
consultas de un lenguaje cerrado, Python las valida, el motor las calcula sobre todas las filas y la
IA juzga su relevancia viendo como mucho 100 filas de cada resultado.

## Recorrido

```
carga ─▶ comprensión ─▶ exploración ─▶ (informe)
      └▶ investigación ─────────────────▶ informe
```

## Lenguaje `explore-v1`

| Tipo                   | Qué calcula                                                     |
| ---------------------- | --------------------------------------------------------------- |
| `aggregate`            | Suma, promedio, mediana o conteo por una o dos dimensiones      |
| `crosstab`             | Registros (o suma de una medida aditiva) por dos dimensiones    |
| `ratio`                | Suma de una medida / suma de otra, en total o por una dimensión |
| `top`                  | Los primeros grupos (hasta 20) por una medida agregada          |
| `correlation_by_group` | Spearman entre dos medidas dentro de cada grupo                 |

Filtro opcional por el valor de otra dimensión. Validación: tipos del catálogo, columnas existentes
con su escala, sólo se suman medidas aditivas, nada repetido y nada de relaciones marcadas «No
relevante».

## Límites

Hasta 8 consultas por reglas, 12 propuestas de la IA y 20 consultas calculadas; 2 llamadas a la
IA; 100 filas por resultado para la IA; 500 grupos guardados por resultado.

## API e interfaz

`GET /versions/{id}/exploration`: `queued`, `running`, `ready` (propuestas con su decisión,
resultados con cifras y relevancia) o `failed`. Panel «Exploración guiada»: resultados relevantes
con gráfico y tabla, descartados y propuestas rechazadas con su motivo. Etapa nueva en el progreso
y sección en el informe.

## Pruebas

`tests/test_phase20_exploration.py`: rechazos con motivo, consultas válidas y repetidas, consultas
por reglas y exclusión por valoración, cifras exactas del motor y evidencias estables, recorrido con
IA falsa (propuestas aceptadas y rechazadas, juicio de relevancia, conteos iguales a las filas del
archivo), sin IA, exclusión en la siguiente carga e informe. E2E `analysis.spec.ts`.
