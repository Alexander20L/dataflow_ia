# ADR-037 — Exploración guiada: consultas propuestas por la IA y calculadas por el motor

Estado: aceptado e implementado en la Fase 20 (API 0.27.0, sin migración; el catálogo de carga
sigue en `analysis-v13`). Documentación: [Fase 20](../architecture/phase-20.md). Se apoya en
[ADR-033](033-bounded-investigation-and-ai-proposals.md) (la IA propone, Python valida, el motor
calcula) y [ADR-036](036-business-comprehension-and-optional-feedback.md) (comprensión y
valoración opcional).

## Contexto

La investigación de la Fase 16 sólo admite tres seguimientos fijos de los hallazgos. Por eso la IA
«sugería poco»: el problema no era la regla de no inventar cifras, sino lo estrecho del catálogo.
La conversación con el profesor propone que la IA, a partir de la estructura, proponga consultas
que un agente ejecute con un límite y que después juzgue su relevancia.

## Decisión

1. **Módulo `exploration`** y trabajo de fondo `exploration` (operación interna
   `exploration.explore@1`), encolado al publicarse la comprensión. Fija la comprensión, el perfil
   (aditividad) y la tabla.
2. **Lenguaje de consultas cerrado `explore-v1`**: `aggregate` (suma, promedio, mediana o conteo
   por una o dos dimensiones), `crosstab`, `ratio` (cociente de sumas), `top` (hasta 20 grupos) y
   `correlation_by_group` (Spearman dentro de cada grupo), con un filtro opcional por el valor de
   otra dimensión. Sólo se suman medidas aditivas y sólo se agrupa por dimensiones nominales u
   ordinales (escalas de la Fase 19).
3. **Propuestas**: primero las reglas (una consulta por relación confirmada de la comprensión,
   hasta 8); después la IA (`copilot/exploration.py`, prompt `exploration-proposal` v1), con la
   estructura, las relaciones confirmadas y las preguntas de negocio, hasta 12. Python valida cada
   una y explica cada rechazo. Hasta 20 consultas en total.
4. **Cálculo sobre todas las filas** (`exploration/engine.py`): sumas, conteos y medianas exactos
   (Decimal); promedios y cocientes con 6 decimales y correlaciones con 4, declarados en el
   método. Cada cifra tiene `evidence_id`. Se guardan hasta 500 grupos por resultado.
5. **El límite de 100 del profesor se aplica a lo que ve la IA, no a los datos**: la IA juzga la
   relevancia (prompt `exploration-relevance` v1) con hasta 100 filas de cada resultado. Su motivo
   no puede tener cifras propias (sólo nombres de columnas y grupos del resultado). Sin IA, los
   resultados de reglas se consideran relevantes por partir de una relación confirmada.
6. **Valoración del usuario**: las relaciones marcadas «No relevante» en la comprensión no se
   exploran (ni por reglas ni por la IA) y se listan como excluidas.
7. **API**: `GET /versions/{id}/exploration`. El progreso añade la etapa «Exploración guiada» y el
   informe una sección con los resultados relevantes (la exploración terminada cuando se genera el
   informe; su hash queda en la procedencia del documento).

## Consecuencias

- Cada carga hace hasta dos llamadas más a la IA (proponer y juzgar), con presupuesto y registro.
- La IA sigue sin producir cifras: propone y juzga; el motor calcula.
- La investigación de la Fase 16 no cambia; ambas conviven (seguimientos de hallazgos y
  exploración del negocio).
- La validación «sí va / no va» de hallazgos y el dashboard adaptado son la Fase 21.
