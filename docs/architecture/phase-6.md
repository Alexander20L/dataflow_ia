# Fase 6 — Conversiones de tipo y calidad configurable

Se entrega en dos partes: **6A** (API 0.8, esta entrega) añade tipos reales, conversiones, marcadores de nulo y deduplicación al ciclo supervisado de Fase 5; **6B** (API 0.9, pendiente) añadirá reglas de calidad configurables (`csv-quality-v2`). [ADR-016](../adr/016-typed-tables-and-conversions.md).

Es la primera vez que una tabla deja de ser sólo texto. Todo reutiliza el ciclo de Fase 5: propuesta → vista previa sobre todo el dataset → aprobación del efecto exacto → versión derivada. El original y la versión de origen no cambian.

## 6A · Recorrido e interfaz

CSV procesado → **Limpieza** → propuesta → «Generar vista previa» → efecto (o lista de valores que no convierten) → aprobar → aplicar → v2 con columnas tipadas y diagnóstico nuevo.

- La propuesta tiene una fila por columna con su tipo y cinco acciones: marcadores de nulo, recortar, convertir (tipo y escala), excluir nulos; y una sección de deduplicación. Orden fijo: **marcadores → recortar → convertir → excluir → deduplicar**. El editor de planes de Fase 4 admite cualquier otro orden válido.
- Sugerencias desde el diagnóstico: Q-003 → recortar; Q-001 → excluir nulos; Q-002 → deduplicar todas las columnas agrupando nulos (mismo criterio que Q-002). **No se preselecciona ninguna conversión**: sólo se indica el tipo sugerido por el perfil.
- La propuesta fija la revisión semántica vigente de la tabla (se indica cuál) y prellena los marcadores de nulo confirmados (`explicit_tokens`). Si hay clave confirmada, ofrece «Usar la clave declarada».
- En columnas ya tipadas se desactivan las acciones que sólo admiten texto.
- La vista previa muestra además las **celdas redondeadas** y los tipos de la nueva versión. Si algo no convierte, muestra el total exacto y hasta 50 casos (columna, registro, valor y motivo) y no ofrece aprobar.

## Operaciones (catálogo `analysis-v3`)

| Operación                          | Parámetros                                                                                   | Columnas admitidas                                     |
| ---------------------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| `cleaning.normalize_null_tokens@1` | `column_ids`, `tokens` (1–20, únicos, 1–100 caracteres)                                      | texto                                                  |
| `cleaning.cast@1`                  | `column_id`, `type`, `format`, `scale` (sólo decimal, 0–12), `confirm_identifier_conversion` | texto                                                  |
| `cleaning.deduplicate@1`           | `column_ids`, `keep: first`, `null_keys: reject \| group_nulls` (obligatorio)                | cualquier tipo                                         |
| `cleaning.trim_whitespace@1` (F5)  | `column_ids`                                                                                 | texto                                                  |
| `cleaning.filter_rows@1` (F5)      | `column_ids`, `predicate`, `match`                                                           | `is_null`: cualquier tipo; `is_whitespace_only`: texto |

- **Marcadores**: la celda completa debe ser igual a un token (`"NA"` sí; `"na"`, `" NA"`, `"NAN"` no). Cada celda que pasa a nulo cuenta como nulo creado.
- **Deduplicación**: conserva la primera aparición en el orden de la tabla y compara valores tipados. `group_nulls` trata los nulos como iguales; `reject` hace **fallar** el plan si una clave tiene nulos y los lista (exclúyelos antes con `filter_rows` o elige agrupar).

### Gramáticas de `cleaning.cast@1` (contrato de ejecución §3)

| Tipo      | Formato             | Gramática y límites                                                                         | Salida canónica                |
| --------- | ------------------- | ------------------------------------------------------------------------------------------- | ------------------------------ |
| `integer` | `integer_ascii`     | `[+-]?(0\|[1-9][0-9]*)`, dígitos ASCII, int64                                               | sin `+`; `-0` → `0`            |
| `decimal` | `decimal_dot`       | `[+-]?(0\|[1-9][0-9]*)(\.[0-9]+)?`, precisión ≤ 38 tras cuantizar a la escala con HALF_EVEN | escala fija; sin cero negativo |
| `date`    | `iso_date`          | `YYYY-MM-DD`, años 0001–9999, calendario válido                                             | ISO                            |
| `boolean` | `boolean_lowercase` | `true` o `false` exactos                                                                    | booleano                       |

Sin notación exponencial (`1e5`), separadores de miles, comas decimales ni dígitos no ASCII. **No se recortan espacios**: `" 12"` y `"12 "` (NBSP) fallan con motivo «espacios en los bordes»; el plan debe recortar antes. Pares tipo/formato incompatibles se rechazan como parámetros inválidos. Un decimal con más decimales que la escala se **redondea** (1.235 → 1.24) y se cuenta en `rounded_cells`; superar 38 dígitos es error.

Motivos de error: `whitespace`, `exponent`, `leading_zero`, `invalid_format`, `out_of_range`, `precision_exceeded`, `invalid_date`, `invalid_boolean` y, en deduplicación, `null_key`.

### Identificadores: dos líneas de defensa

1. **Salvaguarda semántica.** Si el plan fija una revisión semántica en la que la columna está confirmada como `identifier`, convertirla a `integer` o `decimal` exige `confirm_identifier_conversion: true`. Sin ella, la validación del plan devuelve `IDENTIFIER_CONVERSION_UNCONFIRMED` (se resuelve en el paso) y la vista previa responde 422 `PLAN_INCOMPLETE`. La UI pide marcar la confirmación y no genera la vista previa hasta entonces.
2. **Gramática estricta.** Aunque no haya revisión semántica fijada (y la salvaguarda no actúe), un código con ceros a la izquierda como `"007"` **no cumple** `integer_ascii` ni `decimal_dot`: convertirlo perdería información (`"007"` y `"7"` serían el mismo número). La conversión falla con motivo `leading_zero` y no se publica nada. Es la red de seguridad para identificadores que nadie ha declarado; está probada sin revisión semántica (`test_cleaning_cast.py`) y de punta a punta con ella (`test_cleaning_api.py`, `cleaning-cast.spec.ts`).

Un identificador numérico sin ceros a la izquierda (`"12"`) sí convierte si se confirma: la decisión es del usuario, no se infiere.

## Política de errores: estricta

Un solo valor que no convierte (o una clave nula con `reject`) hace fallar la vista previa con `CONVERSION_FAILED` / `NULL_KEY_REJECTED`: no hay efecto aprobable ni versión derivada. El detalle (conteo exacto y hasta 50 casos) se guarda por intento y la vista previa lo expone en `failure`. Políticas «a nulo» o «excluir fila» quedan fuera de esta fase.

Limitaciones conocidas: cada `cast` convierte una columna y el primer paso que falla detiene la cadena, así que si dos columnas tienen valores inválidos la vista previa sólo lista los de la primera; los de la siguiente aparecen al corregirla. La UI separa los marcadores por comas, de modo que un token que contenga una coma sólo puede declararse con el editor de planes.

## Consecuencias de los tipos reales

- **Parquet tipado**: `Int64`, `Decimal(38, 0..12)`, `Date`, `Boolean` o texto. Cualquier otro tipo físico se rechaza (`UNSUPPORTED_COLUMN_TYPE`); ya no existe `UNSUPPORTED_TABLE_TYPE` en ingesta. Cleaning conserva la comprobación de texto en ejecución como `COLUMN_TYPE_MISMATCH`.
- **Hash lógico** (`platform/tabular.py`, único para ingesta y limpieza): esquema con `technical_type` y `type_parameters`; enteros y decimales como cadenas canónicas, fechas ISO, booleanos JSON (§6). Las tablas de texto conservan exactamente su hash. Si el esquema declarado no coincide con el Parquet: `SCHEMA_MISMATCH`.
- **Perfil**: una columna tipada no usa expresiones regulares; su tipo sugerido es el técnico y la estadística numérica sale de los valores (misma precisión de 50 dígitos). **Calidad**: Q-003 sólo en texto; Q-001 y Q-002 comparan valores tipados. **Vista previa de ingesta**: cadenas canónicas y sin `pl.col(nombre)` (corrige la observación de Fase 5 sobre encabezados como `^id$`).
- **Validación de planes**: cada operación declara los tipos que admite y su esquema de salida; el esquema se propaga paso a paso (`COLUMN_TYPE_MISMATCH`, p. ej. recortar después de convertir).
- **Efecto**: una celda está modificada si cambia de valor **o de tipo** conservando un valor no nulo (§6); el manifiesto añade `rounded_cells` y el esquema de salida tipado.

## Problemas de validación nuevos

| Código                              | Se produce cuando                                                             | Se resuelve en |
| ----------------------------------- | ----------------------------------------------------------------------------- | -------------- |
| `COLUMN_TYPE_MISMATCH`              | la columna no tiene un tipo que la operación admita en ese paso               | paso           |
| `IDENTIFIER_CONVERSION_UNCONFIRMED` | conversión numérica de un identificador confirmado sin confirmación explícita | paso           |

## API 0.8

Cambios aditivos: `cleaning.normalize_null_tokens@1`, `cleaning.cast@1` y `cleaning.deduplicate@1` en `/operations` (`analysis-v3`); `PreviewView.failure` (`code`, `total`, `samples`); `EffectManifest.rounded_cells`; `ColumnProfile.technical_type` admite los cinco tipos; dos códigos de problema nuevos; `GET /api/v1/versions/{id}` (arreglo de Fase 5). Los planes guardados conservan su catálogo y su hash; sus validaciones se recalculan con `analysis-v3`.

## Persistencia

Migración **0007**, sólo aditiva: `execution_error_details` (executions) guarda el detalle estructurado de un intento fallido — código y JSON — uno por intento, inmutable (`dataflow_immutable_record`). Executions no interpreta su contenido; cleaning lo lee para la vista previa. El downgrade se rechaza si hay detalles.

**Actualizar desde 0.7 / esquema 0006**: desplegar API y worker juntos. Las versiones, diagnósticos y hashes existentes no cambian (prueba dorada y verificación sobre una base con 90 versiones). Como en 0.7, un despliegue invalida las aprobaciones pendientes de aplicar (cambia el hash de entorno): hay que repetir la vista previa.

## Pruebas

- Prueba dorada (`test_text_golden.py`), capturada antes de cualquier cambio: esquema y hash lógico, perfil, calidad, vista previa de ingesta con cada filtro y efecto de cuatro limpiezas sobre los CSV del repositorio.
- Conversión (`test_cleaning_cast.py`): `+0`, `-0`, `007`, `1e5`, `2026-02-30`, `0000-01-01`, `TRUE`, exceso de escala (HALF_EVEN), más de 38 dígitos, fuera de int64, NBSP, dígitos no ASCII, detalle limitado a 50 con conteo completo y filas de origen tras un filtro.
- Marcadores y deduplicación (`test_cleaning_tokens_dedupe.py`): coincidencias parciales, claves nulas en ambos modos, valores tipados, determinismo.
- Tipos (`test_tabular_types.py`), validación (`test_planning_domain.py`), ejecutor (`test_cleaning_types_runner.py`: derivada tipada, fallo sin publicación), API (`test_cleaning_api.py`: salvaguarda y segunda línea de defensa), migración 0007.
- Navegador: `cleaning-cast.spec.ts` — conversión inválida que bloquea la publicación y, corregida, crea v2 tipada; **requisito semántico** de punta a punta (identificador confirmado en Entendimiento → confirmación exigida en Limpieza → `"001"` no convierte). Es el E2E de requisito semántico pendiente desde [Fase 4](phase-4.md), con la salvaguarda de identificadores como primer requisito real.

### Verificación local — 2026-11-05

Python 3.12.10. Backend: 244 pruebas, Ruff y mypy strict sin errores, contrato exportado sin diferencias. Web: typecheck, lint, format y build correctos. E2E en serie: 14/14.

## 6B · Pendiente

Catálogo `csv-quality-v2` (obligatoriedad, unicidad de clave, rango, valores de catálogo, formato convertible) con `origin: technical | user`, conjuntos de reglas por proyecto con revisiones inmutables (migración 0008), `quality.evaluate@2` con referencia exacta a la revisión de reglas como parámetro del paso, API 0.9 y ADR-017.
