# Aceptación y orden de ejecución

## Fase 1 entregada

- [x] Inventario del modelo y endpoints 0.3.
- [x] Entidades, cardinalidades, propiedad e invariantes objetivo.
- [x] Separación de original, representación tabular y resultado de análisis.
- [x] Revisiones/hash, objetivo opcional y catálogo limitado de operaciones.
- [x] Estados de ejecución/intento, fencing y límites de transacción.
- [x] Vista previa, efecto y ámbito de aprobación.
- [x] Estrategia de migración reanudable y compatibilidad baseline.
- [x] Esquema de diseño y corpus positivo/negativo comprobables sin API ni DB.

La comprobación estructural de ejemplos no demuestra que la implementación futura cumpla los invariantes. Las fases siguientes deben añadir pruebas reales de dominio, SQL, worker y navegador.

## Primera entrega de Fase 2: separación con paridad CSV

1. Introducir contratos públicos de datasets/executions y sus adaptadores 0.3; separar DTO de versión de la proyección de estado. Mantener el esquema HTTP.
2. Introducir límites de transacción explícitos para registrar fuente+trabajo y publicar resultado. Probar rollback antes de separar repositorios.
3. Preparar migraciones aditivas/mapa de backfill, fixtures de 0002 y prueba de drenaje/cutover.
4. Implementar ejecución/intento/artefactos nuevos con cardinalidad N ejecuciones por input. Registrar operación/versión, snapshots y binding legacy.
5. Adaptar composición y worker. Registrar todos los modelos en ambos procesos y ejecutores mediante puertos.
6. Regenerar OpenAPI sólo si hay cambios aditivos previstos; comprobar drift y compatibilidad del cliente.
7. Verificar el recorrido 0.3 en Docker y navegador con datos de prueba.

**Cierre:** mismas cargas, permisos, bytes, reglas y endpoints, más capacidad demostrada de dos ejecuciones independientes sobre una tabla fijada. Sin activar todavía limpieza ni IA.

## Fases posteriores

### Entendimiento semántico

Revisiones persistidas, identidad de columnas, rol/grano/unidad/formato/nulos y confirmaciones. Cierre: corregir una sugerencia, recargar y recuperar revisión/actor exactos; no confirmar contexto durante migración.

### Planificación

Objetivo opcional, selección de operaciones aplicables, validación por catálogo e inputs fijos. Cierre: sin texto del usuario se puede elegir perfil/calidad; un KPI sin definición suficiente no aparece como ejecutable. Cambiar el predeterminado no redirige un plan guardado.

### Limpieza

Implementar inicialmente trim y exclusión de nulos; incorporar conversión/deduplicación tras sus casos límite y requisitos semánticos. Cierre por operación: preview completo → aprobación → ejecución → derivada + linaje + perfil/calidad. Las operaciones del esquema no se consideran disponibles hasta registrar un ejecutor probado.

## Pruebas de aceptación futuras

| Caso                                    | Resultado exigido                                                           |
| --------------------------------------- | --------------------------------------------------------------------------- |
| Dos planes / una versión                | Artefactos separados por ejecución y slot                                   |
| Mismo archivo / distinta interpretación | TableRef distinto; ningún diagnóstico se reutiliza por version_id solamente |
| Reintento / lease antigua               | Un solo conjunto publicado; intento anterior conservado e inhabilitado      |
| Cambio de plan/input/semántica/entorno  | No reutiliza aprobación ni preview incompatibles                            |
| Cambio del dataset predeterminado       | Mantiene el input histórico; requiere selección explícita para cambiarlo    |
| Filtro / deduplicación                  | Orden y correspondencia de filas trazables                                  |
| Error de conversión                     | Fallo visible y cero versiones derivadas publicadas                         |
| Efecto distinto al aprobado             | PREVIEW_EFFECT_MISMATCH, sin publicar                                       |
| Cancelación / permiso revocado          | No confirma nuevos resultados                                               |
| Migración repetida/interrumpida         | Sin duplicar ni cambiar IDs/hashes                                          |
| Historia sin configuración              | legacy_partial explícito; sin inventar un plan reproducible                 |
| Dos workers reales concurrentes         | Claim exclusivo y publicación con fencing comprobados en PostgreSQL         |

## Decisiones pendientes, con momento de resolución

- Nombres físicos de tablas, índices y organización de puertos UnitOfWork: Fase 2, mediante ADR de persistencia y pruebas de transacciones.
- Duración de la ventana de mantenimiento/recuperación: al preparar el primer despliegue con inventario real.
- Caducidad de aprobaciones: por defecto sin expiración temporal automática; vigencia siempre condicionada a referencias/permisos/revocación. Cambiar esta política requiere configuración explícita.
- Recolección y eliminación de objetos: módulo de ciclo de vida, no durante esta separación.
- Excel/PDF, múltiples tablas, joins, streaming y S3: incrementos posteriores. No bloquean los contratos CSV/limpieza de v1.
- Proveedor/modelo IA y parámetros soportados: integración posterior; sin dependencia del motor determinista.

Estas decisiones no impiden comenzar la separación. Si una requiere cambiar una invariante de este diseño, se revisa el contrato antes de migrar datos.
