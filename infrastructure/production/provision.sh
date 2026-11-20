#!/bin/sh
# Prepara un servidor Ubuntu 24.04 recién creado para DataFlow AI (ADR-052). Se ejecuta una vez,
# como root, y se puede repetir sin romper nada (no regenera contraseñas ni tokens existentes).
#
#   scp -r infrastructure root@SERVIDOR:/tmp/dataflow-infrastructure
#   ssh root@SERVIDOR 'DEPLOY_PUBLIC_KEY="ssh-ed25519 AAAA… github-actions" \
#     sh /tmp/dataflow-infrastructure/production/provision.sh'
#
# Variables opcionales:
#   DEPLOY_PUBLIC_KEY   clave pública con la que GitHub Actions entra como `deploy`.
#   DATAFLOW_DOMAIN     dominio propio; sin él, <ip-con-guiones>.sslip.io (HTTPS sin dominio).
#   DATAFLOW_ROOT       directorio de instalación (por defecto /opt/dataflow).
set -eu

ROOT="${DATAFLOW_ROOT:-/opt/dataflow}"
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY_USER=deploy

if [ "$(id -u)" -ne 0 ]; then
  echo "Ejecutar como root." >&2
  exit 1
fi

echo "== Paquetes del sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -yq
apt-get install -yq ca-certificates curl gnupg ufw fail2ban unattended-upgrades rsync iptables
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "== Docker Engine (repositorio oficial)"
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin \
    docker-compose-plugin
fi
systemctl enable --now docker

echo "== Memoria de intercambio (4 GB)"
if ! swapon --show | grep -q .; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi

echo "== Cortafuegos de entrada: sólo SSH, HTTP y HTTPS"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

echo "== Usuario $DEPLOY_USER (despliegues desde GitHub Actions)"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
if [ -n "${DEPLOY_PUBLIC_KEY:-}" ]; then
  KEYS="/home/$DEPLOY_USER/.ssh/authorized_keys"
  touch "$KEYS"
  grep -qxF "$DEPLOY_PUBLIC_KEY" "$KEYS" || echo "$DEPLOY_PUBLIC_KEY" >> "$KEYS"
  chown "$DEPLOY_USER:$DEPLOY_USER" "$KEYS"
  chmod 600 "$KEYS"
fi
# Lo único que `deploy` puede hacer como root: reaplicar el cortafuegos de salida.
echo "$DEPLOY_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart dataflow-egress.service" \
  > /etc/sudoers.d/dataflow-deploy
chmod 440 /etc/sudoers.d/dataflow-deploy

# Sin contraseñas por SSH, pero sólo si root ya entra con clave (para no dejar a nadie fuera).
if [ -s /root/.ssh/authorized_keys ]; then
  cat > /etc/ssh/sshd_config.d/60-dataflow.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
  systemctl reload ssh
fi

echo "== Archivos en $ROOT"
install -d -m 755 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$ROOT" "$ROOT/infrastructure"
install -d -m 700 "$ROOT/backups"
# Docker (root) monta los secretos; `deploy` sólo necesita ver que existen.
install -d -m 750 -o root -g "$DEPLOY_USER" "$ROOT/secrets"
rsync -a --delete "$SOURCE/" "$ROOT/infrastructure/"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$ROOT/infrastructure"

random() { od -An -N32 -tx1 /dev/urandom | tr -d ' \n'; }

# Los secretos los lee el usuario sin privilegios de los contenedores: 644 dentro de un
# directorio de root al que sólo entra `deploy` (que ya es administrador de Docker).
[ -f "$ROOT/secrets/ai_api_key" ] || install -m 644 /dev/null "$ROOT/secrets/ai_api_key"
if [ ! -s "$ROOT/secrets/connector_token" ]; then
  random > "$ROOT/secrets/connector_token"
  chmod 644 "$ROOT/secrets/connector_token"
fi

PUBLIC_IP="$(ip -4 route get 1.1.1.1 | sed -n 's/.* src \([0-9.]*\).*/\1/p')"
DOMAIN="${DATAFLOW_DOMAIN:-$(echo "$PUBLIC_IP" | tr . -).sslip.io}"

if [ ! -f "$ROOT/.env" ]; then
  cat > "$ROOT/.env" <<EOF
# DataFlow AI en producción (ADR-052). Creado por provision.sh; deploy.sh actualiza la versión.
DATAFLOW_DOMAIN=$DOMAIN
POSTGRES_PASSWORD=$(random)
DATAFLOW_AI_API_KEY_SECRET_FILE=$ROOT/secrets/ai_api_key
DATAFLOW_AI_PROVIDER=auto
DATAFLOW_AI_REQUIRED=true
DATAFLOW_REGISTRATION_ENABLED=true
DATAFLOW_CONNECTOR_TOKEN_SECRET_FILE=$ROOT/secrets/connector_token
DATAFLOW_DATABASE_PUBLIC_ACCESS=true
DATAFLOW_DATABASE_EGRESS_IPS=["$PUBLIC_IP"]
DATAFLOW_IMAGE_API=
DATAFLOW_IMAGE_WEB=
DATAFLOW_VERSION=
EOF
fi
chown "$DEPLOY_USER:$DEPLOY_USER" "$ROOT/.env"
chmod 600 "$ROOT/.env"

echo "== Servicios systemd: cortafuegos de salida y copia de seguridad diaria"
install -m 644 "$SOURCE/production/systemd/dataflow-egress.service" /etc/systemd/system/
install -m 644 "$SOURCE/production/systemd/dataflow-backup.service" /etc/systemd/system/
install -m 644 "$SOURCE/production/systemd/dataflow-backup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable dataflow-egress.service
systemctl enable --now dataflow-backup.timer

cat <<EOF

Servidor preparado. Dominio: https://$DOMAIN
Falta:
  1. La clave de Anthropic (sin ella la API no arranca, DATAFLOW_AI_REQUIRED=true):
       read -rs KEY && printf %s "\$KEY" > $ROOT/secrets/ai_api_key
  2. En GitHub (Settings → Secrets and variables → Actions):
       variable DEPLOY_HOST = $PUBLIC_IP
       secreto  DEPLOY_SSH_KEY = la clave privada de DEPLOY_PUBLIC_KEY
       secreto  DEPLOY_KNOWN_HOSTS = salida de: ssh-keyscan -t ed25519 $PUBLIC_IP
  3. Lanzar el workflow «Deploy» (o fusionar en main).
EOF
