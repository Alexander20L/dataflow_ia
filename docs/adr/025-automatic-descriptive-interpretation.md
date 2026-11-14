# ADR-025 — Interpretación automática sin confirmaciones semánticas

Estado: implementado en C1. Referencia: [analista automático](../architecture/automatic-analyst.md).

## Contexto

El dashboard inicial no requiere configuración, pero no explica la interpretación de las columnas y elige gráficos según su posición. El producto necesita actuar sin preguntas, sin convertir tipos o nombres sugeridos en verdades de negocio. Los mapeos confirmados existentes pertenecen al recorrido avanzado y no deben fabricarse para evitar sus validaciones.

## Decisión

- Versionar `understanding.profile@3` y `analysis-v10`, sin modificar las operaciones anteriores.
- Publicar `automatic-overview-v2` con una interpretación estructurada y versionada, calculada dentro del subproceso de importación. No escribir revisiones semánticas ni mapeos.
- Reutilizar los candidatos de `templates` a través de un puerto público puro. Excluir identificadores de los candidatos y de las estadísticas numéricas. Exigir señales centrales, mantener explícitos los contextos ambiguos y no inferir moneda, unidad ni grano.
- Seleccionar primero gráficos temporales y de categorías manteniendo el orden original en el detalle. Etiquetas y métricas siguen siendo descriptivas: no crear sumas de ingresos ni snapshots de stock por heurística.
- Omitir agregaciones monetarias reconocibles cuando una columna de moneda reconocida contenga varios valores. Mostrar una limitación sin bloquear los demás resultados.
- Mostrar la interpretación sin formularios ni botones de confirmación. Recuperarla del artefacto almacenado al recargar, no recalcular durante GET o render.
- Mantener compatibilidad de lectura y serialización de `profile@1`, `profile@2` y snapshots v1.

## Consecuencias

El usuario recibe una explicación de qué se detectó y por qué ciertas conclusiones no se calculan. Es una lectura heurística con límites conocidos, no una certificación del negocio. No requiere credenciales ni llamadas IA, y no introduce proveedores dentro del proceso de cálculo. La integración de propuestas IA y auditoría textual automática se aborda por separado, con evidencia, privacidad y límites de consumo.
