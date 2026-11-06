# ADR-020 — Dashboards persistidos que muestran ejecuciones exactas

Estado: implementado en Fase 8 / API 0.12. Documentación: [Fase 8](../architecture/phase-8.md). Se apoya en [ADR-018](018-deterministic-business-analysis.md) y [ADR-019](019-comparisons-ranking-share.md).

## Contexto

Los análisis de la Fase 7 se calculan y se consultan uno a uno. El usuario necesita reunirlos en dashboards que se conserven entre sesiones, sin que una cifra cambie sin una acción explícita y sin perder la trazabilidad de cada número.

## Decisión

- **Un dashboard no calcula**: cada tarjeta apunta a una revisión de un plan de `analytics.query@2` y a la ejecución exacta que muestra. Las cifras y su evidencia son las de esa ejecución.
- **Revisiones inmutables** por dashboard (`expected_revision`, `Idempotency-Key`, sin cambios no hay revisión), como semántica, reglas y métricas. Migración 0010 aditiva.
- **«Actualizar» explícito** sobre la versión elegida, con revisión nueva. Como un plan está fijado a su tabla, se reutiliza el plan si la tabla y la revisión semántica vigente coinciden; si no, se crea un plan nuevo con los mismos pasos. Los planes guardados no cambian.
- **Filtros globales de presentación**: ocultan filas del resultado ya calculado y sólo se aplican a tarjetas cuya consulta agrupa por esa dimensión; las demás dicen «Filtro no aplicable».
- **Errores por tarjeta** sin romper el resto, a partir del plan (validez) y de la ejecución (estado, filas).
- **Módulo `dashboards`** sin dependencias de planning, executions ni analytics: bootstrap implementa su puerto. Gráficos con el `Chart` existente (ECharts); sin dependencias nuevas.

### Decisiones tomadas en la implementación

- Formas de tarjeta validadas al guardar contra la consulta: KPI de una sola fila (sin dimensiones ni tiempo), líneas con agrupación temporal, barras con un único eje (una dimensión o sólo el periodo), tabla con cualquier resultado.
- Un resultado con 0 filas es «datos insuficientes».
- Un dashboard pertenece a un proyecto; «Actualizar» lleva todas sus tarjetas a la versión elegida, que debe ser del mismo proyecto.
- Un plan no válido se clasifica como «requisito semántico pendiente» si alguno de sus problemas es `SEMANTIC_REQUIREMENT_MISSING`, y si no como «análisis no válido para esta versión» (cuarto tipo de error: p. ej. una métrica cuyas columnas no encajan).
- Las tarjetas que comparten plan comparten la ejecución de «Actualizar»; las claves de planes y ejecuciones derivan (UUIDv5) de la clave de la solicitud, así que repetirla no duplica nada.
- La revisión de «Actualizar» se crea al momento con las ejecuciones en cola; la vista vuelve a consultarse mientras alguna tarjeta está «Calculando…».
- Cada edición de la cuadrícula (mover, tamaño, quitar, filtros) guarda una revisión.
- En los gráficos, las cifras exactas y su procedencia están en «Ver cifras y su procedencia»: el gráfico es una representación aproximada (números de coma flotante).

## Alternativas

- **Filtros que recalculan** (añadirlos a la consulta y ejecutar): el dashboard calcularía y la cifra de la tarjeta dejaría de ser la de su ejecución guardada.
- **Actualización automática al subir datos**: contradice la supervisión; una cifra cambiaría sin acción del usuario.
- **Nueva revisión del mismo plan con otra tabla**: rompe la regla de planes fijados a su tabla (Fase 4).
- **Arrastrar y soltar**: añadiría una dependencia; los botones bastan para ordenar.

## Consecuencias

- Un dashboard se reproduce exactamente por su revisión: mismas ejecuciones, mismas cifras y mismas evidencias.
- La lista de planes del proyecto crece con los creados por «Actualizar» sobre otra versión.
- Desplegar API y worker juntos desde 0.11.
