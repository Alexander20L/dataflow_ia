# ADR-030 — Importación de libros Excel (.xlsx)

Estado: aceptado e implementado en la Fase 12A (API 0.14, catálogo `analysis-v8`); registrado
retroactivamente. La elección de hoja pasó a ser automática en la Fase 13B
([ADR-027](027-excel-and-ai-without-configuration.md)). Documentación: [Fase 12](../architecture/phase-12.md).

## Contexto

Excel es la fuente más habitual después del CSV. Había que leerlo con las mismas garantías
(original inmutable, plan versionado, hash de entorno, errores con código) sin que una biblioteca
decida en silencio cómo interpretar fórmulas, fechas, celdas combinadas o libros que se expanden
al descomprimirse.

## Decisión

1. **Lector propio** `integrations/sources/xlsx_reader.py` (`xlsx-reader-1`): lee el paquete OOXML
   con la biblioteca estándar (zip y XML en flujo), **sin dependencias nuevas**. Se ejecuta sólo en
   el subproceso aislado de ingesta (prueba AST) y su código entra en el hash de entorno.
2. **Operación versionada** `ingestion.read_xlsx@1` con parámetros explícitos
   `{sheet, table, header_row, reader, formulas: "stored_result", empty_cells: "null"}`; después,
   el mismo perfil y calidad que el CSV.
3. **Semántica de lectura**: fórmulas por su resultado guardado (sin él, error); fechas por su
   formato numérico; tablas con nombre por su rango exacto sin la fila de totales; cabeceras vacías
   o duplicadas son error, como en el CSV.
4. **Rechazos explícitos**: `.xls`, `.xlsm`, `.xlsb` y libros cifrados (`UNSUPPORTED_FORMAT`);
   celdas combinadas (`XLSX_MERGED_CELLS`) y hojas protegidas (`XLSX_PROTECTED`); cualquier `DOCTYPE`.
   Ninguna lectura dudosa se corrige en silencio.
5. **Límites**: 5 MB subidos; 64 MB por parte y 160 MB por libro descomprimidos; celdas con datos
   acotadas por filas y columnas del plan (`XLSX_EXPANDED_LIMIT`).

## Consecuencias

- Un `.xlsx` con el mismo contenido que un CSV produce la misma tabla y las mismas cifras (prueba de
  cierre con `examples/ventas.xlsx`).
- Libros con celdas combinadas o macros no se importan; la persona debe guardarlos como `.xlsx`
  simple. Se registran como versión fallida conservando el original.
- Se importa una tabla por carga (la principal desde la Fase 13B).

## Alternativas descartadas

- `fastexcel`: no expone con precisión fórmulas sin resultado, formatos de
  fecha, celdas combinadas y protección, y añade una dependencia.
- Convertir el libro a CSV antes de leerlo: pierde tipos y procedencia.
