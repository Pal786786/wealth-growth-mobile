"""Sprint 17 — Real MT5 Account Module (Phase 1) test suite.

Covers the 18 mandated cases. MT5 Manager API is NOT configured in this
environment, so live provisioning honestly returns MT5_UNAVAILABLE (FAILED);
success/timeout paths are exercised against the isolated service seam.

Run: cd /app/backend && python -m pytest tests/test_real_accounts.py -v
"""
import asyncio
import sys
import time
import uuid

import pytest
import requests
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")

API = "http://localhost:8001/api"
DB = MongoClient("mongodb://localhost:27017").my_funding_bank

ADMIN = {"email": "admin@mfb.in", "password": "Admin@MFB2026"}


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def user():
    """Fresh signup so the account slot is empty; cleaned up afterwards."""
    email = f"ra_test_{uuid.uuid4().hex[:8]}@test.mfb"
    r = requests.post(f"{API}/auth/signup", json={
        "full_name": "RA Tester", "email": email,
        "mobile": f"9{int(time.time()) % 1000000000:09d}", "password": "Test@1234",
    }, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    tok = d.get("access_token") or d.get("token")
    uid = (d.get("user") or {}).get("user_id") or d.get("user_id")
    yield {"email": email, "token": tok, "user_id": uid,
           "h": {"Authorization": f"Bearer {tok}"}}
    DB.real_trading_accounts.delete_many({"user_id": uid})
    DB.real_account_audit.delete_many({"user_id": uid})
    DB.users.delete_one({"user_id": uid})


@pytest.fixture(scope="module")
def admin_h():
    r = requests.post(f"{API}/admin/login", json=ADMIN, timeout=20)
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ------------------------------------------------------------------ 1-3
class TestApplication:
    def test_1_user_without_account_can_apply(self, user):
        before_wallet = DB.forex_wallets.find_one({"user_id": user["user_id"]}) or {}
        r = requests.post(f"{API}/real-account/apply",
                          json={"email": user["email"]}, headers=user["h"], timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        # MT5 Manager API is NOT configured here → honest FAILED, never fake
        assert j["status"] == "FAILED"
        assert j["error_code"] == "MT5_UNAVAILABLE"
        assert j["account"]["mt5_account_number"] is None  # NO fake numbers
        assert j["account"]["email"] == user["email"].lower()
        self.__class__.app_id = j["account"]["application_id"]

    def test_2_email_validation(self, user):
        r = requests.post(f"{API}/real-account/apply",
                          json={"email": "not-an-email"}, headers=user["h"], timeout=20)
        assert r.status_code == 422

    def test_3_duplicate_prevention(self, user):
        # Promote to ACTIVE, then apply again → DUPLICATE, no second doc
        DB.real_trading_accounts.update_one(
            {"user_id": user["user_id"]}, {"$set": {"status": "ACTIVE",
                                                    "mt5_account_number": "777001"}})
        r = requests.post(f"{API}/real-account/apply",
                          json={"email": user["email"]}, headers=user["h"], timeout=20)
        j = r.json()
        assert j["success"] is False and j["error_code"] == "DUPLICATE_ACCOUNT"
        assert DB.real_trading_accounts.count_documents({"user_id": user["user_id"]}) == 1
        DB.real_trading_accounts.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"status": "FAILED", "mt5_account_number": None}})


# ------------------------------------------------------------------ 4-9
class TestProvisioningStates:
    def _fake_provision(self, result):
        """Run real_accounts._provision against the real local DB with a fake
        MT5 outcome, using a throwaway application doc."""
        import real_accounts as ra
        from motor.motor_asyncio import AsyncIOMotorClient

        async def scenario():
            adb = AsyncIOMotorClient("mongodb://localhost:27017").my_funding_bank
            old_db, ra._db = ra._db, adb
            uid = f"utest_{uuid.uuid4().hex[:8]}"
            app_id = f"rapp_test_{uuid.uuid4().hex[:8]}"
            doc = {"application_id": app_id, "user_id": uid,
                   "email": "state@test.mfb", "full_name": "S T",
                   "account_type": "standard", "status": "PENDING"}
            await adb.real_trading_accounts.insert_one(dict(doc))

            async def fake(**kw):
                return result
            orig = ra.mt5_service.create_real_account
            ra.mt5_service.create_real_account = fake
            try:
                out = await ra._provision(doc)
            finally:
                ra.mt5_service.create_real_account = orig
                ra._db = old_db
            audits = [a async for a in adb.real_account_audit.find({"application_id": app_id})]
            await adb.real_trading_accounts.delete_many({"application_id": app_id})
            await adb.real_account_audit.delete_many({"application_id": app_id})
            return out, audits

        return _run(scenario())

    def test_4_successful_provisioning_sets_active(self):
        out, audits = self._fake_provision(
            {"success": True, "mt5_account_number": "20260001"})
        assert out["status"] == "ACTIVE"
        assert out["mt5_account_number"] == "20260001"
        assert out["provisioned_at"] is not None
        assert any(a["action"] == "REAL_ACCOUNT_CREATED" for a in audits)

    def test_5_mt5_failure_sets_failed(self):
        out, audits = self._fake_provision(
            {"success": False, "error_code": "MT5_CREATE_REJECTED", "message": "rejected"})
        assert out["status"] == "FAILED"
        assert out["error_code"] == "MT5_CREATE_REJECTED"
        assert out.get("mt5_account_number") is None
        assert any(a["action"] == "REAL_ACCOUNT_PROVISIONING_FAILED" for a in audits)

    def test_6_mt5_timeout_sets_failed(self):
        out, _ = self._fake_provision(
            {"success": False, "error_code": "MT5_TIMEOUT", "message": "timed out"})
        assert out["status"] == "FAILED" and out["error_code"] == "MT5_TIMEOUT"

    def test_7_pending_recorded_in_audit(self):
        _, audits = self._fake_provision({"success": True, "mt5_account_number": "1"})
        started = [a for a in audits if a["action"] == "REAL_ACCOUNT_PROVISIONING_STARTED"]
        assert started and started[0]["status"] == "PENDING"

    def test_8_9_states_via_api(self, user):
        r = requests.get(f"{API}/real-account/status", headers=user["h"], timeout=20)
        assert r.json()["status"] in ("FAILED", "ACTIVE", "PENDING", "SUSPENDED")

    def test_service_unavailable_is_honest(self):
        import real_accounts as ra
        svc = ra.MT5AccountService()
        assert svc.available is False  # no MT5 env credentials here
        out = _run(svc.create_real_account(email="a@b.c", name="x",
                                           cfg=ra.REAL_ACCOUNT_DEFAULTS))
        assert out["success"] is False and out["error_code"] == "MT5_UNAVAILABLE"


# ------------------------------------------------------------------ 10-12
class TestAdmin:
    def test_10_admin_can_view_accounts(self, user, admin_h):
        r = requests.get(f"{API}/admin/real-accounts", headers=admin_h, timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert any(a["application_id"] == TestApplication.app_id for a in j["accounts"])
        r2 = requests.get(f"{API}/admin/real-accounts?status=FAILED", headers=admin_h, timeout=20)
        assert all(a["status"] == "FAILED" for a in r2.json()["accounts"])
        r3 = requests.get(f"{API}/admin/real-accounts/{TestApplication.app_id}",
                          headers=admin_h, timeout=20)
        assert r3.status_code == 200 and len(r3.json()["history"]) >= 2

    def test_11_admin_retry_failed(self, user, admin_h):
        r = requests.post(f"{API}/admin/real-accounts/{TestApplication.app_id}/retry",
                          headers=admin_h, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "FAILED"  # MT5 still unavailable — honest
        hist = requests.get(f"{API}/admin/real-accounts/{TestApplication.app_id}",
                            headers=admin_h, timeout=20).json()["history"]
        assert any(h["action"] == "REAL_ACCOUNT_PROVISIONING_RETRIED" for h in hist)

    def test_12_admin_suspend_reactivate(self, user, admin_h):
        DB.real_trading_accounts.update_one(
            {"application_id": TestApplication.app_id},
            {"$set": {"status": "ACTIVE", "mt5_account_number": "777002"}})
        r = requests.post(f"{API}/admin/real-accounts/{TestApplication.app_id}/suspend",
                          headers=admin_h, timeout=20)
        assert r.status_code == 200 and r.json()["status"] == "SUSPENDED"
        r = requests.post(f"{API}/admin/real-accounts/{TestApplication.app_id}/activate",
                          headers=admin_h, timeout=20)
        assert r.status_code == 200 and r.json()["status"] == "ACTIVE"
        DB.real_trading_accounts.update_one(
            {"application_id": TestApplication.app_id},
            {"$set": {"status": "FAILED", "mt5_account_number": None}})


# ------------------------------------------------------------------ 13-15
class TestDemoIsolation:
    def test_13_14_15_demo_untouched(self, user):
        uid = user["user_id"]
        snap = {
            "wallet": DB.forex_wallets.find_one({"user_id": uid}, {"_id": 0}),
            "orders": DB.forex_orders.count_documents({"user_id": uid}),
            "positions": DB.forex_orders.count_documents({"user_id": uid, "status": "open"}),
        }
        requests.post(f"{API}/real-account/retry", headers=user["h"], timeout=30)
        after = {
            "wallet": DB.forex_wallets.find_one({"user_id": uid}, {"_id": 0}),
            "orders": DB.forex_orders.count_documents({"user_id": uid}),
            "positions": DB.forex_orders.count_documents({"user_id": uid, "status": "open"}),
        }
        assert snap == after, "demo wallet/trades/positions must be untouched"


# ------------------------------------------------------------------ 16-18
class TestSecurity:
    SECRET_MARKERS = ("MT5_MANAGER_PASSWORD", "manager_password", "api_secret",
                      "JWT_SECRET", "password")

    def test_16_no_secrets_in_api_responses(self, user, admin_h):
        bodies = [
            requests.get(f"{API}/real-account", headers=user["h"], timeout=20).text,
            requests.get(f"{API}/admin/real-accounts", headers=admin_h, timeout=20).text,
            requests.get(f"{API}/admin/real-accounts/{TestApplication.app_id}",
                         headers=admin_h, timeout=20).text,
            requests.get(f"{API}/admin/real-accounts-config", headers=admin_h, timeout=20).text,
        ]
        for b in bodies:
            low = b.lower()
            for m in self.SECRET_MARKERS:
                assert m.lower() not in low, f"secret marker '{m}' leaked in response"

    def test_17_no_secrets_in_audit_or_logs(self):
        for a in DB.real_account_audit.find().limit(200):
            s = str(a).lower()
            assert "password" not in s and "secret" not in s
        try:
            log = open("/var/log/supervisor/backend.err.log").read()[-100000:]
            assert "MT5_MANAGER_PASSWORD=" not in log
        except FileNotFoundError:
            pass

    def test_18_cross_user_isolation(self, user):
        email2 = f"ra_other_{uuid.uuid4().hex[:8]}@test.mfb"
        r = requests.post(f"{API}/auth/signup", json={
            "full_name": "Other User", "email": email2,
            "mobile": f"8{int(time.time()) % 1000000000:09d}", "password": "Test@1234",
        }, timeout=20)
        d = r.json()
        tok2 = d.get("access_token") or d.get("token")
        uid2 = (d.get("user") or {}).get("user_id") or d.get("user_id")
        try:
            r2 = requests.get(f"{API}/real-account", headers={"Authorization": f"Bearer {tok2}"}, timeout=20)
            assert r2.json()["status"] == "NOT_CREATED"      # cannot see user A's account
            assert requests.get(f"{API}/real-account", timeout=20).status_code == 401
            assert requests.get(f"{API}/admin/real-accounts",
                                headers={"Authorization": f"Bearer {tok2}"}, timeout=20).status_code in (401, 403)
        finally:
            DB.users.delete_one({"user_id": uid2})
