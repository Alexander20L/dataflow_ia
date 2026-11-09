# ADR-031 — Interpretación analítica y calidad con análisis afectados

Estado: aceptado e implementado en la Fase 14 (API 0.21.0, catálogo `analysis-v11`, sin migración).
Documentación: [Fase 14](../architecture/phase-14.md). Se apoya en
[ADR-024](024-automatic-descriptive-overview.md), [ADR-025](025-automatic-descriptive-interpretation.md)
y [ADR-026](026-fully-automatic-single-path.md).

## Contexto

El dashboard descriptivo elegía estadísticas por posición de columna (promediaba `Year`), ordenaba
los meses por frecuencia, llamaba «registros» a todo y la calidad sólo contaba vacíos. Faltaba criterio
analítico: qué es tiempo, qué se puede sumar, qué identifica una fila y qué problemas cambian las
conclusiones.

## Decisión

1. **`understanding.profile@4`** con `automatic-interpretation-v2`, pura y por reglas: papeles
   (identificador, dimensión, medida, tiempo, texto, vacía) con evidencia; tiempo compuesto
   `Year` + `Month` (número o nombre en español o inglés), nunca medida; aditividad
   (`additive`, `semi_additive`, `non_additive`, `unknown`), moneda y unidad como conocidas,
   desconocidas o ambiguas (nunca inventadas); claves candidatas comprobadas sobre todas las filas;
   relaciones `A ≈ B × C` con tolerancia explícita (0,5 %, mínimo 0,01); dependencias
   código → atributo con sus conflictos; análisis posibles y **limitados** con su motivo.
2. **`automatic-overview-v3`**: suma sólo medidas aditivas con moneda no ambigua (importes antes que
   cantidades), promedio simple sin ponderar para el resto, meses en orden cronológico sin rellenar
   huecos, comparación por año, gráficos por dimensión con la suma exacta (`amount`) y omisión de las
   dimensiones con identidades contradictorias. La calidad no se mezcla con los resultados.
3. **`quality.evaluate@3`** (`automatic-quality-v1`): juzga la evidencia de la interpretación y mide
   valores imposibles y atípicos (AQ-001 a AQ-008) con severidad `info`, `warning` o `blocking` y los
   **análisis afectados**. `blocking` limita sólo esos análisis. Nada se corrige.
4. **El periodo se deriva en el perfil**, no en una tabla: no hay versión derivada, aprobación ni
   migración (D3). La columna derivada para `analytics` queda para la Fase 15.
5. **Compatibilidad**: `profile@1–@3` y `quality.evaluate@1` conservan su serialización exacta
   (`profile_json`, `QualityReport.serialized`); los planes guardados conservan su catálogo. Las
   cargas nuevas usan `analysis-v11`; las tablas derivadas siguen con `profile@1`/`quality@1`.
6. `quality` importa `understanding.contracts` (dependencia nueva y acíclica). Sin IA (D1): la
   explicación C2 recibe las sumas como cifras con evidencia, con el mismo prompt.

## Consecuencias

- Con el dataset de aceptación: contexto comercial, periodo mensual 2023-01 a 2024-12 con 2024-07
  faltante, `Year` no se promedia, Revenue = Units × Price comprobado, moneda desconocida y análisis
  de clientes limitados sin afectar a productos.
- Más contratos en OpenAPI (cambios aditivos): `AutomaticOverview.analysis`, `OverviewChart.measure`,
  `OverviewPoint.amount` y `QualityReport.analytical`.
- Las reglas dependen de nombres en español e inglés; un nombre sin pistas no se suma (se abstiene).

## Alternativas descartadas

- Propuestas de la IA para interpretar: aplazadas a la Fase 16 (D1).
- Guardar los hallazgos dentro del perfil: mezcla calidad con resultados y rompe el reparto entre
  `understanding` y `quality`.
- Derivar el periodo como versión limpia: exige aprobación o decisión del sistema y una migración
  sin necesidad en esta fase.
