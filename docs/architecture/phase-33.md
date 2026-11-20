# Fase 33 — Todas las tablas de una base, tarde lo que tarde

Estado: **diseño** (pendiente de implementar). Decisión:
[ADR-051](../adr/051-all-tables-background-copy.md). Modifica la
[Fase 31](phase-31.md) ([ADR-049](../adr/049-related-sources-and-postgresql.md) §7: hasta 10
tablas) y la [Fase 32](phase-32.md) (copia dentro de la petición).

## Objetivo

Que al conectar una base DataFlow trabaje como un analista: lea **todas** las tablas del esquema
y las analice todas con el recorrido completo, con IA, aunque tarde horas. El límite de 10
tablas de `sqlserver-selection-v2` y `postgresql-selection-v1` desaparece.

## Decisiones del usuario

1. **Todas las tablas**, no un número mayor: lo que limita es el tamaño, no la cantidad.
2. **Copia en segundo plano**: «Analizar» responde al momento y la copia sigue, tarde lo que
   tarde, con su progreso a la vista.
3. **Si se acaba el presupuesto de IA, esperar y seguir con IA**: los análisis pendientes
   esperan a que se renueve en vez de hacerse sólo con reglas.

## Qué impide hoy leerlo todo

| Freno                     | Hoy                                              | Fase 33                                                    |
| ------------------------- | ------------------------------------------------ | ---------------------------------------------------------- |
| Número de tablas          | 10 (`MAX_TABLES_V2`)                             | Sin límite propio (el catálogo sigue acotado a 500)        |
| Tiempo de la copia        | Dentro de la petición: 45 s (60 en el proxy web) | En segundo plano, `DATAFLOW_DATABASE_COPY_TIMEOUT_SECONDS` |
| Tamaño total de la copia  | 50 MB: al pasarlo, error y no se copia nada      | Se copia hasta el tope y el resto se omite con su motivo   |
| Presupuesto de IA agotado | Los trabajos siguen sólo con reglas              | Los trabajos esperan a que se renueve                      |
| Relaciones y vistas       | En la petición, con el plazo de 45 s             | En el mismo trabajo de fondo                               |

Se mantienen: 100 000 registros y 5 MB por tabla (cada tabla es un original), 128 columnas,
celdas de 64 KB y la cuota de originales de la cuenta (`DATAFLOW_MAX_OWNER_STORAGE_BYTES`).
Una tabla que no cabe se omite con su motivo, como hoy; ninguna se trunca.

## Copia en segundo plano

La contraseña **no se guarda** (ADR-035 §8, ADR-049 §7): ni en la base de DataFlow, ni en la
cola, ni en disco. Por eso la copia no puede ser un trabajo del worker, que corre en otro
proceso y sólo lee de la cola. Se hace en la API, en un hilo de fondo que conserva la conexión
en memoria:

```
POST …/imports/postgresql  ─▶ 202 {copy_id, state: "queued"}   (responde al momento)
hilo de fondo (API)        ─▶ copia (subproceso local o connector) ─▶ relations-v1 y vistas
                           ─▶ registra cada tabla y vista como versión ─▶ cola de análisis
GET  /database-copies/{id} ─▶ estado, tablas copiadas/omitidas y la versión principal
```

- Tabla `database_copies` (migración **0030**): cuenta, proyecto, motor, servidor, base,
  esquema, tipo (`photo` o `import`), estado (`queued`, `running`, `succeeded`, `failed`),
  error, versión principal, número de tablas copiadas y omitidas, fechas. Nunca la contraseña
  ni el certificado.
- Hilos: `DATAFLOW_DATABASE_COPY_WORKERS` (2) por proceso de API; como mucho una copia en curso
  por cuenta (las demás esperan en `queued`).
- Si la API se reinicia, las copias `queued` o `running` pasan a `failed` con
  `DATABASE_COPY_INTERRUPTED` («Vuelve a conectar: por seguridad la contraseña no se guarda»).
  Es el precio de no guardar la contraseña.
- La copia usa `DATAFLOW_DATABASE_COPY_TIMEOUT_SECONDS` (1800) para el subproceso o el
  conector, y el mismo plazo para leer los archivos, relacionarlos y registrar las versiones.
- «Ver esquema» usa el mismo mecanismo (`photo`): responde con el `copy_id` y el modelo de datos
  queda en el registro (sin datos de las tablas) cuando termina.
- `DATAFLOW_DATABASE_MAX_BYTES` sube a 500 MB por defecto y deja de ser un error: al llegar, la
  copia se detiene y las tablas restantes se omiten («La copia alcanzó el tamaño máximo»). Las
  tablas se copian de menor a mayor para que entren las más posibles.

## Presupuesto de IA: esperar y seguir

Hoy cada trabajo con IA (comprensión, investigación, dashboard, informe) llama a
`copilot.available()` en `prepare` y, con `AI_BUDGET_EXCEEDED`, sigue sólo con reglas.

- Nuevo resultado de `prepare`: **aplazar**. El trabajo vuelve a `queued` con `available_at`
  (columna nueva de `executions`, migración **0030**) en el momento en que se renueva el
  presupuesto: 00:00 UTC del día siguiente (tokens por usuario) o el día 1 del mes siguiente
  (costo por proyecto).
- `claim` ignora los trabajos con `available_at` en el futuro; los demás trabajos de la cuenta
  siguen su curso (un trabajo aplazado no bloquea el límite de tres en marcha).
- El progreso muestra la etapa como «En espera: el presupuesto de IA se renueva el …».
- La falta de IA por otros motivos (sin clave, proveedor caído) sigue como hoy: reglas y aviso.

**Cuánto se espera.** Medido en las pruebas de la Fase 31 (69 llamadas reales a Claude Opus
5.5): unos **0,28 USD y 32 000 tokens por versión analizada**. Sakila completa (unas 21
versiones) cuesta unos 6 USD y 670 000 tokens. Con los límites por defecto:

- por proyecto y mes, **50 USD** (antes 5; decisión del usuario): cabe una base de unas 150
  versiones;
- por usuario y día, **1 000 000 de tokens** (antes 200 000; decisión del usuario): unas 30
  versiones al día, así que Sakila completa cabe en un día.

## Interfaz

- Tras «Analizar», la pantalla de carga muestra «Copiando tablas de la base…» con el número
  de tablas copiadas cuando termina, y abre la versión principal. Si la persona cierra la
  pestaña, la copia sigue; el proyecto muestra las versiones a medida que se registran.
- «Ver esquema» muestra «Leyendo el esquema…» hasta que el modelo está listo.
- En el progreso de cada versión, la etapa aplazada dice hasta cuándo espera.

## API

- `POST /projects/{id}/imports/postgresql` y `…/sqlserver`: 202 con `DatabaseCopy`
  (`id`, `state`, …) en vez de la versión.
- `POST …/postgresql/inspect` y `…/sqlserver/inspect`: 202 con `DatabaseCopy` (`kind: photo`).
- `GET /database-copies/{id}` (`getDatabaseCopy`): estado; con `succeeded`, `version_id`
  (import) o `model` (photo); con `failed`, `error_code` y `error_message`.
- Progreso de versión: estado `deferred` con `available_at`.
- Reglas nuevas: `postgresql-selection-v2` y `sqlserver-selection-v3` (sin límite de tablas, de
  menor a mayor, omitidas por tamaño). Las versiones anteriores se siguen leyendo con su regla.

## Configuración

| Variable                                 | Por defecto | Uso                                     |
| ---------------------------------------- | ----------- | --------------------------------------- |
| `DATAFLOW_DATABASE_MAX_BYTES`            | 500 MB      | Tope de una copia (antes 50 MB y error) |
| `DATAFLOW_DATABASE_COPY_TIMEOUT_SECONDS` | `1800`      | Plazo de una copia en segundo plano     |
| `DATAFLOW_DATABASE_COPY_WORKERS`         | `2`         | Copias a la vez por proceso de API      |

## Piezas

| Pieza                                         | Dónde                                                   |
| --------------------------------------------- | ------------------------------------------------------- |
| Reglas sin límite de tablas y tope que omite  | `integrations/sources/*_reader.py`                      |
| Copias (`database_copies`, 0030) y estados    | `modules/ingestion/infrastructure.py`, `application.py` |
| Hilos de fondo y recuperación al arrancar     | `bootstrap/database_copies.py`, `bootstrap/app.py`      |
| Aplazamiento (`available_at`, 0030) y `claim` | `modules/executions/`                                   |
| Trabajos con IA que aplazan                   | `bootstrap/*_job.py` (`prepare`)                        |
| Pantalla de carga y progreso aplazado         | `apps/web/src/features/ingestion/`, progreso de versión |

## Pruebas

- Una base de prueba con 25 tablas: se copian todas y se registran N + H + 1 versiones.
- El tope de bytes omite las últimas tablas con su motivo; las más pequeñas entran primero.
- La copia responde 202 al momento; `GET /database-copies/{id}` pasa por `running` y
  `succeeded`; la contraseña no aparece en ningún registro.
- Reinicio con copias en curso → `DATABASE_COPY_INTERRUPTED`.
- Presupuesto agotado → el trabajo queda `deferred` con su `available_at`, `claim` no lo toma
  antes y lo toma después; los demás trabajos de la cuenta siguen.
- Sin clave de IA → sigue como hoy (reglas y aviso).

## Limitaciones

- Una copia en curso se pierde si la API se reinicia: hay que volver a conectar.
- Una base muy grande puede llenar la cuota de originales de la cuenta; las tablas que no caben
  se omiten con su motivo.
- Con el presupuesto agotado, el análisis completo puede tardar días (o hasta el mes siguiente
  con el presupuesto por proyecto).

## Decisiones del usuario (límites)

1. **Presupuesto mensual por proyecto: 50 USD** (antes 5; `DATAFLOW_AI_PROJECT_MONTHLY_COST_USD`).
2. **Cuota de originales por cuenta: 1 GB** (antes 100 MB; `DATAFLOW_MAX_OWNER_STORAGE_BYTES`).
3. **Tokens por usuario y día: 1 000 000** (antes 200 000; `DATAFLOW_AI_USER_DAILY_TOKENS`).

Ya aplicados en la configuración por defecto y en `.env.example`.
