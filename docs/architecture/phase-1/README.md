# Fase 1 — Contratos para análisis y limpieza supervisada

Estado: especificación de diseño v1, verificable con ejemplos. La separación compatible del recorrido CSV está implementada en [Fase 2](../phase-2.md); los contratos semánticos y la limpieza siguen como objetivo de fases posteriores. Fecha de revisión inicial: 2026-10-27.

## Objetivo

Permitir varios análisis sobre los mismos datos y una limpieza autorizada que produzca una versión derivada. El recorrido CSV 0.3 sigue siendo la implementación vigente. Esta especificación no publica endpoints, no modifica tablas y no conecta IA.

## Leer en este orden

1. [Entidades e invariantes](domain-contracts.md).
2. [Planes, ejecución, aprobación y determinismo](execution-contract.md).
3. [Responsabilidades y dependencias](module-boundaries.md).
4. [Migración y compatibilidad](migration-plan.md).
5. [Criterios de aceptación y siguientes entregas](acceptance.md).
6. [ADR-011](../../adr/011-analysis-contracts.md).

Esquema y ejemplos de referencia: [contracts/analysis/v1](../../../contracts/analysis/v1).

## Artefactos verificables

- [Esquema de diseño](../../../contracts/analysis/v1/schema.json): JSON Schema 2020-12 con entidades y operaciones de alcance v1.
- [Escenarios de referencia](../../../contracts/analysis/v1/examples.json): ingesta, segundo análisis y limpieza con vista previa/aprobación/reintento.
- `npm run contracts:check`: valida estructura, referencias, hashes de revisiones y casos negativos. No abre PostgreSQL, no llama a la API y no procesa archivos del usuario.
- `npm run contracts:examples`: regenera el esquema y los ejemplos sintéticos de diseño.

Estos esquemas describen contratos internos objetivo. El contrato HTTP efectivo continúa siendo `contracts/openapi/dataflow.json`, generado desde FastAPI. En Fase 2, los DTO implementados se contrastarán con estos escenarios; no se mantendrán tipos TypeScript HTTP manuales paralelos.

## Hallazgos que resuelve

| Situación 0.3                                  | Decisión de diseño                                                             |
| ---------------------------------------------- | ------------------------------------------------------------------------------ |
| `Version` mezcla contenido y estado de trabajo | Versiones inmutables separadas de ejecuciones y proyecciones de UI             |
| `import_executions.version_id` es único        | Muchas ejecuciones pueden consumir una versión/representación                  |
| Artefacto único por versión y tipo             | Identidad por ejecución, paso y slot de salida                                 |
| Una lectura de CSV produce una tabla implícita | Referencia explícita a versión + representación publicada + hashes             |
| Versiones sólo importadas                      | Versiones derivadas con padre, ejecución productora y correspondencia de filas |
| Tipos sugeridos sin revisión persistida        | Contrato semántico inmutable por revisión, con origen y confirmación           |
| Configuración leída al arrancar worker         | Plan/configuración fijados y entorno efectivo conservado por intento           |
| Limpieza sólo en el ejemplo                    | Propuesta calculada, vista previa vinculante y aprobación independiente        |

## Decisiones de alcance

- Cuenta individual y propietario de proyecto: se conserva el modelo vigente.
- Un dataset principal por proyecto durante la transición; el contrato permite varios, pero Excel multitabla y selección de múltiples datasets quedan para otro incremento.
- Un input por plan y pasos secuenciales en v1. No hay joins, agregaciones de limpieza ni reanudación parcial entre pasos. Un intento repite el plan completo, con publicación atómica al final.
- La aprobación se solicita antes de encolar una ejecución que transforma datos. El worker no mantiene leases esperando al usuario.
- Cada llamada de extracción/perfilado/calidad puede expresarse como un plan del catálogo. El objetivo del usuario es opcional.
- Sugerencias de IA, si se incorporan, entran como borradores; no autorizan ejecución.

## Cierre de Fase 1

Se entrega una especificación comprobable. La Fase 2 empezará por introducir interfaces de datasets/ejecuciones y migraciones aditivas, con pruebas de compatibilidad del recorrido 0.3. Las decisiones de negocio no conocidas se registran como pendientes, nunca se inventan durante el backfill.
