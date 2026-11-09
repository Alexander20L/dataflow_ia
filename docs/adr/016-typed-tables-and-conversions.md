# ADR-016 — Tablas tipadas, conversiones supervisadas y errores estrictos

Estado: implementado en Fase 6A / API 0.8. Desarrolla las secciones 3 y 6 del [contrato de ejecución](../architecture/phase-1/execution-contract.md) sobre el ciclo de limpieza del [ADR-015](015-supervised-cleaning.md). Documentación: [Fase 6](../architecture/phase-6.md).

> **Vigencia (Fase 13, [ADR-026](026-fully-automatic-single-path.md))**: la supervisión humana que fija este ADR quedó sin efecto en el producto; las conversiones ya no llegan de una persona ni de un mapeo confirmado. Siguen vigentes las tablas tipadas, las gramáticas de conversión y los errores estrictos; la deducción automática de conversiones sin pérdida queda para la Fase 14.

## Contexto

Hasta 0.7 toda tabla publicada era texto nullable: perfil y calidad rechazaban otro tipo (`UNSUPPORTED_TABLE_TYPE`) y el hash lógico serializaba las celdas tal cual. Convertir tipos, normalizar marcadores de nulo y deduplicar exige tipos reales sin cambiar ningún resultado existente, sin decidir conversiones por inferencia y sin publicar efectos parciales.

## Decisión

- **Representación única** en `platform/tabular.py`: tipos del catálogo (`string`, `integer` Int64, `decimal` Decimal(38, 0..12), `date`, `boolean`) y celda canónica del §6 para el hash `table` y las vistas. Las celdas de texto se serializan igual que antes; otro tipo físico se rechaza (`UNSUPPORTED_COLUMN_TYPE`) y un esquema que no coincide con el Parquet, también (`SCHEMA_MISMATCH`). El esquema de columnas ya llevaba `technical_type` y `type_parameters`, así que el hash de las tablas de texto no cambia.
- **Operaciones** `cleaning.cast@1`, `cleaning.normalize_null_tokens@1` y `cleaning.deduplicate@1` en `analysis-v3`, con gramáticas exactas (sin recortar, sin exponentes, sin formatos regionales). Los analizadores de `cleaning/conversion.py` son puros.
- **Tipos en la validación**: el descriptor declara los tipos admitidos por parámetro y su esquema de salida; planning propaga el esquema paso a paso sin datos (`COLUMN_TYPE_MISMATCH`).
- **Identificadores**: salvaguarda `IdentifierConversionGuard` (genérica en planning) que exige `confirm_identifier_conversion` si la revisión fijada confirma la columna como identificador, más la gramática estricta que rechaza ceros a la izquierda aunque no haya semántica.
- **D1 · errores estrictos**: la vista previa **falla** (`CONVERSION_FAILED`, `NULL_KEY_REJECTED`) y el detalle (conteo exacto y ≤ 50 casos) se guarda en `execution_error_details` (executions, uno por intento, inmutable). `ApplicationError` y el subproceso transportan un `details` opcional. No existe un efecto aprobable con errores.
- **D2 · redondeo**: un decimal con más decimales que la escala se cuantiza HALF_EVEN y se cuenta en `EffectManifest.rounded_cells`; exceder 38 dígitos es error.
- **D3 · `null_keys: reject`** falla el plan si una clave tiene nulos; `group_nulls` los agrupa. El parámetro es obligatorio: no hay comportamiento implícito.
- **Efecto**: una celda está modificada si cambia de valor o de tipo conservando un valor no nulo (§6); el manifiesto declara el esquema de salida tipado y la derivada se publica con él.
- **D8**: 6A (API 0.8, migración 0007, este ADR) y 6B (API 0.9, migración 0008, ADR-017) se entregan por separado.

## D7 · Por qué ampliar `profile@1` y `quality@1` no viola el versionado

La regla del proyecto es que cambiar la semántica de una operación exige una versión nueva, porque un plan guardado debe producir siempre lo mismo. Ampliar `understanding.profile@1` y `quality.evaluate@1` a columnas tipadas no cambia ningún resultado posible de esas operaciones:

1. **Para tablas de texto la salida es idéntica.** El camino de texto no cambió; una prueba dorada capturada _antes_ del cambio (hash lógico, perfil, calidad, vista previa y efectos de limpieza de los CSV del repositorio) y la regresión byte a byte de Fase 4 lo verifican. Además, sobre una base con 90 versiones existentes, recalcular perfil y calidad con el código nuevo dio exactamente lo publicado.
2. **Para tablas tipadas no existía resultado anterior.** Hasta 0.7 una tabla con columnas tipadas no podía existir (la ingesta sólo publica texto) y, si se hubiera presentado, ambas operaciones fallaban con `UNSUPPORTED_TABLE_TYPE`. Un plan que antes fallaba no tenía un resultado que preservar.

Por tanto el dominio de las operaciones se amplía sin redefinir ningún resultado. Crear `@2` habría obligado a migrar los planes de sistema que perfilan cada versión, sin ganar reproducibilidad. Si en el futuro cambia el resultado sobre texto (por ejemplo, otra heurística de tipos sugeridos), sí se creará una versión nueva.

## Alternativas

- **Vista previa «exitosa» con efecto bloqueado** (D1-b): mostraría conteos de un efecto que no puede aplicarse y obligaría a decidir qué hacen los pasos posteriores a un `cast` fallido.
- **Rechazar el exceso de escala** (D2-b): más estricto, pero contrario al contrato, que fija cuantización HALF_EVEN visible en la vista previa.
- **Tratar las claves nulas como distintas** en `reject` (D3-b): nunca rechazaría nada y contradiría el significado de la clave semántica.
- **Inferir conversiones o recortar automáticamente**: cambiaría datos sin una operación explícita aprobada.

## Consecuencias

- El contrato crece de forma aditiva (operaciones, `failure`, `rounded_cells`, enum de `technical_type`, códigos de problema). Planes guardados conservan su catálogo y hash.
- Cada `cast` convierte una columna y el primer paso que falla detiene la cadena: los errores de otra columna aparecen al corregir la primera.
- Validación de planes y ejecución comprueban tipos de forma independiente (defensa en profundidad).
- `execution_error_details` es genérica: otras operaciones estrictas pueden aportar detalle sin que executions conozca su contenido.
