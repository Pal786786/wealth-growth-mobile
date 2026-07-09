"""
Iter20 — P0 Hotfix Verification:
  (A) Notification crash fix — seed malformed notif docs, verify list API returns them safely.
  (B) KYC removal — fresh non-KYC user MUST be able to hit forex/wallet endpoints (200/non-403).
  (C) KYC still enforced ONLY at /wallet/withdrawals/* — fresh user MUST get 403 KYC_REQUIRED.

Reusable regression: seeds are TEST_ prefixed and left in place per convention.
"""
import os
import uuid
import time
import pytest
import requests
from pymongo import MongoClient
from datetime import datetime, timezone

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")
if not MONGO_URL or not DB_NAME:
    with open("/app/backend/.env") as f:
        for line in f:
            if line.startswith("MONGO_URL="):
                MONGO_URL = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("DB_NAME="):
                DB_NAME = line.split("=", 1)[1].strip().strip('"')

pytestmark = pytest.mark.skipif(not BASE_URL, reason="EXPO_PUBLIC_BACKEND_URL missing")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="module")
def fresh_user(api):
    uniq = uuid.uuid4().hex[:8]
    payload = {
        "email": f"TEST_iter20_{uniq}@mfb.in",
        "mobile": f"98{uuid.uuid4().int % 10**8:08d}",
        "password": "TestIter20@2026",
        "full_name": f"Iter20 Test {uniq}",
    }
    r = api.post(f"{BASE_URL}/api/auth/signup", json=payload)
    assert r.status_code in (200, 201), f"signup failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    if not tok:
        r2 = api.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": payload["email"], "password": payload["password"]})
        assert r2.status_code == 200
        tok = r2.json().get("token") or r2.json().get("access_token")
    assert tok
    user_id = data.get("user", {}).get("id") or data.get("user_id") or data.get("id")
    # try /api/auth/me
    if not user_id:
        me = requests.get(f"{BASE_URL}/api/auth/me",
                          headers={"Authorization": f"Bearer {tok}"})
        if me.status_code == 200:
            user_id = me.json().get("id") or me.json().get("user_id") or me.json().get("_id")
    return {"token": tok, "user_id": user_id, "email": payload["email"]}


def _auth(t): return {"Authorization": f"Bearer {t['token']}", "Content-Type": "application/json"}


# ============================================================
# (A) NOTIFICATION CRASH FIX — seed malformed docs
# ============================================================

class TestNotificationCrashFix:
    """Seed malformed notification docs and verify list API returns them without 500."""

    def test_seed_malformed_and_list(self, db, fresh_user):
        uid = fresh_user["user_id"]
        assert uid, "user_id missing on fresh_user — cannot seed"

        now = datetime.now(timezone.utc)
        # Doc A: missing `category`
        docA = {
            "notif_id": f"TEST_iter20_A_{uuid.uuid4().hex[:6]}",
            "user_id": uid,
            "title": "A - missing category",
            "body": "body A",
            "read": False,
            "priority": "normal",
            "created_at": now,
        }
        # Doc B: missing `title` and `read`
        docB = {
            "notif_id": f"TEST_iter20_B_{uuid.uuid4().hex[:6]}",
            "user_id": uid,
            "category": "wallet",
            "body": "body B",
            "priority": "normal",
            "created_at": now,
        }
        # Doc C: missing `notif_id` and `created_at`
        docC = {
            "user_id": uid,
            "category": "kyc",
            "title": "C no notif_id",
            "body": "body C",
            "read": False,
            "priority": "critical",
        }
        db.notifications.insert_many([docA, docB, docC])

        r = requests.get(f"{BASE_URL}/api/notifications?limit=100",
                         headers={"Authorization": f"Bearer {fresh_user['token']}"})
        assert r.status_code == 200, f"list failed: {r.status_code} {r.text[:300]}"
        j = r.json()
        assert "items" in j, f"missing items: {j}"
        titles_bodies = [(it.get("title"), it.get("body")) for it in j["items"]]
        print(f"[notif list] {len(j['items'])} items; sample={titles_bodies[:5]}")
        # We expect our 3 seed docs to appear (backend may or may not filter malformed)
        found_bodies = {it.get("body") for it in j["items"]}
        seeded = {"body A", "body B", "body C"}
        assert seeded.issubset(found_bodies), \
            f"Not all seeded notifs returned. Missing: {seeded - found_bodies}"

    def test_preferences_endpoint(self, fresh_user):
        h = {"Authorization": f"Bearer {fresh_user['token']}"}
        r = requests.get(f"{BASE_URL}/api/notifications/preferences", headers=h)
        assert r.status_code == 200, f"prefs get: {r.status_code} {r.text[:200]}"
        toggle_payload = {"push_enabled": True, "wallet_alerts": True}
        r2 = requests.put(f"{BASE_URL}/api/notifications/preferences",
                          headers={**h, "Content-Type": "application/json"},
                          json=toggle_payload)
        assert r2.status_code == 200, f"prefs put: {r2.status_code} {r2.text[:200]}"


# ============================================================
# (B) KYC REMOVAL — non-KYC user allowed on forex/wallet
# ============================================================

class TestKycRemoval:
    """Fresh non-KYC user must NOT be gated on forex/wallet trading endpoints."""

    def test_forex_buy_xauusd(self, fresh_user):
        r = requests.post(f"{BASE_URL}/api/forex/positions",
                          json={"symbol_id": "XAUUSD", "side": "buy", "lot_size": 0.01},
                          headers=_auth(fresh_user))
        print(f"[forex buy] {r.status_code} {r.text[:250]}")
        assert r.status_code != 403 or _not_kyc_block(r), \
            f"Non-KYC user blocked on forex BUY: {r.status_code} {r.text[:250]}"
        # ideally 200
        if r.status_code == 200:
            j = r.json()
            # Store position_id for later close
            pytest.forex_pos_id = j.get("position_id") or j.get("id") or j.get("_id")
            assert "entry_price" in j or "price" in j, f"missing entry_price: {j}"

    def test_forex_sell_eurusd(self, fresh_user):
        r = requests.post(f"{BASE_URL}/api/forex/positions",
                          json={"symbol_id": "EURUSD", "side": "sell", "lot_size": 0.1},
                          headers=_auth(fresh_user))
        print(f"[forex sell] {r.status_code} {r.text[:250]}")
        assert r.status_code != 403 or _not_kyc_block(r), \
            f"Non-KYC user blocked on forex SELL: {r.status_code} {r.text[:250]}"

    def test_wallet_send(self, fresh_user):
        r = requests.post(f"{BASE_URL}/api/wallet/send",
                          json={"amount": 50, "recipient": "9999900002"},
                          headers=_auth(fresh_user))
        print(f"[wallet/send] {r.status_code} {r.text[:250]}")
        assert r.status_code != 403 or _not_kyc_block(r), \
            f"Non-KYC user blocked on wallet/send: {r.status_code} {r.text[:250]}"

    def test_wallet_recharge(self, fresh_user):
        r = requests.post(f"{BASE_URL}/api/wallet/recharge",
                          json={"amount": 100, "mobile": "9999900002",
                                "operator": "Jio", "plan_name": "Basic"},
                          headers=_auth(fresh_user))
        print(f"[wallet/recharge] {r.status_code} {r.text[:250]}")
        assert r.status_code != 403 or _not_kyc_block(r), \
            f"Non-KYC user blocked on wallet/recharge: {r.status_code} {r.text[:250]}"

    def test_wallet_billpay(self, fresh_user):
        r = requests.post(f"{BASE_URL}/api/wallet/billpay",
                          json={"amount": 100, "biller_name": "X",
                                "biller_type": "electricity", "consumer_number": "123"},
                          headers=_auth(fresh_user))
        print(f"[wallet/billpay] {r.status_code} {r.text[:250]}")
        assert r.status_code != 403 or _not_kyc_block(r), \
            f"Non-KYC user blocked on wallet/billpay: {r.status_code} {r.text[:250]}"

    def test_wallet_topup_create_session(self, fresh_user):
        r = requests.post(f"{BASE_URL}/api/wallet/topup/create-session",
                          json={"amount": 500},
                          headers=_auth(fresh_user))
        print(f"[wallet/topup] {r.status_code} {r.text[:250]}")
        assert r.status_code != 403 or _not_kyc_block(r), \
            f"Non-KYC user blocked on wallet/topup: {r.status_code} {r.text[:250]}"

    def test_wallet_payments_create(self, fresh_user):
        r = requests.post(f"{BASE_URL}/api/wallet/payments/create",
                          json={"amount": 500},
                          headers=_auth(fresh_user))
        print(f"[wallet/payments/create] {r.status_code} {r.text[:250]}")
        assert r.status_code != 403 or _not_kyc_block(r), \
            f"Non-KYC user blocked on wallet/payments/create: {r.status_code} {r.text[:250]}"

    def test_forex_open_list(self, fresh_user):
        r = requests.get(f"{BASE_URL}/api/forex/positions?status=open",
                         headers=_auth(fresh_user))
        print(f"[forex list open] {r.status_code} count={len(r.json()) if r.ok else '-'}")
        assert r.status_code == 200, f"list open: {r.status_code} {r.text[:200]}"

    def test_forex_close_position(self, fresh_user):
        pos_id = getattr(pytest, "forex_pos_id", None)
        if not pos_id:
            pytest.skip("no position_id captured from BUY test")
        r = requests.post(f"{BASE_URL}/api/forex/positions/{pos_id}/close",
                          headers=_auth(fresh_user))
        print(f"[forex close] {r.status_code} {r.text[:200]}")
        assert r.status_code in (200, 201), f"close: {r.status_code} {r.text[:200]}"


def _not_kyc_block(r):
    """Return True if a 403 is NOT a KYC_REQUIRED gate (some other 403)."""
    try:
        j = r.json()
        d = j.get("detail")
        if isinstance(d, dict) and d.get("code") == "KYC_REQUIRED":
            return False
        if isinstance(d, str) and "KYC" in d.upper():
            return False
        return True
    except Exception:
        return True


# ============================================================
# (C) KYC STILL ENFORCED — Withdrawal must still be blocked
# ============================================================

class TestKycStillEnforcedOnWithdrawal:

    def test_withdrawal_request_blocked(self, fresh_user):
        r = requests.post(f"{BASE_URL}/api/wallet/withdrawals/request",
                          json={"amount": 100, "bank_account_id": "dummy"},
                          headers=_auth(fresh_user))
        print(f"[withdrawal/request] {r.status_code} {r.text[:300]}")
        assert r.status_code == 403, f"withdrawal MUST be 403 for non-KYC, got {r.status_code}"
        j = r.json()
        d = j.get("detail")
        is_kyc = (isinstance(d, dict) and d.get("code") == "KYC_REQUIRED") or \
                 (isinstance(d, str) and "KYC" in d.upper())
        assert is_kyc, f"withdrawal 403 detail is not KYC-shaped: {d!r}"

    def test_withdrawal_bank_accounts_blocked(self, fresh_user):
        r = requests.post(f"{BASE_URL}/api/wallet/withdrawals/bank-accounts",
                          json={"account_number": "1234567890",
                                "ifsc": "HDFC0001234",
                                "holder_name": "Test User",
                                "bank_name": "HDFC BANK"},
                          headers=_auth(fresh_user))
        print(f"[withdrawal/bank-accounts] {r.status_code} {r.text[:300]}")
        assert r.status_code == 403, f"bank-accounts MUST be 403 for non-KYC, got {r.status_code}"

    def test_withdrawal_passes_after_kyc_approved(self, db, fresh_user):
        uid = fresh_user["user_id"]
        db.kyc_profiles.update_one(
            {"user_id": uid},
            {"$set": {"status": "approved", "user_id": uid}},
            upsert=True,
        )
        # also credit the wallet so we don't get instant-insufficient
        db.wallets.update_one(
            {"user_id": uid},
            {"$set": {"balance": 50000, "user_id": uid}},
            upsert=True,
        )
        time.sleep(0.3)
        r = requests.post(f"{BASE_URL}/api/wallet/withdrawals/request",
                          json={"amount": 100, "bank_account_id": "dummy"},
                          headers=_auth(fresh_user))
        print(f"[withdrawal after kyc approved] {r.status_code} {r.text[:300]}")
        # must NOT be KYC-blocked now — any non-KYC failure (missing bank acc etc) is fine
        if r.status_code == 403:
            j = r.json()
            d = j.get("detail")
            is_kyc = (isinstance(d, dict) and d.get("code") == "KYC_REQUIRED") or \
                     (isinstance(d, str) and "KYC" in d.upper())
            assert not is_kyc, f"still KYC-blocked after approving: {d!r}"
