# ADR-039 — Pestaña Dataset: inspección completa, registros paginados y diccionario corregible

Estado: aceptado e implementado en la Fase 22 (API 0.29.0, migración 0022; el catálogo de carga
sigue en `analysis-v13`). Documentación: [Fase 22](../architecture/phase-22.md). Se apoya en
[ADR-026](026-fully-automatic-single-path.md) (recorrido automático), [ADR-035](035-regional-sources-tables-and-structure.md)
(lectura regional) y [ADR-036](036-business-comprehension-and-optional-feedback.md) (valoración
opcional del usuario).

> **Vigencia:** el punto 7 lo modifica [ADR-040](040-dataset-tab-closure-and-corrections-that-count.md)
> (Fase 23): desde entonces las correcciones del Diccionario se usan en la comprensión y lo que
> depende de ella, y los textos declarados como nulos crean una versión derivada.

## Contexto

La interfaz era una sola página larga con los resultados automáticos. Hacía falta una primera
pestaña, **Dataset**, para inspeccionar, perfilar y diagnosticar el archivo. Tiene seis
subvistas: Resumen, Registros, Columnas, Diccionario, Calidad y Archivo. Todo sale del dataset
completo y nada modifica el original. Además, el usuario debe poder corregir la clasificación de
una columna sin que una nueva ejecución la pise en silencio.

## Decisión

1. **Trabajo de fondo `inspection`** (operación interna `inspection.inspect@1`, reglas
   `dataset-inspection-v1`).
   - Se encola al publicarse cada carga y es el primero de los trabajos de fondo.
   - Fija la tabla leída, el perfil y la calidad de esa carga.
   - Se calcula una vez sobre todos los registros y se guarda como artefacto `inspection`.
   - Cambiar de subvista no recalcula nada.
   - No toca `profile@4`, la calidad, el dashboard ni el informe.
2. **Tipo técnico frente a naturaleza estadística.**
   - **Tipo técnico:** cómo están escritos los valores. Usa las mismas reglas que `profile@4`
     más fecha y hora ISO. Basta un valor que no encaje para que la columna quede como texto.
   - **Naturaleza estadística:** nominal, ordinal, discreta, continua, temporal o desconocida.
     Sale del tipo, del rol de la interpretación automática y de su parte temporal. Por ejemplo,
     un `Year` entero es temporal.
   - La naturaleza ordinal nunca se supone: sólo la indica el usuario.
   - Las estadísticas se calculan sólo cuando tienen sentido:
     - Numéricas para las cuantitativas.
     - Rango, frecuencia y periodos faltantes para las temporales.
     - Frecuencias para las categóricas.
3. **Faltantes por clase, sin convertir nada.** Se cuentan por separado:
   - nulos (una celda vacía se lee como nula);
   - texto en blanco;
   - textos del tipo «N/A», «-» o «NULL».

   Tipos mixtos, ceros iniciales, fechas ambiguas y fechas inválidas se diagnostican con
   ejemplos y filas, sin elegir una interpretación.

4. **Calidad por dimensiones** (completitud, unicidad, validez, consistencia, formato,
   integridad).
   - Une las reglas de la inspección con los hallazgos `automatic-quality-v1` ya calculados.
   - Cada incidencia lleva columnas, registros afectados, porcentaje, ejemplos, filas y
     gravedad.
   - No se elimina, corrige ni descarta nada; un valor extremo no se considera un error.
5. **Datos del original** (`source-facts-v1`): se calculan en el subproceso de ingesta, el único
   que abre el original con sus lectores.
   - CSV: líneas en blanco omitidas.
   - Excel: hojas, rango leído, filas y columnas vacías dentro del rango, celdas con fórmula
     (se lee su resultado guardado) y celdas con formato de fecha.

   Cada hoja con datos sigue siendo una versión propia y las hojas nunca se combinan.

6. **Registros** (`GET /versions/{id}/preview`, ampliado de forma aditiva).
   - Orden por el **identificador** de columna: nunca por un nombre o una expresión de la
     petición.
   - El orden es numérico si todos los valores son números; si no, de texto. Los nulos van al
     final.
   - Búsqueda literal sin distinguir mayúsculas.
   - Como mucho 100 filas por página.
   - Sin filtro, orden ni búsqueda sólo se materializa la página pedida.
   - La ruta responde con `RecordsPage`: los mismos campos de `PreviewPage` más `column_ids`,
     `sort`, `descending` y `search`.
   - `PreviewPage` no cambia: las referencias golden de las tablas de texto siguen idénticas.
     Como ninguna ruta lo devuelve ya, deja de aparecer en el contrato OpenAPI.
7. **Diccionario con correcciones opcionales**, en la tabla `column_annotations` (migración 0022):
   - Es inmutable y sólo de añadir.
   - Se guarda por fuente (archivo y hoja/tabla, la misma clave que la comprensión) y por
     nombre de columna. Vale la última corrección y la heredan las versiones siguientes del
     mismo archivo.
   - Cada entrada distingue _automática_, _corrección manual_ y _confirmada_, con su
     procedencia.
   - Una corrección vacía devuelve la columna a la automática.
   - Se rechazan las combinaciones sin sentido: una medida no cuantitativa, una columna
     cuantitativa sin números o una interpretación temporal en una columna no temporal.
   - Las correcciones **no cambian** el archivo, la inspección ni ningún análisis de esta fase.
     Sólo cambian cómo se describe la columna y la distribución por clasificación.
8. **Navegación**: dos pestañas principales.
   - «Dataset», la primera y la que se abre por defecto.
   - «Análisis», con todo lo anterior sin cambios.

   Comprensión, Investigación, Dashboard e Informe se separarán en su fase.

9. **Separador con líneas en blanco** (`detect_separator`).
   - Primero se usa la detección de siempre.
   - Sólo si su resultado no da registros del mismo ancho, se vuelve a detectar sin las líneas
     en blanco, y ese resultado se usa únicamente si sí es coherente.
   - Así un CSV con `;` y una línea vacía entre registros ya no falla con `CSV_SHAPE`.
   - Los archivos que ya se leían bien no cambian (las golden lo comprueban). El plan de las
     cargas anteriores conserva su separador.

## Decisiones tomadas sin consulta

- La inspección es un trabajo de fondo, no un cálculo síncrono en la API, para no bloquearla.
- Las versiones anteriores a la fase responden `unavailable` y piden volver a subir el archivo;
  no se rellenan con datos inventados.
- No hay nivel de confianza: no existe un método justificable. Se muestra la procedencia y la
  evidencia de cada clasificación.
- **Categorías:**
  - El rol «Categoría» sólo lo asigna el usuario; la regla automática usa «Dimensión».
  - Las identificaciones no muestran frecuencias, sólo repetidos.
  - El texto libre tiene naturaleza desconocida.
- **Cálculo:**
  - Porcentajes con dos decimales y redondeo _half-up_ sobre todos los registros.
  - Cuartiles por interpolación lineal y desviación muestral.
  - Histograma de Sturges con 20 intervalos como máximo, o la frecuencia de cada valor si son
    enteros con pocos valores distintos.
- La memoria es la estimación de Polars para la tabla leída.
- `.xls` sigue sin admitirse: haría falta una dependencia nueva.
- SQL Server y PDF no se tocan en esta fase.

## Consecuencias

- Una ejecución más por carga (rápida, sin IA). Las pruebas que cuentan trabajos en cola se
  actualizaron.
- Las pruebas E2E abren la pestaña «Análisis» antes de comprobar los resultados automáticos.
- La interfaz muestra los valores tal como se leyeron. Las columnas que convirtió la lectura
  regional aparecen en su celda canónica; el original se descarga sin cambios.
