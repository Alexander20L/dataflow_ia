# Fase 33 — Todas las tablas de una base, tarde lo que tarde

Estado: **implementada** (API 0.42.0, migración 0030). Decisión:
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
- Mientras corre (o espera su turno), la copia **late** cada 20 s (`heartbeat_at`). Si la API se
  reinicia, el latido se detiene y, al consultarla, una copia sin latido desde hace 90 s pasa a
  `failed` con `DATABASE_COPY_INTERRUPTED` («Vuelve a conectar: por seguridad la contraseña no
  se guarda»). Es el precio de no guardar la contraseña. Con el latido no hace falta nada al
  arrancar, y funciona con varias réplicas de la API.
- La copia usa `DATAFLOW_DATABASE_COPY_TIMEOUT_SECONDS` (1800) para el subproceso o el
  conector, y el mismo plazo para leer los archivos, relacionarlos y registrar las versiones.
- «Ver esquema» usa el mismo mecanismo (`photo`): responde con el `copy_id` y el modelo de datos
  queda en el registro (sin datos de las tablas) cuando termina.
- `DATAFLOW_DATABASE_MAX_BYTES` sube a **200 MB** por defecto (no 500 como en el diseño: la copia
  entera vive en la memoria del subproceso hasta que termina, y con 500 MB Python necesitaría
  varios GB) y deja de ser un error: al llegar, la copia se detiene y la tabla en curso y las
  restantes se omiten («La copia alcanzó su tamaño máximo»). Las tablas se copian de menor a
  mayor para que entren las más posibles.
- Después de copiar, lo que no cabe como original (5 MB) o en la cuota de la cuenta se omite con
  su motivo, tablas y vistas; si cae la vista principal, se abre la tabla mayor.
- **Cola**: las versiones de una misma copia entran juntas aunque pasen del límite de 50
  trabajos pendientes por cuenta (la cola admite la carga una vez, como un todo). Hallado en la
  prueba real: 30 tablas son 56 versiones.

## Presupuesto de IA: esperar y seguir

Hoy cada trabajo con IA (comprensión, investigación, dashboard, informe) llama a
`copilot.available()` en `prepare` y, con `AI_BUDGET_EXCEEDED`, sigue sólo con reglas.

- Nuevo resultado de `prepare`: **aplazar** (`Deferred`). El intento termina como `deferred` y
  guarda en su `lease_until` el momento en que se renueva el presupuesto: 00:00 UTC del día
  siguiente (tokens por usuario) o el día 1 del mes siguiente (costo por proyecto); el trabajo
  vuelve a `queued`. Sin tabla ni columna nuevas: una columna nueva en `execution_runs` rompía
  las pruebas de las migraciones antiguas, que usan el modelo actual sobre esquemas viejos.
- `claim` ignora los trabajos con un intento aplazado hasta el futuro; los demás de la cuenta
  siguen su curso (un trabajo aplazado no bloquea el límite de tres en marcha). El intento
  aplazado queda como `deferred` y **no gasta** uno de los tres intentos del trabajo.
- `budget_deferral` y `ai_unavailability` (`bootstrap/ai.py`) sustituyen la comprobación que
  repetían los seis puntos de los trabajos con IA; el error de presupuesto lleva `renews_at`.
- El progreso muestra la etapa en cola con «En espera: el presupuesto de IA se renueva el …
  (UTC).» (`AI_BUDGET_WAITING`).
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
- Progreso de versión: la etapa aplazada sigue en `queued` y su detalle dice hasta cuándo
  espera (sin estado nuevo: la web no cambia).
- Reglas nuevas: `postgresql-selection-v2` y `sqlserver-selection-v3` (sin límite de tablas, de
  menor a mayor, omitidas por tamaño). Las versiones anteriores se siguen leyendo con su regla.

## Configuración

| Variable                                 | Por defecto | Uso                                     |
| ---------------------------------------- | ----------- | --------------------------------------- |
| `DATAFLOW_DATABASE_MAX_BYTES`            | 200 MB      | Tope de una copia (antes 50 MB y error) |
| `DATAFLOW_DATABASE_COPY_TIMEOUT_SECONDS` | `1800`      | Plazo de una copia en segundo plano     |
| `DATAFLOW_DATABASE_COPY_WORKERS`         | `2`         | Copias a la vez por proceso de API      |

## Piezas

| Pieza                                         | Dónde                                                   |
| --------------------------------------------- | ------------------------------------------------------- |
| Reglas sin límite de tablas y tope que omite  | `integrations/sources/*_reader.py`                      |
| Copias (`database_copies`, 0030) y estados    | `modules/ingestion/infrastructure.py`, `application.py` |
| Hilos de fondo, latido y una copia por cuenta | `bootstrap/database_copies.py`                          |
| Rutas 202 y `GET /database-copies/{id}`       | `modules/ingestion/presentation.py`                     |
| Aplazamiento (intento `deferred`) y `claim`   | `modules/executions/`                                   |
| Trabajos con IA que aplazan                   | `bootstrap/ai.py`, `bootstrap/*_job.py` (`prepare`)     |
| Pantalla de carga y progreso aplazado         | `apps/web/src/features/ingestion/`, progreso de versión |

## Pruebas

En `test_phase33_all_tables.py` (y adaptadas las de las Fases 18B, 31 y 32 a la respuesta 202):

- Elección de todas las tablas de menor a mayor; un esquema real con 27 tablas se copia entero
  (`postgresql-selection-v2`).
- El tope de la copia deja entrar las tablas pequeñas y omite las demás con su motivo; la
  cuota de la cuenta, igual.
- Una base que pasa del límite de pendientes entra entera en la cola.
- Foto y copia responden 202; `GET /database-copies/{id}` trae el modelo o la versión, otra
  cuenta no la ve y la contraseña no aparece; una copia con contraseña errónea queda `failed`
  con su motivo; una sin latido, `DATABASE_COPY_INTERRUPTED`.
- El ejecutor de hilos hace una copia a la vez por cuenta y en paralelo entre cuentas.
- Presupuesto agotado: la comprensión queda en cola hasta las 00:00 UTC siguientes, el progreso
  lo dice, aplazarla cuatro veces no gasta sus intentos y, con presupuesto, sigue con IA. Sin IA
  configurada, sigue como antes (reglas).

Prueba real contra la API en marcha (hilos de verdad, IA desactivada) con un esquema sintético
de 30 tablas relacionadas: la foto responde en 0,2 s y el modelo (30 tablas, 77 relaciones y
26 vistas) está en 4 s; la copia responde en 0,07 s y en 11 s registra **56 versiones** (30
tablas, 25 vistas de hechos y la vista general, que se abre). No se pudo probar con Pagila:
descargar y ejecutar su SQL no estaba permitido en este entorno.

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
