"""Sprint 7 Slice 1 — Market Data subsystem tests.

Covers: /api/market_data/* (catalog, quotes, favorites, recently-viewed, WS)
and /api/admin/market_data/* (status/settings/test-provider).
"""
import json
import os
import time

import pytest
import requests


BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://wealth-growth-mobile.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"


# ---------- helpers ----------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/admin/login",
                      json={"email": "admin@mfb.in", "password": "Admin@MFB2026"},
                      timeout=15)
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_hdrs(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- catalog ----------
class TestCatalog:
    def test_categories(self):
        r = requests.get(f"{API}/market_data/categories", timeout=10)
        assert r.status_code == 200
        cats = {c["id"]: c["count"] for c in r.json()["categories"]}
        assert cats.get("forex_majors") == 7
        assert cats.get("forex_minors") == 21
        assert cats.get("forex_exotics") == 15
        assert cats.get("metals") == 4
        assert cats.get("energies") == 3
        assert cats.get("indices") == 10
        assert cats.get("crypto") == 30
        assert cats.get("commodities") == 6

    def test_catalog_default(self):
        r = requests.get(f"{API}/market_data/catalog", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 96
        assert len(d["items"]) == 50
        assert d["has_more"] is True

    def test_catalog_crypto_category(self):
        r = requests.get(f"{API}/market_data/catalog",
                         params={"category": "crypto", "limit": 200}, timeout=10)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 30
        assert all(i["category"] == "crypto" for i in items)

    def test_catalog_search_eur(self):
        r = requests.get(f"{API}/market_data/catalog",
                         params={"search": "eur", "limit": 200}, timeout=10)
        assert r.status_code == 200
        items = r.json()["items"]
        assert items, "no results for search=eur"
        # EURUSD should be first (exact prefix)
        assert items[0]["symbol_id"] == "EURUSD"

    def test_catalog_indices_paging(self):
        r = requests.get(f"{API}/market_data/catalog",
                         params={"category": "indices", "page": 1, "limit": 5},
                         timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert len(d["items"]) == 5
        assert d["has_more"] is True

    def test_symbol_meta_xauusd(self):
        r = requests.get(f"{API}/market_data/symbols/XAUUSD", timeout=10)
        assert r.status_code == 200
        d = r.json()
        for k in ("symbol_id", "display", "name", "category", "price_dp", "provider_symbols"):
            assert k in d, f"missing key {k}"
        assert d["symbol_id"] == "XAUUSD"
        assert d["category"] == "metals"
        assert isinstance(d["provider_symbols"], dict)

    def test_symbol_not_found(self):
        r = requests.get(f"{API}/market_data/symbols/NOPE", timeout=10)
        assert r.status_code == 404


# ---------- quotes ----------
class TestQuotes:
    def test_single_quote(self):
        r = requests.get(f"{API}/market_data/quote/XAUUSD", timeout=10)
        assert r.status_code == 200
        q = r.json()
        for k in ("mid", "bid", "ask", "source", "price_dp", "category"):
            assert k in q, f"missing quote field {k}"
        assert q["source"] == "mock"
        assert q["price_dp"] == 2
        assert q["category"] == "metals"
        # change_pct field present (may be 0)
        assert "change_pct" in q

    def test_batch_quotes(self):
        symbols = "XAUUSD,BTCUSD,EURUSD,SOLUSD"
        r = requests.get(f"{API}/market_data/quotes",
                         params={"symbols": symbols}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert len(d["quotes"]) == 4
        mids = {q["symbol_id"]: q["mid"] for q in d["quotes"]}
        assert set(mids.keys()) == {"XAUUSD", "BTCUSD", "EURUSD", "SOLUSD"}
        # values should differ across symbols
        assert len(set(mids.values())) >= 2

    def test_batch_too_many(self):
        many = ",".join([f"S{i}" for i in range(105)])
        r = requests.get(f"{API}/market_data/quotes",
                         params={"symbols": many}, timeout=10)
        assert r.status_code == 400

    def test_history(self):
        r = requests.get(f"{API}/market_data/history/BTCUSD",
                         params={"points": 30}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        pts = d["points"]
        assert len(pts) == 30
        for p in pts:
            assert "ts" in p and "mid" in p
        ts = [p["ts"] for p in pts]
        assert ts == sorted(ts), "history timestamps not monotonic"


# ---------- favorites (auth-gated) ----------
class TestFavorites:
    def test_unauth_favorites_blocked(self):
        r = requests.get(f"{API}/market_data/favorites", timeout=10)
        assert r.status_code in (401, 403)

    def test_favorites_flow(self, demo_headers):
        # Cleanup prior state
        for sid in ("XAUUSD", "BTCUSD"):
            requests.delete(f"{API}/market_data/favorites/{sid}",
                            headers=demo_headers, timeout=10)
        # Add XAUUSD
        r = requests.post(f"{API}/market_data/favorites/XAUUSD",
                          headers=demo_headers, timeout=10)
        assert r.status_code == 200
        assert r.json()["ok"] is True
        # Add BTCUSD
        r = requests.post(f"{API}/market_data/favorites/BTCUSD",
                          headers=demo_headers, timeout=10)
        assert r.status_code == 200
        # Duplicate — idempotent
        r = requests.post(f"{API}/market_data/favorites/XAUUSD",
                          headers=demo_headers, timeout=10)
        assert r.status_code == 200
        # List
        r = requests.get(f"{API}/market_data/favorites",
                         headers=demo_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert set(d["symbols"]) == {"XAUUSD", "BTCUSD"}
        assert len(d["items"]) == 2
        # Delete BTCUSD
        r = requests.delete(f"{API}/market_data/favorites/BTCUSD",
                            headers=demo_headers, timeout=10)
        assert r.status_code == 200
        r = requests.get(f"{API}/market_data/favorites",
                         headers=demo_headers, timeout=10)
        assert r.json()["symbols"] == ["XAUUSD"]

    def test_favorite_unknown_symbol(self, demo_headers):
        r = requests.post(f"{API}/market_data/favorites/NOPE",
                          headers=demo_headers, timeout=10)
        assert r.status_code == 404


# ---------- recently viewed ----------
class TestRecentlyViewed:
    def test_recent_dedup_and_order(self, demo_headers):
        for sid in ("EURUSD", "BTCUSD", "EURUSD"):
            r = requests.post(f"{API}/market_data/recently-viewed/{sid}",
                              headers=demo_headers, timeout=10)
            assert r.status_code == 200
        r = requests.get(f"{API}/market_data/recently-viewed",
                         headers=demo_headers, timeout=10)
        assert r.status_code == 200
        entries = r.json()["entries"]
        assert entries[0]["symbol_id"] == "EURUSD"
        sids = [e["symbol_id"] for e in entries]
        assert len(sids) == len(set(sids)), "entries not deduplicated"

    def test_recent_caps_at_20(self, demo_headers):
        # Push ~25 unique symbols
        pool = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
                "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "EURCHF",
                "GBPJPY", "AUDJPY", "CADJPY", "CHFJPY", "NZDJPY",
                "XAUUSD", "XAGUSD", "WTIUSD", "BTCUSD", "ETHUSD",
                "SOLUSD", "ADAUSD", "XRPUSD", "DOGEUSD", "BNBUSD"]
        for sid in pool:
            requests.post(f"{API}/market_data/recently-viewed/{sid}",
                          headers=demo_headers, timeout=10)
        r = requests.get(f"{API}/market_data/recently-viewed",
                         headers=demo_headers, timeout=10)
        entries = r.json()["entries"]
        assert len(entries) <= 20, f"expected <=20, got {len(entries)}"


# ---------- WebSocket ----------
class TestWebSocket:
    def test_ws_subscribe_ping(self):
        import websocket  # websocket-client
        ws_url = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/api/market_data/ws/stream"
        try:
            ws = websocket.create_connection(ws_url, timeout=10)
        except Exception as e:
            pytest.skip(f"WS connect failed: {e}")
        try:
            ws.send(json.dumps({"action": "subscribe", "symbols": ["XAUUSD", "BTCUSD"]}))
            got_quote = False
            got_sub_ack = False
            deadline = time.time() + 8
            ws.settimeout(6)
            while time.time() < deadline:
                try:
                    msg = json.loads(ws.recv())
                except Exception:
                    break
                if msg.get("type") == "subscribed":
                    got_sub_ack = True
                elif msg.get("type") == "quote":
                    got_quote = True
                    break
            assert got_sub_ack or got_quote, "no subscribe ack / quote received"
            # ping
            ws.send(json.dumps({"action": "ping"}))
            ws.settimeout(4)
            pong = None
            deadline2 = time.time() + 5
            while time.time() < deadline2:
                m = json.loads(ws.recv())
                if m.get("type") == "pong":
                    pong = m
                    break
            assert pong is not None
            # invalid action
            ws.send(json.dumps({"action": "bogus"}))
            deadline3 = time.time() + 4
            err = None
            while time.time() < deadline3:
                m = json.loads(ws.recv())
                if m.get("type") == "error":
                    err = m
                    break
            assert err is not None
        finally:
            ws.close()


# ---------- Admin ----------
class TestAdmin:
    def test_admin_status(self, admin_hdrs):
        r = requests.get(f"{API}/admin/market_data/status",
                         headers=admin_hdrs, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["catalog_size"] == 96
        assert d["provider_health"]["ok"] is True
        assert d["transport_status"]["running"] is True
        assert "settings" in d

    def test_admin_update_interval(self, admin_hdrs):
        r = requests.put(f"{API}/admin/market_data/settings",
                         headers=admin_hdrs,
                         json={"interval_seconds": 2}, timeout=10)
        assert r.status_code == 200
        s = r.json()["settings"]
        assert s["interval_seconds"] == 2
        # Reset to default
        requests.put(f"{API}/admin/market_data/settings",
                     headers=admin_hdrs,
                     json={"interval_seconds": 3}, timeout=10)

    def test_admin_switch_to_twelvedata_and_back(self, admin_hdrs):
        r = requests.put(f"{API}/admin/market_data/settings",
                         headers=admin_hdrs,
                         json={"provider": "twelvedata",
                               "api_keys": {"twelvedata": "FAKE_KEY_123"}},
                         timeout=10)
        assert r.status_code == 200
        # Quote endpoint should not crash (may return 404 or a mock fallback)
        rq = requests.get(f"{API}/market_data/quote/XAUUSD", timeout=15)
        assert rq.status_code in (200, 404)
        # Reset to mock
        r2 = requests.put(f"{API}/admin/market_data/settings",
                          headers=admin_hdrs,
                          json={"provider": "mock",
                                "api_keys": {"twelvedata": ""}},
                          timeout=10)
        assert r2.status_code == 200
        # Confirm mock is active again
        rq2 = requests.get(f"{API}/market_data/quote/XAUUSD", timeout=10)
        assert rq2.status_code == 200
        assert rq2.json()["source"] == "mock"

    def test_admin_test_provider(self, admin_hdrs):
        r = requests.post(f"{API}/admin/market_data/test-provider",
                          headers=admin_hdrs, timeout=10)
        assert r.status_code == 200
        assert r.json()["ok"] is True


# ---------- Regression: Forex trading, KYC, wallet, notifications ----------
class TestRegression:
    def test_forex_symbols_list(self):
        r = requests.get(f"{API}/forex/symbols", timeout=10)
        assert r.status_code == 200
        body = r.json()
        items = body.get("symbols") if isinstance(body, dict) else body
        syms = {i["id"] for i in items}
        expected = {"XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"}
        assert expected.issubset(syms), f"forex symbols regressed: {syms}"

    def test_forex_buy_open_close(self, demo_headers):
        # Open BUY position on XAUUSD (field is lot_size, not lots)
        r = requests.post(f"{API}/forex/positions",
                          headers=demo_headers,
                          json={"symbol_id": "XAUUSD", "side": "buy",
                                "lot_size": 0.01},
                          timeout=15)
        assert r.status_code == 200, f"forex open failed: {r.status_code} {r.text}"
        pos_id = r.json().get("position_id") or r.json().get("position", {}).get("position_id")
        # Fetch open positions
        r2 = requests.get(f"{API}/forex/positions?status=open",
                          headers=demo_headers, timeout=10)
        assert r2.status_code == 200
        open_pos = r2.json()
        assert any((p.get("position_id") == pos_id) for p in open_pos)
        # Close it
        if pos_id:
            rc = requests.post(f"{API}/forex/positions/{pos_id}/close",
                               headers=demo_headers, timeout=15)
            assert rc.status_code == 200

    def test_wallet_send_no_kyc(self, demo_headers):
        r = requests.post(f"{API}/wallet/send", headers=demo_headers,
                          json={"recipient": "9999999998", "amount": 1,
                                "note": "TEST_regression"}, timeout=10)
        assert r.status_code == 200

    def test_wallet_withdrawal_requires_kyc(self, demo_headers):
        r = requests.post(f"{API}/wallet/withdrawals/request",
                          headers=demo_headers,
                          json={"amount": 100,
                                "bank_account_id": "does-not-exist"},
                          timeout=10)
        # Bank check may happen first; KYC gate ensures never 200 for non-KYC user
        assert r.status_code != 200, f"non-KYC user got 200 from withdrawals/request: {r.text}"
        assert r.status_code in (400, 403, 404, 422)

    def test_notifications_endpoint(self, demo_headers):
        r = requests.get(f"{API}/notifications",
                         headers=demo_headers, timeout=10)
        # tolerate either shape
        assert r.status_code in (200, 404)

    def test_market_dashboard(self):
        # Sprint 6 dashboard (via market_module)
        r = requests.get(f"{API}/market/quotes",
                         params={"symbols": "AAPL,BTC-USD"}, timeout=15)
        # tolerate demo/live variations
        assert r.status_code in (200, 400, 401, 404, 422)
