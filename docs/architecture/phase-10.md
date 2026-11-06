# Fase 10 — Copiloto de IA integrado

API 0.14. [ADR-022](../adr/022-ai-copilot.md). Se apoya en el catálogo y la validación de planes ([Fase 4](phase-4.md)), el ciclo de vista previa y aprobación ([Fase 5](phase-5.md)) y las métricas, `analytics.query@2` y la evidencia por cifra ([Fase 7](phase-7.md)).

Objetivo: que el usuario pida y entienda análisis en lenguaje natural. **El copiloto no tiene poderes propios**: traduce una petición a una propuesta del catálogo, que pasa por la misma validación, vista previa y aprobación que si la creara la persona. **Ninguna cifra sale del modelo**: todas salen de resultados calculados.

## Recorrido

CSV propio procesado → panel **Copiloto de análisis** (debajo de la etapa) → «Compara las ventas mensuales por región» →

1. Si falta una definición de negocio, **pregunta** antes de proponer (p. ej. «Falta confirmar la fecha de negocio» con «Ir a Entendimiento»). La semántica la confirma la persona: el copiloto no puede escribirla.
2. Sin métrica para lo pedido, propone un **borrador de métrica** → «Crear métrica».
3. Con la métrica, propone una **consulta** de `analytics.query@2` validada por planning → «Ejecutar consulta» → «Consulta calculada».
4. «Explicar resultado» → texto con **cifras verificadas**: cada cifra es un enlace a «De dónde sale este número».

Una limpieza propuesta («Abrir plan de limpieza») se guarda como plan y abre la etapa Limpieza en «Generar vista previa»: aprobación del efecto exacto y aplicación como en la Fase 5. La conversación se conserva por proyecto. El guion de demostración del fixture no cambia y sigue etiquetado.

Con la IA desactivada o sin clave, el panel muestra «Copiloto no disponible» con el motivo y todo lo demás funciona igual.

## Acciones (salida estructurada)

| Acción                  | Carga del modelo                                                        | Lo que hace el servidor                                                                                                           |
| ----------------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `propose_query`         | IDs de métricas y columnas, filtros, agrupación, periodo, opciones `@2` | Resuelve los IDs (nunca nombres), añade `content_sha256`, valida el plan con planning sin guardarlo (`validate_draft`)            |
| `propose_metric`        | etiqueta, columna medida, agregación, fecha, filtros                    | Comprueba columnas y tipos; la persona la crea con el `POST` de métricas existente                                                |
| `propose_cleaning_plan` | pasos `cleaning.*` con parámetros JSON                                  | Rechaza lo que no es limpieza, valida con planning; guardarlo nunca lo ejecuta (`APPROVAL_REQUIRED` sigue protegiendo el plan)    |
| `ask_clarification`     | tema (`metric`, `measure`, `currency`, `business_date`, `dimension`)    | Enlaza a Entendimiento o a Análisis                                                                                               |
| `explain_result`        | texto con `{{evidence:id}}` y `{{label:id}}`                            | Sustituye cada referencia por el valor exacto y formateado o la etiqueta del grupo; recalcula cada dirección como `GET /evidence` |

Una propuesta inválida se muestra con sus problemas (los mismos códigos de planning y `UNKNOWN_METRIC`, `UNKNOWN_COLUMN`, `NOT_A_CLEANING_OPERATION`, `EMPTY_QUERY`) y su botón queda desactivado; la acción responde 409 `PROPOSAL_INVALID`. Una salida fuera del esquema (otra acción, carga incompleta) se descarta (`AI_INVALID_OUTPUT`). No hay Python ni SQL generado por el modelo.

## Cifras verificadas

- En `explain_result` el modelo no escribe números: cita `{{evidence:<evidence_id>}}` y el servidor pone el valor en formato colombiano (`1.234,56`, con la moneda o unidad de la definición, `%` en variaciones y participación, «puesto n» en el ranking) sin perder dígitos de un `Decimal(38, s)`.
- Las etiquetas de grupo y periodo contienen dígitos («2026-01»): se citan con `{{label:<evidence_id>}}`.
- Una referencia inexistente, de otra ejecución, mal formada o un marcador desconocido **invalidan toda la respuesta** (`INVALID_EVIDENCE_REFERENCE`).
- Cualquier número escrito libremente, en cualquier respuesta (`1.234,56`, `1,234.56`, `12,5 %`, `2026`, `Q1`), se sustituye por «[cifra no verificada]» y se cuenta (`unverified_numbers`). Los números escritos con letras no se detectan (limitación documentada en el ADR).

## Datos que salen hacia el proveedor (aprobado)

En todas las llamadas: prompt de sistema versionado, mensaje del usuario y los últimos 10 mensajes (los del copiloto con sus referencias, nunca con las cifras sustituidas); de la tabla, filas y columnas y por columna ID, **nombre**, tipo técnico, nulos y distintos; de la semántica, rol, si está confirmada, unidad o moneda y **descripción**, más **descripción del dataset** y **grano de fila**; de las métricas, ID, **etiqueta**, agregación, columnas y **filtros con sus valores**. Sólo en «Explicar resultado», además: definiciones y conteos del resultado y, por cifra (hasta 200), `evidence_id`, métrica, **valores de las dimensiones del grupo**, periodo y valor calculado.

Nunca: filas, valores de ejemplo del perfil, resumen numérico del perfil (total, media, mínimo, máximo), diagnóstico de calidad, nombre del archivo, nombre o descripción del proyecto, identidad del usuario ni hashes de contenido.

Lo **destacado** viene de los datos o de textos de personas: va dentro de `{"dato_no_confiable": ...}` en un bloque `<contexto_autorizado>` con `<`, `>` y `&` escapados, de modo que un dato no puede cerrar el bloque ni pasar por instrucción.

## Configuración

| Variable                               | Por defecto       | Uso                                                                     |
| -------------------------------------- | ----------------- | ----------------------------------------------------------------------- |
| `DATAFLOW_AI_PROVIDER`                 | `disabled`        | `disabled`, `fake` (pytest, CI, E2E) o `anthropic`                      |
| `DATAFLOW_AI_MODEL`                    | `claude-opus-5-5` | modelo del proveedor                                                    |
| `DATAFLOW_AI_EFFORT`                   | `low`             | profundidad de razonamiento (`low`, `medium`, `high`)                   |
| `DATAFLOW_AI_API_KEY`                  | —                 | clave en el `.env` local (ignorado por git)                             |
| `DATAFLOW_AI_API_KEY_FILE`             | —                 | archivo de secreto (Docker: `/run/secrets/ai_api_key`); tiene prioridad |
| `DATAFLOW_AI_TIMEOUT_SECONDS`          | 30                | plazo por llamada (5–120)                                               |
| `DATAFLOW_AI_MAX_OUTPUT_TOKENS`        | 4000              | tokens de salida por llamada                                            |
| `DATAFLOW_AI_USER_DAILY_TOKENS`        | 200000            | límite por usuario y día UTC                                            |
| `DATAFLOW_AI_PROJECT_MONTHLY_COST_USD` | 5                 | límite de costo estimado por proyecto y mes UTC                         |

En Docker la clave es un secreto (`DATAFLOW_AI_API_KEY_SECRET_FILE` apunta al archivo; por defecto un marcador vacío versionado, así que `compose up` funciona sin clave). La clave nunca se registra, no aparece en OpenAPI ni llega al frontend, y se pasa explícitamente al cliente del SDK (que no busca otras credenciales). Superar un límite: 429 `AI_BUDGET_EXCEEDED` con el límite y cuándo se renueva; el estado lo muestra como `budget_exhausted`.

## API 0.14

| Ruta                                            | Función                                                                        |
| ----------------------------------------------- | ------------------------------------------------------------------------------ |
| GET `/projects/{id}/copilot/status`             | Disponible o motivo (`disabled`, `missing_key`, `budget_exhausted`) y uso      |
| GET/POST `/projects/{id}/copilot/conversations` | Conversaciones del proyecto; alta con `Idempotency-Key`                        |
| GET `/copilot/conversations/{id}`               | Mensajes con sus propuestas y las acciones registradas                         |
| POST `/copilot/conversations/{id}/messages`     | Petición → respuesta (`Idempotency-Key`; misma clave y texto: misma respuesta) |
| POST `/copilot/conversations/{id}/explanations` | Explica una ejecución terminada de `analytics.query` del proyecto              |
| POST `/copilot/messages/{id}/run-query`         | Guarda el plan de la propuesta y lo encola                                     |
| POST `/copilot/messages/{id}/create-metric`     | Crea la métrica propuesta                                                      |
| POST `/copilot/messages/{id}/cleaning-plan`     | Guarda el plan de limpieza (no lo ejecuta)                                     |

Sesión y propietario en todas (ajeno: 404); Origin y CSRF en las mutaciones. Las tres acciones son idempotentes por mensaje (repetirlas devuelve la misma acción registrada). Errores: 503 `COPILOT_UNAVAILABLE`, 429 `AI_BUDGET_EXCEEDED`, 409 `PROPOSAL_INVALID`, 409 `RESULT_NOT_READY`. Una llamada que falla en el proveedor (`AI_TIMEOUT`, `AI_RATE_LIMITED`, `AI_REFUSED`, `AI_INVALID_OUTPUT`, `AI_UNAVAILABLE`) queda en la conversación como mensaje de error. Cambios aditivos; planning añade `validate_draft` (sin ruta nueva).

## Arquitectura y persistencia

- `integrations/ai`: puerto `AIProvider` (salida Pydantic, `prompt_id` y versión, tokens, error con código), proveedor falso determinista y `anthropic_provider.py`, **único archivo que importa el SDK** (prueba AST). El SDK sólo se carga si la IA real está activada.
- Módulo `copilot`: sólo usa sus puertos, el puerto de IA y `audit` (prueba AST); bootstrap traduce planning, métricas, ejecuciones, semántica y evidencia a hechos simples (`bootstrap/copilot_access.py`). Prompts versionados en `copilot/prompts.py` (`copilot-turn@v1`, `copilot-explain@v1`); la simulación del proveedor falso en `copilot/simulation.py`.
- Migración **0012**, sólo aditiva: `copilot_conversations`, `copilot_messages`, `copilot_action_links`, `copilot_requests` y `copilot_ai_calls`, todas inmutables por trigger. Downgrade bloqueado si hay conversaciones o llamadas.
- Registro de cada llamada (`copilot_ai_calls`): proveedor, modelo que respondió, parámetros, prompt y versión, hash del contexto, tokens (entrada, salida y caché), costo estimado, latencia, resultado (`accepted`, `rejected`, `provider_error`) y resumen de la validación (códigos y conteos). Nunca contenido tabular ni el texto del prompt.
- Dependencia nueva: `anthropic` 2.6 (con `httpx2`, `jiter`, `docstring_parser`, `sniffio`, `truststore`), Python puro. **Actualizar desde 0.13 / esquema 0011**: instalar la dependencia; el worker no cambia.

## Pruebas

Suite de evaluación en `apps/api/tests/ai/` con el proveedor falso (ninguna prueba necesita clave ni red):

- Ciclo completo por la API: aclaración → métrica → consulta → ejecución → explicación con cifras iguales a las de `GET /evidence`.
- Estructura: acción fuera del esquema, carga incompleta y timeout descartados y registrados.
- Catálogo: operaciones inexistentes o ajenas a limpieza, métrica inexistente y consulta sin métricas rechazadas; validación de planning en la tarjeta; un plan de limpieza guardado no se puede ejecutar sin aprobación.
- Cifras: números libres en ambos formatos retirados; referencias ajenas, inexistentes, mal formadas o desconocidas invalidan la respuesta; formato colombiano sin pérdida de dígitos.
- Aclaraciones: sin medida confirmada y sin fecha de negocio; preguntar no crea nada.
- Inyección: un encabezado de columna que pide «ignorar las instrucciones» y cerrar el bloque viaja sólo como dato marcado y escapado; un modelo que «obedece» sólo produce una propuesta inválida.
- Privacidad del contexto y del registro, límites de tokens y costo, idempotencia, accesos cruzados y CSRF; IA desactivada y sin clave.
- Casos reales opcionales (`test_ai_live.py`): sólo con `DATAFLOW_AI_LIVE_TESTS=1` y una clave.
- Migración 0012; las pruebas de 0005–0011 excluyen sus tablas nuevas. Arquitectura: copilot y SDK del proveedor.
- Navegador (`copilot.spec.ts`, API con `DATAFLOW_AI_PROVIDER=fake`): petición → aclaración → Entendimiento → métrica → consulta → explicación con «De dónde sale este número»; y plan de limpieza → Limpieza → vista previa con aprobación pendiente.

### Verificación local — 2026-11-06

Python 3.12.10. Backend: 405 pruebas y 4 casos reales omitidos sin clave (Ruff y mypy strict sin errores), contrato exportado sin diferencias y `contracts:check` correcto. Web: typecheck, lint, format y build correctos. E2E en serie: 21/21.
