"""Sprint 7B.3 — Admin Copy Trading Console backend tests.

Covers:
  - /copy_trading/meta baseline (28 traders, styles, approval_levels, categories, risk_tiers, simulator)
  - Trader Management: list, filter by category/approval, get, create custom, update overlays,
    update custom, verify/unverify, disable/enable, reset-overlay, delete rules
  - Simulation Panel: status, pause/resume, speed valid/invalid, force-open/force-close
  - Master Trade Explorer: list with followers_copied, filter by status/trader
  - Follower Monitor: summary, drill-in with signed-up user
  - Analytics: full nested structure
  - System Health: full field set
  - Configuration: get + PUT defaults persistence
  - Regression: /wallet, /notifications, /forex/*, /market/*, /auth/me
  - Regression 7B.2: /my/copies, /my/summary, start-copy
  - Custom trader simulator pickup (force-open on custom → follower trade)
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

SYSTEM_TRADER_1 = "marcus_wolfe"
SYSTEM_TRADER_2 = "aarav_menon"
SYSTEM_TRADER_3 = "hana_tanaka"


# ------------------------- fixtures -------------------------
@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _rand_suffix(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


@pytest.fixture(scope="module")
def admin_headers(api_client) -> Dict[str, str]:
    r = api_client.post(f"{API}/admin/login",
                        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("token")
    assert tok, f"no admin token: {r.json()}"
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def user_ctx(api_client) -> Dict[str, Any]:
    sfx = _rand_suffix()
    mobile = "9" + "".join(random.choices(string.digits, k=9))
    payload = {
        "full_name": f"AdmTest {sfx}",
        "email": f"admtest_{sfx}@mfb.in",
        "mobile": mobile,
        "password": "Test@1234",
    }
    r = api_client.post(f"{API}/auth/signup", json=payload, timeout=20)
    assert r.status_code == 200, f"signup: {r.status_code} {r.text[:200]}"
    body = r.json()
    tok = body.get("token") or body.get("access_token")
    assert tok
    return {
        "token": tok,
        "headers": {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        "user": body.get("user", {}),
        "email": payload["email"],
    }


@pytest.fixture(scope="module")
def state() -> Dict[str, Any]:
    return {}


# ------------------------- META -------------------------
class TestMeta:
    def test_meta_baseline(self, api_client):
        r = api_client.get(f"{API}/copy_trading/meta")
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert d["trader_count"] == 28, f"trader_count={d['trader_count']}"
        assert isinstance(d["styles"], list) and len(d["styles"]) == 10, f"styles={d['styles']}"
        assert list(d["approval_levels"]) == ["verified", "professional", "elite", "master"]
        assert list(d["categories"]) == ["system", "verified", "custom", "disabled"]
        assert isinstance(d["risk_tiers"], list) and len(d["risk_tiers"]) >= 3
        sim = d["simulator"]
        assert "enabled" in sim and "speed" in sim


# ------------------------- TRADER MANAGEMENT -------------------------
class TestTraderManagementList:
    def test_list_default_28(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/traders",
                           headers=admin_headers, params={"limit": 200})
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert d["total"] == 28, f"expected 28, got {d['total']}"
        # Every item is system, visible, not disabled, has stats/risk/approval_level
        for item in d["items"]:
            assert item["kind"] == "system"
            assert item.get("visible") is True
            assert item.get("disabled") is False
            assert "approval_level" in item
            assert "stats" in item and "risk" in item

    def test_filter_category_system(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/traders",
                           headers=admin_headers,
                           params={"category": "system", "limit": 200})
        assert r.status_code == 200
        assert r.json()["total"] == 28

    def test_filter_category_custom(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/traders",
                           headers=admin_headers,
                           params={"category": "custom", "limit": 200})
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_filter_category_verified(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/traders",
                           headers=admin_headers,
                           params={"category": "verified", "limit": 200})
        assert r.status_code == 200
        d = r.json()
        assert d["total"] > 0
        for t in d["items"]:
            assert t.get("verified") is True

    def test_filter_category_disabled_empty(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/traders",
                           headers=admin_headers,
                           params={"category": "disabled", "limit": 200})
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_get_single_trader_with_curve(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/traders/{SYSTEM_TRADER_1}",
                           headers=admin_headers)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert d["id"] == SYSTEM_TRADER_1
        assert "equity_curve" in d and isinstance(d["equity_curve"], list) and len(d["equity_curve"]) > 0
        assert d["kind"] == "system"


class TestCustomTraderCRUD:
    def test_create_custom_trader(self, api_client, admin_headers, state):
        body = {
            "name": "Test AI",
            "country_code": "JP",
            "country_name": "Japan",
            "style": "Scalping",
            "bio": "auto-created",
            "experience_years": 5,
            "verified": True,
            "approval_level": "elite",
            "truth": {"win_rate": 0.68, "payoff_ratio": 1.4, "avg_lot": 0.5},
        }
        r = api_client.post(f"{API}/copy_trading/admin/traders",
                            headers=admin_headers, json=body)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["id"].startswith("custom_"), f"id={d['id']}"
        assert d["kind"] == "custom"
        assert d["name"] == "Test AI"
        assert d["country_code"] == "JP"
        assert d["style"] == "Scalping"
        assert d["verified"] is True
        assert d["approval_level"] == "elite"
        assert "stats" in d and d["stats"]
        assert "risk" in d and d["risk"]
        state["custom_id"] = d["id"]

    def test_leaderboard_total_29_after_create(self, api_client):
        # public leaderboard should now show 29 (28 system + 1 custom)
        r = api_client.get(f"{API}/copy_trading/traders", params={"limit": 50})
        assert r.status_code == 200
        assert r.json()["total"] == 29

    def test_update_custom_trader(self, api_client, admin_headers, state):
        cid = state["custom_id"]
        r = api_client.put(f"{API}/copy_trading/admin/traders/{cid}",
                           headers=admin_headers,
                           json={"name": "Test AI v2", "bio": "updated"})
        assert r.status_code == 200, r.text[:200]
        # Verify via GET
        r2 = api_client.get(f"{API}/copy_trading/admin/traders/{cid}",
                            headers=admin_headers)
        assert r2.status_code == 200
        d = r2.json()
        assert d["name"] == "Test AI v2"
        assert d["bio"] == "updated"


class TestSystemTraderOverlay:
    def test_update_system_trader_overlay(self, api_client, admin_headers):
        r = api_client.put(f"{API}/copy_trading/admin/traders/{SYSTEM_TRADER_2}",
                           headers=admin_headers,
                           json={"bio": "edited by admin", "approval_level": "master",
                                 "risk_tier": "Aggressive"})
        assert r.status_code == 200, r.text[:300]
        # GET verify
        r2 = api_client.get(f"{API}/copy_trading/admin/traders/{SYSTEM_TRADER_2}",
                            headers=admin_headers)
        assert r2.status_code == 200
        d = r2.json()
        assert d["bio"] == "edited by admin"
        assert d["approval_level"] == "master"
        assert d["risk"]["risk_tier"] == "Aggressive"
        assert d.get("_edited") is True

    def test_reset_overlay(self, api_client, admin_headers):
        r = api_client.post(
            f"{API}/copy_trading/admin/traders/{SYSTEM_TRADER_2}/reset-overlay",
            headers=admin_headers)
        assert r.status_code == 200
        # bio should return to seeded default (not our edited value)
        r2 = api_client.get(f"{API}/copy_trading/admin/traders/{SYSTEM_TRADER_2}",
                            headers=admin_headers)
        d = r2.json()
        assert d["bio"] != "edited by admin"
        assert d.get("_edited") is not True


class TestVerifyDisableEnable:
    def test_verify_unverify_system(self, api_client, admin_headers):
        r = api_client.post(
            f"{API}/copy_trading/admin/traders/{SYSTEM_TRADER_1}/verify",
            headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["verified"] is True
        r2 = api_client.post(
            f"{API}/copy_trading/admin/traders/{SYSTEM_TRADER_1}/unverify",
            headers=admin_headers)
        assert r2.status_code == 200
        assert r2.json()["verified"] is False
        # restore verify + clean overlay so leaderboard stays stable
        api_client.post(
            f"{API}/copy_trading/admin/traders/{SYSTEM_TRADER_1}/reset-overlay",
            headers=admin_headers)

    def test_verify_unverify_custom(self, api_client, admin_headers, state):
        cid = state["custom_id"]
        r = api_client.post(f"{API}/copy_trading/admin/traders/{cid}/unverify",
                            headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["verified"] is False
        r2 = api_client.post(f"{API}/copy_trading/admin/traders/{cid}/verify",
                             headers=admin_headers)
        assert r2.status_code == 200
        assert r2.json()["verified"] is True

    def test_disable_excludes_from_public_leaderboard(self, api_client, admin_headers):
        r = api_client.post(
            f"{API}/copy_trading/admin/traders/{SYSTEM_TRADER_1}/disable",
            headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["disabled"] is True
        # Public leaderboard (include_disabled=false) should NOT contain SYSTEM_TRADER_1
        r2 = api_client.get(f"{API}/copy_trading/traders", params={"limit": 50})
        ids = [t["id"] for t in r2.json()["items"]]
        assert SYSTEM_TRADER_1 not in ids, f"disabled trader still in leaderboard"
        # Re-enable
        r3 = api_client.post(
            f"{API}/copy_trading/admin/traders/{SYSTEM_TRADER_1}/enable",
            headers=admin_headers)
        assert r3.status_code == 200
        assert r3.json()["disabled"] is False
        # Cleanup overlay
        api_client.post(
            f"{API}/copy_trading/admin/traders/{SYSTEM_TRADER_1}/reset-overlay",
            headers=admin_headers)

    def test_delete_system_forbidden(self, api_client, admin_headers):
        r = api_client.delete(
            f"{API}/copy_trading/admin/traders/{SYSTEM_TRADER_1}",
            headers=admin_headers)
        assert r.status_code == 400, f"expected 400, got {r.status_code}"


# ------------------------- SIMULATION -------------------------
class TestSimulation:
    def test_status_shape(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/simulation/status",
                           headers=admin_headers)
        assert r.status_code == 200
        s = r.json()
        for f in ("enabled", "speed", "active_traders",
                  "open_master_trades", "lifetime_master_trades"):
            assert f in s, f"missing {f}"

    def test_pause_resume(self, api_client, admin_headers):
        r = api_client.post(f"{API}/copy_trading/admin/simulation/pause",
                            headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["enabled"] is False
        r2 = api_client.post(f"{API}/copy_trading/admin/simulation/resume",
                             headers=admin_headers)
        assert r2.status_code == 200
        assert r2.json()["enabled"] is True

    def test_speed_valid(self, api_client, admin_headers):
        r = api_client.post(f"{API}/copy_trading/admin/simulation/speed",
                            headers=admin_headers, json={"speed": "fast"})
        assert r.status_code == 200
        assert r.json()["speed"] == "fast"
        # restore
        api_client.post(f"{API}/copy_trading/admin/simulation/speed",
                        headers=admin_headers, json={"speed": "normal"})

    def test_speed_invalid_400(self, api_client, admin_headers):
        r = api_client.post(f"{API}/copy_trading/admin/simulation/speed",
                            headers=admin_headers, json={"speed": "invalid"})
        assert r.status_code == 400

    def test_force_open_close(self, api_client, admin_headers, state):
        r = api_client.post(f"{API}/copy_trading/admin/simulation/force-open",
                            headers=admin_headers,
                            json={"trader_id": SYSTEM_TRADER_1, "side": "buy"})
        assert r.status_code == 200
        mt = r.json()["master_trade"]
        assert mt["side"] == "buy"
        assert mt["trader_id"] == SYSTEM_TRADER_1
        state["master_id_force"] = mt["master_id"]
        r2 = api_client.post(
            f"{API}/copy_trading/admin/simulation/force-close/{mt['master_id']}",
            headers=admin_headers)
        assert r2.status_code == 200
        d = r2.json()
        assert d.get("status") == "closed"
        assert d.get("pnl_pct") is not None


# ------------------------- MASTER TRADE EXPLORER -------------------------
class TestMasterTradeExplorer:
    def test_list_with_followers_copied(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/master-trades",
                           headers=admin_headers, params={"limit": 20})
        assert r.status_code == 200
        trades = r.json()["trades"]
        assert isinstance(trades, list)
        if trades:
            for t in trades[:5]:
                assert "followers_copied" in t
                assert isinstance(t["followers_copied"], int) and t["followers_copied"] >= 0

    def test_filter_by_status_open(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/master-trades",
                           headers=admin_headers,
                           params={"status": "open", "limit": 20})
        assert r.status_code == 200
        for t in r.json()["trades"]:
            assert t["status"] == "open"

    def test_filter_by_status_closed(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/master-trades",
                           headers=admin_headers,
                           params={"status": "closed", "limit": 20})
        assert r.status_code == 200
        for t in r.json()["trades"]:
            assert t["status"] == "closed"

    def test_filter_by_trader(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/master-trades",
                           headers=admin_headers,
                           params={"trader_id": SYSTEM_TRADER_3, "limit": 20})
        assert r.status_code == 200
        for t in r.json()["trades"]:
            assert t["trader_id"] == SYSTEM_TRADER_3


# ------------------------- FOLLOWER MONITOR -------------------------
class TestFollowerMonitor:
    def test_setup_follower_flow(self, api_client, user_ctx):
        # Start copy on hana_tanaka
        r = api_client.post(
            f"{API}/copy_trading/traders/{SYSTEM_TRADER_3}/copy/start",
            headers=user_ctx["headers"],
            json={"settings": {}})
        assert r.status_code == 200, r.text[:200]
        assert r.json()["status"] == "active"

    def test_summary_shape_and_top(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/followers/summary",
                           headers=admin_headers)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        for f in ("total_relationships", "active", "paused", "stopped", "halted",
                  "unique_followers", "top_traders"):
            assert f in d, f"missing {f}"
        assert d["active"] >= 1
        top_ids = [t["trader_id"] for t in d["top_traders"]]
        assert SYSTEM_TRADER_3 in top_ids, f"hana_tanaka not in top_traders: {top_ids}"
        # each top row shape
        for row in d["top_traders"]:
            assert "trader_id" in row and "trader_name" in row and "follower_count" in row

    def test_drill_in_followers(self, api_client, admin_headers, user_ctx):
        r = api_client.get(
            f"{API}/copy_trading/admin/traders/{SYSTEM_TRADER_3}/followers",
            headers=admin_headers)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert "trader" in d
        assert "followers" in d
        # Find our fresh user
        target_email = user_ctx["email"]
        match = None
        for f in d["followers"]:
            if (f.get("user") or {}).get("email") == target_email:
                match = f
                break
        assert match is not None, f"our test user not found in followers"
        assert match["status"] == "active"
        assert "live" in match
        assert "lifetime_pnl_usd" in match["live"]
        assert "open_positions" in match["live"]


# ------------------------- ANALYTICS -------------------------
class TestAnalytics:
    def test_analytics_shape(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/analytics",
                           headers=admin_headers)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        # trades
        for f in ("total_master", "total_mirrored", "open_positions", "closed_trades"):
            assert f in d["trades"], f"trades missing {f}"
        # pnl
        for f in ("total_profit_usd", "total_loss_usd", "net_usd", "win_rate_pct"):
            assert f in d["pnl"], f"pnl missing {f}"
        # roi
        for f in ("daily_usd", "weekly_usd", "monthly_usd", "avg_trader_roi_pct",
                  "avg_trader_risk"):
            assert f in d["roi"], f"roi missing {f}"
        # copies
        for f in ("active", "daily_new", "monthly_new", "unique_followers", "most_copied"):
            assert f in d["copies"], f"copies missing {f}"
        # leaders
        for f in ("highest_roi", "highest_win_rate", "highest_aum"):
            assert f in d["leaders"], f"leaders missing {f}"
            leader = d["leaders"][f]
            if leader:
                for k in ("id", "name", "style", "total_roi_pct", "win_rate_pct", "aum_usd"):
                    assert k in leader, f"leader {f} missing {k}"


# ------------------------- SYSTEM HEALTH -------------------------
class TestSystemHealth:
    def test_health_shape(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/system-health",
                           headers=admin_headers)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        for f in ("event_queue_size", "active_simulators", "active_followers",
                  "active_copy_sessions", "broker", "avg_fanout_ms", "avg_exec_ms",
                  "failed_mirrors", "retry_queue_size", "server", "database", "simulator"):
            assert f in d, f"missing {f}"
        assert d["active_simulators"] >= 28
        assert d["broker"]["name"] == "paper"
        assert d["broker"]["ok"] is True
        assert isinstance(d["avg_fanout_ms"], (int, float))
        assert isinstance(d["avg_exec_ms"], (int, float))
        assert isinstance(d["failed_mirrors"], int)
        assert isinstance(d["retry_queue_size"], int)
        assert d["server"]["ok"] is True
        assert "uptime_sec" in d["server"]
        assert d["database"]["ok"] is True


# ------------------------- CONFIGURATION -------------------------
class TestConfig:
    def test_get_config(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/config",
                           headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert "defaults" in d and "sim" in d and "schema" in d

    def test_put_defaults_persist(self, api_client, admin_headers):
        # capture originals
        r0 = api_client.get(f"{API}/copy_trading/admin/config", headers=admin_headers)
        orig = r0.json()["defaults"]
        orig_daily = orig.get("max_daily_loss_pct", 10)
        orig_open = orig.get("max_open_trades", 10)
        # PUT
        r = api_client.put(f"{API}/copy_trading/admin/config/defaults",
                           headers=admin_headers,
                           json={"max_daily_loss_pct": 12.5, "max_open_trades": 8})
        assert r.status_code == 200, r.text[:200]
        merged = r.json()["defaults"]
        assert merged["max_daily_loss_pct"] == 12.5
        assert merged["max_open_trades"] == 8
        # verify persistence via GET
        r2 = api_client.get(f"{API}/copy_trading/admin/config", headers=admin_headers)
        d2 = r2.json()["defaults"]
        assert d2["max_daily_loss_pct"] == 12.5
        assert d2["max_open_trades"] == 8
        # restore
        api_client.put(f"{API}/copy_trading/admin/config/defaults",
                       headers=admin_headers,
                       json={"max_daily_loss_pct": orig_daily,
                             "max_open_trades": orig_open})


# ------------------------- CUSTOM TRADER SIMULATOR PICKUP -------------------------
class TestCustomTraderSimPickup:
    def test_force_open_on_custom_creates_follower_trade(self, api_client, admin_headers,
                                                          user_ctx, state):
        cid = state.get("custom_id")
        assert cid, "custom trader not created (previous test failed)"
        # Start copy on custom trader
        r = api_client.post(
            f"{API}/copy_trading/traders/{cid}/copy/start",
            headers=user_ctx["headers"],
            json={"settings": {"mode": "multiplier", "multiplier": 1.0}})
        assert r.status_code == 200, r.text[:200]

        # Force-open master trade on custom
        r2 = api_client.post(f"{API}/copy_trading/admin/simulation/force-open",
                             headers=admin_headers,
                             json={"trader_id": cid, "side": "buy"})
        assert r2.status_code == 200, r2.text[:200]
        mt = r2.json()["master_trade"]
        master_id = mt["master_id"]
        assert mt["trader_id"] == cid

        # Poll for follower trade
        deadline = time.time() + 8
        found = None
        while time.time() < deadline:
            r3 = api_client.get(f"{API}/copy_trading/my/trades",
                                params={"trader_id": cid},
                                headers=user_ctx["headers"])
            for t in (r3.json().get("trades") or []):
                if t.get("master_id") == master_id:
                    found = t
                    break
            if found:
                break
            time.sleep(1)
        assert found is not None, f"no follower trade for custom master {master_id}"
        # cleanup
        api_client.post(
            f"{API}/copy_trading/admin/simulation/force-close/{master_id}",
            headers=admin_headers)


# ------------------------- DELETE CUSTOM + BASELINE RESTORE -------------------------
class TestZFinalCleanup:
    """Runs last (Z prefix). Deletes custom trader so baseline returns to 28."""
    def test_delete_custom_trader(self, api_client, admin_headers, user_ctx, state):
        cid = state.get("custom_id")
        assert cid
        # Stop any copy on it first
        api_client.post(f"{API}/copy_trading/traders/{cid}/copy/stop",
                        headers=user_ctx["headers"])
        r = api_client.delete(f"{API}/copy_trading/admin/traders/{cid}",
                              headers=admin_headers)
        assert r.status_code == 200, r.text[:200]
        assert r.json().get("deleted") is True

    def test_baseline_28_after_delete(self, api_client, admin_headers):
        r = api_client.get(f"{API}/copy_trading/admin/traders",
                           headers=admin_headers, params={"limit": 200})
        assert r.status_code == 200
        assert r.json()["total"] == 28


# ------------------------- REGRESSION -------------------------
class TestRegression:
    def test_wallet(self, api_client, user_ctx):
        r = api_client.get(f"{API}/wallet", headers=user_ctx["headers"])
        assert r.status_code == 200

    def test_notifications(self, api_client, user_ctx):
        r = api_client.get(f"{API}/notifications", headers=user_ctx["headers"])
        assert r.status_code == 200

    def test_forex_symbols(self, api_client):
        r = api_client.get(f"{API}/forex/symbols")
        assert r.status_code == 200

    def test_forex_balance(self, api_client, user_ctx):
        r = api_client.get(f"{API}/forex/balance", headers=user_ctx["headers"])
        assert r.status_code == 200

    def test_market_dashboard(self, api_client):
        r = api_client.get(f"{API}/market/dashboard")
        assert r.status_code == 200

    def test_auth_me(self, api_client, user_ctx):
        r = api_client.get(f"{API}/auth/me", headers=user_ctx["headers"])
        assert r.status_code == 200


class TestRegression7B2:
    def test_my_copies(self, api_client, user_ctx):
        r = api_client.get(f"{API}/copy_trading/my/copies",
                           headers=user_ctx["headers"])
        assert r.status_code == 200
        assert "copies" in r.json()

    def test_my_summary(self, api_client, user_ctx):
        r = api_client.get(f"{API}/copy_trading/my/summary",
                           headers=user_ctx["headers"])
        assert r.status_code == 200

    def test_start_copy_regression(self, api_client, user_ctx):
        # already started earlier — this ensures endpoint still returns 200
        r = api_client.post(
            f"{API}/copy_trading/traders/{SYSTEM_TRADER_3}/copy/start",
            headers=user_ctx["headers"],
            json={"settings": {}})
        assert r.status_code == 200
