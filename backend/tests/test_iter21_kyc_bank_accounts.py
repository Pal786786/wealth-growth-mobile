"""
Iter21 backend regression:
  1. Fresh signup (kyc_status='not_started') can hit these endpoints WITHOUT 403 KYC_REQUIRED:
     - POST /api/forex/positions (BUY, SELL)
     - POST /api/invest/buy
     - POST /api/wallet/send
     - POST /api/wallet/recharge
     - POST /api/wallet/billpay
     - POST /api/wallet/topup/create-session
     - POST /api/wallet/payments/create
     - POST /api/wallet/withdrawals/bank-accounts   (NEW — was 403 pre iter21)
  2. POST /api/wallet/withdrawals/request MUST still return 403 KYC_REQUIRED.
"""
import os
import secrets
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"


def _signup_fresh():
    tag = secrets.token_hex(4)
    email = f"TEST_iter21_{tag}@mfb.in"
    mobile = "9" + str(secrets.randbelow(10**9)).rjust(9, "0")
    r = requests.post(
        f"{BASE_URL}/api/auth/signup",
        json={
            "full_name": f"Test Iter21 {tag}",
            "email": email,
            "mobile": mobile,
            "password": "Testpass1234",
        },
        timeout=30,
    )
    assert r.status_code in (200, 201), f"signup failed {r.status_code} {r.text[:200]}"
    body = r.json()
    tok = body.get("token") or body.get("access_token") or body.get("session", {}).get("token")
    assert tok, f"no token in signup response {body}"
    return tok, email, mobile


@pytest.fixture(scope="module")
def fresh():
    tok, email, mobile = _signup_fresh()
    return {"token": tok, "email": email, "mobile": mobile, "headers": {"Authorization": f"Bearer {tok}"}}


def _kyc_required(resp):
    """Return True iff response is a 403 with detail.code == KYC_REQUIRED."""
    if resp.status_code != 403:
        return False
    try:
        d = resp.json().get("detail")
        if isinstance(d, dict):
            return d.get("code") == "KYC_REQUIRED"
    except Exception:
        return False
    return False


class TestKycNotBlocking:
    def test_kyc_status_not_started(self, fresh):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=fresh["headers"], timeout=15)
        assert r.status_code == 200
        # kyc_status may be 'pending' or 'not_started' depending on shape
        assert r.json().get("kyc_status") in ("pending", "not_started", None)

    def test_forex_buy_xauusd(self, fresh):
        r = requests.post(
            f"{BASE_URL}/api/forex/positions",
            headers=fresh["headers"],
            json={"symbol_id": "XAUUSD", "side": "buy", "lot_size": 0.01},
            timeout=20,
        )
        assert not _kyc_required(r), f"KYC gate present! {r.text[:200]}"
        assert r.status_code in (200, 201, 400, 402), f"unexpected {r.status_code} {r.text[:200]}"

    def test_forex_sell_eurusd(self, fresh):
        r = requests.post(
            f"{BASE_URL}/api/forex/positions",
            headers=fresh["headers"],
            json={"symbol_id": "EURUSD", "side": "sell", "lot_size": 0.1},
            timeout=20,
        )
        assert not _kyc_required(r), f"KYC gate present! {r.text[:200]}"

    def test_invest_buy(self, fresh):
        r = requests.post(
            f"{BASE_URL}/api/invest/buy",
            headers=fresh["headers"],
            json={
                "asset_id": "MF1",
                "asset_type": "mutual_fund",
                "asset_name": "HDFC",
                "amount": 100,
                "units": 1,
                "sip": False,
            },
            timeout=20,
        )
        assert not _kyc_required(r), f"KYC gate present! {r.text[:200]}"

    def test_wallet_send(self, fresh):
        r = requests.post(
            f"{BASE_URL}/api/wallet/send",
            headers=fresh["headers"],
            json={"amount": 50, "recipient": "9999900002"},
            timeout=20,
        )
        assert not _kyc_required(r), f"KYC gate present! {r.text[:200]}"

    def test_wallet_recharge(self, fresh):
        r = requests.post(
            f"{BASE_URL}/api/wallet/recharge",
            headers=fresh["headers"],
            json={"amount": 100, "operator": "Jio", "plan": "Basic", "mobile": "9999900002"},
            timeout=20,
        )
        assert not _kyc_required(r), f"KYC gate present! {r.text[:200]}"

    def test_wallet_billpay(self, fresh):
        r = requests.post(
            f"{BASE_URL}/api/wallet/billpay",
            headers=fresh["headers"],
            json={"amount": 100, "category": "electricity", "biller": "BESCOM", "consumer_id": "123"},
            timeout=20,
        )
        assert not _kyc_required(r), f"KYC gate present! {r.text[:200]}"

    def test_wallet_topup_create_session(self, fresh):
        r = requests.post(
            f"{BASE_URL}/api/wallet/topup/create-session",
            headers=fresh["headers"],
            json={"amount": 500},
            timeout=20,
        )
        assert not _kyc_required(r), f"KYC gate present! {r.text[:200]}"

    def test_wallet_payments_create(self, fresh):
        r = requests.post(
            f"{BASE_URL}/api/wallet/payments/create",
            headers=fresh["headers"],
            json={"amount": 500},
            timeout=20,
        )
        assert not _kyc_required(r), f"KYC gate present! {r.text[:200]}"

    def test_withdrawals_bank_accounts_add(self, fresh):
        # NEW in iter21 — was 403 KYC_REQUIRED before iter21, must now succeed.
        r = requests.post(
            f"{BASE_URL}/api/wallet/withdrawals/bank-accounts",
            headers=fresh["headers"],
            json={
                "holder_name": "Test Iter21",
                "bank_name": "HDFC Bank",
                "account_number": "1234567890",
                "ifsc": "HDFC0001234",
            },
            timeout=20,
        )
        assert not _kyc_required(r), f"KYC gate still present on bank-accounts! {r.text[:200]}"
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:200]}"
        j = r.json()
        assert j.get("ok") is True
        assert j.get("bank_id"), "bank_id missing"

    def test_withdrawals_request_still_gated(self, fresh):
        # MUST still 403 KYC_REQUIRED
        r = requests.post(
            f"{BASE_URL}/api/wallet/withdrawals/request",
            headers=fresh["headers"],
            json={"amount": 500, "bank_account_id": "ba_fake"},
            timeout=20,
        )
        assert _kyc_required(r), (
            f"withdrawals/request MUST still be KYC gated. got {r.status_code} {r.text[:200]}"
        )
