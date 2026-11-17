# ADR-028 — Las cargas esperan en cola, no se rechazan

Estado: aceptado e implementado en la Fase 13C (API 0.20.0, sin migración). Completa ADR-026.

## Contexto

La admisión de trabajos (`Executions.ensure_capacity`) rechazaba una carga con 409 si el
propietario tenía 3 trabajos en cola o en marcha (`QUEUE_LIMIT`) o si el proyecto ya tenía una
importación pendiente (`PROJECT_BUSY`). La persona tenía que esperar y volver a subir el archivo:
una intervención manual que contradice el recorrido automático (ADR-026).

## Decisión

1. **Admisión**: una carga se registra siempre (original inmutable y versión) y su ejecución
   queda `queued`. Sólo se rechaza con `QUEUE_LIMIT` (409) si el propietario acumula
   `PENDING_LIMIT` = 50 trabajos pendientes, como protección frente a abusos. `PROJECT_BUSY`
   deja de emitirse.
2. **Concurrencia al reclamar** (`SQLExecutionRepository.claim`): el worker toma el trabajo más
   antiguo cuyo propietario tenga menos de `RUNNING_LIMIT` = 3 trabajos en marcha (con concesión
   vigente) y, si es una importación, sin otra importación del mismo proyecto en marcha. Las
   versiones de un proyecto se procesan así en orden de llegada. Una concesión vencida se
   recupera siempre.
3. Las reclamaciones se serializan con un bloqueo consultivo de transacción de PostgreSQL
   (`pg_advisory_xact_lock`) para que varios workers evalúen los límites sobre un estado estable;
   la transacción de reclamación es corta.
4. Los límites son constantes del dominio de `executions` (`domain.py`), no configuración.

## Consecuencias

- La interfaz muestra «En cola: esperando su turno» y no exige volver a subir nada.
- Un propietario con muchas cargas no ocupa más de 3 huecos del worker a la vez; el resto de
  propietarios sigue avanzando.
- Cambio de comportamiento compatible: los clientes que reintentaban ante `PROJECT_BUSY` o
  `QUEUE_LIMIT` reciben ahora 202.

## Alternativas descartadas

- Reintentar la subida desde la interfaz: sigue dependiendo de que la persona mantenga la página
  abierta y duplica originales.
- Una tabla de cola separada: el estado `queued` de `executions` ya es la cola durable.
