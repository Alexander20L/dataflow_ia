# ADR-013 — Revisión semántica persistida sin transformación

Estado: implementado en Fase 3 / API 0.5. Desarrolla SemanticContract de Fase 1.

> **Vigencia (Fase 13, [ADR-026](026-fully-automatic-single-path.md))**: la supervisión humana que fija este ADR quedó sin efecto en el producto; la revisión semántica confirmada por una persona y sus rutas se retiraron. Siguen vigentes las revisiones inmutables y el servicio (sin rutas públicas). La interpretación actual es automática y por reglas (`understanding.profile@3`, [ADR-025](025-automatic-descriptive-interpretation.md)) y no se registra como «confirmada».

## Contexto

Un perfil no determina qué representa cada fila ni si un número es código, medida o importe en cierta moneda. Se necesitan decisiones persistentes y trazables sin modificar datos o análisis anteriores.

## Decisión

- Understanding es dueño del dominio, revisiones, puertos y API. Bootstrap inyecta acceso autorizado a representaciones y conteos Polars para evitar ciclos con executions.
- Familia única por tabla publicada: fija versión, SHA físico y fingerprint de esquema con IDs existentes. GET no crea familia ni confirma nada.
- Revisiones inmutables con padre, número, contenido/hash, actor y fecha. Cabeza bajo lock y expected_revision. Guardado parcial; revisión pending/confirmed/rejected por columna, grano y clave.
- Actor/origen/fecha se asignan en servidor. Cambios intactos conservan procedencia; no-op no crea revisión. Nonce idempotente recupera la revisión original aunque avance la cabeza. Conflicto no sobrescribe.
- Heurísticas `semantic-hints-v1`; no se confirman moneda, unidad ni granularidad por inferencia. Catálogo fijo de monedas incluye códigos históricos/especiales para declarar contexto, sin tipos de cambio ni habilitación automática de KPIs.
- Descripción, interpretación declarada y versión de sugerencias amplían aditivamente el esquema de diseño; se conservan sus ejemplos anteriores.
- Declarar nulos no reinterpreta valores ni reglas existentes. Confirmar una clave no prueba unicidad: duplicados/nulos generan observaciones, sin borrar ni bloquear el contrato.
- Semántica opcional en planes técnicos. Referencia fija por ID/revisión/hash y TableRef; comprobada al encolar y en worker. Una cabeza posterior no cambia referencias históricas.
- 0004 es aditiva y no crea confirmaciones. Triggers de inmutabilidad y vínculo de familia; downgrade rechazado si hay revisiones o planes semánticos.

## Alternativas y consecuencias

Sobrescribir una descripción pierde contexto histórico; confirmar por nombre produce certezas falsas; mezclar semántica con conversión modifica datos sin operación explícita. La solución añade revisiones/conflictos, pero conserva decisiones exactas. Confirmar es una declaración del usuario, no una prueba de verdad de negocio.

La revisión actual agrupa atributos de una definición. La UI vuelve a pendiente al editarlos. Operaciones futuras exigirán sólo atributos pertinentes confirmados. Origen IA está reservado en lectura; no hay proveedor ni llamadas LLM en esta fase.
