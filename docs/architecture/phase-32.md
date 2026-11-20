# Fase 32 — Conexión a bases de datos públicas

Estado: **diseño aceptado** (pendiente de implementar). Decisión:
[ADR-050](../adr/050-public-database-connections.md). Amplía la [Fase 31](phase-31.md)
([ADR-049](../adr/049-related-sources-and-postgresql.md) §7) y la Fase 18B
([ADR-035](../adr/035-regional-sources-tables-and-structure.md) §8).

## Objetivo

Que cualquier persona con cuenta pueda conectar **su** base de PostgreSQL (y, más adelante,
SQL Server) accesible desde internet y analizarla, sin que un administrador tenga que añadir
el servidor a una lista. Al mismo tiempo, que nadie pueda usar DataFlow para llegar a la red
interna donde corre, a su propia base de datos, a los metadatos de la nube ni para atacar a
terceros.

## Por qué hoy no basta con ampliar la lista

Quien se conecta a la base es el **servidor** de DataFlow, no el navegador. Hoy la única
defensa es `DATAFLOW_*_ALLOWED_HOSTS` (coincidencia exacta del nombre,
`ingestion/application.py`). Si se abriera a cualquier servidor sin más:

| Riesgo                                      | Cómo ocurre hoy                                                                                                         |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Acceso a la red interna (SSRF)              | `127.0.0.1`, `10.x`, `postgres` (el servicio de Compose) o `169.254.169.254` serían destinos válidos                    |
| Ataque a la propia base de DataFlow         | En Compose la API comparte red con `postgres`, cuya contraseña de desarrollo es pública (`dataflow_local`)              |
| Nombre que cambia de IP (DNS rebinding)     | El nombre se comprueba, pero libpq y FreeTDS lo vuelven a resolver al conectar                                          |
| Secretos al alcance del proceso que conecta | `platform/isolation.py` pasa `os.environ` completo al subproceso: `DATAFLOW_DATABASE_URL`, `DATAFLOW_AI_API_KEY`, `PG*` |
| Contraseña interceptada                     | PostgreSQL usa `sslmode=prefer` (sin cifrado si el servidor no lo ofrece, sin verificar certificado)                    |
| Servidor hostil que agota memoria           | `fetchall()` de hasta `max_rows + 1` filas sin límite de bytes por celda ni total; consultas al catálogo sin `LIMIT`    |
| Fuerza bruta contra bases de terceros       | No hay límite de intentos de conexión (sólo en el inicio de sesión)                                                     |
| Redirecciones del controlador               | Azure SQL puede redirigir la sesión TDS a otro host:puerto que no pasa por ninguna comprobación                         |

## Modos de acceso

| Modo        | Configuración                                                            | Destinos permitidos                                                                                      |
| ----------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| Desactivado | Lista vacía y `DATAFLOW_DATABASE_PUBLIC_ACCESS=false` (por defecto)      | Ninguno (503 `*_DISABLED`, como hoy)                                                                     |
| Lista       | `DATAFLOW_POSTGRESQL_ALLOWED_HOSTS` / `DATAFLOW_SQLSERVER_ALLOWED_HOSTS` | Sólo esos nombres, aunque sean privados (bases de la propia organización). Sin cambios de comportamiento |
| Pública     | `DATAFLOW_DATABASE_PUBLIC_ACCESS=true`                                   | Los de la lista **y** cualquier servidor cuyas direcciones sean todas públicas y no estén denegadas      |

La lista sigue sirviendo para bases privadas de confianza; el modo público se suma a ella, no
la sustituye. En modo público sólo PostgreSQL acepta servidores fuera de la lista mientras
SQL Server no pueda verificar certificados ni impedir redirecciones (ver «Decisiones del usuario»).

## Regla `database-destination-v1`

Función pura en `integrations/sources/destination.py`: recibe el servidor, el puerto, las
direcciones resueltas y la política (modo, lista, denegados), y devuelve `Permitido(ip)` o
`Denegado(código)`. No resuelve nombres ni lee la configuración: quien llama le pasa todo.

1. Servidor en la lista (coincidencia exacta, sin distinguir mayúsculas) → permitido, fijado a
   su primera dirección resuelta. No se mira el tipo de dirección.
2. Fuera de la lista y modo público desactivado → `*_HOST_NOT_ALLOWED` (como hoy).
3. Sin direcciones (A y AAAA, plazo de 5 s) → `DATABASE_HOST_UNKNOWN`.
4. **Alguna** dirección no global → `DATABASE_HOST_PRIVATE`. Se rechaza el nombre entero aunque
   otras direcciones sean públicas. No global: `ipaddress.ip_address(x).is_global` falso
   (privadas, `127/8`, `0/8`, `169.254/16`, `100.64/10`, multidifusión, reservadas, `::1`,
   `fc00::/7`, `fe80::/10`…) y, en IPv6, la IPv4 incrustada de `::ffff:0:0/96`, `64:ff9b::/96`
   y `2002::/16` se comprueba como IPv4.
5. Alguna dirección denegada → `DATABASE_HOST_PRIVATE` (mismo código: no revela qué está
   denegado). Denegadas: las del servidor de `DATAFLOW_DATABASE_URL` (por si la base de
   DataFlow es un servicio gestionado con IP pública) y las de `DATAFLOW_DATABASE_DENIED_HOSTS`
   (nombres o rangos CIDR de otra infraestructura propia).
6. Permitido → se conecta **a esa IP**, nunca al nombre.

La regla se aplica dos veces: en la API, para responder rápido sin lanzar el subproceso, y en el
subproceso, justo antes de conectar, que es la que cuenta (la resolución de la API puede haber
cambiado). La validación actual del campo servidor (`^[A-Za-z0-9.\-]+$`) se mantiene: impide
listas de hosts de libpq (`a,b`), instancias de SQL Server (`host\instancia`) y rutas de socket.

## Conexión fijada y cifrada

| Motor      | Modo lista (como hoy)             | Modo público                                                                                                         |
| ---------- | --------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| PostgreSQL | `host=<nombre>`, `sslmode=prefer` | `host=<nombre>` + `hostaddr=<ip fijada>`, `sslmode=verify-full`, `sslrootcert=system` o el certificado de la persona |
| SQL Server | `encryption=require`              | No disponible en esta fase                                                                                           |

- `hostaddr` hace que libpq conecte a la IP comprobada y use el nombre sólo para verificar el
  certificado (libpq 18.0 incluido en `psycopg[binary]`; `sslrootcert=system` exige libpq ≥ 16).
- Muchos servicios gestionados (Amazon RDS, Azure, Cloud SQL) firman con su propia autoridad.
  Campo opcional **«Certificado del servidor»** (PEM, hasta 16 KB) dentro de «Opciones
  avanzadas»; se usa en esa conexión y se descarta, como la contraseña.
- Sin cifrado verificable → `DATABASE_TLS_UNVERIFIED` con un mensaje que explica qué falta.

## Límites frente a un servidor hostil

El servidor remoto lo controla la persona que conecta, así que todo lo que devuelve se trata
como entrada no confiable:

- Consultas al catálogo con `LIMIT` (500 tablas, 5000 columnas).
- Copia con `fetchmany(1000)` y cuenta de bytes: una celda de más de 64 KB omite la tabla con su
  motivo; al pasar de `DATAFLOW_DATABASE_MAX_BYTES` (50 MB) se detiene la copia
  (`DATABASE_TOO_LARGE`). Nunca se trunca, igual que hoy con las filas.
- Límite de memoria del subproceso (`RLIMIT_AS`, 1 GiB, en Linux; en Windows sólo el plazo).
- Los mensajes del servidor nunca llegan a la persona ni al registro: sólo los códigos propios.

## Intentos

Tabla `database_attempts` (migración **0029**, aditiva): huellas SHA-256 de usuario, IP de
origen y dirección de destino, éxito y fecha. Cuentan «Ver esquema» y «Analizar». Se purgan a
las 24 h.

| Límite                                  | Por defecto  | Variable                                |
| --------------------------------------- | ------------ | --------------------------------------- |
| Intentos por usuario                    | 10 en 15 min | `DATAFLOW_DATABASE_ATTEMPTS_PER_USER`   |
| Intentos fallidos por usuario y día     | 30           | `DATAFLOW_DATABASE_FAILURES_PER_DAY`    |
| Intentos hacia un mismo destino (todos) | 20 en 15 min | `DATAFLOW_DATABASE_ATTEMPTS_PER_TARGET` |

Al superarlo: 429 `DATABASE_RATE_LIMITED`. El límite por destino protege a terceros de que
DataFlow se use para probar contraseñas contra su servidor.

## Aislamiento

**32A — en la aplicación.** `run_isolated` deja de heredar `os.environ`: pasa sólo `PATH`,
`SYSTEMROOT`, `TEMP`/`TMP`, `HOME`, `PYTHONPATH` si existe y `POLARS_MAX_THREADS`. Sin
`DATAFLOW_*`, `PG*`, `FREETDS*`, `SSL*` ni variables de proxy. Vale para todos los pasos
aislados, no sólo para las bases.

**32B — en el despliegue.** Nuevo servicio `connector` (misma imagen,
`python -m dataflow.bootstrap.connector`) que hace las copias y fotos de bases. La API lo llama
por HTTP interno con un token compartido cuando `DATAFLOW_CONNECTOR_URL` está definido; si no,
usa el subproceso local como hoy.

```
red backend (interna) : web, api, worker, postgres
red connector (interna): api ◀──▶ connector
red egress            : connector ──▶ internet   (cortafuegos: sin RFC 1918, 169.254/16, 100.64/10)
```

- `connector` no tiene credenciales de la base de DataFlow, ni clave de IA, ni volúmenes;
  sistema de archivos de sólo lectura, usuario sin privilegios, límite de memoria y CPU.
- La red `egress` necesita además una regla de cortafuegos (cadena `DOCKER-USER` o el grupo de
  seguridad de la nube) que niegue rangos privados y de metadatos: Docker por sí solo deja
  salir hacia la red local del anfitrión. Es la defensa que cubre lo que la regla no ve
  (redirecciones del controlador, errores de libpq o FreeTDS).
- Con `DATAFLOW_DATABASE_PUBLIC_ACCESS=true` y sin `DATAFLOW_CONNECTOR_URL`, la API **no
  arranca**, salvo con `DATAFLOW_DATABASE_PUBLIC_UNISOLATED=true` (sólo para desarrollo local),
  igual que `bootstrap/operations.py` falla al arrancar cuando falta una pieza.

## Experiencia

Sin pasos nuevos para la persona. En «Conectar base de datos», con el modo público activo:

- Una nota: «Tu base debe aceptar conexiones desde estas direcciones: …» (IP de salida de
  DataFlow, `DATAFLOW_DATABASE_EGRESS_IPS`) y «Usa un usuario con permiso sólo de lectura».
- «Opciones avanzadas» plegadas con el certificado del servidor.
- Errores en lenguaje llano:

| Código                    | Mensaje                                                                                                               |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_HOST_PRIVATE`   | Esa dirección pertenece a una red privada. DataFlow sólo se conecta a servidores accesibles desde internet.           |
| `DATABASE_HOST_UNKNOWN`   | No se encontró ese servidor. Revisa el nombre.                                                                        |
| `DATABASE_TLS_UNVERIFIED` | No se pudo verificar la conexión cifrada. Si tu proveedor usa su propio certificado, añádelo en «Opciones avanzadas». |
| `DATABASE_TOO_LARGE`      | La base supera el tamaño que se puede copiar. Elige un esquema con menos datos.                                       |
| `DATABASE_RATE_LIMITED`   | Demasiados intentos de conexión. Espera unos minutos.                                                                 |

## API

- `GET /api/v1/database-access` (`getDatabaseAccess`): `{"mode": "disabled" | "allowlist" |
"public", "engines": ["postgresql", "sqlserver"], "egress_ips": [...]}`. La web decide con
  esto qué mostrar en lugar de descubrirlo por el error 503.
- `PostgresConnection` añade `ca_certificate: str | None` (PEM, hasta 16 KB). No entra en el
  plan, en la huella de idempotencia ni en el registro.
- Errores nuevos: 422 `DATABASE_HOST_PRIVATE`, `DATABASE_HOST_UNKNOWN`,
  `DATABASE_TLS_UNVERIFIED`; 413 `DATABASE_TOO_LARGE`; 429 `DATABASE_RATE_LIMITED`.
- `source_origin` añade `access` (`allowlist` | `public`) y `tls` (`verified` | `encrypted` |
  `none`). Es JSON del plan: sin migración.

## Configuración

| Variable                                | Por defecto | Uso                                                       |
| --------------------------------------- | ----------- | --------------------------------------------------------- |
| `DATAFLOW_DATABASE_PUBLIC_ACCESS`       | `false`     | Activa el modo público                                    |
| `DATAFLOW_DATABASE_DENIED_HOSTS`        | `[]`        | Nombres o CIDR propios que nunca se conectan              |
| `DATAFLOW_DATABASE_EGRESS_IPS`          | `[]`        | Direcciones de salida que se muestran a la persona        |
| `DATAFLOW_DATABASE_MAX_BYTES`           | `52428800`  | Tamaño máximo de una copia                                |
| `DATAFLOW_DATABASE_ATTEMPTS_PER_USER`   | `10`        | Intentos por usuario en 15 min                            |
| `DATAFLOW_DATABASE_FAILURES_PER_DAY`    | `30`        | Intentos fallidos por usuario y día                       |
| `DATAFLOW_DATABASE_ATTEMPTS_PER_TARGET` | `20`        | Intentos hacia un destino en 15 min                       |
| `DATAFLOW_CONNECTOR_URL`                | —           | Servicio `connector` (32B)                                |
| `DATAFLOW_CONNECTOR_TOKEN`              | —           | Token compartido API ↔ connector (secreto)                |
| `DATAFLOW_DATABASE_PUBLIC_UNISOLATED`   | `false`     | Permite el modo público sin `connector` (sólo desarrollo) |

## Piezas

| Pieza                                         | Dónde                                                 |
| --------------------------------------------- | ----------------------------------------------------- |
| Regla `database-destination-v1` (pura)        | `integrations/sources/destination.py`                 |
| Resolución y fijación antes de conectar       | `integrations/sources/postgresql_reader.py`           |
| Límites de bytes y `fetchmany`                | `postgresql_reader.py`, `sqlserver_reader.py`         |
| Entorno mínimo del subproceso                 | `platform/isolation.py`                               |
| Intentos (`database_attempts`, 0029)          | `modules/ingestion/infrastructure.py`                 |
| Comprobación previa, intentos y modo          | `modules/ingestion/application.py`                    |
| Ruta `database-access` y campo de certificado | `modules/ingestion/presentation.py`, `contracts.py`   |
| Servicio `connector` (32B)                    | `bootstrap/connector.py`, `infrastructure/compose/`   |
| Nota, opciones avanzadas y mensajes           | `apps/web/src/features/ingestion/database-fields.tsx` |

## Pruebas

- `destination.py`: tabla de casos con cada rango no global en IPv4 e IPv6, IPv4 incrustada,
  nombres con mezcla de direcciones públicas y privadas, lista, denegados por nombre y por CIDR,
  la IP de `DATAFLOW_DATABASE_URL`.
- Fijación: un resolvedor falso que devuelve una IP pública en la API y `127.0.0.1` en el
  subproceso → rechazado (rebinding).
- PostgreSQL real de pruebas: modo público rechaza `127.0.0.1` y `localhost`; modo lista sigue
  aceptándolos; `verify-full` contra un servidor con certificado autofirmado falla sin el campo
  y funciona con él.
- Servidor hostil simulado: celdas de 1 MB, catálogo de 10 000 tablas, copia que pasa de
  `MAX_BYTES` → omitida o `DATABASE_TOO_LARGE`, sin agotar memoria.
- `isolation.py`: el subproceso no ve `DATAFLOW_DATABASE_URL`, `DATAFLOW_AI_API_KEY` ni `PG*`.
- Intentos: los tres límites con peticiones concurrentes (mismo bloqueo consultivo que el
  inicio de sesión).
- `test_architecture.py`: `destination.py` no importa la configuración ni redes; los lectores
  sólo conectan con una IP que salió de la regla.
- 32B: prueba de Compose donde `connector` no alcanza `postgres:5432` ni `169.254.169.254`.

## Etapas y criterios de aceptación

| Etapa | Contenido                                                                    | Se puede activar en producción |
| ----- | ---------------------------------------------------------------------------- | ------------------------------ |
| 32A   | Regla, fijación, TLS verificado, límites, intentos, entorno mínimo, interfaz | No                             |
| 32B   | Servicio `connector`, redes, cortafuegos de salida, arranque condicionado    | Sí                             |

La fase está terminada cuando una persona puede conectar una base PostgreSQL pública (por
ejemplo, Pagila en un servicio gestionado) y analizarla, y las pruebas demuestran que ninguno
de los riesgos de la tabla inicial sigue abierto.

## Limitaciones

- SQL Server sigue sólo con lista hasta resolver la verificación del certificado y las
  redirecciones.
- Bases detrás de una VPN o sin IP pública siguen necesitando la lista (o un túnel que la
  persona exponga).
- El límite de memoria del subproceso sólo existe en Linux.
- Un servidor público legítimo que comparte IP con algo denegado no se puede conectar.

## Decisiones del usuario

1. **SQL Server sigue sólo con lista en esta fase.** pymssql (FreeTDS 1.5) cifra pero no
   verifica el certificado desde sus parámetros, y no está comprobado si sigue la redirección
   de Azure SQL. El controlador (un `freetds.conf` temporal con `ca file` y
   `check certificate hostname`, u ODBC Driver 18 con `TrustServerCertificate=no`) se decide
   en una fase posterior.
2. **Sin cifrado sin verificar como alternativa.** No se usa `sslmode=require` cuando la
   verificación falla: expondría la contraseña a quien intercepte el camino. Si el proveedor
   usa su propia autoridad, la persona aporta el certificado.
3. **Límites por defecto confirmados**: 50 MB por copia, 64 KB por celda y 10 intentos por
   usuario en 15 min, ajustables por configuración.
