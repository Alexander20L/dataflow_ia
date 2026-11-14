# ADR-047 — Analista con objetivo: objetivo, factores con significancia, control e IA obligatoria

Estado: aceptado e implementado en la Fase 29 (API 0.37.0, migración 0028; el catálogo de carga
sigue en `analysis-v13` y `profile@4` no cambia). Documentación: [Fase 29](../architecture/phase-29.md).
Modifica [ADR-046](046-analytic-criteria-date-role-and-rates.md) (la IA puede proponer tasas y
cohortes; `relevance-v3` sustituye a `relevance-v2` en las cargas nuevas) y
[ADR-041](041-comprehension-tab-grain-formulas-and-validations.md) (comprensión v5).

## Contexto

Tras la Fase 28 el análisis ya no cometía los errores más visibles, pero seguía sin el juicio de un
analista:

- cruzaba medidas y dimensiones de forma general, sin preguntarse qué importa (las bajas, las
  ventas…) ni qué lo explica;
- clasificaba por magnitud con un mínimo fijo de registros, sin saber si una diferencia es real o
  ruido (25 % frente a 5 % con 20 personas por grupo da p ≈ 0,099), y una investigación de veinte
  pruebas casi siempre encuentra algo «interesante» por azar;
- no comprobaba otras explicaciones: un área con más bajas puede tenerlas sólo porque tiene más
  gente nueva;
- usaba la fecha de ingreso tal cual, cuando un analista calcula la antigüedad;
- y la IA, cuando faltaba la clave, se apagaba en silencio.

## Decisión

1. **Objetivo del análisis** (`business-comprehension-v5`, `AnalysisTarget`): una columna de dos
   valores (se analiza su tasa) o una medida (su promedio). Prioridad: el elegido por el usuario
   (si sigue siendo válido), el propuesto por la IA (prompt `business-comprehension` v4, validado),
   y por reglas una columna de dos valores con nombre de resultado (activo, baja, aprobado,
   abandono…) o, si no la hay, la medida principal (monetaria, aditiva; también una calculada como
   ingresos = unidades × precio). Se publican los candidatos.
2. **Elección del usuario** (`analysis_targets`, migración 0028): metadato de la fuente, inmutable y
   sólo de añadir; vale el último y lo heredan las cargas siguientes. `POST
/versions/{id}/comprehension/target` encola otra comprensión y tras ella investigación,
   dashboard e informe. Nunca bloquea; sin columna vuelve al propuesto.
3. **Variables derivadas** (`DerivedVariable`): «antigüedad de X» (tramos de menos de 1, 1 a 3,
   3 a 5 y 5 o más años hasta la fecha más reciente de X, para que el resultado no cambie con el
   tiempo) a partir de una fecha que describe al registro, y «cuartil de X» de hasta dos medidas
   (no del objetivo ni de las columnas de su fórmula). La IA puede proponer otras de esos dos tipos.
   El motor las resuelve por su nombre.
4. **Factores** (`explore-v4`, `exploration.explore@4`, `investigation-v4`): `factor` calcula el
   objetivo en cada grupo de una dimensión o variable derivada con intervalo al 95 % (Wilson para
   tasas, t para promedios) y una prueba de que los grupos difieren sobre los grupos con al menos
   10 registros (chi-cuadrado con V de Cramér; Kruskal-Wallis con épsilon cuadrado). El plan
   empieza por la tasa del objetivo y hasta seis factores.
5. **Significancia** (`relevance-v3`): un factor es hallazgo sólo con magnitud (≥ 10 puntos en una
   tasa, ≥ 30 % de diferencia relativa en un promedio para «relevante»; 5 puntos o 10 % para
   «secundario») **y** p < 0,05. Al terminar la investigación los valores p de todas las pruebas
   se corrigen por Benjamini-Hochberg (valor q) y lo que deja de ser significativo pasa a «no
   concluyente», con su texto.
6. **Control de otras explicaciones**: un factor interesante se comprueba con hasta dos variables
   (primero las derivadas). `stratified` compara, para cada grupo, lo observado con lo esperado
   sólo por su composición en la variable de control (estandarización indirecta, que funciona con
   combinaciones de pocos registros). Veredicto por la diferencia residual frente a la observada:
   «se mantiene» (≥ 2/3), «se atenúa» (≥ 1/3) o «se explica por X». Se anota en el factor y, si se
   explica, el factor baja un nivel. Una comprobación de un factor que no resultó significativo se
   muestra como descripción.
7. **La IA como analista**: con objetivo, el catálogo que se ofrece a la IA incluye `factor`,
   `stratified`, `rate` y `cohort` (prompt `exploration-proposal` v3, con el objetivo en el
   contexto). Sigue sin calcular: propone, Python valida y el motor calcula.
8. **IA siempre visible**: el estado de la IA con su motivo (ya guardado en `ai_reason`) se muestra
   en un aviso en todas las pestañas. `DATAFLOW_AI_REQUIRED=true` impide arrancar la API y el
   worker sin IA activa (por defecto `false`, para que `docker compose up` funcione sin clave).
9. **Dashboard e informe**: factores y comprobaciones se dibujan en barras (la primera cifra es la
   tasa o el promedio) y el informe los usa en sus conclusiones, con recomendaciones sin
   causalidad.

## Decisiones tomadas sin consulta

- Estadística en Python puro (funciones gamma y beta incompletas regularizadas), sin scipy.
- Umbrales: α = 0,05 sobre el valor q; 10 registros por grupo en las pruebas; 2/3 y 1/3 para el
  veredicto de control; hasta 6 factores y 2 comprobaciones por factor.
- La antigüedad se mide hasta la fecha más reciente de la columna, no hasta hoy.
- La IA puede proponer el objetivo, pero el del usuario manda; el de la IA manda sobre el de
  reglas.
- `DATAFLOW_AI_REQUIRED` es opcional y está desactivado por defecto.

## Consecuencias

- Con pocos registros por grupo muchas diferencias pasan a «no concluyente»: es lo correcto, y el
  texto dice por qué (valor p o q).
- Las cargas nuevas dan menos hallazgos pero más fiables, y cada uno dice si resiste otra
  explicación.
- Las versiones analizadas antes se siguen leyendo con sus reglas; para aplicar las nuevas hay que
  volver a cargar el archivo.
