"""Investment Calculator — backend API tests.
Covers public GET /calculator/config, admin GET/PUT /admin/calculator/config,
validation errors, and persistence via re-fetch.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wealth-growth-mobile.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mfb.in"
ADMIN_PASS = "Admin@MFB2026"


# ---------- helpers / fixtures ----------
@pytest.fixture(scope="module")
def admin_token():
    s = requests.Session()
    r = s.post(f"{API}/admin/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=20)
    if r.status_code != 200:
        # try alternate login path
        r = s.post(f"{API}/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=20)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    body = r.json()
    token = body.get("token") or body.get("access_token") or body.get("admin_token")
    assert token, f"No token in admin login response: {body}"
    return token


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def original_cfg(admin_headers):
    r = requests.get(f"{API}/admin/calculator/config", headers=admin_headers, timeout=20)
    assert r.status_code == 200
    return r.json()


# ---------- public endpoint ----------
class TestPublicCalculatorConfig:
    def test_public_get_no_auth(self):
        r = requests.get(f"{API}/calculator/config", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # core shape
        assert "enabled" in data and isinstance(data["enabled"], bool)
        assert "min_amount" in data
        assert "max_amount" in data
        assert "types" in data and isinstance(data["types"], dict)
        for k in ("onetime", "sip", "daily", "compound"):
            assert k in data["types"], f"missing type {k}"
            t = data["types"][k]
            for fld in ("enabled", "return_min", "return_max", "return_default"):
                assert fld in t, f"{k} missing {fld}"
        # public payload must not leak admin metadata
        assert "updated_by" not in data
        assert "updated_at" not in data


# ---------- admin endpoints ----------
class TestAdminCalculatorConfig:
    def test_admin_get_requires_auth(self):
        r = requests.get(f"{API}/admin/calculator/config", timeout=20)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_admin_get_with_auth(self, admin_headers):
        r = requests.get(f"{API}/admin/calculator/config", headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "types" in data
        assert set(data["types"].keys()) >= {"onetime", "sip", "daily", "compound"}

    def test_put_persists_changes(self, admin_headers, original_cfg):
        payload = {
            "min_amount": 200,
            "max_amount": original_cfg.get("max_amount", 1000000),
            "types": {
                "onetime": {
                    **original_cfg["types"]["onetime"],
                    "return_default": 15,
                },
                "daily": {
                    **original_cfg["types"]["daily"],
                    "enabled": False,
                },
            },
        }
        r = requests.put(f"{API}/admin/calculator/config", headers=admin_headers, json=payload, timeout=20)
        assert r.status_code == 200, r.text

        # Re-fetch and validate persistence
        r2 = requests.get(f"{API}/admin/calculator/config", headers=admin_headers, timeout=20)
        assert r2.status_code == 200
        cfg = r2.json()
        assert cfg["min_amount"] == 200
        assert cfg["types"]["onetime"]["return_default"] == 15
        assert cfg["types"]["daily"]["enabled"] is False

        # Public endpoint should also reflect changes
        r3 = requests.get(f"{API}/calculator/config", timeout=20)
        assert r3.status_code == 200
        pub = r3.json()
        assert pub["min_amount"] == 200
        assert pub["types"]["daily"]["enabled"] is False

    def test_validation_min_ge_max(self, admin_headers):
        payload = {"min_amount": 5000, "max_amount": 1000}
        r = requests.put(f"{API}/admin/calculator/config", headers=admin_headers, json=payload, timeout=20)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"

    def test_validation_return_min_ge_max(self, admin_headers, original_cfg):
        payload = {
            "types": {
                "sip": {
                    **original_cfg["types"]["sip"],
                    "return_min": 50,
                    "return_max": 10,
                }
            }
        }
        r = requests.put(f"{API}/admin/calculator/config", headers=admin_headers, json=payload, timeout=20)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"

    def test_restore_original_cfg(self, admin_headers, original_cfg):
        # Cleanup: restore to original values (keeps env tidy for next iteration)
        payload = {
            "enabled": original_cfg.get("enabled", True),
            "min_amount": original_cfg.get("min_amount", 100),
            "max_amount": original_cfg.get("max_amount", 1000000),
            "types": {k: v for k, v in original_cfg["types"].items()},
        }
        r = requests.put(f"{API}/admin/calculator/config", headers=admin_headers, json=payload, timeout=20)
        assert r.status_code == 200, r.text
        # verify
        r2 = requests.get(f"{API}/admin/calculator/config", headers=admin_headers, timeout=20)
        cfg = r2.json()
        assert cfg["min_amount"] == original_cfg["min_amount"]
        assert cfg["types"]["daily"]["enabled"] == original_cfg["types"]["daily"]["enabled"]
