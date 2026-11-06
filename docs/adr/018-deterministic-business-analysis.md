# ADR-018 — Análisis de negocio determinista con métricas definidas y evidencia por cifra

Estado: implementado en Fase 7A / API 0.10. Documentación: [Fase 7](../architecture/phase-7.md). Desarrolla la sección de determinismo de la [arquitectura](../architecture/architecture.md) y el requisito semántico de la [Fase 4](014-planning-catalog.md).

## Contexto

Hasta 0.9 el producto diagnostica, limpia y convierte datos, pero no responde preguntas de negocio sobre ellos; la etapa de análisis era sólo una demostración con un KPI fijo. Responder «importe total por región y mes» exige que la cifra sea exacta, reproducible y trazable, y que nadie —ni el sistema ni, más adelante, una IA— decida por su cuenta que una suma son «ingresos».

## Decisión

- **Módulo analytics** con las mismas capas y reglas: acceso entre módulos por `public`/`contracts`; planning y executions no lo importan; su cómputo (contratos, dominio, motor y procesador) no accede a la base de datos (pruebas AST).
- **Métricas definidas por el usuario** como revisiones inmutables: columna medida, agregación, filtros estructurados, fecha de negocio opcional y política de nulos `exclude`. El nombre de negocio es una etiqueta. Una familia por métrica, anclada a su tabla base (columnas por ID, aplicable a derivadas compatibles), igual que las reglas de calidad (ADR-017).
- **Requisito semántico positivo**: las agregaciones medidas exigen una columna numérica confirmada como `measure`; agrupar o filtrar por tiempo exige una fecha confirmada como `business_date`; las métricas medidas de una consulta comparten moneda o unidad, que salen de la revisión semántica fijada (no se repiten en la métrica). Los conteos no tienen requisitos de rol ni de unidad (D4, D5). Planning lo valida mediante un puerto, sin importar analytics.
- **Consulta estructurada `analytics.query@1`**: métricas por referencia exacta, dimensiones, filtros, granularidad, periodo, `avg_scale` y `max_result_rows`, todos explícitos en el plan. Se ejecuta como plan normal (sólo lectura): sin vista previa ni aprobación. No hay expresiones ni SQL del usuario.
- **D1 · Motor**: Polars lee la tabla y la agregación se hace en Python con `int` y `Decimal` exactos. Se descartó DuckDB por ahora: añade una dependencia binaria y un segundo motor con otra semántica numérica (su media de decimales también es `DOUBLE`), sin necesidad con el límite de 100.000 filas. El motor queda encapsulado en `analytics/engine.py`.
- **D6 · Nulos**: excluidos y contados por métrica; un nulo en una dimensión forma el grupo «(sin valor)». **D7**: `avg` con `avg_scale` (por defecto 4) y HALF_EVEN. **D8**: semanas ISO 8601 y periodos por fecha de negocio; las zonas horarias quedan fuera (no hay columnas de instante). **D10**: presupuesto de filas y tiempo con errores explícitos.
- **D9 · Evidencia**: artefacto `analysis_result` con definiciones, conteos y un `evidence_id` por cifra, hash canónico de su dirección completa; la clave de fila usa la celda canónica de la Fase 6 y una marca explícita para el grupo sin valor. Una ruta resuelve y verifica cada evidencia.
- **D3 · Semántica en derivadas**: cada tabla conserva su propia revisión (ADR-013); Entendimiento ofrece partir de la revisión del origen como borrador, sin confirmar nada hasta guardar.

## Alternativas

- **DuckDB** (D1-b): mejor a gran escala; hoy, coste de dependencia y de verificación sin beneficio.
- **Moneda en la métrica**: dos fuentes de verdad que podrían contradecirse con la revisión semántica.
- **Exigir rol de medida también a los conteos**: obligaría a llamar «medida» a un identificador para contar operaciones.
- **Evidencia por índice de fila**: frágil ante cualquier cambio de orden o de presentación.
- **Fijar en un plan de v2 la revisión semántica de v1** (D3-b): rompe la verificación revisión ↔ tabla exacta de la Fase 3.
- **«Nulo = 0»**: cambia el resultado sin decisión explícita del usuario; queda fuera.

## Consecuencias

- Una cifra se reproduce con la misma versión de datos, revisión semántica, revisiones de métricas y parámetros; su `evidence_id` es estable para el mismo cálculo y distinto entre ejecuciones (incluye la ejecución).
- Para medir un importe de un CSV propio hay que convertirlo antes (Fase 6) y confirmar la semántica en la versión convertida.
- Las comparaciones, el ranking y la participación (7B) se añadieron como una versión nueva de la operación, `analytics.query@2`, sin cambiar `@1`: [ADR-019](019-comparisons-ranking-share.md).
