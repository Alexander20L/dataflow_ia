# ADR-036 — Comprensión del negocio y valoración opcional del usuario

Estado: aceptado e implementado en la Fase 19 (API 0.26.0, migración 0020; el catálogo de carga
sigue en `analysis-v13`). Documentación: [Fase 19](../architecture/phase-19.md). Modifica el
principio «sin aprobaciones» de [ADR-026](026-fully-automatic-single-path.md) (decisión del
usuario): el recorrido sigue siendo automático y la valoración del usuario es **opcional y no
bloquea nada**. Se apoya en [ADR-031](031-analytical-interpretation-and-quality.md) y
[ADR-033](033-bounded-investigation-and-ai-proposals.md).

## Contexto

La interpretación de la Fase 14 decide el papel de cada columna con reglas sobre nombres y
valores. No describe el negocio, no entiende nombres codificados (`CDG_20`), no distingue escalas
de medida (nominal, ordinal, intervalo, razón) y no mide relaciones entre columnas. La IA entraba
tarde (investigación), con un catálogo estrecho, y por eso «sugería poco».

## Decisión

1. **Módulo `comprehension`** y trabajo de fondo `comprehension` (operación interna
   `comprehension.understand@1`), encolado al publicarse una carga con interpretación analítica,
   **antes** que la investigación (se reclama antes por llegar antes; si falla, la investigación
   sigue).
2. **IA sobre la estructura** (`copilot/comprehension.py`, prompt `business-comprehension` v1):
   recibe sólo nombres de columnas y un perfil agregado (tipo, rol, escala por reglas, distintos,
   nulos, mínimo, máximo y los valores más frecuentes de las dimensiones), nunca filas. Devuelve
   en un esquema cerrado: de qué trata el dataset, entidades, significado de cada columna,
   órdenes de escalas ordinales, relaciones candidatas y preguntas de negocio. Python retira las
   columnas inexistentes y los textos con cifras propias (las de un nombre de columna se
   admiten).
3. **Escalas de medida por reglas** (`measurement-scale-v1`): medida → razón; tiempo →
   intervalo; identificador y texto aparte; una dimensión es ordinal sólo con un orden
   demostrable (rangos numéricos, vocabulario ordenado conocido, pocos enteros) o con un orden de
   la IA que contiene exactamente los valores observados.
4. **Asociaciones sobre todas las filas** (`comprehension/measures.py`, Polars): Pearson y
   Spearman entre medidas, V de Cramér entre dimensiones, eta entre medida y dimensión, y
   dependencia funcional A → B. Hasta 10 medidas y 10 dimensiones; pares con menos de 10 filas
   o sin variación no se miden. Valores redondeados a 4 decimales (declarado en el método).
5. **Relaciones con evidencia**: las de la IA, las fuertes de los datos, las dependencias de la
   interpretación y las **claves foráneas declaradas** en SQL Server (leídas al copiar). Estado:
   confirmada (|medida| ≥ 0,3 o dependencia ≥ 98 %), no respaldada o no comprobable.
6. **Valoración opcional** («Relevante» / «No relevante»), tabla `comprehension_feedback`
   (migración 0020, inmutable, sólo de añadir; vale la última). No recalcula nada; la siguiente
   carga de la misma fuente (archivo y hoja, tabla o segmentos) fija una instantánea en su plan:
   lo relevante va primero y lo no relevante al final, sin ocultarlo.
7. **API**: `GET /versions/{id}/comprehension` y `POST /versions/{id}/comprehension/feedback`.
   El progreso añade la etapa «Entendimiento del negocio» y el informe una sección.

## Consecuencias

- Cada carga añade una llamada a la IA (con presupuesto y registro como las demás); sin IA se
  calculan igual escalas, asociaciones y relaciones de los datos.
- La IA sigue sin producir cifras publicadas: sólo hipótesis que los datos confirman o no.
- La interfaz tiene botones de valoración; ninguno es necesario para obtener resultados.
- Las uniones entre tablas por claves foráneas quedan para la fase de MySQL y MCP.
