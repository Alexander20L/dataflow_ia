# Fase 18 — Ampliar fuentes

Estado: **implementada** (18A archivos y 18B SQL Server y PDF; API 0.25.0, sin migración,
catálogo de carga `analysis-v13`). Decisión: [ADR-035](../adr/035-regional-sources-tables-and-structure.md).
Plan general en [Fase 14](phase-14.md).

## Objetivo

Que los datos reales se analicen sin pasos manuales: CSV y Excel con formatos regionales,
libros con varias tablas, versiones cuya estructura cambia, tablas de SQL Server y tablas de PDF.
Ante la duda no se adivina: se explica.

## Etapa 18A — archivos

### CSV regional (`ingestion.read_csv@2`)

- Codificación resuelta al subir: UTF-8 (con o sin BOM) y, si no, Windows-1252; fijada en el
  plan. Otro contenido falla con `CSV_ENCODING`.
- Valores con `regional-values-v1`:

| Valor               | Lectura                      | Celda                       |
| ------------------- | ---------------------------- | --------------------------- |
| `1.234,56`          | coma decimal, punto de miles | `1234.56`                   |
| `1,234.56`          | punto decimal, coma de miles | `1234.56`                   |
| `31/12/2024`        | día/mes/año                  | `2024-12-31`                |
| `1.234` (sola)      | ambigua                      | la del archivo o sin cambio |
| `01/02/2024` (sola) | ambigua                      | texto, con motivo           |

Una columna se reescribe sólo si todos sus valores admiten una única lectura. En CSV, la
convención del archivo (coma o punto decimal, probada por otra columna) decide los valores
ambiguos; en Excel no, porque los números nativos ya son canónicos.

### Excel (`ingestion.read_xlsx@2`, `xlsx-selection-v2`)

- Los textos con números o fechas regionales se leen con la misma regla.
- La hoja o tabla principal es la de v1. Hasta cuatro tablas más con al menos dos columnas con
  cabecera y dos registros se analizan como **versiones propias** de la misma carga (comparten el
  original y la cuota lo cuenta una vez). Portadas y notas de una columna quedan omitidas.

### Cambios de estructura (`structure-comparison-v1`)

Al terminar la carga se compara con la versión anterior del mismo archivo (y de la misma hoja o
tabla): columnas nuevas, quitadas y con otro tipo o papel. Sólo se informa.

### API e informe

| Ruta                         | Respuesta                                                                                        |
| ---------------------------- | ------------------------------------------------------------------------------------------------ |
| `GET /versions/{id}/reading` | `reading` (codificación, separador, columnas leídas y columnas dejadas como texto) y `structure` |

El informe PDF añade «Lectura del archivo» y «Cambios respecto de la versión N»; ambos se fijan en
el plan del informe. Las versiones anteriores responden `reading: null`.

### Interfaz

Debajo del resumen, «Lectura del archivo» (sólo si hubo algo que interpretar: Windows-1252,
valores regionales o columnas dejadas como texto) y «Cambios respecto de la versión N». En la lista
de versiones, las de un libro indican su hoja o tabla. Sin botones de decisión.

### Pruebas

`tests/test_phase18_sources.py`: regla regional (números, convención de archivo, fechas, casos
ambiguos), CSV Windows-1252 de extremo a extremo con el original intacto, cambios de estructura,
varias tablas como versiones con cuota única, secciones del informe y revisión fijada en su plan.
E2E `regional.spec.ts`: el CSV regional se explica sin acciones.

## Etapa 18B — SQL Server y PDF

Decisiones del usuario: `pymssql` (sin drivers del sistema), credenciales **no guardadas** y
`pdfplumber`. Ambas dependencias sólo se importan en el subproceso de ingesta.

### SQL Server (`POST /projects/{id}/imports/sqlserver`)

- Copia **de un solo uso**: servidor, puerto, base, usuario y contraseña viajan en la petición; la
  contraseña sólo llega al directorio temporal del subproceso (que se borra) y no entra en el plan,
  la huella de idempotencia, los registros ni el original.
- Sólo servidores de `DATAFLOW_SQLSERVER_ALLOWED_HOSTS` (vacío: 503 `SQLSERVER_DISABLED`; otro
  host: 422 `SQLSERVER_HOST_NOT_ALLOWED`). Evita usar la API para alcanzar equipos internos.
- Conexión cifrada (`encryption=require`); se recomienda una cuenta con sólo `SELECT`.
- `sqlserver-selection-v1`: tablas de usuario con al menos dos columnas de tipos admitidos y dos
  registros, dentro de los límites de registros y columnas, de mayor a menor (registros ×
  columnas), hasta cinco. Una tabla se copia **completa o nada** (nunca se trunca); columnas
  binarias, XML, espaciales o `sql_variant` se dejan fuera con su motivo.
- Cada tabla es una versión con su CSV estándar como original inmutable (`esquema.tabla.csv`) y
  se lee con `read_csv@2`. Celdas canónicas: decimales sin exponente, `true`/`false`, fechas ISO
  (una columna de fecha y hora con todas las horas a medianoche se publica como fecha).
- Una copia posterior de la misma tabla se compara con la anterior (cambios de estructura).

### PDF (`POST /projects/{id}/imports/pdf`, `ingestion.read_pdf@1`)

- `pdf-selection-v1`: tablas que pdfplumber detecta por sus líneas, con una fila de cabecera de
  nombres únicos, al menos dos columnas y dos registros. Una tabla cuya cabecera se repite en la
  página siguiente se une. La mayor es la principal y hasta cuatro más son versiones propias que
  comparten el PDF original.
- `read_pdf@1` vuelve a extraer del original la tabla fijada en el plan (segmentos página/índice)
  y aplica `regional-values-v1` con convención de archivo. Los saltos de línea dentro de una celda
  se vuelven espacios.
- Rechazos con motivo, sin registrar nada: `PDF_NO_TEXT` (escaneado; haría falta OCR),
  `PDF_NO_TABLES`, `PDF_ENCRYPTED`, `PDF_MALFORMED`, `PDF_PAGE_LIMIT` (más de 200 páginas).

### Origen e interfaz

`source_origin` (en la versión y en `GET /versions/{id}/reading`) dice de qué tabla sale cada
versión, qué más se analizó aparte y qué se omitió; el informe lo incluye en «Lectura del
archivo». En `/new` se puede subir un PDF y conectar SQL Server (formulario de conexión; la
contraseña se borra del formulario al terminar).

### Pruebas

`tests/test_phase18b_sources.py`: lector de SQL Server con una conexión simulada (selección,
celdas canónicas, tablas completas o nada, columnas excluidas), conexión fallida sin eco de la
contraseña, lista de servidores permitidos, versiones por tabla sin la contraseña en planes ni
originales, cambios de estructura entre copias; PDF con tabla en dos páginas, PDF escaneado o sin
tablas, versiones por tabla con valores regionales y origen en el informe. E2E: PDF con dos
tablas y SQL Server desactivado.
