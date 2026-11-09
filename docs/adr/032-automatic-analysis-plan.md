# ADR-032 — Plan analítico automático y análisis con métricas virtuales

Estado: aceptado e implementado en la Fase 15 (API 0.22.0, catálogo `analysis-v12`, sin migración).
Documentación: [Fase 15](../architecture/phase-15.md). Se apoya en
[ADR-018](018-deterministic-business-analysis.md), [ADR-019](019-comparisons-ranking-share.md),
[ADR-026](026-fully-automatic-single-path.md) y [ADR-031](031-analytical-interpretation-and-quality.md).

## Contexto

`analytics.query@1–3` calcula cifras exactas con evidencia, pero exige métricas guardadas
(`created_by` de una persona) y tablas tipadas con una columna de fecha. Las cargas son tablas de
texto y el periodo `Year` + `Month` no es una columna. Faltaba decidir qué analizar sin preguntar.

## Decisión

1. **`planning/automatic.py` (`automatic-plan-v1`)**: plan puro desde la interpretación v2, con
   análisis aceptados y omitidos (siempre con motivo), prioridades y límites (12 análisis,
   4 desgloses). `planning` sigue sin importar `quality` ni `analytics`.
2. **`analytics.automatic@1` (`automatic-analysis-v1`)**: un paso más de la carga que, en el
   subproceso de analytics, prepara en memoria una tabla tipada y reutiliza el motor de
   `analytics.query@2` con **métricas virtuales** (identificador `uuid5` determinista, contenido con
   la tabla de entrada); no se guardan revisiones ni hace falta `created_by`.
3. Concentración, promedio ponderado, estacionalidad y anomalías se calculan con Decimal exacto en
   `analytics/automatic.py`, con métodos explícitos; las anomalías sólo **se asocian** a grupos.
4. **Evidencia autocontenida**: cada cifra de un hallazgo tiene `evidence_id` determinista y se
   resuelve con el artefacto guardado (`automatic_analysis`), sin consultar métricas en la BD.
5. La tabla de entrada la produce la propia carga: el alcance la identifica por versión, ejecución
   y hash de la tabla.
6. Versiones publicadas antes de `analysis-v12` no se recalculan (404 explícito).

## Consecuencias

- Una carga produce hallazgos verificables sin ninguna acción; la interfaz los muestra primero.
- Nuevas dependencias acíclicas: `analytics` usa `planning.public` y `understanding.public`;
  `ingestion` lee el contrato `analytics.contracts` para servir el resultado.
- La explicación IA aún no usa los hallazgos (Fase 16).

## Alternativas descartadas

- Guardar métricas del sistema como revisiones: exige `created_by` humano o una migración, y no
  aporta trazabilidad adicional (el artefacto ya contiene las definiciones).
- Recalcular las cifras sin el motor existente: duplicaría la semántica ya probada de
  comparaciones, participación y ranking.
- Que la IA elija los análisis: aplazado a la Fase 16 (D1).
