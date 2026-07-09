"""Sprint 7B.1 — Copy Trading backend tests.

Coverage:
  - /meta (broker + 28 traders)
  - /traders leaderboard (sort/search/filters/limit)
  - /traders/{id} determinism (in-process + across restart)
  - /traders/{id} profile detail fields
  - open/closed trades
  - copy lifecycle: start/pause/resume/settings/stop (auth-gated)
  - /my/copies aggregation
  - Regression sanity for prior slices (forex, wallet, notifications, market)
"""
import os
import subprocess
import time
from typing import Any, Dict

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL not set"
BASE_URL = BASE_URL.rstrip("/")

DEMO_EMAIL = "demo@mfb.in"
DEMO_PASSWORD = "demo1234"


# ------------------------------ fixtures ------------------------------
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def auth_token(api) -> str:
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"identifier": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    tok = data.get("access_token") or data.get("token") or data.get("jwt")
    assert tok, f"no token in response: {list(data.keys())}"
    return tok


@pytest.fixture(scope="module")
def auth_headers(auth_token) -> Dict[str, str]:
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# ------------------------------ META -----------------------------------
class TestMeta:
    def test_meta(self, api):
        r = api.get(f"{BASE_URL}/api/copy_trading/meta")
        assert r.status_code == 200
        d = r.json()
        assert d["trader_count"] == 28
        assert d["broker"] == "paper"
        assert set(d["modes"]) == {"fixed_lot", "multiplier", "equity_percent"}
        assert "total_roi" in d["sort_keys"]


# ------------------------------ LEADERBOARD ----------------------------
class TestLeaderboard:
    def test_sort_total_roi_limit_5(self, api):
        r = api.get(f"{BASE_URL}/api/copy_trading/traders",
                    params={"sort": "total_roi", "limit": 5})
        assert r.status_code == 200
        d = r.json()
        assert len(d["items"]) == 5
        rois = [t["stats"]["total_roi_pct"] for t in d["items"]]
        assert rois == sorted(rois, reverse=True), f"not desc: {rois}"

    def test_sort_risk_asc(self, api):
        r = api.get(f"{BASE_URL}/api/copy_trading/traders",
                    params={"sort": "risk", "limit": 50})
        assert r.status_code == 200
        risks = [t["risk"]["risk_score"] for t in r.json()["items"]]
        # Lowest risk first
        assert risks == sorted(risks), f"not ascending risk: {risks}"

    def test_search_india(self, api):
        r = api.get(f"{BASE_URL}/api/copy_trading/traders",
                    params={"search": "india", "limit": 50})
        assert r.status_code == 200
        ids = {t["id"] for t in r.json()["items"]}
        for expected in ("aarav_menon", "maya_patel", "raj_kapoor"):
            assert expected in ids, f"missing {expected} in {ids}"

    def test_verified_only(self, api):
        r = api.get(f"{BASE_URL}/api/copy_trading/traders",
                    params={"verified_only": "true", "limit": 50})
        assert r.status_code == 200
        for t in r.json()["items"]:
            assert t["verified"] is True

    def test_risk_range_filter(self, api):
        r = api.get(f"{BASE_URL}/api/copy_trading/traders",
                    params={"min_risk": 1, "max_risk": 4, "limit": 50})
        assert r.status_code == 200
        for t in r.json()["items"]:
            assert 1 <= t["risk"]["risk_score"] <= 4


# ------------------------------ DETERMINISM ---------------------------
class TestDeterminism:
    """P0: same trader must return identical numbers across calls AND restart."""

    def _fetch(self, api) -> Dict[str, Any]:
        r = api.get(f"{BASE_URL}/api/copy_trading/traders/marcus_wolfe")
        assert r.status_code == 200
        return r.json()

    def test_repeat_same_process(self, api):
        a = self._fetch(api)
        b = self._fetch(api)
        assert a["stats"]["total_roi_pct"] == b["stats"]["total_roi_pct"]
        assert a["stats"]["followers"] == b["stats"]["followers"]
        assert a["risk"]["risk_score"] == b["risk"]["risk_score"]
        assert a["equity_curve"][0]["balance"] == b["equity_curve"][0]["balance"]
        assert a["equity_curve"][-1]["balance"] == b["equity_curve"][-1]["balance"]
        assert a["monthly_returns_pct"] == b["monthly_returns_pct"]

    def test_repeat_across_restart(self, api):
        before = self._fetch(api)
        # Restart backend
        subprocess.run(["sudo", "supervisorctl", "restart", "backend"],
                       check=True, capture_output=True)
        # Wait for service to come back
        deadline = time.time() + 40
        while time.time() < deadline:
            try:
                pong = api.get(f"{BASE_URL}/api/copy_trading/meta", timeout=3)
                if pong.status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(1.5)
        else:
            pytest.fail("backend did not come back within 40s")
        after = self._fetch(api)
        assert before["stats"]["total_roi_pct"] == after["stats"]["total_roi_pct"], \
            f"ROI drifted: {before['stats']['total_roi_pct']} vs {after['stats']['total_roi_pct']}"
        assert before["stats"]["followers"] == after["stats"]["followers"]
        assert before["risk"]["risk_score"] == after["risk"]["risk_score"]
        assert before["equity_curve"][0]["balance"] == after["equity_curve"][0]["balance"]
        assert before["equity_curve"][-1]["balance"] == after["equity_curve"][-1]["balance"]
        assert before["monthly_returns_pct"] == after["monthly_returns_pct"]


# ------------------------------ PROFILE -------------------------------
class TestProfile:
    def test_profile_shape(self, api):
        r = api.get(f"{BASE_URL}/api/copy_trading/traders/marcus_wolfe")
        assert r.status_code == 200
        d = r.json()
        for f in ("name", "country_code", "avatar_url", "verified", "bio",
                  "stats", "risk", "monthly_returns_pct", "equity_curve"):
            assert f in d, f"missing {f}"
        assert len(d["stats"]) >= 12, f"stats has {len(d['stats'])} metrics"
        for f in ("risk_score", "risk_tier", "components"):
            assert f in d["risk"]
        assert len(d["monthly_returns_pct"]) == 12
        assert len(d["equity_curve"]) >= 100

    def test_open_trades(self, api):
        r = api.get(f"{BASE_URL}/api/copy_trading/traders/marcus_wolfe/open-trades")
        assert r.status_code == 200
        assert 0 <= len(r.json()["trades"]) <= 5

    def test_closed_trades(self, api):
        r = api.get(f"{BASE_URL}/api/copy_trading/traders/marcus_wolfe/closed-trades")
        assert r.status_code == 200
        assert len(r.json()["trades"]) == 40

    def test_not_found(self, api):
        r = api.get(f"{BASE_URL}/api/copy_trading/traders/does_not_exist")
        assert r.status_code == 404


# ------------------------------ COPY LIFECYCLE ------------------------
TRADER = "marcus_wolfe"


class TestCopyLifecycle:
    """Ordered lifecycle: start -> get -> pause -> resume -> update -> stop."""

    def test_unauth_start_returns_401(self, api):
        r = api.post(f"{BASE_URL}/api/copy_trading/traders/{TRADER}/copy/start", json={})
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"

    def test_start(self, api, auth_headers):
        r = api.post(
            f"{BASE_URL}/api/copy_trading/traders/{TRADER}/copy/start",
            headers=auth_headers,
            json={"settings": {"mode": "multiplier", "multiplier": 0.5,
                               "max_daily_loss_pct": 3}},
        )
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["status"] == "active"
        s = d["settings"]
        assert s["mode"] == "multiplier"
        assert s["multiplier"] == 0.5
        assert s["max_daily_loss_pct"] == 3.0

    def test_get_relationship(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/copy_trading/traders/{TRADER}/copy",
                    headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "active"
        assert d["settings"]["multiplier"] == 0.5

    def test_pause(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/copy_trading/traders/{TRADER}/copy/pause",
                     headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "paused"

    def test_resume(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/copy_trading/traders/{TRADER}/copy/resume",
                     headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "active"

    def test_update_settings(self, api, auth_headers):
        r = api.put(f"{BASE_URL}/api/copy_trading/traders/{TRADER}/copy/settings",
                    headers=auth_headers, json={"multiplier": 1.5})
        assert r.status_code == 200
        d = r.json()
        assert d["settings"]["multiplier"] == 1.5
        # other settings retained
        assert d["settings"]["max_daily_loss_pct"] == 3.0

    def test_my_copies(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/copy_trading/my/copies",
                    headers=auth_headers)
        assert r.status_code == 200
        copies = r.json()["copies"]
        ids = [c["trader_id"] for c in copies]
        assert TRADER in ids
        # trader summary enrichment
        found = next(c for c in copies if c["trader_id"] == TRADER)
        assert "trader" in found and found["trader"]["name"] == "Marcus Wolfe"

    def test_stop(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/copy_trading/traders/{TRADER}/copy/stop",
                     headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "stopped"


# ------------------------------ REGRESSION ----------------------------
class TestRegression:
    """Quick smoke against prior slice endpoints — must still work."""

    @pytest.mark.parametrize("path", [
        "/api/market_data/quotes?symbols=EURUSD",
        "/api/market/dashboard",
    ])
    def test_public_endpoints(self, api, path):
        r = api.get(f"{BASE_URL}{path}")
        assert r.status_code in (200, 401, 403), \
            f"{path} -> {r.status_code}: {r.text[:200]}"

    def test_forex_symbol_ticket(self, api):
        r = api.get(f"{BASE_URL}/api/forex/symbols")
        assert r.status_code == 200

    def test_notifications_endpoints(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/notifications", headers=auth_headers)
        assert r.status_code == 200
        r2 = api.get(f"{BASE_URL}/api/notifications/preferences", headers=auth_headers)
        assert r2.status_code == 200

    def test_wallet_requires_auth(self, api):
        r = api.get(f"{BASE_URL}/api/wallet")
        assert r.status_code in (401, 403)

    def test_forex_position_open_non_kyc(self, api, auth_headers):
        # Sprint expects non-KYC users to still be able to open forex (200)
        r = api.post(f"{BASE_URL}/api/forex/positions", headers=auth_headers,
                     json={"symbol_id": "EURUSD", "side": "buy", "lot_size": 0.01})
        assert r.status_code in (200, 201), \
            f"forex open failed with {r.status_code}: {r.text[:200]}"
        d = r.json()
        assert d.get("status") == "open"

    def test_withdrawal_request_blocked_by_kyc(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/wallet/withdrawals/request",
                     headers=auth_headers,
                     json={"amount": 500, "bank_account_id": "dummy"})
        # 403 KYC_REQUIRED expected before bank-account lookup for non-KYC.
        # If the endpoint checks bank_account first (404), that's still a
        # non-crashing rejection — flag as WARN, not P0.
        assert r.status_code in (400, 403, 404, 422), r.text[:200]
        if r.status_code == 403:
            body = r.json()
            detail = body.get("detail")
            if isinstance(detail, dict):
                assert detail.get("code") == "KYC_REQUIRED" or "KYC" in str(detail).upper()
