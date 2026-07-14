"""Sprint 14.1.5 — ProviderManager refresh loop diagnostic surface.

Verifies:
  1. GET /api/market_providers/status exposes the three new fields:
       - refresh_running (bool, True on healthy backend)
       - refresh_healthy (bool, True on healthy backend)
       - seconds_since_last_refresh (float, < refresh_interval_sec * 1.5)
  2. refresh_interval_sec still returned (no regression)
  3. Loop liveness: seconds_since_last_refresh increases monotonically over
     a short window (loop is running, not frozen)
  4. Manual POST /api/market_providers/refresh works — provider=mock and
     seconds_since_last_refresh < 3s afterwards
  5. Cache freshness — market_price_cache.XAUUSD.updated_at newer than 60s
     and provider=mock
"""
from __future__ import annotations
import os
import time

import pytest
import requests


BASE_URL = os.environ.get("EXPO_BACKEND_URL", "https://wealth-growth-mobile.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@mfb.in"
ADMIN_PASSWORD = "Admin@MFB2026"


@pytest.fixture(scope="module")
def admin_token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/admin/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok, "no token in admin login response"
    return tok


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ------------------------------------------------------------------
# 1. New diagnostic fields present in /status
# ------------------------------------------------------------------
class TestStatusDiagnosticFields:
    def test_status_returns_200(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/market_providers/status", headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text

    def test_status_exposes_refresh_running(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/market_providers/status", headers=auth_headers, timeout=15)
        d = r.json()
        assert "refresh_running" in d, f"missing refresh_running; keys={sorted(d.keys())}"
        assert isinstance(d["refresh_running"], bool), f"refresh_running not bool: {type(d['refresh_running'])}"
        assert d["refresh_running"] is True, "refresh loop task must be alive on a healthy backend"

    def test_status_exposes_refresh_healthy(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/market_providers/status", headers=auth_headers, timeout=15)
        d = r.json()
        assert "refresh_healthy" in d, f"missing refresh_healthy; keys={sorted(d.keys())}"
        assert isinstance(d["refresh_healthy"], bool)
        assert d["refresh_healthy"] is True, (
            f"refresh_healthy False — seconds_since_last_refresh="
            f"{d.get('seconds_since_last_refresh')}, interval={d.get('refresh_interval_sec')}"
        )

    def test_status_exposes_seconds_since_last_refresh(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/market_providers/status", headers=auth_headers, timeout=15)
        d = r.json()
        assert "seconds_since_last_refresh" in d
        val = d["seconds_since_last_refresh"]
        assert val is not None, "seconds_since_last_refresh is None on live backend"
        assert isinstance(val, (int, float))
        interval = d.get("refresh_interval_sec", 60)
        assert val < interval * 1.5, (
            f"seconds_since_last_refresh={val} exceeds 1.5x interval ({interval * 1.5})"
        )
        assert val >= 0

    def test_refresh_interval_sec_still_returned(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/market_providers/status", headers=auth_headers, timeout=15)
        d = r.json()
        assert "refresh_interval_sec" in d, "regression: refresh_interval_sec missing"
        assert isinstance(d["refresh_interval_sec"], int)
        assert d["refresh_interval_sec"] == 60, f"expected default 60s, got {d['refresh_interval_sec']}"


# ------------------------------------------------------------------
# 2. Loop liveness — sleep and confirm counter changes
# ------------------------------------------------------------------
class TestLoopLiveness:
    def test_seconds_since_last_refresh_advances_or_resets(self, auth_headers):
        """Between two /status calls seconds_since_last_refresh must EITHER
        increase (loop hasn't fired between the two reads) OR reset to a
        smaller value (loop fired between the two reads). Both prove the
        counter is live."""
        r1 = requests.get(f"{BASE_URL}/api/market_providers/status", headers=auth_headers, timeout=15).json()
        v1 = r1["seconds_since_last_refresh"]
        t1 = r1["last_refresh_at"]
        time.sleep(8)
        r2 = requests.get(f"{BASE_URL}/api/market_providers/status", headers=auth_headers, timeout=15).json()
        v2 = r2["seconds_since_last_refresh"]
        t2 = r2["last_refresh_at"]

        if t1 == t2:
            # Loop did not fire — counter must have increased by ~8s
            assert v2 > v1, f"counter did not advance: {v1} → {v2}"
            assert (v2 - v1) >= 5, f"counter advanced by only {v2 - v1}s over 8s wall clock"
        else:
            # Loop fired between the two reads — counter must have reset
            assert v2 < v1, f"loop fired but counter didn't reset: {v1} → {v2}"

    def test_loop_fires_within_cadence(self, auth_headers):
        """Over ~65s window, last_refresh_at must change at least once,
        proving the background task actually runs on cadence."""
        r0 = requests.get(f"{BASE_URL}/api/market_providers/status", headers=auth_headers, timeout=15).json()
        t0 = r0["last_refresh_at"]
        interval = r0["refresh_interval_sec"]
        deadline = time.time() + interval + 10  # +10s slack
        seen_new_refresh = False
        min_seconds_since_last = float("inf")
        while time.time() < deadline:
            time.sleep(5)
            r = requests.get(f"{BASE_URL}/api/market_providers/status", headers=auth_headers, timeout=15).json()
            if r["last_refresh_at"] != t0:
                seen_new_refresh = True
                min_seconds_since_last = min(min_seconds_since_last, r["seconds_since_last_refresh"])
                break
        assert seen_new_refresh, (
            f"last_refresh_at did not change over {interval + 10}s — refresh loop appears stalled"
        )
        assert min_seconds_since_last < 10, (
            f"after loop fired, seconds_since_last_refresh={min_seconds_since_last} (expected <10)"
        )


# ------------------------------------------------------------------
# 3. Manual refresh endpoint works
# ------------------------------------------------------------------
class TestManualRefresh:
    def test_manual_refresh_returns_200_and_mock(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/market_providers/refresh", headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("provider") == "mock", f"expected provider=mock, got {d}"
        # accepted should be > 0 (universe size 20)
        assert d.get("count", 0) >= 20 or d.get("accepted", 0) >= 20, (
            f"expected count/accepted >=20, got {d}"
        )

    def test_status_after_manual_refresh_is_fresh(self, auth_headers):
        requests.post(f"{BASE_URL}/api/market_providers/refresh", headers=auth_headers, timeout=30)
        time.sleep(0.5)
        r = requests.get(f"{BASE_URL}/api/market_providers/status", headers=auth_headers, timeout=15).json()
        assert r["seconds_since_last_refresh"] is not None
        assert r["seconds_since_last_refresh"] < 3, (
            f"after manual refresh, seconds_since_last_refresh={r['seconds_since_last_refresh']}"
        )
        assert r["refresh_healthy"] is True


# ------------------------------------------------------------------
# 4. Cache freshness — XAUUSD in Mongo cache
# ------------------------------------------------------------------
class TestCacheFreshness:
    def test_xauusd_cache_recent_and_mock(self, auth_headers):
        # Force a fresh write first
        requests.post(f"{BASE_URL}/api/market_providers/refresh", headers=auth_headers, timeout=30)
        time.sleep(0.5)
        # Read via /status → market_status + cache stats
        r = requests.get(f"{BASE_URL}/api/market_providers/status", headers=auth_headers, timeout=15).json()
        cache = r.get("cache", {})
        assert cache.get("total_symbols_cached", 0) >= 20
        newest = cache.get("newest_age_sec")
        assert newest is not None
        assert newest <= 60, f"newest cached quote is {newest}s old (expected <=60s)"
        assert r.get("last_active_provider") == "mock"

    def test_xauusd_cache_via_mongo(self):
        """Direct Mongo read — matches user's original reproduction path."""
        try:
            from motor.motor_asyncio import AsyncIOMotorClient  # noqa: F401
        except ImportError:
            pytest.skip("motor not installed in test env")
        import asyncio
        from pymongo import MongoClient

        # Read backend env
        env = {}
        with open("/app/backend/.env") as fh:
            for line in fh:
                if "=" in line and not line.strip().startswith("#"):
                    k, _, v = line.strip().partition("=")
                    env[k] = v.strip().strip('"')
        client = MongoClient(env["MONGO_URL"])
        try:
            db = client[env["DB_NAME"]]
            doc = db["market_price_cache"].find_one({"_id": "XAUUSD"}) or \
                  db["market_price_cache"].find_one({"symbol": "XAUUSD"})
            assert doc, "no XAUUSD document in market_price_cache"
            # updated_at may be datetime or string
            from datetime import datetime, timezone
            ua = doc.get("updated_at")
            if isinstance(ua, str):
                ua = datetime.fromisoformat(ua.replace("Z", "+00:00"))
            assert ua is not None, "updated_at missing on XAUUSD doc"
            if ua.tzinfo is None:
                ua = ua.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ua).total_seconds()
            assert age < 90, f"XAUUSD cache is {age:.1f}s old (expected <90s)"
            # provider label
            prov = (doc.get("provider") or doc.get("source") or "").lower()
            assert "mock" in prov, f"expected provider=mock on XAUUSD, got {prov} — full doc keys: {list(doc.keys())}"
        finally:
            client.close()
        asyncio.get_event_loop  # noqa: silence unused import warning


# ------------------------------------------------------------------
# 5. No regression: previously-returned fields still present
# ------------------------------------------------------------------
class TestNoRegression:
    def test_all_previous_fields_still_present(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/market_providers/status", headers=auth_headers, timeout=15).json()
        expected = {
            "active_provider", "last_active_provider", "last_refresh_at",
            "last_refresh_error", "refresh_interval_sec", "auto_fallback",
            "manual_provider", "universe", "cache", "market_status", "providers",
        }
        missing = expected - set(r.keys())
        assert not missing, f"regression — missing fields: {missing}"
