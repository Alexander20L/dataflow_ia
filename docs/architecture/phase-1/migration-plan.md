# Migración incremental y compatibilidad 0.3

Estado: diseño. Ningún paso de este documento se ha ejecutado como parte de Fase 1.

## 1. Inventario conocido

Revisión actual de Alembic: `0002`.

| Origen               | Restricción relevante                      | Destino conceptual                                                  |
| -------------------- | ------------------------------------------ | ------------------------------------------------------------------- |
| `datasets`           | project_id único                           | Mismo ID; metadatos/default tabular añadidos gradualmente           |
| `dataset_versions`   | campos orientados a original CSV           | Registro de versión neutral, conservando ID/número/hash             |
| `import_executions`  | version_id único                           | Ejecuciones con muchos runs por input; historia legacy identificada |
| `analysis_artifacts` | UNIQUE(version_id, kind)                   | Artefactos por ejecución/paso/slot                                  |
| `audit_events`       | actor, entidad, acción, correlación, fecha | Conservar; añadir referencias a nuevas decisiones                   |

El diagnóstico 0.3 combina perfil y calidad en un mismo JSON. No se debe fingir que ya existían dos ejecuciones o dos artefactos distintos. `parquet` y `diagnostic` legacy conservan bytes, hashes e IDs; pueden clasificarse como `table` y `legacy_diagnostic` en el catálogo de compatibilidad. Nuevas ejecuciones producen perfiles/calidad con slots explícitos.

## 2. Estrategia expandir → copiar → verificar → cambiar → retirar

### M1. Expansión aditiva

Crear, mediante nuevas revisiones Alembic, registros de objetos/referencias, versiones neutrales, planes, contratos semánticos, ejecuciones/intentos, artefactos y aprobaciones. Nombres finales de tablas se decidirán en Fase 2 con un ADR de persistencia; se prefieren tablas sombra para los modelos que cambian de identidad/cardinalidad, evitando relajar una restricción que el código 0.3 todavía asume.

No renombrar ni eliminar tablas que usa el código vigente. Los nuevos módulos se introducen detrás de puertos con el recorrido anterior aún disponible. Registrar progreso y mapeos con claves únicas para que repetir un lote no duplique registros. IDs nuevos de metadatos se derivan de un namespace de migración fijo o se guardan en el mapa; nunca se regeneran en cada reintento.

### M2. Corte controlado de escritura y drenaje

Para el volumen actual, elegir una ventana corta de mantenimiento de escritura: rechazar nuevas importaciones/ediciones relevantes con respuesta explícita, mantener consultas y dejar terminar el worker 0.3. El corte exige cero trabajos queued/processing. Si un trabajo no termina, cancelarlo mediante su recorrido autorizado o posponer el corte. No traducir leases activos ni ejecutar un worker viejo y uno nuevo sobre el mismo trabajo.

Respaldar PostgreSQL y el volumen de objetos de forma coordinada. Conservar imagen/configuración anterior y manifiesto de conteos/hashes. Una restauración sólo es válida si metadatos y objetos corresponden al mismo punto de consistencia.

### M3. Backfill reanudable

1. Copiar datasets/versiones conservando identidades y números; referenciar claves existentes mediante objetos privados nuevos, sin mover ni reescribir archivos.
2. Verificar tamaño/hash de originales y artefactos publicados. Un objeto ausente o corrupto se informa como discrepancia y bloquea la aceptación del corte hasta resolverlo.
3. Copiar ejecuciones terminales conservando ID, estado, contador histórico, errores y correlación. Marcar `reproducibility=legacy_partial` cuando falten snapshots. Nunca inventar timestamps de intentos anteriores, versiones de Python o configuración efectiva.
4. Si no es posible reconstruir un plan exactamente, conservar `plan_ref=null` y procedencia legacy explícita. Ese registro terminal es consultable, no encolable. Una reejecución futura crea un plan completo y otra ejecución con referencia a la anterior.
5. Conservar IDs/hashes de artefactos. `attempt_id=null` sólo está permitido para artefactos legacy sin intento identificable. El contador histórico no se convierte en N intentos ficticios.
6. Registrar columnas/ordinales y correspondencia de filas originales desde el Parquet verificado; no convertir valores. Inicializar semántica como pendiente/origen migration, sin confirmar roles ni moneda.
7. Guardar `legacy_import_binding` por versión: ejecución original y artefactos baseline de tabla/diagnóstico. Este enlace es fijo, no una consulta al resultado más reciente.
8. Conservar eventos de auditoría e incorporar un evento de migración con mapeos/procedencia, sin atribuir aprobaciones al usuario.

No hay derivadas reales 0.3: no se inventan padres para las versiones importadas ni se trata la limpieza del fixture local como dato persistido del usuario.

### M4. Validación y cutover

Comparar conteos, IDs, hashes, estados, alcance por propietario y payloads de diagnóstico. Verificar un corpus con carga fallida, cancelada, reintentada, dos versiones y proyecto archivado. Completar pruebas de atomicidad y compatibilidad antes de dirigir tráfico al nuevo recorrido.

Cambiar la autoridad de escritura una sola vez a datasets/executions. Los componentes nuevos comparten una transacción; no se mantienen commits independientes ni doble escritura asincrónica sin reconciliación. Las tablas anteriores quedan de sólo lectura durante la ventana de recuperación.

### M5. Retirada posterior

Eliminar estructuras legacy sólo después de una ventana acordada, manifiesto de reconciliación aprobado y restauración verificada. No forma parte del primer despliegue de separación. El descenso de versión de esquema tras publicar derivadas no es seguro por defecto: el modelo 0.3 no puede representar sus datos.

## 3. Compatibilidad HTTP

Conservar inicialmente todos los endpoints y DTO efectivos de OpenAPI 0.3.

| Ruta actual                  | Comportamiento que debe conservarse                                                              |
| ---------------------------- | ------------------------------------------------------------------------------------------------ |
| POST projects/{id}/imports   | Misma validación CSV, idempotencia y 202; crea fuente y ejecución de lectura                     |
| GET projects/{id}/versions   | `VersionResponse` compuesto con estado de su ejecución de ingesta baseline                       |
| GET versions/{id}/diagnostic | Diagnóstico baseline fijado por binding; no mezcla planes                                        |
| GET versions/{id}/preview    | Tabla baseline y filtros de incidencias correspondientes al mismo diagnóstico                    |
| GET versions/{id}/original   | Mismos bytes de versiones importadas; la ruta no finge que una derivada Parquet sea CSV original |
| POST executions/{id}/cancel  | Mismo ID y reglas para trabajos vigentes; terminales conservan el conflicto esperado             |
| GET datasets/summary         | Mantener semántica 0.3 (cargas/ingestas); no contar previews/limpiezas como cargas               |

Los consumidores nuevos seleccionarán artefacto/ejecución explícitos mediante endpoints aditivos a especificar en Fase 2. La descarga de una derivada y la consulta de su fuente original serán operaciones distintas. Una actualización incompatible requiere contrato HTTP versionado; el esquema interno v1 no reemplaza el OpenAPI actual.

Mapeo de estado para la proyección legacy: `queued → queued`, `running → processing`, `succeeded → succeeded`, `failed → failed`, `cancelled → cancelled`. `attempts` usa el contador histórico conservado o los intentos del run baseline, sin inventar timestamps. Los errores originales se conservan.

Hasta activar el frontend nuevo, el listado legacy incluye versiones importadas representables por su contrato. Las derivadas se exponen por el recorrido aditivo tipado; no se insertan en una respuesta antigua que las presente como archivos CSV originales. La selección predeterminada nueva y la selección baseline legacy tienen funciones diferentes y deben estar documentadas en el adaptador.

## 4. Recuperación

- Antes del cutover: mantener el código 0.3 y descartar/reconciliar sólo la copia nueva mediante su mapa; no borrar originales.
- Después del cutover, sin nuevas escrituras: volver a la imagen anterior sólo si la validación confirma que siguen siendo las mismas tablas autoritativas y objetos.
- Después de nuevas cargas/derivadas: roll-forward es la opción preferida. Restaurar un backup requiere ventana de escritura detenida y una decisión explícita sobre las escrituras posteriores. No prometer downgrade automático sin pérdida.
- Objetos de commit incierto se conservan y se reconcilian por referencias/hash; no se eliminan basándose únicamente en edad o nombre de carpeta.

## 5. Prueba obligatoria de migración

Preparar una base/volumen de prueba desde el esquema 0002, aplicar expansión/backfill dos veces, comparar manifiestos, ejecutar endpoints legacy y crear dos análisis nuevos sobre una versión conservada. Repetir con interrupción entre lotes y con objeto corrupto/ausente. Las pruebas nunca operarán sobre la base del usuario.
