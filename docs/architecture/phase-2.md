# Fase 2 — Datasets y ejecuciones independientes

API implementada: 0.4. Ver [ADR-012](../adr/012-phase2-persistence.md).

## Responsabilidades

| Módulo                  | Posee                                                                           |
| ----------------------- | ------------------------------------------------------------------------------- |
| datasets                | Originales, objetos privados, versiones y baseline/default tabular              |
| executions              | Planes de sistema, runs, intentos, fencing y artefactos por ejecución/paso/slot |
| ingestion               | Carga CSV y coordinación por interfaces públicas                                |
| understanding / quality | Cálculos deterministas de sus productores                                       |
| bootstrap               | Composición, UnitOfWork, ejecutores, publicación y cutover                      |

Las versiones no contienen estado operativo. La respuesta legacy sigue siendo una proyección. Ingesta ya no tiene repositorio SQL ni tablas nuevas propias.

## API aditiva

- GET `/api/v1/versions/{id}/representations`: tablas publicadas y hashes, sin rutas privadas.
- POST `/api/v1/versions/{id}/analyses`: tabla + SHA + tipo `profile_quality` o `quality_only`; requiere Idempotency-Key, CSRF y permiso.
- GET `/api/v1/versions/{id}/executions`: últimas 50 ejecuciones.
- GET `/api/v1/executions/{id}`: estado, plan y snapshots de intentos, sin tokens de fencing.
- GET `/api/v1/executions/{id}/artifacts`, `/quality` y `/profile`: resultados de ese run.
- POST `/api/v1/executions/{id}/cancel-analysis`: cancelación individual.

Rutas y DTO CSV existentes se conservan. Cancelación legacy `/cancel` corresponde sólo a ingesta baseline. Hash/input incompatibles: 409. Propietario ajeno: 404. Proyectos archivados se consultan, pero no admiten nuevos análisis. Sólo calidad no publica un perfil.

## Interfaz

En un CSV procesado, **Ejecuciones independientes** permite elegir tabla y análisis, ejecutar y consultar plan/hash, intentos, entorno y calidad. Cada ejecución mantiene sus resultados; el diagnóstico de la carga y sus versiones no se sustituyen. La caché nueva usa execution_id. El objetivo es opcional porque los planes técnicos ya tienen propósito definido; preguntas de negocio y planificación libre llegarán después.

## Migración y respaldo

1. Construir imágenes: `docker compose -f infrastructure/compose/compose.yaml --profile full build`.
2. Esperar/cancelar autorizadamente cualquier trabajo 0.3 activo.
3. En el host: `python tools/backup_phase2.py --stop`. Pausa web/API/worker, deja PostgreSQL activo y crea copias privadas en `.data/backups/<UTC>/`: pg_dump, objetos, hashes y manifiesto con imagen anterior.
4. `python tools/verify_phase2_backup.py "<directorio>"` restaura en DB/volumen aleatorios, ejecuta 0003/cutover, compara conteos/identidades/hashes y elimina sólo esos recursos temporales. Requiere imágenes nuevas construidas y Compose local `dataflow`.
5. `docker compose -f infrastructure/compose/compose.yaml --profile full up -d`. La API aplica migración y `scripts/cutover.py --apply` antes de abrir tráfico.
6. Verificar health y manifiesto. Tabla legacy queda de sólo lectura. No se trasladan leases activos ni se ejecutan workers viejos/nuevos contra el mismo trabajo.

`python scripts/cutover.py` desde apps/api verifica sin confirmar: las escrituras de ensayo se revierten en la misma transacción. Usar el mismo almacenamiento y configuración de base que el despliegue; no reescribe archivos.

Las herramientas de backup son específicas del corte desde 0002, no un sistema general de backups. También exportan el filesystem del contenedor API anterior y conservan WorkingDir/User/Cmd, porque una etiqueta Docker reconstruida puede dejar de resolver el digest anterior. El lector del volumen puede utilizar la imagen nueva: sólo archiva bytes. El filesystem exportado no incluye los volúmenes; PostgreSQL y objetos se restauran desde sus copias separadas. La configuración de conexión debe suministrarse desde Compose, no inferirse de un hash de imagen.

Repetir el backfill no duplica ni cambia IDs. Si falla o se interrumpe, revierte metadatos y se puede repetir completo. Se conservan historia/errores/contador y se marca configuración desconocida como `legacy_partial`; no se generan N intentos ficticios a partir del contador viejo.

Antes de nuevas escrituras, una recuperación puede usar la imagen nueva para bajar a 0002 y después reactivar la imagen anterior. Tras aceptar runs nuevos se exige roll-forward o restauración coordinada con reconciliación: el downgrade está protegido para no perderlos.

## Pruebas

- Paridad CSV, bytes/hashes y compatibilidad baseline.
- Dos planes sobre una tabla, salidas separadas y cero versiones adicionales.
- Rollback de fuente+encolado y publicación+artefactos+baseline.
- Dos workers PostgreSQL independientes con jobs distintos y competencia por un mismo job.
- Lease vencida, token antiguo, cancelación y agotamiento de intentos.
- Migración desde 0002, repetición, cola activa, corrupción, interrupción y fences reales de PostgreSQL.
- Hash canónico Python compatible con corpus JavaScript de Fase 1.
- Navegador: creación de dos análisis, resultados, plan, recarga y móvil.

## Siguiente fase

Contrato semántico persistido por revisión: roles, grano, claves, unidades, formatos y nulos. Planificación libre y limpieza con preview/aprobación/versiones derivadas se implementarán sobre esta base, sin tratar los planes de lectura como transformaciones.
