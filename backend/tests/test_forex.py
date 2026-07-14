"""Forex Phase 1 backend tests — public + admin APIs."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wealth-growth-mobile.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

EXPECTED_SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"]


# ----------- admin auth fixture -----------
@pytest.fixture(scope="module")
def admin_headers():
    s = requests.Session()
    r = s.post(f"{API}/admin/login",
               json={"email": "admin@mfb.in", "password": "Admin@MFB2026"})
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code} {r.text}")
    tok = r.json().get("token")
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------------- Public API ----------------
class TestForexSymbols:
    """GET /api/forex/symbols module-level + per-symbol fields."""

    def test_symbols_shape(self, session):
        r = session.get(f"{API}/forex/symbols")
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("enabled", "demo_mode", "live_mode", "margin_per_lot", "usd_inr", "symbols"):
            assert k in data, f"missing module-level key: {k}"
        ids = [s["id"] for s in data["symbols"]]
        assert set(ids) == set(EXPECTED_SYMBOLS), f"unexpected symbols: {ids}"
        for s in data["symbols"]:
            for k in ("enabled", "spread_pips", "min_lot", "max_lot"):
                assert k in s, f"{s['id']} missing {k}"
            # Iteration 16: tradingview_symbol MUST be fully removed
            assert "tradingview_symbol" not in s, (
                f"{s['id']} still exposes deprecated tradingview_symbol field"
            )


class TestForexPrices:
    """GET /api/forex/prices — 5 quotes, bid<mid<ask, simulated source, prices walk."""

    def test_prices_shape_and_walk(self, session):
        r1 = session.get(f"{API}/forex/prices")
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert "prices" in d1
        prices1 = {q["symbol_id"]: q for q in d1["prices"]}
        assert set(prices1.keys()) == set(EXPECTED_SYMBOLS)
        for sid, q in prices1.items():
            for k in ("bid", "ask", "mid", "ts", "source", "age_ms"):
                assert k in q, f"{sid} missing {k}"
            assert q["source"] in ("simulated", "mock", "twelvedata", "alphavantage", "binance"), f"{sid} source={q['source']}"
            assert q["bid"] < q["mid"] < q["ask"], f"{sid} bid<mid<ask fails: {q}"
        # second poll after 3s — at least one symbol should move
        # Sprint 14.1.4 — cache refresh cadence is 60s; poke it once so
        # values definitively update within the 3s window.
        try:
            adm = requests.post(f"{API}/admin/login",
                                 json={"email":"admin@mfb.in","password":"Admin@MFB2026"},
                                 timeout=10)
            if adm.status_code == 200:
                atok = adm.json()["token"]
                requests.post(f"{API}/market_providers/refresh",
                              headers={"Authorization": f"Bearer {atok}"}, timeout=15)
        except Exception:
            pass
        time.sleep(1.5)
        r2 = session.get(f"{API}/forex/prices")
        d2 = r2.json()
        prices2 = {q["symbol_id"]: q for q in d2["prices"]}
        moved = any(abs(prices2[s]["mid"] - prices1[s]["mid"]) > 0 for s in EXPECTED_SYMBOLS)
        assert moved, "prices did not walk between polls"


class TestForexAuthRequired:
    """All trade endpoints require Bearer token."""

    @pytest.mark.parametrize("method,path,body", [
        ("get", "/forex/balance", None),
        ("get", "/forex/positions", None),
        ("post", "/forex/positions", {"symbol_id": "EURUSD", "side": "buy", "lot_size": 0.1}),
        ("get", "/forex/history", None),
    ])
    def test_requires_token(self, method, path, body):
        fn = getattr(requests, method)
        r = fn(f"{API}{path}", json=body) if body else fn(f"{API}{path}")
        assert r.status_code in (401, 403), f"{path} unauth got {r.status_code}"


class TestForexTrading:
    """End-to-end paper trade workflow against demo account."""

    @pytest.fixture(scope="class", autouse=True)
    def reset_account(self, demo_headers):
        # reset balance to default (also cancels open positions silently)
        requests.post(f"{API}/forex/balance/reset", headers=demo_headers)
        yield

    def test_balance_initial(self, demo_headers):
        r = requests.get(f"{API}/forex/balance", headers=demo_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["currency"] == "INR"
        # after reset → exactly 10L
        assert data["balance"] == 1_000_000.0, f"balance={data['balance']}"

    def test_open_position_validation(self, demo_headers):
        # lot_size <= 0 → 422
        r = requests.post(f"{API}/forex/positions", headers=demo_headers,
                          json={"symbol_id": "EURUSD", "side": "buy", "lot_size": 0})
        assert r.status_code == 422, f"got {r.status_code}"
        # invalid side → 422
        r = requests.post(f"{API}/forex/positions", headers=demo_headers,
                          json={"symbol_id": "EURUSD", "side": "hold", "lot_size": 0.1})
        assert r.status_code == 422, f"got {r.status_code}"
        # missing symbol → 400 (engine raises ValueError → 400)
        r = requests.post(f"{API}/forex/positions", headers=demo_headers,
                          json={"symbol_id": "ZZZZZZ", "side": "buy", "lot_size": 0.1})
        assert r.status_code == 400, f"got {r.status_code}"

    def test_full_trade_lifecycle(self, demo_headers):
        # initial balance
        bal0 = requests.get(f"{API}/forex/balance", headers=demo_headers).json()["balance"]
        # OPEN
        r = requests.post(f"{API}/forex/positions", headers=demo_headers,
                          json={"symbol_id": "EURUSD", "side": "buy", "lot_size": 0.1})
        assert r.status_code == 200, r.text
        pos = r.json()
        assert pos["status"] == "open"
        assert pos["margin_inr"] == 100.0  # 0.1 lot * 1000
        assert pos["entry_price"] > 0
        pos_id = pos["position_id"]
        # balance decreased
        bal1 = requests.get(f"{API}/forex/balance", headers=demo_headers).json()["balance"]
        assert round(bal0 - bal1, 2) == 100.0, f"margin delta={bal0-bal1}"
        # LIST OPEN
        r = requests.get(f"{API}/forex/positions?status=open", headers=demo_headers)
        assert r.status_code == 200
        opens = r.json()
        assert any(p["position_id"] == pos_id for p in opens)
        the = next(p for p in opens if p["position_id"] == pos_id)
        assert "pnl_inr" in the and "current_price" in the
        # GET single
        r = requests.get(f"{API}/forex/positions/{pos_id}", headers=demo_headers)
        assert r.status_code == 200 and r.json()["position_id"] == pos_id
        # PUT TP/SL
        entry = pos["entry_price"]
        r = requests.put(f"{API}/forex/positions/{pos_id}", headers=demo_headers,
                         json={"tp": round(entry + 0.05, 5), "sl": round(entry - 0.05, 5)})
        assert r.status_code == 200, r.text
        upd = r.json()
        assert upd["tp"] is not None and upd["sl"] is not None
        # PUT nothing → 400
        r = requests.put(f"{API}/forex/positions/{pos_id}", headers=demo_headers, json={})
        assert r.status_code == 400, f"empty put got {r.status_code}"
        # CLOSE
        r = requests.post(f"{API}/forex/positions/{pos_id}/close", headers=demo_headers)
        assert r.status_code == 200, r.text
        closed = r.json()
        assert closed["status"] == "closed"
        assert closed["close_reason"] == "manual"
        assert closed["close_price"] is not None
        # Balance refunded
        bal2 = requests.get(f"{API}/forex/balance", headers=demo_headers).json()["balance"]
        expected = bal1 + 100.0 + closed["pnl_inr"]
        assert abs(bal2 - expected) < 0.01, f"balance refund mismatch bal2={bal2} expected={expected}"
        # CLOSED list
        r = requests.get(f"{API}/forex/positions?status=closed", headers=demo_headers)
        assert any(p["position_id"] == pos_id for p in r.json())
        # HISTORY
        r = requests.get(f"{API}/forex/history", headers=demo_headers)
        assert r.status_code == 200
        events = r.json()
        ev_for_pos = [e for e in events if e.get("position_id") == pos_id]
        kinds = {e["event"] for e in ev_for_pos}
        assert {"open", "close"}.issubset(kinds), f"history events: {kinds}"


# ---------------- Admin API ----------------
class TestForexAdmin:
    def test_get_settings(self, admin_headers):
        r = requests.get(f"{API}/admin/forex/settings", headers=admin_headers)
        assert r.status_code == 200, r.text
        cfg = r.json()
        for k in ("enabled", "demo_mode", "live_mode", "symbols", "diagnostics"):
            assert k in cfg, f"missing {k}"
        # twelve_data_api_key never exposed
        assert cfg.get("twelve_data_api_key", "") == ""

    def test_disable_module_blocks_open(self, admin_headers, demo_headers):
        # disable
        r = requests.put(f"{API}/admin/forex/settings", headers=admin_headers,
                         json={"enabled": False})
        assert r.status_code == 200, r.text
        try:
            r2 = requests.post(f"{API}/forex/positions", headers=demo_headers,
                               json={"symbol_id": "EURUSD", "side": "buy", "lot_size": 0.1})
            assert r2.status_code == 400, r2.text
            assert "disabled" in r2.text.lower()
        finally:
            requests.put(f"{API}/admin/forex/settings", headers=admin_headers,
                         json={"enabled": True})

    def test_disable_symbol_blocks_open(self, admin_headers, demo_headers):
        r = requests.put(f"{API}/admin/forex/settings", headers=admin_headers,
                         json={"symbols": {"EURUSD": {"enabled": False, "spread_pips": 1,
                                                       "min_lot": 0.01, "max_lot": 100.0}}})
        assert r.status_code == 200, r.text
        try:
            r2 = requests.post(f"{API}/forex/positions", headers=demo_headers,
                               json={"symbol_id": "EURUSD", "side": "buy", "lot_size": 0.1})
            assert r2.status_code == 400
            assert "EURUSD" in r2.text or "disabled" in r2.text.lower()
        finally:
            requests.put(f"{API}/admin/forex/settings", headers=admin_headers,
                         json={"symbols": {"EURUSD": {"enabled": True, "spread_pips": 1,
                                                       "min_lot": 0.01, "max_lot": 100.0}}})

    def test_admin_stats(self, admin_headers):
        r = requests.get(f"{API}/admin/forex/stats", headers=admin_headers)
        assert r.status_code == 200, r.text
        s = r.json()
        for k in ("active_traders", "open_positions", "closed_positions",
                  "total_realized_pnl_inr", "feed_diagnostics"):
            assert k in s, f"missing {k}"
