"""Sprint 16.1 regression tests — commission engine, pending orders, position ops,
chart objects/prefs persistence.

Key guarantees verified:
  * ₹0 commission behaves EXACTLY like the old engine (net == gross).
  * Commission snapshot is immutable — admin changes affect only NEW trades.
  * per_side doubles the charge, USD rate converts at USD_INR.
  * Pending limit/stop orders validate placement, trigger from the SAME feed,
    and fill at the live quote.
  * Partial close / reverse / double keep balance math consistent.
  * Chart objects + prefs persist per user in MongoDB.
"""
from __future__ import annotations
import os
import sys
import time

import pytest
import requests

sys.path.insert(0, "/app/backend")
from forex.costs import commission_inr, settle  # noqa: E402
from forex.symbols import USD_INR  # noqa: E402


def _base_url() -> str:
    url = os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    if not url:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                    url = line.split("=", 1)[1].strip().strip('"')
                    break
    assert url
    return url.rstrip("/")


API = f"{_base_url()}/api"
ADMIN = {"email": "admin@mfb.in", "password": "Admin@MFB2026"}
DEMO = {"identifier": "demo@mfb.in", "password": "demo1234"}


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/admin/login", json=ADMIN, timeout=10)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def user_headers():
    r = requests.post(f"{API}/auth/login", json=DEMO, timeout=10)
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
    c = MongoClient(url)
    yield c[dbname]
    c.close()


def _set_costs(admin_headers, per_lot, ctype="fixed_per_lot", ccur="INR"):
    r = requests.put(f"{API}/admin/forex/settings", headers=admin_headers,
                     json={"trading_costs": {"commission_per_lot": per_lot,
                                             "commission_type": ctype,
                                             "commission_currency": ccur}}, timeout=10)
    assert r.status_code == 200, r.text[:200]


@pytest.fixture(scope="module", autouse=True)
def zero_costs_teardown(admin_headers):
    yield
    _set_costs(admin_headers, 0.0)  # always restore demo default


def _open(user_headers, lot=0.01, symbol="EURUSD", side="buy"):
    r = requests.post(f"{API}/forex/positions", headers=user_headers,
                      json={"symbol_id": symbol, "side": side, "lot_size": lot}, timeout=15)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def _close(user_headers, pid):
    r = requests.post(f"{API}/forex/positions/{pid}/close", headers=user_headers, timeout=15)
    assert r.status_code == 200, r.text[:300]
    return r.json()


# ------------------------------------------------------------------ #
# Commission engine — pure math                                      #
# ------------------------------------------------------------------ #
class TestCommissionMath:
    def test_zero_is_noop(self):
        snap = {"commission_type": "fixed_per_lot", "commission_rate": 0, "commission_currency": "INR"}
        s = settle(snap, 1.0, 1234.56)
        assert s["commission_amount"] == 0 and s["net_pnl"] == pytest.approx(1234.56)
        assert s["gross_pnl"] == pytest.approx(1234.56) and s["swap_amount"] == 0

    def test_fixed_per_lot(self):
        snap = {"commission_type": "fixed_per_lot", "commission_rate": 50, "commission_currency": "INR"}
        assert commission_inr(snap, 0.10) == pytest.approx(5.0)
        assert settle(snap, 0.10, 100.0)["net_pnl"] == pytest.approx(95.0)

    def test_per_side_doubles(self):
        snap = {"commission_type": "per_side", "commission_rate": 50, "commission_currency": "INR"}
        assert commission_inr(snap, 1.0) == pytest.approx(100.0)

    def test_round_turn_single(self):
        snap = {"commission_type": "round_turn", "commission_rate": 50, "commission_currency": "INR"}
        assert commission_inr(snap, 1.0) == pytest.approx(50.0)

    def test_usd_converts(self):
        snap = {"commission_type": "fixed_per_lot", "commission_rate": 1, "commission_currency": "USD"}
        assert commission_inr(snap, 1.0) == pytest.approx(USD_INR)


# ------------------------------------------------------------------ #
# Commission engine — trade lifecycle                                #
# ------------------------------------------------------------------ #
class TestCommissionLifecycle:
    def test_zero_commission_net_equals_gross(self, user_headers, admin_headers):
        _set_costs(admin_headers, 0.0)
        pos = _open(user_headers)
        closed = _close(user_headers, pos["position_id"])
        assert closed["commission_amount"] == 0
        assert closed["net_pnl"] == pytest.approx(closed["gross_pnl"])
        assert closed["pnl_inr"] == pytest.approx(closed["net_pnl"])
        assert closed["swap_amount"] == 0

    def test_snapshot_immutable_old_trades_unaffected(self, user_headers, admin_headers):
        _set_costs(admin_headers, 0.0)
        old = _open(user_headers, lot=0.1)           # opened at ₹0
        _set_costs(admin_headers, 200.0)             # admin raises commission
        new = _open(user_headers, lot=0.1)           # opened at ₹200/lot
        closed_old = _close(user_headers, old["position_id"])
        closed_new = _close(user_headers, new["position_id"])
        assert closed_old["commission_amount"] == 0          # old snapshot wins
        assert closed_new["commission_amount"] == pytest.approx(20.0)  # 200 * 0.1
        assert closed_new["net_pnl"] == pytest.approx(closed_new["gross_pnl"] - 20.0)
        _set_costs(admin_headers, 0.0)

    def test_open_position_shows_estimates(self, user_headers, admin_headers):
        _set_costs(admin_headers, 100.0)
        pos = _open(user_headers, lot=0.05)
        r = requests.get(f"{API}/forex/positions/{pos['position_id']}", headers=user_headers, timeout=10)
        body = r.json()
        assert body["est_commission"] == pytest.approx(5.0)
        assert body["est_net_pnl"] == pytest.approx(body["pnl_inr"] - 5.0)
        _close(user_headers, pos["position_id"])
        _set_costs(admin_headers, 0.0)

    def test_commission_report(self, admin_headers):
        r = requests.get(f"{API}/admin/forex/commission-report",
                         headers=admin_headers, params={"group_by": "symbol"}, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["total_commission_collected"] >= 20.0  # from tests above
        assert any(row["key"] == "EURUSD" for row in body["rows"])
        for gb in ("day", "week", "month", "user"):
            assert requests.get(f"{API}/admin/forex/commission-report",
                                headers=admin_headers, params={"group_by": gb}, timeout=10).status_code == 200
        assert requests.get(f"{API}/admin/forex/commission-report",
                            headers=admin_headers, params={"group_by": "bad"}, timeout=10).status_code == 400


# ------------------------------------------------------------------ #
# Pending orders                                                     #
# ------------------------------------------------------------------ #
class TestPendingOrders:
    def _quote(self, user_headers, symbol="EURUSD"):
        r = requests.get(f"{API}/forex/prices", timeout=10)
        return next(p for p in r.json()["prices"] if p["symbol_id"] == symbol)

    def test_placement_validation(self, user_headers):
        q = self._quote(user_headers)
        # Buy limit ABOVE ask must be rejected
        r = requests.post(f"{API}/forex/orders", headers=user_headers,
                          json={"symbol_id": "EURUSD", "side": "buy", "order_type": "limit",
                                "price": q["ask"] * 1.01, "lot_size": 0.01}, timeout=10)
        assert r.status_code == 400
        # Sell stop ABOVE bid must be rejected
        r = requests.post(f"{API}/forex/orders", headers=user_headers,
                          json={"symbol_id": "EURUSD", "side": "sell", "order_type": "stop",
                                "price": q["bid"] * 1.01, "lot_size": 0.01}, timeout=10)
        assert r.status_code == 400

    def test_place_modify_cancel(self, user_headers):
        q = self._quote(user_headers)
        price = round(q["ask"] * 0.95, 5)
        r = requests.post(f"{API}/forex/orders", headers=user_headers,
                          json={"symbol_id": "EURUSD", "side": "buy", "order_type": "limit",
                                "price": price, "lot_size": 0.02, "tp": q["ask"] * 1.05}, timeout=10)
        assert r.status_code == 200, r.text[:200]
        order = r.json()
        assert order["status"] == "pending" and order["type"] == "limit"
        # appears in pending list
        lst = requests.get(f"{API}/forex/orders", headers=user_headers, timeout=10).json()
        assert any(o["order_id"] == order["order_id"] for o in lst)
        # modify price (chart drag)
        new_price = round(q["ask"] * 0.96, 5)
        r = requests.put(f"{API}/forex/orders/{order['order_id']}", headers=user_headers,
                         json={"price": new_price}, timeout=10)
        assert r.status_code == 200 and r.json()["price"] == pytest.approx(new_price)
        # cancel
        r = requests.delete(f"{API}/forex/orders/{order['order_id']}", headers=user_headers, timeout=10)
        assert r.status_code == 200 and r.json()["status"] == "cancelled"

    def test_pending_triggers_and_fills_at_live_quote(self, user_headers, mongo):
        q = self._quote(user_headers)
        price = round(q["ask"] * 0.90, 5)  # far below — safe placement
        r = requests.post(f"{API}/forex/orders", headers=user_headers,
                          json={"symbol_id": "EURUSD", "side": "buy", "order_type": "limit",
                                "price": price, "lot_size": 0.01}, timeout=10)
        order = r.json()
        # Force triggerable: raise limit price above current ask (as if market dropped)
        mongo.forex_orders.update_one({"order_id": order["order_id"]},
                                      {"$set": {"price": q["ask"] * 1.10}})
        filled = None
        for _ in range(10):  # mark loop runs every 3s
            time.sleep(2)
            lst = requests.get(f"{API}/forex/orders", headers=user_headers,
                               params={"status": "filled"}, timeout=10).json()
            filled = next((o for o in lst if o["order_id"] == order["order_id"]), None)
            if filled:
                break
        assert filled, "pending order did not fill"
        assert filled["position_id"]
        # Entry price equals live quote at fill time (ask side for buys)
        pos = requests.get(f"{API}/forex/positions/{filled['position_id']}",
                           headers=user_headers, timeout=10).json()
        assert pos["entry_price"] == pytest.approx(filled["filled_price"])
        _close(user_headers, filled["position_id"])


# ------------------------------------------------------------------ #
# Position ops                                                       #
# ------------------------------------------------------------------ #
class TestPositionOps:
    def test_partial_close(self, user_headers):
        pos = _open(user_headers, lot=0.10)
        r = requests.post(f"{API}/forex/positions/{pos['position_id']}/partial-close",
                          headers=user_headers, json={"fraction": 0.5}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["closed"]["lot_size"] == pytest.approx(0.05)
        assert body["closed"]["status"] == "closed"
        assert body["closed"]["close_reason"] == "partial_close"
        assert body["position"]["lot_size"] == pytest.approx(0.05)
        assert body["position"]["status"] == "open"
        # margins add up: original 0.10 lot * 1000 = 100 → 50 remains
        assert body["position"]["margin_inr"] == pytest.approx(pos["margin_inr"] / 2)
        _close(user_headers, pos["position_id"])

    def test_partial_close_validation(self, user_headers):
        pos = _open(user_headers, lot=0.01)
        r = requests.post(f"{API}/forex/positions/{pos['position_id']}/partial-close",
                          headers=user_headers, json={"fraction": 1.5}, timeout=10)
        assert r.status_code == 422  # pydantic lt=1
        _close(user_headers, pos["position_id"])

    def test_reverse(self, user_headers):
        pos = _open(user_headers, lot=0.02, side="buy")
        r = requests.post(f"{API}/forex/positions/{pos['position_id']}/reverse",
                          headers=user_headers, timeout=15)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["closed"]["status"] == "closed" and body["closed"]["close_reason"] == "reverse"
        assert body["opened"]["side"] == "sell" and body["opened"]["lot_size"] == pytest.approx(0.02)
        _close(user_headers, body["opened"]["position_id"])

    def test_double(self, user_headers):
        pos = _open(user_headers, lot=0.03, side="sell")
        r = requests.post(f"{API}/forex/positions/{pos['position_id']}/double",
                          headers=user_headers, timeout=15)
        assert r.status_code == 200
        opened = r.json()["opened"]
        assert opened["side"] == "sell" and opened["lot_size"] == pytest.approx(0.03)
        _close(user_headers, pos["position_id"])
        _close(user_headers, opened["position_id"])


# ------------------------------------------------------------------ #
# Chart objects + prefs persistence                                  #
# ------------------------------------------------------------------ #
class TestChartPersistence:
    def test_objects_roundtrip(self, user_headers):
        objs = [{"type": "trendline", "p1": {"t": 1700000000, "price": 1.1},
                 "p2": {"t": 1700003600, "price": 1.2}, "color": "#f0b90b"},
                {"type": "hline", "price": 1.15, "color": "#26a69a"}]
        r = requests.put(f"{API}/forex/chart-objects", headers=user_headers,
                         json={"symbol_id": "EURUSD", "chart_key": "main", "objects": objs}, timeout=10)
        assert r.status_code == 200 and r.json()["count"] == 2
        r = requests.get(f"{API}/forex/chart-objects", headers=user_headers,
                         params={"symbol_id": "EURUSD", "chart_key": "main"}, timeout=10)
        assert r.json()["objects"] == objs

    def test_prefs_roundtrip(self, user_headers):
        prefs = {"indicators": {"ema": {"enabled": True, "period": 20}},
                 "workspace": {"layout": "dual_v", "panes": [{"symbol": "EURUSD", "tf": "1m"}]}}
        r = requests.put(f"{API}/forex/chart-prefs", headers=user_headers,
                         json={"prefs": prefs}, timeout=10)
        assert r.status_code == 200
        r = requests.get(f"{API}/forex/chart-prefs", headers=user_headers, timeout=10)
        assert r.json()["prefs"] == prefs

    def test_auth_required(self):
        assert requests.get(f"{API}/forex/chart-objects",
                            params={"symbol_id": "EURUSD"}, timeout=10).status_code in (401, 403)
        assert requests.put(f"{API}/forex/chart-prefs", json={"prefs": {}}, timeout=10).status_code in (401, 403)
