"""Push notifications + notification preferences — Iteration 5 release-readiness tests.

Covers:
- POST /api/register-push (demo mode — should NEVER 500)
- GET  /api/notifications/preferences (auth, defaults)
- PUT  /api/notifications/preferences (persists)
- GET  /api/admin/push-status (demo state)
- POST /api/admin/notifications/send (still works in push-demo mode)
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wealth-growth-mobile.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="session")
def demo_token(s):
    r = s.post(f"{API}/auth/login", json={"identifier": "demo@mfb.in", "password": "demo1234"})
    if r.status_code != 200:
        pytest.skip(f"Demo login failed: {r.status_code} {r.text}")
    return r.json()["token"]


@pytest.fixture(scope="session")
def demo_headers(demo_token):
    return {"Authorization": f"Bearer {demo_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def admin_token(s):
    r = s.post(f"{API}/admin/login", json={"email": "admin@mfb.in", "password": "Admin@MFB2026"})
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text}")
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def demo_user_id(s, demo_headers):
    for path in ("/auth/me", "/users/me"):
        r = s.get(f"{API}{path}", headers=demo_headers)
        if r.status_code == 200:
            d = r.json()
            uid = d.get("user_id") or d.get("id") or d.get("user", {}).get("user_id")
            if uid:
                return uid
    return None


# ============================================================
# Push token registration
# ============================================================
class TestRegisterPush:
    def test_register_push_demo_mode(self, s, demo_user_id):
        if not demo_user_id:
            pytest.skip("Demo user_id not resolvable")
        body = {
            "user_id": demo_user_id,
            "platform": "android",
            "device_token": f"TEST_dt_{uuid.uuid4().hex[:12]}",
        }
        r = s.post(f"{API}/register-push", json=body)
        assert r.status_code == 201, f"expected 201, got {r.status_code}: {r.text}"
        d = r.json()
        assert d.get("status") == "stored_demo", d
        assert d.get("push_enabled") is False, d

    def test_register_push_never_500(self, s):
        """Even with weird/empty input, MUST not be 500 — push endpoint must be demo-safe."""
        body = {
            "user_id": f"TEST_ghost_{uuid.uuid4().hex[:8]}",
            "platform": "ios",
            "device_token": f"TEST_dt_{uuid.uuid4().hex[:12]}",
        }
        r = s.post(f"{API}/register-push", json=body)
        assert r.status_code < 500, f"push endpoint should never 500: got {r.status_code} {r.text}"
        assert r.status_code == 201

    def test_register_push_upsert_idempotent(self, s, demo_user_id):
        if not demo_user_id:
            pytest.skip("Demo user_id not resolvable")
        token = f"TEST_dt_{uuid.uuid4().hex[:12]}"
        body = {"user_id": demo_user_id, "platform": "android", "device_token": token}
        r1 = s.post(f"{API}/register-push", json=body)
        r2 = s.post(f"{API}/register-push", json=body)
        assert r1.status_code == 201 and r2.status_code == 201


# ============================================================
# Notification preferences (auth)
# ============================================================
class TestNotificationPreferences:
    def test_get_defaults(self, s, demo_headers):
        r = s.get(f"{API}/notifications/preferences", headers=demo_headers)
        assert r.status_code == 200
        d = r.json()
        for k in ("transactions", "rewards", "promotional", "security", "push_enabled"):
            assert k in d, f"missing key {k}: {d}"
        assert d["push_enabled"] is False, "EMERGENT_PUSH_KEY is placeholder — should be False"

    def test_put_promotional_off_then_persist(self, s, demo_headers):
        # set promotional False
        r = s.put(
            f"{API}/notifications/preferences",
            headers=demo_headers,
            json={"transactions": True, "rewards": True, "promotional": False, "security": True},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("success") is True
        assert d.get("promotional") is False

        # GET back
        r2 = s.get(f"{API}/notifications/preferences", headers=demo_headers)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["promotional"] is False, "promotional did not persist"
        assert d2["transactions"] is True
        assert d2["rewards"] is True
        assert d2["security"] is True

        # Restore (cleanup)
        s.put(
            f"{API}/notifications/preferences",
            headers=demo_headers,
            json={"transactions": True, "rewards": True, "promotional": True, "security": True},
        )

    def test_get_requires_auth(self, s):
        r = s.get(f"{API}/notifications/preferences")
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


# ============================================================
# Admin push-status
# ============================================================
class TestAdminPushStatus:
    def test_push_status_demo(self, s):
        r = s.get(f"{API}/admin/push-status")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("configured") is False
        assert d.get("status") == "demo"
        assert "registered_devices" in d and d["registered_devices"] >= 0
        assert "FCM Not Configured" in d.get("message", ""), d


# ============================================================
# Admin broadcast — must still succeed in demo push mode
# ============================================================
class TestAdminBroadcast:
    def test_broadcast_all_succeeds(self, s, admin_headers):
        r = s.post(
            f"{API}/admin/notifications/send",
            headers=admin_headers,
            json={"title": "TEST_iter5 broadcast", "body": "regression test", "target": "all"},
        )
        assert r.status_code == 200, f"broadcast failed: {r.text}"
        d = r.json()
        assert d.get("success") is True
        assert "batch_id" in d
        assert d.get("recipients", 0) >= 1


# ============================================================
# REGRESSION quick smoke — make sure earlier endpoints still up
# ============================================================
class TestRegressionSmoke:
    def test_login(self, s):
        r = s.post(f"{API}/auth/login", json={"identifier": "demo@mfb.in", "password": "demo1234"})
        assert r.status_code == 200

    def test_wallet(self, s, demo_headers):
        r = s.get(f"{API}/wallet", headers=demo_headers)
        assert r.status_code == 200

    def test_ai_suggestions(self, s, demo_headers):
        r = s.get(f"{API}/invest/ai-suggestions", headers=demo_headers)
        assert r.status_code == 200

    def test_travel_buses(self, s):
        r = s.get(f"{API}/travel/buses")
        assert r.status_code == 200

    def test_travel_trains(self, s):
        r = s.get(f"{API}/travel/trains")
        assert r.status_code == 200

    def test_insurance_quote(self, s):
        r = s.post(f"{API}/insurance/quote", json={"plan_type": "health", "age": 35, "cover": 500000})
        assert r.status_code == 200

    def test_rewards_tier(self, s, demo_headers):
        r = s.get(f"{API}/rewards/tier", headers=demo_headers)
        assert r.status_code == 200
