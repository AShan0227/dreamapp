#!/usr/bin/env bash
# DreamApp full backup — Postgres dump + MinIO mirror, optionally encrypted
# and pushed offsite.
#
# Designed for cron:
#   0 3 * * *  /Users/sylvan/.openclaw/workspace/projects/dreamapp/scripts/backup.sh
#
# Output goes to $BACKUP_DIR (default ./backups/YYYY-MM-DD/).
# Old backups beyond $RETENTION_DAYS (default 14) are pruned.
#
# Encryption (recommended for prod):
#   Set $BACKUP_GPG_RECIPIENT to a gpg key id/email — the pg dump and
#   knowledge snapshot tarball are encrypted with that key. Without it,
#   files are written in the clear (acceptable for dev only).
#
# Offsite (optional but you should):
#   Set $BACKUP_RCLONE_REMOTE to an rclone remote spec (e.g. "s3:dreamapp-backups").
#   The day's directory is rclone-pushed there after writing locally. Requires
#   rclone installed and configured on the host.

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BACKUP_ROOT="${BACKUP_DIR:-${PROJECT_DIR}/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

DATE=$(date -u +%Y-%m-%d)
TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)
OUT="${BACKUP_ROOT}/${DATE}"
mkdir -p "$OUT"

echo "==> backup target: $OUT"

# --- Postgres dump ------------------------------------------------------
echo "==> dumping postgres"
docker exec dreamapp-db-1 pg_dump \
  -U dreamapp \
  -d dreamapp \
  --format=custom \
  --no-owner \
  > "$OUT/dreamapp-${TS}.dump"

PG_BYTES=$(wc -c < "$OUT/dreamapp-${TS}.dump")
echo "    pg dump: $((PG_BYTES / 1024)) KB"

# --- MinIO mirror -------------------------------------------------------
# Uses mc inside the running minio container (saves installing mc on host).
echo "==> mirroring minio bucket"
docker exec dreamapp-minio-1 sh -c '
  command -v mc >/dev/null 2>&1 || {
    wget -qO /usr/local/bin/mc https://dl.min.io/client/mc/release/linux-amd64/mc
    chmod +x /usr/local/bin/mc
  }
  mc alias set local http://localhost:9000 dreamapp dreamapp_minio_secret >/dev/null 2>&1 || true
  mc mirror --overwrite --remove --quiet local/dreamapp-videos /data-mirror
' || echo "    minio mirror skipped (bucket empty or mc unavailable)"

# Pull the mirror out to host
docker cp dreamapp-minio-1:/data-mirror "$OUT/minio-mirror" 2>/dev/null || true
MINIO_BYTES=$(du -sk "$OUT/minio-mirror" 2>/dev/null | cut -f1 || echo 0)
echo "    minio mirror: ${MINIO_BYTES} KB"

# --- Knowledge JSONs ----------------------------------------------------
# These are source-of-truth for L1/L2 seeding; back them up too.
echo "==> snapshotting knowledge JSONs"
cp -r "${PROJECT_DIR}/backend/knowledge" "$OUT/knowledge"

# --- Manifest -----------------------------------------------------------
cat > "$OUT/MANIFEST.json" <<JSON
{
  "timestamp_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "pg_dump_bytes": ${PG_BYTES},
  "minio_kb": ${MINIO_BYTES},
  "host": "$(hostname)"
}
JSON

# --- Encryption (optional) ----------------------------------------------
if [ -n "${BACKUP_GPG_RECIPIENT:-}" ]; then
    if ! command -v gpg >/dev/null 2>&1; then
        echo "    WARN: BACKUP_GPG_RECIPIENT set but gpg not installed — skipping encryption"
    else
        echo "==> encrypting pg dump with gpg recipient ${BACKUP_GPG_RECIPIENT}"
        gpg --batch --yes --trust-model always \
            --output "$OUT/dreamapp-${TS}.dump.gpg" \
            --encrypt --recipient "$BACKUP_GPG_RECIPIENT" \
            "$OUT/dreamapp-${TS}.dump"
        rm "$OUT/dreamapp-${TS}.dump"
        echo "==> encrypting knowledge snapshot"
        tar -czf "$OUT/knowledge.tar.gz" -C "$OUT" knowledge
        gpg --batch --yes --trust-model always \
            --output "$OUT/knowledge.tar.gz.gpg" \
            --encrypt --recipient "$BACKUP_GPG_RECIPIENT" \
            "$OUT/knowledge.tar.gz"
        rm -rf "$OUT/knowledge" "$OUT/knowledge.tar.gz"
    fi
else
    echo "    NOTE: backups are unencrypted. Set BACKUP_GPG_RECIPIENT for production."
fi

# --- Offsite push (optional) --------------------------------------------
if [ -n "${BACKUP_RCLONE_REMOTE:-}" ]; then
    if ! command -v rclone >/dev/null 2>&1; then
        echo "    WARN: BACKUP_RCLONE_REMOTE set but rclone not installed — skipping offsite"
    else
        echo "==> pushing to ${BACKUP_RCLONE_REMOTE}/${DATE}"
        rclone copy "$OUT" "${BACKUP_RCLONE_REMOTE}/${DATE}" --quiet
    fi
else
    echo "    NOTE: backups are local-only. Set BACKUP_RCLONE_REMOTE for offsite copies."
fi

# --- Retention prune ----------------------------------------------------
echo "==> pruning backups older than ${RETENTION_DAYS} days"
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" -print -exec rm -rf {} \;

echo "==> done: $OUT"
