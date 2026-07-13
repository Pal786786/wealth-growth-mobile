"""Sprint 2 — Withdrawal module comprehensive backend tests.

Covers:
  - Bank account CRUD (KYC gate, IFSC validation, masking)
  - Withdrawal request lifecycle (min/max, insufficient bal, duplicate, rate limit, idempotency)
  - OTP verify / resend cooldown / attempts / expiry
  - User cancel with refund
  - Detail + list + PDF receipt
  - Admin: dashboard, state transitions, refund-on-reject, bulk, CSV, settings
"""
import os
import time
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wealth-growth-mobile.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
DEMO_ID = "demo@mfb.in"
DEMO_PW = "demo1234"
ADMIN_ID = "admin@mfb.in"
ADMIN_PW = "Admin@MFB2026"


@pytest.fixture(scope="module")
def mongo():
    m = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return m[os.environ.get("DB_NAME", "my_funding_bank")]


@pytest.fixture(scope="module")
def user_token():
    r = requests.post(f"{API}/auth/login", json={"identifier": DEMO_ID, "password": DEMO_PW})
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]["user_id"]


@pytest.fixture(scope="module")
def uhdr(user_token):
    return {"Authorization": f"Bearer {user_token[0]}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def uid(user_token):
    return user_token[1]


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/admin/login", json={"email": ADMIN_ID, "password": ADMIN_PW})
    assert r.status_code == 200, r.text
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def ahdr(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module", autouse=True)
def _seed(mongo, uid):
    # Ensure KYC approved + wallet balance sufficient
    mongo.kyc_profiles.update_one({"user_id": uid}, {"$set": {"status": "approved", "user_id": uid}}, upsert=True)
    mongo.wallets.update_one({"user_id": uid}, {"$set": {"balance": 200000, "user_id": uid, "currency": "INR"}}, upsert=True)
    # Boost rate limit + daily count for testing.
    # Sprint 12.2 — also relax the new gates so this legacy Sprint 2A suite still passes:
    #   * `require_verified_bank`: legacy tests create banks without penny-drop.
    #   * `single_pending_only`: legacy tests intentionally issue multiple in-flight requests.
    #   * `auto_approve_enabled`: legacy tests expect the manual admin approval flow.
    #   * `hard_reject_amount`: keep aligned with legacy `max_amount` (₹100k).
    #   * `compliance_hold`: never on during regression.
    mongo.withdrawal_settings.update_one({"_id": "singleton"},
        {"$set": {"rate_limit_per_hour": 50, "daily_max_count": 50,
                  "duplicate_window_seconds": 60, "min_amount": 100,
                  "max_amount": 100000, "promo_waiver": True,
                  # Sprint 12.2 compat toggles
                  "require_verified_bank": False,
                  "single_pending_only": False,
                  "auto_approve_enabled": False,
                  "auto_dispatch_on_approve": False,
                  "hard_reject_amount": 100000,
                  "monthly_max_amount": 10_000_000,
                  "compliance_hold": False}}, upsert=True)
    # Clean past withdrawal requests for the demo user to keep counters low
    mongo.withdrawal_requests.delete_many({"user_id": uid})
    mongo.withdrawal_otps.delete_many({"user_id": uid})
    yield


# ---------------- BANK ACCOUNT TESTS ----------------
class TestBankAccounts:
    def test_add_bank_invalid_ifsc(self, uhdr):
        r = requests.post(f"{API}/wallet/withdrawals/bank-accounts", headers=uhdr,
                          json={"holder_name": "Demo User", "bank_name": "HDFC",
                                "ifsc": "INVALID1234", "account_number": "1234567890"})
        assert r.status_code == 400
        assert "IFSC" in r.text

    def test_add_bank_valid(self, uhdr):
        r = requests.post(f"{API}/wallet/withdrawals/bank-accounts", headers=uhdr,
                          json={"holder_name": "Demo User", "bank_name": "HDFC Bank",
                                "ifsc": "HDFC0001234", "account_number": "1234567890123"})
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        assert "bank_id" in r.json()
        pytest.bank_id = r.json()["bank_id"]

    def test_list_banks_masked_only(self, uhdr):
        r = requests.get(f"{API}/wallet/withdrawals/bank-accounts", headers=uhdr)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        for it in items:
            assert "account_number" not in it, "Raw account number must NOT be exposed"
            assert "account_masked" in it
            assert it["account_masked"].startswith("X")

    def test_add_bank_duplicate_returns_same(self, uhdr):
        r = requests.post(f"{API}/wallet/withdrawals/bank-accounts", headers=uhdr,
                          json={"holder_name": "Demo User", "bank_name": "HDFC Bank",
                                "ifsc": "HDFC0001234", "account_number": "1234567890123"})
        assert r.status_code == 200
        assert r.json().get("duplicate") is True


# ---------------- WITHDRAWAL REQUEST + OTP ----------------
class TestWithdrawRequest:
    def test_request_below_min(self, uhdr):
        r = requests.post(f"{API}/wallet/withdrawals/request", headers=uhdr,
                          json={"amount": 50, "bank_account_id": pytest.bank_id})
        assert r.status_code == 400
        assert "Minimum" in r.text

    def test_request_above_max(self, uhdr):
        r = requests.post(f"{API}/wallet/withdrawals/request", headers=uhdr,
                          json={"amount": 200000, "bank_account_id": pytest.bank_id})
        assert r.status_code == 400
        assert "Maximum" in r.text

    def test_request_insufficient_balance(self, uhdr, mongo, uid):
        # Temporarily reduce balance
        mongo.wallets.update_one({"user_id": uid}, {"$set": {"balance": 10}})
        r = requests.post(f"{API}/wallet/withdrawals/request", headers=uhdr,
                          json={"amount": 5000, "bank_account_id": pytest.bank_id})
        assert r.status_code == 400
        assert "Insufficient" in r.text
        mongo.wallets.update_one({"user_id": uid}, {"$set": {"balance": 200000}})

    def test_request_happy_path(self, uhdr):
        r = requests.post(f"{API}/wallet/withdrawals/request", headers=uhdr,
                          json={"amount": 500, "bank_account_id": pytest.bank_id})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["reference_no"].startswith("MFB-W-")
        assert "otp_demo" in d
        pytest.wid = d["withdrawal_id"]
        pytest.otp = d["otp_demo"]

    def test_request_duplicate_window(self, uhdr):
        # Same amount within 60s window should 429
        r = requests.post(f"{API}/wallet/withdrawals/request", headers=uhdr,
                          json={"amount": 500, "bank_account_id": pytest.bank_id})
        assert r.status_code == 429
        assert "Duplicate" in r.text

    def test_idempotency_key_dedupe(self, uhdr):
        key = f"test-idem-{uuid.uuid4()}"
        hdr = {**uhdr, "Idempotency-Key": key}
        r1 = requests.post(f"{API}/wallet/withdrawals/request", headers=hdr,
                           json={"amount": 777, "bank_account_id": pytest.bank_id})
        assert r1.status_code == 200
        wid1 = r1.json()["withdrawal_id"]
        r2 = requests.post(f"{API}/wallet/withdrawals/request", headers=hdr,
                           json={"amount": 777, "bank_account_id": pytest.bank_id})
        assert r2.status_code == 200
        assert r2.json().get("idempotent") is True
        assert r2.json()["withdrawal_id"] == wid1


# ---------------- OTP FLOW ----------------
class TestOTP:
    def test_wrong_otp(self, uhdr):
        r = requests.post(f"{API}/wallet/withdrawals/verify-otp", headers=uhdr,
                          json={"withdrawal_id": pytest.wid, "otp": "000000"})
        assert r.status_code == 400
        assert "Invalid OTP" in r.text

    def test_resend_cooldown(self, uhdr):
        # Immediately after create — should be within cooldown (30s)
        r = requests.post(f"{API}/wallet/withdrawals/resend-otp", headers=uhdr,
                          json={"withdrawal_id": pytest.wid})
        assert r.status_code == 429
        assert "wait" in r.text.lower()

    def test_verify_correct_otp(self, uhdr):
        r = requests.post(f"{API}/wallet/withdrawals/verify-otp", headers=uhdr,
                          json={"withdrawal_id": pytest.wid, "otp": pytest.otp})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "under_review"

    def test_verify_already_verified(self, uhdr):
        r = requests.post(f"{API}/wallet/withdrawals/verify-otp", headers=uhdr,
                          json={"withdrawal_id": pytest.wid, "otp": pytest.otp})
        assert r.status_code == 400

    def test_wallet_debited_after_otp(self, mongo, uid):
        w = mongo.wallets.find_one({"user_id": uid})
        assert w["balance"] <= 199500  # started at 200000, debited 500


# ---------------- LIST + DETAIL + PDF ----------------
class TestListDetail:
    def test_list_history(self, uhdr):
        r = requests.get(f"{API}/wallet/withdrawals?limit=10", headers=uhdr)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "total" in d
        assert d["total"] >= 1

    def test_list_status_filter(self, uhdr):
        r = requests.get(f"{API}/wallet/withdrawals?status=under_review", headers=uhdr)
        assert r.status_code == 200
        for it in r.json()["items"]:
            assert it["status"] == "under_review"

    def test_detail_with_timeline(self, uhdr):
        r = requests.get(f"{API}/wallet/withdrawals/{pytest.wid}", headers=uhdr)
        assert r.status_code == 200
        d = r.json()
        assert d["withdrawal"]["withdrawal_id"] == pytest.wid
        events = [t["event"] for t in d["timeline"]]
        assert "created" in events
        assert "otp_verified" in events

    def test_receipt_pdf(self, uhdr):
        r = requests.get(f"{API}/wallet/withdrawals/{pytest.wid}/receipt.pdf", headers=uhdr)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert len(r.content) > 2000, f"PDF too small ({len(r.content)} bytes)"


# ---------------- CANCEL WITH REFUND ----------------
class TestCancel:
    def test_cancel_and_refund(self, uhdr, mongo, uid):
        # Create + verify a new withdrawal, then cancel
        # First, wait for duplicate window since amount 500 is blocked
        r = requests.post(f"{API}/wallet/withdrawals/request", headers=uhdr,
                          json={"amount": 250, "bank_account_id": pytest.bank_id})
        assert r.status_code == 200, r.text
        wid = r.json()["withdrawal_id"]
        otp = r.json()["otp_demo"]
        v = requests.post(f"{API}/wallet/withdrawals/verify-otp", headers=uhdr,
                          json={"withdrawal_id": wid, "otp": otp})
        assert v.status_code == 200
        bal_before = mongo.wallets.find_one({"user_id": uid})["balance"]
        c = requests.post(f"{API}/wallet/withdrawals/{wid}/cancel", headers=uhdr)
        assert c.status_code == 200
        bal_after = mongo.wallets.find_one({"user_id": uid})["balance"]
        assert bal_after == bal_before + 250, f"Refund missing: {bal_before} -> {bal_after}"


# ---------------- ADMIN TESTS ----------------
class TestAdmin:
    def test_dashboard(self, ahdr):
        r = requests.get(f"{API}/admin/withdrawals/dashboard", headers=ahdr)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "stats" in d and "chart" in d
        assert len(d["chart"]) == 7

    def test_list_admin(self, ahdr):
        r = requests.get(f"{API}/admin/withdrawals?limit=50", headers=ahdr)
        assert r.status_code == 200
        assert "items" in r.json()

    def test_get_settings(self, ahdr):
        r = requests.get(f"{API}/admin/withdrawals/settings", headers=ahdr)
        assert r.status_code == 200
        s = r.json()
        assert "min_amount" in s and "max_amount" in s

    def test_update_settings_propagates(self, ahdr, uhdr):
        r = requests.put(f"{API}/admin/withdrawals/settings", headers=ahdr,
                        json={"min_amount": 250})
        assert r.status_code == 200
        # Verify user-facing endpoint reflects change
        u = requests.get(f"{API}/wallet/withdrawals/settings", headers=uhdr)
        assert u.status_code == 200
        assert u.json()["min_amount"] == 250
        # Restore
        requests.put(f"{API}/admin/withdrawals/settings", headers=ahdr,
                     json={"min_amount": 100})

    def test_full_state_transition_approve_processing_complete(self, uhdr, ahdr):
        # Create new withdrawal
        r = requests.post(f"{API}/wallet/withdrawals/request", headers=uhdr,
                          json={"amount": 1100, "bank_account_id": pytest.bank_id})
        assert r.status_code == 200, r.text
        wid = r.json()["withdrawal_id"]
        otp = r.json()["otp_demo"]
        # Verify OTP
        requests.post(f"{API}/wallet/withdrawals/verify-otp", headers=uhdr,
                      json={"withdrawal_id": wid, "otp": otp})
        # Approve
        a = requests.post(f"{API}/admin/withdrawals/{wid}/approve", headers=ahdr)
        assert a.status_code == 200, a.text
        assert a.json()["status"] == "approved"
        # Processing
        p = requests.post(f"{API}/admin/withdrawals/{wid}/processing", headers=ahdr)
        assert p.status_code == 200
        # Complete
        c = requests.post(f"{API}/admin/withdrawals/{wid}/completed", headers=ahdr)
        assert c.status_code == 200
        assert c.json()["status"] == "completed"

    def test_reject_requires_reason(self, uhdr, ahdr):
        r = requests.post(f"{API}/wallet/withdrawals/request", headers=uhdr,
                          json={"amount": 1200, "bank_account_id": pytest.bank_id})
        wid = r.json()["withdrawal_id"]
        otp = r.json()["otp_demo"]
        requests.post(f"{API}/wallet/withdrawals/verify-otp", headers=uhdr,
                      json={"withdrawal_id": wid, "otp": otp})
        # Reject without reason
        no = requests.post(f"{API}/admin/withdrawals/{wid}/reject", headers=ahdr, json={})
        assert no.status_code == 400
        # Reject with reason -> refund
        rr = requests.post(f"{API}/admin/withdrawals/{wid}/reject", headers=ahdr,
                           json={"reason": "Suspicious pattern"})
        assert rr.status_code == 200

    def test_reject_refunds_wallet(self, uhdr, ahdr, mongo, uid):
        # New req to isolate
        r = requests.post(f"{API}/wallet/withdrawals/request", headers=uhdr,
                          json={"amount": 1300, "bank_account_id": pytest.bank_id})
        wid = r.json()["withdrawal_id"]
        otp = r.json()["otp_demo"]
        requests.post(f"{API}/wallet/withdrawals/verify-otp", headers=uhdr,
                      json={"withdrawal_id": wid, "otp": otp})
        bal_before = mongo.wallets.find_one({"user_id": uid})["balance"]
        rr = requests.post(f"{API}/admin/withdrawals/{wid}/reject", headers=ahdr,
                           json={"reason": "test refund"})
        assert rr.status_code == 200
        bal_after = mongo.wallets.find_one({"user_id": uid})["balance"]
        assert bal_after == bal_before + 1300, f"Refund on reject failed: {bal_before} -> {bal_after}"

    def test_illegal_transition(self, uhdr, ahdr):
        # Create fresh in pending, try to approve directly (not allowed, must be under_review)
        r = requests.post(f"{API}/wallet/withdrawals/request", headers=uhdr,
                          json={"amount": 1400, "bank_account_id": pytest.bank_id})
        wid = r.json()["withdrawal_id"]
        a = requests.post(f"{API}/admin/withdrawals/{wid}/approve", headers=ahdr)
        assert a.status_code == 400
        assert "Cannot go from pending" in a.text

    def test_failed_refunds_wallet(self, uhdr, ahdr, mongo, uid):
        r = requests.post(f"{API}/wallet/withdrawals/request", headers=uhdr,
                          json={"amount": 1500, "bank_account_id": pytest.bank_id})
        wid = r.json()["withdrawal_id"]
        otp = r.json()["otp_demo"]
        requests.post(f"{API}/wallet/withdrawals/verify-otp", headers=uhdr,
                      json={"withdrawal_id": wid, "otp": otp})
        requests.post(f"{API}/admin/withdrawals/{wid}/approve", headers=ahdr)
        bal_before = mongo.wallets.find_one({"user_id": uid})["balance"]
        f = requests.post(f"{API}/admin/withdrawals/{wid}/failed", headers=ahdr,
                          json={"reason": "Bank rejected"})
        assert f.status_code == 200
        bal_after = mongo.wallets.find_one({"user_id": uid})["balance"]
        assert bal_after == bal_before + 1500

    def test_bulk_action(self, uhdr, ahdr):
        wids = []
        for amt in (1600, 1700):
            r = requests.post(f"{API}/wallet/withdrawals/request", headers=uhdr,
                              json={"amount": amt, "bank_account_id": pytest.bank_id})
            wid = r.json()["withdrawal_id"]
            otp = r.json()["otp_demo"]
            requests.post(f"{API}/wallet/withdrawals/verify-otp", headers=uhdr,
                          json={"withdrawal_id": wid, "otp": otp})
            wids.append(wid)
        r = requests.post(f"{API}/admin/withdrawals/bulk", headers=ahdr,
                          json={"action": "approve", "ids": wids})
        assert r.status_code == 200
        assert r.json()["processed"] == 2

    def test_export_csv(self, ahdr):
        r = requests.get(f"{API}/admin/withdrawals/export.csv", headers=ahdr)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("text/csv")
        text = r.content.decode()
        assert "reference_no" in text.splitlines()[0]


# ---------------- KYC GATE ----------------
class TestKYCGate:
    def test_kyc_gate_blocks_when_not_approved(self, uhdr, mongo, uid):
        """KYC gate was intentionally moved from bank-account add to the actual
        withdrawal request endpoint (product decision: allow users to set up
        their banking details ahead of KYC approval). Verify KYC still blocks
        the withdrawal-request endpoint for non-approved users."""
        mongo.kyc_profiles.update_one({"user_id": uid}, {"$set": {"status": "pending"}})
        r = requests.post(f"{API}/wallet/withdrawals/request", headers=uhdr,
                          json={"amount": 500, "bank_account_id": "ba_missing"})
        assert r.status_code in (400, 403), f"Expected KYC gate block on withdrawal request, got {r.status_code}: {r.text}"
        # Restore
        mongo.kyc_profiles.update_one({"user_id": uid}, {"$set": {"status": "approved"}})
