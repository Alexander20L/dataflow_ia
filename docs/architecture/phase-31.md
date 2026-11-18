# Fase 31 — Tablas relacionadas, foto del esquema y bases de datos

Estado: **implementada** (API 0.39.0, sin migración). Decisión:
[ADR-049](../adr/049-related-sources-and-postgresql.md).

## Objetivo

Que se puedan subir varias tablas relacionadas por columnas identificadoras (estudiantes,
asistencia, notas, carreras) o conectar un esquema de SQL Server o PostgreSQL, ver cómo se
relacionan antes de analizar y obtener un análisis general del negocio con todas las tablas,
además del análisis de cada tabla.

## Recorrido

```
pantalla de carga ─▶ «Cargar archivo» (como antes)
                  ─▶ «Cargar varios archivos relacionados» ─▶ «Ver esquema» (opcional) ─▶ analizar
                  ─▶ «Conectar base de datos» (SQL Server | PostgreSQL, esquema) ─▶ «Ver esquema» ─▶ analizar
subproceso de ingesta ─▶ leer cada tabla ─▶ relations-v1: claves, relaciones, papeles y vistas
API ─▶ «Ver esquema»: el modelo (no guarda nada)
    ─▶ analizar: una versión por tabla + una por vista de hechos + la vista general
    ─▶ cada versión sigue el recorrido automático (Dataset … Informe); se abre la principal
```

## Modelo de datos (`relations-v1`)

| Concepto        | Regla                                                                            |
| --------------- | -------------------------------------------------------------------------------- |
| Clave           | Sin vacíos ni repetidos; PK si su nombre es de identificador o la apuntan        |
| Relación        | Clave foránea declarada o mismo nombre / `id_<tabla>`; todos los valores existen |
| Tabla de hechos | Apunta a otras y nadie apunta a ella                                             |
| Entidad         | La tabla a la que apuntan más tablas de hechos                                   |
| Vista de hechos | Hechos + lo que apuntan (N:1, dos pasos); registros intactos                     |
| Vista general   | Un registro por entidad + dimensiones + métricas de cada tabla de hechos         |
| Métricas        | Registros, promedio de cada número, % de la categoría menos frecuente            |
| Se abre         | Vista general con 2+ tablas de hechos; si no, la de hechos; si no, la mayor      |

## Piezas

| Pieza                                             | Dónde                                                 |
| ------------------------------------------------- | ----------------------------------------------------- |
| Regla `relations-v1` (pura)                       | `modules/ingestion/relations.py`                      |
| Lectura y modelo en el subproceso (`relate`)      | `modules/ingestion/processor.py`                      |
| Lector de PostgreSQL (`postgresql-selection-v1`)  | `integrations/sources/postgresql_reader.py`           |
| SQL Server con esquema (`sqlserver-selection-v2`) | `integrations/sources/sqlserver_reader.py`            |
| Foto del esquema y registro de tablas y vistas    | `modules/ingestion/application.py`                    |
| Contratos (`DataModel`, `RelatedView`, …)         | `modules/ingestion/contracts.py`                      |
| Rutas                                             | `modules/ingestion/presentation.py`                   |
| Pantalla de carga con tres opciones               | `apps/web/src/features/ingestion/import-project.tsx`  |
| Campos de conexión (SQL Server o PostgreSQL)      | `apps/web/src/features/ingestion/database-fields.tsx` |
| Diagrama del esquema                              | `apps/web/src/features/ingestion/schema-diagram.tsx`  |
| Modelo de datos de una versión                    | `apps/web/src/features/ingestion/related-sources.tsx` |

## API

- `POST /api/v1/projects/{id}/imports/related` (`uploadRelatedFiles`): `{"files": [{"name",
"content_base64"}]}` con 2 a 5 CSV o .xlsx. Devuelve la vista principal (o, sin relaciones,
  la tabla con más registros). Errores 422 `RELATED_INVALID`, `RELATED_FORMAT`,
  `RELATED_DUPLICATE_NAMES`, `RELATED_FILE_INVALID`; 413 `RELATED_TOO_LARGE` y
  `RELATED_JOINED_TOO_LARGE`; 415 `RELATED_CONTENT_TYPE`.
- `POST /api/v1/projects/{id}/imports/related/inspect` (`inspectRelatedFiles`),
  `…/imports/sqlserver/inspect` (`inspectSqlServer`) y `…/imports/postgresql/inspect`
  (`inspectPostgresql`): `DataModel` (tablas, relaciones, vistas, vista principal y tablas
  omitidas) sin guardar nada.
- `POST /api/v1/projects/{id}/imports/postgresql` (`importPostgresql`): servidor, puerto, base,
  `schema_name` (por defecto `public`), usuario y contraseña. 503 `POSTGRESQL_DISABLED`, 422
  `POSTGRESQL_HOST_NOT_ALLOWED`, `POSTGRESQL_CONNECTION`, `POSTGRESQL_READ` y
  `POSTGRESQL_NO_TABLES`.
- `SqlServerConnection` admite `schema_name` (opcional); 422 `SQLSERVER_SCHEMA_EMPTY`.
- `source_origin` admite `kind` `postgresql` y `related` con `joined`, `view_kind`, `tables`,
  `relations` y `views`.
- Configuración: `DATAFLOW_POSTGRESQL_ALLOWED_HOSTS` (vacía: desactivado).

## Interfaz

- **Pantalla de carga**: tres opciones como botones. Con varios archivos o con una base,
  «Ver esquema» muestra el diagrama (tablas con columnas, PK y FK, y flechas con su
  cardinalidad: continuas si se usan, discontinuas si no), las vistas que se analizarán (cuál se
  abre primero), el papel de cada tabla y cada relación con su motivo.
- **Versión**: el mismo modelo con la vista actual marcada.

## Pruebas

- `tests/test_phase31_related.py`: la regla (vista de hechos a dos pasos, vista general con dos
  tablas de hechos y métricas exactas, `id` contra `id`, valores sin pareja, clave con repetidos,
  columnas hacia la misma tabla, claves foráneas con cualquier nombre, nombres repetidos, límite
  de columnas, nombres de identificador); el subproceso con un CSV en Windows-1252 y un libro; la
  API (foto sin guardar, siete versiones, idempotencia, preview de la vista general, conjunto sin
  relaciones, validaciones); SQL Server con esquema, hasta 10 tablas y claves declaradas; y
  PostgreSQL contra la base real de pruebas (copia en sólo lectura, contraseña sin eco, servidores
  permitidos, foto y carga).
- `test_architecture.py`: `psycopg` sólo dentro de `connect()` del lector de PostgreSQL.
- E2E `related.spec.ts`: las tres opciones, el esquema de la base, «Ver esquema» con cuatro
  archivos y la vista general hasta sus registros; `regional.spec.ts`: SQL Server desactivado
  desde la nueva opción.

## Limitaciones

- Sólo relaciones de una columna; las claves compuestas y las de muchos a muchos no se usan.
- La unión compara el texto exacto de las celdas (`001` no es `1`).
- Como mucho 5 archivos o 10 tablas de una base; vistas a dos pasos de su tabla de partida.
- La vista general sólo resume con registros, promedios y porcentajes.
