# ADR-017 — Reglas de calidad configurables (csv-quality-v2)

Estado: implementado en Fase 6B / API 0.9. Documentación: [Fase 6](../architecture/phase-6.md). Complementa el [ADR-016](016-typed-tables-and-conversions.md).

## Contexto

`csv-quality-v1` sólo evalúa reglas técnicas fijas (Q-001 vacíos, Q-002 filas repetidas, Q-003 sólo espacios) y una completitud de celdas. Los usuarios necesitan expresar reglas de negocio (una columna obligatoria, una clave única, un rango, un catálogo de valores, un formato convertible) sin que se mezclen con la completitud técnica, sin modificar diagnósticos existentes y con la misma reproducibilidad que planes y revisiones semánticas.

## Decisión

- **Catálogo `csv-quality-v2`** en el módulo quality, con cinco tipos de regla: `required`, `unique_key` (una clave con nulos también es infracción), `range` (inclusivo; entero/decimal como cadena decimal, fecha ISO), `allowed_values` (comparación exacta con la cadena canónica de la celda) y `convertible` (gramáticas de `cleaning.cast@1`, sin convertir). Cada regla declara los tipos de columna que admite. Las gramáticas de conversión pasan a `platform/conversion.py` para que quality y cleaning las compartan sin crear un ciclo entre módulos.
- **Diagnóstico con `origin`**: el informe separa `technical` (exactamente csv-quality-v1: mismas incidencias y completitud) y `user`. La completitud nunca incluye reglas de negocio.
- **D5 · Conjuntos por tabla base del proyecto**: una familia por tabla publicada, con revisiones inmutables (padre, número, contenido, hash `quality_ruleset`, actor, fecha), `expected_revision` (409 si cambió), `Idempotency-Key` y sin revisión si no hay cambios. Las reglas referencian columnas **por ID**: sirven para esa tabla y para sus versiones derivadas, que conservan los IDs. El contexto de una tabla lista los conjuntos del proyecto con su aplicabilidad (columnas existentes y tipos compatibles); una importación nueva tiene otros IDs y no los hereda.
- **Unicidad desde la semántica**: la UI ofrece «Activar unicidad de la clave declarada» sólo si la revisión semántica tiene la clave confirmada; la regla guarda `source: semantic_key` y la referencia exacta de la revisión. Nunca se activa sola.
- **D6 · `quality.evaluate@2`** (catálogo `analysis-v4`) lleva la referencia exacta como **parámetro del paso** (`ruleset_revision_id`, `ruleset_sha256`), no como campo del plan, para no alterar el contenido ni el hash de los planes existentes. La validación de planes resuelve la revisión mediante un puerto (planning sigue sin importar quality) y devuelve `QUALITY_RULESET_MISMATCH` (inexistente, ajena, hash distinto o columna ausente) o `COLUMN_TYPE_MISMATCH` (tipo incompatible en ese paso). Se ejecuta como plan normal y publica un artefacto nuevo `quality_rules`; `quality.evaluate@1` y su ruta no cambian.
- **Lectura antes del cómputo**: el paso lee la revisión en un gancho `prepare` que el ejecutor llama antes de cerrar la transacción de metadatos; el cálculo en subproceso no abre transacciones.
- **Persistencia**: migración 0008 aditiva (`quality_ruleset_families`, `quality_ruleset_revisions`, `quality_ruleset_save_requests`); revisiones y solicitudes inmutables por trigger; downgrade bloqueado si hay conjuntos.

## Alternativas

- **Conjunto por proyecto con columnas por nombre**: se aplicaría a cualquier importación, pero contradice la regla de columnas por ID y confundiría columnas homónimas con significado distinto.
- **Conjunto por tabla sin herencia**: más simple, pero obligaría a repetir las reglas en cada versión derivada.
- **Referencia en el contenido del plan**: cambiaría el esquema y el hash de todos los planes; como parámetro de paso es un cambio aditivo del catálogo.
- **Extender `quality.evaluate@1`**: cambiaría su resultado y su contrato; las reglas del usuario son una operación nueva.
- **Una puntuación única que combine reglas técnicas y de negocio**: mezclaría completitud con decisiones del usuario y haría incomparables los diagnósticos.

## Consecuencias

- El diagnóstico baseline de cada versión sigue siendo csv-quality-v1; las reglas del usuario se evalúan bajo demanda y quedan en el historial de ejecuciones con su revisión exacta.
- Copiar reglas a una importación nueva (emparejando columnas con confirmación) queda pendiente.
- `ArtifactKind` y `OutputKind` ganan `quality_rules`; los consumidores deben consultar el resultado que produce cada plan.
