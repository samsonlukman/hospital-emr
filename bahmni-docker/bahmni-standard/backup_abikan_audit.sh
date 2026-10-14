#!/bin/sh
# Copy the Hospital EMR audit, notification, messaging, and staff-log SQLite files out of their
# shared persistent Docker volume.
# Does not dump OpenMRS, OpenELIS, Odoo, or other clinical databases.
# Run from bahmni-docker/bahmni-standard. Destination directory is created if needed.

set -eu

ROOT="${1:-./backup-artifacts/abikan-audit}"
STAMP=$(date -u +'%Y-%m-%d_%H-%M-%S')
DEST="$ROOT/$STAMP"
mkdir -p "$DEST"

VOLUME="${ABIKAN_AUDIT_VOLUME:-bahmni-standard_abikan-admin-audit}"

docker run --rm \
  -v "$VOLUME:/var/lib/abikan:ro" \
  -v "$(cd "$DEST" && pwd):/backup" \
  alpine:3.20 \
  sh -c 'cp -a /var/lib/abikan/. /backup/ && ls -l /backup'

echo "Wrote Hospital EMR audit, notification, messaging, and staff-log copy to $DEST"
