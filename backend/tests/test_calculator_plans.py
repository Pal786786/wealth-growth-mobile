"""Investment Calculator — Saved Plans CRUD tests (Phase 2).
Covers POST/GET/PUT/DELETE /api/calculator/plans with auth, validation,
ownership isolation, and persistence verification.
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wealth-growth-mobile.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "demo@mfb.in"
DEMO_PASS = "demo1234"


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{API}/auth/login", json={"identifier": DEMO_EMAIL, "password": DEMO_PASS}, timeout=20)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text}"
    body = r.json()
    tok = body.get("token") or body.get("access_token")
    assert tok, f"no token in login response: {body}"
    return tok


@pytest.fixture(scope="module")
def headers(demo_token):
    return {"Authorization": f"Bearer {demo_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def cleanup_plans(headers):
    """Track created plans for cleanup."""
    created: list[str] = []
    yield created
    for pid in created:
        try:
            requests.delete(f"{API}/calculator/plans/{pid}", headers=headers, timeout=10)
        except Exception:
            pass


def _valid_payload(name="TEST_Plan"):
    return {
        "name": name,
        "calc_type": "onetime",
        "amount": 10000,
        "duration": 12,
        "rate_pct": 12,
        "reinvest": False,
        "invested": 10000,
        "profit": 1200,
        "maturity": 11200,
        "growth": 12.0,
    }


# ---------------- auth ----------------
class TestAuthRequired:
    def test_post_requires_auth(self):
        r = requests.post(f"{API}/calculator/plans", json=_valid_payload(), timeout=20)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_get_list_requires_auth(self):
        r = requests.get(f"{API}/calculator/plans", timeout=20)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_get_single_requires_auth(self):
        r = requests.get(f"{API}/calculator/plans/{uuid.uuid4()}", timeout=20)
        assert r.status_code in (401, 403)

    def test_put_requires_auth(self):
        r = requests.put(f"{API}/calculator/plans/{uuid.uuid4()}", json={"name": "x"}, timeout=20)
        assert r.status_code in (401, 403)

    def test_delete_requires_auth(self):
        r = requests.delete(f"{API}/calculator/plans/{uuid.uuid4()}", timeout=20)
        assert r.status_code in (401, 403)


# ---------------- create ----------------
class TestCreatePlan:
    def test_create_success_returns_plan(self, headers, cleanup_plans):
        payload = _valid_payload("TEST_SIPGoal_Create")
        r = requests.post(f"{API}/calculator/plans", json=payload, headers=headers, timeout=20)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert "plan_id" in data and data["plan_id"]
        cleanup_plans.append(data["plan_id"])
        assert "_id" not in data, "MongoDB _id leaked into response"
        assert data["name"] == payload["name"]
        assert data["calc_type"] == "onetime"
        assert data["amount"] == 10000
        assert data["invested"] == 10000
        assert data["maturity"] == 11200
        assert "created_at" in data
        # created_at must be string (ISO), not raw datetime
        assert isinstance(data["created_at"], str)

    def test_create_invalid_calc_type(self, headers):
        p = _valid_payload("TEST_BadType")
        p["calc_type"] = "garbage"
        r = requests.post(f"{API}/calculator/plans", json=p, headers=headers, timeout=20)
        assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text}"

    def test_create_amount_zero(self, headers):
        p = _valid_payload("TEST_Zero")
        p["amount"] = 0
        r = requests.post(f"{API}/calculator/plans", json=p, headers=headers, timeout=20)
        assert r.status_code == 422, f"expected 422, got {r.status_code}"

    def test_create_amount_negative(self, headers):
        p = _valid_payload("TEST_Neg")
        p["amount"] = -100
        r = requests.post(f"{API}/calculator/plans", json=p, headers=headers, timeout=20)
        assert r.status_code == 422, f"expected 422, got {r.status_code}"

    def test_create_duration_zero(self, headers):
        p = _valid_payload("TEST_DurZero")
        p["duration"] = 0
        r = requests.post(f"{API}/calculator/plans", json=p, headers=headers, timeout=20)
        assert r.status_code == 422

    def test_create_persists_via_get(self, headers, cleanup_plans):
        payload = _valid_payload("TEST_Persist")
        r = requests.post(f"{API}/calculator/plans", json=payload, headers=headers, timeout=20)
        assert r.status_code in (200, 201)
        pid = r.json()["plan_id"]
        cleanup_plans.append(pid)
        # GET single
        r2 = requests.get(f"{API}/calculator/plans/{pid}", headers=headers, timeout=20)
        assert r2.status_code == 200
        assert r2.json()["plan_id"] == pid
        assert r2.json()["name"] == "TEST_Persist"


# ---------------- list ----------------
class TestListPlans:
    def test_list_returns_users_plans_sorted_desc(self, headers, cleanup_plans):
        # Create two plans
        p1 = requests.post(f"{API}/calculator/plans", json=_valid_payload("TEST_List_A"), headers=headers, timeout=20).json()
        p2 = requests.post(f"{API}/calculator/plans", json=_valid_payload("TEST_List_B"), headers=headers, timeout=20).json()
        cleanup_plans.extend([p1["plan_id"], p2["plan_id"]])

        r = requests.get(f"{API}/calculator/plans", headers=headers, timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        ids = [p["plan_id"] for p in data]
        assert p1["plan_id"] in ids and p2["plan_id"] in ids
        # Newest first → p2 should appear before p1
        assert ids.index(p2["plan_id"]) < ids.index(p1["plan_id"]), "list not sorted desc by created_at"
        # No _id leakage
        for d in data:
            assert "_id" not in d


# ---------------- get single ----------------
class TestGetPlan:
    def test_get_missing_returns_404(self, headers):
        r = requests.get(f"{API}/calculator/plans/{uuid.uuid4()}", headers=headers, timeout=20)
        assert r.status_code == 404


# ---------------- update ----------------
class TestUpdatePlan:
    def test_update_name(self, headers, cleanup_plans):
        p = requests.post(f"{API}/calculator/plans", json=_valid_payload("TEST_BeforeRename"), headers=headers, timeout=20).json()
        cleanup_plans.append(p["plan_id"])
        r = requests.put(f"{API}/calculator/plans/{p['plan_id']}", json={"name": "TEST_AfterRename"}, headers=headers, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "TEST_AfterRename"
        # Verify via GET
        r2 = requests.get(f"{API}/calculator/plans/{p['plan_id']}", headers=headers, timeout=20)
        assert r2.json()["name"] == "TEST_AfterRename"

    def test_update_notes(self, headers, cleanup_plans):
        p = requests.post(f"{API}/calculator/plans", json=_valid_payload("TEST_NotesPlan"), headers=headers, timeout=20).json()
        cleanup_plans.append(p["plan_id"])
        r = requests.put(f"{API}/calculator/plans/{p['plan_id']}", json={"notes": "remember Q3 2026"}, headers=headers, timeout=20)
        assert r.status_code == 200
        assert r.json()["notes"] == "remember Q3 2026"

    def test_update_empty_payload_returns_400(self, headers, cleanup_plans):
        p = requests.post(f"{API}/calculator/plans", json=_valid_payload("TEST_NoChange"), headers=headers, timeout=20).json()
        cleanup_plans.append(p["plan_id"])
        r = requests.put(f"{API}/calculator/plans/{p['plan_id']}", json={}, headers=headers, timeout=20)
        assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text}"

    def test_update_missing_plan_404(self, headers):
        r = requests.put(f"{API}/calculator/plans/{uuid.uuid4()}", json={"name": "x"}, headers=headers, timeout=20)
        assert r.status_code == 404


# ---------------- delete ----------------
class TestDeletePlan:
    def test_delete_then_re_delete(self, headers):
        p = requests.post(f"{API}/calculator/plans", json=_valid_payload("TEST_ToDelete"), headers=headers, timeout=20).json()
        pid = p["plan_id"]
        r = requests.delete(f"{API}/calculator/plans/{pid}", headers=headers, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        # GET should now 404
        r2 = requests.get(f"{API}/calculator/plans/{pid}", headers=headers, timeout=20)
        assert r2.status_code == 404
        # Re-delete should 404
        r3 = requests.delete(f"{API}/calculator/plans/{pid}", headers=headers, timeout=20)
        assert r3.status_code == 404


# ---------------- isolation (token-less) ----------------
class TestOwnershipIsolation:
    def test_other_request_without_token_cannot_read(self, headers, cleanup_plans):
        p = requests.post(f"{API}/calculator/plans", json=_valid_payload("TEST_Private"), headers=headers, timeout=20).json()
        cleanup_plans.append(p["plan_id"])
        # No auth header
        r = requests.get(f"{API}/calculator/plans/{p['plan_id']}", timeout=20)
        assert r.status_code in (401, 403)

    def test_bad_token_cannot_read(self, cleanup_plans, headers):
        p = requests.post(f"{API}/calculator/plans", json=_valid_payload("TEST_Private2"), headers=headers, timeout=20).json()
        cleanup_plans.append(p["plan_id"])
        bad = {"Authorization": "Bearer not-a-real-token", "Content-Type": "application/json"}
        r = requests.get(f"{API}/calculator/plans/{p['plan_id']}", headers=bad, timeout=20)
        assert r.status_code in (401, 403)
