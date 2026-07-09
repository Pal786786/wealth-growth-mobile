"""Sprint 7B.2 — Copy Execution Engine backend tests.

Covers:
  - /meta shape (defaults, modes, simulator, trader_count)
  - MasterSimulator liveness (master trades generated)
  - Copy lifecycle w/ fresh signed-up user (start / get / update / pause / resume / stop)
  - Fan-out execution (force_open -> mirrored follower trade)
  - Modes: multiplier, fixed_lot, equity_percent (lot computation)
  - /my/summary, /my/copies enrichment, /my/trades filtering
  - Bulk actions: pause-all, resume-all, close-all
  - Admin simulation control (status / pause / resume / speed / force-open / force-close)
  - Admin config (get / put defaults)
  - Regression on unrelated endpoints (/wallet, /notifications, /forex/symbols,
    /market/dashboard, /auth/me)
  - Event-driven mirroring assertion (fan-out via force-open triggers follower trade
    within a few seconds, no scheduled sweep).
"""
from __future__ import annotations
import os
import random
import string
import time
from typing import Any, Dict, List, Optional

import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL"))
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL not set"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mfb.in"
ADMIN_PASS = "Admin@MFB2026"

SCALPER = "hana_tanaka"
SWING = "marcus_wolfe"


# ------------------------- fixtures -------------------------
@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _rand_suffix(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


@pytest.fixture(scope="module")
def user_ctx(api_client) -> Dict[str, str]:
    """Create a fresh user via /auth/signup and return {token, headers}."""
    sfx = _rand_suffix()
    mobile = "9" + "".join(random.choices(string.digits, k=9))
    payload = {
        "full_name": f"CopyTest {sfx}",
        "email": f"copytest_{sfx}@mfb.in",
        "mobile": mobile,
        "password": "Test@1234",
    }
    r = api_client.post(f"{API}/auth/signup", json=payload, timeout=20)
    assert r.status_code == 200, f"signup failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    token = body.get("token") or body.get("access_token")
    assert token, f"no token in signup response: {list(body.keys())}"
    return {
        "token": token,
        "headers": {"Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"},
        "email": payload["email"],
    }


@pytest.fixture(scope="module")
def admin_headers(api_client) -> Dict[str, str]:
    r = api_client.post(f"{API}/admin/auth/login",
                        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=20)
    if r.status_code != 200:
        r = api_client.post(f"{API}/admin/login",
                            json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    tok = body.get("token") or body.get("access_token") or body.get("admin_token")
    assert tok, f"no token in admin login: {body}"
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ------------------------- META -------------------------
class TestMeta:
    def test_meta_defaults_and_sim(self, api_client):
        r = api_client.get(f"{API}/copy_trading/meta")
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert d["trader_count"] == 28
        assert d["broker"] == "paper"
        assert set(d["modes"]) == {"fixed_lot", "multiplier", "equity_percent"}
        ds = d["default_settings"]
        # Required defaults per Sprint 7B.2 spec
        assert ds["max_daily_loss_pct"] == 10
        assert ds["max_drawdown_pct"] == 20
        assert ds["max_open_trades"] == 10
        assert ds["equity_protection_pct"] == 30
        assert ds["mode"] == "multiplier"
        sim = d["simulator"]
        assert sim["enabled"] is True
        assert sim["speed"] in ("slow", "normal", "fast")


# ------------------------- SIMULATOR RUNNING -------------------------
class TestSimulatorRunning:
    def test_hana_scalper_has_master_trades(self, api_client):
        """Hana Tanaka is a Scalper (30–90s interval). After backend has been
        running a while, we should see at least one master trade for her
        within a reasonable wait. We poll up to ~100s.
        """
        deadline = time.time() + 100
        while time.time() < deadline:
            r = api_client.get(
                f"{API}/copy_trading/traders/{SCALPER}/master-trades",
                params={"limit": 5})
            assert r.status_code == 200, r.text[:200]
            trades = r.json().get("trades") or []
            if len(trades) > 0:
                # Assert shape
                t = trades[0]
                for f in ("master_id", "trader_id", "symbol", "side",
                          "lot_size", "entry_price", "status"):
                    assert f in t, f"missing {f} in master trade"
                assert t["trader_id"] == SCALPER
                assert t["side"] in ("buy", "sell")
                return
            time.sleep(5)
        pytest.fail("No master trades for scalper hana_tanaka in 100s — simulator may be idle")


# ------------------------- COPY LIFECYCLE -------------------------
class TestCopyLifecycle:
    def test_start_copy(self, api_client, user_ctx):
        r = api_client.post(
            f"{API}/copy_trading/traders/{SCALPER}/copy/start",
            headers=user_ctx["headers"],
            json={"settings": {"mode": "multiplier", "multiplier": 1.5,
                               "max_open_trades": 3}},
        )
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["status"] == "active"
        assert d["settings"]["mode"] == "multiplier"
        assert d["settings"]["multiplier"] == 1.5
        assert d["settings"]["max_open_trades"] == 3
        # defaults merged
        assert d["settings"]["max_daily_loss_pct"] == 10.0
        assert d["settings"]["max_drawdown_pct"] == 20.0
        assert d.get("copy_id"), "copy_id missing"
        assert d.get("starting_equity_usd") == 10000

    def test_update_settings_persistence(self, api_client, user_ctx):
        r = api_client.put(
            f"{API}/copy_trading/traders/{SCALPER}/copy/settings",
            headers=user_ctx["headers"],
            json={"multiplier": 2.0, "max_daily_loss_pct": 15},
        )
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert d["settings"]["multiplier"] == 2.0
        assert d["settings"]["max_daily_loss_pct"] == 15.0
        # verify via GET
        r2 = api_client.get(f"{API}/copy_trading/traders/{SCALPER}/copy",
                            headers=user_ctx["headers"])
        assert r2.status_code == 200
        assert r2.json()["settings"]["multiplier"] == 2.0
        assert r2.json()["settings"]["max_daily_loss_pct"] == 15.0

    def test_pause(self, api_client, user_ctx):
        r = api_client.post(f"{API}/copy_trading/traders/{SCALPER}/copy/pause",
                            headers=user_ctx["headers"])
        assert r.status_code == 200
        assert r.json()["status"] == "paused"

    def test_resume(self, api_client, user_ctx):
        r = api_client.post(f"{API}/copy_trading/traders/{SCALPER}/copy/resume",
                            headers=user_ctx["headers"])
        assert r.status_code == 200
        assert r.json()["status"] == "active"


# ------------------------- FAN-OUT / MIRRORING (deterministic via force-open) -------------------------
class TestFanOut:
    """Deterministic: use admin force-open to synchronously drive a master trade
    and verify a follower trade is created."""

    def test_fanout_via_force_open(self, api_client, user_ctx, admin_headers):
        # Ensure copy is active on SCALPER (redundant safety)
        api_client.post(f"{API}/copy_trading/traders/{SCALPER}/copy/resume",
                        headers=user_ctx["headers"])
        # Count follower trades before
        r0 = api_client.get(f"{API}/copy_trading/my/trades",
                            params={"trader_id": SCALPER},
                            headers=user_ctx["headers"])
        assert r0.status_code == 200
        before = len(r0.json().get("trades") or [])

        # Force-open a buy master trade on SCALPER
        r = api_client.post(f"{API}/copy_trading/admin/simulation/force-open",
                            headers=admin_headers,
                            json={"trader_id": SCALPER, "side": "buy"})
        assert r.status_code == 200, r.text[:200]
        mt = r.json().get("master_trade")
        assert mt and mt["trader_id"] == SCALPER
        assert mt["side"] == "buy"
        assert mt["status"] == "open"
        master_id = mt["master_id"]

        # Poll for follower mirror trade
        deadline = time.time() + 20
        follower = None
        while time.time() < deadline:
            r2 = api_client.get(f"{API}/copy_trading/my/trades",
                                params={"trader_id": SCALPER},
                                headers=user_ctx["headers"])
            trades = r2.json().get("trades") or []
            for t in trades:
                if t.get("master_id") == master_id:
                    follower = t
                    break
            if follower:
                break
            time.sleep(1.5)
        assert follower, (
            f"No follower trade mirrored for master {master_id} within 20s — "
            f"fan-out via EventBus appears broken")
        # multiplier=2.0, master_lot roughly avg_lot*(0.7..1.3), should be capped at 5.0
        assert follower["symbol"] == mt["symbol"]
        assert follower["side"] == "buy"
        assert follower["lot_size"] > 0
        # roughly multiplier * master lot (within 1% due to rounding)
        expected = round(mt["lot_size"] * 2.0, 2)
        expected_clamped = min(5.0, max(0.01, expected))
        assert abs(follower["lot_size"] - expected_clamped) <= 0.02, (
            f"expected ~{expected_clamped}, got {follower['lot_size']}")

        # Now force-close and verify follower closes too
        r3 = api_client.post(
            f"{API}/copy_trading/admin/simulation/force-close/{master_id}",
            headers=admin_headers)
        assert r3.status_code == 200, r3.text[:200]
        # Poll for close propagation
        deadline = time.time() + 20
        while time.time() < deadline:
            r4 = api_client.get(f"{API}/copy_trading/my/trades",
                                params={"trader_id": SCALPER},
                                headers=user_ctx["headers"])
            trades = r4.json().get("trades") or []
            for t in trades:
                if t.get("master_id") == master_id and t.get("status") == "closed":
                    assert t.get("pnl_usd") is not None, "closed trade missing pnl_usd"
                    return
            time.sleep(1.5)
        pytest.fail(
            f"Follower trade for master {master_id} was not closed after force-close")


# ------------------------- SUMMARY / COPIES ENRICHMENT / TRADES -------------------------
class TestAggregations:
    def test_summary_shape(self, api_client, user_ctx):
        r = api_client.get(f"{API}/copy_trading/my/summary",
                           headers=user_ctx["headers"])
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        for f in ("total_pnl_usd", "today_pnl_usd", "today_trades",
                  "open_positions", "active_copies", "paused_copies",
                  "halted_copies", "total_trades", "win_rate_pct"):
            assert f in d, f"summary missing {f}"

    def test_my_copies_enriched(self, api_client, user_ctx):
        r = api_client.get(f"{API}/copy_trading/my/copies",
                           headers=user_ctx["headers"])
        assert r.status_code == 200
        copies = r.json().get("copies") or []
        assert any(c["trader_id"] == SCALPER for c in copies)
        c = next(x for x in copies if x["trader_id"] == SCALPER)
        assert "live" in c
        for f in ("open_positions", "lifetime_pnl_usd", "today_pnl_usd",
                  "starting_equity_usd", "current_equity_usd"):
            assert f in c["live"], f"live missing {f}"
        assert "trader" in c and c["trader"]
        for f in ("name", "avatar_url", "style"):
            assert f in c["trader"], f"trader summary missing {f}"


# ------------------------- MODES: fixed_lot & equity_percent -------------------------
class TestExecutionModes:
    def test_fixed_lot_mode(self, api_client, user_ctx, admin_headers):
        # Start copy on SWING (marcus_wolfe) with fixed_lot mode
        r = api_client.post(
            f"{API}/copy_trading/traders/{SWING}/copy/start",
            headers=user_ctx["headers"],
            json={"settings": {"mode": "fixed_lot", "fixed_lot": 0.5}},
        )
        assert r.status_code == 200, r.text[:200]
        assert r.json()["settings"]["mode"] == "fixed_lot"
        assert r.json()["settings"]["fixed_lot"] == 0.5

        # Force-open on SWING
        r2 = api_client.post(f"{API}/copy_trading/admin/simulation/force-open",
                             headers=admin_headers,
                             json={"trader_id": SWING, "side": "sell"})
        assert r2.status_code == 200
        mt = r2.json()["master_trade"]
        master_id = mt["master_id"]

        deadline = time.time() + 20
        follower = None
        while time.time() < deadline:
            r3 = api_client.get(f"{API}/copy_trading/my/trades",
                                params={"trader_id": SWING},
                                headers=user_ctx["headers"])
            for t in (r3.json().get("trades") or []):
                if t.get("master_id") == master_id:
                    follower = t
                    break
            if follower:
                break
            time.sleep(1.5)
        assert follower, "fixed_lot fan-out failed"
        # fixed_lot mode → lot ~ 0.5 (respecting min/max caps)
        assert abs(follower["lot_size"] - 0.5) <= 0.02, (
            f"fixed_lot expected ~0.5, got {follower['lot_size']}")
        # cleanup: close it
        api_client.post(
            f"{API}/copy_trading/admin/simulation/force-close/{master_id}",
            headers=admin_headers)

    def test_equity_percent_mode(self, api_client, user_ctx, admin_headers):
        r = api_client.post(
            f"{API}/copy_trading/traders/{SWING}/copy/start",
            headers=user_ctx["headers"],
            json={"settings": {"mode": "equity_percent", "equity_percent": 2}},
        )
        assert r.status_code == 200
        assert r.json()["settings"]["mode"] == "equity_percent"
        assert r.json()["settings"]["equity_percent"] == 2.0

        r2 = api_client.post(f"{API}/copy_trading/admin/simulation/force-open",
                             headers=admin_headers,
                             json={"trader_id": SWING, "side": "buy"})
        assert r2.status_code == 200
        mt = r2.json()["master_trade"]
        master_id = mt["master_id"]

        deadline = time.time() + 20
        follower = None
        while time.time() < deadline:
            r3 = api_client.get(f"{API}/copy_trading/my/trades",
                                params={"trader_id": SWING},
                                headers=user_ctx["headers"])
            for t in (r3.json().get("trades") or []):
                if t.get("master_id") == master_id:
                    follower = t
                    break
            if follower:
                break
            time.sleep(1.5)
        assert follower, "equity_percent fan-out failed"
        # equity_percent: (10000 * 0.02) / 100_000 * max(1, master_lot) = 0.002 * master_lot
        # After clamping to min_lot=0.01 -> should equal 0.01
        assert follower["lot_size"] >= 0.01, f"got {follower['lot_size']}"
        assert follower["lot_size"] <= 5.0
        api_client.post(
            f"{API}/copy_trading/admin/simulation/force-close/{master_id}",
            headers=admin_headers)


# ------------------------- BULK OPERATIONS -------------------------
class TestBulkOps:
    def test_pause_resume_close_all(self, api_client, user_ctx):
        # Ensure both copies are active
        api_client.post(f"{API}/copy_trading/traders/{SCALPER}/copy/start",
                        headers=user_ctx["headers"],
                        json={"settings": {"mode": "multiplier", "multiplier": 1.0}})
        api_client.post(f"{API}/copy_trading/traders/{SWING}/copy/start",
                        headers=user_ctx["headers"],
                        json={"settings": {"mode": "multiplier", "multiplier": 1.0}})

        r = api_client.post(f"{API}/copy_trading/my/copies/pause-all",
                            headers=user_ctx["headers"])
        assert r.status_code == 200
        assert r.json().get("paused") >= 2

        r2 = api_client.post(f"{API}/copy_trading/my/copies/resume-all",
                             headers=user_ctx["headers"])
        assert r2.status_code == 200
        assert r2.json().get("resumed") >= 2

        r3 = api_client.post(f"{API}/copy_trading/my/copies/close-all",
                             headers=user_ctx["headers"])
        assert r3.status_code == 200
        # verify statuses
        r4 = api_client.get(f"{API}/copy_trading/my/copies",
                            headers=user_ctx["headers"])
        for c in r4.json().get("copies") or []:
            assert c["status"] == "stopped", f"{c['trader_id']} still {c['status']}"


# ------------------------- INDIVIDUAL STOP -------------------------
class TestStop:
    def test_stop_scalper(self, api_client, user_ctx):
        # Restart it first
        api_client.post(f"{API}/copy_trading/traders/{SCALPER}/copy/start",
                        headers=user_ctx["headers"],
                        json={"settings": {"mode": "multiplier", "multiplier": 1.0}})
        r = api_client.post(f"{API}/copy_trading/traders/{SCALPER}/copy/stop",
                            headers=user_ctx["headers"])
        assert r.status_code == 200
        assert r.json()["status"] == "stopped"


# ------------------------- ADMIN SIMULATION CONTROLS -------------------------
class TestAdminSimulation:
    def test_status(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/simulation/status",
                           headers=admin_headers)
        assert r.status_code == 200, r.text[:200]
        s = r.json()
        for f in ("enabled", "speed", "active_traders",
                  "open_master_trades", "lifetime_master_trades"):
            assert f in s, f"status missing {f}"
        # Roughly 28 traders
        assert s["active_traders"] >= 20, f"active_traders={s['active_traders']}"

    def test_pause_resume_toggle(self, api_client, admin_headers):
        r = api_client.post(f"{API}/copy_trading/admin/simulation/pause",
                            headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["enabled"] is False
        r2 = api_client.post(f"{API}/copy_trading/admin/simulation/resume",
                             headers=admin_headers)
        assert r2.status_code == 200
        assert r2.json()["enabled"] is True

    def test_set_speed(self, api_client, admin_headers):
        r = api_client.post(f"{API}/copy_trading/admin/simulation/speed",
                            headers=admin_headers, json={"speed": "fast"})
        assert r.status_code == 200, r.text[:200]
        assert r.json()["speed"] == "fast"
        # Restore to normal so we don't stress the DB across CI
        api_client.post(f"{API}/copy_trading/admin/simulation/speed",
                        headers=admin_headers, json={"speed": "normal"})

    def test_admin_config_defaults_get_and_put(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/config",
                           headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert "defaults" in body and "sim" in body
        original = body["defaults"].get("max_daily_loss_pct", 10.0)
        # PUT change to 8, verify, then restore
        r2 = api_client.put(f"{API}/copy_trading/admin/config/defaults",
                            headers=admin_headers,
                            json={"max_daily_loss_pct": 8})
        assert r2.status_code == 200
        merged = r2.json()["defaults"]
        assert merged["max_daily_loss_pct"] == 8.0
        # Restore
        api_client.put(f"{API}/copy_trading/admin/config/defaults",
                       headers=admin_headers,
                       json={"max_daily_loss_pct": original})


# ------------------------- REGRESSION -------------------------
class TestRegression:
    def test_auth_me(self, api_client, user_ctx):
        r = api_client.get(f"{API}/auth/me", headers=user_ctx["headers"])
        assert r.status_code == 200, r.text[:200]

    def test_wallet(self, api_client, user_ctx):
        r = api_client.get(f"{API}/wallet", headers=user_ctx["headers"])
        assert r.status_code == 200

    def test_notifications(self, api_client, user_ctx):
        r = api_client.get(f"{API}/notifications", headers=user_ctx["headers"])
        assert r.status_code == 200

    def test_forex_symbols(self, api_client):
        r = api_client.get(f"{API}/forex/symbols")
        assert r.status_code == 200

    def test_market_dashboard(self, api_client):
        r = api_client.get(f"{API}/market/dashboard")
        assert r.status_code == 200
