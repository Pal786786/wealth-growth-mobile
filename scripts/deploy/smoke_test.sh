#!/usr/bin/env bash
# ==============================================================================
# My Funding Bank — Post-deploy smoke test
# ==============================================================================
# Fast (< 30s) verification that a freshly deployed environment is serving
# healthy responses on all critical endpoints.
#
# Usage: BASE_URL=https://app.myfundingbank.in bash scripts/deploy/smoke_test.sh
# ==============================================================================
set -euo pipefail

BASE="${BASE_URL:-http://localhost:8001}"
FAILED=0

check() {
    local name="$1" url="$2" expect="${3:-200}"
    local code
    code=$(curl -sk -o /dev/null -w "%{http_code}" -m 10 "$url" || echo 000)
    if [ "$code" = "$expect" ]; then
        printf "\033[32m✓\033[0m  %-40s [%s]\n" "$name" "$code"
    else
        printf "\033[31m✗\033[0m  %-40s [expected %s got %s]\n" "$name" "$expect" "$code"
        FAILED=$((FAILED+1))
    fi
}

echo "---- SMOKE TEST @ $BASE ----"
check "Liveness"               "$BASE/api/health/live"    200
check "Readiness"              "$BASE/api/health/ready"   200
check "Deep health"            "$BASE/api/health"         200
check "Prometheus metrics"     "$BASE/api/metrics"        200
check "Root API banner"        "$BASE/api/"                405
check "KYC public config"      "$BASE/api/kyc/config"      200
check "Market status"          "$BASE/api/market/status"   200

if [ "$FAILED" -gt 0 ]; then
    echo
    echo "💥  $FAILED smoke tests FAILED – rollback recommended."
    exit 1
fi
echo
echo "🚀  All smoke tests passed."
