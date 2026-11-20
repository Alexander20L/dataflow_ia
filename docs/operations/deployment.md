# Despliegue en producción

Decisión y motivos: [ADR-052](../adr/052-production-deployment.md). Resultado: DataFlow AI en
`https://<dominio>` sobre un servidor Linux, con despliegue automático al fusionar en `main`.

```text
internet ──443──▶ caddy ──edge──▶ web (Next) ──backend──▶ api ──▶ postgres
                                                           │  └─▶ worker (misma cola)
                                                           └─connector─▶ connector ──egress──▶ bases públicas
```

## Sin servidor: publicar desde tu equipo con un túnel

Para una demo o pruebas con otras personas, sin pagar un servidor: Cloudflare da una dirección
pública con HTTPS (`https://<algo>.trycloudflare.com`) que llega a la aplicación de tu equipo.

```powershell
winget install --id Cloudflare.cloudflared          # una vez
powershell -ExecutionPolicy Bypass -File infrastructure\compose\tunnel.ps1
```

`tunnel.ps1` levanta la aplicación, abre el túnel en segundo plano, guarda la dirección en
`infrastructure/compose/.env` (`DATAFLOW_PUBLIC_URL`), reinicia la API con
`compose.tunnel.yaml` (acepta ese origen y las cookies van sólo por HTTPS), comprueba la cadena
entera y muestra la dirección. Opciones: `-Registration off` cierra el registro de cuentas
nuevas (`on` lo abre) y `-Stop` cierra el túnel.

Límites: el equipo debe seguir encendido con Docker abierto; la dirección cambia cada vez que se
abre el túnel (para una fija hacen falta una cuenta de Cloudflare y un dominio propio); con el
registro abierto, cualquiera con el enlace puede crear una cuenta y gastar el saldo de IA.

## 1. Crear el servidor (una vez)

1. Crear un VPS con **Ubuntu 24.04**, al menos **4 vCPU y 8 GB** de RAM y 80 GB de disco (por
   ejemplo Hetzner CX32), con tu clave SSH para root.
2. Crear en tu equipo la clave con la que GitHub Actions entrará al servidor:

   ```powershell
   ssh-keygen -t ed25519 -N '""' -C github-actions-dataflow -f $HOME\.ssh\dataflow_deploy
   ```

3. Copiar la infraestructura y aprovisionar (instala Docker, ufw, fail2ban, actualizaciones
   automáticas, swap, el usuario `deploy`, contraseñas aleatorias y los servicios systemd):

   ```powershell
   scp -r infrastructure root@IP:/tmp/dataflow-infrastructure
   ssh root@IP "DEPLOY_PUBLIC_KEY='$(Get-Content $HOME\.ssh\dataflow_deploy.pub)' sh /tmp/dataflow-infrastructure/production/provision.sh"
   ```

   Con dominio propio, añadir `DATAFLOW_DOMAIN=midominio.com` (con un registro DNS A hacia la
   IP); sin él se usa `IP-con-guiones.sslip.io`.

4. Guardar la clave de Anthropic (sin ella la API no arranca):

   ```sh
   ssh root@IP
   read -rs KEY && printf %s "$KEY" > /opt/dataflow/secrets/ai_api_key && unset KEY
   ```

## 2. Configurar GitHub (una vez)

En el repositorio, **Settings → Secrets and variables → Actions**:

| Tipo     | Nombre               | Valor                                           |
| -------- | -------------------- | ----------------------------------------------- |
| Variable | `DEPLOY_HOST`        | IP del servidor                                 |
| Secreto  | `DEPLOY_SSH_KEY`     | contenido de `~/.ssh/dataflow_deploy` (privada) |
| Secreto  | `DEPLOY_KNOWN_HOSTS` | salida de `ssh-keyscan -t ed25519 IP`           |

Sin `DEPLOY_HOST` el workflow sólo publica las imágenes. Para exigir aprobación antes de cada
despliegue: **Settings → Environments → production → Required reviewers**.

## 3. Desplegar

- **Automático**: cada fusión en `main` compila, publica en GHCR y despliega.
- **A mano**: **Actions → Deploy → Run workflow**.
- **Volver a una versión anterior**: **Run workflow** con `version` = el commit completo de esa
  versión (sus imágenes siguen en GHCR).

`deploy.sh` descarga las imágenes, arranca todo (la API aplica las migraciones), espera a que
esté sano, reaplica el cortafuegos de salida y comprueba `https://<dominio>/api/v1/auth/me`
(401 = la cadena entera responde). Si la versión nueva no arranca, vuelve a la anterior y el
workflow falla con los registros.

## Operación

Todo como `deploy` en `/opt/dataflow`, con este alias:

```sh
alias dc='docker compose --env-file /opt/dataflow/.env -f /opt/dataflow/infrastructure/compose/compose.yaml -f /opt/dataflow/infrastructure/compose/compose.production.yaml --profile full --profile public-databases'
dc ps                     # estado
dc logs -f --tail 100 api worker
dc restart worker
```

- **Configuración**: `/opt/dataflow/.env` (cualquier `DATAFLOW_*` de `platform/config.py` que
  pase `compose.yaml`) y `dc up -d --no-build`. Cerrar el registro:
  `DATAFLOW_REGISTRATION_ENABLED=false`.
- **Cambiar a un dominio propio**: registro DNS A hacia la IP, `DATAFLOW_DOMAIN=…` en `.env` y
  `dc up -d --no-build` (Caddy pide el certificado solo y la API acepta el origen nuevo).
- **Cortafuegos de salida**: `sudo systemctl status dataflow-egress`.

## Copias de seguridad

Cada día a las 03:30 UTC, en `/opt/dataflow/backups` (14 días): `db-*.dump` (PostgreSQL) y
`objects-*.tar.gz` (archivos). A mano: `sudo systemctl start dataflow-backup`.

**Fuera del servidor (recomendado)**: instalar y configurar `rclone` para root (por ejemplo un
Hetzner Storage Box o un bucket S3) y añadir `DATAFLOW_BACKUP_REMOTE=remoto:dataflow` a `.env`.

**Restaurar** (como root, desde `/opt/dataflow`, en este servidor o en uno nuevo ya aprovisionado
y desplegado):

```sh
dc stop api worker web connector
dc exec -T postgres pg_restore -U dataflow -d dataflow --clean --if-exists < backups/db-FECHA.dump
docker run --rm -v dataflow_objects_data:/data -v /opt/dataflow/backups:/backup alpine:3.22 \
  sh -c 'rm -rf /data/* && tar xzf /backup/objects-FECHA.tar.gz -C /data'
dc up -d --no-build
```

Restaurar siempre la base y los archivos de la misma fecha.

## Límites conocidos

- Un solo servidor: si se pierde, se restaura la última copia en otro.
- Un despliegue interrumpe las copias de bases en curso (viven en memoria de la API, ADR-051).
- El registro está abierto y no hay verificación de correo ni recuperación de contraseña
  (ADR-009).
