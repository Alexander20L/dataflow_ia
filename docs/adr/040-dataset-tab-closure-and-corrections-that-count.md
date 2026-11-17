# ADR-040 — Cierre de la pestaña Dataset: diagnóstico analítico y correcciones que cuentan

Estado: aceptado e implementado en la Fase 23 (API 0.30.0, migración 0023; el catálogo de carga
sigue en `analysis-v13`). Documentación: [Fase 23](../architecture/phase-23.md). **Modifica el
punto 7 de [ADR-039](039-dataset-tab-inspection-and-dictionary.md)**: las correcciones del
Diccionario ya no son sólo descriptivas. Se apoya en [ADR-026](026-fully-automatic-single-path.md)
(recorrido automático) y [ADR-036](036-business-comprehension-and-optional-feedback.md)
(comprensión y valoración opcional).

## Contexto

La revisión de la pestaña Dataset con un dataset real (200 estudiantes) mostró que:

- las cifras eran exactas, pero la subvista Calidad salía casi siempre vacía: sin rangos
  esperados no había nada que validar, y los atípicos sólo se miraban en las medidas con 3·IQR;
- «0 filas duplicadas» era engañoso cuando cada fila tiene un identificador propio;
- un ciclo académico (enteros del 1 al 10) se presentaba como una medida con media 5,38; una
  columna Sí/No, como nominal genérica; y el nombre de las personas, como «texto desconocido»;
- el Diccionario guardaba correcciones que ninguna otra etapa leía, y la pestaña Dataset y la
  comprensión clasificaban por separado (`ciclo` era «discreta» en una y «ratio» en la otra).

## Decisión

1. **`dataset-inspection-v2`** (reglas puras en `inspection/domain.py`, Polars sólo en
   `inspection/engine.py`, sin IA ni base de datos):
   - **Dominio evidente por el nombre de la columna.** Porcentajes (`pct`, `porcentaje`, `%`…):
     de 0 a 100. Cantidades que no deberían ser negativas (edad, cantidad, unidades, precio,
     horas, peso, asistencia…): desde 0. Un importe o un monto no se incluyen porque pueden ser
     negativos (devoluciones). Los valores fuera de dominio son un aviso de **validez** con
     ejemplos y filas.
   - **Atípicos con las vallas de Tukey** sobre las columnas cuantitativas (al menos 8 valores
     e IQR > 0), con los mismos cuartiles que se muestran (interpolación lineal): atípico fuera
     de 1,5·IQR y extremo fuera de 3·IQR. Es un aviso informativo; el hallazgo `AQ-007` de la
     calidad automática no se repite en esas columnas.
   - **Filas repetidas sin los identificadores.** Si hay columnas con rol identificador, también
     se cuentan las filas iguales a una anterior en todo lo demás, diciendo qué columnas se
     excluyeron. Sólo hay aviso si suman más que los duplicados exactos.
   - **Columnas dicotómicas:** exactamente dos valores distintos (salvo identificadores), con la
     proporción de cada uno.
   - **Escala ordinal candidata:** enteros con 3 a 12 valores distintos y un nombre de escala
     (ciclo, nivel, grado, semestre, prioridad, valoración…) o consecutivos de 0/1 a 3, 4, 5, 7
     o 10. **Es una candidata**: no cambia la clasificación hasta que el usuario la confirma.
   - **Datos personales:** por el nombre de la columna (nombre, apellido, correo, teléfono,
     documento, dirección), salvo que hable de un objeto («nombre_producto»), y, salvo nombres y
     direcciones, también por el formato de al menos el 80 % de los valores. Un correo se
     reconoce también sólo por sus valores. Un nombre o una dirección sólo se marcan si la
     columna es texto libre: un nombre que se repite y agrupa registros (`Customer_Name` en
     ventas) es una dimensión del negocio y el usuario puede marcarlo a mano.
   - Los textos de «sin dato» guardan sus **escrituras exactas** (`variants`, como «N/A» y
     «n/a») para poder declararlos con una coincidencia exacta.
2. **Las correcciones del Diccionario cuentan** (migración 0023, tabla
   `column_annotation_details`: textos nulos declarados y la decisión sobre datos personales,
   inmutable y sólo de añadir, una fila por corrección que lo necesite):
   - **Clasificación única.** La comprensión (`business-comprehension-v2`) parte de la misma
     clasificación que la pestaña Dataset: mismas reglas (`inspection.engine.classify_table`)
     sobre la misma tabla, con las correcciones encima. Una columna sin corregir conserva su
     rol analítico de siempre (sin regresiones); una corregida toma el rol del usuario; una
     escala que el usuario declara ordinal o nominal manda sobre las reglas de escala.
   - **Recálculo inmediato.** Una corrección que cambia la clasificación encola otra
     comprensión de la versión con una instantánea de las correcciones; al publicarse se rehacen
     la exploración y el dashboard, y este pide otra versión del informe. Lo anterior se
     conserva. Si la última comprensión ya usa esas correcciones, no se encola nada.
   - **Datos personales fuera de la IA.** Las columnas con datos personales se tratan como texto
     (no se agrupan ni se analizan) y no aparecen en el contexto de ninguna llamada a la IA. El
     usuario puede confirmar, descartar o marcar a mano.
   - **Textos declarados como nulos → versión derivada.** El usuario elige, entre los textos de
     «sin dato» que la inspección encontró, cuáles lo son. Se encola un trabajo `null_cleaning`
     sobre la tabla leída de la versión: sólo pasos `cleaning.normalize_null_tokens@1` con las
     escrituras exactas. Es una decisión del sistema sin aprobación aparte (como toda limpieza
     desde ADR-026): su efecto exacto (`effect_sha256`) y el linaje quedan registrados, no se
     pierden filas ni columnas, y el original y la versión de partida no cambian. La versión
     derivada se analiza como una carga nueva (perfil@4, calidad@3, análisis automático,
     inspección, comprensión, investigación, exploración, dashboard e informe) y conserva la
     identidad de la fuente, así que hereda las correcciones.
3. **Procedencia de una carga.** Los trabajos de fondo aceptan que la tabla de una versión
   derivada venga de `null_cleaning` y el resto de su análisis de `table_analysis` cuando la
   entrada fijada de ese análisis es exactamente esa tabla (`bootstrap/loads.py`).
4. **Interfaz.**
   - Columnas: avisos de dicotómica, escala candidata y datos personales; rango esperado y
     atípicos.
   - Calidad: las filas de ejemplo abren su página en Registros, resaltadas.
   - Resumen: filas repetidas sin identificador y columnas con datos personales.
   - Diccionario: decisión sobre datos personales, textos «sin dato» que pasan a nulos, acceso
     directo a la escala ordinal candidata, aviso del recálculo en curso y botón para abrir la
     versión derivada. Al terminar un recálculo, las demás pestañas vuelven a pedir sus
     resultados.

## Decisiones tomadas sin consulta

- Las versiones cargadas antes de la fase conservan su inspección v1 y su comprensión v1: no se
  recalculan en masa, y una corrección en ellas no encola otra comprensión.
- Vallas de Tukey estándar (1,5·IQR) en la pestaña Dataset; la calidad automática conserva su
  `AQ-007` (3·IQR) para el resto del recorrido.
- Los rangos esperados sólo salen del nombre de la columna; no se deducen de los valores (una
  nota de 0 a 20 no se puede afirmar sin conocer la escala).
- Sólo se declaran como nulos los textos que la inspección encontró; volver a enviar los ya
  aplicados en una versión derivada se acepta sin crear otra versión.
- Descartar o marcar datos personales cuenta como corrección (estado «Corrección manual»).
- Detectar columnas calculadas a partir de otras (por ejemplo, un promedio ponderado de notas)
  queda para la pestaña Comprensión.

## Consecuencias

- Una corrección puede encolar hasta cuatro trabajos (comprensión, exploración, dashboard e
  informe) y una declaración de nulos, el recorrido completo de una versión nueva.
- La comprensión vuelve a clasificar la tabla al calcularse (mismo coste que la inspección, sin
  IA).
- Un nuevo tipo de ejecución, `null_cleaning`, con su finalizador `DeclaredNullsFinalizer`.
