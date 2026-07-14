#!/usr/bin/env bash
# ==============================================================================
# My Funding Bank — MongoDB Restore Script
# ==============================================================================
# Usage:
#   mongo_restore.sh <backup-file>            # from local /backups
#   mongo_restore.sh s3://bucket/key.tar.gz   # streams from S3
#
# Optional env:
#   RESTORE_DB_NAME   (defaults to MONGO_DB_NAME)
#   BACKUP_ENCRYPT_PASSPHRASE  (required if encrypted .gpg)
#   DROP_BEFORE_RESTORE=true   (dangerous – drops target DB first)
# ==============================================================================
set -euo pipefail

SRC="${1:-}"
if [ -z "$SRC" ]; then
    echo "Usage: $0 <backup-file | s3://...>"
    exit 1
fi

TMP="/tmp/restore_$$"
mkdir -p "$TMP"
trap 'rm -rf "$TMP"' EXIT

# --- Fetch from S3 if needed ---
if [[ "$SRC" == s3://* ]]; then
    export AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY"
    export AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY"
    export AWS_DEFAULT_REGION="${S3_REGION:-us-east-1}"
    ENDPOINT_FLAG=""
    [ -n "${S3_ENDPOINT:-}" ] && ENDPOINT_FLAG="--endpoint-url ${S3_ENDPOINT}"
    LOCAL="${TMP}/$(basename "$SRC")"
    echo "[restore] Downloading $SRC → $LOCAL"
    aws ${ENDPOINT_FLAG} s3 cp "$SRC" "$LOCAL" --only-show-errors
    SRC="$LOCAL"
fi

[ -f "$SRC" ] || { echo "ERROR: $SRC not found"; exit 2; }

# --- Decrypt if needed ---
if [[ "$SRC" == *.gpg ]]; then
    : "${BACKUP_ENCRYPT_PASSPHRASE:?BACKUP_ENCRYPT_PASSPHRASE required for encrypted backup}"
    DEC="${TMP}/dec.tar.gz"
    echo "[restore] Decrypting"
    gpg --batch --yes --passphrase "$BACKUP_ENCRYPT_PASSPHRASE" -o "$DEC" -d "$SRC"
    SRC="$DEC"
fi

# --- Extract ---
echo "[restore] Extracting archive"
tar -xzf "$SRC" -C "$TMP"
DUMP_DIR=$(find "$TMP" -maxdepth 1 -type d -name 'mfb_*' | head -1)
[ -d "$DUMP_DIR" ] || { echo "ERROR: dump directory not found in archive"; exit 3; }

DB_NAME_VAL="${RESTORE_DB_NAME:-${MONGO_DB_NAME:-mfb_prod}}"

if [ "${DROP_BEFORE_RESTORE:-false}" = "true" ]; then
    echo "[restore] ⚠️  Dropping target DB '$DB_NAME_VAL' before restore"
    mongosh "$MONGO_URL" --quiet --eval "db.getSiblingDB('$DB_NAME_VAL').dropDatabase()"
fi

echo "[restore] Running mongorestore into '$DB_NAME_VAL'"
mongorestore --uri="$MONGO_URL" --gzip --nsInclude="${DB_NAME_VAL}.*" "$DUMP_DIR"

echo "[restore] ✅ Restore complete"
