"""Sprint 15.1 regression tests — Demo Account Reset & Virtual Wallet Recharge.

Runs against the LIVE backend served via EXPO_PUBLIC_BACKEND_URL.

Covers:
  1. POST /api/demo/reset (user) — balance restored, positions closed,
     history archived, reset record written.
  2. POST /api/admin/demo/reset/{user_id} (admin) — admin-initiated reset.
  3. Real wallet (`/api/wallet/v2/summary`) is NEVER affected by a reset.
  4. Default demo balance is configurable via admin forex settings.
  5. Auth guards (401 without token, 404 for unknown user).
  6. Legacy /api/forex/balance/reset delegates to the full reset.
"""
from __future__ import annotations
import os

import pytest
import requests


def _base_url() -> str:
    url = os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    if not url:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip().strip('"')
                        break
        except FileNotFoundError:
            pass
    assert url, "EXPO_PUBLIC_BACKEND_URL not set"
    return url.rstrip("/")


BASE_URL = _base_url()
API = f"{BASE_URL}/api"
ADMIN_EMAIL = "admin@mfb.in"
ADMIN_PASSWORD = "Admin@MFB2026"
DEMO_USER = {"identifier": "demo@mfb.in", "password": "demo1234"}


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/admin/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=10)
    assert r.status_code == 200, f"admin login failed: {r.text[:200]}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def user_headers():
    r = requests.post(f"{API}/auth/login", json=DEMO_USER, timeout=10)
    if r.status_code != 200:
        pytest.skip(f"demo user login failed: {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def user_id(user_headers):
    r = requests.get(f"{API}/auth/me", headers=user_headers, timeout=10)
    assert r.status_code == 200
    body = r.json()
    return body.get("user_id") or body.get("user", {}).get("user_id")


def _default_demo_balance(admin_headers) -> float:
    r = requests.get(f"{API}/admin/forex/settings", headers=admin_headers, timeout=10)
    assert r.status_code == 200
    return float(r.json().get("default_demo_balance", 1_000_000.0))


def _real_wallet_balance(user_headers) -> float:
    r = requests.get(f"{API}/wallet/v2/summary", headers=user_headers, timeout=10)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    return float(body.get("available") or body.get("balance") or 0.0)


# ------------------------------------------------------------------ #
# 1. User-initiated reset                                            #
# ------------------------------------------------------------------ #
class TestUserDemoReset:
    def test_open_position_then_reset(self, user_headers, admin_headers):
        default_bal = _default_demo_balance(admin_headers)
        real_before = _real_wallet_balance(user_headers)

        # Open a demo position so the reset has something to close
        r = requests.post(f"{API}/forex/positions", headers=user_headers,
                          json={"symbol_id": "EURUSD", "side": "buy", "lot_size": 0.1},
                          timeout=15)
        position_opened = r.status_code == 200

        r = requests.post(f"{API}/demo/reset", headers=user_headers, timeout=15)
        assert r.status_code == 200, r.text[:300]
        rec = r.json()
        assert rec["new_balance"] == pytest.approx(default_bal)
        assert rec["currency"] == "INR"
        assert rec["initiated_by"]["kind"] == "user"
        assert "reset_id" in rec
        if position_opened:
            assert rec["positions_closed"] >= 1

        # Balance restored
        r = requests.get(f"{API}/forex/balance", headers=user_headers, timeout=10)
        assert r.status_code == 200
        assert float(r.json()["balance"]) == pytest.approx(default_bal)
        assert r.json()["currency"] == "INR"

        # No open positions; closed list is a fresh session (archived hidden)
        r = requests.get(f"{API}/forex/positions", headers=user_headers,
                         params={"status": "open"}, timeout=10)
        assert r.status_code == 200 and r.json() == []
        r = requests.get(f"{API}/forex/positions", headers=user_headers,
                         params={"status": "closed"}, timeout=10)
        assert r.status_code == 200 and r.json() == []

        # Equity/margin/free-margin reset
        r = requests.get(f"{API}/forex/equity", headers=user_headers, timeout=10)
        assert r.status_code == 200
        eq = r.json()
        assert eq["balance"] == pytest.approx(default_bal)
        assert eq["equity"] == pytest.approx(default_bal)
        assert eq["margin_used"] == 0
        assert eq["unrealized_pnl"] == 0
        assert eq["open_position_count"] == 0

        # History = new session: only the demo_reset marker remains visible
        r = requests.get(f"{API}/forex/history", headers=user_headers, timeout=10)
        assert r.status_code == 200
        events = [h.get("event") for h in r.json()]
        assert "open" not in events and "close" not in events
        assert "demo_reset" in events

        # REAL wallet untouched
        assert _real_wallet_balance(user_headers) == pytest.approx(real_before)

    def test_reset_history_recorded(self, user_headers):
        r = requests.get(f"{API}/demo/reset/history", headers=user_headers, timeout=10)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        latest = items[0]
        for field in ("reset_id", "previous_balance", "new_balance", "initiated_by", "ts"):
            assert field in latest

    def test_copy_trading_summary_clean_after_reset(self, user_headers):
        r = requests.get(f"{API}/copy_trading/my/summary", headers=user_headers, timeout=10)
        if r.status_code != 200:
            pytest.skip("copy trading summary unavailable")
        body = r.json()
        assert body["open_positions"] == 0


# ------------------------------------------------------------------ #
# 2. Admin-initiated reset                                           #
# ------------------------------------------------------------------ #
class TestAdminDemoReset:
    def test_admin_reset_for_user(self, admin_headers, user_headers, user_id):
        default_bal = _default_demo_balance(admin_headers)
        real_before = _real_wallet_balance(user_headers)

        r = requests.post(f"{API}/admin/demo/reset/{user_id}", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text[:300]
        rec = r.json()
        assert rec["initiated_by"]["kind"] == "admin"
        assert rec["new_balance"] == pytest.approx(default_bal)

        # Admin can see reset history for this user
        r = requests.get(f"{API}/admin/demo/reset/history",
                         headers=admin_headers, params={"user_id": user_id}, timeout=10)
        assert r.status_code == 200
        assert any(i["reset_id"] == rec["reset_id"] for i in r.json()["items"])

        # REAL wallet untouched
        assert _real_wallet_balance(user_headers) == pytest.approx(real_before)

    def test_admin_reset_unknown_user_404(self, admin_headers):
        r = requests.post(f"{API}/admin/demo/reset/usr_does_not_exist",
                          headers=admin_headers, timeout=10)
        assert r.status_code == 404


# ------------------------------------------------------------------ #
# 3. Configurable default balance                                    #
# ------------------------------------------------------------------ #
class TestConfigurableDefault:
    def test_reset_uses_admin_configured_default(self, admin_headers, user_headers):
        original = _default_demo_balance(admin_headers)
        new_default = 500_000.0
        try:
            r = requests.put(f"{API}/admin/forex/settings", headers=admin_headers,
                             json={"default_demo_balance": new_default}, timeout=10)
            assert r.status_code == 200
            r = requests.post(f"{API}/demo/reset", headers=user_headers, timeout=15)
            assert r.status_code == 200
            assert r.json()["new_balance"] == pytest.approx(new_default)
        finally:
            requests.put(f"{API}/admin/forex/settings", headers=admin_headers,
                         json={"default_demo_balance": original}, timeout=10)
            requests.post(f"{API}/demo/reset", headers=user_headers, timeout=15)


# ------------------------------------------------------------------ #
# 4. Guards                                                          #
# ------------------------------------------------------------------ #
class TestGuards:
    def test_user_reset_requires_auth(self):
        r = requests.post(f"{API}/demo/reset", timeout=10)
        assert r.status_code in (401, 403)

    def test_admin_reset_requires_admin_token(self, user_headers):
        r = requests.post(f"{API}/admin/demo/reset/anything", headers=user_headers, timeout=10)
        assert r.status_code in (401, 403)

    def test_legacy_forex_reset_delegates(self, user_headers, admin_headers):
        default_bal = _default_demo_balance(admin_headers)
        r = requests.post(f"{API}/forex/balance/reset", headers=user_headers, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert float(body["balance"]) == pytest.approx(default_bal)
        assert "reset_id" in body
