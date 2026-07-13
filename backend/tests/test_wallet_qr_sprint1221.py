"""Sprint 12.2.1 — Wallet QR Top-up (MFB-owned QR only) tests.

Covers:
  * Admin config CRUD (allowed VPAs, domains, enable flag)
  * Parse: valid MFB QR, third-party QR (rejected), malformed URI
  * Parse: static QR (no amount), dynamic QR (amount fixed)
  * Initiate: creates Razorpay order + returns intent URI
  * Initiate: rejects third-party QR (never crediting wallet)
  * Initiate: amount mismatch (client sends different amount than QR)
  * Idempotency: same Idempotency-Key returns the same order
  * Amount limits (min/max)
  * Wallet credit only via webhook — verify /status shows uncredited until captured
  * Kill-switch: enabled=false blocks all QR flows
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

MFB_VPA = "mfb-topup@razorpay"
MFB_VPA_ALT = "mfb-wallet@icici"
MFB_DOMAIN = "mfb-collect"
THIRD_PARTY_VPA = "somemerchant@paytm"


# --------------------------------------------------------------- fixtures --
def _signup():
    mob = f"9{uuid.uuid4().int % 10**9:09d}"
    email = f"qr_{uuid.uuid4().hex[:8]}@mfb.in"
    r = requests.post(f"{API}/auth/signup",
                      json={"email": email, "mobile": mob,
                            "password": "QRTest123!", "full_name": "QR Tester"},
                      timeout=30)
    assert r.status_code in (200, 201), r.text
    tok = r.json()["token"]
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def user_headers():
    return _signup()


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/admin/login",
                      json={"email": "admin@mfb.in", "password": "Admin@MFB2026"}, timeout=30)
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['token']}",
         "Content-Type": "application/json"}
    # Configure allowed MFB VPAs (idempotent)
    requests.put(f"{API}/admin/wallet/qr/config",
                 json={"allowed_vpas": [MFB_VPA, MFB_VPA_ALT],
                       "allowed_vpa_domains": [MFB_DOMAIN],
                       "enabled": True,
                       "merchant_name": "My Funding Bank",
                       "min_amount": 1.0, "max_amount": 200000.0},
                 headers=h, timeout=15)
    return h


# ------------------------------------------------------- Admin config CRUD -
def test_admin_get_config(admin_headers):
    r = requests.get(f"{API}/admin/wallet/qr/config", headers=admin_headers, timeout=10)
    assert r.status_code == 200, r.text
    c = r.json()
    assert MFB_VPA in c["allowed_vpas"]
    assert c["enabled"] is True


def test_admin_put_config_invalid_vpa(admin_headers):
    r = requests.put(f"{API}/admin/wallet/qr/config",
                     json={"allowed_vpas": ["not-a-vpa"]},
                     headers=admin_headers, timeout=10)
    assert r.status_code == 400, r.text
    assert "invalid" in r.text.lower() or "vpa" in r.text.lower()


def test_admin_list_scans(admin_headers):
    r = requests.get(f"{API}/admin/wallet/qr/scans", headers=admin_headers, timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert "items" in j and "total" in j


# -------------------------------------------------------------- User config -
def test_user_config_hides_internals(user_headers, admin_headers):
    r = requests.get(f"{API}/wallet/qr/config", headers=user_headers, timeout=10)
    assert r.status_code == 200
    c = r.json()
    # Must expose MFB VPA list for UX pre-validation, but nothing secret
    assert MFB_VPA in c["allowed_vpas"]
    assert "min_amount" in c and "max_amount" in c


# ----------------------------------------------------------- QR parse tests -
def test_parse_valid_mfb_static_qr(user_headers, admin_headers):
    """Static QR — no amount. Backend should return is_mfb=True and amount=None."""
    uri = f"upi://pay?pa={MFB_VPA}&pn=MFB&cu=INR"
    r = requests.post(f"{API}/wallet/qr/parse", json={"upi_uri": uri},
                      headers=user_headers, timeout=10)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["is_mfb"] is True
    assert j["payee_vpa"] == MFB_VPA
    assert j["amount"] is None    # static → user must enter amount
    assert j["supported_message"] is None


def test_parse_valid_mfb_dynamic_qr_with_amount(user_headers, admin_headers):
    """Dynamic QR carrying a fixed amount."""
    uri = f"upi://pay?pa={MFB_VPA}&pn=MFB&am=500.00&cu=INR&tn=Sample"
    r = requests.post(f"{API}/wallet/qr/parse", json={"upi_uri": uri},
                      headers=user_headers, timeout=10)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["is_mfb"] is True
    assert j["amount"] == 500.0
    assert j["note"] == "Sample"


def test_parse_third_party_qr_marked_unsupported(user_headers, admin_headers):
    uri = f"upi://pay?pa={THIRD_PARTY_VPA}&pn=Chai+Stall&am=25&cu=INR"
    r = requests.post(f"{API}/wallet/qr/parse", json={"upi_uri": uri},
                      headers=user_headers, timeout=10)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["is_mfb"] is False
    assert j["reason"] == "not_mfb_vpa"
    assert j["supported_message"] == "This QR is not supported for Wallet Top-up."


def test_parse_domain_match(user_headers, admin_headers):
    """VPA in the configured allowed domain should validate too."""
    uri = f"upi://pay?pa=order123@{MFB_DOMAIN}&pn=MFB&am=99&cu=INR"
    r = requests.post(f"{API}/wallet/qr/parse", json={"upi_uri": uri},
                      headers=user_headers, timeout=10)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["is_mfb"] is True
    assert j["match_type"] == "domain"


def test_parse_malformed_uri(user_headers, admin_headers):
    for bad in ["not a uri", "http://example.com/pay?pa=foo", "upi://transfer?pa=x@y",
                "upi://pay?pa=missingdomain"]:
        r = requests.post(f"{API}/wallet/qr/parse", json={"upi_uri": bad},
                          headers=user_headers, timeout=10)
        # Some malformed URIs will be 400; the missing-domain one might parse
        # and just get flagged is_mfb=False. Either behaviour is acceptable.
        assert r.status_code in (200, 400), (bad, r.text)
        if r.status_code == 200:
            assert r.json()["is_mfb"] is False


# ---------------------------------------------------------- Initiate tests --
def test_initiate_third_party_rejected(user_headers, admin_headers):
    """Critical security: third-party QR must never create an order."""
    uri = f"upi://pay?pa={THIRD_PARTY_VPA}&pn=Chai+Stall&am=25&cu=INR"
    r = requests.post(f"{API}/wallet/qr/initiate",
                      json={"upi_uri": uri, "amount": 25},
                      headers=user_headers, timeout=10)
    assert r.status_code == 422, r.text
    assert "not supported" in r.text.lower()


def test_initiate_valid_mfb_creates_order(user_headers, admin_headers):
    uri = f"upi://pay?pa={MFB_VPA}&pn=MFB&cu=INR"
    r = requests.post(f"{API}/wallet/qr/initiate",
                      json={"upi_uri": uri, "amount": 100},
                      headers=user_headers, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] is True
    assert j["order"]["amount_paise"] == 10000
    assert j["intent_uri"].startswith("upi://pay?")
    # `@` becomes `%40` in a properly URL-encoded intent URI
    assert MFB_VPA.replace("@", "%40") in j["intent_uri"]
    assert "am=100.00" in j["intent_uri"]
    # `checkout.key_id` is only present in live mode — in demo mode it may be empty
    assert "key_id" in j["checkout"]
    assert j["merchant"]["vpa"] == MFB_VPA


def test_initiate_amount_mismatch_rejected(user_headers, admin_headers):
    """If the QR embeds an amount, client-side amount must match exactly."""
    uri = f"upi://pay?pa={MFB_VPA}&pn=MFB&am=100.00&cu=INR"
    r = requests.post(f"{API}/wallet/qr/initiate",
                      json={"upi_uri": uri, "amount": 250},
                      headers=user_headers, timeout=10)
    assert r.status_code == 400, r.text
    assert "does not match" in r.text.lower() or "match the qr" in r.text.lower()


def test_initiate_idempotency(user_headers, admin_headers):
    """Same Idempotency-Key + same body → same order (no duplicate order)."""
    uri = f"upi://pay?pa={MFB_VPA}&pn=MFB&cu=INR"
    key = f"qr_test_idem_{uuid.uuid4().hex[:8]}"
    hdr = {**user_headers, "Idempotency-Key": key}
    r1 = requests.post(f"{API}/wallet/qr/initiate",
                       json={"upi_uri": uri, "amount": 150},
                       headers=hdr, timeout=15)
    assert r1.status_code == 200, r1.text
    r2 = requests.post(f"{API}/wallet/qr/initiate",
                       json={"upi_uri": uri, "amount": 150},
                       headers=hdr, timeout=15)
    assert r2.status_code == 200, r2.text
    # Same order_id proves idempotency
    assert r1.json()["order"]["order_id"] == r2.json()["order"]["order_id"]


def test_initiate_below_min_rejected(user_headers, admin_headers):
    uri = f"upi://pay?pa={MFB_VPA}&pn=MFB&cu=INR"
    r = requests.post(f"{API}/wallet/qr/initiate",
                      json={"upi_uri": uri, "amount": 0.5},
                      headers=user_headers, timeout=10)
    assert r.status_code == 400, r.text
    assert "minimum" in r.text.lower()


def test_initiate_above_max_rejected(user_headers, admin_headers):
    uri = f"upi://pay?pa={MFB_VPA}&pn=MFB&cu=INR"
    r = requests.post(f"{API}/wallet/qr/initiate",
                      json={"upi_uri": uri, "amount": 300_000},
                      headers=user_headers, timeout=10)
    assert r.status_code == 400, r.text


# ---------------------------------------------------------- Status test -----
def test_status_shows_pending_until_webhook(user_headers, admin_headers):
    uri = f"upi://pay?pa={MFB_VPA}&pn=MFB&cu=INR"
    r = requests.post(f"{API}/wallet/qr/initiate",
                      json={"upi_uri": uri, "amount": 200},
                      headers=user_headers, timeout=15)
    order_id = r.json()["order"]["order_id"]
    s = requests.get(f"{API}/wallet/qr/status/{order_id}", headers=user_headers, timeout=10)
    assert s.status_code == 200, s.text
    body = s.json()
    assert body["order_id"] == order_id
    # Fresh order = not captured yet (wallet credit gated on webhook)
    assert body["status"] in ("created", "attempted", "pending")
    assert body.get("wallet_credited") in (False, None)


# ---------------------------------------------------------- Kill switch -----
def test_kill_switch_blocks_all_qr(user_headers, admin_headers):
    # Disable
    requests.put(f"{API}/admin/wallet/qr/config", json={"enabled": False},
                 headers=admin_headers, timeout=10)
    try:
        uri = f"upi://pay?pa={MFB_VPA}&pn=MFB&cu=INR"
        r = requests.post(f"{API}/wallet/qr/parse", json={"upi_uri": uri},
                          headers=user_headers, timeout=10)
        assert r.status_code == 423, r.text
        r2 = requests.post(f"{API}/wallet/qr/initiate",
                           json={"upi_uri": uri, "amount": 100},
                           headers=user_headers, timeout=10)
        assert r2.status_code == 423, r2.text
    finally:
        # Re-enable
        requests.put(f"{API}/admin/wallet/qr/config", json={"enabled": True},
                     headers=admin_headers, timeout=10)


# --------------------------------------------------------- Auth guard tests -
def test_endpoints_require_auth():
    uri = f"upi://pay?pa={MFB_VPA}&pn=MFB&cu=INR"
    for path in ("/wallet/qr/config",):
        r = requests.get(f"{API}{path}", timeout=10)
        assert r.status_code in (401, 403), (path, r.status_code)
    for path in ("/wallet/qr/parse", "/wallet/qr/initiate"):
        r = requests.post(f"{API}{path}", json={"upi_uri": uri, "amount": 100}, timeout=10)
        assert r.status_code in (401, 403), (path, r.status_code)
