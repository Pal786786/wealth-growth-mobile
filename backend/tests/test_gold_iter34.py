"""Sprint 10 / iter34 — Gold Investment Platform backend tests."""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wealth-growth-mobile.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def demo_headers():
    r = requests.post(f"{API}/auth/login",
                      json={"identifier": "demo@mfb.in", "password": "demo1234"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/admin/login",
                      json={"email": "admin@mfb.in", "password": "Admin@MFB2026"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="module", autouse=True)
def _reset_state_at_end(admin_headers):
    """Ensure state is clean at the end of the test module."""
    yield
    try:
        requests.put(f"{API}/admin/gold/config",
                     json={"provider": "live_market",
                           "manual_price_inr_per_gram": 0,
                           "maintenance_mode": False},
                     headers=admin_headers, timeout=15)
    except Exception:
        pass


def _wallet(headers):
    r = requests.get(f"{API}/wallet", headers=headers, timeout=15)
    assert r.status_code == 200, r.text
    return float(r.json()["balance"])


# ---------------- 1. Quote structure ----------------
class TestQuote:
    def test_01_quote_shape_and_spread(self, demo_headers):
        r = requests.get(f"{API}/gold/quote", headers=demo_headers, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("ok", "mid_price", "buy_price", "sell_price", "spread_bps",
                  "provider", "source", "quoted_at", "maintenance_mode", "trading_open"):
            assert k in j, f"missing key {k}: {j}"
        assert j["ok"] is True
        assert j["buy_price"] > j["mid_price"] > j["sell_price"] > 0
        # spread_bps consistency: (buy - sell) / mid * 10000 approx = spread_bps
        implied = (j["buy_price"] - j["sell_price"]) / j["mid_price"] * 10000
        assert abs(implied - j["spread_bps"]) < 5, f"implied {implied} vs {j['spread_bps']}"


# ---------------- 2. Buy flow / wallet debit / notification / audit ----------------
class TestBuySell:
    def test_02_buy_500_debits_wallet_and_notifies(self, demo_headers):
        bal_before = _wallet(demo_headers)
        q = requests.get(f"{API}/gold/quote", headers=demo_headers, timeout=15).json()
        buy_price = float(q["buy_price"])
        r = requests.post(f"{API}/gold/buy", json={"amount_inr": 500},
                          headers=demo_headers, timeout=15)
        assert r.status_code == 200, r.text
        tx = r.json()
        assert tx["side"] == "buy"
        assert abs(tx["amount_inr"] - 500) < 0.01
        # grams = 500 / buy_price ± 1 tick
        assert abs(tx["grams"] - 500 / buy_price) < 0.01
        assert tx.get("status") == "completed"

        bal_after = _wallet(demo_headers)
        assert abs((bal_before - bal_after) - 500) < 0.01, f"{bal_before} -> {bal_after}"

        # Holdings increased
        h = requests.get(f"{API}/gold/holdings", headers=demo_headers, timeout=15).json()
        assert h["grams"] > 0
        assert h["avg_buy_price"] > 0

        # Notification present
        n = requests.get(f"{API}/notifications", headers=demo_headers, timeout=15)
        assert n.status_code == 200, n.text
        items = n.json().get("items") if isinstance(n.json(), dict) else n.json()
        assert any("Gold purchased" in (i.get("title") or "") for i in items), \
            f"no gold purchase notification: titles={[i.get('title') for i in items[:5]]}"

    def test_03_idempotency_key_buy(self, demo_headers):
        key = f"iter34-{uuid.uuid4().hex[:10]}"
        headers = {**demo_headers, "Idempotency-Key": key}
        bal_before = _wallet(demo_headers)
        r1 = requests.post(f"{API}/gold/buy", json={"amount_inr": 100},
                           headers=headers, timeout=15)
        assert r1.status_code == 200, r1.text
        tx1 = r1.json()
        bal_mid = _wallet(demo_headers)
        r2 = requests.post(f"{API}/gold/buy", json={"amount_inr": 100},
                           headers=headers, timeout=15)
        assert r2.status_code == 200, r2.text
        tx2 = r2.json()
        bal_after = _wallet(demo_headers)
        assert tx1["tx_id"] == tx2["tx_id"], f"expected idempotent tx: {tx1} vs {tx2}"
        # Wallet only debited ONCE (100)
        assert abs((bal_before - bal_after) - 100) < 0.01, \
            f"double debit? {bal_before} -> {bal_mid} -> {bal_after}"

    def test_04_below_min_purchase(self, demo_headers):
        r = requests.post(f"{API}/gold/buy", json={"amount_inr": 5},
                          headers=demo_headers, timeout=15)
        assert r.status_code == 400, r.text
        assert "minimum" in r.text.lower()

    def test_05_insufficient_wallet(self, demo_headers, admin_headers):
        bal = _wallet(demo_headers)
        # Bump max_buy_inr above wallet+overshoot so we hit *insufficient* branch, not max cap
        try:
            requests.put(f"{API}/admin/gold/config",
                         json={"max_buy_inr": bal + 500000},
                         headers=admin_headers, timeout=15)
            r = requests.post(f"{API}/gold/buy", json={"amount_inr": bal + 100000},
                              headers=demo_headers, timeout=15)
            assert r.status_code == 400, r.text
            assert "insufficient" in r.text.lower(), r.text
        finally:
            requests.put(f"{API}/admin/gold/config",
                         json={"max_buy_inr": 200000},
                         headers=admin_headers, timeout=15)

    def test_06_sell_half_holdings(self, demo_headers):
        h = requests.get(f"{API}/gold/holdings", headers=demo_headers, timeout=15).json()
        held = float(h["grams"])
        assert held > 0, "no gold to sell — buy tests must have run first"
        half = round(held / 2, 4)
        bal_before = _wallet(demo_headers)
        r = requests.post(f"{API}/gold/sell", json={"grams": half},
                          headers=demo_headers, timeout=15)
        assert r.status_code == 200, r.text
        tx = r.json()
        assert tx["side"] == "sell"
        assert "realized_pnl_inr" in tx
        bal_after = _wallet(demo_headers)
        # Wallet credited by proceeds (~ amount_inr)
        assert abs((bal_after - bal_before) - tx["amount_inr"]) < 0.5, \
            f"wallet credit mismatch: {bal_before}->{bal_after} proceeds={tx['amount_inr']}"
        # Holdings decreased
        h2 = requests.get(f"{API}/gold/holdings", headers=demo_headers, timeout=15).json()
        assert h2["grams"] < held + 1e-6
        # Notification
        n = requests.get(f"{API}/notifications", headers=demo_headers, timeout=15).json()
        items = n.get("items") if isinstance(n, dict) else n
        titles = " ".join((i.get("title") or "") for i in items[:15])
        assert "Gold sold" in titles, f"no sell notification: {titles[:200]}"


# ---------------- 3. Chart windows ----------------
class TestChart:
    @pytest.mark.parametrize("win", ["1D", "1W", "1M", "3M", "1Y", "ALL"])
    def test_07_chart_all_windows(self, demo_headers, win):
        r = requests.get(f"{API}/gold/chart?window={win}",
                         headers=demo_headers, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        pts = j.get("points", [])
        assert isinstance(pts, list)
        assert len(pts) > 0, f"empty chart for window {win}"


# ---------------- 4. Transactions filter ----------------
class TestTransactions:
    def test_08_side_buy_only(self, demo_headers):
        r = requests.get(f"{API}/gold/transactions?side=buy",
                         headers=demo_headers, timeout=15)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) > 0
        assert all(x["side"] == "buy" for x in items)


# ---------------- 5. Admin: manual override / maintenance / provider / dashboard / providers list ----------------
class TestAdmin:
    def test_09_manual_price_override(self, demo_headers, admin_headers):
        r = requests.put(f"{API}/admin/gold/config",
                         json={"manual_price_inr_per_gram": 7000},
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        q = requests.get(f"{API}/gold/quote", headers=demo_headers, timeout=15).json()
        assert q["mid_price"] == 7000, q
        assert q["provider"] == "manual"
        assert q["source"] == "admin_override"
        # reset
        requests.put(f"{API}/admin/gold/config",
                     json={"manual_price_inr_per_gram": 0},
                     headers=admin_headers, timeout=15)

    def test_10_maintenance_mode_blocks_buy(self, demo_headers, admin_headers):
        r = requests.put(f"{API}/admin/gold/config",
                         json={"maintenance_mode": True},
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        b = requests.post(f"{API}/gold/buy", json={"amount_inr": 50},
                          headers=demo_headers, timeout=15)
        assert b.status_code == 400
        assert "maintenance" in b.text.lower()
        # reset
        requests.put(f"{API}/admin/gold/config",
                     json={"maintenance_mode": False},
                     headers=admin_headers, timeout=15)

    def test_11_provider_switch_mock_and_augmont(self, demo_headers, admin_headers):
        # mock
        r = requests.put(f"{API}/admin/gold/config",
                         json={"provider": "mock"},
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        d = requests.get(f"{API}/admin/gold/dashboard",
                         headers=admin_headers, timeout=15).json()
        assert d["provider_status"]["active"] == "mock", d["provider_status"]
        # augmont — unconfigured → fallback acceptable
        r = requests.put(f"{API}/admin/gold/config",
                         json={"provider": "augmont"},
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        q = requests.get(f"{API}/gold/quote", headers=demo_headers, timeout=15).json()
        assert q.get("mid_price"), q
        ok_a = (q.get("provider") == "augmont" and
                str(q.get("source", "")).startswith("augmont"))
        ok_b = "chosen provider 'augmont' unavailable" in str(q.get("note", ""))
        assert ok_a or ok_b, f"augmont fallback not indicated: {q}"
        # reset provider
        requests.put(f"{API}/admin/gold/config",
                     json={"provider": "live_market"},
                     headers=admin_headers, timeout=15)

    def test_12_admin_providers_list(self, admin_headers):
        r = requests.get(f"{API}/admin/gold/providers",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        names = {p["name"] for p in j["providers"]}
        assert names == {"mock", "live_market", "augmont", "mmtc_pamp", "safegold"}, names
        for p in j["providers"]:
            assert "real" in p and "configured" in p and "active" in p

    def test_13_admin_dashboard_totals(self, admin_headers):
        d = requests.get(f"{API}/admin/gold/dashboard",
                         headers=admin_headers, timeout=15).json()
        for k in ("total_buy_inr", "total_sell_inr", "realized_pnl_users_inr",
                  "platform_revenue_inr", "active_investors"):
            assert k in d["totals"], f"missing {k}: {d['totals']}"
        assert "provider_status" in d

    def test_14_audit_log(self, admin_headers):
        a = requests.get(f"{API}/admin/gold/audit",
                         headers=admin_headers, timeout=15).json()
        actions = {row["action"] for row in a["items"]}
        for expected in ("gold.buy", "gold.sell", "gold.config.updated"):
            assert expected in actions, f"missing {expected} in {actions}"


# ---------------- 6. Business rule: no KYC required ----------------
class TestBusinessRules:
    def test_15_no_kyc_gate_on_buy_or_sell(self, demo_headers):
        r = requests.post(f"{API}/gold/buy", json={"amount_inr": 20},
                          headers=demo_headers, timeout=15)
        # Either succeed (200) or a normal validation 400, but NOT 403 kyc_required
        assert r.status_code != 403, r.text
        assert "kyc_required" not in r.text.lower()
        # sell
        h = requests.get(f"{API}/gold/holdings", headers=demo_headers, timeout=15).json()
        if h.get("grams", 0) > 0.001:
            s = requests.post(f"{API}/gold/sell", json={"grams": 0.0001},
                              headers=demo_headers, timeout=15)
            assert s.status_code != 403, s.text
            assert "kyc_required" not in s.text.lower()


# ---------------- Public config ----------------
class TestConfig:
    def test_16_public_config(self, demo_headers):
        r = requests.get(f"{API}/gold/config", headers=demo_headers, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("min_buy_inr", "max_buy_inr", "spread_bps", "provider",
                  "maintenance_mode", "trading_hours"):
            assert k in j
