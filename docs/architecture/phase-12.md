# Fase 12 — Nuevas fuentes: Excel, SQL Server y PDF

Estado: **plan objetivo**, sin implementación. Se separa de la [Fase 11](phase-11.md) para no mezclar dos cambios grandes: la automatización funciona primero con CSV y después se amplían las fuentes.

## Objetivo

Que la fuente activa de una sesión de análisis (Fase 11A) pueda ser, además de un CSV, una hoja de Excel, una tabla o vista de SQL Server, o una tabla de un PDF con texto.

## Principio común

Cada adaptador produce **una única representación tabular identificable**, igual a la que hoy produce el CSV: columnas con IDs, Parquet inmutable y hash lógico (Fase 6). Todo lo posterior —perfil, calidad, interpretación, políticas, limpieza, análisis, dashboard y auditoría— funciona sin cambios para cualquier fuente.

| Regla                            | Aplicación                                                                                                                        |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Original o extracción inmutable  | El archivo subido se conserva con su hash; una extracción de SQL Server se materializa y se conserva igual                        |
| Vista previa antes de activar    | La persona ve la tabla candidata antes de que pase a ser la fuente activa (o la política la acepta, 11B)                          |
| Una tabla por entrada            | Hoja, tabla de PDF o tabla/vista de SQL Server: se elige una; nunca se combinan en silencio                                       |
| Lectores aislados                | Cada biblioteca se importa sólo en su adaptador (`integrations/sources/`), con prueba AST, como el SDK de IA                      |
| Versión del lector en el entorno | La versión de cada biblioteca entra en el hash de entorno: un cambio de biblioteca no altera en silencio resultados reproducibles |
| Errores explícitos               | Formato no soportado, tabla ambigua o límite superado → error con código; nunca una tabla «aproximada»                            |

Operaciones del catálogo (internas de ingesta, como `ingestion.read_csv@1`):

| Operación                    | Entrega |
| ---------------------------- | ------- |
| `ingestion.read_xlsx@1`      | 12A     |
| `ingestion.read_sqlserver@1` | 12B     |
| `ingestion.read_pdf_table@1` | 12C     |

## 12A · Excel

- **Enumerar** hojas y, si existen, tablas con nombre (ListObjects); **seleccionar una**.
- **Vista previa** de la tabla candidata antes de activarla.
- Tratamiento explícito de:
  - **Fórmulas**: se lee el **resultado almacenado** en el archivo; nunca se recalcula. Una celda con fórmula sin resultado guardado → error con la celda.
  - **Fechas**: Excel guarda números de serie; se convierten a fecha ISO sólo si la celda tiene formato de fecha, y siempre a la representación canónica de texto. La conversión de tipo posterior sigue siendo la de Limpieza (Fase 6).
  - **Números**: se escriben en su representación canónica; un valor binario que no tiene representación decimal exacta se registra como advertencia de la extracción.
  - **Cabeceras**: fila elegida (por defecto la primera); cabeceras vacías o duplicadas → error, como en el CSV.
  - **Celdas combinadas** y hojas protegidas: error claro.
- **Límites**: tamaño de archivo y de tabla **expandida** (filas × columnas tras descomprimir el XLSX), para evitar archivos pequeños que se expanden a millones de celdas.
- Formatos: `.xlsx`. `.xls` antiguo, `.xlsm` con macros y `.xlsb` se rechazan con `UNSUPPORTED_FORMAT` en esta entrega.
- Biblioteca propuesta: `polars.read_excel` con motor `calamine` (`fastexcel`), leyendo como texto.

Cierre: un `.xlsx` con el mismo contenido que un CSV del repositorio produce la misma tabla y las mismas cifras.

## 12B · SQL Server

- **SQLAlchemy** con controlador **ODBC** (`pyodbc` + Microsoft ODBC Driver 18). La imagen de Docker debe instalar `msodbcsql18`, lo que exige aceptar la licencia de Microsoft al construirla (decisión de despliegue).
- **Credenciales protegidas**: conexiones guardadas por proyecto con la contraseña **cifrada** con una clave del servidor (secreto de Docker, como la clave de IA). Nunca vuelven al frontend, a los logs ni a OpenAPI.
- **Usuario de sólo lectura** recomendado y comprobado al conectar (aviso si tiene permisos de escritura).
- **Tablas y vistas autorizadas**: la persona elige de una lista (`INFORMATION_SCHEMA`), opcionalmente restringida por configuración de la conexión.
- **Identificadores validados** contra esa lista y citados (`[esquema].[tabla]`); valores (límites, filtros) **parametrizados**. **No se acepta SQL arbitrario** en esta entrega.
- **Timeouts y límites**: tiempo de consulta, filas y bytes extraídos; superarlos aborta la extracción sin publicar nada.
- **Conexiones cifradas** (`Encrypt=yes`; `TrustServerCertificate` sólo por configuración explícita).
- **Extracción materializada e inmutable**: el resultado se escribe a Parquet como una importación; la versión registra conexión, objeto, columnas, hora, filas y bytes.
- **Consistencia**: se registra si la extracción se hizo con una vista consistente (`SNAPSHOT` o `READ COMMITTED SNAPSHOT` disponibles) o sin garantía, y la interfaz lo muestra.
- SQL Server se consulta **sólo durante la extracción**, nunca al renderizar un dashboard.

Persistencia: `ingestion_connections` (cifrada) y la procedencia de cada extracción.

Cierre: extracción de una tabla de prueba en un contenedor SQL Server de CI; contraseña ausente de respuestas, logs y auditoría; un objeto no autorizado se rechaza.

## 12C · PDF

- Extracción de tablas de **PDF con capa de texto**; un PDF escaneado sin texto → `PDF_NO_TEXT_LAYER`.
- **Selección y revisión**: se listan las tablas candidatas por página con su vista previa; la persona elige una.
- **Validación** de estructura (número de columnas constante, cabeceras) y de valores.
- **No se activa en silencio una extracción ambigua**: si hay varias tablas candidatas o la estructura es dudosa, se exige elección humana aunque haya una política activa.
- Tablas que continúan en varias páginas: sólo si la persona confirma la unión.
- **OCR** en un incremento separado.
- Biblioteca propuesta: `pdfplumber`.

Cierre: un PDF de ejemplo produce exactamente la tabla esperada; uno con dos tablas pide elección; uno escaneado se rechaza con su código.

## Cierre común

Cada adaptador produce una única representación tabular identificable que recorre el mismo pipeline posterior de la Fase 11, sin rutas especiales por fuente.

## Archivos previstos

```
apps/api/src/dataflow/
├── integrations/sources/        # único sitio que importa cada biblioteca (prueba AST)
│   ├── xlsx_reader.py           # 12A
│   ├── sqlserver_reader.py      # 12B
│   └── pdf_reader.py            # 12C
└── modules/ingestion/           # + operaciones read_xlsx, read_sqlserver, read_pdf_table; conexiones
apps/web/src/features/ingestion/ # + selector de tipo de fuente, hoja/tabla, conexión SQL, tabla de PDF
examples/                        # ventas.xlsx, ventas_tabla.pdf
```

## Decisiones abiertas

1. Controlador de SQL Server: `pyodbc` + ODBC Driver 18 (recomendado) o `pymssql` (sin ODBC, menos soporte).
2. Límites por defecto de tamaño (archivo, tabla expandida, extracción SQL).
3. ¿`.xlsm` sin ejecutar macros se acepta en una entrega posterior?
4. Restricción de objetos SQL: lista abierta del esquema o lista blanca por conexión.
