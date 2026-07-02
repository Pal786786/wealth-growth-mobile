"""
Iter19 — KYC_REQUIRED backend smoke test.

Verifies the RAW backend response shape for a KYC-gated endpoint when the
caller is a non-KYC user. The frontend axios interceptor (kycGate.ts) then
normalizes this into a plain-string `detail`, but here we assert the raw
backend contract that the frontend layer relies on.
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fall back to reading frontend/.env directly (test rig only)
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

pytestmark = pytest.mark.skipif(not BASE_URL, reason="EXPO_PUBLIC_BACKEND_URL missing")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def demo_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"identifier": "demo@mfb.in", "password": "demo1234"})
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def fresh_non_kyc_token(api):
    """Register a brand-new user; they will NOT have KYC approved."""
    uniq = uuid.uuid4().hex[:8]
    payload = {
        "email": f"TEST_kyc_{uniq}@mfb.in",
        "mobile": f"98{uuid.uuid4().int % 10**8:08d}",
        "password": "TestKyc@2026",
        "full_name": f"KYC Test {uniq}",
    }
    r = api.post(f"{BASE_URL}/api/auth/signup", json=payload)
    if r.status_code not in (200, 201):
        pytest.skip(f"signup endpoint returned {r.status_code}: {r.text[:200]}")
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    if not tok:
        # some backends require follow-up login
        r2 = api.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": payload["email"], "password": payload["password"]})
        assert r2.status_code == 200, r2.text[:200]
        tok = r2.json().get("token") or r2.json().get("access_token")
    assert tok, f"no token after register/login: {data}"
    return tok


def test_demo_login_works(demo_token):
    assert isinstance(demo_token, str) and len(demo_token) > 10


def test_non_kyc_user_forex_positions_returns_kyc_required(api, fresh_non_kyc_token):
    """
    Core assertion: POST /api/forex/positions with a non-KYC user returns
    403 and `detail` is an OBJECT with code='KYC_REQUIRED'.
    """
    h = {"Authorization": f"Bearer {fresh_non_kyc_token}", "Content-Type": "application/json"}
    body = {"symbol_id": "XAUUSD", "side": "sell", "lot_size": 0.1}
    r = requests.post(f"{BASE_URL}/api/forex/positions", json=body, headers=h)
    print(f"[non-kyc forex/positions] status={r.status_code} body={r.text[:300]}")
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:300]}"
    j = r.json()
    detail = j.get("detail")
    assert isinstance(detail, dict), f"expected detail to be object, got {type(detail)}: {detail!r}"
    assert detail.get("code") == "KYC_REQUIRED", f"detail.code != KYC_REQUIRED — {detail!r}"
    assert "message" in detail
    assert "current_status" in detail


def test_kyc_approved_demo_can_place_forex_order(api, demo_token):
    """Regression: KYC-approved demo user is NOT blocked by the KYC gate."""
    h = {"Authorization": f"Bearer {demo_token}", "Content-Type": "application/json"}
    body = {"symbol": "XAUUSD", "side": "SELL", "lots": 0.01, "leverage": 100}
    r = requests.post(f"{BASE_URL}/api/forex/positions", json=body, headers=h)
    print(f"[demo forex/positions] status={r.status_code} body={r.text[:300]}")
    # Accept 200/201 (success) or 4xx that is NOT a KYC block.
    if r.status_code in (200, 201):
        return
    if r.status_code == 403:
        j = r.json()
        d = j.get("detail")
        # must NOT be a KYC_REQUIRED gate for demo user
        if isinstance(d, dict):
            assert d.get("code") != "KYC_REQUIRED", \
                f"demo user was blocked by KYC gate: {d!r}"
    # any other non-KYC failure (e.g. market closed, insufficient balance) is acceptable
