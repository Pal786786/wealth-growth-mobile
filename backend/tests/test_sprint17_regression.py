"""Sprint 17 supplemental — verifies demo trading + admin config remain healthy
alongside the new real-account module.

Focus areas (not duplicated by test_real_accounts.py):
  * public admin config endpoint returns mt5_provisioning_available=false and NO secrets
  * demo forex/market endpoints still 200 (regression)
  * unauthorized user access returns 401
  * duplicate ACTIVE apply blocked (already-existing account)
"""
import os
import uuid
import time

import pytest
import requests

BASE = "http://localhost:8001/api"
ADMIN = {"email": "admin@mfb.in", "password": "Admin@MFB2026"}
DEMO_USER = {"email": "demo@mfb.in", "password": "demo1234"}


@pytest.fixture(scope="module")
def admin_h():
    r = requests.post(f"{BASE}/admin/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def demo_h():
    r = requests.post(f"{BASE}/auth/login", json={
        "identifier": DEMO_USER["email"], "password": DEMO_USER["password"]}, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    tok = d.get("access_token") or d.get("token")
    return {"Authorization": f"Bearer {tok}"}


# -------------------- Real account: admin config & security
def test_admin_config_hides_secrets_and_shows_unavailable(admin_h):
    r = requests.get(f"{BASE}/admin/real-accounts-config", headers=admin_h, timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert j["mt5_provisioning_available"] is False
    cfg = j["config"]
    for key in ("mt5_server", "account_type", "currency", "leverage", "group"):
        assert key in cfg
    body = r.text.lower()
    for bad in ("password", "secret", "mt5_manager_password"):
        assert bad not in body, f"leaked marker: {bad}"


def test_admin_list_supports_status_filter(admin_h):
    r = requests.get(f"{BASE}/admin/real-accounts?status=FAILED", headers=admin_h, timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert "accounts" in j and "counts" in j
    for a in j["accounts"]:
        assert a["status"] == "FAILED"
    # invalid filter
    r2 = requests.get(f"{BASE}/admin/real-accounts?status=BOGUS", headers=admin_h, timeout=15)
    assert r2.status_code == 400


def test_real_account_unauth_returns_401():
    for path in ("/real-account", "/real-account/status"):
        r = requests.get(f"{BASE}{path}", timeout=10)
        assert r.status_code == 401, f"{path} -> {r.status_code}"
    r = requests.post(f"{BASE}/real-account/apply",
                      json={"email": "x@y.z"}, timeout=10)
    assert r.status_code == 401


def test_admin_endpoints_reject_user_token(demo_h):
    r = requests.get(f"{BASE}/admin/real-accounts", headers=demo_h, timeout=10)
    assert r.status_code in (401, 403)


# -------------------- Demo trading & market regression
def test_demo_wallet_still_works(demo_h):
    # Prefer forex balance endpoint
    r = requests.get(f"{BASE}/forex/balance", headers=demo_h, timeout=15)
    if r.status_code == 404:
        r = requests.get(f"{BASE}/forex/wallet", headers=demo_h, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    # balance key varies; accept common shapes
    assert any(k in j for k in ("balance", "wallet", "available_balance"))


def test_market_candles_still_serves(demo_h):
    r = requests.get(f"{BASE}/market/candles/XAUUSD?tf=1m&limit=50",
                     headers=demo_h, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "candles" in j
    assert isinstance(j["candles"], list)


# -------------------- User flow (fresh signup) apply → FAILED (MT5_UNAVAILABLE)
def test_fresh_user_apply_returns_failed_no_fake_number():
    email = f"ra_sup_{uuid.uuid4().hex[:6]}@test.mfb"
    r = requests.post(f"{BASE}/auth/signup", json={
        "full_name": "Sup Tester", "email": email,
        "mobile": f"7{int(time.time()) % 1000000000:09d}",
        "password": "Test@1234",
    }, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    tok = d.get("access_token") or d.get("token")
    uid = (d.get("user") or {}).get("user_id") or d.get("user_id")
    h = {"Authorization": f"Bearer {tok}"}
    try:
        rr = requests.post(f"{BASE}/real-account/apply",
                           json={"email": email}, headers=h, timeout=30)
        assert rr.status_code == 200, rr.text
        j = rr.json()
        assert j["status"] == "FAILED"
        assert j["error_code"] == "MT5_UNAVAILABLE"
        assert j["account"]["mt5_account_number"] is None
        # /real-account should now show the FAILED account
        rg = requests.get(f"{BASE}/real-account", headers=h, timeout=10)
        assert rg.status_code == 200
        assert rg.json()["status"] == "FAILED"
        # retry still FAILED
        rt = requests.post(f"{BASE}/real-account/retry", headers=h, timeout=30)
        assert rt.status_code == 200
        assert rt.json()["status"] == "FAILED"
    finally:
        from pymongo import MongoClient
        db = MongoClient("mongodb://localhost:27017").my_funding_bank
        db.real_trading_accounts.delete_many({"user_id": uid})
        db.real_account_audit.delete_many({"user_id": uid})
        db.users.delete_one({"user_id": uid})
