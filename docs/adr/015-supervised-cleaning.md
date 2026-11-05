# ADR-015 — Limpieza supervisada con efecto aprobado y versión derivada

Estado: implementado en Fase 5 / API 0.7. Desarrolla las secciones 3–6 del [contrato de ejecución](../architecture/phase-1/execution-contract.md) sobre el catálogo y el worker por pasos del [ADR-014](014-planning-catalog.md).

## Contexto

Las incidencias Q-001 (nulos) y Q-003 (sólo espacios) se detectaban pero no se corregían. Corregir datos exige que el usuario vea el efecto exacto antes de autorizarlo, que la autorización no pueda aplicarse a otro efecto y que el original y la versión de origen no cambien nunca.

## Decisión

- Módulo cleaning con dos operaciones del catálogo `analysis-v2`, ambas `transforms_data`: `cleaning.trim_whitespace@1` (bordes SP/TAB/CR/LF, los mismos caracteres que Q-003; vacío → nulo creado) y `cleaning.filter_rows@1` (`is_null | is_whitespace_only`, `any | all`; conserva el orden). Columnas por ID con la validación genérica de Fase 4. NBSP y otros espacios Unicode se conservan.
- Un plan de limpieza es una cadena lineal sólo de operaciones `cleaning.*` (422 `CLEANING_PLAN_REQUIRED`). Nunca se ejecuta como `plan`: la API devuelve 409 `APPROVAL_REQUIRED` y el worker lo rechaza también.
- **Vista previa** (`cleaning_preview`): mismos ejecutores que la aplicación, un subproceso por paso con plazo compartido y un finalizador que calcula el efecto sobre el dataset completo. Publica sólo `effect` (manifiesto + `effect_sha256`) y `effect_samples` (≤ 50); ninguna tabla, versión ni cambio de predeterminada. Las tablas intermedias quedan bajo el prefijo privado del intento sin registrarse (recolectables según ADR-010).
- **Manifiesto** sin IDs temporales ni fechas: plan y hash, tabla de entrada, revisión semántica, hash de configuración y de entorno, columnas y hash lógico de la salida, hash del linaje de filas y conteos exactos (entrada, salida, excluidas, filas y celdas modificadas, nulos creados). `effect_sha256 = digest("effect", manifiesto)`. El hash de entorno incluye el del código: un despliegue entre vista previa y aplicación invalida la aprobación (`PREVIEW_EFFECT_MISMATCH`), como exige el contrato.
- **Aprobación** (`cleaning_approvals`): se envía el `effect_sha256` visto (si no coincide, 409 `APPROVAL_SCOPE_MISMATCH`). Una vigente por vista previa; inmutable salvo `revoked_at` (NULL → fecha, por trigger). Revocable mientras la aplicación esté en cola (se cancela en la misma transacción); en curso, 409. Una sola aplicación por aprobación: su ID es la clave idempotente de la ejecución.
- **Aplicación** (`cleaning_apply`): el worker recalcula el efecto y exige el aprobado antes de producir nada publicable. En una sola transacción con lease y fencing: versión `derived` (ID determinista por ejecución), linaje, artefactos `table` y `row_lineage` asignados a la nueva versión, vínculo, auditoría y perfil/calidad en cola. La revocación se vuelve a comprobar al confirmar. Si falla, se cancela o la lease vence antes, la derivada no existe para nadie. La derivada **no** pasa a ser la predeterminada y no hay todavía ruta para elegirla (no existe consumidor).
- **Contenido de la derivada**: su Parquet (SHA físico; hash lógico en el artefacto). Conserva los IDs de columna de su origen, de modo que el hash lógico de vista previa y aplicación coinciden; una revisión semántica de la derivada sigue siendo propia de su tabla (Fase 3). `/versions/{id}/original` responde 409 `DERIVED_HAS_NO_ORIGINAL` y la UI enlaza el original de la versión de origen. Exportar CSV derivado queda para Fase 9.
- **Linaje de versiones** en `dataset_version_lineage` (1:1, inmutable) y no en columnas de `dataset_version_records`: igual que en ADR-014, columnas nuevas harían que el ORM rompiera el código y las migraciones 0.5/0.6 sobre esquemas anteriores.
- executions recibe finalizadores por tipo de ejecución, un gancho de publicación previo a `stage` y `ArtifactOutput.version_id`; sigue sin importar cleaning. El cálculo de cleaning (`infrastructure`, `engine`, `processor`) no importa SQLAlchemy (prueba AST).

## Deuda: `dataset_import_bindings` para derivadas

El listado de versiones, el diagnóstico y la vista previa pasan por `dataset_import_bindings` (versión → ejecución de referencia → tabla, perfil, calidad). Para no reescribir esos recorridos, una derivada reutiliza ese vínculo: su ejecución de referencia es el perfil/calidad encolado al publicar y su tabla, la derivada; `materialize_derived` completa el diagnóstico sin tocar la predeterminada. Es una **decisión de compatibilidad y una deuda de nombres**: el vínculo ya no es sólo de «importación». Se prevé renombrarlo o generalizarlo (p. ej. `dataset_version_baselines`) cuando haya un tercer origen de versiones o se rediseñe la selección de versión predeterminada.

## Alternativas y consecuencias

Aplicar sin vista previa, o aprobar «la limpieza» sin hash, permitiría publicar un efecto distinto del revisado. Recalcular en la aplicación cuesta un segundo cálculo completo, a cambio de garantizar que lo publicado es lo aprobado. Limpiar puede **bajar** la completitud (un valor sólo de espacios pasa a nulo): la UI lo destaca para que «limpiar» no se confunda con «más datos completos». Los ejemplos son una muestra; los conteos salen siempre del cálculo completo.
