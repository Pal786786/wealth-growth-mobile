"""Sprint 7.5 P0 — TwelveData Batch + Exponential Backoff Backend Validation

Covers the NEW requirements from the P0 fix that go beyond iter28:
  (a) Status shape: refresh_interval_sec=60, cache.ttl_sec=60,
      cache.fresh_max_sec=30, cache.stale_max_sec=300, per-provider `backoff`
      sub-object, top-level `market_status` object with correct keys/state.
  (b) Backoff triggers only on 429: invalid TD key increments circuit
      failures but NOT backoff.total_429_events / backoff.active.
  (c) Consumer reads still work: AI signal entry ≈ cached BTCUSD price.
  (d) Universe scope: shrink → restore → cache returns to 20 symbols.
  (e) Config persistence & migration clamps (5..300).
  (f) Full regression sanity of downstream endpoints.
"""
from __future__ import annotations
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or
            os.environ.get("EXPO_BACKEND_URL", "").rstrip("/"))
if not BASE_URL:
    raise RuntimeError("EXPO_PUBLIC_BACKEND_URL (or EXPO_BACKEND_URL) must be set")

ADMIN_EMAIL = "admin@mfb.in"
ADMIN_PASSWORD = "Admin@MFB2026"

EXPECTED_UNIVERSE = {
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    "XAUUSD", "XAGUSD",
    "BTCUSD", "ETHUSD",
    "US30", "NAS100", "SPX500", "GER40", "UK100", "IND50",
    "USOIL", "UKOIL", "NATGAS",
}


# ---------------- fixtures ---------------- #

@pytest.fixture(scope="session")
def admin_headers() -> dict:
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def user_headers() -> dict:
    for path, body in [
        ("/api/auth/login", {"identifier": "demo@mfb.in", "password": "demo1234"}),
        ("/api/auth/login", {"identifier": "9999999999", "password": "demo1234"}),
    ]:
        try:
            r = requests.post(f"{BASE_URL}{path}", json=body, timeout=10)
            if r.status_code == 200:
                tok = r.json().get("token") or r.json().get("access_token")
                if tok:
                    return {"Authorization": f"Bearer {tok}",
                            "Content-Type": "application/json"}
        except Exception:
            continue
    email = f"TEST_p0_{int(time.time())}@mfb.in"
    r = requests.post(f"{BASE_URL}/api/auth/signup",
                      json={"email": email, "password": "Test@1234", "name": "p0"},
                      timeout=10)
    tok = None
    if r.status_code in (200, 201):
        tok = r.json().get("token") or r.json().get("access_token")
    if not tok:
        pytest.skip("could not obtain user token")
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _get_status(headers) -> dict:
    r = requests.get(f"{BASE_URL}/api/market_providers/status",
                     headers=headers, timeout=15)
    assert r.status_code == 200, r.text[:200]
    return r.json()


# ---------------- (a) Status shape validation ---------------- #

class TestStatusShape:
    """P0 requirement: 60s refresh, cache thresholds, backoff & market_status."""

    def test_refresh_interval_is_60(self, admin_headers):
        j = _get_status(admin_headers)
        assert j["refresh_interval_sec"] == 60, \
            f"expected refresh_interval_sec=60, got {j['refresh_interval_sec']}"

    def test_cache_thresholds(self, admin_headers):
        j = _get_status(admin_headers)
        c = j["cache"]
        assert c["ttl_sec"] == 60, c
        assert c["fresh_max_sec"] == 30, c
        assert c["stale_max_sec"] == 300, c

    def test_every_provider_has_backoff_subobject(self, admin_headers):
        j = _get_status(admin_headers)
        required_keys = {"active", "step", "remaining_sec", "until",
                         "last_429_at", "total_429_events", "schedule"}
        for p in j["providers"]:
            bo = p.get("backoff")
            assert bo is not None, f"{p['name']} has no backoff sub-object"
            missing = required_keys - set(bo.keys())
            assert not missing, f"{p['name']}.backoff missing keys {missing}"
            # TwelveData is the only provider with an active exp-backoff
            # schedule per spec (30/60/120/240/600). Others expose the key
            # for uniformity but may be empty.
            if p["name"] == "twelvedata":
                assert bo["schedule"] == [30, 60, 120, 240, 600], \
                    f"twelvedata backoff.schedule = {bo['schedule']}"

    def test_market_status_shape(self, admin_headers):
        j = _get_status(admin_headers)
        ms = j.get("market_status")
        assert ms is not None
        for k in ["state", "tint", "reason", "newest_age_sec",
                  "oldest_age_sec", "last_real_success_at",
                  "last_real_provider"]:
            assert k in ms, f"market_status missing {k}"
        assert ms["state"] in {"LIVE", "STALE", "FALLBACK"}
        assert ms["tint"] in {"green", "amber", "blue"}

    def test_no_real_keys_state_is_fallback(self, admin_headers):
        # Ensure keys are clear
        for prov in ("twelvedata", "alphavantage"):
            requests.put(f"{BASE_URL}/api/market_providers/api-key",
                         json={"provider": prov, "key": ""},
                         headers=admin_headers, timeout=10)
        # Trigger a refresh so market_status is derived from a mock refresh
        requests.post(f"{BASE_URL}/api/market_providers/refresh",
                      headers=admin_headers, timeout=30)
        j = _get_status(admin_headers)
        assert j["active_provider"] == "mock", j["active_provider"]
        assert j["market_status"]["state"] == "FALLBACK", j["market_status"]
        assert j["market_status"]["tint"] == "blue"


# ---------------- (b) Backoff triggers ONLY on 429 ---------------- #

class TestBackoffOn429Only:
    """Invalid TD key → not-configured/error → circuit++ but backoff must NOT
    activate and total_429_events must remain 0."""

    def test_invalid_td_key_does_not_activate_backoff(self, admin_headers):
        # Read baseline
        j0 = _get_status(admin_headers)
        td0 = next(p for p in j0["providers"] if p["name"] == "twelvedata")
        base_429_events = td0["backoff"]["total_429_events"]

        # Set fake key
        r = requests.put(f"{BASE_URL}/api/market_providers/api-key",
                         json={"provider": "twelvedata",
                               "key": "FAKE_TEST_KEY_backoff_check"},
                         headers=admin_headers, timeout=10)
        assert r.status_code == 200

        try:
            # Trigger a refresh — should fall through to mock
            rr = requests.post(f"{BASE_URL}/api/market_providers/refresh",
                               headers=admin_headers, timeout=30)
            assert rr.status_code == 200
            body = rr.json()
            assert body.get("provider") == "mock", body
            assert body.get("count") == 20, body

            # Give the manager a moment to persist stats
            time.sleep(0.5)
            j = _get_status(admin_headers)
            td = next(p for p in j["providers"] if p["name"] == "twelvedata")

            # 429 counters must NOT have moved
            assert td["backoff"]["active"] is False, td["backoff"]
            assert td["backoff"]["total_429_events"] == base_429_events, \
                td["backoff"]
            assert td["backoff"]["remaining_sec"] == 0
            assert td["backoff"]["step"] == 0
            # But the failure did register somewhere: either circuit
            # consecutive_failures OR stats.failed_requests. The invalid-key
            # case usually surfaces as JSON "error" → counts as network-ish
            # failure through the circuit. Accept either signal so we don't
            # over-constrain the implementation.
            circ_fail = td["circuit"]["consecutive_failures"]
            stat_fail = td.get("failed_requests", 0)
            assert (circ_fail >= 1) or (stat_fail >= 1), \
                f"expected some failure signal, got circuit={td['circuit']}, "\
                f"failed_requests={stat_fail}"
        finally:
            # Clear the fake key (mandatory cleanup)
            requests.put(f"{BASE_URL}/api/market_providers/api-key",
                         json={"provider": "twelvedata", "key": ""},
                         headers=admin_headers, timeout=10)


# ---------------- (c) Consumer reads still work ---------------- #

class TestConsumerReadsStillWork:
    def test_ai_signal_entry_matches_cache(self, admin_headers, user_headers):
        # Fresh refresh
        requests.post(f"{BASE_URL}/api/market_providers/refresh",
                      headers=admin_headers, timeout=30)
        q = requests.get(f"{BASE_URL}/api/market_providers/quote/BTCUSD",
                         headers=admin_headers, timeout=10).json()
        cache_price = float(q["price"])
        r = requests.get(f"{BASE_URL}/api/ai/signals/BTCUSD?with_ai=false",
                         headers=user_headers, timeout=20)
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        entry = j.get("entry") or j.get("signal", {}).get("entry")
        assert entry is not None, f"no entry in signal: {j}"
        diff_pct = abs(float(entry) - cache_price) / cache_price * 100
        assert diff_pct <= 0.5, \
            f"entry {entry} diverges from cache {cache_price} by {diff_pct:.2f}%"


# ---------------- (d) Universe scope after shrink/restore ---------------- #

class TestUniverseScope:
    def test_shrink_restore_returns_to_20(self, admin_headers):
        try:
            r = requests.put(f"{BASE_URL}/api/market_providers/universe",
                             json={"symbols": ["EURUSD", "BTCUSD"]},
                             headers=admin_headers, timeout=10)
            assert r.status_code == 200
            requests.post(f"{BASE_URL}/api/market_providers/refresh",
                          headers=admin_headers, timeout=30)
            j = _get_status(admin_headers)
            assert set(j["universe"]) == {"EURUSD", "BTCUSD"}
        finally:
            # Restore
            r = requests.put(f"{BASE_URL}/api/market_providers/universe",
                             json={"symbols": sorted(list(EXPECTED_UNIVERSE))},
                             headers=admin_headers, timeout=10)
            assert r.status_code == 200
            requests.post(f"{BASE_URL}/api/market_providers/refresh",
                          headers=admin_headers, timeout=30)
        # Poll for eventual cache repopulation to 20
        got_20 = False
        for _ in range(10):
            j = _get_status(admin_headers)
            if j["cache"].get("total_symbols_cached", 0) >= 20 and \
               set(j["universe"]) == EXPECTED_UNIVERSE:
                got_20 = True
                break
            time.sleep(1)
        assert got_20, f"cache did not return to 20: {j['cache']}"


# ---------------- (e) Config persistence & migration ---------------- #

class TestRefreshIntervalClamps:
    def test_lower_clamp_is_5(self, admin_headers):
        try:
            r = requests.put(f"{BASE_URL}/api/market_providers/refresh-interval",
                             json={"seconds": 1}, headers=admin_headers, timeout=10)
            assert r.status_code == 200
            j = _get_status(admin_headers)
            assert j["refresh_interval_sec"] == 5, \
                f"expected lower clamp 5, got {j['refresh_interval_sec']}"
        finally:
            # restore to 60
            requests.put(f"{BASE_URL}/api/market_providers/refresh-interval",
                         json={"seconds": 60}, headers=admin_headers, timeout=10)

    def test_upper_clamp_is_300(self, admin_headers):
        try:
            r = requests.put(f"{BASE_URL}/api/market_providers/refresh-interval",
                             json={"seconds": 9999}, headers=admin_headers, timeout=10)
            assert r.status_code == 200
            j = _get_status(admin_headers)
            assert j["refresh_interval_sec"] == 300, \
                f"expected upper clamp 300, got {j['refresh_interval_sec']}"
        finally:
            requests.put(f"{BASE_URL}/api/market_providers/refresh-interval",
                         json={"seconds": 60}, headers=admin_headers, timeout=10)

    def test_normal_value_persists(self, admin_headers):
        try:
            r = requests.put(f"{BASE_URL}/api/market_providers/refresh-interval",
                             json={"seconds": 90}, headers=admin_headers, timeout=10)
            assert r.status_code == 200
            j = _get_status(admin_headers)
            assert j["refresh_interval_sec"] == 90
        finally:
            requests.put(f"{BASE_URL}/api/market_providers/refresh-interval",
                         json={"seconds": 60}, headers=admin_headers, timeout=10)


# ---------------- (f) Full regression sanity ---------------- #

REGRESSION_PATHS = [
    "/api/wallet",
    "/api/notifications",
    "/api/forex/symbols",
    "/api/forex/balance",
    "/api/market/dashboard",
    "/api/copy_trading/meta",
    "/api/ai/meta",
    "/api/ai/signals?limit=5",
    "/api/ai/watchlist",
    "/api/auth/me",
]


class TestRegression:
    @pytest.mark.parametrize("path", REGRESSION_PATHS)
    def test_user_paths_200(self, user_headers, path):
        r = requests.get(f"{BASE_URL}{path}", headers=user_headers, timeout=15)
        assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"

    def test_copy_trading_admin_system_health(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/copy_trading/admin/system-health",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text[:200]

    def test_copy_trading_trader_marcus(self, user_headers):
        r = requests.get(f"{BASE_URL}/api/copy_trading/traders/marcus_wolfe",
                         headers=user_headers, timeout=15)
        assert r.status_code == 200, r.text[:200]
