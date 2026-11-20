#!/bin/sh
# Copia de seguridad diaria (ADR-052): base de datos y archivos, juntos. La lanza el temporizador
# `dataflow-backup.timer`; a mano: `sudo systemctl start dataflow-backup.service`.
#
# Primero la base y después los archivos: los originales y versiones son inmutables, así que la
# copia de archivos siempre contiene todo lo que la base menciona.
#
# Fuera del servidor (recomendado): con rclone configurado para root y
# DATAFLOW_BACKUP_REMOTE=remoto:carpeta en /opt/dataflow/.env, cada copia se sube también allí.
set -eu

ROOT="${DATAFLOW_ROOT:-/opt/dataflow}"
DEST="$ROOT/backups"
KEEP_DAYS="${DATAFLOW_BACKUP_KEEP_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
COMPOSE_DIR="$ROOT/infrastructure/compose"

compose() {
  docker compose --env-file "$ROOT/.env" -f "$COMPOSE_DIR/compose.yaml" \
    -f "$COMPOSE_DIR/compose.production.yaml" "$@"
}

umask 077
compose exec -T postgres pg_dump -U dataflow -d dataflow --format=custom \
  > "$DEST/db-$STAMP.dump.partial"
mv "$DEST/db-$STAMP.dump.partial" "$DEST/db-$STAMP.dump"

docker run --rm -v dataflow_objects_data:/data:ro -v "$DEST:/backup" alpine:3.22 \
  tar czf "/backup/objects-$STAMP.tar.gz.partial" -C /data .
mv "$DEST/objects-$STAMP.tar.gz.partial" "$DEST/objects-$STAMP.tar.gz"

find "$DEST" -name 'db-*.dump' -mtime +"$KEEP_DAYS" -delete
find "$DEST" -name 'objects-*.tar.gz' -mtime +"$KEEP_DAYS" -delete
find "$DEST" -name '*.partial' -mtime +1 -delete

REMOTE="$(sed -n 's/^DATAFLOW_BACKUP_REMOTE=//p' "$ROOT/.env")"
if [ -n "$REMOTE" ] && command -v rclone >/dev/null 2>&1; then
  rclone copy "$DEST" "$REMOTE" --include "*-$STAMP.*"
fi
echo "Copia $STAMP en $DEST"
