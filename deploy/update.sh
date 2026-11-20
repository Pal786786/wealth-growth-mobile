#!/usr/bin/env bash
# ==============================================================================
# My Funding Bank — pull latest code from GitHub and redeploy
# ==============================================================================
#     bash deploy/update.sh            # update from the current branch
#     bash deploy/update.sh main       # switch to / update a specific branch
#
# Rebuilds only what changed. MongoDB data and SSL certificates are kept
# (they live in Docker volumes). Takes a backup before rebuilding.
# ==============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE=".env.prod"
DC="docker compose -f deploy/docker-compose.prod.yml --env-file $ENV_FILE"
BRANCH="${1:-$(git rev-parse --abbrev-ref HEAD)}"

echo "==> Backup before update"
docker exec mfb_backup bash -c 'source /etc/mfb_backup.env && /usr/local/bin/mongo_backup.sh' \
    || echo "   (backup skipped — backup container not running yet)"

echo "==> Pulling $BRANCH"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"
git log -1 --oneline

echo "==> Rebuilding + restarting"
$DC up -d --build --remove-orphans

echo "==> Waiting for backend health"
for i in $(seq 1 40); do
    status=$(docker inspect -f '{{.State.Health.Status}}' mfb_backend 2>/dev/null || echo starting)
    [ "$status" = "healthy" ] && { echo "   backend healthy"; break; }
    sleep 5
done
[ "${status:-}" = "healthy" ] || { echo "WARNING: backend not healthy. Check: $DC logs --tail=100 backend"; }

docker image prune -f >/dev/null
$DC ps
echo "Update complete."
