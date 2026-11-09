# Analista automático — dashboard y explicación sin configuración

> **Estado actual (Fases 13–13C)**: este recorrido es ya el **único** del producto
> ([ADR-026](../adr/026-fully-automatic-single-path.md)). Las secciones A1–C2 se conservan como
> historia de cada incremento y algunas de sus frases ya no describen el sistema:
>
> - A1 estabilizó el pipeline por política, retirado en la Fase 13 (migración 0019).
> - B2 ofrecía «Herramientas avanzadas (opcionales)»; se retiraron en la Fase 13.
> - C2 dejaba la IA desactivada por defecto; desde la Fase 13B es `auto` (activa si hay clave,
>   [ADR-027](../adr/027-excel-and-ai-without-configuration.md)). Decisión de C2:
>   [ADR-029](../adr/029-automatic-ai-explanation.md).
> - La IA **sólo explica** resultados publicados; no propone interpretaciones, transformaciones ni
>   análisis.

## Objetivo acordado

**Subir una fuente → procesar sin formularios → dashboard → explicación opcional.**

El recorrido principal no exige activar políticas, confirmar semántica, elegir moldes, aprobar limpiezas ni ejecutar planes manualmente. El backend calcula con Polars y decide con reglas versionadas; la IA sólo explica resultados publicados, sin generar cifras, código ejecutable ni SQL libre. Se conserva la evidencia y el original inmutable.

La fuente activa puede contener varias tablas. Se analizan por separado, sin joins ni concatenaciones inferidos. Cuando una interpretación es ambigua, se muestran análisis genéricos y limitaciones, no preguntas ni significados inventados. Los errores de lectura siguen siendo explícitos.

Este documento describe cómo se construyó el recorrido por incrementos. El recorrido supervisado de las Fases 4–11 se retiró de la API y de la interfaz en la Fase 13, conservando sus tablas y su historia.

## A1 — Estabilización inicial implementada

Sin migraciones ni cambios del contrato HTTP:

- Una consulta analítica fallida o cancelada no permite publicar el dashboard ni marcar el pipeline como completado. Se conserva el motivo `ANALYSIS_FAILED` o `EXECUTION_CANCELLED`.
- Si no hay limpieza que aplicar, las reglas de calidad se evalúan sobre la representación original antes de seleccionar la fuente. No se crea una derivada innecesaria.
- La exclusión mutua del pipeline usa una conexión PostgreSQL dedicada y fijada hasta liberar el advisory lock. Los commits y rollbacks de la sesión de trabajo no cambian la conexión propietaria del bloqueo. Una adquisición repetida por el mismo repositorio no incrementa el contador reentrante.
- El destino de publicación del dashboard (crear o revisar, familia y revisión esperada) se persiste antes de publicar. Si el worker cae después del commit del dashboard y antes de registrar su salida, repite la solicitud original con la misma clave y obtiene el replay, sin crear otra revisión ni adoptar otra cabeza.

Cada pipeline en avance consume una conexión adicional mientras posee el bloqueo; los límites de concurrencia y el tamaño del pool deben tenerlo en cuenta. Ante errores al adquirir o liberar el lock, su conexión se invalida para no devolver al pool una sesión PostgreSQL con un posible bloqueo retenido.

Pruebas de regresión: `apps/api/tests/test_automation_stabilization.py`, más recuperación real tras caída en `test_automation_dashboard.py` y comprobación de la ruta sin limpieza en `test_automation_pipeline.py`.

Esta entrega mantiene el comportamiento supervisado y sus códigos de estado. **No activa todavía el recorrido sin preguntas**, no llama automáticamente a la IA y no modifica el despliegue Docker existente.

## B1 — Dashboard descriptivo al importar (API 0.15)

Las nuevas cargas CSV y las importaciones XLSX seleccionadas generan automáticamente un snapshot `profile.overview` con `kpis`, `charts`, `table_detail` y limitaciones. No exige política, mapeo ni revisión semántica. Se calcula dentro del subproceso acotado de ingesta y se publica atómicamente junto al perfil y calidad, bajo las mismas garantías de permisos, cancelación, reintentos y fencing. Abrir o recargar la página sólo lee el resultado guardado: no calcula ni llama a IA.

El catálogo pasa a `analysis-v9`: `understanding.profile@2` incorpora este resultado al perfil. `understanding.profile@1`, los planes ya guardados y sus referencias doradas permanecen compatibles. Los análisis técnicos explícitos sobre tablas siguen usando `@1`. No hay migración SQL ni backfill: una carga histórica sin overview continúa mostrando su diagnóstico existente; una nueva carga produce el snapshot.

La interfaz presenta «Tu análisis automático» antes de las herramientas avanzadas, que siguen disponibles como opciones no necesarias para obtener el resultado inicial. Los indicadores incluyen registros, columnas, completitud y filas idénticas adicionales. Hasta tres columnas numéricas reconocibles aportan promedio (seis decimales, HALF_EVEN), mínimo y máximo con cobertura; nombres reconocidos como identificadores se excluyen. No se generan sumas ni se atribuye significado monetario o comercial. Categorías repetidas y fechas ISO permiten conteos y evolución mensual, con límites de grupos explícitos. El detalle conserva orden, nulos y ceros iniciales; se acota a veinte filas y trescientos caracteres por celda, sin modificar la fuente.

Este es un **dashboard inicial descriptivo**, no una familia editable del módulo `dashboards`. Todavía no utiliza IA, no transforma datos, no descubre automáticamente todas las hojas de un libro y no sustituye el pipeline supervisado para análisis avanzados. La interpretación de negocio, la simplificación completa de las pantallas y la auditoría automática siguen pendientes.

## B2 — Dashboard como vista principal

El workspace abre con el dashboard descriptivo y un botón «Herramientas avanzadas (opcionales)». Los componentes de políticas, mapeos, semántica, planes, ejecuciones y copiloto sólo se montan al abrir esa sección. La vista principal no dispara sus consultas HTTP ni exige decisiones para mostrar el snapshot. Cerrar la sección vuelve a la vista inicial y protege los borradores con el mismo aviso de descarte existente; las revisiones guardadas no se alteran.

Los estados de carga, error y cancelación siguen visibles sin abrir herramientas. Las versiones históricas y derivadas sin snapshot muestran su diagnóstico técnico existente, sin recalcular ni inventar un dashboard. Recargar una carga nueva vuelve a la vista automática; la sección avanzada no se activa por preferencias globales ni por una política guardada.

Se mantienen la descarga del original y la navegación de versiones. No se borran endpoints ni tablas del recorrido avanzado. Las pruebas de esas funcionalidades entran ahora explícitamente mediante el botón, mientras que el E2E del recorrido automático verifica su ausencia inicial, la ausencia de consultas de configuración y el guard de borradores al cerrar.

## C1 — Interpretación descriptiva automática (API 0.16)

Las nuevas importaciones usan `understanding.profile@3` en `analysis-v10`. El snapshot `automatic-overview-v2` añade una interpretación versionada por reglas (`automatic-interpretation-v1`): columnas identificadoras probables, fechas reconocibles, valores numéricos, categorías, texto y columnas vacías. Normaliza acentos y separa camelCase para detectar nombres de identificadores; no agrega esas columnas como medidas.

Se reutiliza la detección pura de candidatos de `templates` mediante su interfaz pública, sin importar persistencia ni crear mapeos. Se exigen las señales centrales de fecha+importe para un candidato de ventas y producto+cantidad para inventario; un contexto incompleto o varios candidatos completos permanecen ambiguos. La moneda, unidad y grano no se inventan. No se generan ingresos, conteos de ventas ni stock actual. Columnas monetarias reconocibles no se agregan cuando una columna de moneda reconocida tiene varios valores distintos; los demás análisis siguen disponibles.

El dashboard prioriza fechas y categorías para elegir gráficos, conserva el orden original del detalle y explica qué puede calcular y qué no. La interpretación es informativa, no es una revisión semántica confirmada y no exige respuestas. Se publica con el perfil en el subproceso de importación; recargar sólo recupera el snapshot almacenado. No se llama a proveedores IA en esta entrega.

Los artefactos `profile@1` y `profile@2` conservan su serialización anterior: el campo nuevo `interpretation` se omite en los snapshots v1. Los planes antiguos se siguen ejecutando con la operación fijada, sin alterar sus cifras ni reclasificar sus datos. No se requiere migración SQL.

Limitación: esta entrega interpreta el contexto y selecciona análisis descriptivos seguros; **no implementa todavía propuestas semánticas del modelo, análisis de negocio automáticos ni explicación IA**. El siguiente incremento debe añadir esas capacidades con validación y evidencia, sin volver a introducir confirmaciones obligatorias.

## C2 — Explicación automática sobre el dashboard publicado (API 0.17)

Las importaciones con `understanding.profile@2/@3` encolan `overview_audit` dentro de su publicación si hay proveedor configurado (y clave para Anthropic). El trabajo fija ID y SHA-256 del perfil y de la versión, además de la ejecución productora. Reutiliza la cola, las autorizaciones y el fencing existentes; `copilot.audit_overview@1` es una operación interna, no una opción del catálogo. No crea versiones ni altera datos, perfiles o dashboards.

El prompt `automatic-overview-audit@1` recibe hasta 64 cifras calculadas (KPI y puntos agregados de gráficos), etiquetas marcadas como no confiables y limitaciones. No recibe `table_detail`, ejemplos del perfil, filas ni archivos. Las etiquetas de categorías sí son datos de la fuente: se incluyen sólo para identificar sus agregados. El contexto serializado tiene un máximo de 64 KB. La salida contiene resumen ejecutivo, hasta tres alertas y exactamente dos recomendaciones. El verificador existente sustituye las referencias por cifras exactas, retira números libres y rechaza toda respuesta con referencias desconocidas. La verificación de cifras no garantiza la corrección semántica de toda la prosa del modelo.

Se guardan la explicación verificada, evidencia con rutas al snapshot y metadatos de consumo. Los GET de estado y evidencia nunca llaman al proveedor. La interfaz los consulta automáticamente y hace polling sólo mientras el trabajo está en cola o ejecutándose. No pide confirmaciones ni incorpora botones de generación. Si el proveedor falla, el presupuesto registrado se agota o la salida es inválida, el dashboard continúa disponible.

El trabajo tiene un solo intento y el proveedor worker desactiva los reintentos del SDK; su timeout se limita al plazo de procesamiento menos un margen. Una caída después de la llamada y antes de publicar puede dejar consumo no registrado y una explicación fallida: no se promete exactamente una llamada facturada ni recuperación automática de ese resultado. Los controles de presupuesto son comprobaciones sobre consumo registrado, **no reservas durables ni un techo estricto ante concurrencia**. La IA real permanece desactivada por defecto; las pruebas usan `fake`, sin red ni coste externo. No hay generación retroactiva para versiones antiguas.

Compose pasa al worker el mismo proveedor, modelo y secreto que a la API. No se necesita migración SQL: se añaden tipos sobre las columnas de texto de ejecuciones y artefactos existentes. SQL Server y lectura de PDF siguen pendientes.

## Siguientes entregas

Hechas desde entonces: retirar la configuración del recorrido principal sin borrar historia (Fase 13),
Excel sin elegir hoja e IA `auto` (13B) y cargas en cola en vez de rechazos (13C). Lo pendiente se
especifica en la Fase 14 a partir de las especificaciones del producto:

1. **Preparación automática**: sólo transformaciones seguras y sin pérdida, decididas por reglas
   versionadas y registradas como decisión del sistema; nunca excluir filas ni convertir
   identificadores. Versiones derivadas con el dashboard descriptivo (`profile@3`).
2. **Análisis**: calidad con reglas deducidas y análisis con evidencia (`analytics.query@3`) elegidos
   por reglas, sin sumar medidas no aditivas ni mezclar monedas.
3. **Endurecer la explicación C2**: reservas durables de presupuesto y contabilización ante caídas.
4. **Fuentes**: varias tablas por libro, SQL Server y PDF, redefinidos sin elección humana.
5. **Operación**: cuotas totales, retención, backups y destino de las tablas sin uso de las
   Fases 4–10 y de `reportlab`.

## Criterio de producto

Una carga legible produce resultados guardados sin configuración del usuario. Un análisis no sustentable se omite con una explicación y no bloquea los demás. El mismo input y decisiones guardadas producen las mismas cifras; no se promete determinismo del texto del modelo.
