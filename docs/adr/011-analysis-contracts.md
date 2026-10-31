# ADR-011 — Identidades de datos, planes y ejecución separadas

Estado: diseño aceptado para guiar Fase 2; implementación pendiente. Complementa ADR-005/007/008/010. No cambia el comportamiento del incremento 0.3.

## Contexto

La ingesta actual reúne versiones, una ejecución por versión y un artefacto por versión/tipo. La limpieza necesita producir derivadas y ejecutar distintos planes sobre las mismas entradas. Además, un archivo puede tener varias interpretaciones tabulares y las decisiones semánticas deben ser revisables.

## Decisión

1. Separar datasets, executions y planning mediante contratos públicos. Los ejecutores de operaciones se inyectan en bootstrap; el orquestador no importa reglas internas de los módulos.
2. Versiones inmutables sin estado operativo. Inputs tabulares fijan versión y representación publicada con hashes; no se resuelven por «latest».
3. Planes/contratos semánticos inmutables por revisión, con hash canónico restringido y snapshots de configuración/entorno. Datos históricos incompletos se identifican como legacy_partial.
4. Muchas ejecuciones por input/plan. Intentos separados y artefactos identificados por ejecución/paso/slot, con publicación transaccional y fencing.
5. Preview y aprobación vinculados al efecto completo, inputs, semántica y entorno. El objetivo del usuario es opcional; las operaciones transformadoras requieren autorización independiente de IA.
6. Migración aditiva con pausa de escritura, drenaje, backfill reanudable y bindings legacy. Conservar originales/IDs y separar historia incompleta de nuevos planes ejecutables.

## Alternativas

- Extender indefinidamente ingestion: menos cambios inmediatos, pero obliga a limpieza/analítica a depender de internals y perpetúa cardinalidades incorrectas.
- Microservicios: no resuelven los contratos y complican las transacciones de publicación.
- Recalcular y sustituir historia durante migración: simplifica datos aparentes, pero pierde evidencia y puede atribuir configuración inexistente.
- Confiar sólo en temperatura/seed de IA: no fija datos, operaciones ni autorizaciones, y no garantiza reproducibilidad de cálculos.

## Ventajas y consecuencias

Reutilización por limpieza/analítica, explicaciones con evidencia, repetición de planes y compatibilidad de fuentes futuras. Se requiere una migración coordinada, control de revisiones y mayor disciplina en transacciones. Un hash de contenido detecta cambios; no es una firma digital ni sustituye autenticación/autorización.

## Riesgos y controles

Dos fuentes de verdad durante transición: una sola autoridad de escritura tras cutover. Resultados ambiguos: TableRef/binding baseline y cachés por artefacto. Doble publicación: unicidad de slots e intento activo. Autorización obsoleta: comprobar aprobación/permisos al encolar y confirmar. Reproducibilidad aparente: conservar desconocidos históricos y snapshots efectivos. Complejidad prematura: un input, pasos secuenciales y sin reanudación parcial en v1.
