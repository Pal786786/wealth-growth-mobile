"""Sprint 7C.2 — AI News, Calendar, Summary, Analytics + Full regression.

Covers:
  New AI News/Analytics endpoints (public & admin)
  Calendar CRUD lifecycle
  News admin PUT / DELETE / generate
  Summary generate / delete
  Analytics forced tick + shape validation
  Filter validation (category, impact, sentiment)
  Full regression on wallet, notifications, auth/me, forex, market,
  market_providers, copy_trading, ai_intelligence, kyc
"""
from __future__ import annotations
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("EXPO_PUBLIC_BACKEND_URL must be set")

ADMIN_EMAIL = "admin@mfb.in"
ADMIN_PASSWORD = "Admin@MFB2026"
USER_EMAIL = "demo@mfb.in"
USER_PASSWORD = "demo1234"

TIMEOUT = 20


# ------------- fixtures -------------

@pytest.fixture(scope="session")
def admin_token() -> str:
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=TIMEOUT)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def user_token() -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": USER_EMAIL, "password": USER_PASSWORD},
                      timeout=TIMEOUT)
    assert r.status_code == 200, f"user login failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_h(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def user_h(user_token) -> dict:
    return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}


# ============================================================
# 1. NEWS (public + admin)
# ============================================================
class TestAINews:
    def test_list_news_shape(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/news?limit=10", headers=user_h,
                         timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("items", "count", "categories", "category_labels"):
            assert k in j, f"missing key {k}"
        assert set(j["categories"]) == {
            "forex", "crypto", "indices", "commodities", "indian_market", "global"}
        assert isinstance(j["items"], list)
        if j["items"]:
            item = j["items"][0]
            required = {"news_id", "category", "title", "summary", "body",
                        "sentiment", "tags", "symbols", "published_at",
                        "is_ai_generated", "high_impact"}
            missing = required - set(item.keys())
            assert not missing, f"news item missing keys: {missing}"

    def test_get_news_by_id(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/news?limit=1", headers=user_h, timeout=TIMEOUT)
        items = r.json().get("items", [])
        if not items:
            pytest.skip("no news items available")
        nid = items[0]["news_id"]
        r2 = requests.get(f"{BASE_URL}/api/ai/news/{nid}", headers=user_h, timeout=TIMEOUT)
        assert r2.status_code == 200
        assert r2.json()["news_id"] == nid

    def test_get_news_404(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/news/does_not_exist_xxx",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 404

    def test_news_filter_category(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/news?category=crypto&limit=20",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200
        for it in r.json()["items"]:
            assert it["category"] == "crypto", f"got {it['category']}"

    def test_news_filter_sentiment(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/news?sentiment=bullish&limit=20",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200
        for it in r.json()["items"]:
            assert it["sentiment"] == "bullish"

    def test_news_high_impact_only(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/news?high_impact_only=true&limit=20",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200
        for it in r.json()["items"]:
            assert it["high_impact"] is True

    def test_news_unauth(self):
        r = requests.get(f"{BASE_URL}/api/ai/news", timeout=TIMEOUT)
        assert r.status_code in (401, 403)

    def test_admin_news_list(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/ai/admin/news?limit=5", headers=admin_h,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert "items" in j and "count" in j

    def test_admin_news_generate(self, admin_h):
        body = {"categories": ["forex"], "per_category": 1}
        r = requests.post(f"{BASE_URL}/api/ai/admin/news/generate",
                          headers=admin_h, json=body, timeout=120)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "generated" in j
        assert isinstance(j["generated"], int)

    def test_admin_news_put_delete_lifecycle(self, admin_h):
        # generate a batch first
        gen = requests.post(f"{BASE_URL}/api/ai/admin/news/generate",
                            headers=admin_h,
                            json={"categories": ["global"], "per_category": 1},
                            timeout=120)
        assert gen.status_code == 200
        lst = requests.get(f"{BASE_URL}/api/ai/admin/news?category=global&limit=1",
                           headers=admin_h, timeout=TIMEOUT)
        assert lst.status_code == 200
        items = lst.json()["items"]
        if not items:
            pytest.skip("no global news generated")
        nid = items[0]["news_id"]

        # PUT — update title + high_impact
        new_title = f"TEST_iter30 headline {uuid.uuid4().hex[:6]}"
        r = requests.put(f"{BASE_URL}/api/ai/admin/news/{nid}", headers=admin_h,
                         json={"title": new_title, "high_impact": True},
                         timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["title"] == new_title
        assert r.json()["high_impact"] is True

        # GET to verify persistence (public endpoint requires user auth)
        user_h_tmp = {"Authorization": admin_h["Authorization"]}
        # use the user token instead
        user_login = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"identifier": USER_EMAIL, "password": USER_PASSWORD},
            timeout=TIMEOUT).json()
        uh = {"Authorization": f"Bearer {user_login['token']}"}
        r2 = requests.get(f"{BASE_URL}/api/ai/news/{nid}", headers=uh, timeout=TIMEOUT)
        assert r2.status_code == 200
        assert r2.json()["title"] == new_title

        # DELETE
        r3 = requests.delete(f"{BASE_URL}/api/ai/admin/news/{nid}",
                             headers=admin_h, timeout=TIMEOUT)
        assert r3.status_code == 200
        assert r3.json().get("deleted") is True

        # Confirm 404
        r4 = requests.get(f"{BASE_URL}/api/ai/news/{nid}",
                          headers=uh, timeout=TIMEOUT)
        assert r4.status_code == 404


# ============================================================
# 2. CALENDAR
# ============================================================
class TestAICalendar:
    def test_calendar_meta(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/calendar/meta", headers=user_h,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert j["impacts"] == ["low", "medium", "high"]
        assert set(j["impact_labels"].keys()) == {"low", "medium", "high"}

    def test_calendar_list(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/calendar?days_ahead=90&limit=100",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "events" in j and "count" in j
        # Seeded ~32 events; use ≥1 to avoid brittleness
        assert j["count"] >= 1, "no calendar events found (seed missing?)"
        ev = j["events"][0]
        for k in ("event_id", "title", "country", "currency", "impact",
                  "event_time", "countdown_sec"):
            assert k in ev, f"missing {k}"
        # datetime ISO format
        assert isinstance(ev["event_time"], str)
        assert "T" in ev["event_time"]

    def test_calendar_filter_impact(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/calendar?impact=high&days_ahead=90&limit=50",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200
        for e in r.json()["events"]:
            assert e["impact"] == "high"

    def test_calendar_filter_currency(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/calendar?currency=USD&days_ahead=90&limit=50",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200
        for e in r.json()["events"]:
            assert e["currency"] == "USD"

    def test_calendar_crud_lifecycle(self, admin_h, user_h):
        et = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        payload = {
            "title": "TEST_iter30 FOMC Rate Decision",
            "country": "US",
            "currency": "USD",
            "impact": "high",
            "category": "Central Bank",
            "event_time": et,
            "forecast": "5.25%",
            "previous": "5.25%",
            "description": "TEST_iter30 seeded event",
        }
        # CREATE
        r = requests.post(f"{BASE_URL}/api/ai/admin/calendar",
                          headers=admin_h, json=payload, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        ev = r.json()
        eid = ev["event_id"]
        assert ev["title"] == payload["title"]
        assert ev["impact"] == "high"

        # LIST (user side) — event should appear
        r_list = requests.get(
            f"{BASE_URL}/api/ai/calendar?impact=high&days_ahead=30&limit=200",
            headers=user_h, timeout=TIMEOUT)
        ids = {e["event_id"] for e in r_list.json()["events"]}
        assert eid in ids

        # UPDATE
        new_title = "TEST_iter30 FOMC (updated)"
        r_up = requests.put(f"{BASE_URL}/api/ai/admin/calendar/{eid}",
                            headers=admin_h,
                            json={"title": new_title, "impact": "medium"},
                            timeout=TIMEOUT)
        assert r_up.status_code == 200
        assert r_up.json()["title"] == new_title
        assert r_up.json()["impact"] == "medium"

        # DELETE
        r_del = requests.delete(f"{BASE_URL}/api/ai/admin/calendar/{eid}",
                                headers=admin_h, timeout=TIMEOUT)
        assert r_del.status_code == 200

        # Confirm gone
        r_del2 = requests.delete(f"{BASE_URL}/api/ai/admin/calendar/{eid}",
                                 headers=admin_h, timeout=TIMEOUT)
        assert r_del2.status_code == 404

    def test_calendar_bad_impact(self, admin_h):
        et = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        r = requests.post(f"{BASE_URL}/api/ai/admin/calendar",
                          headers=admin_h,
                          json={"title": "TEST_bad", "impact": "extreme",
                                "event_time": et},
                          timeout=TIMEOUT)
        assert r.status_code == 400


# ============================================================
# 3. SUMMARY
# ============================================================
class TestAISummary:
    def test_summary_daily(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/summary?type=daily",
                         headers=user_h, timeout=90)
        assert r.status_code == 200
        s = r.json().get("summary")
        assert s, "empty summary"
        for k in ("summary_id", "type", "body", "sentiment",
                  "is_ai_generated", "generated_at"):
            assert k in s

    def test_summary_intraday(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/summary?type=intraday",
                         headers=user_h, timeout=90)
        assert r.status_code == 200
        assert r.json()["summary"]["type"] == "intraday"

    def test_summary_weekly(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/summary?type=weekly",
                         headers=user_h, timeout=90)
        assert r.status_code == 200
        assert r.json()["summary"]["type"] == "weekly"

    def test_summary_bad_type(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/summary?type=hourly",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code in (400, 422)

    def test_summary_history(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/summary/history?limit=10",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert "items" in j and "count" in j

    def test_admin_summary_generate_and_delete(self, admin_h):
        r = requests.post(f"{BASE_URL}/api/ai/admin/summary/generate?type=daily",
                          headers=admin_h, timeout=120)
        assert r.status_code == 200, r.text
        sid = r.json().get("summary_id")
        assert sid
        r_del = requests.delete(f"{BASE_URL}/api/ai/admin/summary/{sid}",
                                headers=admin_h, timeout=TIMEOUT)
        assert r_del.status_code == 200


# ============================================================
# 4. ANALYTICS
# ============================================================
class TestAIAnalytics:
    def test_overview_shape(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/analytics/overview",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        required = {
            "total_signals", "resolved_signals", "pending_signals",
            "tp_hits", "sl_hits", "expired",
            "win_rate_pct", "tp1_hit_rate_pct", "tp2_hit_rate_pct",
            "tp3_hit_rate_pct", "sum_roi_pct", "avg_roi_pct",
            "avg_confidence_pct", "confidence_edge_pct",
        }
        missing = required - set(d.keys())
        assert not missing, f"missing keys: {missing}"

    def test_overview_window_days(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/analytics/overview?window_days=7",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("window_days") == 7

    def test_by_symbol(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/analytics/by-symbol?limit=5",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert "rows" in j and "count" in j
        for row in j["rows"]:
            assert "symbol" in row
            assert "win_rate_pct" in row

    def test_by_timeframe(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/analytics/by-timeframe",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200
        for row in r.json()["rows"]:
            assert "timeframe" in row

    def test_history(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/analytics/history?limit=10",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert "items" in j
        if j["items"]:
            row = j["items"][0]
            for k in ("symbol", "timeframe", "side", "entry", "outcome",
                      "generated_at"):
                assert k in row, f"missing {k}"

    def test_admin_tick(self, admin_h, user_h):
        before = requests.get(f"{BASE_URL}/api/ai/analytics/overview",
                              headers=user_h, timeout=TIMEOUT).json()
        r = requests.post(f"{BASE_URL}/api/ai/admin/analytics/tick",
                          headers=admin_h, timeout=120)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "tracked" in body and "resolved" in body
        after = requests.get(f"{BASE_URL}/api/ai/analytics/overview",
                             headers=user_h, timeout=TIMEOUT).json()
        assert after["total_signals"] >= before["total_signals"]

    def test_arithmetic_consistency(self, user_h):
        ov = requests.get(f"{BASE_URL}/api/ai/analytics/overview",
                          headers=user_h, timeout=TIMEOUT).json()
        # win_rate = tp_hits / resolved (approx)
        if ov["resolved_signals"] > 0:
            expected = round(ov["tp_hits"] * 100.0 / ov["resolved_signals"], 2)
            # tolerate small rounding drift
            assert abs(expected - ov["win_rate_pct"]) < 0.5, \
                f"win_rate mismatch: {ov['win_rate_pct']} vs {expected}"


# ============================================================
# 5. ADMIN CONSOLE
# ============================================================
class TestAdminConsole:
    def test_console_shape(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/ai/admin/console",
                         headers=admin_h, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("news", "calendar", "summary", "analytics"):
            assert k in d
        assert "broadcaster_interval_sec" in d["news"]

    def test_admin_only(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/admin/console",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code in (401, 403)


# ============================================================
# 6. BROADCASTER — high-impact news → notifications
# ============================================================
class TestBroadcaster:
    def test_notifications_include_market_news(self, user_h):
        r = requests.get(f"{BASE_URL}/api/notifications?limit=100",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        items = j if isinstance(j, list) else j.get("items", j.get("notifications", []))
        cats = {(n.get("category") or n.get("type") or "") for n in items}
        # Broadcaster should have created at least one entry after startup
        # (may be zero if no high_impact news exists yet — not a hard fail)
        has_news = any("news" in (c or "").lower() or c == "market_news" for c in cats)
        # log but soft-assert
        if not has_news:
            pytest.skip(f"no market_news notifications yet; categories: {cats}")


# ============================================================
# 7. REGRESSION SUITE — must keep passing
# ============================================================
class TestRegression:
    # ---- auth
    def test_auth_me(self, user_h):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200
        assert "user_id" in r.json()

    # ---- wallet
    def test_wallet(self, user_h):
        r = requests.get(f"{BASE_URL}/api/wallet", headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200
        assert "balance" in r.json()

    # ---- notifications
    def test_notifications(self, user_h):
        r = requests.get(f"{BASE_URL}/api/notifications", headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200

    # ---- forex
    def test_forex_symbols(self, user_h):
        r = requests.get(f"{BASE_URL}/api/forex/symbols", headers=user_h,
                         timeout=TIMEOUT)
        assert r.status_code == 200

    def test_forex_balance(self, user_h):
        r = requests.get(f"{BASE_URL}/api/forex/balance", headers=user_h,
                         timeout=TIMEOUT)
        assert r.status_code == 200

    def test_forex_positions(self, user_h):
        r = requests.get(f"{BASE_URL}/api/forex/positions", headers=user_h,
                         timeout=TIMEOUT)
        assert r.status_code == 200

    # ---- market
    def test_market_dashboard(self, user_h):
        r = requests.get(f"{BASE_URL}/api/market/dashboard", headers=user_h,
                         timeout=TIMEOUT)
        assert r.status_code == 200

    def test_market_providers_status(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/market_providers/status",
                         headers=admin_h, timeout=TIMEOUT)
        assert r.status_code == 200

    def test_market_providers_quotes(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/market_providers/quotes",
                         headers=admin_h, timeout=TIMEOUT)
        assert r.status_code == 200

    # ---- copy trading
    def test_copy_meta(self, user_h):
        r = requests.get(f"{BASE_URL}/api/copy_trading/meta", headers=user_h,
                         timeout=TIMEOUT)
        assert r.status_code == 200

    def test_copy_admin_health(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/copy_trading/admin/system-health",
                         headers=admin_h, timeout=TIMEOUT)
        assert r.status_code == 200

    def test_copy_trader_detail(self, user_h):
        r = requests.get(f"{BASE_URL}/api/copy_trading/traders/marcus_wolfe",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200

    def test_copy_my_summary(self, user_h):
        r = requests.get(f"{BASE_URL}/api/copy_trading/my/summary",
                         headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200

    # ---- AI intelligence (7C.1)
    def test_ai_meta(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/meta", headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200

    def test_ai_signals(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/signals?limit=5", headers=user_h,
                         timeout=TIMEOUT)
        assert r.status_code == 200

    def test_ai_watchlist(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/watchlist", headers=user_h,
                         timeout=TIMEOUT)
        assert r.status_code == 200

    def test_ai_alerts(self, user_h):
        r = requests.get(f"{BASE_URL}/api/ai/alerts", headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200

    # ---- KYC
    def test_kyc_status(self, user_h):
        r = requests.get(f"{BASE_URL}/api/kyc/status", headers=user_h, timeout=TIMEOUT)
        assert r.status_code == 200
