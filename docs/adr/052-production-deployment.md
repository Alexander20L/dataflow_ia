# ADR-052 — Despliegue en producción: un servidor Linux con Docker Compose

Estado: aceptado. Guía de operación: [Despliegue en producción](../operations/deployment.md).
Completa [ADR-009](009-local-identity.md) (proxy confiable para el límite de intentos) y
[ADR-050](050-public-database-connections.md) (cortafuegos de salida en el anfitrión).

## Contexto

DataFlow AI se ejecuta en local con Docker Compose y no tiene todavía un entorno público.
Varias piezas condicionan dónde puede vivir:

- La API y el worker comparten los archivos en un volumen (`objects_data`), no en un
  almacenamiento de objetos.
- Las copias de bases (Fase 33) corren hasta 30 minutos en hilos de la API.
- El conector de bases públicas (Fase 32B) necesita una red de salida aislada y reglas de
  iptables en el anfitrión (`egress-firewall.sh`).
- El límite de intentos de la identidad veía la IP del proxy de Next, no la de cada persona.

## Decisión

1. **Un servidor Linux (VPS, Ubuntu 24.04) con Docker Compose**: la misma composición que en
   local más una capa `compose.production.yaml` (imágenes publicadas, reinicio automático,
   sin puertos internos publicados, registros con rotación, más memoria para API y worker).
2. **Caddy como única entrada**, con HTTPS automático (Let's Encrypt) y cabeceras de
   seguridad. Sólo está en la red `edge` con la web: no llega a la API ni a PostgreSQL.
3. **IP real en el límite de intentos**: Caddy sustituye `X-Forwarded-For` por la IP de la
   conexión, el proxy de Next la reenvía y uvicorn sólo la cree si llega de la subred fija de
   la red `backend` (`FORWARDED_ALLOW_IPS`). Fuera de producción no cambia nada: uvicorn
   confía por defecto sólo en `127.0.0.1` y el arranque local mantiene `proxy_headers=False`.
4. **Imágenes compiladas en GitHub Actions** y publicadas en GHCR con la etiqueta del
   commit; el servidor nunca compila. Cada fusión en `main` despliega por SSH
   (`.github/workflows/deploy.yml`); el token de GHCR sólo vive durante el paso de despliegue.
   Volver atrás = desplegar una etiqueta anterior.
5. **Migraciones al arrancar la API** (como ya hacía el contenedor). `deploy.sh` espera a que
   todo esté sano, comprueba la cadena entera por HTTPS y, si la versión nueva no arranca,
   vuelve a la anterior.
6. **Copia de seguridad diaria** (temporizador systemd): `pg_dump` y después los archivos,
   14 días en el servidor y, opcionalmente, una copia fuera con rclone.
7. **Cortafuegos**: de entrada (ufw: SSH, 80 y 443) y de salida del conector como servicio
   systemd que se reaplica al arrancar Docker y en cada despliegue.

## Decisiones tomadas con el usuario

- **VPS nuevo** en lugar de una nube gestionada (que exigiría pasar los archivos a
  almacenamiento de objetos) o de Render/Railway/Vercel (sin volumen compartido ni
  cortafuegos del anfitrión).
- **Sin dominio propio por ahora**: `<ip-con-guiones>.sslip.io` da HTTPS válido; cambiar a un
  dominio propio es editar `DATAFLOW_DOMAIN` y volver a desplegar.
- **Registro abierto** (`DATAFLOW_REGISTRATION_ENABLED=true`), aunque ADR-009 recomienda
  verificación de correo antes del autoservicio público. Se puede cerrar en cualquier momento
  con esa variable.
- **Bases públicas activas** con el conector aislado.

## Decisiones tomadas sin consulta

- **IA obligatoria en producción** (`DATAFLOW_AI_REQUIRED=true`): sin clave, la API no arranca
  y el despliegue falla de forma visible, en vez de analizar sin IA sin que nadie lo note.
- **Usuario `deploy`** en el grupo `docker` (equivale a root en el anfitrión) con un único
  permiso de sudo: reaplicar el cortafuegos de salida.
- **Fusionar en `main` despliega** sin esperar a otro workflow: a `main` sólo llegan PR que ya
  pasaron Backend y Frontend. El entorno `production` de GitHub permite añadir aprobación
  manual si se quiere.

## Alternativas descartadas

- **Compilar en el servidor** (`git pull` + `up --build`): necesita credenciales del repositorio
  y memoria para Next, y no deja etiquetas a las que volver.
- **Nginx + Certbot**: más piezas y renovación aparte; Caddy lo hace solo.
- **Kubernetes**: desproporcionado para un monolito modular con un worker.

## Consecuencias

- Un solo servidor: un fallo del equipo detiene el servicio hasta restaurar la copia en otro.
  Las copias de bases en curso se pierden al desplegar (ADR-051: viven en memoria de la API).
- Para crecer en horizontal habrá que llevar `objects_data` a almacenamiento de objetos.
- Variables nuevas sólo de producción: `DATAFLOW_DOMAIN`, `DATAFLOW_IMAGE_API`,
  `DATAFLOW_IMAGE_WEB`, `DATAFLOW_VERSION`, `DATAFLOW_BACKEND_SUBNET`, `DATAFLOW_BACKUP_REMOTE`.
