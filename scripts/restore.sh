#!/usr/bin/env bash
# DreamApp restore — pg_restore + MinIO mirror push.
#
# WARNING: drops and recreates the dreamapp database.
#
# Usage:
#   scripts/restore.sh ./backups/2026-04-16

set -euo pipefail

if [ -z "${1:-}" ]; then
  echo "Usage: $0 <backup-dir>" >&2
  echo "  e.g. $0 ./backups/2026-04-16" >&2
  exit 2
fi

DIR="$1"
[ -d "$DIR" ] || { echo "Backup dir not found: $DIR" >&2; exit 2; }

DUMP=$(ls "$DIR"/dreamapp-*.dump 2>/dev/null | head -1 || true)
[ -n "$DUMP" ] || { echo "No pg dump in $DIR" >&2; exit 2; }

echo "==> restoring from: $DIR"
read -p "This will OVERWRITE the live dreamapp database. Continue? [y/N] " ok
[ "$ok" = "y" ] || [ "$ok" = "Y" ] || { echo "aborted"; exit 1; }

# --- Postgres ------------------------------------------------------------
echo "==> dropping & recreating dreamapp database"
docker exec dreamapp-db-1 psql -U dreamapp -d postgres -c \
  "DROP DATABASE IF EXISTS dreamapp WITH (FORCE);"
docker exec dreamapp-db-1 psql -U dreamapp -d postgres -c \
  "CREATE DATABASE dreamapp OWNER dreamapp;"

echo "==> piping pg dump into pg_restore"
docker cp "$DUMP" dreamapp-db-1:/tmp/restore.dump
docker exec dreamapp-db-1 pg_restore \
  -U dreamapp -d dreamapp --no-owner /tmp/restore.dump
docker exec dreamapp-db-1 rm -f /tmp/restore.dump

# --- MinIO ---------------------------------------------------------------
if [ -d "$DIR/minio-mirror" ]; then
  echo "==> restoring MinIO bucket from mirror"
  docker cp "$DIR/minio-mirror" dreamapp-minio-1:/data-restore
  docker exec dreamapp-minio-1 sh -c '
    command -v mc >/dev/null 2>&1 || {
      wget -qO /usr/local/bin/mc https://dl.min.io/client/mc/release/linux-amd64/mc
      chmod +x /usr/local/bin/mc
    }
    mc alias set local http://localhost:9000 dreamapp dreamapp_minio_secret >/dev/null 2>&1 || true
    mc mb --ignore-existing local/dreamapp-videos
    mc mirror --overwrite --quiet /data-restore local/dreamapp-videos
  '
fi

# --- Restart backend so the in-process embedding cache invalidates ------
echo "==> restarting backend"
docker restart dreamapp-backend-1

echo "==> restore complete"
