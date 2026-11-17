# ADR-042 — Mejoras de la pestaña Comprensión y cifras con tres decimales en pantalla

Estado: aceptado e implementado en la Fase 24B (API 0.32.0, migración 0025; el catálogo de carga
sigue en `analysis-v13`). Documentación: [Fase 24B](../architecture/phase-24b.md). Completa
[ADR-041](041-comprehension-tab-grain-formulas-and-validations.md).

## Contexto

Revisando la Fase 24 frente a la especificación de la pestaña Comprensión quedaban cuatro huecos:

- el significado que escribía el usuario se veía en la pestaña, pero el informe seguía
  describiendo la columna con el de la IA (no se usaba en las etapas posteriores);
- la vista Columnas no mostraba el tipo técnico ni la naturaleza estadística (ya calculados en la
  pestaña Dataset), y un significado de la IA no decía en qué se basaba;
- no se podía marcar una columna como desconocida, sólo escribir o confirmar;
- el rol sólo se podía cambiar en el Diccionario, sin un camino desde Comprensión.

Además, todas las presentaciones mostraban las cifras con todos sus decimales (por ejemplo,
`0,8123456789`), lo que las hacía difíciles de leer.

## Decisión

1. **El significado vigente llega al informe.** El informe aplica, al generarse, los
   significados del usuario de la misma fuente (escritos, confirmados o marcados como
   desconocidos) sobre los de la IA, y lo deja registrado con `meanings_sha256` en su origen. La
   columna dice su procedencia («(usuario)»). Guardar un significado pide otra versión del
   informe (la anterior se conserva); no se rehace la comprensión, la exploración ni el
   dashboard, porque un significado no cambia ningún cálculo.
2. **Columna desconocida** (migración 0025, tabla nueva `column_meaning_marks`, inmutable y sólo
   de añadir, una fila por significado marcado; no se añaden columnas a `column_meanings`). La
   marca se hereda como el resto de significados, no admite texto ni confirmación (422
   `MEANING_INVALID`) y se quita guardando un significado vacío, sin confirmar y sin marcar.
3. **Justificación de la IA** (prompt de comprensión v3): una frase corta por significado (el
   nombre, los valores frecuentes o el rango). Pasa los mismos filtros que el resto de textos de
   la IA: si trae cifras que no salen de los datos se retira con su motivo.
4. **Columnas con tipo técnico y naturaleza** de la inspección vigente (con las correcciones del
   Diccionario); la pestaña Comprensión no los recalcula. Un botón abre el Diccionario de la
   pestaña Dataset para cambiar el rol.
5. **Tres decimales como mucho en lo que se muestra** (`display-decimals-v1`), en la interfaz y
   en el PDF:
   - una cifra con cuatro o más decimales se redondea a tres, mitad lejos de cero;
   - si se redondeó, se quitan los ceros finales que deja el redondeo (1,29999 → 1,3);
   - una cifra con tres decimales o menos se deja igual (12,50 sigue siendo 12,50);
   - **sólo cambia la lectura**: las cifras canónicas, sus evidencias, los artefactos, la API y
     las descargas conservan todos sus decimales.

## Decisiones tomadas sin consulta

- Los valores de la subvista Registros (las celdas del propio archivo) no se redondean: son
  datos, no resultados. Tampoco los identificadores, conteos, fechas ni lo que escribe el
  usuario.
- En el PDF la regla se aplica al dibujar cada texto y las etiquetas del eje de los gráficos
  (`delivery/numbers.py`, sin ReportLab), así que ningún bloque puede escaparse de ella.
- Las versiones cargadas antes de la fase conservan sus significados de la IA sin justificación.

## Consecuencias

- Guardar un significado encola, como mucho, una versión nueva del informe.
- El texto del informe ya no dice «Significado (IA)», sino «Significado» con su procedencia.
