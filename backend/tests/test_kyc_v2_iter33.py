"""Sprint 9 — KYC v2 backend tests.

Covers all 17 scenarios from the review request against the live public URL.
Uses the shared session/demo_headers fixtures from conftest.py.
"""
from __future__ import annotations

import base64
import os

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL",
                           "https://wealth-growth-mobile.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ---------------- shared helpers ----------------
def _tiny_png(byte_val: int = 0) -> str:
    """Return a small deterministic base64 string (any bytes work in demo mode)."""
    payload = bytes([byte_val, 1, 2, 3, 4, 5, 6, 7, 8, 9]) * 20
    return base64.b64encode(payload).decode()


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/admin/login",
                       json={"email": "admin@mfb.in", "password": "Admin@MFB2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}",
            "Content-Type": "application/json"}


# ---------------- PAN verification ----------------
class TestPanVerify:
    def test_01_pan_happy_path(self, demo_headers):
        r = requests.post(f"{API}/kyc/v2/pan/verify",
                          json={"pan": "ABCDE1234F", "name": "Reyansh Sharma"},
                          headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["result"]["ok"] is True
        assert j["result"]["provider"] == "demo"
        assert j["result"]["status"] == "valid"
        assert j["result"]["name_match"] is True
        assert "official_name" in j["result"]
        assert j["verification"]["kind"] == "pan"

    def test_02_pan_invalid_format(self, demo_headers):
        r = requests.post(f"{API}/kyc/v2/pan/verify",
                          json={"pan": "NOTAPAN99A"},
                          headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["result"]["ok"] is False
        assert j["result"]["status"] == "invalid_format"

    def test_03_pan_bad_prefix_not_found(self, demo_headers):
        r = requests.post(f"{API}/kyc/v2/pan/verify",
                          json={"pan": "BADAB1234F"},
                          headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["result"]["ok"] is False
        assert j["result"]["status"] == "not_found"


# ---------------- Aadhaar soft verify ----------------
class TestAadhaar:
    def test_04_aadhaar_soft_verify(self, demo_headers):
        r = requests.post(f"{API}/kyc/v2/aadhaar/verify",
                          json={"aadhaar_last4": "1234",
                                 "name": "Reyansh Sharma", "dob": "1990-01-01"},
                          headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["result"]["ok"] is True
        assert j["result"]["status"] == "soft_verified"
        assert j["result"]["aadhaar_last4"] == "1234"
        assert "aadhaar_hash" in j["result"]


# ---------------- DigiLocker ----------------
class TestDigiLocker:
    def test_05_digilocker_full_flow(self, demo_headers):
        # start
        r1 = requests.post(f"{API}/kyc/v2/digilocker/start",
                            json={"redirect_uri": "https://example.com/cb"},
                            headers=demo_headers)
        assert r1.status_code == 200, r1.text
        j1 = r1.json()
        assert "authorization_url" in j1 and "state" in j1 and "code" in j1
        state, code = j1["state"], j1["code"]
        # callback
        r2 = requests.post(f"{API}/kyc/v2/digilocker/callback",
                            json={"code": code, "state": state},
                            headers=demo_headers)
        assert r2.status_code == 200, r2.text
        aad = r2.json()["result"]
        assert aad["ok"] is True
        for k in ("aadhaar_last4", "aadhaar_hash", "name", "address"):
            assert k in aad, f"missing {k}"
        assert len(aad["aadhaar_last4"]) == 4

    def test_06a_digilocker_wrong_state(self, demo_headers):
        r = requests.post(f"{API}/kyc/v2/digilocker/callback",
                          json={"code": "dlcode_bogus", "state": "st_wrongxxxx"},
                          headers=demo_headers)
        assert r.status_code == 400, r.text

    def test_06b_digilocker_foreign_state_forbidden(self, demo_headers, admin_headers):
        # Create a state as demo user
        r1 = requests.post(f"{API}/kyc/v2/digilocker/start",
                           json={"redirect_uri": "https://example.com/cb"},
                           headers=demo_headers)
        assert r1.status_code == 200
        state, code = r1.json()["state"], r1.json()["code"]

        # Login a second user (create if missing) and try the callback
        register = requests.post(f"{API}/auth/signup", json={
            "full_name": "KycV2 OtherUser",
            "email": "kyc2other@mfb.in",
            "mobile": "9000000199",
            "password": "Other@1234",
        })
        # register may 200 or 409 — either is fine, we just need to be able to login
        login = requests.post(f"{API}/auth/login",
                              json={"identifier": "kyc2other@mfb.in",
                                    "password": "Other@1234"})
        if login.status_code != 200:
            pytest.skip(f"other user login failed: {login.status_code} {login.text}")
        other_headers = {"Authorization": f"Bearer {login.json()['token']}",
                         "Content-Type": "application/json"}
        r2 = requests.post(f"{API}/kyc/v2/digilocker/callback",
                            json={"code": code, "state": state},
                            headers=other_headers)
        assert r2.status_code == 403, r2.text


# ---------------- OCR ----------------
class TestOCR:
    def test_07a_ocr_pan(self, demo_headers):
        r = requests.post(f"{API}/kyc/v2/ocr",
                          json={"doc_type": "pan", "image_b64": _tiny_png(11)},
                          headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()["result"]
        assert j["ok"] is True
        assert j["doc_type"] == "pan"
        for k in ("pan", "name", "dob"):
            assert k in j["fields"]
        assert 0.0 <= j["confidence"] <= 1.0
        assert "doc_hash" in j

    def test_07b_ocr_aadhaar(self, demo_headers):
        r = requests.post(f"{API}/kyc/v2/ocr",
                          json={"doc_type": "aadhaar", "image_b64": _tiny_png(22)},
                          headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()["result"]
        assert j["ok"] is True
        assert j["doc_type"] == "aadhaar"
        for k in ("aadhaar", "name", "dob"):
            assert k in j["fields"]
        assert 0.0 <= j["confidence"] <= 1.0
        assert "doc_hash" in j


# ---------------- Face Match ----------------
class TestFaceMatch:
    def test_08a_face_match_identical(self, demo_headers):
        img = _tiny_png(50)
        r = requests.post(f"{API}/kyc/v2/face-match",
                          json={"id_photo_b64": img, "selfie_b64": img},
                          headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()["result"]
        assert j["match"] is True
        assert j["score"] == 0.98
        assert "threshold" in j and "provider" in j

    def test_08b_face_match_different(self, demo_headers):
        r = requests.post(f"{API}/kyc/v2/face-match",
                          json={"id_photo_b64": _tiny_png(1),
                                 "selfie_b64": _tiny_png(2)},
                          headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()["result"]
        # Regardless of match outcome, must return required keys
        for k in ("match", "score", "threshold", "provider"):
            assert k in j


# ---------------- Documents ----------------
class TestDocuments:
    def test_09_document_upload_and_hash(self, demo_headers):
        r = requests.post(f"{API}/kyc/v2/documents",
                          json={"doc_type": "pan_card",
                                 "image_b64": _tiny_png(77),
                                 "mime": "image/png"},
                          headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["document_id"].startswith("kd_")
        assert len(j["sha256"]) == 64
        # KYC_ENCRYPTION_KEY is placeholder → encrypted flag must be false
        assert j["encrypted"] is False

    def test_10_document_too_large(self, demo_headers):
        # >8MB raw payload
        big = base64.b64encode(b"A" * (8 * 1024 * 1024 + 10)).decode()
        r = requests.post(f"{API}/kyc/v2/documents",
                          json={"doc_type": "pan_card", "image_b64": big},
                          headers=demo_headers)
        assert r.status_code == 413, f"expected 413, got {r.status_code}: {r.text[:200]}"


# ---------------- Summary / Gates / Compliance ----------------
class TestSummaryAndGate:
    def test_11_summary_shape(self, demo_headers):
        r = requests.get(f"{API}/kyc/v2/summary", headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("status", "pan_verified", "aadhaar_verified",
                   "verifications", "gates", "documents_count",
                   "encryption"):
            assert k in j, f"missing {k}"
        assert isinstance(j["verifications"], list)
        assert isinstance(j["gates"], dict)
        # All 4 gated actions must be present
        for a in ("withdrawal", "become_signal_provider",
                   "become_copy_trader", "compliance_limits"):
            assert a in j["gates"]

    def test_12_gate_gated_action(self, demo_headers):
        r = requests.get(f"{API}/kyc/v2/gate",
                          params={"action": "withdrawal"},
                          headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "required" in j
        assert j["action"] == "withdrawal"
        # Must be boolean; correlation with kyc_status
        st = j.get("kyc_status") or j.get("status")
        if st == "approved":
            assert j["required"] is False
        else:
            assert j["required"] is True

    def test_13_gate_non_gated_action(self, demo_headers):
        r = requests.get(f"{API}/kyc/v2/gate",
                          params={"action": "forex_trade"},
                          headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["required"] is False
        assert j["status"] == "not_gated"

    def test_14_compliance_report(self, demo_headers):
        r = requests.get(f"{API}/kyc/v2/compliance", headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("cumulative_deposit_paise",
                   "over_cumulative_limit", "over_single_txn_limit"):
            assert k in j, f"missing {k}"
        assert isinstance(j["over_cumulative_limit"], bool)
        assert isinstance(j["over_single_txn_limit"], bool)


# ---------------- Admin ----------------
class TestAdmin:
    def test_15_admin_dashboard(self, admin_headers):
        r = requests.get(f"{API}/admin/kyc/v2/dashboard", headers=admin_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("pan_verified", "aadhaar_verified", "face_matched",
                   "documents_stored", "providers", "encryption",
                   "gated_actions", "compliance_limits"):
            assert k in j, f"missing {k}"
        assert isinstance(j["providers"], dict)
        assert "pan" in j["providers"]

    def test_16a_admin_verifications_requires_auth(self):
        r = requests.get(f"{API}/admin/kyc/v2/verifications")
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_16b_admin_verifications_list(self, admin_headers):
        r = requests.get(f"{API}/admin/kyc/v2/verifications",
                          headers=admin_headers, params={"limit": 20})
        assert r.status_code == 200, r.text
        j = r.json()
        assert "items" in j and isinstance(j["items"], list)
        assert "count" in j

    def test_17_admin_providers(self, admin_headers):
        r = requests.get(f"{API}/admin/kyc/v2/providers", headers=admin_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        for prov in ("pan", "digilocker"):
            assert prov in j
            assert "provider" in j[prov]
            assert isinstance(j[prov]["configured"], bool)
            assert isinstance(j[prov]["real_backend"], bool)

    def test_17b_admin_gating_events(self, admin_headers):
        r = requests.get(f"{API}/admin/kyc/v2/gating-events",
                          headers=admin_headers, params={"limit": 20})
        assert r.status_code == 200, r.text
        j = r.json()
        assert "items" in j and isinstance(j["items"], list)
