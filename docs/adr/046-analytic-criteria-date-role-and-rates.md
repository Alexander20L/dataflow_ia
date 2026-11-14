# ADR-046 — Criterio analítico: papel de las fechas, mínimo por grupo y tasas

Estado: aceptado e implementado en la Fase 28 (API 0.36.0, sin migración; el catálogo de carga
sigue en `analysis-v13` y `profile@4` no cambia). Documentación: [Fase 28](../architecture/phase-28.md).
Modifica [ADR-041](041-comprehension-tab-grain-formulas-and-validations.md) (comprensión v4),
[ADR-040](040-dataset-tab-closure-and-corrections-that-count.md) (inspección v3) y
[ADR-043](043-investigation-tab-plan-tree-and-control.md) (investigación v3, `relevance-v2`).

## Contexto

La revisión de un análisis real (un padrón de 200 empleados) mostró conclusiones que un analista
no daría:

1. La fecha de ingreso se trató como línea de tiempo: «Evolución mensual del salario −33 %» salió
   como hallazgo relevante con una mediana de un empleado por mes, y la calidad avisó de «meses sin
   registros».
2. Se compararon promedios de grupos de 4 a 8 personas como si fueran diferencias reales.
3. La columna «activo» (20 bajas de 200, del 2,9 % al 14,3 % según el departamento) no se
   analizó como tasa: es el indicador más útil del archivo.
4. Un ranking y una agregación por la misma dimensión y medida aparecían como dos hallazgos.
5. «evaluacion_desempeno» (1 a 5) y «dias_ausencia» no tenían rango esperado.

## Decisión

1. **`date-role-v1`** (`platform/timing.py`, regla pura compartida): una fecha es un **atributo**
   del registro cuando el grano es una entidad (hay una clave única que no incluye las columnas
   del periodo) y la mediana de registros por mes observado es menor que 2; si no, registra
   **eventos**. Una serie con una fila por mes (clave = el propio periodo) sigue siendo una serie.
2. **Comprensión `business-comprehension-v4`**: con una fecha atributo no hay periodo; se publica
   en `dated_attributes` (primera y última fecha, registros por año y motivo). Los planes
   guardados con v3 se siguen calculando como v3.
3. **Inspección `dataset-inspection-v3`**: la misma regla marca `date_role` y su motivo en la
   columna; con una fecha atributo no se emiten los avisos de meses faltantes, frecuencia ni
   candidato de periodo. Se reconocen escalas de valoración (evaluación, puntuación, puntaje,
   calificación, valoración, satisfacción, rating, score) en 1–5, 0–5, 1–10 o 0–10 según los
   valores observados, y más cantidades no negativas (días, horas, ausencias…).
4. **`relevance-v2`**: en promedios, medianas y tasas, un grupo o un mes con menos de 10
   registros se muestra pero no cuenta para clasificar; si no quedan dos grupos (o tres meses), el
   resultado es «no concluyente» y lo explica. Las sumas y los conteos son totales exactos y
   cuentan siempre.
5. **`explore-v3` (`exploration.explore@3`, `investigation-v3`)**: dos tipos de consulta sólo de
   reglas: `rate` (proporción de la categoría minoritaria de una columna de dos valores, en total
   y por la primera dimensión) y `cohort` (registros por año de una fecha atributo). La tasa por
   grupo se clasifica por puntos de diferencia (≥ 10 relevante, ≥ 5 secundaria). El plan no
   repite consultas equivalentes (un `top` y un `aggregate` con la misma dimensión, medida y
   agregación son la misma).
6. **Dashboard e informe**: la tasa total es un indicador en «%» (como mucho dos columnas); la
   tasa por grupo se dibuja en barras y la cohorte en barras o líneas. El informe usa la tasa en
   sus conclusiones y recomienda revisar los grupos con la tasa más alta.

## Decisiones tomadas sin consulta

- El papel de la fecha se decide después de la carga (comprensión e inspección) y no en
  `profile@4` ni en el catálogo `analysis-v13`, para no cambiar resultados publicados.
- `rate` y `cohort` no se ofrecen a la IA: su prompt de propuestas no cambia de versión.
- Umbrales: 2 registros por mes (mediana) y 10 registros por grupo; 10 y 5 puntos para las tasas.
- La categoría de la tasa es la menos frecuente (en empate, la primera en orden).

## Consecuencias

- Un padrón deja de producir «evoluciones mensuales» de casos sueltos y gana su tasa de bajas.
- Algunos hallazgos de grupos pequeños pasan a «no concluyente» con su motivo.
- Las versiones analizadas antes siguen leyéndose con sus reglas; volver a cargar el archivo
  aplica las nuevas.
