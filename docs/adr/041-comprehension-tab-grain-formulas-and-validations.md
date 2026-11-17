# ADR-041 — Pestaña Comprensión: grano, fórmulas, relaciones por familia y validaciones que cuentan

Estado: aceptado e implementado en la Fase 24 (API 0.31.0, migración 0024; el catálogo de carga
sigue en `analysis-v13`). Documentación: [Fase 24](../architecture/phase-24.md). **Modifica
[ADR-036](036-business-comprehension-and-optional-feedback.md)**: la valoración de una relación
ya no cuenta sólo en la siguiente carga. Se apoya en
[ADR-040](040-dataset-tab-closure-and-corrections-that-count.md) (clasificación de partida desde
la pestaña Dataset).

## Contexto

La comprensión de la Fase 19 calculaba escalas, asociaciones e hipótesis de la IA, y se mostraba
dentro de la pestaña «Análisis». Con un dataset real de estudiantes:

- `promedio` era exactamente 0,3·parcial + 0,4·final + 0,3·prácticas y `aprobado` era
  `promedio ≥ 10,5`, pero la comprensión los presentaba como 8 «relaciones fuertes» y la
  exploración las convertía en consultas;
- el grano («una fila = un estudiante»), la sumabilidad de las medidas y el periodo ya los
  calculaba `profile@4`, pero no se mostraban;
- no había forma de saber qué tan segura era la IA de un significado, ni de corregirlo;
- la valoración «Relevante / No relevante» sólo contaba en la siguiente carga.

## Decisión

1. **`business-comprehension-v3`** (reglas puras en `comprehension/domain.py`, Polars sólo en
   `comprehension/measures.py`):
   - **Grano:** la primera clave única de la interpretación analítica y la entidad que nombra su
     identificador (`estudiante_id` → estudiante). Sin clave única, se dice.
   - **Columnas calculadas a partir de otras**, comprobadas fila a fila sobre todas las filas:
     - **suma ponderada:** mínimos cuadrados sin constante con hasta 6 fuentes; pesos redondeados
       a múltiplos de 0,05, positivos y de 0,05 a 1; error máximo de medio dígito del último
       decimal escrito en la columna;
     - **producto:** los que `profile@4` ya comprobó en todas las filas;
     - **umbral:** una columna de dos valores cuyos rangos en una medida no se solapan en ninguna
       fila; el umbral es el menor valor observado de la categoría alta. Uno por columna,
       prefiriendo una columna calculada como fuente.
   - **Misma entidad 1:1:** dos columnas que se repiten y se determinan mutuamente
     (`Customer_ID` ↔ `Customer_Name`). Una columna única por fila no cuenta.
   - **Periodo:** el eje temporal de `profile@4`, sin crear fechas.
   - **Medidas y dimensiones con su justificación:** sumabilidad, unidad y agregación correcta
     (nunca se suma lo que no se demostró sumable); cardinalidad y si sirve para agrupar.
   - **Tres familias de relaciones:** estructurales (calculada, misma entidad, dependencia, clave
     declarada), estadísticas (asociaciones) y temporales (periodo). Una fórmula se representa
     como una relación «derivada» por cada par (columna calculada, fuente), así que se conserva
     el formato de pares que leen la exploración y el informe.
   - **Estados:** validada y rechazada (la valoración del usuario; se conservan los valores
     guardados `relevant` y `not_relevant`), y sin valoración, **pendiente** si los datos la
     respaldan con fuerza o es estructural, y **ambigua** si no la respaldan del todo.
2. **Las fórmulas no son hallazgos.** Las asociaciones entre una columna calculada y sus fuentes
   (también las heredadas de otra calculada) no se proponen como relaciones, no pasan a la
   exploración y no llegan a la IA de la exploración. Se siguen viendo en el mapa de
   asociaciones.
3. **Validar o rechazar cuenta ya.** La valoración se guarda en `comprehension_feedback` y encola
   otra exploración con una instantánea de las valoraciones vigentes; al publicarse se rehacen el
   dashboard y el informe. No se vuelve a llamar a la IA de comprensión. La siguiente carga del
   mismo archivo también la tiene en cuenta.
4. **Significados con confianza** (prompt de comprensión v2): la IA da una confianza (alta,
   media o baja) y puede decir que no sabe; Python limita a baja la de los nombres de código
   (`ESTREG`, `CDG_20`). El usuario puede escribir o confirmar un significado (tabla nueva
   `column_meanings`, migración 0024, inmutable y sólo de añadir, por fuente y columna, heredada
   por las versiones siguientes). Un significado nunca cambia un cálculo.
5. **Pestaña propia.** «Comprensión», entre «Dataset» y «Análisis», con las subvistas Resumen
   (grano, dominio, fórmulas, periodo y preguntas), Columnas (escala, uso y significado) y
   Relaciones (por familia, con estado, validación y mapa de asociaciones). La sección sale de
   «Análisis».

## Decisiones tomadas sin consulta

- Sin dependencias nuevas: el sistema lineal de la suma ponderada se resuelve en Python puro
  (el proyecto no usa numpy) con las sumas calculadas por Polars.
- Hasta 6 fuentes por fórmula y 10 medidas candidatas, como el resto de la comprensión.
- Las versiones cargadas antes de la fase conservan su comprensión v1 o v2 y su valoración sigue
  contando sólo en la siguiente carga.
- Un significado escrito por el usuario muestra «confianza alta» porque lo afirma quien conoce el
  negocio.
- Fórmulas no lineales (cocientes, porcentajes de otra columna, sumas con constante) quedan fuera
  de esta fase.

## Consecuencias

- La comprensión clasifica la tabla, ajusta fórmulas y busca entidades: más cálculo por carga,
  sin IA.
- Con estudiantes, de las 8 consultas de exploración que salían de fórmulas sólo quedan las que
  relacionan `horas_estudio_sem` con `promedio` y con `aprobado`, que son relaciones reales.
- Una validación puede encolar hasta tres trabajos (exploración, dashboard e informe).
