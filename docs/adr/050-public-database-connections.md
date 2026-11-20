# ADR-050 — Conexión a bases de datos públicas

Estado: diseño aceptado para guiar la Fase 32; implementación pendiente. Documentación:
[Fase 32](../architecture/phase-32.md). Modifica [ADR-049](049-related-sources-and-postgresql.md)
§7 («sólo servidores permitidos», SSL `prefer`) y [ADR-035](035-regional-sources-tables-and-structure.md)
§8 (SQL Server sólo a servidores de la lista).

## Contexto

Desde la Fase 18B (SQL Server) y la 31 (PostgreSQL) DataFlow copia tablas de una base remota,
pero sólo a servidores que un administrador escribe en `DATAFLOW_*_ALLOWED_HOSTS`. Sirve para
probar en local o para una organización con sus propias bases, pero no para un servicio donde
cualquiera conecta la suya.

Quien conecta es el servidor de DataFlow. Abrir la lista sin más permitiría usarlo para llegar a
la red interna, a la propia base de DataFlow o a los metadatos de la nube (SSRF), y para probar
contraseñas contra bases de terceros. Además, el subproceso que conecta hereda todas las
variables de entorno (URL de la base y clave de IA), PostgreSQL acepta conexiones sin cifrar y
la copia confía en el tamaño de lo que devuelve el servidor remoto.

## Decisión

1. **Modo público opcional** (`DATAFLOW_DATABASE_PUBLIC_ACCESS`, desactivado por defecto) que se
   suma a la lista: la lista sigue valiendo para bases privadas de confianza.
2. **Regla pura `database-destination-v1`**: se permite un servidor fuera de la lista sólo si
   **todas** sus direcciones son globales y ninguna está denegada (las de la base de DataFlow y
   `DATAFLOW_DATABASE_DENIED_HOSTS`). Se aplica en la API y otra vez en el subproceso justo
   antes de conectar.
3. **Conexión fijada a la IP comprobada** (`hostaddr` en libpq) para que un cambio de DNS no
   salte la regla.
4. **Cifrado verificado en modo público**: `sslmode=verify-full` con las autoridades del sistema
   o un certificado que aporta la persona y se descarta tras la conexión.
5. **El servidor remoto es entrada no confiable**: catálogo con `LIMIT`, copia por lotes con
   límite de bytes por celda y total, límite de memoria del subproceso y sin repetir sus
   mensajes.
6. **Límite de intentos** por usuario, por día y por destino (tabla `database_attempts`,
   migración 0029).
7. **Entorno mínimo** en todos los subprocesos aislados.
8. **Aislamiento de red en el despliegue** (servicio `connector` sin credenciales, en una red de
   salida con cortafuegos hacia rangos privados). El modo público no arranca sin él salvo con
   `DATAFLOW_DATABASE_PUBLIC_UNISOLATED=true`, sólo para desarrollo.

## Decisiones tomadas sin consulta

- **Rechazar el nombre entero** si alguna de sus direcciones es privada, en vez de elegir la
  pública: evita destinos que alternan entre direcciones.
- **Un solo código** (`DATABASE_HOST_PRIVATE`) para privadas y denegadas: no revela qué
  infraestructura propia está protegida.
- **Dos capas** (regla en la aplicación y red en el despliegue): la regla da mensajes claros y
  funciona en local; la red cubre lo que la regla no ve (redirecciones del controlador, errores
  de libpq o FreeTDS).
- **Sólo PostgreSQL** en modo público en esta fase; SQL Server sigue con lista (decisión del
  usuario, igual que no admitir cifrado sin verificar y los límites por defecto: ver la
  [Fase 32](../architecture/phase-32.md#decisiones-del-usuario)).
- **Sin pasos nuevos para la persona**: el certificado es opcional y va plegado, de acuerdo con
  el principio automático de [ADR-026](026-fully-automatic-single-path.md).

## Alternativas descartadas

- **Lista con comodines** (`*.rds.amazonaws.com`): sigue exigiendo un administrador y no
  protege si un nombre del comodín resuelve a una IP privada.
- **Sólo la regla en la aplicación**: no cubre redirecciones del protocolo ni fallos de los
  controladores.
- **Sólo el cortafuegos**: no da mensajes comprensibles y no protege en los despliegues sin él.

## Consecuencias

- Migración 0029 (aditiva) y nuevas variables de configuración.
- Un servicio más en Compose (`connector`) y una regla de cortafuegos que documentar en el
  despliegue.
- Las personas deben permitir en su base las direcciones de salida de DataFlow.
- Proveedores con autoridad propia necesitan que la persona pegue su certificado.
- Los subprocesos aislados dejan de ver variables que hoy heredan por accidente; cualquier paso
  que dependa de una de ellas debe recibirla explícitamente.
