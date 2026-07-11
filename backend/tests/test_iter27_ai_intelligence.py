"""Sprint 7C.1 — AI Trading Intelligence backend tests (iter27).

Covers:
  - /api/ai/meta
  - /api/ai/signals list + filters
  - /api/ai/signals/{symbol} detail + AI explanation
  - /api/ai/indicators/{symbol}
  - /api/ai/candles/{symbol}
  - determinism (same bar → same entry)
  - TA sanity checks
  - Watchlist CRUD (auth)
  - Alerts CRUD + all 5 types + validation
  - Alerts pause/resume/delete
  - Alerts eval loop triggers + notifications
  - Admin alerts config
  - Regression: existing endpoints
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_BACKEND_URL")
            or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or "https://wealth-growth-mobile.preview.emergentagent.com").rstrip("/")


# ---------------- fixtures ----------------

@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def user_token(api):
    """Signup a fresh user and return {token, user_id, headers}."""
    suffix = uuid.uuid4().hex[:8]
    mobile = "9" + str(int(time.time()))[-9:]
    payload = {
        "full_name": f"TEST AI User {suffix}",
        "email": f"test_ai_{suffix}@mfb.in",
        "mobile": mobile,
        "password": "TestPass@123",
    }
    r = api.post(f"{BASE_URL}/api/auth/signup", json=payload, timeout=15)
    assert r.status_code == 200, f"signup failed: {r.status_code} {r.text}"
    data = r.json()
    token = data["token"]
    return {
        "token": token,
        "user": data["user"],
        "headers": {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    }


@pytest.fixture(scope="module")
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/admin/login",
                 json={"email": "admin@mfb.in", "password": "Admin@MFB2026"}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    tok = r.json()["token"]
    return {"token": tok, "headers": {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}}


# ---------------- meta ----------------

class TestMeta:
    def test_meta_shape(self, api):
        r = api.get(f"{BASE_URL}/api/ai/meta", timeout=10)
        assert r.status_code == 200
        d = r.json()
        for tf in ("M5", "M15", "M30", "H1", "H4", "D1"):
            assert tf in d["timeframes"], f"timeframe {tf} missing"
        assert d["default_timeframe"] == "H1"
        for ac in ("forex", "metals", "indices", "crypto", "commodities", "energies"):
            assert ac in d["asset_classes"]
        for at in ("price_above", "price_below", "percent_move", "indicator_cross", "rsi_alert"):
            assert at in d["alert_types"]
        assert isinstance(d["universe"], list) and 10 <= len(d["universe"]) <= 30
        assert isinstance(d["signal_expiry_bars"], dict)
        assert isinstance(d["eval_interval_sec"], int) and d["eval_interval_sec"] >= 5


# ---------------- signals ----------------

class TestSignalsList:
    def test_list_fields(self, api):
        r = api.get(f"{BASE_URL}/api/ai/signals", params={"timeframe": "H1", "limit": 10}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "signals" in d
        assert d["timeframe"] == "H1"
        assert 0 < len(d["signals"]) <= 10
        required = {"symbol", "display", "asset_class", "category", "timeframe",
                    "side", "entry", "stop_loss", "tp1", "tp2", "tp3",
                    "risk_reward_ratio", "confidence_pct", "trend",
                    "signal_strength", "expires_at", "generated_at", "bar_index"}
        for s in d["signals"]:
            missing = required - set(s.keys())
            assert not missing, f"missing fields {missing} in signal {s.get('symbol')}"
            assert s["side"] in ("buy", "sell", "hold")
            assert isinstance(s["entry"], (int, float))
            assert 30 <= s["confidence_pct"] <= 92
            assert s["trend"] in ("bullish", "bearish", "neutral")
            assert s["signal_strength"] in ("weak", "moderate", "strong", "very_strong")
            assert isinstance(s["bar_index"], int)
            if s["side"] in ("buy", "sell"):
                assert s["risk_reward_ratio"] == 3.0
                assert isinstance(s["expires_at"], str) and "T" in s["expires_at"]
            else:  # hold
                assert s["expires_at"] is None
            assert isinstance(s["generated_at"], str) and "T" in s["generated_at"]

    def test_anchor_prices(self, api):
        """Prices must roughly match instrument anchors (not fixed at ~100 nor 1000× off)."""
        r = api.get(f"{BASE_URL}/api/ai/signals", params={"timeframe": "H1", "limit": 30}, timeout=15)
        assert r.status_code == 200
        by_sym = {s["symbol"]: s["entry"] for s in r.json()["signals"]}
        # Anchors from market_data catalog
        expected_ranges = {
            "BTCUSD": (60_000, 130_000),
            "XAUUSD": (3500, 4500),
            "EURUSD": (1.0, 1.30),
            "GER40":  (17_000, 24_000),
            "ETHUSD": (2500, 5000),
        }
        for sym, (lo, hi) in expected_ranges.items():
            if sym in by_sym:
                px = by_sym[sym]
                assert lo <= px <= hi, f"{sym} price {px} outside expected [{lo},{hi}]"

    def test_filter_asset_class(self, api):
        r = api.get(f"{BASE_URL}/api/ai/signals", params={"asset_class": "crypto", "limit": 30}, timeout=15)
        assert r.status_code == 200
        rows = r.json()["signals"]
        assert len(rows) > 0
        for s in rows:
            assert s["asset_class"] == "crypto", f"{s['symbol']} asset_class={s['asset_class']}"

    def test_filter_side_buy(self, api):
        r = api.get(f"{BASE_URL}/api/ai/signals", params={"side": "buy", "limit": 30}, timeout=15)
        assert r.status_code == 200
        for s in r.json()["signals"]:
            assert s["side"] == "buy"

    def test_filter_min_confidence(self, api):
        r = api.get(f"{BASE_URL}/api/ai/signals", params={"min_confidence": 75, "limit": 30}, timeout=15)
        assert r.status_code == 200
        for s in r.json()["signals"]:
            assert s["confidence_pct"] >= 75


class TestSignalDetail:
    def test_signal_detail_with_ai(self, api, user_token):
        r = api.get(f"{BASE_URL}/api/ai/signals/BTCUSD",
                    params={"timeframe": "H1", "with_ai": "true"},
                    headers=user_token["headers"], timeout=30)
        assert r.status_code == 200, r.text
        sig = r.json()
        # AI explanation must be non-empty string (either Claude output or fallback)
        assert isinstance(sig.get("ai_explanation"), str) and len(sig["ai_explanation"]) > 20
        assert isinstance(sig.get("reason_hits"), list) and len(sig["reason_hits"]) >= 1
        # Indicators pack
        ind = sig["indicators"]
        for key in ("ema20", "ema50", "ema200", "rsi", "macd", "atr",
                    "bollinger", "adx", "supertrend", "vwap", "volatility_pct", "trend"):
            assert key in ind, f"indicator '{key}' missing"
        # indicator_summary
        summary = sig["indicator_summary"]
        assert isinstance(summary, list) and len(summary) >= 8
        for row in summary:
            assert {"name", "value", "verdict"} <= set(row.keys())

    def test_unknown_symbol_404(self, api, user_token):
        r = api.get(f"{BASE_URL}/api/ai/signals/UNKNOWN_XYZ",
                    headers=user_token["headers"], timeout=10)
        assert r.status_code == 404

    def test_indicators_endpoint(self, api):
        r = api.get(f"{BASE_URL}/api/ai/indicators/EURUSD", params={"timeframe": "H1"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["symbol"] == "EURUSD"
        assert "indicators" in d and "summary" in d
        assert len(d["summary"]) >= 8


class TestCandles:
    def test_candles_100(self, api):
        r = api.get(f"{BASE_URL}/api/ai/candles/EURUSD", params={"count": 100, "timeframe": "H1"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert len(d["candles"]) == 100
        for c in d["candles"]:
            for k in ("t", "open", "high", "low", "close", "volume"):
                assert k in c
            assert c["high"] >= max(c["open"], c["close"]) - 1e-9
            assert c["low"] <= min(c["open"], c["close"]) + 1e-9


class TestDeterminism:
    def test_signal_deterministic_same_bar(self, api, user_token):
        r1 = api.get(f"{BASE_URL}/api/ai/signals/EURUSD",
                     params={"timeframe": "H1", "with_ai": "false"},
                     headers=user_token["headers"], timeout=15)
        r2 = api.get(f"{BASE_URL}/api/ai/signals/EURUSD",
                     params={"timeframe": "H1", "with_ai": "false"},
                     headers=user_token["headers"], timeout=15)
        assert r1.status_code == 200 and r2.status_code == 200
        s1, s2 = r1.json(), r2.json()
        assert s1["entry"] == s2["entry"]
        assert s1["bar_index"] == s2["bar_index"]


class TestTAEngine:
    def test_ta_sanity(self, api):
        r = api.get(f"{BASE_URL}/api/ai/indicators/EURUSD", params={"timeframe": "H1"}, timeout=15)
        ind = r.json()["indicators"]
        price = ind["price"]
        assert 0 <= ind["rsi"] <= 100
        assert ind["ema200"] <= 2 * price, f"ema200 runaway: {ind['ema200']} vs price {price}"
        assert 0 <= ind["adx"] <= 100
        macd = ind["macd"]
        assert abs((macd["macd"] - macd["signal"]) - macd["hist"]) < 1e-4
        bb = ind["bollinger"]
        assert bb["upper"] > bb["middle"] > bb["lower"]
        assert ind["supertrend"]["direction"] in ("up", "down")
        assert ind["volatility_pct"] >= 0


# ---------------- watchlist ----------------

class TestWatchlist:
    def test_add_and_get(self, api, user_token):
        r = api.post(f"{BASE_URL}/api/ai/watchlist",
                     json={"symbol": "XAUUSD"}, headers=user_token["headers"], timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["item"]["symbol"] == "XAUUSD"
        enriched = data["enriched"]
        for key in ("trend", "signal", "confidence_pct", "volatility_pct",
                    "daily_change_pct", "weekly_change_pct"):
            assert key in enriched, f"enriched missing {key}"

        # GET
        r = api.get(f"{BASE_URL}/api/ai/watchlist", headers=user_token["headers"], timeout=10)
        assert r.status_code == 200
        syms = [it["symbol"] for it in r.json()["items"]]
        assert "XAUUSD" in syms

    def test_add_duplicate_idempotent(self, api, user_token):
        r = api.post(f"{BASE_URL}/api/ai/watchlist",
                     json={"symbol": "XAUUSD"}, headers=user_token["headers"], timeout=10)
        assert r.status_code == 200

    def test_add_invalid_symbol(self, api, user_token):
        r = api.post(f"{BASE_URL}/api/ai/watchlist",
                     json={"symbol": "FOOBAR"}, headers=user_token["headers"], timeout=10)
        assert r.status_code == 400

    def test_delete(self, api, user_token):
        r = api.delete(f"{BASE_URL}/api/ai/watchlist/XAUUSD",
                       headers=user_token["headers"], timeout=10)
        assert r.status_code == 200
        assert r.json()["removed"] is True
        # verify absent
        r = api.get(f"{BASE_URL}/api/ai/watchlist", headers=user_token["headers"], timeout=10)
        assert "XAUUSD" not in [it["symbol"] for it in r.json()["items"]]


# ---------------- alerts ----------------

class TestAlertsCRUD:
    """Create all 5 types, list, pause/resume, delete."""
    def test_price_above(self, api, user_token):
        r = api.post(f"{BASE_URL}/api/ai/alerts",
                     json={"type": "price_above", "symbol": "EURUSD", "target_price": 5.0},
                     headers=user_token["headers"], timeout=10)
        assert r.status_code == 200, r.text
        alert = r.json()["alert"]
        assert alert["status"] == "active"
        assert "alert_id" in alert
        user_token.setdefault("_alerts", {})["price_above"] = alert["alert_id"]

    def test_price_below(self, api, user_token):
        r = api.post(f"{BASE_URL}/api/ai/alerts",
                     json={"type": "price_below", "symbol": "EURUSD", "target_price": 0.001},
                     headers=user_token["headers"], timeout=10)
        assert r.status_code == 200

    def test_percent_move(self, api, user_token):
        r = api.post(f"{BASE_URL}/api/ai/alerts",
                     json={"type": "percent_move", "symbol": "BTCUSD",
                           "target_percent": 1.5, "direction": "both"},
                     headers=user_token["headers"], timeout=10)
        assert r.status_code == 200

    def test_indicator_cross(self, api, user_token):
        r = api.post(f"{BASE_URL}/api/ai/alerts",
                     json={"type": "indicator_cross", "symbol": "EURUSD",
                           "fast_ema": 20, "slow_ema": 50, "timeframe": "H1"},
                     headers=user_token["headers"], timeout=10)
        assert r.status_code == 200

    def test_rsi_alert(self, api, user_token):
        r = api.post(f"{BASE_URL}/api/ai/alerts",
                     json={"type": "rsi_alert", "symbol": "EURUSD",
                           "threshold": 70, "direction": "cross_above", "timeframe": "H1"},
                     headers=user_token["headers"], timeout=10)
        assert r.status_code == 200

    # Validation
    def test_invalid_type(self, api, user_token):
        r = api.post(f"{BASE_URL}/api/ai/alerts",
                     json={"type": "not_a_type", "symbol": "EURUSD"},
                     headers=user_token["headers"], timeout=10)
        assert r.status_code == 400

    def test_rsi_missing_threshold(self, api, user_token):
        r = api.post(f"{BASE_URL}/api/ai/alerts",
                     json={"type": "rsi_alert", "symbol": "EURUSD",
                           "direction": "cross_above", "timeframe": "H1"},
                     headers=user_token["headers"], timeout=10)
        assert r.status_code == 400

    def test_indicator_fast_ge_slow(self, api, user_token):
        r = api.post(f"{BASE_URL}/api/ai/alerts",
                     json={"type": "indicator_cross", "symbol": "EURUSD",
                           "fast_ema": 50, "slow_ema": 20, "timeframe": "H1"},
                     headers=user_token["headers"], timeout=10)
        assert r.status_code == 400

    def test_percent_invalid_direction(self, api, user_token):
        r = api.post(f"{BASE_URL}/api/ai/alerts",
                     json={"type": "percent_move", "symbol": "EURUSD",
                           "target_percent": 1.0, "direction": "sideways"},
                     headers=user_token["headers"], timeout=10)
        assert r.status_code == 400

    def test_pause_resume_delete(self, api, user_token):
        aid = user_token.get("_alerts", {}).get("price_above")
        assert aid, "prior test did not stash price_above alert_id"
        # pause
        r = api.post(f"{BASE_URL}/api/ai/alerts/{aid}/pause",
                     headers=user_token["headers"], timeout=10)
        assert r.status_code == 200
        assert r.json()["alert"]["status"] == "paused"
        # resume
        r = api.post(f"{BASE_URL}/api/ai/alerts/{aid}/resume",
                     headers=user_token["headers"], timeout=10)
        assert r.status_code == 200
        assert r.json()["alert"]["status"] == "active"
        # delete
        r = api.delete(f"{BASE_URL}/api/ai/alerts/{aid}",
                       headers=user_token["headers"], timeout=10)
        assert r.status_code == 200
        assert r.json()["deleted"] is True
        # delete non-existent
        r = api.delete(f"{BASE_URL}/api/ai/alerts/al_deadbeef0000",
                       headers=user_token["headers"], timeout=10)
        assert r.status_code == 404
        # pause non-existent
        r = api.post(f"{BASE_URL}/api/ai/alerts/al_deadbeef0000/pause",
                     headers=user_token["headers"], timeout=10)
        assert r.status_code == 404


class TestAlertsTrigger:
    """Verifies alerts eval loop actually fires + writes a notification."""

    def test_eval_loop_triggers(self, api, user_token, admin_token):
        # Speed up eval loop to 5s
        r = api.put(f"{BASE_URL}/api/ai/admin/alerts/config",
                    json={"eval_interval_sec": 5}, headers=admin_token["headers"], timeout=10)
        assert r.status_code == 200
        assert r.json()["eval_interval_sec"] == 5

        # Create guaranteed-firing alert on EURUSD
        r = api.post(f"{BASE_URL}/api/ai/alerts",
                     json={"type": "price_above", "symbol": "EURUSD", "target_price": 0.0001},
                     headers=user_token["headers"], timeout=10)
        assert r.status_code == 200
        alert_id = r.json()["alert"]["alert_id"]

        try:
            # Loop was already sleeping when we set 5s → wait up to 45s total
            fired = False
            for _ in range(9):
                time.sleep(5)
                r = api.get(f"{BASE_URL}/api/ai/alerts",
                            headers=user_token["headers"], timeout=10)
                assert r.status_code == 200
                match = [a for a in r.json()["alerts"] if a["alert_id"] == alert_id]
                if match and match[0]["status"] == "triggered":
                    fired = True
                    break
            assert fired, f"alert did not fire within 45s; last status={match[0]['status'] if match else 'missing'}"

            # Verify notification created (endpoint returns {items, total, ...})
            r = api.get(f"{BASE_URL}/api/notifications",
                        headers=user_token["headers"], timeout=10)
            assert r.status_code == 200
            body = r.json()
            if isinstance(body, list):
                notif_list = body
            else:
                # Handle both legacy `notifications` key and current `items` key
                notif_list = body.get("items") or body.get("notifications") or []
            hits = [n for n in notif_list
                    if n.get("category") == "price_alert"
                    and "EURUSD" in (n.get("title") or "")]
            assert len(hits) >= 1, (
                f"no price_alert notification with EURUSD in title found; "
                f"got {len(notif_list)} notifications, response_keys={list(body.keys()) if isinstance(body, dict) else 'list'}"
            )
        finally:
            # Reset eval interval to 30
            api.put(f"{BASE_URL}/api/ai/admin/alerts/config",
                    json={"eval_interval_sec": 30}, headers=admin_token["headers"], timeout=10)


class TestAdminConfig:
    def test_get_set_persist_clamp(self, api, admin_token):
        r = api.get(f"{BASE_URL}/api/ai/admin/alerts/config", headers=admin_token["headers"], timeout=10)
        assert r.status_code == 200
        assert "eval_interval_sec" in r.json()

        r = api.put(f"{BASE_URL}/api/ai/admin/alerts/config",
                    json={"eval_interval_sec": 15}, headers=admin_token["headers"], timeout=10)
        assert r.status_code == 200
        assert r.json()["eval_interval_sec"] == 15

        r = api.get(f"{BASE_URL}/api/ai/admin/alerts/config", headers=admin_token["headers"], timeout=10)
        assert r.json()["eval_interval_sec"] == 15

        # Clamp: out-of-range values
        r = api.put(f"{BASE_URL}/api/ai/admin/alerts/config",
                    json={"eval_interval_sec": 1}, headers=admin_token["headers"], timeout=10)
        assert r.json()["eval_interval_sec"] == 5   # clamped up

        r = api.put(f"{BASE_URL}/api/ai/admin/alerts/config",
                    json={"eval_interval_sec": 9999}, headers=admin_token["headers"], timeout=10)
        assert r.json()["eval_interval_sec"] == 600  # clamped down

        # reset to 30
        api.put(f"{BASE_URL}/api/ai/admin/alerts/config",
                json={"eval_interval_sec": 30}, headers=admin_token["headers"], timeout=10)


# ---------------- regression: existing endpoints still work ----------------

class TestRegression:
    def test_wallet(self, api, user_token):
        r = api.get(f"{BASE_URL}/api/wallet", headers=user_token["headers"], timeout=10)
        assert r.status_code == 200

    def test_notifications(self, api, user_token):
        r = api.get(f"{BASE_URL}/api/notifications", headers=user_token["headers"], timeout=10)
        assert r.status_code == 200

    def test_forex_symbols(self, api, user_token):
        r = api.get(f"{BASE_URL}/api/forex/symbols", headers=user_token["headers"], timeout=10)
        assert r.status_code == 200

    def test_forex_balance(self, api, user_token):
        r = api.get(f"{BASE_URL}/api/forex/balance", headers=user_token["headers"], timeout=10)
        assert r.status_code == 200

    def test_market_dashboard(self, api, user_token):
        r = api.get(f"{BASE_URL}/api/market/dashboard", headers=user_token["headers"], timeout=15)
        assert r.status_code == 200

    def test_copy_trading_meta(self, api, user_token):
        r = api.get(f"{BASE_URL}/api/copy_trading/meta", headers=user_token["headers"], timeout=10)
        assert r.status_code == 200

    def test_auth_me(self, api, user_token):
        r = api.get(f"{BASE_URL}/api/auth/me", headers=user_token["headers"], timeout=10)
        assert r.status_code == 200

    def test_copy_trading_my_copies(self, api, user_token):
        r = api.get(f"{BASE_URL}/api/copy_trading/my/copies", headers=user_token["headers"], timeout=10)
        assert r.status_code == 200

    def test_admin_system_health(self, api, admin_token):
        r = api.get(f"{BASE_URL}/api/copy_trading/admin/system-health",
                    headers=admin_token["headers"], timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("active_simulators", 0) >= 28
        broker = data.get("broker") or data.get("broker_status") or ""
        # Accept either 'paper' or a dict containing paper OK
        assert "paper" in str(broker).lower() or "ok" in str(broker).lower(), f"broker={broker}"
