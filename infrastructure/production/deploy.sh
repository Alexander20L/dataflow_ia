#!/bin/sh
# Despliega una versión ya publicada en GHCR (ADR-052). Lo llama GitHub Actions por SSH como
# `deploy`, con la sesión de `docker login ghcr.io` abierta durante la llamada.
#
#   sh /opt/dataflow/infrastructure/production/deploy.sh ghcr.io/propietario/dataflow 1a2b3c4…
#
# Volver a una versión anterior: el mismo comando con su etiqueta (o el workflow «Deploy» con
# `version`). Las migraciones son aditivas, así que una API anterior funciona sobre el esquema
# nuevo salvo que la nota de la versión diga lo contrario.
set -eu

PREFIX="$1"
VERSION="$2"
ROOT="${DATAFLOW_ROOT:-/opt/dataflow}"
COMPOSE_DIR="$ROOT/infrastructure/compose"

case "$VERSION" in
  *[!0-9a-zA-Z._-]* | "") echo "Versión no válida: $VERSION" >&2; exit 1 ;;
esac

# Fija una variable en .env (de `deploy`, modo 600; root también lo lee).
set_env() {
  if grep -q "^$1=" "$ROOT/.env"; then
    sed -i "s|^$1=.*|$1=$2|" "$ROOT/.env"
  else
    echo "$1=$2" >> "$ROOT/.env"
  fi
}
PREVIOUS="$(sed -n 's/^DATAFLOW_VERSION=//p' "$ROOT/.env")"

compose() {
  docker compose --env-file "$ROOT/.env" -f "$COMPOSE_DIR/compose.yaml" \
    -f "$COMPOSE_DIR/compose.production.yaml" --profile full --profile public-databases "$@"
}

echo "== Imágenes $PREFIX-{api,web}:$VERSION"
DATAFLOW_IMAGE_API="$PREFIX-api" DATAFLOW_IMAGE_WEB="$PREFIX-web" DATAFLOW_VERSION="$VERSION" \
  compose pull --quiet api web
set_env DATAFLOW_IMAGE_API "$PREFIX-api"
set_env DATAFLOW_IMAGE_WEB "$PREFIX-web"
set_env DATAFLOW_VERSION "$VERSION"

echo "== Arranque (la API aplica las migraciones antes de escuchar)"
if ! compose up -d --no-build --remove-orphans --wait --wait-timeout 300; then
  echo "La versión $VERSION no arrancó." >&2
  compose ps >&2
  compose logs --tail 80 api worker >&2
  if [ -n "$PREVIOUS" ] && [ "$PREVIOUS" != "$VERSION" ]; then
    echo "Vuelvo a $PREVIOUS." >&2
    set_env DATAFLOW_VERSION "$PREVIOUS"
    compose up -d --no-build --remove-orphans --wait --wait-timeout 300 || true
  fi
  exit 1
fi

echo "== Cortafuegos de salida del conector"
sudo /usr/bin/systemctl restart dataflow-egress.service

echo "== Comprobación desde fuera (HTTPS → Caddy → web → API)"
DOMAIN="$(sed -n 's/^DATAFLOW_DOMAIN=//p' "$ROOT/.env")"
for _ in $(seq 1 30); do
  # Sin sesión, /auth/me responde 401: la cadena entera funciona.
  status="$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMAIN/api/v1/auth/me" || true)"
  [ "$status" = "401" ] && break
  sleep 5
done
if [ "$status" != "401" ]; then
  echo "https://$DOMAIN/api/v1/auth/me respondió «$status» (se esperaba 401)." >&2
  exit 1
fi

docker image prune -f >/dev/null
echo "Desplegada $VERSION en https://$DOMAIN"
