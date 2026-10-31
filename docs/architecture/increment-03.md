# Incremento 0.3 — Ingesta CSV y calidad reales

Recorrido: crear proyecto → cargar CSV → conservar original → encolar ejecución → worker → Parquet + perfil + calidad → consultar registros y descargar original. Módulos nuevos: ingestion, understanding y quality, más contrato público de permisos de projects. Ingestion coordina por puertos; los módulos exponen interfaces públicas sin compartir modelos SQL internos.

## API

| Método | Endpoint                                                   | Resultado                                               |
| ------ | ---------------------------------------------------------- | ------------------------------------------------------- |
| POST   | /api/v1/projects/{id}/imports?file_name=...&separator=auto | CSV binario, Idempotency-Key, 202 con versión/ejecución |
| GET    | /api/v1/projects/{id}/versions                             | Versiones paginadas y estados                           |
| GET    | /api/v1/datasets/summary                                   | Conteos de cuenta, sin fixture                          |
| GET    | /api/v1/versions/{id}/diagnostic                           | Perfil y calidad, tras éxito                            |
| GET    | /api/v1/versions/{id}/preview                              | Filas paginadas, opcional issue_id                      |
| GET    | /api/v1/versions/{id}/original                             | Original íntegro, con hash verificado                   |
| POST   | /api/v1/executions/{id}/cancel                             | Cancelación y fencing                                   |

Sesión y propietario en todas las rutas. CSRF/Origin en mutaciones. Versiones ajenas: 404. Proyectos archivados: lectura permitida, no nuevas cargas. Respuestas sin claves/rutas del volumen. Originales de cargas fallidas disponibles para corregirlos.

## Frontend

El formulario crea proyecto y sube CSV. Si la subida falla tras crear el proyecto, reintenta sobre ese proyecto con clave estable para el mismo File/configuración. Workspace con selección paginada de versiones, estado, cancelación, SHA-256, descarga, esquema y calidad con filas afectadas. Polling sólo mientras hay trabajo activo. Recarga recupera datos de API, no localStorage.

OpenAPI genera DTO y binarios Blob. Proxy same-origin con límite de 5 MiB y cabeceras de idempotencia/CSRF. Se distinguen envío, cola y procesamiento sin porcentajes inventados. Las etapas posteriores todavía no procesan archivos reales. El ejemplo conserva su recorrido simulado independiente; indicadores generales consultan conteos reales y los gráficos de ejemplo están etiquetados.

## Verificación

PostgreSQL en esquemas efímeros: bytes/SHA original, idempotencia/conflicto, cuotas/busy, versiones, reproducibilidad, precisión y ceros iniciales, errores de estructura/codificación/cabecera, permisos, cancelación, recuperación de lease y rechazo de intento antiguo. E2E con API/worker separados: datos propios, incidencias, descarga comparando bytes y nueva versión conservando la anterior.

Consultar ADR-010 para límites y semántica. Siguiente incremento: planes de limpieza versionados, revisión antes/después y aprobación humana real.
