# Fase 11 — Automatización determinista

Estado: **11.0 implementada**; de 11A, la **propuesta de limpieza en el backend** está implementada y la sesión de análisis no. El resto (11A–11F) es plan objetivo y no describe funcionalidades implementadas. [ADR-023](../adr/023-policy-governed-automation.md). Las fuentes nuevas (Excel, SQL Server, PDF) son la [Fase 12](phase-12.md).

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

## 11E · Dashboard automático determinista

Cada molde genera **planes analíticos y una configuración visual versionados**, reutilizando métricas y consultas de `analytics`, la evidencia por cifra y la persistencia de dashboards (Fase 8, `cause: template`). El resultado visual mantiene tres niveles: `kpis`, `charts`, `table_detail`. Procedencia y advertencias son metadatos de la ejecución.

### Ampliaciones de `analytics` necesarias

| Necesidad                                     | Estado                                    | Propuesta (`analytics.query@3`)                                                              |
| --------------------------------------------- | ----------------------------------------- | -------------------------------------------------------------------------------------------- |
| Valor del inventario = Σ(cantidad × costo)    | No existe: una métrica agrega una columna | Agregación `sum_product` sobre dos medidas, aritmética exacta y evidencia como `sum`         |
| No sumar cortes de inventario entre fechas    | No existe: `sum` suma todos los periodos  | Medida **semi-aditiva**: «último corte» por periodo (`last_snapshot`), declarada en el molde |
| Ventas por mes, top N, % del total, variación | Existe (`analytics.query@2`, Fase 7B)     | —                                                                                            |

`analytics.query@1` y `@2` no cambian; referencias congeladas como en la Fase 7B.

### Reglas

- Orden estable de tarjetas y categorías.
- Tratamiento explícito de nulos; ningún «sin datos» se convierte en cero.
- No mezclar monedas o unidades incompatibles (`UNIT_MISMATCH`).
- Filtros visuales (ocultan filas, Fase 8) diferenciados de filtros que recalculan métricas.
- No sumar snapshots de inventario entre fechas como si fueran movimientos.
- Publicar un dashboard coherente; si se admite un resultado parcial, identificar exactamente qué falta.

Cierre: el mismo input, configuración y entorno lógico producen el mismo contenido calculado, excluyendo IDs y fechas operativas.

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
