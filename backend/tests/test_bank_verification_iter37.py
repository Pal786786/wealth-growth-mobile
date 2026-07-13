"""Sprint 12.1 — Bank Verification tests."""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def demo_headers():
    r = requests.post(f"{API}/auth/login",
                      json={"identifier": "demo@mfb.in", "password": "demo1234"}, timeout=30)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/admin/login",
                      json={"email": "admin@mfb.in", "password": "Admin@MFB2026"}, timeout=30)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def bank_id(demo_headers):
    """Create a fresh bank account for the demo user."""
    payload = {
        "holder_name": "DEMO USER",
        "bank_name": "HDFC Bank",
        "ifsc": "HDFC0000123",
        "account_number": f"{uuid.uuid4().int % 10**10:010d}",
    }
    r = requests.post(f"{API}/wallet/withdrawals/bank-accounts",
                      json=payload, headers=demo_headers, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["bank_id"]


# =========================================================================
# USER
# =========================================================================
def test_user_config(demo_headers):
    r = requests.get(f"{API}/bank-verification/config", headers=demo_headers, timeout=10)
    assert r.status_code == 200
    j = r.json()
    for k in ("provider", "configured", "min_name_match_score"):
        assert k in j


def test_verify_bank_demo_success(demo_headers, bank_id):
    r = requests.post(f"{API}/bank-verification/verify/{bank_id}",
                      headers=demo_headers, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] is True
    assert j["status"] == "verified"
    assert j["provider"] == "demo"
    assert j["name_match_score"] > 0


def test_verify_is_idempotent_within_dedup_window(demo_headers, bank_id):
    # A second call within the dedup window should return duplicate/already_verified
    r = requests.post(f"{API}/bank-verification/verify/{bank_id}",
                      headers=demo_headers, timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert (j.get("already_verified") is True) or (j.get("duplicate") is True)


def test_verify_failing_account(demo_headers):
    payload = {
        "holder_name": "TEST", "bank_name": "HDFC Bank",
        "ifsc": "HDFC0000999", "account_number": "0001234567",  # starts with 000 → demo fails
    }
    r = requests.post(f"{API}/wallet/withdrawals/bank-accounts",
                      json=payload, headers=demo_headers, timeout=15)
    fail_id = r.json()["bank_id"]
    r = requests.post(f"{API}/bank-verification/verify/{fail_id}",
                      headers=demo_headers, timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is False
    assert j["status"] in ("failed", "invalid", "error")


def test_set_primary_requires_verified(demo_headers):
    payload = {"holder_name": "TEST", "bank_name": "HDFC Bank",
                 "ifsc": "HDFC0000456",
                 "account_number": f"{uuid.uuid4().int % 10**10:010d}"}
    r = requests.post(f"{API}/wallet/withdrawals/bank-accounts",
                      json=payload, headers=demo_headers, timeout=15)
    unverified_id = r.json()["bank_id"]
    r = requests.post(f"{API}/bank-verification/primary/{unverified_id}",
                      headers=demo_headers, timeout=10)
    assert r.status_code == 400  # not verified


def test_set_primary_after_verification(demo_headers, bank_id):
    r = requests.post(f"{API}/bank-verification/primary/{bank_id}",
                      headers=demo_headers, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["is_primary"] is True


def test_user_history(demo_headers, bank_id):
    r = requests.get(f"{API}/bank-verification/history",
                      headers=demo_headers, timeout=10)
    assert r.status_code == 200
    assert any(x["bank_id"] == bank_id for x in r.json()["items"])


def test_verify_unauthorized_returns_401():
    r = requests.post(f"{API}/bank-verification/verify/ba_x",
                       timeout=10)
    assert r.status_code == 401


def test_verify_nonexistent_bank_fails(demo_headers):
    r = requests.post(f"{API}/bank-verification/verify/ba_nonexistent_xxx",
                       headers=demo_headers, timeout=10)
    assert r.status_code == 400


# =========================================================================
# ADMIN
# =========================================================================
def test_admin_config_get(admin_headers):
    r = requests.get(f"{API}/admin/bank-verification/config",
                      headers=admin_headers, timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert "provider" in j
    # Secret must always be masked
    if j.get("client_secret"):
        assert j["client_secret"].startswith("•")


def test_admin_config_update(admin_headers):
    r = requests.put(f"{API}/admin/bank-verification/config",
                      json={"min_name_match_score": 55},
                      headers=admin_headers, timeout=10)
    assert r.status_code == 200
    assert r.json()["min_name_match_score"] == 55
    # restore
    requests.put(f"{API}/admin/bank-verification/config",
                  json={"min_name_match_score": 60},
                  headers=admin_headers, timeout=10)


def test_admin_test_connection(admin_headers):
    r = requests.post(f"{API}/admin/bank-verification/test-connection",
                        headers=admin_headers, timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert "ok" in j and "provider" in j


def test_admin_providers(admin_headers):
    r = requests.get(f"{API}/admin/bank-verification/providers",
                      headers=admin_headers, timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert "demo" in j["registry"] and "cashfree" in j["registry"]


def test_admin_history(admin_headers):
    r = requests.get(f"{API}/admin/bank-verification/history?limit=10",
                      headers=admin_headers, timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json()["items"], list)


# =========================================================================
# BUSINESS RULES — verify Sprint 12.1 does NOT accidentally gate other flows
# =========================================================================
def test_existing_flows_unaffected_by_bank_verification(demo_headers):
    """Signup / topup / gold / MF invest / trading MUST still work without a
    verified bank account (per business rules)."""
    r = requests.get(f"{API}/wallet", headers=demo_headers, timeout=10)
    assert r.status_code == 200
    r = requests.get(f"{API}/gold/quote", headers=demo_headers, timeout=10)
    assert r.status_code == 200
    r = requests.get(f"{API}/mf/funds?limit=1", headers=demo_headers, timeout=10)
    assert r.status_code == 200
    r = requests.get(f"{API}/mf/portfolio", headers=demo_headers, timeout=15)
    assert r.status_code == 200
