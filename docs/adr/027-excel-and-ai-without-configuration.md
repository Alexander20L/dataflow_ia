# ADR-027 — Excel e IA sin configuración

Estado: aceptado e implementado en la Fase 13B (API 0.19.0, sin migración). Completa ADR-026.

## Contexto

Tras la Fase 13 quedaban dos pasos que pedían algo a una persona o que no ocurrían sin ella:

- **Excel**: `uploadXlsx` exigía `sheet`, el espacio de trabajo pedía elegir hoja o tabla y fila
  de cabecera tras una vista previa, y el asistente `/new` sólo aceptaba CSV. El CSV también
  ofrecía elegir el separador (por defecto, detección automática).
- **IA**: `DATAFLOW_AI_PROVIDER=disabled` por defecto; aunque hubiera una clave, nadie veía la
  explicación hasta cambiar la configuración.

## Decisión

1. **Regla `xlsx-selection-v1`** (en `integrations/sources/xlsx_reader.py`, `Workbook.automatic`),
   determinista: sólo hojas visibles (todas si todas están ocultas); si hay tablas con nombre con
   cabecera, la de mayor área (registros × columnas); si no, la hoja con más celdas con valor
   (las ilegibles o protegidas van detrás, para que su error se explique si son la única);
   cabecera = primera fila con el máximo de celdas con valor entre las primeras 50 filas con
   datos (salta títulos de una celda). Empates: orden del libro.
2. **Se importa una sola hoja o tabla** (la principal) y se informa lo que quedó fuera; no se
   crean varias versiones por libro. Para analizar otra hoja, se guarda como libro aparte.
3. La regla se aplica **al recibir el archivo** (en el subproceso de ingesta, como la vista
   previa) y el resultado se fija como parámetros explícitos de `ingestion.read_xlsx@1`, que **no
   cambia** (ni el catálogo `analysis-v10`). La decisión queda en el plan inmutable
   (`source_selection`) y se expone en `VersionResponse.source_selection`.
4. Un libro que no se puede abrir (no es `.xlsx`, macros, binario, dañado) se **rechaza al
   subirlo** (422 con código); un problema de la hoja elegida (celdas combinadas, cabecera
   inválida…) se registra y **falla en el worker conservando el original**, igual que un CSV.
5. La API conserva la elección explícita (`sheet`, `table`, `header_row`) por compatibilidad;
   `table` sin `sheet` es `XLSX_SHEET_REQUIRED`. La interfaz ya no la ofrece, ni el separador
   del CSV (siempre `auto`).
6. **`DATAFLOW_AI_PROVIDER=auto` por defecto**: Anthropic si hay clave (`DATAFLOW_AI_API_KEY` o
   el secreto), si no desactivada. `disabled`, `fake` y `anthropic` siguen disponibles. Pytest
   fuerza `disabled` cuando no se indica otro, para no llamar nunca a la IA real.

## Consecuencias

- Un `.xlsx` se analiza con cero clics desde `/new` o el espacio de trabajo, y la versión explica
  qué hoja se usó, con qué cabecera y qué quedó fuera.
- Si la cabecera real tiene menos celdas que las filas de datos, la regla puede elegir mal; la
  lectura falla entonces con un código explicado (`XLSX_SHAPE`, `XLSX_HEADERS`…), nunca importa
  en silencio una forma dudosa.
- Quien actualice desde 0.18 con una clave ya presente en el entorno verá activarse la
  explicación (costo); `disabled` la mantiene apagada.
