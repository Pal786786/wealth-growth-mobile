"""Sprint 16.0 regression tests — live candle generation + timeframe aggregation.

Covers:
  1. Pure bucket aggregation math (aggregate_candles) — OHLCV correctness.
  2. GET /api/market/candles validation (tf whitelist, unknown symbol, limits).
  3. All 7 timeframes (1m 5m 15m 30m 1h 4h 1d) return valid candle series.
  4. Live candle generation from the unified ProviderManager tick stream
     (single scheduler — POST /api/market_providers/refresh drives it).
  5. 4h aggregation from seeded (Finnhub-style) 1h bars in market_price_history —
     historical OHLC always comes from the cached DB, never regenerated.
  6. Candle invariants (h >= max(o,c), l <= min(o,c), ascending unique t).
  7. Without a Finnhub key the sync layer degrades gracefully (no crash,
     zero API credits consumed).
"""
from __future__ import annotations
import os
import sys
import time

import pytest
import requests

sys.path.insert(0, "/app/backend")
from market_candles import aggregate_candles, TIMEFRAMES  # noqa: E402


def _base_url() -> str:
    url = os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    if not url:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                    url = line.split("=", 1)[1].strip().strip('"')
                    break
    assert url, "backend url not resolvable"
    return url.rstrip("/")


BASE_URL = _base_url()
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@mfb.in", "password": "Admin@MFB2026"}
ALL_TFS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/admin/login", json=ADMIN, timeout=10)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def mongo():
    from pymongo import MongoClient
    url, dbname = "mongodb://localhost:27017", "my_funding_bank"
    for line in open("/app/backend/.env"):
        if line.startswith("MONGO_URL="):
            url = line.split("=", 1)[1].strip().strip('"')
        if line.startswith("DB_NAME="):
            dbname = line.split("=", 1)[1].strip().strip('"')
    client = MongoClient(url)
    yield client[dbname]
    client.close()


# ------------------------------------------------------------------ #
# 1. Pure aggregation math                                           #
# ------------------------------------------------------------------ #
class TestAggregationMath:
    def _mk_1m(self, t0: int, bars):
        return [{"t": t0 + i * 60, "o": o, "h": h, "l": l, "c": c, "v": v, "source": "finnhub"}
                for i, (o, h, l, c, v) in enumerate(bars)]

    def test_5m_bucket_ohlcv(self):
        t0 = 1_700_000_100  # deliberately NOT aligned to 5m
        rows = self._mk_1m(t0, [
            (1.10, 1.12, 1.09, 1.11, 5),
            (1.11, 1.15, 1.10, 1.14, 3),
            (1.14, 1.14, 1.05, 1.06, 2),
        ])
        out = aggregate_candles(rows, 300)
        # all three 1m bars land inside aligned 5m buckets
        assert all(c["t"] % 300 == 0 for c in out)
        total_v = sum(c["v"] for c in out)
        assert total_v == 10
        hi = max(c["h"] for c in out)
        lo = min(c["l"] for c in out)
        assert hi == 1.15 and lo == 1.05
        # first bucket opens with first bar's open; last closes with last bar's close
        assert out[0]["o"] == 1.10
        assert out[-1]["c"] == 1.06

    def test_4h_from_1h(self):
        t0 = 1_700_006_400  # 4h-aligned
        rows = [{"t": t0 + i * 3600, "o": 100 + i, "h": 110 + i, "l": 90 + i,
                 "c": 105 + i, "v": 10, "source": "finnhub"} for i in range(8)]
        out = aggregate_candles(rows, 14400)
        assert len(out) == 2
        b1, b2 = out
        assert b1["t"] == t0 and b2["t"] == t0 + 14400
        assert b1["o"] == 100 and b1["c"] == 108 and b1["h"] == 113 and b1["l"] == 90
        assert b1["v"] == 40 and b2["v"] == 40
        assert b2["o"] == 104 and b2["c"] == 112

    def test_out_of_order_input_is_sorted(self):
        rows = self._mk_1m(1_700_000_400, [(1, 2, 0.5, 1.5, 1), (1.5, 3, 1, 2, 1)])
        out_fwd = aggregate_candles(rows, 300)
        out_rev = aggregate_candles(list(reversed(rows)), 300)
        assert out_fwd == out_rev


# ------------------------------------------------------------------ #
# 2. Endpoint validation                                             #
# ------------------------------------------------------------------ #
class TestValidation:
    def test_bad_tf_400(self):
        r = requests.get(f"{API}/market/candles/EURUSD", params={"tf": "2m"}, timeout=10)
        assert r.status_code == 400

    def test_unknown_symbol_404(self):
        r = requests.get(f"{API}/market/candles/NOPEUSD", params={"tf": "1m"}, timeout=10)
        assert r.status_code == 404

    def test_limit_bounds(self):
        r = requests.get(f"{API}/market/candles/EURUSD", params={"tf": "1m", "limit": 5000}, timeout=10)
        assert r.status_code == 422
        r = requests.get(f"{API}/market/candles/EURUSD", params={"tf": "1m", "limit": 1}, timeout=10)
        assert r.status_code == 200


# ------------------------------------------------------------------ #
# 3+6. All timeframes + invariants                                   #
# ------------------------------------------------------------------ #
class TestAllTimeframes:
    @pytest.mark.parametrize("tf", ALL_TFS)
    def test_tf_returns_valid_series(self, tf):
        r = requests.get(f"{API}/market/candles/XAUUSD", params={"tf": tf, "limit": 100}, timeout=15)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body["tf"] == tf and body["symbol"] == "XAUUSD"
        assert "volume_available" in body and "sync" in body
        candles = body["candles"]
        prev_t = 0
        for c in candles:
            assert c["t"] % TIMEFRAMES[tf] == 0, "bucket not aligned"
            assert c["t"] > prev_t, "timestamps must be ascending & unique"
            prev_t = c["t"]
            assert c["h"] >= max(c["o"], c["c"]) - 1e-12
            assert c["l"] <= min(c["o"], c["c"]) + 1e-12
            assert c["v"] >= 0

    def test_quote_comes_from_unified_cache(self):
        r = requests.get(f"{API}/market/candles/EURUSD", params={"tf": "1m"}, timeout=10)
        q = r.json().get("quote")
        assert q and q.get("bid") and q.get("ask") and q.get("provider")


# ------------------------------------------------------------------ #
# 4. Live candle generation from the single unified scheduler        #
# ------------------------------------------------------------------ #
class TestLiveCandleGeneration:
    def test_ticks_update_forming_candle(self, admin_headers):
        def last_1m():
            r = requests.get(f"{API}/market/candles/EURUSD", params={"tf": "1m", "limit": 3}, timeout=10)
            cs = r.json()["candles"]
            return cs[-1] if cs else None

        before = last_1m()
        # Drive the ONE unified scheduler twice
        for _ in range(2):
            rr = requests.post(f"{API}/market_providers/refresh", headers=admin_headers, timeout=20)
            assert rr.status_code == 200
            time.sleep(1)
        after = last_1m()
        assert after is not None
        assert after["v"] >= 1
        assert after["complete"] is False  # forming bucket
        # volume must have increased (tick-count) OR a new bucket started
        if before is not None and before["t"] == after["t"] and before.get("source") == "live":
            assert after["v"] > before["v"]

    def test_forming_candle_merges_into_higher_tf(self):
        r1 = requests.get(f"{API}/market/candles/EURUSD", params={"tf": "1m", "limit": 5}, timeout=10)
        r15 = requests.get(f"{API}/market/candles/EURUSD", params={"tf": "15m", "limit": 5}, timeout=10)
        m1 = r1.json()["candles"]
        m15 = r15.json()["candles"]
        assert m1 and m15
        # the last 15m bucket must contain the last 1m close
        assert m15[-1]["t"] <= m1[-1]["t"] < m15[-1]["t"] + 900
        assert abs(m15[-1]["c"] - m1[-1]["c"]) < 1e-9


# ------------------------------------------------------------------ #
# 5. Historical bars: cached DB is the source of truth               #
# ------------------------------------------------------------------ #
class TestHistoricalAggregationFromCache:
    T0 = 1_500_000_000 - (1_500_000_000 % 14400)  # ancient, 4h-aligned (2017)

    @pytest.fixture(autouse=True)
    def seed(self, mongo):
        rows = [{"symbol": "EURUSD", "tf": "1h", "t": self.T0 + i * 3600,
                 "o": 1.0 + i * 0.01, "h": 1.2 + i * 0.01, "l": 0.9 + i * 0.01,
                 "c": 1.1 + i * 0.01, "v": 100.0, "source": "finnhub"} for i in range(8)]
        mongo.market_price_history.delete_many({"symbol": "EURUSD", "tf": "1h", "t": {"$gte": self.T0, "$lt": self.T0 + 8 * 3600}})
        mongo.market_price_history.insert_many(rows)
        yield
        mongo.market_price_history.delete_many({"symbol": "EURUSD", "tf": "1h", "t": {"$gte": self.T0, "$lt": self.T0 + 8 * 3600}})

    def test_4h_served_from_cached_finnhub_bars(self):
        before = self.T0 + 9 * 3600
        r = requests.get(f"{API}/market/candles/EURUSD",
                         params={"tf": "4h", "limit": 10, "before": before}, timeout=15)
        assert r.status_code == 200
        candles = [c for c in r.json()["candles"] if self.T0 <= c["t"] < self.T0 + 8 * 3600]
        assert len(candles) == 2
        b1, b2 = candles
        assert b1["t"] == self.T0
        assert b1["o"] == pytest.approx(1.0) and b1["c"] == pytest.approx(1.13)
        assert b1["h"] == pytest.approx(1.23) and b1["l"] == pytest.approx(0.9)
        assert b1["v"] == pytest.approx(400.0)
        assert b2["o"] == pytest.approx(1.04) and b2["c"] == pytest.approx(1.17)
        assert b1["source"] == "finnhub"  # never regenerated locally

    def test_1h_bars_returned_verbatim(self):
        before = self.T0 + 9 * 3600
        r = requests.get(f"{API}/market/candles/EURUSD",
                         params={"tf": "1h", "limit": 20, "before": before}, timeout=15)
        candles = [c for c in r.json()["candles"] if self.T0 <= c["t"] < self.T0 + 8 * 3600]
        assert len(candles) == 8
        assert candles[0]["o"] == pytest.approx(1.0)
        assert candles[-1]["c"] == pytest.approx(1.17)
        assert all(c["v"] == pytest.approx(100.0) for c in candles)


# ------------------------------------------------------------------ #
# 7. Graceful degradation without a Finnhub key                      #
# ------------------------------------------------------------------ #
class TestNoKeyGraceful:
    def test_sync_reports_reason_without_key(self, admin_headers):
        st = requests.get(f"{API}/market_providers/status", headers=admin_headers, timeout=10).json()
        fin = next((p for p in st["providers"] if p["name"] == "finnhub"), {})
        r = requests.get(f"{API}/market/candles/GBPUSD", params={"tf": "1h"}, timeout=15)
        assert r.status_code == 200
        sync = r.json()["sync"]
        if not fin.get("configured"):
            assert sync["synced"] is False
            assert sync["reason"] in ("provider_unavailable", "throttled", "up_to_date")
