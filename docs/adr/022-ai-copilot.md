# ADR-022 — Copiloto de IA: puerto AIProvider, propuestas del catálogo y cifras sólo por evidencia

Estado: implementado en Fase 10 / API 0.14. Documentación: [Fase 10](../architecture/phase-10.md). Concreta el [ADR-006](decisions.md) y se apoya en [ADR-014](014-planning-catalog.md), [ADR-015](015-supervised-cleaning.md) y [ADR-018](018-deterministic-business-analysis.md).

## Contexto

El usuario quiere pedir y entender análisis en lenguaje natural. Un modelo de lenguaje no es determinista, puede inventar cifras y lee texto que viene de los datos (nombres de columnas, descripciones, etiquetas) y que puede contener instrucciones. El producto ya tiene un catálogo validado, un ciclo de aprobación y evidencia por cifra: el copiloto debe usarlos, no rodearlos.

## Decisión

- **Sin poderes propios.** El modelo sólo devuelve una de cuatro acciones estructuradas (`propose_query`, `propose_metric`, `propose_cleaning_plan`, `ask_clarification`) o un texto de explicación. El servidor resuelve los IDs contra el contexto, valida con planning (`validate_draft`, sin guardar) y muestra la propuesta. Ejecutar, crear una métrica o guardar un plan de limpieza son botones explícitos que usan los casos de uso existentes; una limpieza nunca se aplica sin la vista previa y la aprobación de la Fase 5.
- **Ninguna cifra sale del modelo.** En una explicación cita `{{evidence:id}}`; el servidor pone el valor exacto, recalculando su dirección. Una referencia inválida invalida toda la respuesta; un número escrito libremente se retira y se marca.
- **Puerto `AIProvider` en `integrations/ai`** con salida Pydantic, prompts versionados, timeout y límite de tokens. Un **proveedor falso determinista** cubre pytest, CI y E2E sin clave ni red.
- **Proveedor y SDK** (decisión bloqueante aprobada): Anthropic con el SDK oficial `anthropic` y `claude-opus-5-5` con `effort: low`, configurable con `DATAFLOW_AI_MODEL`. Frente a OpenAI (equivalente en salida estructurada y costo) y a un modelo local (máxima privacidad, pero salida estructurada menos fiable para planificar en español y una imagen de varios GB con GPU complicada en Windows y Docker). Salida estructurada con `messages.parse` y el esquema Pydantic; prompt de sistema cacheado; respaldo del servidor ante rechazos (`fallbacks: "default"`) en los modelos que lo admiten, registrando el modelo que respondió.
- **Clave y activación** (aprobada): IA desactivada por defecto (`DATAFLOW_AI_PROVIDER=disabled`). La clave va en el `.env` local, ignorado por git, o en un secreto de Docker (`DATAFLOW_AI_API_KEY_FILE`, que tiene prioridad). Nunca en el repositorio, los logs, OpenAPI ni el frontend, y se pasa explícitamente al cliente.
- **Privacidad** (aprobada): contexto mínimo, sin filas, sin valores de ejemplo ni resumen numérico del perfil. Al explicar un resultado sí se envían sus valores calculados y las etiquetas de sus grupos. Todo texto de los datos o de personas va marcado como `dato_no_confiable` y escapado. Riesgo aceptado: agrupar por una columna con datos personales envía esas etiquetas al explicar.

### Decisiones tomadas en la implementación

- `{{label:id}}` además de `{{evidence:id}}`: las etiquetas de grupo y periodo contienen dígitos y no pueden escribirse sin marcarse como cifras.
- Detección de números libres estricta: cualquier dígito fuera de una referencia (también años, posiciones, «Q1»). Los números escritos con letras no se detectan; se acepta porque la sustitución por evidencia es la fuente de verdad y el prompt lo prohíbe.
- Formato colombiano sobre la cadena canónica: `format(Decimal, "f")` usa la precisión del contexto (28 dígitos) y redondeaba un `Decimal(38, s)`.
- Acciones idempotentes **por mensaje** (una ejecución, una métrica o un plan por propuesta; claves derivadas del mensaje) en lugar de `Idempotency-Key`; crear conversaciones, enviar mensajes y pedir explicaciones sí la exigen.
- Menos datos de los aprobados: el diagnóstico de calidad no se envía (los nulos del perfil bastan para proponer limpiezas).
- Una llamada fallida queda como mensaje de error en la conversación y en el registro (`provider_error`) para auditar costo y causa.
- Explicar es una acción explícita sobre una ejecución terminada, no automática al calcular.
- Límites contados sobre el propio registro de llamadas (tokens del usuario en el día UTC; costo estimado del proyecto en el mes UTC); el costo usa precios de lista por modelo y es `null` para un modelo desconocido.
- La simulación del proveedor falso vive en el módulo copilot (`simulation.py`); `integrations/ai` sólo recibe una función y no conoce el negocio.
- Las respuestas se guardan; no se promete regenerar la misma respuesta.

## Alternativas

- **SDK directo en los casos de uso**: acopla el producto al proveedor y complica las pruebas.
- **Que el modelo escriba cifras y luego compararlas**: frágil (formatos, redondeos) y deja pasar cifras plausibles pero falsas.
- **SQL o Python generado por el modelo**: fuera del catálogo y de la validación; descartado por el ADR-006.
- **Herramientas (tool use) que ejecutan acciones**: darían al modelo poder de ejecutar; la salida estructurada deja la decisión en un botón de la persona.

## Consecuencias

- Toda capacidad del copiloto está acotada por el catálogo y la validación existentes: una operación nueva en el catálogo lo amplía sin tocar la seguridad.
- Dependencia nueva `anthropic` (con `httpx2`, `jiter`, `docstring_parser`, `sniffio`, `truststore`).
- Evaluación continua sin costo con el proveedor falso; los casos reales, opcionales, miden el comportamiento del modelo.
- El costo por petición depende del modelo y del tamaño del contexto. Con la configuración por defecto, el orden de magnitud es de céntimos de dólar por turno.
