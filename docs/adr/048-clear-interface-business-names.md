# ADR-048 — Interfaz que se entiende sin leer: nombres de negocio, tarjetas y detalle plegado

Estado: aceptado e implementado en la Fase 30 (API 0.38.0, sin migración). Documentación:
[Fase 30](../architecture/phase-30.md). Modifica la presentación de ADR-041, ADR-043 y
[ADR-047](047-analysis-target-factors-and-significance.md); los cálculos no cambian.

## Contexto

Las pestañas explicaban cada resultado con frases técnicas: «La tasa de la categoría menos
frecuente en «activo»», un selector con nombres de columna, un plan de investigación en una tabla
de nueve columnas y una narrativa con códigos de evidencia intercalados («347,745 [d988a123cadf]»).
Quien abre el análisis tenía que leerlo todo para saber qué se estaba explicando.

## Decisión

1. **Nombres de negocio** (prompt de comprensión v5): la IA propone el tema del archivo (hasta 3
   palabras), el nombre del objetivo (hasta 4) y un nombre corto por columna (hasta 3). Python los
   valida como el resto de sus textos: sin cifras propias, con pocas palabras y sobre columnas que
   existen; lo que no cumple se retira con motivo. Sin IA no hay nombres y la interfaz usa el de
   la columna.
2. **Categoría contada** (`business-comprehension-v6`): el objetivo de tipo tasa publica
   `counted`, la categoría pedida o, si no hay, la menos frecuente (en empate, la primera en orden
   alfabético), con la misma regla que la investigación. El objetivo publica también `label`: el
   nombre de la IA si el objetivo es el suyo; si no, el nombre corto de la columna.
3. **Comprensión › Resumen**: el objetivo en una tarjeta con icono, nombre y medida («% de
   registros con activo = No»); las variables que lo explican como etiquetas; el cambio de
   objetivo con un clic en tarjetas con icono y tipo (% o promedio); lo básico en cifras grandes
   (cada fila, tema, periodo); las preguntas en una lista corta; y el resto (grano, motivo del
   objetivo, dominio, fórmulas, fechas, método y reglas) plegado en «Ver detalle técnico».
4. **Iconos por reglas** sobre el nombre y el papel de la columna (dinero, horas, ausencias,
   valoraciones, existencias, fechas, bajas), con `lucide-react`, que ya estaba.
5. **Investigación**: el plan es una lista de tarjetas (pregunta, clase, origen y prioridad) con
   el detalle plegado; los textos de las reglas se leen con la categoría contada («el % de activo
   = No» en vez de «la tasa de la categoría menos frecuente en activo»), sólo en pantalla.
6. **Informe, Dashboard y Dataset**: la evidencia de cada cifra de la narrativa es una marca
   discreta con su código al pasar el ratón (el PDF la conserva escrita); los datos técnicos de la
   cabecera del informe y la explicación del diseño del dashboard quedan plegados.

## Decisiones tomadas sin consulta

- Los análisis no cambian: sólo su presentación y tres campos nuevos (`theme`, `labels`, y
  `label`/`counted` del objetivo).
- Las versiones analizadas antes se ven con el diseño nuevo, sin nombres de negocio hasta volver a
  cargar el archivo.
- La sustitución de «la categoría menos frecuente» se hace en la interfaz: las consultas y sus
  claves no cambian.
- Un clic en una tarjeta cambia el objetivo (sin botón de confirmar); «Volver al sugerido» lo
  deshace.

## Consecuencias

- El resumen se entiende de un vistazo; el detalle sigue a un clic.
- El prompt de comprensión sube a v5 y cada respuesta trae unos pocos campos más.
