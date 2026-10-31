# Decisiones arquitectónicas iniciales

Estado: aceptadas como dirección técnica; las capacidades futuras se implementarán por incrementos.

## ADR-001 — Monorepo

Contexto: producto pequeño con contratos coordinados. Decisión: apps independientes en un repositorio. Alternativa: multirepo. Ventaja: cambios trazables juntos. Consecuencia: CI por rutas y dependencias separadas. Riesgo: acoplar builds; evitar imports de código backend desde web.

## ADR-002 — Monolito modular

Contexto: reglas y límites todavía evolucionan. Decisión: un backend modular y worker del mismo código. Alternativa: microservicios. Ventaja: menor costo operativo y transacciones simples. Consecuencia: disciplina de interfaces. Riesgo: monolito acoplado; pruebas de importaciones y propiedad de datos.

## ADR-003 — Clean Architecture pragmática

Contexto: coexistirán reglas complejas y CRUD simple. Decisión: capas y puertos donde exista lógica o integración real. Alternativas: capas obligatorias en todo / lógica en routers. Ventaja: pruebas y reemplazo de adaptadores. Consecuencia: composición explícita. Riesgo: sobreabstracción; no crear repositorios genéricos universales.

## ADR-004 — Persistencia separada

Contexto: metadatos transaccionales y archivos tabulares tienen necesidades distintas. Decisión: PostgreSQL + objetos + DuckDB/Polars. Alternativas: todo en PostgreSQL / warehouse desde el inicio. Ventaja: procesamiento columnar y archivos inmutables. Consecuencia: coordinar publicación y recolección. Riesgo: objetos huérfanos; hashes, estados y reconciliación.

## ADR-005 — Pipeline versionado

Contexto: reproducibilidad, aprobación y reintentos. Decisión: versiones inmutables de datos y planes, artefactos con procedencia. Alternativa: modificar datasets en sitio. Ventaja: auditabilidad. Consecuencia: almacenamiento y retención. Riesgo: confundir equivalencia numérica con identidad binaria; tolerancias y formatos canónicos.

## ADR-006 — Adaptadores IA

Contexto: proveedores variables y respuestas no deterministas. Decisión: puertos, salidas estructuradas y evidencia verificada. Alternativa: SDK directo en casos de uso. Ventaja: motor independiente. Consecuencia: evaluación y registro de configuración. Riesgo: fuga de datos y cifras inventadas; minimización y validación.

## ADR-007 — Procesamiento asíncrono confiable

Contexto: solicitudes HTTP no garantizan finalización de análisis largos. Decisión: worker, estado durable, outbox y cola cuando se implemente procesamiento real. Alternativa: BackgroundTasks en proceso / orquestador distribuido complejo. Ventaja: reintentos y recuperación. Consecuencia: entrega al menos una vez e idempotencia obligatoria. Riesgo: duplicación y trabajos atascados; leases, heartbeat y conciliación. Biblioteca de cola pendiente de evaluar.

## ADR-008 — OpenAPI

Contexto: Python y TypeScript se despliegan independientemente. Decisión: FastAPI publica contrato, cliente generado y comprobación de cambios en CI. Alternativa: tipos manuales / compartir código entre lenguajes. Ventaja: consistencia y documentación. Consecuencia: regeneración controlada. Riesgo: compatibilidad semántica no detectada por esquema; pruebas de contrato y de recorrido.
