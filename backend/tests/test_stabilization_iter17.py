"""
Iteration 17 — Stabilization sprint P0 backend health check.

Focus: verify the backend endpoints called by the screens that were reported
to be crashing on the real Android APK (push notifications, AI advisor, forex,
kyc, market, notification prefs). We just want 2xx across the board.
"""

import os
import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE:
    # fall back to the env var name used in this repo's /app/frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break

assert BASE, "EXPO_PUBLIC_BACKEND_URL must be set"

DEMO = {"identifier": "demo@mfb.in", "password": "demo1234"}


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE}/api/auth/login", json=DEMO, timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"no token in login response: {data}"
    return tok


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- Public / no-auth ----------

def test_firebase_status():
    r = requests.get(f"{BASE}/api/auth/firebase/status", timeout=10)
    assert r.status_code == 200, r.text


def test_forex_prices_public():
    r = requests.get(f"{BASE}/api/forex/prices", timeout=10)
    assert r.status_code == 200
    body = r.json()
    # accept either {"prices":[...]} or a bare list
    prices = body.get("prices", body) if isinstance(body, dict) else body
    assert isinstance(prices, list) and len(prices) >= 5, f"expected >=5 symbols, got {prices}"


def test_market_dashboard_public():
    r = requests.get(f"{BASE}/api/market/dashboard", timeout=15)
    assert r.status_code == 200, r.text


# ---------- Auth ----------

def test_login_returns_token(token):
    assert isinstance(token, str) and len(token) > 20


# ---------- Auth-gated ----------

def test_forex_equity(auth):
    r = requests.get(f"{BASE}/api/forex/equity", headers=auth, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("balance", "unrealized_pnl", "equity", "margin_used", "free_margin", "open_position_count", "currency"):
        assert k in body, f"missing key {k} in {body}"


def test_notifications_list(auth):
    r = requests.get(f"{BASE}/api/notifications", headers=auth, timeout=15)
    assert r.status_code == 200, r.text


def test_notification_preferences(auth):
    # tolerate either /preferences or /prefs — try both
    urls = [f"{BASE}/api/notifications/preferences", f"{BASE}/api/notifications/prefs"]
    codes = []
    for u in urls:
        r = requests.get(u, headers=auth, timeout=15)
        codes.append((u, r.status_code))
        if r.status_code == 200:
            return
    pytest.fail(f"no notification-prefs endpoint returned 200: {codes}")


def test_kyc_status(auth):
    r = requests.get(f"{BASE}/api/kyc/status", headers=auth, timeout=15)
    assert r.status_code == 200, r.text


def test_ai_suggestions(auth):
    r = requests.get(f"{BASE}/api/ai/suggestions", headers=auth, timeout=15)
    assert r.status_code == 200, r.text


def test_wallet(auth):
    r = requests.get(f"{BASE}/api/wallet", headers=auth, timeout=15)
    assert r.status_code == 200, r.text
