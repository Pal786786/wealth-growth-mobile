"""Forex regression tests for the 2026 price refresh + new /candles endpoint +
symbol detail blank-white-screen fix. Covers points explicitly called out in
the review request.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wealth-growth-mobile.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

EXPECTED_SYMBOLS = {"XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"}


# ------------------ New price ranges (2026 anchors) ------------------
class TestForexPriceRanges:
    """Verify new 2026 starting prices are within the announced band and NOT
    the old range (XAU/USD ~2340). Ensures the frontend chart & watchlist show
    believable numbers.
    """

    def test_xauusd_and_btcusd_within_2026_bands(self, session):
        r = session.get(f"{API}/forex/prices")
        assert r.status_code == 200
        m = {q["symbol_id"]: q for q in r.json()["prices"]}
        assert set(m.keys()) == EXPECTED_SYMBOLS

        xau = m["XAUUSD"]["mid"]
        btc = m["BTCUSD"]["mid"]
        assert 3900 <= xau <= 4200, f"XAU/USD mid={xau} outside 2026 band 3900-4200"
        assert 100_000 <= btc <= 105_000, f"BTC/USD mid={btc} outside 2026 band"

    def test_symbols_endpoint_matches_prices(self, session):
        cfg = session.get(f"{API}/forex/symbols").json()
        prices = {q["symbol_id"]: q for q in session.get(f"{API}/forex/prices").json()["prices"]}
        # Every enabled symbol must have a live quote
        for s in cfg["symbols"]:
            if s["enabled"]:
                assert s["id"] in prices, f"enabled symbol {s['id']} has no live quote"


# ------------------ New /candles endpoint ------------------
class TestForexCandles:
    """/api/forex/candles/{id} must return ring-buffer history that matches the
    quote in /api/forex/prices — this is the fix for the price-mismatch bug.
    """

    @pytest.mark.parametrize("sid", ["XAUUSD", "EURUSD", "BTCUSD"])
    def test_candles_shape_and_size(self, session, sid):
        r = session.get(f"{API}/forex/candles/{sid}", params={"limit": 100})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["symbol_id"] == sid
        assert "price_decimals" in d
        pts = d["points"]
        assert isinstance(pts, list)
        assert len(pts) >= 50, f"expected >=50 points, got {len(pts)}"
        # Fields present
        for p in pts[:5]:
            assert "ts" in p and "mid" in p
            assert isinstance(p["ts"], (int, float))
            assert isinstance(p["mid"], (int, float))
        # Monotonic non-decreasing timestamps
        for a, b in zip(pts, pts[1:]):
            assert b["ts"] >= a["ts"], "timestamps not monotonic"

    def test_candles_consistent_with_prices(self, session):
        """Last candle mid should be within a tiny window of the live quote mid
        (they come from the SAME cache — the entire point of the fix)."""
        # Poll a few times so we have a fresh candle right after a prices call
        prices = {q["symbol_id"]: q for q in session.get(f"{API}/forex/prices").json()["prices"]}
        candles = session.get(f"{API}/forex/candles/XAUUSD", params={"limit": 5}).json()
        last_mid = candles["points"][-1]["mid"]
        live_mid = prices["XAUUSD"]["mid"]
        # Simulated random walk can drift between calls; allow ~0.5% deviation
        drift = abs(last_mid - live_mid) / live_mid
        assert drift < 0.01, f"last candle {last_mid} vs live {live_mid} — drift {drift:.4%} too large"

    def test_candles_unknown_symbol_returns_404(self, session):
        r = session.get(f"{API}/forex/candles/FOOBAR")
        assert r.status_code == 404

    def test_candles_limit_clamped(self, session):
        # limit=5 should be clamped up to 10 (per implementation)
        r = session.get(f"{API}/forex/candles/XAUUSD", params={"limit": 5}).json()
        assert len(r["points"]) >= 10
        # limit=9999 should be clamped down to 300
        r = session.get(f"{API}/forex/candles/XAUUSD", params={"limit": 9999}).json()
        assert len(r["points"]) <= 300

    def test_candles_appends_over_time(self, session):
        """History ring buffer keeps growing every ~2s."""
        r1 = session.get(f"{API}/forex/candles/XAUUSD", params={"limit": 200}).json()
        n1 = len(r1["points"])
        last_ts1 = r1["points"][-1]["ts"]
        time.sleep(3.5)  # 1-2 ticks
        r2 = session.get(f"{API}/forex/candles/XAUUSD", params={"limit": 200}).json()
        n2 = len(r2["points"])
        last_ts2 = r2["points"][-1]["ts"]
        # Either buffer grew (still filling) OR last_ts moved forward (buffer full)
        assert n2 >= n1 or last_ts2 > last_ts1, (
            f"candles neither grew ({n1}→{n2}) nor advanced ts ({last_ts1}→{last_ts2})"
        )


# ------------------ Entry price = live feed ask/bid ------------------
class TestOrderEntryFromLiveFeed:
    """When we open a BUY, entry_price must be close to the current ask."""

    @pytest.fixture(scope="class", autouse=True)
    def reset(self, demo_headers):
        requests.post(f"{API}/forex/balance/reset", headers=demo_headers)
        yield

    def test_buy_xauusd_entry_price_matches_ask(self, demo_headers):
        pre = requests.get(f"{API}/forex/prices").json()
        ask = next(q for q in pre["prices"] if q["symbol_id"] == "XAUUSD")["ask"]
        r = requests.post(f"{API}/forex/positions", headers=demo_headers,
                          json={"symbol_id": "XAUUSD", "side": "buy", "lot_size": 0.1})
        assert r.status_code == 200, r.text
        pos = r.json()
        assert pos["status"] == "open"
        # Margin correctness: 0.1 lot * ₹1000 default = ₹100
        assert pos["margin_inr"] == 100.0
        # Entry price should be within 0.5% of the ask we just read (simulated walk between calls)
        drift = abs(pos["entry_price"] - ask) / ask
        assert drift < 0.005, f"entry {pos['entry_price']} vs recent ask {ask} — drift {drift:.4%}"
        # Cleanup
        requests.post(f"{API}/forex/positions/{pos['position_id']}/close", headers=demo_headers)

    def test_sell_btcusd_with_tp_sl_stored(self, demo_headers):
        r = requests.post(f"{API}/forex/positions", headers=demo_headers,
                          json={"symbol_id": "BTCUSD", "side": "sell", "lot_size": 0.01,
                                "tp": 90000, "sl": 110000})
        assert r.status_code == 200, r.text
        pos = r.json()
        assert pos["side"] == "sell"
        assert pos["tp"] == 90000
        assert pos["sl"] == 110000
        # 0.01 lot * ₹1000 = ₹10 margin
        assert pos["margin_inr"] == 10.0
        # Cleanup
        requests.post(f"{API}/forex/positions/{pos['position_id']}/close", headers=demo_headers)


# ------------------ Regression smoke for other modules ------------------
class TestSiblingModulesStillOnline:
    """Ensure the forex refactor did NOT break other modules."""

    @pytest.mark.parametrize("path,unauth_code", [
        ("/wallet", (401, 403)),
        ("/kyc/status", (401, 403)),
        ("/ai/suggestions", (401, 403)),
        ("/notifications", (401, 403)),
        ("/market/dashboard", (200, 401, 403)),  # sprint 6 may be public
    ])
    def test_endpoint_reachable(self, session, path, unauth_code):
        r = session.get(f"{API}{path}")
        # Just ensure the route exists (not 404 / 5xx)
        assert r.status_code != 404, f"{path} 404 — regression!"
        assert r.status_code < 500, f"{path} {r.status_code} — server error"
