"""Tests for the new centralized API Management + Demo Mode system."""
import os
import requests
import pytest

from conftest import API


# ---------- Public api-status endpoint (no auth) ----------
class TestPublicApiStatus:
    def test_public_status_no_auth_required(self, session):
        r = session.get(f"{API}/app/api-status")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("any_demo", "demo_count", "live_count", "items"):
            assert k in d, f"missing key {k}"
        assert isinstance(d["items"], list) and len(d["items"]) >= 11
        valid_statuses = {"live", "demo", "disabled"}
        for it in d["items"]:
            for k in ("api_name", "display_name", "category", "status"):
                assert k in it
            assert it["status"] in valid_statuses
            # Never expose key in public endpoint
            assert "api_key" not in it
            assert "api_key_masked" not in it

    def test_alpha_vantage_is_live_from_env(self, session):
        r = session.get(f"{API}/app/api-status")
        items = r.json()["items"]
        sm = next((i for i in items if i["api_name"] == "stock_market"), None)
        assert sm is not None
        assert sm["status"] == "live", f"stock_market should be live (env key set), got {sm['status']}"

    def test_stripe_is_demo(self, session):
        r = session.get(f"{API}/app/api-status")
        items = r.json()["items"]
        st = next((i for i in items if i["api_name"] == "payment_gateway_stripe"), None)
        assert st is not None
        assert st["status"] == "demo"

    def test_any_demo_true(self, session):
        d = session.get(f"{API}/app/api-status").json()
        assert d["any_demo"] is True
        assert d["demo_count"] >= 1


# ---------- Admin login ----------
@pytest.fixture(scope="module")
def admin_token(session):
    r = session.post(f"{API}/admin/login", json={"email": "admin@mfb.in", "password": "Admin@MFB2026"})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data
    assert data["admin"]["role"] == "super_admin"
    return data["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestAdminLogin:
    def test_admin_login_returns_token(self, session):
        r = session.post(f"{API}/admin/login", json={"email": "admin@mfb.in", "password": "Admin@MFB2026"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "token" in d
        assert d["admin"]["email"] == "admin@mfb.in"
        assert d["admin"]["role"] == "super_admin"
        assert "_id" not in d["admin"]
        assert "password" not in d["admin"]

    def test_admin_login_invalid(self, session):
        r = session.post(f"{API}/admin/login", json={"email": "admin@mfb.in", "password": "wrong"})
        assert r.status_code == 401


# ---------- Admin api-settings list ----------
class TestAdminApiSettingsList:
    def test_requires_auth(self, session):
        r = session.get(f"{API}/admin/api-settings")
        assert r.status_code == 401

    def test_list_returns_catalog(self, session, admin_headers):
        r = session.get(f"{API}/admin/api-settings", headers=admin_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("items", "total", "demo_count", "live_count", "disabled_count"):
            assert k in d
        assert d["total"] >= 11
        assert len(d["items"]) >= 11
        names = {i["api_name"] for i in d["items"]}
        for required in [
            "payment_gateway_stripe", "payment_gateway_razorpay", "sms_provider",
            "email_service", "stock_market", "mutual_fund", "gold_price",
            "flight_booking", "hotel_booking", "push_notifications", "kyc_verification",
        ]:
            assert required in names, f"missing catalog entry: {required}"

        for it in d["items"]:
            for k in ("api_name", "display_name", "category", "description", "fields",
                      "test_kind", "has_key", "api_key_masked", "extra", "is_enabled",
                      "force_demo", "status"):
                assert k in it, f"missing {k} in {it['api_name']}"
            assert "api_key" not in it, "raw api_key must NOT leak in masked response"
            assert it["status"] in {"live", "demo", "disabled"}

    def test_alpha_vantage_key_is_masked(self, session, admin_headers):
        r = session.get(f"{API}/admin/api-settings", headers=admin_headers)
        items = r.json()["items"]
        sm = next(i for i in items if i["api_name"] == "stock_market")
        assert sm["has_key"] is True
        assert sm["status"] == "live"
        # Masked: first 4 + bullets + last 4 (key length >=8)
        m = sm["api_key_masked"]
        assert len(m) >= 8
        assert "•" in m


# ---------- Admin update (PUT) ----------
class TestAdminApiSettingsUpdate:
    def test_update_sms_provider_set_key_flips_live(self, session, admin_headers):
        r = session.put(f"{API}/admin/api-settings/sms_provider", headers=admin_headers,
                        json={"api_key": "TEST_msg91_key_abcdef1234", "extra": {"sender_id": "MFBTST"}, "is_enabled": True, "force_demo": False})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "live"
        assert d["has_key"] is True
        assert d["extra"]["sender_id"] == "MFBTST"
        assert d["api_key_masked"].startswith("TEST")
        assert d["api_key_masked"].endswith("1234")
        # verify with GET (persistence)
        all_r = session.get(f"{API}/admin/api-settings", headers=admin_headers).json()
        sms = next(i for i in all_r["items"] if i["api_name"] == "sms_provider")
        assert sms["status"] == "live"

    def test_update_razorpay_force_demo_flips_demo(self, session, admin_headers):
        r = session.put(f"{API}/admin/api-settings/payment_gateway_razorpay", headers=admin_headers,
                        json={"api_key": "rzp_live_abcdefghij1234", "extra": {"key_secret": "sec_xyz"}, "force_demo": True})
        assert r.status_code == 200
        assert r.json()["status"] == "demo"

    def test_update_stock_market_disable_flips_disabled(self, session, admin_headers):
        # First save current state to restore
        before = session.get(f"{API}/admin/api-settings", headers=admin_headers).json()
        sm_before = next(i for i in before["items"] if i["api_name"] == "stock_market")

        r = session.put(f"{API}/admin/api-settings/stock_market", headers=admin_headers,
                        json={"is_enabled": False})
        assert r.status_code == 200
        assert r.json()["status"] == "disabled"

        # Public endpoint must also show disabled
        pub = session.get(f"{API}/app/api-status").json()
        sm_pub = next(i for i in pub["items"] if i["api_name"] == "stock_market")
        assert sm_pub["status"] == "disabled"

        # Restore
        session.put(f"{API}/admin/api-settings/stock_market", headers=admin_headers,
                    json={"is_enabled": True, "force_demo": False})

    def test_update_unknown_api_returns_404(self, session, admin_headers):
        r = session.put(f"{API}/admin/api-settings/totally_fake_api_xyz", headers=admin_headers,
                        json={"api_key": "x"})
        assert r.status_code == 404

    def test_clear_key_flips_back_to_demo(self, session, admin_headers):
        # Clear the sms_provider key we set earlier
        r = session.put(f"{API}/admin/api-settings/sms_provider", headers=admin_headers,
                        json={"api_key": "", "force_demo": False, "is_enabled": True})
        assert r.status_code == 200
        assert r.json()["status"] == "demo"
        assert r.json()["has_key"] is False


# ---------- Admin test-connection ----------
class TestAdminTestConnection:
    def test_stripe_fake_key_returns_ok_false_demo(self, session, admin_headers):
        # Set a fake stripe key
        session.put(f"{API}/admin/api-settings/payment_gateway_stripe", headers=admin_headers,
                    json={"api_key": "sk_test_fakekey_thisIsNotReal12345", "force_demo": False, "is_enabled": True})
        r = session.post(f"{API}/admin/api-settings/payment_gateway_stripe/test", headers=admin_headers)
        assert r.status_code == 200, r.text  # NEVER 500/4xx
        d = r.json()
        assert "ok" in d and "mode" in d and "message" in d
        assert d["ok"] is False
        assert d["mode"] == "demo"
        # restore - clear stripe key so wallet topup demo flow still works
        session.put(f"{API}/admin/api-settings/payment_gateway_stripe", headers=admin_headers,
                    json={"api_key": "", "force_demo": False, "is_enabled": True})

    def test_alpha_vantage_live_key_returns_ok(self, session, admin_headers):
        r = session.post(f"{API}/admin/api-settings/stock_market/test", headers=admin_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        # Could be true (live) or false (rate-limited) but should never raise
        assert "ok" in d and "mode" in d and "message" in d
        # Accept either ok:true mode:live OR rate-limit demo
        if d["ok"]:
            assert d["mode"] == "live"

    def test_test_unconfigured_returns_demo(self, session, admin_headers):
        # gold_price has no key
        session.put(f"{API}/admin/api-settings/gold_price", headers=admin_headers,
                    json={"api_key": "", "force_demo": False, "is_enabled": True})
        r = session.post(f"{API}/admin/api-settings/gold_price/test", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is False
        assert d["mode"] == "demo"


# ---------- Stripe top-up resilience in demo mode ----------
@pytest.fixture(scope="module")
def demo_user_headers(session):
    r = session.post(f"{API}/auth/login", json={"identifier": "demo@mfb.in", "password": "demo1234"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}


class TestStripeDemoFallback:
    def test_topup_create_session_demo(self, session, demo_user_headers, admin_headers):
        # ensure stripe is in demo
        session.put(f"{API}/admin/api-settings/payment_gateway_stripe", headers=admin_headers,
                    json={"api_key": "", "force_demo": False, "is_enabled": True})
        r = session.post(f"{API}/wallet/topup/create-session", headers=demo_user_headers,
                         json={"amount": 100.0, "platform": "mobile"})
        assert r.status_code == 200, f"demo top-up create should succeed, got {r.status_code}: {r.text}"
        d = r.json()
        # Expect a demo flag and mfb://demo-pay URL
        assert d.get("demo") is True or "demo" in (d.get("checkout_url", "")).lower(), f"missing demo indicator: {d}"
        url = d.get("checkout_url") or d.get("url") or ""
        assert "demo-pay" in url or url.startswith("mfb://"), f"expected demo URL, got {url}"
        assert "session_id" in d
        pytest.demo_session_id = d["session_id"]

    def test_topup_status_credits_wallet(self, session, demo_user_headers):
        sid = getattr(pytest, "demo_session_id", None)
        if not sid:
            pytest.skip("no demo session_id from previous test")
        before = session.get(f"{API}/wallet", headers=demo_user_headers).json()["balance"]
        r = session.get(f"{API}/wallet/topup/status/{sid}", headers=demo_user_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("payment_status") in ("paid", "complete", "succeeded", "success") or d.get("status") in ("paid", "complete", "succeeded", "success", "completed"), f"unexpected status payload: {d}"
        after = session.get(f"{API}/wallet", headers=demo_user_headers).json()["balance"]
        assert after >= before + 99.0, f"wallet not credited: before={before} after={after}"


# ---------- Existing endpoints still work ----------
class TestExistingEndpointsUnaffected:
    def test_invest_stocks_still_works(self, session):
        r = session.get(f"{API}/invest/stocks")
        assert r.status_code == 200
        assert isinstance(r.json(), list) and len(r.json()) > 0

    def test_auth_login_still_works(self, session):
        r = session.post(f"{API}/auth/login", json={"identifier": "demo@mfb.in", "password": "demo1234"})
        assert r.status_code == 200

    def test_notifications_endpoint(self, session, demo_user_headers):
        r = session.get(f"{API}/notifications", headers=demo_user_headers)
        assert r.status_code == 200

    def test_app_banners_endpoint(self, session):
        r = session.get(f"{API}/app/banners")
        assert r.status_code == 200

    def test_admin_dashboard_stats(self, session, admin_headers):
        r = session.get(f"{API}/admin/dashboard/stats", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        for k in ("users", "wallet", "investments", "bookings", "charts"):
            assert k in d
