# ADR-023 — Automatización determinista gobernada por políticas

Estado: **sustituido** por [ADR-026](026-fully-automatic-single-path.md) (Fase 13): fue implementado en 11B–11E y retirado; la migración 0019 elimina sus tablas. Documentación: [Fase 11](../architecture/phase-11.md) y [Fase 12](../architecture/phase-12.md). Modifica quién puede autorizar una limpieza del [ADR-015](015-supervised-cleaning.md) sin cambiar sus garantías, y limita el papel de la IA del [ADR-022](022-ai-copilot.md) dentro del modo automático. Se apoya en [ADR-002, ADR-005 y ADR-007](decisions.md).

## Contexto

DataFlow es supervisado: cada efecto de limpieza lo aprueba una persona y cada etapa se encadena con botones. El objetivo del producto es que el recorrido —fuente, validación, interpretación, limpieza, análisis, dashboard— funcione con la menor interacción posible.

La base para automatizar con seguridad ya existe: catálogo y validación de planes, vista previa sobre todo el dataset, aprobación ligada al `effect_sha256`, recálculo en la aplicación, versiones derivadas con el original intacto, evidencia por cifra, una cola en PostgreSQL con encolado dentro de la transacción que publica y recuperación de leases vencidas.

Antes de automatizar hay errores conocidos del motor que una aprobación automática amplificaría: la exclusión de nulos falla en columnas tipadas y la precisión decimal no es uniforme entre agregaciones.

## Decisión

- **Estabilizar primero (11.0).** No se habilitan aprobaciones automáticas hasta corregir los errores conocidos del motor y tener la batería completa en verde.
- **Aprobación humana o por política; nunca sin aprobación.** Una política por proyecto, con revisiones inmutables, autoriza operaciones concretas sobre columnas concretas y fija barreras sobre el efecto. Los porcentajes globales son barreras adicionales, no autorización.
- **Desactivada por defecto y sin operaciones autorizadas** hasta que una persona la configure. Los perfiles predefinidos sólo rellenan la política para revisarla.
- **Evaluación en dos partes:** una función pura sobre el plan validado y el manifiesto del efecto (ampliado con efectos por operación y columna), y una comprobación transaccional de permisos, revocación, vigencia y compatibilidad de la aprobación.
- **Restricciones fijas** que ninguna política relaja: no convertir identificadores a número, no operar fuera del catálogo, no publicar conversiones fallidas, no reutilizar aprobaciones incompatibles, no continuar en silencio si falla una columna necesaria.
- **Responsabilidad trazable.** `cleaning_approvals.approved_by` registra a la persona que autorizó la política (columna sin cambios) y `automation_approvals` registra al ejecutor (pipeline y paso), la revisión exacta de la política y el efecto autorizado. Se evita añadir columnas a tablas existentes, como en los ADR-014 y ADR-015.
- **Una tabla activa por sesión de análisis**, independiente de la autenticación y de `dataset_defaults`. Una candidata no sustituye a la activa hasta validarse.
- **Orquestación durable dentro del monolito.** Transición y encolado del paso siguiente en la misma transacción que publica, sobre la cola existente; pasos que no son ejecuciones resueltos en esa transacción; un reconciliador para pipelines detenidos por caídas; claves idempotentes por pipeline, paso e intento. Sin orquestador externo.
- **Sin fallback silencioso ni bucles automáticos.** Ante un error, el pipeline se detiene en «revisión necesaria»; un plan modificado es una revisión nueva, con vista previa y evaluación nuevas.
- **Interpretación por mapeos confirmados, no por inferencia.** Los moldes producen candidatos; una persona confirma el mapeo la primera vez y se reutiliza sólo si cumple un contrato de compatibilidad (columnas, tipos, unidades, grano). La igualdad de nombres o de esquema no basta.
- **La IA sólo explica.** Dentro del modo automático no propone acciones ejecutables. La auditoría textual es un trabajo posterior, anclado a una revisión de dashboard publicada, con cifras resueltas por evidencia y respuesta guardada por clave de contenido. No se promete determinismo por temperatura ni `seed`.
- **Fuentes nuevas separadas (Fase 12)**, cada una produciendo la misma representación tabular inmutable que el CSV.

## Alternativas

- **Aprobar automáticamente todo con el modo activo**: rompe la garantía de que lo publicado es lo autorizado y deja sin respuesta «¿quién autorizó este cambio?».
- **Autorizar sólo por porcentajes globales**: un cambio grave en una columna se diluye en el total.
- **Usuario de sistema como aprobador**: separa lo automático, pero exige un usuario sin credenciales y vistas especiales; registrar a la persona de la política mantiene la responsabilidad en alguien.
- **Confirmar la semántica automáticamente**: un rol mal inferido contamina todos los análisis posteriores sin que nadie lo haya visto; los mapeos confirmados cuestan una revisión por tipo de fuente.
- **Reintentar quitando la conversión que falla**: elimina clics, pero publica un plan que nadie autorizó.
- **Orquestador externo (Celery, Temporal, Airflow)**: reintentos y visibilidad de serie a cambio de otro componente y un segundo modelo de estado; descartado por ADR-002 mientras el volumen lo permita.
- **Determinismo de la IA por `temperature=0` y `seed`**: no lo garantiza ningún proveedor; guardar la respuesta sí.

## Consecuencias

- Tras la primera carga de un tipo de fuente (mapeo y política configurados), una carga compatible llega al dashboard sin clics.
- Cada derivada y cada aprobación automática son rastreables a una persona, una revisión de política y una evaluación.
- Hace falta una bandeja de avisos: un pipeline en «revisión necesaria» que nadie ve no aporta nada.
- El almacenamiento crece con cada derivada automática; se necesita retención que nunca borre versiones referenciadas.
- `analytics` necesita `analytics.query@3` (agregación `sum_product` y medidas semi-aditivas de último corte) para el molde de Inventario; `@1` y `@2` no cambian.
- El manifiesto del efecto crece con datos por operación y columna, de forma aditiva: los efectos publicados conservan su hash y, como en cada despliegue, las aprobaciones pendientes se invalidan.
- Migraciones aditivas, una por entrega, numeradas según el head real; API y worker se despliegan juntos.
