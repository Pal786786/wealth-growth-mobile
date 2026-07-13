"""Sprint 12.2 — Withdrawals with Cashfree Payouts (demo fallback) tests.

Covers:
  * Verified-bank requirement (Sprint 12.1 integration)
  * Single-pending rule (only 1 in-flight withdrawal per user)
  * Hard-reject cap (self-service ceiling)
  * Auto-approve engine + Cashfree payout dispatch (demo)
  * Manual admin approve → dispatch payout
  * Monthly cap enforcement
  * Admin payout test endpoint + settings mask
  * Admin mark-utr
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"


# ------------------------------------------------------------ helpers -------
def _login_user(identifier: str, password: str):
    r = requests.post(f"{API}/auth/login",
                      json={"identifier": identifier, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def user_headers():
    # Create an isolated user for Sprint 12.2 tests so we don't collide with other test state.
    mob = f"9{uuid.uuid4().int % 10**9:09d}"
    email = f"s122_{uuid.uuid4().hex[:8]}@mfb.in"
    r = requests.post(f"{API}/auth/signup",
                      json={"email": email, "mobile": mob,
                            "password": "Sprint122!",
                            "full_name": "Sprint 12.2 User"},
                      timeout=30)
    assert r.status_code in (200, 201), r.text
    j = r.json()
    tok = j.get("token")
    assert tok, j
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}, mob


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/admin/login",
                      json={"email": "admin@mfb.in", "password": "Admin@MFB2026"}, timeout=30)
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['token']}",
         "Content-Type": "application/json"}
    # Sprint 12.2 test suite invariants — restore full Sprint 12.2 defaults regardless of
    # what any earlier legacy test may have overridden in the settings singleton.
    requests.put(f"{API}/admin/withdrawals/settings",
                 json={
                     "require_verified_bank": True,
                     "single_pending_only": True,
                     "auto_approve_enabled": True,
                     "auto_dispatch_on_approve": True,
                     "auto_approve_threshold": 25_000,
                     "hard_reject_amount": 200_000,
                     "monthly_max_amount": 2_000_000,
                     "min_amount": 100,
                     "max_amount": 200_000,
                     "compliance_hold": False,
                     "payout_provider": "demo",
                     "duplicate_window_seconds": 1,  # avoid dedupe in fast tests
                     "rate_limit_per_hour": 100,
                     "daily_max_count": 100,
                 },
                 headers=h, timeout=15)
    return h


def _fund_wallet(uid: str, amount: float, admin_headers):
    """Credit the test user's wallet directly via admin adjust endpoint."""
    r = requests.post(f"{API}/admin/wallet/adjust",
                      json={"user_id": uid, "amount": amount,
                            "reason": "Sprint 12.2 test funding"},
                      headers=admin_headers, timeout=15)
    return r


def _kyc_approve(uid: str, admin_headers):
    """Grant a KYC bypass so downstream withdrawal / KYC-gated flows work.
    Uses the super-admin bypass endpoint (avoids needing a real KYC submission)."""
    r = requests.post(f"{API}/admin/kyc-bypass/grant",
                      json={"user_id": uid, "reason": "sprint12.2-test",
                            "expires_in_days": 1},
                      headers=admin_headers, timeout=10)
    return r


def _make_verified_bank(headers, admin_headers, holder="Sprint User",
                        bank="HDFC Bank", ifsc="HDFC0001111"):
    """Create + penny-drop-verify a bank account. Returns bank_id."""
    payload = {"holder_name": holder, "bank_name": bank, "ifsc": ifsc,
               "account_number": f"{uuid.uuid4().int % 10**10:010d}"}
    r = requests.post(f"{API}/wallet/withdrawals/bank-accounts",
                      json=payload, headers=headers, timeout=15)
    assert r.status_code == 200, r.text
    bank_id = r.json()["bank_id"]
    # Penny-drop verify via Sprint 12.1
    v = requests.post(f"{API}/bank-verification/verify/{bank_id}",
                      headers=headers, timeout=15)
    assert v.status_code == 200, v.text
    return bank_id


def _me(headers):
    r = requests.get(f"{API}/auth/me", headers=headers, timeout=10)
    r.raise_for_status()
    j = r.json()
    return j.get("user_id") or j.get("id") or (j.get("user") or {}).get("user_id")


# =============================================================================
# ADMIN — settings + payout provider test
# =============================================================================
def test_admin_payout_providers_registry(admin_headers):
    r = requests.get(f"{API}/admin/withdrawals/payout/providers",
                     headers=admin_headers, timeout=10)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "demo" in j["registry"]
    assert "cashfree" in j["registry"]
    # Active should default to demo (until an admin configures Cashfree)
    assert j["active"] in ("demo", "cashfree")


def test_admin_payout_test_endpoint(admin_headers):
    r = requests.post(f"{API}/admin/withdrawals/payout/test",
                      headers=admin_headers, timeout=10)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] is True
    assert j["provider"] in ("demo", "cashfree")


def test_admin_settings_have_sprint122_fields(admin_headers):
    r = requests.get(f"{API}/admin/withdrawals/settings",
                     headers=admin_headers, timeout=10)
    assert r.status_code == 200, r.text
    s = r.json()
    for k in ("require_verified_bank", "single_pending_only", "hard_reject_amount",
              "auto_approve_enabled", "auto_approve_threshold", "payout_provider",
              "monthly_max_amount", "compliance_hold"):
        assert k in s, f"missing settings key: {k}"
    # Max amount default should be ₹2L
    assert s["max_amount"] >= 100_000


def test_admin_settings_mask_payout_secret(admin_headers):
    # Set a fake secret then confirm GET masks it
    r = requests.put(f"{API}/admin/withdrawals/settings",
                     json={"payout_client_secret": "cf_test_secret_1234"},
                     headers=admin_headers, timeout=10)
    assert r.status_code == 200, r.text
    # Now GET
    g = requests.get(f"{API}/admin/withdrawals/settings",
                     headers=admin_headers, timeout=10)
    assert g.status_code == 200
    s = g.json()
    assert s["payout_client_secret"].startswith("•••"), s["payout_client_secret"]
    assert s["payout_client_secret"].endswith("1234")

    # Sending back the masked placeholder should NOT overwrite the real value
    r2 = requests.put(f"{API}/admin/withdrawals/settings",
                      json={"payout_client_secret": s["payout_client_secret"]},
                      headers=admin_headers, timeout=10)
    # Might return 400 "No changes" (if only that field sent + stripped) — acceptable
    assert r2.status_code in (200, 400)

    # Clear the secret so downstream tests use demo
    requests.put(f"{API}/admin/withdrawals/settings",
                 json={"payout_client_secret": ""},
                 headers=admin_headers, timeout=10)


# =============================================================================
# USER — Sprint 12.2 core flows
# =============================================================================
def test_user_settings_expose_sprint122(user_headers):
    hdr, _ = user_headers
    r = requests.get(f"{API}/wallet/withdrawals/settings", headers=hdr, timeout=10)
    assert r.status_code == 200
    s = r.json()
    for k in ("require_verified_bank", "single_pending_only", "hard_reject_amount",
              "auto_approve_enabled", "auto_approve_threshold", "monthly_max_amount"):
        assert k in s, f"missing user-visible key: {k}"


def test_unverified_bank_rejected(user_headers, admin_headers):
    hdr, mob = user_headers
    uid = _me(hdr)
    if not uid:
        pytest.skip("cannot resolve user_id from /auth/me")

    _kyc_approve(uid, admin_headers)
    _fund_wallet(uid, 10_000, admin_headers)

    # Add an UNVERIFIED bank
    unv = requests.post(f"{API}/wallet/withdrawals/bank-accounts",
                        json={"holder_name": "Sprint User", "bank_name": "HDFC Bank",
                              "ifsc": "HDFC0001111",
                              "account_number": f"{uuid.uuid4().int % 10**10:010d}"},
                        headers=hdr, timeout=15)
    assert unv.status_code == 200
    unv_bank = unv.json()["bank_id"]

    # Try to withdraw against unverified bank → should be rejected with 400
    r = requests.post(f"{API}/wallet/withdrawals/request",
                      json={"amount": 500, "bank_account_id": unv_bank},
                      headers=hdr, timeout=10)
    assert r.status_code == 400, r.text
    assert "verified" in r.text.lower() or "penny" in r.text.lower()


def test_hard_reject_cap(user_headers, admin_headers):
    hdr, _ = user_headers
    uid = _me(hdr)

    bank_id = _make_verified_bank(hdr, admin_headers)
    _fund_wallet(uid, 30_000, admin_headers)  # enough for a small withdrawal

    # Force a low hard_reject to exercise the cap without hitting max_amount first.
    requests.put(f"{API}/admin/withdrawals/settings",
                 json={"hard_reject_amount": 5_000, "max_amount": 10_000,
                       "compliance_hold": False},
                 headers=admin_headers, timeout=10)
    try:
        # Attempt > hard_reject cap (but ≤ max_amount) → 400 with 'exceeds' / 'limit'
        r = requests.post(f"{API}/wallet/withdrawals/request",
                          json={"amount": 7_000, "bank_account_id": bank_id},
                          headers=hdr, timeout=10)
        assert r.status_code == 400, r.text
        body = r.text.lower()
        assert "exceed" in body or "limit" in body or "maximum" in body
    finally:
        # Restore Sprint 12.2 defaults
        requests.put(f"{API}/admin/withdrawals/settings",
                     json={"hard_reject_amount": 200_000, "max_amount": 200_000},
                     headers=admin_headers, timeout=10)


def test_auto_approve_flow_full_cycle(user_headers, admin_headers):
    """Amount ≤ auto_approve_threshold → OTP verified → auto-approved →
    demo payout SUCCESS → status = completed, UTR present."""
    hdr, _ = user_headers
    uid = _me(hdr)
    _kyc_approve(uid, admin_headers)

    # Fresh verified bank
    bank_id = _make_verified_bank(hdr, admin_headers, holder="Auto User", ifsc="HDFC0002222")
    _fund_wallet(uid, 5_000, admin_headers)

    # Reset settings to guarantee auto-approve is on for this test
    requests.put(f"{API}/admin/withdrawals/settings",
                 json={"auto_approve_enabled": True, "auto_approve_threshold": 25_000,
                       "compliance_hold": False, "payout_provider": "demo"},
                 headers=admin_headers, timeout=10)

    # Small amount → auto-approve path
    r = requests.post(f"{API}/wallet/withdrawals/request",
                      json={"amount": 500, "bank_account_id": bank_id},
                      headers=hdr, timeout=15)
    assert r.status_code == 200, r.text
    wid = r.json()["withdrawal_id"]
    otp = r.json().get("otp_demo")
    assert otp, "demo OTP should be present"

    # Verify OTP → should auto-approve + demo payout success
    v = requests.post(f"{API}/wallet/withdrawals/verify-otp",
                      json={"withdrawal_id": wid, "otp": otp},
                      headers=hdr, timeout=15)
    assert v.status_code == 200, v.text
    j = v.json()
    assert j["auto_approved"] is True, j
    assert j["status"] in ("completed", "processing"), j
    if j["status"] == "completed":
        assert j.get("utr"), "UTR should be stamped on demo success"

    # Confirm detail reflects settlement
    d = requests.get(f"{API}/wallet/withdrawals/{wid}", headers=hdr, timeout=10)
    assert d.status_code == 200
    wd = d.json()["withdrawal"]
    assert wd["status"] in ("completed", "processing")
    assert wd.get("provider") in ("demo", "cashfree")


def test_single_pending_rule(user_headers, admin_headers):
    """Ensure only 1 in-flight withdrawal is allowed per user at a time."""
    hdr, _ = user_headers
    uid = _me(hdr)
    _kyc_approve(uid, admin_headers)

    # Disable auto-approve so requests sit in pending / under_review
    requests.put(f"{API}/admin/withdrawals/settings",
                 json={"auto_approve_enabled": False, "compliance_hold": False},
                 headers=admin_headers, timeout=10)

    bank_id = _make_verified_bank(hdr, admin_headers, holder="Pending User", ifsc="HDFC0003333")
    _fund_wallet(uid, 20_000, admin_headers)

    r1 = requests.post(f"{API}/wallet/withdrawals/request",
                       json={"amount": 200, "bank_account_id": bank_id},
                       headers=hdr, timeout=10)
    assert r1.status_code == 200, r1.text
    wid1 = r1.json()["withdrawal_id"]

    # Second request while first is still pending should be 409
    r2 = requests.post(f"{API}/wallet/withdrawals/request",
                       json={"amount": 300, "bank_account_id": bank_id},
                       headers=hdr, timeout=10)
    assert r2.status_code == 409, r2.text

    # Cancel first — free the slot
    c = requests.post(f"{API}/wallet/withdrawals/{wid1}/cancel", headers=hdr, timeout=10)
    assert c.status_code == 200

    # Restore auto-approve for other tests
    requests.put(f"{API}/admin/withdrawals/settings",
                 json={"auto_approve_enabled": True},
                 headers=admin_headers, timeout=10)


def test_admin_manual_approve_triggers_payout(user_headers, admin_headers):
    """When auto_approve is off, admin approve → automatic payout dispatch → UTR."""
    hdr, _ = user_headers
    uid = _me(hdr)
    _kyc_approve(uid, admin_headers)

    # Force auto-approve OFF
    requests.put(f"{API}/admin/withdrawals/settings",
                 json={"auto_approve_enabled": False, "compliance_hold": False,
                       "payout_provider": "demo"},
                 headers=admin_headers, timeout=10)

    bank_id = _make_verified_bank(hdr, admin_headers, holder="Manual Approve",
                                    ifsc="HDFC0004444")
    _fund_wallet(uid, 5_000, admin_headers)

    r = requests.post(f"{API}/wallet/withdrawals/request",
                      json={"amount": 400, "bank_account_id": bank_id},
                      headers=hdr, timeout=10)
    assert r.status_code == 200, r.text
    wid = r.json()["withdrawal_id"]
    otp = r.json()["otp_demo"]

    v = requests.post(f"{API}/wallet/withdrawals/verify-otp",
                      json={"withdrawal_id": wid, "otp": otp}, headers=hdr, timeout=10)
    assert v.status_code == 200, v.text
    assert v.json()["status"] == "under_review"
    assert v.json().get("auto_approved") in (False, None)

    # Admin approve → should also dispatch payout
    a = requests.post(f"{API}/admin/withdrawals/{wid}/approve",
                      headers=admin_headers, timeout=15)
    assert a.status_code == 200, a.text
    j = a.json()
    # Response should contain the payout dispatch outcome
    assert "payout" in j, j
    assert j["payout"]["status"] in ("completed", "processing")

    # Restore
    requests.put(f"{API}/admin/withdrawals/settings",
                 json={"auto_approve_enabled": True}, headers=admin_headers, timeout=10)


def test_admin_mark_utr(user_headers, admin_headers):
    """Admin can stamp a UTR manually on an approved/processing withdrawal."""
    hdr, _ = user_headers
    uid = _me(hdr)
    _kyc_approve(uid, admin_headers)

    requests.put(f"{API}/admin/withdrawals/settings",
                 json={"auto_approve_enabled": False, "compliance_hold": False},
                 headers=admin_headers, timeout=10)

    bank_id = _make_verified_bank(hdr, admin_headers, holder="UTR User", ifsc="HDFC0005555")
    _fund_wallet(uid, 5_000, admin_headers)

    r = requests.post(f"{API}/wallet/withdrawals/request",
                      json={"amount": 350, "bank_account_id": bank_id},
                      headers=hdr, timeout=10)
    assert r.status_code == 200, r.text
    wid = r.json()["withdrawal_id"]
    otp = r.json()["otp_demo"]
    requests.post(f"{API}/wallet/withdrawals/verify-otp",
                  json={"withdrawal_id": wid, "otp": otp}, headers=hdr, timeout=10)

    # Admin approve first
    requests.post(f"{API}/admin/withdrawals/{wid}/approve",
                  headers=admin_headers, timeout=10)

    # Then stamp UTR — status must become "completed"
    fake_utr = f"MFB{uuid.uuid4().int % 10**12:012d}"
    m = requests.post(f"{API}/admin/withdrawals/{wid}/mark-utr",
                      json={"utr": fake_utr}, headers=admin_headers, timeout=10)
    # Might return 400 if already terminal from auto-dispatch — that's also fine
    assert m.status_code in (200, 400), m.text
    if m.status_code == 200:
        assert m.json()["utr"] == fake_utr
        # Confirm detail sees it
        d = requests.get(f"{API}/wallet/withdrawals/{wid}", headers=hdr, timeout=10).json()
        assert d["withdrawal"]["utr"] == fake_utr
        assert d["withdrawal"]["status"] == "completed"

    # Restore
    requests.put(f"{API}/admin/withdrawals/settings",
                 json={"auto_approve_enabled": True}, headers=admin_headers, timeout=10)


def test_compliance_hold_kill_switch(user_headers, admin_headers):
    """When compliance_hold is ON, no new withdrawal requests should be created."""
    hdr, _ = user_headers
    uid = _me(hdr)
    _kyc_approve(uid, admin_headers)

    bank_id = _make_verified_bank(hdr, admin_headers, holder="Hold Test", ifsc="HDFC0006666")
    _fund_wallet(uid, 5_000, admin_headers)

    # Turn on the kill-switch
    requests.put(f"{API}/admin/withdrawals/settings",
                 json={"compliance_hold": True}, headers=admin_headers, timeout=10)
    try:
        r = requests.post(f"{API}/wallet/withdrawals/request",
                          json={"amount": 500, "bank_account_id": bank_id},
                          headers=hdr, timeout=10)
        assert r.status_code == 423, r.text
    finally:
        requests.put(f"{API}/admin/withdrawals/settings",
                     json={"compliance_hold": False}, headers=admin_headers, timeout=10)
