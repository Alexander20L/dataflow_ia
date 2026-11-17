# ADR-033 — Investigación acotada y propuestas de la IA validadas

Estado: aceptado e implementado en la Fase 16 (API 0.23.0, sin migración; el catálogo de carga
sigue en `analysis-v12`). Modifica el principio 6 de [ADR-026](026-fully-automatic-single-path.md)
según la decisión D1 de la [Fase 14](../architecture/phase-14.md). Documentación:
[Fase 16](../architecture/phase-16.md). Se apoya en [ADR-029](029-automatic-ai-explanation.md) y
[ADR-032](032-automatic-analysis-plan.md).

## Contexto

La Fase 15 publica hallazgos con evidencia, pero se detiene ahí: un mes atípico o una variación
interanual no se siguen, y la explicación con IA (C2) sigue hablando del dashboard descriptivo.
D1 permitía a la IA proponer desde la Fase 16 y D2 pedía un módulo `investigation` sobre la cola
existente, sin recrear `automation`.

## Decisión

1. **Nuevo principio** (sustituye al punto 6 de ADR-026): el motor determinista decide y calcula
   con reglas versionadas; la IA **explica** resultados publicados y **propone** investigaciones
   en un esquema cerrado; Python valida cada propuesta contra el plan y los hallazgos y el motor la
   calcula. Ninguna cifra sale del modelo y nada fuera del catálogo se ejecuta.
2. **Módulo `investigation`** (dominio y aplicación puros, con puertos `FollowUps`, `Proposer` y
   `Explainer`). Ciclo `investigation-v1`:
   - iteración 1: seguimientos por **reglas** (siempre, también sin IA): desglose del mes atípico
     por las dos primeras agrupaciones, reparto de la variación interanual y evolución del grupo
     principal;
   - iteraciones siguientes: la IA propone (`investigation-proposal@1`); Python valida tipo,
     dimensión (sólo agrupaciones aceptadas por el plan; las omitidas se rechazan con su motivo),
     mes, año y grupo existentes, campos exclusivos y duplicados;
   - final: la IA explica hallazgos y seguimientos (`automatic-findings-audit@1`) con la regla de
     cifras de C2.
3. **Límites duros** guardados con cada investigación y configurables por entorno
   (`DATAFLOW_INVESTIGATION_MAX_*`): 3 iteraciones, 4 llamadas, 60 s, US$ 0,05 y 12 consultas.
   Cada corte queda registrado (`stopped`).
4. **Catálogo cerrado de seguimientos** `analytics.followup@1` (`investigation-followup-v1`):
   `month_by_group`, `change_by_group` y `group_evolution`, calculados en el subproceso de
   analytics con las métricas virtuales de la Fase 15 y evidencia por cifra.
5. **Ejecución**: trabajo `investigation` de la cola (un solo intento: una llamada facturable no
   se reintenta) encolado al publicar una carga con `analytics.automatic@1`. Su input fija el
   análisis y la tabla de esa carga por id y hash. Es una operación interna, fuera del catálogo de
   planes, como la explicación C2.
   La cola lo reclama **después** de cualquier otro trabajo en cola (trabajo de fondo): una
   investigación nunca retrasa una carga, una limpieza o un plan del mismo propietario.
6. **Presupuesto durable**: cada llamada se registra en el consumo de IA existente al publicar
   (tareas `investigation_proposal` y `findings_audit`) y cuenta para los límites diarios y
   mensuales. Sin tablas nuevas.
7. Para las cargas con hallazgos la investigación **sustituye** a la explicación del dashboard; las
   versiones anteriores conservan C2 y no se recalculan (404 `INVESTIGATION_NOT_AVAILABLE`).

## Consecuencias

- Cada carga con hallazgos se sigue sola; sin IA, las reglas siguen aportando seguimientos.
- La IA puede elegir mal, pero no puede ejecutar nada no validado ni aportar cifras; lo rechazado
  se muestra con su motivo.
- Dependencias: `investigation` usa `analytics.contracts` y `copilot.contracts`; `bootstrap`
  compone motor, IA y cola. `copilot` sigue sin depender de otros módulos.

## Alternativas descartadas

- Recrear un orquestador (`automation`): lo prohíbe la prueba AST y la cola ya da leases,
  fencing y orden.
- Dejar que la IA formule consultas libres (SQL o parámetros de `analytics.query`): imposible de
  validar con garantías y contrario a «ninguna cifra sale del modelo».
- Mantener dos explicaciones (dashboard y hallazgos): duplica consumo y confunde.
