#!/usr/bin/env bash
# ==============================================================================
# My Funding Bank — MongoDB Backup Script (local + S3-compatible upload)
# ==============================================================================
# Runs daily by cron in the `backup` container. Local-first, optional S3.
#
# Environment:
#   MONGO_URL, MONGO_DB_NAME
#   BACKUP_STORAGE=local|s3       (default local)
#   BACKUP_RETENTION_DAYS=30
#   BACKUP_ENCRYPT=true|false
#   BACKUP_ENCRYPT_PASSPHRASE
#   S3_ENDPOINT / S3_BUCKET / S3_REGION / S3_ACCESS_KEY / S3_SECRET_KEY / S3_PREFIX
# ==============================================================================
set -euo pipefail

BACKUP_DIR="/backups"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DB_NAME_VAL="${MONGO_DB_NAME:-mfb_prod}"
BACKUP_NAME="mfb_${DB_NAME_VAL}_${STAMP}"
DUMP_DIR="${BACKUP_DIR}/${BACKUP_NAME}"
ARCHIVE="${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
ENCRYPTED="${ARCHIVE}.gpg"
LOG_TAG="[mongo_backup]"

log() { echo "$(date -u +%FT%TZ) ${LOG_TAG} $*"; }

# ---- 1. Dump ----
log "Starting mongodump db=${DB_NAME_VAL}"
mkdir -p "$DUMP_DIR"
mongodump --uri="${MONGO_URL}" --db="${DB_NAME_VAL}" --out="${DUMP_DIR}" --gzip --quiet
log "Dump complete: $(du -sh "$DUMP_DIR" | cut -f1)"

# ---- 2. Compress ----
log "Compressing to ${ARCHIVE}"
tar -czf "$ARCHIVE" -C "$BACKUP_DIR" "$BACKUP_NAME"
rm -rf "$DUMP_DIR"
ARCHIVE_FINAL="$ARCHIVE"

# ---- 3. Optional GPG encryption ----
if [ "${BACKUP_ENCRYPT:-false}" = "true" ]; then
    if [ -z "${BACKUP_ENCRYPT_PASSPHRASE:-}" ]; then
        log "ERROR: BACKUP_ENCRYPT=true but BACKUP_ENCRYPT_PASSPHRASE empty"
        exit 2
    fi
    log "Encrypting with GPG symmetric AES256"
    gpg --batch --yes --passphrase "$BACKUP_ENCRYPT_PASSPHRASE" \
        --symmetric --cipher-algo AES256 -o "$ENCRYPTED" "$ARCHIVE"
    rm -f "$ARCHIVE"
    ARCHIVE_FINAL="$ENCRYPTED"
fi

SIZE=$(du -sh "$ARCHIVE_FINAL" | cut -f1)
log "Local backup ready: ${ARCHIVE_FINAL} (${SIZE})"

# ---- 4. Optional S3 upload ----
if [ "${BACKUP_STORAGE:-local}" = "s3" ]; then
    if [ -z "${S3_BUCKET:-}" ] || [ -z "${S3_ACCESS_KEY:-}" ] || [ -z "${S3_SECRET_KEY:-}" ]; then
        log "WARN: BACKUP_STORAGE=s3 but S3 credentials incomplete – keeping local only"
    else
        export AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY"
        export AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY"
        export AWS_DEFAULT_REGION="${S3_REGION:-us-east-1}"
        ENDPOINT_FLAG=""
        [ -n "${S3_ENDPOINT:-}" ] && ENDPOINT_FLAG="--endpoint-url ${S3_ENDPOINT}"
        S3_KEY="${S3_PREFIX:-mfb-backups}/$(basename "$ARCHIVE_FINAL")"
        log "Uploading to s3://${S3_BUCKET}/${S3_KEY}"
        aws ${ENDPOINT_FLAG} s3 cp "$ARCHIVE_FINAL" "s3://${S3_BUCKET}/${S3_KEY}" --only-show-errors
        log "S3 upload complete"
    fi
fi

# ---- 5. Local retention cleanup ----
log "Pruning local backups older than ${RETENTION_DAYS} days"
find "$BACKUP_DIR" -maxdepth 1 -type f -mtime +"$RETENTION_DAYS" \
     \( -name 'mfb_*.tar.gz' -o -name 'mfb_*.tar.gz.gpg' \) -print -delete || true

# ---- 6. Write manifest ----
MANIFEST="${BACKUP_DIR}/latest.json"
cat > "$MANIFEST" <<EOF
{
  "timestamp": "${STAMP}",
  "db": "${DB_NAME_VAL}",
  "file": "$(basename "$ARCHIVE_FINAL")",
  "size": "${SIZE}",
  "encrypted": ${BACKUP_ENCRYPT:-false},
  "storage": "${BACKUP_STORAGE:-local}"
}
EOF
log "Manifest written: ${MANIFEST}"
log "BACKUP OK"
