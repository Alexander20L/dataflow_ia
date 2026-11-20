# ADR-051 — Todas las tablas de una base, copia en segundo plano y espera del presupuesto de IA

Estado: aceptado e implementado en la Fase 33 (API 0.42.0, migración 0030). Documentación:
[Fase 33](../architecture/phase-33.md). Modifica [ADR-049](049-related-sources-and-postgresql.md)
§7 (hasta 10 tablas) y [ADR-050](050-public-database-connections.md) (copia dentro de la
petición, error al pasar el tope de bytes).

## Contexto

DataFlow quiere trabajar como un analista: ante una base, leerla entera y analizarla con
criterio, tarde lo que tarde. Hoy lee como mucho 10 tablas, copia dentro de la petición HTTP
(45 s), falla entera si pasa de 50 MB y, cuando se agota el presupuesto de IA, sigue sólo con
reglas.

## Decisión

1. **Sin límite de tablas** en `postgresql-selection-v2` y `sqlserver-selection-v3`: se copian
   todas las que caben, de menor a mayor; lo que no cabe se omite con su motivo.
2. **El tope de bytes omite en vez de fallar** y sube a 200 MB (la copia vive en memoria).
3. **Copia en segundo plano, en la API y en memoria**: la contraseña sigue sin guardarse en
   ningún sitio, así que la copia corre en un hilo de la API que la conserva en memoria; su
   estado (sin credenciales) queda en `database_copies`. Un reinicio la interrumpe.
4. **Presupuesto de IA agotado → aplazar**: los trabajos con IA vuelven a la cola con
   un intento `deferred` cuyo `lease_until` es el momento de la renovación, en vez de seguir
   sin IA.

## Decisiones tomadas sin consulta

- **Hilo en la API y no trabajo del worker**: el worker sólo lee de la cola, y llevar la
  contraseña hasta él exigiría guardarla (cifrada o no) en la base o en disco. Se acepta
  perder la copia si la API se reinicia.
- **De menor a mayor** al copiar: con un tope de bytes, entran más tablas.
- **Una copia en curso por cuenta**: una base grande no acapara los hilos de la API.
- **Latido en vez de limpieza al arrancar**: una copia sin latido se da por interrumpida al
  consultarla; sirve con varias réplicas de la API.
- **La cola admite una carga como un todo**: las versiones de una misma base entran juntas
  aunque pasen del límite de pendientes.
- **Sin estado nuevo en el progreso**: la etapa aplazada sigue en cola y su detalle dice hasta
  cuándo espera.
- **«Ver esquema» también en segundo plano**, con el mismo mecanismo: con muchas tablas tampoco
  cabe en 45 s.

## Alternativas descartadas

- **Subir el plazo de la petición**: frágil (proxies, cortes de conexión) y sin progreso.
- **Guardar la contraseña cifrada para el worker**: contradice ADR-035 §8 y ADR-049 §7.
- **Seguir sin IA al agotar el presupuesto**: análisis de menor calidad en parte de la base,
  contra la decisión del usuario.

## Consecuencias

- Migración 0030: `database_copies` (el aplazamiento usa los intentos existentes).
- Las rutas de copia y foto responden 202 con un `DatabaseCopy` en vez de la versión o el
  modelo: la web los sigue con `GET /database-copies/{id}`.
- Un análisis completo puede tardar horas o días si se agota el presupuesto de IA.
