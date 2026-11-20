# ADR-049 — Modelo de datos de tablas relacionadas, foto del esquema y PostgreSQL

Estado: aceptado e implementado en la Fase 31 (API 0.39.0, sin migración). Documentación:
[Fase 31](../architecture/phase-31.md). Amplía [ADR-035](035-regional-sources-tables-and-structure.md)
(fuentes de la Fase 18): las tablas de una misma carga forman un modelo de datos y se analizan
también juntas.

## Contexto

Hasta la Fase 30 cada tabla se analizaba por separado: un archivo por carga, y las varias tablas
de un libro, un PDF o una base de SQL Server como versiones independientes. Con datos repartidos
en varias tablas (estudiantes, asistencia, notas y carreras) no se podían cruzar: no había forma
de ver «asistencia y promedio por carrera». La conexión a SQL Server existía, pero escondida en
un panel lateral, sin elegir esquema y con cinco tablas como mucho, y no había otros motores ni
forma de ver cómo se relacionan las tablas antes de analizar.

## Decisión

1. **Tres formas de traer los datos** en la pantalla de carga: «Cargar archivo» (como antes),
   «Cargar varios archivos relacionados» (de 2 a 5 CSV o .xlsx) y «Conectar base de datos»
   (SQL Server o PostgreSQL, con esquema). Siguen sin mapeos ni aprobaciones.
2. **Foto del esquema** («Ver esquema»): antes de analizar, la API devuelve el modelo de datos
   (tablas con columnas y claves, relaciones y vistas que se analizarían) sin guardar nada. El
   mismo modelo y su diagrama acompañan a cada versión del conjunto.
3. **Regla `relations-v1`** (pura, `ingestion/relations.py`), sobre todas las tablas a la vez:
   - **clave**: columna sin vacíos ni repetidos; se muestra como clave (PK) si su nombre es de
     identificador (`id`, `codigo`, `IdVenta`…) o si otra tabla apunta a ella;
   - **relación**: declarada por la base (clave foránea de una columna) o detectada por el
     nombre (la misma columna en las dos tablas, o una clave genérica combinada con el nombre de
     la otra tabla: `id_estudiante` → `estudiantes.id`; `id` contra `id` no cuenta). Sólo vale si
     **todos** los valores existen en la clave (al menos dos distintos). Cardinalidad N:1 o 1:1.
     Una columna que coincide con varias tablas no se usa;
   - **papeles**: tablas de hechos (apuntan a otras y nadie apunta a ellas), entidad principal (a
     la que apuntan más tablas de hechos), dimensiones (describen a otra) y por separado.
4. **Vistas**, cada una una versión más con su CSV estándar como original:
   - **de cada tabla de hechos**: la tabla con lo que apunta, de muchos a uno y a dos pasos
     (asistencia + estudiante + carrera); sus registros no cambian;
   - **general por entidad**: un registro por cada entidad (estudiante) con sus dimensiones y, de
     cada tabla de hechos, registros, promedio de cada columna numérica y % de la categoría menos
     frecuente de cada columna de dos valores (decimales exactos, sin redondear). Es la que
     permite cruzar todas las tablas («% de asistencia y promedio de nota por carrera»).
     Ante la duda no se une y se explica por qué (dos columnas hacia la misma tabla, más de dos
     pasos, más de 128 columnas, valores sin pareja).
5. **Versión que se abre**: la vista general si hay dos tablas de hechos o más; si no, la vista
   de la tabla de hechos; sin relaciones, la tabla con más registros. Todas las tablas y vistas se
   analizan con el recorrido automático completo. La decisión (modelo, vistas y motivos) queda en
   `source_origin` del plan, inmutable: no hace falta migración.
6. **Lectura igual que una carga normal**: en el subproceso de ingesta (modo `relate`), cada CSV
   con su codificación, separador y valores regionales; cada libro con la tabla principal de
   `xlsx-selection-v2`. La unión compara las celdas canónicas (texto exacto: `001` no es `1`).
7. **Bases de datos**: copia de un solo uso de las tablas de **un esquema**, en sólo lectura;
   sólo servidores permitidos; la contraseña no se guarda. SQL Server pasa a
   `sqlserver-selection-v2` (esquema opcional y hasta 10 tablas); PostgreSQL usa
   `postgresql-selection-v1` (esquema `public` por defecto, hasta 10 tablas, transacción de sólo
   lectura con tiempo máximo por consulta; tipos sin lectura canónica excluidos con su motivo).
   Las claves foráneas declaradas entran en `relations-v1`.

## Decisiones tomadas sin consulta

- **Vista general con métricas por entidad** en vez de uniones dentro de cada consulta de la
  investigación: reutiliza todo el recorrido automático y cada cifra sigue siendo trazable a su
  tabla. Las métricas son las mínimas que no inventan nada (registros, promedios y porcentajes);
  las sumas o máximos se pueden calcular después sobre la vista de hechos.
- **Sin migración ni trabajo de fondo nuevo**: las vistas se calculan al subir, en el mismo
  subproceso que lee los archivos, y se guardan como originales. Las ejecuciones admiten una sola
  tabla de entrada.
- **Ver el esquema crea el proyecto** si aún no existe (las rutas cuelgan de un proyecto); no
  registra versiones.
- **Un solo envío JSON** con los archivos en base64 (hasta 5 archivos y 10 MB entre todos; cada
  uno, 5 MB) en vez de multipart: no añade dependencias. El proxy web admite ese tamaño sólo en
  estas rutas y da 60 s a las copias y fotos de bases y a esta lectura.
- **Excepción acotada en la prueba de arquitectura**: los lectores de fuentes no pueden importar
  `psycopg`. El de PostgreSQL lo importa sólo dentro de `connect()`, como el de SQL Server con
  `pymssql`, y la prueba comprueba además que no lee la configuración ni la conexión de la
  aplicación.
- **SSL `prefer`** en PostgreSQL (un servidor local sin SSL también vale); SQL Server sigue
  exigiendo cifrado.
- De un libro sólo cuenta su tabla principal; los PDF no entran en el conjunto.

## Consecuencias

- Un conjunto de N tablas con H tablas de hechos genera N + H + 1 versiones, todas analizadas.
- `SourceOrigin` admite `postgresql` y `related`, con `joined`, `view_kind`, `tables`
  (columnas, claves y papel), `relations` (cardinalidad) y `views`.
- Una copia de SQL Server con tablas relacionadas abre ahora la vista principal, no la tabla más
  grande; `sqlserver-selection-v1` sigue descrita para las cargas anteriores.
