#!/usr/bin/env bash
# ==============================================================================
# My Funding Bank — Crash Recovery Runbook (executable helper)
# ==============================================================================
# Detects common failure modes and offers guided recovery steps.
# ==============================================================================
set -euo pipefail

COMPOSE="docker compose -f deploy/docker-compose.prod.yml --env-file .env.prod"

section() { printf "\n\033[1;36m== %s ==\033[0m\n" "$1"; }
ok()      { printf "  \033[32m✓\033[0m %s\n" "$1"; }
fail()    { printf "  \033[31m✗\033[0m %s\n" "$1"; }

section "1. Docker daemon"
if docker info >/dev/null 2>&1; then ok "Docker running"; else fail "Docker down → sudo systemctl start docker"; exit 1; fi

section "2. Container status"
$COMPOSE ps || fail "compose ps failed"

section "3. Mongo health"
if $COMPOSE exec -T mongo mongosh --quiet --eval "db.adminCommand('ping').ok" 2>/dev/null | grep -q 1; then
    ok "Mongo responding"
else
    fail "Mongo unreachable → attempting restart"
    $COMPOSE restart mongo
    sleep 8
fi

section "4. Backend health"
if curl -fsS http://localhost:8001/api/health/live >/dev/null 2>&1; then
    ok "Backend live"
else
    fail "Backend live check failing → tail logs"
    $COMPOSE logs --tail=200 backend || true
    read -rp "Restart backend? [y/N] " a
    [ "$a" = "y" ] && $COMPOSE restart backend
fi

section "5. Nginx / TLS"
if curl -fsSk https://localhost/api/health/live >/dev/null 2>&1; then
    ok "HTTPS front-door OK"
else
    fail "HTTPS failing – check certs in nginx_certs volume"
    $COMPOSE logs --tail=100 nginx || true
fi

section "6. Disk free"
df -h / | tail -1 | awk '{ if ($5+0 > 85) { print "  \033[31mDisk usage " $5 " – clean logs/backups!\033[0m" } else { print "  \033[32mDisk " $5 " used\033[0m" } }'

section "7. Recent finance alerts"
curl -fsS http://localhost:8001/api/health/ready 2>/dev/null | head -c 500 || true

echo
echo "Recovery script done. Refer /app/docs/deployment/ROLLBACK_PROCEDURE.md for full runbook."
