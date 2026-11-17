# ADR-035 — Fuentes regionales, varias tablas y cambios de estructura

Estado: aceptado e implementado (18A y 18B; API 0.25.0, sin migración, catálogo de carga
`analysis-v13`). Documentación: [Fase 18](../architecture/phase-18.md). Cumple la fila 18 del plan
de la [Fase 14](../architecture/phase-14.md) para archivos; SQL Server y PDF son la etapa 18B. Se
apoya en [ADR-026](026-fully-automatic-single-path.md) (sin intervención), [ADR-027](027-excel-and-ai-without-configuration.md)
(Excel sin elegir hoja) y [ADR-034](034-automatic-report-and-stage-progress.md) (informe).

## Contexto

- Un CSV guardado por Excel en Windows (ANSI) se rechazaba con `CSV_ENCODING`.
- Los números con coma decimal (`1.234,56`) y las fechas `dd/mm/aaaa` quedaban como texto: la
  columna no era medida ni eje temporal y sus análisis se omitían.
- De un libro sólo se analizaba una hoja; las demás se informaban como omitidas.
- Al subir otra versión del mismo archivo no se avisaba de columnas nuevas, quitadas o con otro
  tipo.

## Decisión

1. **`ingestion.read_csv@2`**: la codificación se resuelve al subir sobre los bytes (UTF-8 con o
   sin BOM; si no, Windows-1252) y queda fijada en el plan; si tampoco es Windows-1252, falla con
   `CSV_ENCODING`. El separador se detecta con esa codificación.
2. **Regla `regional-values-v1`** (`platform/regional.py`, pura), aplicada al leer:
   - Una columna se reescribe en la celda canónica (número con punto, fecha ISO) sólo si **todos**
     sus valores admiten una única lectura: coma decimal con punto de miles, punto decimal con coma
     de miles, `dd/mm/aaaa`, `mm/dd/aaaa` o `aaaa/mm/dd`.
   - Un valor con dos lecturas que dan cifras distintas (`1.234`, `1,234`) se decide por la
     convención del archivo (otra columna que sólo admite una), **sólo en CSV** y sólo si no hay
     columnas con convenciones opuestas. Sin esa evidencia, una columna ya canónica no cambia y
     una que no lo es queda como texto con su motivo.
   - Día y mes se distinguen sólo si algún valor lo prueba (un número mayor que 12); si no, texto.
   - Sin ceros a la izquierda (pueden ser códigos), monedas, porcentajes ni espacios de miles.
   - Es una lectura sin pérdida: el original no cambia y el valor es el mismo; por eso no crea
     versión derivada ni aprobación. La decisión (`SourceReading`) se guarda en los metadatos del
     Parquet de la tabla (`dataflow:source_reading`): cada paso publica un solo artefacto.
3. **`ingestion.read_xlsx@2`**: como @1 más `regional-values-v1` **sin convención de archivo**
   (los números nativos de Excel ya son canónicos; sólo cambian los textos que lo prueban).
4. **`xlsx-selection-v2`**: la tabla principal es la de v1 y es la versión que devuelve la subida;
   hasta cuatro tablas más con al menos dos columnas con cabecera y dos registros se registran como
   **versiones propias de la misma carga** (mismo original, un solo objeto, misma transacción;
   idempotencia por clave derivada). No se cruzan tablas. La selección guarda `analyzed_together`.
   La cuota cuenta una vez un original compartido.
5. **`structure-comparison-v1`** (`ingestion/structure.py`, pura): compara el perfil con el de la
   versión importada anterior más reciente del mismo archivo (y de la misma hoja o tabla): columnas
   nuevas, quitadas y con otro tipo o papel. Sólo informa; no renombra ni empareja.
6. **API**: `GET /versions/{id}/reading` → `{reading, structure}` (409 `RESULT_NOT_READY` hasta que
   termine la carga). El informe (`delivery.report@1`) añade «Lectura del archivo» y «Cambios
   respecto de la versión N»; la revisión se fija en el plan del informe.
7. **Catálogo `analysis-v13`**: las cargas nuevas usan las lecturas @2; las anteriores conservan
   su plan, su lectura y su hash.

8. **SQL Server (18B)**, decisión del usuario: `pymssql` y **sin guardar credenciales**. Copia de
   un solo uso, cifrada, sólo a servidores de `DATAFLOW_SQLSERVER_ALLOWED_HOSTS`; la contraseña
   sólo existe en la petición y en el directorio temporal del subproceso. `sqlserver-selection-v1`
   elige hasta cinco tablas y cada una se copia completa o se omite; su CSV estándar es el
   original inmutable de una versión. Actualizar exige volver a conectar.
9. **PDF (18B)**, decisión del usuario: `pdfplumber`. `pdf-selection-v1` elige hasta cinco tablas
   con cabecera (las que siguen en otra página con la cabecera repetida se unen);
   `ingestion.read_pdf@1` las lee del PDF original con `regional-values-v1`. Sin OCR: un PDF
   escaneado se rechaza con su motivo.
10. **`source_origin`** en la versión y en la lectura: tabla de origen, lo analizado aparte y lo
    omitido, también en el informe.

## Consecuencias

- CSV de Excel en español se analizan sin pasos manuales; lo ambiguo se explica en vez de
  adivinarse.
- La tabla publicada muestra los valores canónicos (`1234.50`), no el texto original; el original
  sigue descargable byte a byte.
- Un libro con varias hojas de datos produce varias versiones, cada una con su análisis,
  investigación e informe.
- Dependencias nuevas: `pymssql` y `pdfplumber` (con `pdfminer.six`, `pypdfium2` y
  `cryptography`), importadas sólo en el subproceso de ingesta.
- Sin credenciales guardadas no hay actualización programada de una base: cada copia es una
  carga nueva y los cambios de estructura se comparan con la anterior.
- `DatasetProfile.encoding` sigue diciendo `utf-8-sig` (la tabla publicada); la codificación real
  del original está en la lectura.
