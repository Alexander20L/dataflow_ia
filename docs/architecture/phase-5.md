# Fase 5 — Limpieza supervisada mínima

API 0.7. [ADR-015](../adr/015-supervised-cleaning.md). Primer recorrido completo de limpieza sobre CSV propios: propuesta → vista previa sobre todo el dataset → aprobación del efecto exacto → versión derivada con diagnóstico nuevo, con el original intacto.

## Recorrido e interfaz

CSV procesado → etapa **Limpieza** → propuesta (borrador) → «Generar vista previa» (se guarda como plan) → efecto, nulos creados y ejemplos → «Aprobar efecto…» → «Aplicar limpieza» → «Ver la versión derivada».

- La propuesta inicial sale del diagnóstico: una incidencia Q-003 sugiere recortar esa columna; una Q-001, excluir los registros con nulo. Es editable por columna; se recorta antes de excluir.
- La vista previa muestra conteos exactos (entrada, salida, excluidos, celdas modificadas, **nulos creados**) y hasta 50 ejemplos antes/después. Si se crean nulos, avisa de que la completitud puede bajar.
- La aprobación muestra el resumen y el `effect_sha256`. Revocable mientras la aplicación no haya empezado.
- Si la aplicación falla por `PREVIEW_EFFECT_MISMATCH`: «Los datos, el plan o el sistema cambiaron desde la vista previa. Genera una vista previa nueva y vuelve a aprobar», con botón «Repetir vista previa».
- Selector de versión con linaje («v2 · derivada de v1») y una franja que indica siempre qué versión se ve, si es derivada y su origen, con «Ver v1». Una derivada ofrece «Descargar original de v1». La derivada no pasa a ser la predeterminada; el selector muestra la más reciente.
- El fixture de demostración sigue separado y etiquetado.

## Operaciones (catálogo `analysis-v2`)

| Operación                    | Parámetros                                                                          | Efecto                                                                           |
| ---------------------------- | ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `cleaning.trim_whitespace@1` | `column_ids`                                                                        | Quita SP/TAB/CR/LF de los bordes. Nulos siguen nulos; vacío → nulo (nulo creado) |
| `cleaning.filter_rows@1`     | `column_ids`, `predicate` (`is_null`, `is_whitespace_only`), `match` (`any`, `all`) | Excluye los registros que cumplen el predicado; conserva el orden del resto      |

Columnas por ID (validación genérica de Fase 4). NBSP y otros espacios Unicode se conservan. Ceros iniciales intactos (todo es texto). Los planes de Fase 4 conservan `analysis-v1` y su hash; las validaciones se recalculan con el catálogo nuevo.

## API

| Ruta                                             | Función                                                                                        |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| POST `/api/v1/plans/{revision_id}/previews`      | Encola la vista previa (`Idempotency-Key`); 422 si el plan no es una cadena de limpieza válida |
| GET `/api/v1/previews/{execution_id}`            | Estado, manifiesto, `effect_sha256`, ejemplos, aprobación vigente y aplicación                 |
| POST `/api/v1/previews/{execution_id}/approvals` | Aprueba el `effect_sha256` enviado; 409 `APPROVAL_SCOPE_MISMATCH` si no coincide               |
| POST `/api/v1/approvals/{id}/revoke`             | Revoca (cancela la aplicación en cola); 409 si está en curso o ya aplicada                     |
| POST `/api/v1/approvals/{id}/apply`              | Encola la aplicación; idempotente por aprobación; 409 `APPROVAL_REVOKED`                       |
| GET `/api/v1/versions/{id}/lineage`              | Versión de origen, ejecución productora, efecto y operaciones                                  |
| GET `/api/v1/versions/{id}`                      | Una versión por ID (el selector carga así un origen que no está en la página actual)           |

Además: `VersionResponse` añade `kind` y `parent_version_id`; `/versions/{id}/original` de una derivada responde 409 `DERIVED_HAS_NO_ORIGINAL` («Esta versión es derivada; descarga el original de la versión de origen»); `/plans/{id}/executions` rechaza planes que transforman datos (409 `APPROVAL_REQUIRED`). Sesión y propietario en todas las rutas; Origin y CSRF en mutaciones; ajeno: 404. Cambios de contrato aditivos: 6 operaciones nuevas y valores nuevos en `RunKind` (`cleaning_preview`, `cleaning_apply`) y `ArtifactKind` (`effect`, `effect_samples`, `row_lineage`).

## Persistencia

Migración 0006, sólo aditiva:

- `cleaning_approvals`: plan, vista previa, `effect_sha256`, hash de la tabla de entrada, revisión semántica, hashes de configuración y entorno, autor, fecha y `revoked_at`. Trigger: sólo `revoked_at` NULL → fecha. Índice único parcial: una vigente por vista previa.
- `dataset_version_lineage`: versión derivada, versión de origen y ejecución productora (1:1, inmutable).

Downgrade bloqueado si hay aprobaciones o derivadas. Las derivadas reutilizan `dataset_import_bindings` como vínculo de diagnóstico (deuda de nombres documentada en ADR-015).

## Ejecución y publicación

`cleaning_preview` y `cleaning_apply` ejecutan los pasos con el despacho por paso de Fase 4 (plazo compartido) y un finalizador que calcula el efecto en otro subproceso. La aplicación recalcula y compara con el efecto aprobado antes de producir nada publicable; después, en una transacción con lease y fencing, registra la versión derivada, linaje, artefactos, vínculo, auditoría y encola perfil/calidad (sin límite de capacidad: forma parte de la publicación). La revocación se comprueba al empezar y al confirmar. Cancelación, lease vencida, revocación o efecto distinto: nada publicado.

## Pruebas

Operaciones: nulos, celdas sólo de espacios, ceros iniciales, Unicode (NBSP conservado), orden, linaje, conteos exactos, muestra limitada con conteos completos y nombres de columna que Polars podría interpretar como regex. Determinismo: dos vistas previas, mismo `effect_sha256`. Fallos sin derivada: efecto distinto, cancelación durante la aplicación, intento vencido que termina tarde (el reintento publica una vez), revocación antes de publicar y aplicación sin aprobación. SHA-256 del original intacto. Migración 0006 (ida y vuelta, `compare_metadata`, triggers, downgrade bloqueado). API: recorrido completo, aprobación con hash erróneo, idempotencia, revocación, cadena inválida, propiedad y CSRF. Navegador: `cleaning.spec.ts` con `examples/ventas_calidad.csv` (trim de `importe`: 1 nulo creado; v2 con 93,33 % frente al 96,67 % de v1; v1 seleccionable e intacta).

## Observaciones y pendiente

- `PolarsPreview` de la ingesta (Fase 2) usaba `pl.col(nombre)` con encabezados del usuario: un nombre como `^id$` se interpretaría como expresión regular. Resuelto en [Fase 6](phase-6.md) con alias neutros.
- Elegir la versión predeterminada, exportar CSV derivado (Fase 9) y nuevas operaciones (`deduplicate`, `cast`) quedan fuera de esta fase; las conversiones y la deduplicación llegan en [Fase 6](phase-6.md).
