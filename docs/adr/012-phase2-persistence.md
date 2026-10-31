# ADR-012 — Persistencia separada y compatibilidad CSV

Estado: implementado en Fase 2 / API 0.4. Desarrolla ADR-011.

## Contexto

0.3 impone una ejecución por versión y un artefacto por versión/tipo. Relajar esas restricciones mientras el código viejo escribe puede mezclar resultados. Se necesita conservar originales, IDs, permisos y claves idempotentes.

## Decisión

- `datasets` conserva su ID; `dataset_objects`, `dataset_version_records`, `dataset_import_bindings` y `dataset_defaults` separan contenido, representación y proyección baseline.
- `execution_plan_revisions`, `execution_runs`, `execution_attempts` y `execution_artifacts` permiten múltiples runs por input y salidas únicas por ejecución/paso/slot.
- Planes de sistema sellados: extracción CSV + perfil/calidad, perfil/calidad de tabla y sólo calidad. No son planificación libre ni transformación.
- Cada intento registra configuración, código/lock, Python, Polars, plataforma y hash del entorno. Inputs tabulares fijan artefacto y SHA-256; no se resuelven por último resultado.
- Repositorios nuevos hacen flush, no commit. UnitOfWork coordina fuente+plan+run+baseline, o artefactos+baseline/default+cierre del intento. La lectura de metadatos termina antes del subproceso.
- Bootstrap registra ejecutores y hook transaccional de publicación. Executions no importa reglas internas de ingesta/calidad.
- Backfill atómico y repetible para el volumen MVP, con verificación de todos los objetos. Conserva historia como `legacy_partial` sin fabricar planes, intentos ni fechas de finalización.
- Triggers protegen tablas viejas tras cutover y objetos/versiones/planes/artefactos nuevos frente a sobrescritura. Downgrade rechazado si hay runs completos nuevos.

## Corte y compatibilidad

Se respaldan PostgreSQL y objetos con servicios de escritura pausados y se ensaya su restauración en recursos temporales. 0.3 no dispone de bandera de mantenimiento: este corte utiliza una pausa breve del servicio, sin prometer lecturas continuas. La API nueva aplica 0003 y cutover antes de aceptar tráfico; el worker espera su healthcheck. Cola legacy activa, objeto ausente o discrepancia bloquean el corte.

Endpoints 0.3 siguen el binding baseline: no devuelven el diagnóstico del análisis más reciente. Runs independientes no cuentan como nuevas cargas. `running` se proyecta como `processing` sólo en DTO legacy. Artefactos históricos conservan sus IDs y JSON combinado como `legacy_diagnostic`; los nuevos publican perfiles/calidad separados.

## Alternativas y consecuencias

Alterar tablas in-place dificulta rollback; doble escritura permanente crea dos autoridades; microservicios añaden coordinación sin resolver el contrato. Tablas sombra y una autoridad tras cutover requieren más estructuras y una ventana coordinada, pero conservan la historia y permiten retirada posterior.

Se mantienen un dataset principal por proyecto, fuentes CSV y operaciones de lectura. Contratos semánticos revisables, planificación abierta, aprobaciones y derivadas pertenecen a las siguientes fases. El backfill se reinicia completo si falla; no requiere checkpoints confirmados por lote para este volumen. Los objetos no se reescriben ni se eliminan por commits inciertos.
