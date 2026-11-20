#!/bin/sh
# Fase 32B (ADR-050): cortafuegos de salida del servicio `connector`.
#
# La red `egress` de Compose (puente `df-egress`) es la única salida del conector. Docker por sí
# solo deja salir de ella hacia la red local del anfitrión y hacia los metadatos de la nube; estas
# reglas en la cadena DOCKER-USER lo impiden: el conector sólo llega a direcciones públicas.
# Es la capa que cubre lo que la regla `database-destination-v1` no ve (redirecciones del
# protocolo, errores de libpq).
#
# Uso, en el anfitrión Linux (root), después de `docker compose ... up` (la red debe existir):
#   sh infrastructure/compose/egress-firewall.sh          # aplica (idempotente)
#   sh infrastructure/compose/egress-firewall.sh --remove # quita las reglas
#
# Docker Desktop (Windows/macOS) no expone estas cadenas: allí sólo protege la regla de la
# aplicación. En la nube, aplicar lo mismo con el grupo de seguridad o la política de red.
set -eu

BRIDGE="${DATAFLOW_EGRESS_BRIDGE:-df-egress}"
TAG="dataflow-egress"
RANGES="0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 169.254.0.0/16 172.16.0.0/12 \
192.0.0.0/24 192.0.2.0/24 192.168.0.0/16 198.18.0.0/15 198.51.100.0/24 203.0.113.0/24 \
224.0.0.0/4 240.0.0.0/4"

# Borra todas las reglas con nuestra etiqueta de una herramienta (iptables o ip6tables).
remove_from() {
  tool="$1"
  command -v "$tool" >/dev/null 2>&1 || return 0
  "$tool" -S DOCKER-USER >/dev/null 2>&1 || return 0
  "$tool" -S DOCKER-USER | grep -- "--comment $TAG" | sed 's/^-A /-D /' | while read -r rule; do
    # shellcheck disable=SC2086
    "$tool" $rule
  done
}

remove_from iptables
remove_from ip6tables
if [ "${1:-}" = "--remove" ]; then
  echo "Reglas de $TAG eliminadas."
  exit 0
fi

if ! ip link show "$BRIDGE" >/dev/null 2>&1; then
  echo "No existe el puente $BRIDGE: arranca antes Compose con --profile public-databases." >&2
  exit 1
fi

for range in $RANGES; do
  iptables -I DOCKER-USER -i "$BRIDGE" -d "$range" -m comment --comment "$TAG" -j DROP
done
# La red `egress` no tiene IPv6 (Compose no lo activa); si se activara, se corta entero.
if command -v ip6tables >/dev/null 2>&1 && ip6tables -S DOCKER-USER >/dev/null 2>&1; then
  ip6tables -I DOCKER-USER -i "$BRIDGE" -m comment --comment "$TAG" -j DROP
fi
echo "Salida de $BRIDGE limitada a direcciones públicas."
