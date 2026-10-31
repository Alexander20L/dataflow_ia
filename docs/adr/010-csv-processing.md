# ADR-010 — CSV acotado, objetos locales y cola PostgreSQL

Estado: aceptado para el incremento 0.3.

## Contexto

Se necesita un recorrido real desde carga hasta diagnóstico, conservando originales, aislando propietarios y recuperando trabajos tras interrupciones. El incremento admite archivos pequeños y todavía no requiere un servicio de cola o de almacenamiento externo.

## Decisión

- Puerto `ObjectStore` y adaptador local de objetos inmutables en volumen persistente compartido por API y worker. PostgreSQL guarda referencias, tamaños y SHA-256; nunca el contenido tabular.
- Un dataset principal por proyecto. Cada carga nueva crea una versión numerada e inmutable. El estado pertenece a la ejecución, no modifica los bytes de la versión.
- Carga binaria `text/csv` con `Idempotency-Key` UUID. Misma clave/contenido/configuración devuelve la misma versión; otra entrada con la misma clave da 409. Locks por propietario/proyecto serializan cuota, numeración y archivo.
- La ejecución en cola se confirma en la misma transacción que los metadatos. Sin publicación en un broker externo: no hay dual-write ni se necesita outbox en este incremento.
- Worker separado: `FOR UPDATE SKIP LOCKED`, lease de 120 segundos, token de fencing y máximo 3 intentos. El cómputo corre en subproceso con timeout de 45 segundos (máximo configurable 60). No se mantiene una transacción abierta durante el cómputo. Un intento antiguo o cancelado no puede publicar.
- Artefactos por intento, visibles sólo tras validar resultados y confirmar una transacción única. Errores de entrada no se reintentan; fallos transitorios/timeout sí, dentro del límite. Cancelación cooperativa: el subproceso puede terminar, pero su resultado se descarta.
- Parser CSV estricto y Polars para Parquet, perfilado y vistas paginadas. DuckDB se incorporará cuando las consultas analíticas lo justifiquen.

## Semántica reproducible

UTF-8 con/sin BOM. Coma, punto y coma o tabulador; autodetección opcional con `csv.Sniffer`, registrando el separador efectivo. Cabecera única/no vacía, hasta 128 columnas y 200 caracteres por nombre. Líneas físicamente vacías se omiten; registros con columnas desiguales se rechazan. Se preservan orden, ceros iniciales, espacios y texto; campos vacíos (incluido texto vacío entre comillas) se representan como nulos en la copia. El original nunca cambia.

Parquet conserva columnas de texto nullable. Sugerencias de tipo sobre todos los valores válidos: no conversiones aprobadas ni IA. Números candidatos con punto decimal, hasta 38 caracteres y exponente ajustado acotado; agregaciones Decimal con precisión de 50 dígitos, incluida media redondeada. Fechas candidatas ISO YYYY-MM-DD válidas. Se registra motor, Polars, hash, separador y reglas. Se reproducen resultados estructurados bajo condiciones equivalentes, sin prometer identidad binaria de Parquet entre versiones de librerías.

Reglas `csv-quality-v1`: Q-001 vacíos por columna; Q-002 filas idénticas posteriores a su primera aparición comparando todas las columnas; Q-003 campos no vacíos compuestos sólo por espacio, tabulador, CR o LF. Completitud = celdas no nulas / celdas totales × 100, no una calidad universal. Registros de datos 1-based, distintos de líneas físicas cuando hay campos multilínea. Incidencias con conteo y hasta 5 ejemplos de números de registro; filas completas con autorización/paginación.

## Límites y operación

5 MiB, 100.000 registros, 128 columnas y 10.000 caracteres/campo. Cuota por defecto de 100 MiB de originales/cuenta; una carga activa/proyecto y tres/cuenta. El proxy permite binarios sólo en carga y mantiene 64 KiB para JSON. Worker Docker: 512 MiB y 1 CPU; API con concurrencia HTTP limitada. Límites reducibles por configuración.

Objetos verificados por tamaño/hash antes de usarlos. Publicación mediante temporal, fsync y enlace exclusivo, sin sobrescritura. Claves generadas por el servidor, sin nombres del usuario ni rutas estáticas públicas. Acceso exclusivamente por endpoints autorizados.

## Alternativas y consecuencias

Redis + cola: conveniente para mayor throughput, programación o workers especializados; añade coordinación transaccional y servicio ahora. S3: adecuado para despliegue multinodo, sustituirá el adaptador local. FastAPI BackgroundTasks: descartado por falta de recuperación durable. Cómputo dentro del HTTP: descartado por timeout y falta de reanudación.

El volumen local exige compartir disco entre API y worker. PostgreSQL/objetos se respaldan juntos. Commit incierto, crash o intento obsoleto pueden dejar objetos no referenciados y `.work`; no se borran automáticamente para no eliminar datos potencialmente confirmados. La recolección conservadora y la retención/eliminación quedan para ciclo de vida de datasets. Leases sin heartbeat, sustentados por timeout corto y fencing de publicación.
