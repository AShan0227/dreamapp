#!/usr/bin/env bash
# Install / update the DreamApp cron entries.
#
# Adds (or replaces if present):
#   - Daily backup at 03:00 local time
#
# Idempotent: re-running won't add duplicates. Uses a marker comment to
# identify our entries.

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
MARKER="# DREAMAPP-CRON v1"

# Build the desired crontab block
DESIRED=$(cat <<EOF
${MARKER}
0 3 * * * ${PROJECT_DIR}/scripts/backup.sh >> ${PROJECT_DIR}/backups/backup.log 2>&1
EOF
)

# Strip any prior block bearing our marker, then append the new one.
TMP=$(mktemp)
crontab -l 2>/dev/null | awk -v marker="$MARKER" '
  $0 == marker { skip=1; next }
  skip && /^[[:space:]]*$/ { skip=0; next }
  skip && /^[^#]/ { skip=0 }
  !skip { print }
' > "$TMP" || true

printf "%s\n" "$DESIRED" >> "$TMP"

crontab "$TMP"
rm -f "$TMP"

echo "Cron installed:"
crontab -l | grep -A1 "$MARKER"
