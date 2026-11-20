#!/bin/bash
# ==============================================================================
# My Funding Bank — backup container entrypoint
# ==============================================================================
# Installs cron, writes a cron job that runs mongo_backup.sh on BACKUP_CRON
# (default 02:00 UTC daily). cron does not pass the container's environment to
# jobs, so the needed variables are exported to a file the job sources first.
# ==============================================================================
set -euo pipefail

apt-get update -qq
apt-get install -y -qq --no-install-recommends cron gnupg awscli >/dev/null

export -p | grep -E ' (MONGO_|BACKUP_|S3_)[A-Z_]*=' > /etc/mfb_backup.env
chmod 600 /etc/mfb_backup.env

cat > /etc/cron.d/mfb_backup <<CRON
SHELL=/bin/bash
${BACKUP_CRON:-0 2 * * *} root source /etc/mfb_backup.env && /usr/local/bin/mongo_backup.sh >> /var/log/mfb_backup.log 2>&1
CRON
chmod 0644 /etc/cron.d/mfb_backup
touch /var/log/mfb_backup.log

echo "[backup] cron scheduled: ${BACKUP_CRON:-0 2 * * *} (UTC)"
cron
exec tail -F /var/log/mfb_backup.log
