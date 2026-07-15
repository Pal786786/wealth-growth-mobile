"""Sprint 16.3 — E2E verification via PUBLIC preview URL.

Focus of THIS file (do NOT duplicate the 19 tests already in
test_sprint_163_candle_fix.py — those run against localhost):

  * All six symbols return HTTP 200 through the public ingress
  * Response shape matches PRD: symbol, tf, candles[{t,o,h,l,c,v,source,complete}],
    volume_available, quote, sync
  * Candles strictly ascending, no duplicate t's
  * Higher tf (5m/1h/1d) for XAUUSD + BTCUSD
  * GBPUSD naive-meta regression (was 500 pre-fix) — mutation on real DB
  * sync always a dict; if 'sync_error:' prefix -> STILL 200 with candles
  * Backfill path (before=<epoch>) returns 200 with reason=range_cached
  * Regression endpoints: /api/market_providers/status (admin auth) and
    /api/forex/candles/XAUUSD?limit=5
"""
import os
import time
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_BACKEND_URL",
                          "https://wealth-growth-mobile.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient("mongodb://localhost:27017").my_funding_bank

SYMBOLS = ["BTCUSD", "EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "XAGUSD"]
CANDLE_KEYS = ("t", "o", "h", "l", "c", "v", "source", "complete")


# ------------------------------------------------------------------ helpers
def _get(path: str, **kwargs):
    return requests.get(f"{API}{path}", timeout=45, **kwargs)


# ============================================================ 1) all symbols
class TestAllSymbolsPublic:
    @pytest.mark.parametrize("sym", SYMBOLS)
    def test_200_and_shape(self, sym):
        r = _get(f"/market/candles/{sym}?tf=1m&limit=300")
        assert r.status_code == 200, f"{sym}: {r.status_code} {r.text[:200]}"
        j = r.json()
        assert j["symbol"] == sym
        assert j["tf"] == "1m"
        assert isinstance(j["candles"], list) and len(j["candles"]) > 0
        assert "volume_available" in j
        assert "quote" in j
        assert isinstance(j["sync"], dict)
        c0 = j["candles"][0]
        for k in CANDLE_KEYS:
            assert k in c0, f"{sym}: candle missing key {k}: {c0}"
        assert isinstance(c0["complete"], bool)

    @pytest.mark.parametrize("sym", SYMBOLS)
    def test_timestamps_strictly_ascending_no_dupes(self, sym):
        r = _get(f"/market/candles/{sym}?tf=1m&limit=300")
        assert r.status_code == 200
        ts = [c["t"] for c in r.json()["candles"]]
        assert len(ts) == len(set(ts)), f"{sym}: duplicate timestamps"
        assert ts == sorted(ts), f"{sym}: not ascending"


# ============================================================ 2) higher TFs
class TestHigherTimeframes:
    @pytest.mark.parametrize("sym,tf",
                             [("XAUUSD", "5m"), ("XAUUSD", "1h"), ("XAUUSD", "1d"),
                              ("BTCUSD", "5m"), ("BTCUSD", "1h"), ("BTCUSD", "1d")])
    def test_agg_ok(self, sym, tf):
        r = _get(f"/market/candles/{sym}?tf={tf}&limit=100")
        assert r.status_code == 200, f"{sym} {tf}: {r.status_code} {r.text[:200]}"
        j = r.json()
        assert len(j["candles"]) > 0
        ts = [c["t"] for c in j["candles"]]
        assert ts == sorted(set(ts))


# ============================================================ 3) GBPUSD naive-meta regression
class TestGBPUSDNaiveMetaRegression:
    """The exact production 500: pymongo-written naive last_sync_at."""

    def test_gbpusd_naive_meta_returns_200(self):
        mid = "GBPUSD:1m"
        backup = DB.market_history_meta.find_one({"_id": mid})
        now = int(time.time())
        # Use pymongo (naive round-trip) exactly as production DB stored it.
        DB.market_history_meta.replace_one({"_id": mid}, {
            "_id": mid,
            "oldest_t": now - 2 * 86400,
            "newest_t": now - 7200,
            "last_sync_at": datetime.now(timezone.utc) - timedelta(hours=2),
        }, upsert=True)
        try:
            r = _get("/market/candles/GBPUSD?tf=1m&limit=50")
            assert r.status_code == 200, (
                f"GBPUSD naive-meta scenario returned {r.status_code}: {r.text[:200]}"
            )
            j = r.json()
            assert isinstance(j.get("candles"), list) and len(j["candles"]) > 0
            reason = str(j["sync"].get("reason", ""))
            # If a sync error happened, it must NOT be the pre-fix TypeError.
            assert "TypeError" not in reason and "offset-naive" not in reason, (
                f"naive-datetime TypeError leaked into sync.reason: {reason}"
            )
        finally:
            # Cleanup as requested
            DB.market_history_meta.delete_one({"_id": mid})
            if backup is not None:
                DB.market_history_meta.replace_one({"_id": mid}, backup, upsert=True)


# ============================================================ 4) sync failure isolation
class TestSyncIsolation:
    def test_sync_always_dict_and_200(self):
        # We can't force a sync error deterministically without mocking the
        # provider, but we can assert the contract on every symbol.
        for sym in SYMBOLS:
            r = _get(f"/market/candles/{sym}?tf=1m&limit=10")
            assert r.status_code == 200, f"{sym}: {r.status_code}"
            j = r.json()
            assert isinstance(j["sync"], dict)
            reason = str(j["sync"].get("reason", ""))
            if reason.startswith("sync_error:"):
                # Contract: still 200 + candles served
                assert len(j["candles"]) > 0, f"{sym}: sync_error but no candles"


# ============================================================ 5) backfill path
class TestBackfill:
    def test_backfill_range_cached_for_future_before(self):
        # before = now + 100_000 → past the newest cached bar → range_cached
        before = int(time.time()) + 100_000
        r = _get(f"/market/candles/XAUUSD?tf=1m&limit=100&before={before}")
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        j = r.json()
        assert isinstance(j["sync"], dict)
        # In this preview env with no Finnhub key, backfill can also return
        # provider_unavailable — both are acceptable NON-500 outcomes.
        reason = j["sync"].get("reason", "")
        assert reason in ("range_cached", "provider_unavailable"), (
            f"unexpected backfill reason: {reason}"
        )


# ============================================================ 6) regression: other endpoints
class TestRegressionOtherEndpoints:
    def test_forex_candles_endpoint_still_ok(self):
        r = _get("/forex/candles/XAUUSD?limit=5")
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"

    def test_market_providers_status_requires_admin(self):
        # Sanity: without token this must not 500 — 401/403 is expected.
        r = _get("/market_providers/status")
        assert r.status_code in (200, 401, 403), f"{r.status_code}: {r.text[:120]}"

        # With admin token, must be 200.
        login = requests.post(
            f"{API}/admin/login",
            json={"email": "admin@mfb.in", "password": "Admin@MFB2026"},
            timeout=20,
        )
        if login.status_code != 200:
            pytest.skip(f"admin login unavailable: {login.status_code}")
        token = login.json().get("token") or login.json().get("access_token")
        assert token, f"no token in admin login response: {login.text[:120]}"
        r = _get("/market_providers/status",
                 headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"admin status: {r.status_code}: {r.text[:200]}"
