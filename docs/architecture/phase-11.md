# Fase 11 — Automatización determinista

> **Fase 13 ([ADR-026](../adr/026-fully-automatic-single-path.md))**: la sesión de análisis (11A), el pipeline gobernado por política (11B–11E) y la auditoría textual con botón (11F) se retiraron; la migración 0019 elimina las tablas de 0013–0017. Siguen vigentes 11.0, la propuesta de limpieza calculada en el backend (11A) y `analytics.query@3` (11E). Este documento se conserva como historia.

Estado: **11.0 a 11E implementadas** (propuesta de limpieza en el backend, sesión de análisis con fuente única, aprobación por política, pipeline automático durable, moldes con interpretación reutilizable y dashboard automático). 11F se entrega en su propio PR y no describen funcionalidades implementadas salvo donde una sección lo indique. [ADR-023](../adr/023-policy-governed-automation.md). Las fuentes nuevas (Excel, SQL Server, PDF) son la [Fase 12](phase-12.md).

## Objetivo

Construir este recorrido sobre el sistema existente, con la menor interacción posible:

**seleccionar una fuente → validar → interpretar → aplicar políticas → calcular → publicar dashboard → auditoría textual opcional.**

## Decisiones

- **Polars** sigue siendo el motor único de cálculo; agregaciones con aritmética exacta (`int`/`Decimal`, Fase 7).
- **Una tabla activa por sesión de análisis**, independiente de la sesión de autenticación.
- Originales, versiones y resultados históricos **inmutables**.
- SQL Server se consulta durante la extracción, **nunca** durante el renderizado (Fase 12).
- **Ninguna transformación se publica sin aprobación humana o autorización explícita de una política.**
- Dentro del modo automático **la IA no propone acciones ejecutables**: sólo explica resultados publicados. El copiloto de la Fase 10 sigue igual fuera del modo automático.
- El modo automático está **desactivado por defecto**.
- Se reutilizan los módulos actuales; **no** se crea un motor paralelo.

## Arquitectura

```
Adaptadores de fuentes (CSV hoy; Excel, SQL Server, PDF en Fase 12)
        │
        ▼
Original o extracción inmutable + hash
        │
        ▼
Representación tabular
        │
        ▼
Perfil y calidad técnica
        │
        ▼
Interpretación y molde ──(sin mapeo compatible)──▶ Revisión necesaria
        │
        ▼
Plan determinista
        │
        ▼
Vista previa → evaluación de política
        │
   ┌────┴─────────────┐
   ▼                  ▼
Aprobado         Revisión necesaria
   │
   ▼
Derivada + diagnóstico + reglas
   │
   ▼
Análisis determinista
   │
   ▼
Dashboard y evidencia persistidos
   │
   ▼
Auditoría textual IA (opcional, trabajo independiente)
```

| Componente          | Responsabilidad                                                | Estado                   |
| ------------------- | -------------------------------------------------------------- | ------------------------ |
| `ingestion`         | Extraer una tabla de la fuente elegida                         | existente (CSV); Fase 12 |
| `analysis_sessions` | Mantener una entrada activa y su historial de selección        | nuevo (11A)              |
| `understanding`     | Interpretación semántica y mapeos confirmados                  | existente; amplía (11D)  |
| `templates`         | Detectar moldes candidatos y producir definiciones de análisis | nuevo (11D)              |
| `automation`        | Políticas, evaluación de efectos y estado del pipeline         | nuevo (11B–11C)          |
| `cleaning`          | Propuesta, vista previa, aprobación y transformaciones         | existente; amplía (11A)  |
| `analytics`         | Cálculos y evidencia                                           | existente; amplía (11E)  |
| `dashboards`        | Presentación persistida de resultados                          | existente                |
| `copilot`           | Auditoría textual posterior, sin capacidad de ejecución        | existente; amplía (11F)  |
| `bootstrap`         | Conectar módulos mediante puertos                              | existente                |

`SingleSourceAnalyst`, si se conserva el nombre, es una **fachada de aplicación** sobre estos servicios: no contiene el procesamiento ni mantiene un DataFrame global. El equivalente persistente de «el DataFrame activo» es la representación tabular de la versión activa de la sesión.

## Entregas

| Entrega | Contenido                                        | Depende de |
| ------- | ------------------------------------------------ | ---------- |
| 11.0    | Estabilización del motor                         | —          |
| 11A     | Sesión con fuente única y propuesta centralizada | 11.0       |
| 11B     | Políticas y limpieza automática                  | 11A        |
| 11C     | Orquestación durable                             | 11B        |
| 11D     | Moldes e interpretación reutilizable             | 11C        |
| 11E     | Dashboard automático determinista                | 11D        |
| 11F     | Auditoría textual IA                             | 11E        |

## 11.0 · Estabilización del motor

Debe terminar **antes** de habilitar aprobaciones automáticas: una política no puede autorizar efectos calculados por un motor con errores conocidos.

Errores corregidos:

| Problema                                                                                                                                                                                   | Corrección                                                                                                                                                    |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `cleaning.filter_rows@1` con `is_null` se validaba para cualquier tipo, pero la ejecución usaba `text_column()`, que rechaza columnas no texto (`COLUMN_TYPE_MISMATCH`)                    | `any_column()` en `cleaning/infrastructure.py`: `is_null` funciona en texto, entero, decimal, fecha y booleano; `is_whitespace_only` sigue exigiendo texto    |
| Las sumas acumuladas de `sum`/`avg` (`acc.total += value`) usaban la precisión por defecto de Python (28 dígitos): un total de `Decimal(38, s)` de 29 a 38 dígitos se redondeaba sin aviso | `aggregate()` acumula dentro del contexto exacto                                                                                                              |
| La variación absoluta (`Decimal(current) - Decimal(base)`) y el total del % del total (`sum(values, Decimal(0))`) también se calculaban con 28 dígitos                                     | Ambos dentro del contexto exacto                                                                                                                              |
| Precisión distinta según el cálculo: media y conversión con 2×38 dígitos, variación, % del total y cuantización con 4×38                                                                   | Un único contexto: `platform/decimal_context.py` (`exact_context()`, 4×38 dígitos) en `analytics/engine.py`, `platform/tabular.py` y `platform/conversion.py` |

Con 4×38 dígitos, una suma de N valores de hasta 38 dígitos nunca se redondea; los cocientes (media, variación %, participación) se cuantizan después con HALF_EVEN; un resultado de más de 38 dígitos sigue siendo `RESULT_PRECISION_EXCEEDED`. El resumen numérico del perfil (`understanding`, 50 dígitos, Fase 6) y el formato de cifras del copiloto no cambian: no son cálculo del motor y el perfil está protegido por la prueba dorada de texto.

Pruebas: `tests/test_engine_stabilization.py` (filtro de nulos en los cinco tipos y combinado, texto obligatorio para espacios, columnas desconocidas; suma, media, variación y % del total con valores de 30 dígitos; error explícito por encima de 38 dígitos). `alembic check` sigue en CI para verificar que los modelos registrados coinciden con las migraciones (corregido en el PR #1).

Antes de incorporar automatización se ejecuta la batería completa (backend, contratos, frontend, E2E, migraciones).

Cierre: filtrar nulos funciona en los cinco tipos; los cálculos son exactos dentro del rango admitido; fuera de rango hay un error explícito (`RESULT_PRECISION_EXCEEDED`), nunca un redondeo silencioso; todas las pruebas aprobadas.

## 11A · Sesión con fuente única y propuesta centralizada

### Sesión de análisis

Identifica proyecto y propietario, revisión de selección, versión y representación activas, estado de preparación, y fecha y actor de cada selección.

Reglas:

- Como máximo **una tabla activa** por sesión.
- **Una sesión por proyecto** en esta entrega (la API admite varias para no cerrar la puerta, pero crear una segunda devuelve la existente).
- Una carga candidata **no sustituye** a la activa hasta validarse; si falla, la fuente anterior sigue activa.
- Cambiar de fuente no modifica planes ni resultados históricos.
- Un resultado que termina después de cambiar la fuente queda asociado a **su** entrada original.
- La sesión **no** modifica `dataset_defaults` (versión predeterminada por dataset): son conceptos distintos. La sesión elige entre datasets (CSV A, Excel B); el predeterminado sigue siendo por dataset.

Persistencia: `analysis_sessions` (selección vigente: referencia mutable, con `revision` y control de concurrencia) y `analysis_session_input_revisions` (cada selección, inmutable por trigger).

**Implementado** (módulo `analysis_sessions`, migración **0013**, sólo aditiva):

- Una versión está **lista** cuando su procesamiento terminó bien y tiene tabla publicada (`AnalysisSessionInputs` en bootstrap). Seleccionar una en cola o en proceso responde 409 `INPUT_NOT_READY`; una que falló o se canceló, 409 `INPUT_INVALID`; una de otro proyecto, 404 `INPUT_NOT_FOUND`. En los tres casos la fuente activa no cambia.
- Cada selección guarda la versión, su número, tipo y nombre de archivo, y la **tabla exacta** (artefacto y SHA-256), con autor y fecha. Seleccionar la misma tabla activa no crea revisión; una `expected_revision` antigua responde 409 `ANALYSIS_SESSION_CONFLICT`. Auditoría: `analysis_session.input_selected`.
- Proyecto archivado: se puede consultar la sesión, no cambiar la fuente (409 `PROJECT_ARCHIVED`).
- Los planes, ejecuciones y resultados ya fijan su tabla de entrada (Fases 2 y 4): cambiar la fuente activa no los altera y un resultado que termina después conserva su entrada original.
- El módulo sólo usa sus puertos y `audit` (prueba AST); las pruebas de migraciones anteriores excluyen las tablas nuevas mediante `tests/migration_support.py`, que cada migración de la Fase 11 amplía.

| Ruta                                    | Función                                                          |
| --------------------------------------- | ---------------------------------------------------------------- |
| POST `/projects/{id}/analysis-sessions` | Crea la sesión del proyecto (201) o devuelve la existente (200)  |
| GET `/projects/{id}/analysis-session`   | Sesión del proyecto (404 si todavía no existe)                   |
| GET `/analysis-sessions/{id}`           | Fuente activa, revisión y estado (`empty` o `ready`)             |
| POST `/analysis-sessions/{id}/inputs`   | Selecciona una versión lista (`version_id`, `expected_revision`) |
| GET `/analysis-sessions/{id}/inputs`    | Historial de selecciones, de la más reciente a la más antigua    |

Pruebas: `tests/test_analysis_sessions.py` (una sesión por proyecto, candidata inválida o en cola que no sustituye a la activa, cambio de fuente con historial, plan anterior intacto, conflicto, sin cambios sin revisión, accesos y archivado) y `tests/test_migration_0013.py` (ida y vuelta, comparación de esquema, inmutabilidad y downgrade bloqueado).

### Propuesta de limpieza en el backend (implementada)

El borrador inicial se armaba en el frontend (`initialDraft` y `draftSteps` en `features/cleaning/proposal.tsx`). Ahora es una función pura del backend, `modules/cleaning/proposal.py`:

```
propose(columnas, incidencias de calidad, marcadores confirmados) → CleaningProposal (cleaning-proposal@1)
```

| Regla                                  | Propuesta                                                         |
| -------------------------------------- | ----------------------------------------------------------------- |
| Q-003 (sólo espacios)                  | Recortar la columna, sólo si es texto                             |
| Q-001 (celdas vacías)                  | Excluir registros con nulo en la columna, de cualquier tipo       |
| Q-002 (filas repetidas)                | Deduplicar por todas las columnas agrupando nulos                 |
| Marcadores confirmados en la semántica | Normalizarlos a nulo, sólo en columnas de texto                   |
| Conversiones de tipo                   | Nunca se proponen; sólo se muestra el tipo sugerido por el perfil |

La respuesta incluye el **borrador editable** por columna y los **pasos del catálogo** en el orden fijo (marcadores → recortar → convertir → excluir nulos → deduplicar), además de la tabla y la revisión semántica usadas. `GET /representations/{id}/cleaning-proposal` la expone (sólo lectura, sin guardar planes); bootstrap reúne los hechos con `CleaningProposalAccess` (columnas y revisión vigente de understanding, incidencias del diagnóstico de la versión).

La interfaz parte de esa propuesta (`draftFromProposal`) y la persona sigue editándola como antes; `draftSteps` del frontend sólo convierte las ediciones en pasos. La política de automatización (11B) se aplicará sobre esta misma propuesta.

Pruebas: `tests/test_cleaning_proposal.py` reproduce las reglas del frontend anterior (tipos admitidos por regla, orden de columnas, marcadores agrupados y sin repetidos, orden fijo de pasos, propuesta vacía) y, con PostgreSQL, comprueba la propuesta de `examples/ventas_calidad.csv` (recortar y excluir `importe`, deduplicar), que el plan resultante valida y que su vista previa se calcula. La arquitectura protege `proposal.py` igual que el resto del cálculo de cleaning (sin base de datos).

### Frontend

Indicador visible de fuente activa; sustitución explícita de fuente; aviso de cambios sin guardar (hook compartido existente); historial de entradas utilizadas.

**Implementado** (`features/analysis-sessions`): bajo la franja de la versión, «Fuente activa: vN · archivo» con «Es la que estás viendo» o «Ver fuente activa»; en una versión procesada que no es la activa, «Usar vN como fuente activa» abre una confirmación que explica que planes y resultados no cambian; «Historial (N)» lista las selecciones. Cambiar la fuente no navega, así que no puede perder borradores; cambiar de versión sigue pasando por el aviso de cambios sin guardar. E2E: `analysis-session.spec.ts`.

Cierre: subir CSV A; intentar un CSV B inválido y comprobar que A sigue activo; cambiar después a C sin alterar los análisis de A.

## 11B · Políticas y limpieza automática

### Política versionada

Una familia por proyecto, con revisiones inmutables como semántica, reglas, métricas y dashboards (`expected_revision`, `Idempotency-Key`, sin cambios no hay revisión; 409 `AUTOMATION_POLICY_CONFLICT`).

| Campo                    | Valor inicial | Significado                                                         |
| ------------------------ | ------------- | ------------------------------------------------------------------- |
| `enabled`                | `false`       | Interruptor del pipeline para cargas nuevas                         |
| `allowed_operations`     | `[]`          | Operaciones de limpieza del catálogo autorizadas                    |
| `column_scopes`          | `{}`          | Por operación, columnas (o roles) en las que se permite             |
| `null_tokens_by_column`  | `{}`          | Marcadores de nulo exactos por columna                              |
| `max_excluded_rows_pct`  | `0`           | Barrera global de filas excluidas                                   |
| `max_nulls_created_pct`  | `0`           | Barrera global de nulos creados                                     |
| `max_rounded_cells`      | `0`           | Celdas redondeadas por conversión a decimal                         |
| `min_output_rows`        | `1`           | Filas mínimas de salida                                             |
| `evaluate_quality_rules` | `true`        | Evaluar el conjunto de reglas aplicable (Fase 6B) sobre la derivada |

Los porcentajes globales son **barreras adicionales, no autorización suficiente** para eliminar datos: una operación debe estar en `allowed_operations` y en su `column_scopes`.

**Perfiles predefinidos.** Con los valores iniciales el modo automático no hace nada. La interfaz ofrece perfiles que rellenan la política para que la persona la revise y guarde; nunca se activan solos:

| Perfil        | Autoriza                                                                            |
| ------------- | ----------------------------------------------------------------------------------- |
| Conservador   | Recortar espacios y marcadores de nulo por columna; sin exclusiones ni conversiones |
| Tipado        | Conservador + conversiones sin redondeo en columnas no identificador                |
| Personalizado | Lo que la persona configure                                                         |

### Evaluación

```
evaluate(policy, validated_plan, effect_manifest, authorization_context) → approved | blocked(reasons)
```

Dos partes separadas:

- **Evaluación pura de límites** (dominio, sin base de datos): operaciones y columnas autorizadas, efecto por operación y columna, totales.
- **Comprobación transaccional**: permisos vigentes, política no revocada ni sustituida, aprobación compatible, pipeline no cancelado.

El manifiesto del efecto (Fase 5) se amplía con **efectos por operación y columna** además de los totales, para que una modificación importante en una columna no quede diluida en el porcentaje global. Es un cambio aditivo del manifiesto: los efectos ya publicados conservan su `effect_sha256`; las vistas previas nuevas tienen el manifiesto ampliado y, como en cada despliegue (ADR-015), las aprobaciones pendientes de aplicar se invalidan y hay que repetir la vista previa.

### Restricciones fijas

Ninguna política puede relajarlas:

- No convertir identificadores a números automáticamente.
- No ejecutar operaciones fuera del catálogo.
- No publicar conversiones fallidas (`CONVERSION_FAILED`, `NULL_KEY_REJECTED`).
- No reutilizar una aprobación incompatible (otro efecto, plan, entrada o entorno).
- No continuar en silencio si falla una columna necesaria para el análisis.

### Aprobación

Persistencia: `automation_policy_families`, `automation_policy_revisions`, `automation_policy_save_requests` y `automation_approvals`.

`cleaning_approvals.approved_by` sigue exigiendo un usuario y no se modifica. La aprobación automática registra ahí a la **persona que autorizó la política**, y `automation_approvals` añade:

- **Actor humano**: autora de la revisión de política.
- **Ejecutor**: automatización (pipeline y paso).
- **Revisión exacta de política** y **efecto autorizado** (`effect_sha256`), con el resultado de la evaluación.

Sin fila en `automation_approvals`, la aprobación es humana. Desactivar o sustituir la política revoca las aprobaciones automáticas aún no aplicadas.

Cierre: una transformación autorizada publica una derivada; la misma operación fuera de sus límites se detiene con un motivo verificable y permite continuar manualmente.

### Implementación (11B)

Módulo `automation` (sólo sus puertos y `audit`, prueba AST), `PolicyCleaningAccess` en bootstrap y migración **0014**, sólo aditiva: `automation_policy_families`, `automation_policy_revisions`, `automation_policy_save_requests` y `automation_approvals` (las tres últimas inmutables por trigger).

- **Columnas por nombre exacto.** Los IDs cambian en cada importación (Fase 6B); la política nombra columnas para aplicarse a cualquier carga con esos nombres. Una operación autorizada **sin alcance** no autoriza ninguna columna.
- **Desglose por columna** (`column_effects` de la vista previa): celdas modificadas y nulos creados por columna, calculados con el mismo criterio que los totales. Se guarda junto al manifiesto, **fuera** de él: el `effect_sha256` no cambia y la aplicación compara el efecto completo como siempre. Una vista previa anterior no tiene desglose y se bloquea con `EFFECT_BREAKDOWN_MISSING`.
- **Barreras exactas:** `excluidas × 100 > límite × entrada` en enteros y `Decimal`. Los nulos creados se comprueban sobre el total de celdas **y por columna** (sobre las filas de entrada), para que una columna muy afectada no se diluya.
- **Aprobación:** si la política autoriza el efecto, `CleaningService.approve` crea la aprobación normal y, en la misma transacción (`before_commit`), `automation_approvals` registra la revisión exacta de la política, el efecto, la evaluación y el ejecutor (`manual` hoy; `pipeline` en 11C). Si ya hay una aprobación vigente del mismo efecto, se reutiliza.
- **Revocación:** guardar una revisión nueva revoca, cada una en su transacción, las aprobaciones automáticas del proyecto aún no aplicadas; las aplicadas o en curso no cambian.

| Ruta                                             | Función                                                                        |
| ------------------------------------------------ | ------------------------------------------------------------------------------ |
| GET `/projects/{id}/automation-policy`           | Revisión vigente (`revision: null` si no hay política)                         |
| POST `/projects/{id}/automation-policy`          | Nueva revisión (`expected_revision`, `Idempotency-Key`); sin cambios, la misma |
| GET `/automation-policies/{revision_id}`         | Revisión exacta                                                                |
| POST `/previews/{execution_id}/policy-approvals` | Evalúa con la política vigente; si autoriza, aprueba el efecto exacto          |
| GET `/approvals/{approval_id}/origin`            | Si una aprobación la concedió una política, con su revisión y evaluación       |

Códigos de evaluación: `POLICY_MISSING`, `POLICY_DISABLED`, `PLAN_INVALID`, `EFFECT_NOT_READY`, `EFFECT_BREAKDOWN_MISSING`, `OPERATION_NOT_AUTHORIZED`, `COLUMN_NOT_AUTHORIZED`, `TOKENS_NOT_AUTHORIZED`, `IDENTIFIER_CONVERSION`, `EXCLUDED_ROWS_ABOVE_LIMIT`, `NULLS_CREATED_ABOVE_LIMIT`, `ROUNDED_CELLS_ABOVE_LIMIT`, `OUTPUT_ROWS_BELOW_MINIMUM`. Un efecto bloqueado no cambia nada; la persona puede aprobarlo con «Aprobar efecto…».

**Interfaz:** en la etapa Limpieza, «Modo automático» (editor de la política con perfiles Conservador y Tipado que sólo rellenan el formulario); en la vista previa, «Aprobar con la política» muestra los motivos si bloquea y, si aprueba, la aprobación lleva «Aprobada automáticamente por la política rev N».

Pruebas: `test_automation_policy.py` (16 casos de la evaluación pura: valores por defecto, alcance, marcadores, identificadores, barreras en el límite exacto, nulos globales y por columna, plan y efecto), `test_automation_api.py` (revisiones, conflicto, validación, bloqueo y aprobación del efecto exacto, origen, reutilización, aplicación, revocación al cambiar la política, accesos), `test_cleaning_ops.py` (el desglose suma los totales) y `test_migration_0014.py`.

## 11C · Orquestación durable

Estados: `running`, `needs_review`, `completed`, `failed`, `cancelled`.

| Paso                | Reutiliza                              | Disponible desde |
| ------------------- | -------------------------------------- | ---------------- |
| `ingest`            | `csv_import` (Fase 12: otros lectores) | 11C              |
| `profile_quality`   | perfil y calidad existentes            | 11C              |
| `interpret`         | `understanding` + mapeos               | 11D              |
| `propose`           | `cleaning.propose` (11A)               | 11C              |
| `preview`           | `cleaning_preview`                     | 11C              |
| `approve`           | `evaluate` (11B)                       | 11C              |
| `apply`             | `cleaning_apply`                       | 11C              |
| `diagnose`          | perfil y calidad de la derivada        | 11C              |
| `quality_rules`     | `quality.evaluate@2`                   | 11C              |
| `analyze`           | `analytics.query`                      | 11E              |
| `publish_dashboard` | dashboards                             | 11E              |

En 11C el pipeline **termina en `quality_rules`**; los pasos `interpret`, `analyze` y `publish_dashboard` se activan con 11D y 11E. Mientras `interpret` no exista, `propose` usa la semántica confirmada por la persona, si la hay. La auditoría IA es un trabajo posterior independiente; su fallo no invalida el dashboard.

### Garantías

- Política, entrada, semántica y versiones de operaciones **fijadas al iniciar** el pipeline.
- **Transición y encolado del paso siguiente en una sola transacción.** El mecanismo ya existe: la cola es la tabla `execution_runs` en PostgreSQL y `enqueue_followup` encola dentro de la transacción que publica (Fase 5). Los pasos que no son ejecuciones (`interpret`, `propose`, `approve`) se resuelven dentro de esa misma transacción.
- **Recuperación:** `claim()` ya reclama ejecuciones con lease vencida. Se añade un **reconciliador** que busca pipelines `running` sin ejecución activa ni paso pendiente (caída entre publicar y avanzar) y reaplica la transición, que es idempotente.
- Claves idempotentes `uuid5(pipeline, paso, intento)` y restricción única por pipeline/paso.
- Revalidación de permisos y cancelación **antes de publicar**.
- **Sin bucles ilimitados** y **sin fallback silencioso**: si se cambia un plan tras un error, es una revisión nueva con nueva vista previa y evaluación, iniciada por una persona.

Persistencia: `automation_runs` y `automation_step_attempts` (inmutables). `automation_events` y un outbox separado sólo si el encolado transaccional existente resultara insuficiente.

### Avisos de «revisión necesaria»

Un pipeline detenido no sirve si nadie lo ve. Bandeja de avisos en la aplicación (pipelines en `needs_review` y `failed` del usuario, con enlace a la etapa); correo como incremento posterior.

### Límites operativos

Configurables por instalación: tamaño máximo de fuente, pipelines simultáneos por usuario y por proyecto, y **retención** de derivadas automáticas no activas (cada una añade un Parquet; la retención nunca borra una versión referenciada por un resultado, dashboard o informe).

Cierre: el pipeline se recupera tras reiniciar el worker y no duplica derivadas, aprobaciones ni ejecuciones aunque un evento se procese dos veces.

### Implementación (11C)

Migración **0015**, sólo aditiva: `automation_runs` (un pipeline por versión importada; estado, paso y referencias a lo que creó) y `automation_step_attempts` (registro de transiciones, inmutable por trigger).

- **Inicio.** Al publicarse una importación (`DatasetPublication.published`, `csv_import`), si el proyecto tiene una política activa se crea el pipeline en **la misma transacción**, con la revisión de la política fijada. Es idempotente por versión (restricción única). Superado `DATAFLOW_AUTOMATION_MAX_RUNNING_PER_OWNER` (5 por defecto), la carga queda en `needs_review` con `AUTOMATION_LIMIT`.
- **Avance.** `PipelineService` (`modules/automation/pipeline.py`) encadena casos de uso existentes a través de `PipelineAccess` (bootstrap): propuesta (11A) → plan → vista previa → aprobación por política (11B, ejecutor `pipeline`) → aplicación → diagnóstico de la derivada → reglas de calidad (conjunto aplicable o aviso `RULESET_NOT_APPLICABLE`) → fuente activa de la sesión (11A). Sin nada que limpiar, se activa la versión importada.
- **Durabilidad.** El worker reconcilia después de cada trabajo y en cada vuelta en reposo (`reconcile`): avanza los pipelines `running`, también los que quedaron a medias por una caída. Cada paso usa una clave idempotente `uuid5(pipeline, paso)` en planning, cleaning y quality, así que repetirlo devuelve lo mismo; un lock de sesión por pipeline (`pg_try_advisory_lock`) evita que dos workers lo avancen a la vez. Se usó el encolado transaccional existente: no hizo falta un outbox aparte.
- **Sin reintentos.** Un fallo de ejecución, un bloqueo de la política, un cambio de política (`POLICY_CHANGED`) o un caso de uso que rechaza el paso (`STEP_ERROR`) detiene el pipeline en `needs_review` con motivos; el reconciliador no lo vuelve a intentar.
- **Cancelar** detiene el pipeline y cancela su vista previa o aplicación si siguen en cola.

| Ruta                                 | Función                                            |
| ------------------------------------ | -------------------------------------------------- |
| GET `/projects/{id}/automation-runs` | Pipelines del proyecto, paginados                  |
| GET `/automation-runs/{id}`          | Pipeline con su registro de pasos                  |
| POST `/automation-runs/{id}/cancel`  | Cancelar                                           |
| GET `/versions/{id}/automation-run`  | Pipeline de una versión (o `null`)                 |
| GET `/notifications`                 | Pipelines en `needs_review` o `failed` del usuario |

La ruta prevista `/analysis-sessions/{id}/automation-runs` se implementó por proyecto (una sesión por proyecto en 11A).

**Interfaz:** bajo la fuente activa, el estado del pipeline de la versión que se ve (paso en curso con «Cancelar», «Revisión necesaria» con motivos, o «listo» con «Ver la versión limpia») y la bandeja «N cargas automáticas esperan revisión».

**Pendiente:** la retención de derivadas automáticas no activas y el aviso por correo quedan para un incremento posterior; hoy la bandeja de avisos está sólo en la aplicación.

Pruebas: `test_automation_pipeline.py` (pipeline completo de `ventas_calidad.csv` hasta la derivada activa con aprobación `pipeline`, bloqueo por política sin cambios, nada que limpiar, política desactivada, reconciliaciones repetidas sin duplicar vistas previas, cancelación, cambio de política a mitad, límite de pipelines y privacidad) y `test_migration_0015.py`.

## 11D · Moldes e interpretación reutilizable

### Moldes iniciales

| Molde      | Requiere                                                                                               | Nota                                     |
| ---------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------- |
| Ventas     | Fecha de negocio; importe y moneda; dimensiones; **grano** declarado (venta, pedido o línea)           | El grano evita contar líneas como ventas |
| Inventario | Producto; cantidad y unidad; costo unitario (opcional); **fecha de corte**; ubicación (si corresponde) | Cantidades de un corte, no movimientos   |
| Genérico   | Perfil, calidad y tabla                                                                                | Sin métricas de negocio inferidas        |

### Detección

Reglas **versionadas** (`sales@1`, `inventory@1`, `generic@1`) sobre nombres, tipos y perfil. Parten de las sugerencias existentes (`understanding/domain.py: suggestions`) y producen **candidatos, no confirmaciones semánticas**. Orden: Inventario → Ventas → Genérico (un inventario también tiene montos).

### Mapeos reutilizables

Una configuración confirmada por la persona (molde + columna para cada rol + moneda/unidad + grano) se guarda y se reutiliza **sólo** si cumple el contrato de compatibilidad:

- Columnas requeridas presentes.
- Tipos e interpretación compatibles.
- Unidades y moneda definidas.
- Grano conservado.

La igualdad de nombres o del hash de esquema **no** es prueba de equivalencia de negocio. Los IDs de columna cambian en cada importación (Fase 6B), así que el mapeo se resuelve por la descripción de cada columna (nombre, tipo, rol) y se valida antes de usarse.

Cierre: la primera carga pide las definiciones necesarias; otra carga compatible reutiliza el mapeo sin preguntar; una incompatible pide revisión en vez de inventar significado.

### Implementación (11D)

Módulo `templates` (sólo sus puertos y `audit`, prueba AST), `TemplateTablesAccess` en bootstrap y migración **0016**, sólo aditiva: `template_mapping_families` (una por proyecto y molde), `template_mapping_revisions` y `template_mapping_save_requests` (inmutables), y `automation_run_interpretations` (1:1 con el pipeline: mapeo aplicado, revisión semántica y número de pasada; tabla aparte para no añadir columnas a `automation_runs`, como en los ADR-014 y ADR-015).

- **Candidatos** (`GET /representations/{id}/template-candidates`): reglas por nombre y tipo; la sugerencia de rol del perfil sólo se usa donde no es ambigua (fechas, importe y dimensión de Ventas, fecha de corte de Inventario), para que un CSV de ventas no parezca un inventario completo. Si el proyecto ya tiene un mapeo de ese molde, se indica si es compatible con la tabla.
- **Mapeo confirmado** (`POST /projects/{id}/template-mappings`, revisiones con `expected_revision` e `Idempotency-Key`): rol → columna por nombre, tipo destino (y escala), moneda (roles de importe), unidad (cantidad) y grano (Ventas: `venta`, `pedido` o `linea`). Se valida contra el molde (422 `TEMPLATE_MAPPING_INVALID`).
- **Compatibilidad:** columnas por nombre; mismo tipo y escala, o texto que se convierte con la conversión confirmada; un tipo distinto o una columna ausente es incompatible.
- **En el pipeline:** antes de proponer, un mapeo incompatible detiene (`MAPPING_INCOMPATIBLE`) sin limpiar nada; uno compatible añade sus **conversiones confirmadas** a la propuesta (`cleaning-proposal@1` admite `casts`; la UI no las envía). Tras activar la versión limpia, el paso `interpret` guarda una revisión semántica normal que confirma los roles, la moneda o unidad y el grano. Sin mapeo, se detiene con `MAPPING_REQUIRED` (la versión limpia ya es la fuente activa).
- **Reanudar** (`POST /automation-runs/{id}/resume`): sólo para paradas de interpretación. Desde `interpret` hace **otra pasada** sobre la importación original con la interpretación confirmada (claves idempotentes propias de la pasada), así la nueva versión limpia queda tipada; la anterior se conserva en el historial.

**Interfaz:** cuando un pipeline pide la interpretación, la franja muestra el editor (molde candidato, columna y tipo por rol, moneda, unidad y grano); «Confirmar interpretación» guarda el mapeo y reanuda el pipeline.

Pruebas: `test_templates.py` (candidatos de ventas e inventario, validación, compatibilidad, borrador semántico y API con revisiones, conflicto y compatibilidad) y `test_automation_interpretation.py` (primera carga que pide la interpretación y, al reanudar, reprocesa con conversiones y confirma la semántica; carga compatible sin preguntar; incompatible que se detiene antes de limpiar; sólo se reanudan paradas de interpretación), `test_migration_0016.py`.

## 11E · Dashboard automático determinista

Cada molde genera **planes analíticos y una configuración visual versionados**, reutilizando métricas y consultas de `analytics`, la evidencia por cifra y la persistencia de dashboards (Fase 8, `cause: template`). El resultado visual mantiene tres niveles: `kpis`, `charts`, `table_detail`. Procedencia y advertencias son metadatos de la ejecución.

### Ampliaciones de `analytics` necesarias (implementadas)

| Necesidad                                     | Estado                                | `analytics.query@3`                                                                             |
| --------------------------------------------- | ------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Valor del inventario = Σ(cantidad × costo)    | **Implementada**                      | Agregación `sum_product` sobre dos medidas, aritmética exacta y evidencia como `sum`            |
| No sumar cortes de inventario entre fechas    | **Implementada**                      | Medida **semi-aditiva** `last_snapshot`: último corte de cada periodo, común a todos sus grupos |
| Ventas por mes, top N, % del total, variación | Existe (`analytics.query@2`, Fase 7B) | Igual en `@3`                                                                                   |

`analytics.query@1` y `@2` no cambian (modelo, motor y resultado; la referencia congelada de `@1` sigue intacta) y **rechazan** las métricas nuevas: planning con `METRIC_UNSUPPORTED` («necesita analytics.query@3») y el motor con el mismo código si un plan llegara a ejecutarse. Catálogo **`analysis-v7`** con los tres descriptores.

**Métrica.** Dos campos opcionales en el contenido de la métrica (sin migración: las métricas se guardan como contenido JSON en `analytics_metric_revisions`):

| Campo                      | Contenido                                                                                          |
| -------------------------- | -------------------------------------------------------------------------------------------------- |
| `second_measure_column_id` | segunda medida; obligatoria con `sum_product` y sólo con ella                                      |
| `semi_additive`            | `last_snapshot` o nulo; sólo con `sum` y `sum_product` y con columna temporal (la fecha del corte) |

Sin usarse, los dos campos quedan **fuera del hash** (`MetricContent.hashed()`): toda métrica guardada antes conserva su `content_sha256` y las referencias exactas de los planes siguen siendo válidas.

**`sum_product`.** Σ(medida × segunda medida) fila a fila, en `int`/`Decimal` dentro del contexto único `exact_context()` (11.0): el producto de dos valores de 38 dígitos y su suma nunca se redondean. Un nulo en cualquiera de las dos medidas excluye la fila y se cuenta en `excluded_by_nulls`. Escala del resultado = suma de las escalas (entero × decimal(3) → 3; decimal(3) × decimal(3) → 6; entero × entero → entero); más de 38 dígitos → `RESULT_PRECISION_EXCEEDED`. Requisito semántico: **ambas** columnas numéricas y confirmadas como `measure`. Unidad: una cantidad por un costo unitario da la moneda del costo; dos unidades, su producto («kg×m»); **dos monedas no se multiplican** (`UNIT_MISMATCH`). Es sumable entre grupos: admite % del total.

**`last_snapshot`.** El corte de un periodo es la última fecha de negocio con filas incluidas (filtros y nulos ya aplicados) **dentro del periodo**, o de todo el resultado si no se agrupa por tiempo. Es **común a todos los grupos del periodo**: cada grupo suma sólo sus filas de esa fecha, de modo que la suma de los grupos coincide con el total sin dimensiones (dashboard coherente) y nunca se suman cortes de fechas distintas. Un grupo que sólo tiene filas de cortes anteriores existe pero vale **nulo** («sin filas en el corte»), nunca 0. Una fila sin fecha no pertenece a ningún corte: se excluye y se cuenta como nulo. Las filas de fechas anteriores al corte se declaran en `snapshot.superseded_rows` (las que forman el valor son `included_rows − superseded_rows`); en las comparaciones, la base usa el último corte del periodo base (`snapshot.base_superseded_rows`). Exige la columna temporal confirmada como `business_date` aunque la consulta no agrupe por tiempo.

**Resultado y evidencia.** `AnalysisResultV3` (`operation: analytics.query@3`) es el de `@2` con `MetricDefinitionV3` (segunda medida, `semi_additive`, `snapshot`) y filas con `snapshots` (métrica → fecha del corte usado). La dirección de `value` no cambia (misma fórmula que `@1` y `@2`); `GET /evidence` devuelve además `snapshot`. Con métricas de `@2`, `@3` calcula exactamente las mismas cifras, conteos y `evidence_id` que `@2`.

**API e interfaz.** Cambios aditivos (agregación `sum_product`, campos opcionales de métrica, `AnalysisResultV3`, `METRIC_UNSUPPORTED`, `analysis-v7`). La interfaz crea `@3` cuando alguna métrica elegida lo necesita y muestra «Suma de productos»; el formulario «Nueva métrica» no ofrece todavía las agregaciones nuevas (las crean los moldes de 11E) y «Añadir a un dashboard» sigue limitado a `@2` hasta que los dashboards admitan `@3`. Sin migración; API y worker se despliegan juntos (un worker anterior no tiene ejecutor para `analytics.query@3`).

Pruebas: `tests/test_analytics_query_v3.py` (motor: escalas y exactitud de `sum_product`, nulos en cualquiera de las medidas, más de 38 dígitos, último corte por periodo y sin agrupar, corte común a los grupos y suma coherente, rango y filtros, comparación con la base de su último corte, % del total, evidencia, `@3` igual a `@2` en los 8 casos de la referencia congelada, `@1`/`@2` que rechazan las métricas nuevas, validación de la métrica y hash de las métricas anteriores), `tests/test_planning_domain.py` (versión mínima, ambas medidas confirmadas, unidades, fecha de corte confirmada) y `tests/test_analytics_query_v3_runner.py` (de punta a punta con PostgreSQL: métrica por la API, plan `@2` rechazado, `@3` ejecutado, evidencia con corte y CSV).

### Reglas

- Orden estable de tarjetas y categorías.
- Tratamiento explícito de nulos; ningún «sin datos» se convierte en cero.
- No mezclar monedas o unidades incompatibles (`UNIT_MISMATCH`).
- Filtros visuales (ocultan filas, Fase 8) diferenciados de filtros que recalculan métricas.
- No sumar snapshots de inventario entre fechas como si fueran movimientos.
- Publicar un dashboard coherente; si se admite un resultado parcial, identificar exactamente qué falta.

Cierre: el mismo input, configuración y entorno lógico producen el mismo contenido calculado, excluyendo IDs y fechas operativas.

### Implementación del dashboard automático (11E)

Tras `interpret`, el pipeline sigue con `analyze` y `publish` (migración **0017**, aditiva: `automation_run_analyses`, 1:1 con el pipeline).

- **Especificación por molde** (`modules/templates/analysis.py`, `template-analysis@1`, datos puros): métricas, consultas y tarjetas en orden estable.
  - **Ventas** (`analytics.query@2`): KPI de ventas totales, operaciones y ticket promedio; línea de ventas por mes; barras con el top 10 por la dimensión y su % del total; tabla de detalle con el top 20.
  - **Inventario** (`analytics.query@3`): unidades con **último corte** (`last_snapshot`, nunca suma cortes entre fechas) y productos distintos; valor del inventario (`sum_product` cantidad × costo, último corte) en su **propia consulta** para no mezclar unidad y moneda (`UNIT_MISMATCH`); top 10 de productos; detalle de menor stock por ubicación o producto.
  - **Genérico:** sin dashboard.
- **`analyze`:** crea las métricas sobre la tabla limpia (familias nuevas: cada importación tiene otros IDs de columna), los planes con la revisión semántica confirmada fijada y lanza las consultas **respetando la capacidad** del propietario (`QUEUE_LIMIT`, 3 trabajos activos): las pendientes se lanzan en reconciliaciones siguientes. Claves idempotentes por pasada y consulta.
- **`publish`:** cuando todas las consultas terminaron, crea el dashboard del molde la primera vez y, en cargas siguientes, guarda una **revisión nueva del mismo dashboard** (IDs de tarjeta estables), de modo que el historial conserva cada carga. Una tarjeta fallida conserva su estado (`failed`, `insufficient_data`…) sin romper las demás.
- **Dashboards** aceptan ahora tarjetas de `analytics.query@3` además de `@2`.
- **Interfaz:** al terminar, la franja del pipeline ofrece «Ver dashboard».

Pruebas: `test_automation_dashboard.py` (especificación estable de ventas; inventario con último corte y moneda separada; pipeline que publica el dashboard con sus 6 tarjetas listas y, con una segunda carga, revisa el mismo dashboard) y `test_migration_0017.py`.

## 11F · Auditoría textual IA

### Contrato

```python
class Alerta(BaseModel):
    titulo: str = Field(max_length=120)
    detalle: str = Field(max_length=600)  # cifras sólo como {{evidence:id}}
    severidad: Literal["alta", "media", "baja"]


class AuditoriaTextual(BaseModel):
    resumen_ejecutivo: str = Field(max_length=1500)
    alertas_criticas: list[Alerta] = Field(max_length=3)
    recomendaciones: list[str] = Field(min_length=2, max_length=2)
```

### Funcionamiento

- Se ancla a una **revisión de dashboard publicada**, no al pipeline, para que también sirva a dashboards hechos a mano.
- Se implementa como **tarea del copiloto** (Fase 10): reutiliza `AIProvider`, `copilot_ai_calls`, los límites de tokens y costo, y la sustitución de cifras por evidencia.
- Sólo resultados ya publicados; sin herramientas de ejecución, sin SQL ni código generado, sin acceso a credenciales.
- Envía agregados y etiquetas autorizadas; **no** filas de detalle.
- Cifras: el modelo cita `{{evidence:id}}` y el servidor pone el valor exacto. Regla única, la existente: un número escrito libremente se sustituye por «[cifra no verificada]» y se cuenta; una referencia inexistente o ajena **anula** la auditoría (`INVALID_EVIDENCE_REFERENCE`).
- Modelo, prompt (`copilot-audit@v1`), parámetros y consumo registrados.

### Reproducibilidad

Se guarda la respuesta con clave derivada de: hash del resultado (cifras y evidencias), proveedor y modelo, versión del prompt y configuración de la auditoría. La misma clave devuelve la auditoría guardada **sin otra llamada**. No se promete determinismo mediante temperatura o `seed`; sólo se usan parámetros que el modelo elegido admite.

Cierre: si la IA falla, el dashboard sigue disponible; una cifra sin evidencia se marca o anula según la regla anterior; la misma auditoría guardada se recupera sin otra llamada.

### Implementación (11F implementada)

**API.** `POST /api/v1/dashboard-revisions/{id}/text-audits` (`Idempotency-Key`, Origin y CSRF) devuelve `{audit, reused}`; `GET` de la misma ruta lista las auditorías guardadas de la revisión, de la más reciente a la más antigua. Propietario en ambas (ajena o inexistente: 404). Errores: 503 `COPILOT_UNAVAILABLE`, 429 `AI_BUDGET_EXCEEDED`, 409 `RESULT_NOT_READY` (ninguna tarjeta con resultado terminado), 422 `INVALID_EVIDENCE_REFERENCE` (auditoría anulada) y 502 con el código del proveedor (`AI_TIMEOUT`, `AI_INVALID_OUTPUT`…).

**Tarea del copiloto.** `CopilotService.text_audit`, con el mismo puerto `AIProvider`, la misma comprobación de disponibilidad y límites de tokens y costo, y el registro en `copilot_ai_calls` (`task: text_audit`, `prompt_id: copilot-audit`, `prompt_version: v1`, sin conversación). El módulo copilot sigue sin importar dashboards: bootstrap le da la revisión por `CopilotSources.dashboard` (`DashboardFacts`: título, descripción y tarjetas con su ejecución).

**Qué se envía.** Sólo tarjetas con ejecución **terminada** del mismo proyecto; las demás se declaran en `cards` (`not_executed`, `not_ready`) y no se auditan. Por tarjeta, su título y el resultado como en «Explicar resultado» (definiciones, conteos y hasta 40 cifras con su `evidence_id`, grupo y periodo); títulos, descripción y etiquetas van marcados como `dato_no_confiable`. Nunca filas de detalle.

**Cifras.** La regla única de la Fase 10 se aplica a cada texto (`resumen_ejecutivo`, título y detalle de cada alerta, cada recomendación): `{{evidence:id}}` se sustituye por el valor exacto con la ejecución de su tarjeta (el segmento enlaza a «De dónde sale este número»), `{{label:id}}` por la etiqueta del grupo, un número libre por «[cifra no verificada]» y se cuenta (`unverified_numbers`), y una referencia inexistente, ajena o mal formada **anula toda la auditoría**. Además, cada cifra citada se recalcula como `GET /evidence`.

**Reproducibilidad.** `result_sha256` = hash canónico de lo auditado (título y descripción del dashboard y, por tarjeta, título, métrica, ejecución, operación y cada cifra con su evidencia). `audit_key` = hash de `result_sha256`, proveedor, modelo, `copilot-audit@v1` y configuración (`max_output_tokens`, cifras por tarjeta y parámetros normalizados del proveedor). Con la misma clave sobre la misma revisión se devuelve la guardada (`reused: true`) **sin llamar al proveedor**; otra configuración u otro resultado es otra clave. Sólo se guarda una auditoría aceptada: un fallo del proveedor o una auditoría anulada se registran en `copilot_ai_calls` y no dejan nada guardado, así que un reintento vuelve a llamar. No se usan temperatura ni `seed` como promesa de determinismo.

**Persistencia.** Migración **0018** (encadenada detrás de 0017): tabla `copilot_text_audits`, inmutable por trigger, única por `(dashboard_revision_id, audit_key)` (dos peticiones simultáneas guardan una sola), con el modelo que respondió, el prompt, la configuración, las tarjetas, el contenido verificado y la llamada (`call_id`). La idempotencia de la petición reutiliza `copilot_requests` con la revisión como ámbito. Downgrade bloqueado si hay auditorías.

**Interfaz.** Panel «Auditoría textual (IA)» al pie del dashboard en la etapa Visualización: muestra la última auditoría de la revisión que se ve, pide una nueva o devuelve la guardada, enlaza cada cifra con su procedencia y avisa de las cifras retiradas y de las tarjetas no auditadas. No modifica tarjetas, filtros ni revisiones; si la IA falla, muestra el motivo y el dashboard sigue igual. Con la IA desactivada, el botón queda inactivo con el mismo aviso que el copiloto. El proveedor falso (`simulation.audit`) responde de forma determinista para pytest y E2E.

Pruebas: `tests/ai/test_ai_text_audit.py` (cifras por evidencia con la ejecución de su tarjeta; guardada y reutilizada sin otra llamada con otra o la misma `Idempotency-Key`; otra configuración, otra clave; el dashboard no cambia; números libres retirados y contados; referencias inexistentes, vacías o desconocidas que anulan la auditoría sin guardar nada; fallo del proveedor y salida fuera del esquema registrados sin guardar; sólo resultados terminados y ninguna fila en el contexto; nada que auditar, IA desactivada, límite de tokens, CSRF, `Idempotency-Key` obligatoria y acceso ajeno; reglas de verificación y esquema sin la API) y `tests/test_migration_0018.py` (ida y vuelta, `compare_metadata`, unicidad por clave, inmutabilidad y downgrade bloqueado). Las pruebas de 0005–0017 excluyen la tabla nueva (`tests/migration_support.py`).

## API propuesta

Nombres a contrastar con el contrato actual antes de implementar. Todas bajo `/api/v1`, con autorización por propietario (ajeno: 404), Origin y CSRF en mutaciones, `Idempotency-Key` y control de concurrencia.

| Ruta                                             | Función                                        | Entrega |
| ------------------------------------------------ | ---------------------------------------------- | ------- |
| POST `/projects/{id}/analysis-sessions`          | Crear (o devolver) la sesión del proyecto      | 11A     |
| GET `/analysis-sessions/{id}`                    | Fuente activa y estado                         | 11A     |
| POST `/analysis-sessions/{id}/inputs`            | Seleccionar una entrada (`expected_revision`)  | 11A     |
| GET `/representations/{id}/cleaning-proposal`    | Propuesta de limpieza del backend              | 11A     |
| GET/POST `/projects/{id}/automation-policy`      | Consultar o guardar la política                | 11B     |
| GET `/automation-policies/{revision_id}`         | Revisión exacta de la política                 | 11B     |
| GET `/analysis-sessions/{id}/automation-runs`    | Pipelines de la sesión                         | 11C     |
| POST `/automation-runs/{id}/cancel`              | Cancelar                                       | 11C     |
| GET `/notifications`                             | Bandeja de avisos (revisión necesaria, fallos) | 11C     |
| GET `/representations/{id}/template-candidates`  | Moldes candidatos                              | 11D     |
| POST `/analysis-sessions/{id}/template-mappings` | Guardar interpretación                         | 11D     |
| POST `/dashboard-revisions/{id}/text-audits`     | Solicitar auditoría (o devolver la guardada)   | 11F     |

## Pruebas y despliegue

Cada entrega incluye:

- **Dominio:** límites, reglas y determinismo.
- **PostgreSQL:** transacciones, conflictos e inmutabilidad.
- **Worker:** reintentos, cancelación y fencing.
- **Recuperación:** caída entre publicación y paso siguiente.
- **Seguridad:** acceso ajeno, secretos y fuentes no autorizadas.
- **E2E:** recorrido completo y revisión necesaria.
- **Migración aditiva** y ensayo de restauración; registrar los modelos nuevos en `bootstrap/models.py` (`alembic check` en CI).

Las migraciones se numeran según el head real al implementar (hoy `0012`); cada entrega lleva la suya.

## Decisiones abiertas

1. Contenido exacto de los perfiles predefinidos de política.
2. Plazo de retención por defecto de derivadas automáticas no activas.
3. ¿Correo para «revisión necesaria» en esta fase o más adelante?
4. ¿Se permite publicar dashboards parciales (11E) o sólo completos?
5. Varias sesiones por proyecto: ¿se necesitan a corto plazo?
