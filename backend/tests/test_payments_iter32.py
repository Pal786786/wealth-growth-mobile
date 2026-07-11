"""Sprint 8 — Production Payments (Razorpay) backend test suite.

Covers scenarios A-I from the review request:
  A. Smoke E2E in demo mode
  B. Webhook signature security (bad/good/replay)
  C. Idempotency-Key
  D. Refund lifecycle (partial, full, over-refund)
  E. Admin config flow (secrets never leaked)
  F. Reconciliation + audit log
  G. Dashboard aggregations
  H. Amount validation (min/max/currency)
  I. Auth gating
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://wealth-growth-mobile.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mfb.in"
ADMIN_PW = "Admin@MFB2026"
USER_ID = "demo@mfb.in"
USER_PW = "demo1234"

WEBHOOK_SECRET_FOR_TEST = "iter32_webhook_secret_topsecret"


# ----------------------------- fixtures -----------------------------

@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def user_headers(s):
    r = s.post(f"{API}/auth/login",
               json={"identifier": USER_ID, "password": USER_PW}, timeout=15)
    assert r.status_code == 200, f"user login failed: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin_headers(s):
    r = s.post(f"{API}/admin/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module", autouse=True)
def _prime_config(s, admin_headers):
    """Ensure demo_mode=true and webhook_secret configured before other tests."""
    r = s.put(f"{API}/admin/payments/config", headers=admin_headers, json={
        "demo_mode": True,
        "webhook_secret": WEBHOOK_SECRET_FOR_TEST,
        "min_topup_paise": 100,
        "max_topup_paise": 10_000_000,
    }, timeout=15)
    assert r.status_code == 200, r.text
    yield


def _get_wallet_balance(s, user_headers):
    r = s.get(f"{API}/wallet", headers=user_headers, timeout=15)
    assert r.status_code == 200, r.text
    return float(r.json().get("balance", 0))


# ============================================================
# I. Auth gating (run first — cheap, fail fast)
# ============================================================
class TestAuthGating:
    def test_config_requires_user_auth(self, s):
        r = s.get(f"{API}/payments/config", timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_create_order_requires_user_auth(self, s):
        r = s.post(f"{API}/payments/orders",
                   json={"amount_paise": 1000}, timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_admin_dashboard_requires_admin(self, s):
        r = s.get(f"{API}/admin/payments/dashboard", timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_admin_dashboard_forbids_user_token(self, s, user_headers):
        r = s.get(f"{API}/admin/payments/dashboard",
                  headers=user_headers, timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_webhook_is_public_but_secured(self, s):
        # No auth → but bad signature returns 401 (mismatch) not 401 (auth)
        r = s.post(f"{API}/payments/webhooks/razorpay",
                   data=b'{"event":"payment.captured"}',
                   headers={"X-Razorpay-Signature": "bad",
                             "Content-Type": "application/json"},
                   timeout=15)
        assert r.status_code == 401, r.text
        assert "signature" in r.text.lower()


# ============================================================
# E. Admin config flow
# ============================================================
class TestAdminConfig:
    def test_get_config_shape(self, s, admin_headers):
        r = s.get(f"{API}/admin/payments/config",
                  headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("mode", "demo_mode", "has_webhook_secret",
                  "key_id_public", "min_topup_paise", "max_topup_paise"):
            assert k in j, f"missing {k}: {j}"
        # Secrets are NEVER in the read
        assert "key_secret" not in j
        assert "webhook_secret" not in j

    def test_put_sets_flags(self, s, admin_headers):
        r = s.put(f"{API}/admin/payments/config", headers=admin_headers, json={
            "key_id": "rzp_test_iter32_key",
            "key_secret": "rzp_test_iter32_secret_XYZ",
            "webhook_secret": WEBHOOK_SECRET_FOR_TEST,
        }, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("has_webhook_secret") is True, j
        # After setting key + secret, has_key_secret should be present via admin GET
        r = s.get(f"{API}/admin/payments/config",
                  headers=admin_headers, timeout=15)
        assert r.status_code == 200
        j2 = r.json()
        assert j2.get("has_key_secret") is True, j2
        assert j2.get("key_id_public") == "rzp_test_iter32_key"
        assert "key_secret" not in j2

    def test_placeholders_force_demo(self, s, admin_headers):
        r = s.put(f"{API}/admin/payments/config", headers=admin_headers, json={
            "key_id": "placeholder", "key_secret": "placeholder"
        }, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("demo_mode") is True, j
        # Re-arm real webhook secret for downstream tests
        s.put(f"{API}/admin/payments/config", headers=admin_headers, json={
            "webhook_secret": WEBHOOK_SECRET_FOR_TEST}, timeout=15)


# ============================================================
# H. Amount validation
# ============================================================
class TestAmountValidation:
    def test_amount_too_small(self, s, user_headers):
        r = s.post(f"{API}/payments/orders", headers=user_headers,
                   json={"amount_paise": 50}, timeout=15)
        assert r.status_code == 400 or r.status_code == 422, r.text

    def test_amount_too_large(self, s, user_headers):
        r = s.post(f"{API}/payments/orders", headers=user_headers,
                   json={"amount_paise": 999_999_999}, timeout=15)
        assert r.status_code in (400, 422), r.text

    def test_non_inr_rejected(self, s, user_headers):
        r = s.post(f"{API}/payments/orders", headers=user_headers,
                   json={"amount_paise": 1000, "currency": "USD"}, timeout=15)
        assert r.status_code in (400, 422), r.text


# ============================================================
# A + C. Smoke E2E (demo mode) + Idempotency
# ============================================================
class TestSmokeAndIdempotency:
    _cache: dict = {}

    def test_create_order_success(self, s, user_headers):
        idem = f"iter32_smoke_{uuid.uuid4().hex[:10]}"
        r = s.post(f"{API}/payments/orders",
                   headers={**user_headers, "Idempotency-Key": idem},
                   json={"amount_paise": 5000}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["created_new"] is True
        order = j["order"]
        assert order["status"] == "created"
        assert order["amount_paise"] == 5000
        assert order.get("is_demo") is True
        TestSmokeAndIdempotency._cache["order_id"] = order["order_id"]
        TestSmokeAndIdempotency._cache["idem"] = idem

    def test_idempotency_returns_same_order(self, s, user_headers):
        idem = TestSmokeAndIdempotency._cache["idem"]
        r = s.post(f"{API}/payments/orders",
                   headers={**user_headers, "Idempotency-Key": idem},
                   json={"amount_paise": 5000}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["created_new"] is False, j
        assert j["order"]["order_id"] == TestSmokeAndIdempotency._cache["order_id"]

    def test_demo_capture_credits_wallet(self, s, user_headers):
        order_id = TestSmokeAndIdempotency._cache["order_id"]
        pre = _get_wallet_balance(s, user_headers)
        r = s.post(f"{API}/payments/demo/capture",
                   params={"order_id": order_id, "method": "upi"},
                   headers=user_headers, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, j
        assert j.get("payment_id"), j
        TestSmokeAndIdempotency._cache["payment_id"] = j["payment_id"]

        # Wallet increased by 50.00 INR
        post = _get_wallet_balance(s, user_headers)
        assert round(post - pre, 2) == 50.00, (pre, post)

        # Order status = captured
        r2 = s.get(f"{API}/payments/orders/{order_id}",
                   headers=user_headers, timeout=15)
        assert r2.status_code == 200, r2.text
        assert r2.json()["status"] == "captured"

    def test_notification_appears(self, s, user_headers):
        r = s.get(f"{API}/notifications", headers=user_headers, timeout=15)
        assert r.status_code == 200, r.text
        items = r.json().get("items") or r.json().get("notifications") or []
        if isinstance(r.json(), list):
            items = r.json()
        titles = [str(i.get("title", "")) for i in items]
        assert any("Wallet top-up" in t or "top-up successful" in t
                   for t in titles), f"no topup notif; titles={titles[:5]}"


# ============================================================
# B. Webhook signature security
# ============================================================
class TestWebhookSecurity:
    def _make_body(self, order_id: str, amount_paise: int) -> bytes:
        payload = {
            "event": "payment.captured",
            "contains": ["payment"],
            "payload": {"payment": {"entity": {
                "id": f"pay_iter32_{uuid.uuid4().hex[:12]}",
                "amount": amount_paise, "currency": "INR",
                "status": "captured", "order_id": order_id,
                "method": "upi", "captured": True,
            }}},
        }
        return json.dumps(payload).encode("utf-8")

    def test_bad_signature_returns_401(self, s):
        body = self._make_body("order_iter32_fake", 100)
        r = s.post(f"{API}/payments/webhooks/razorpay",
                   data=body,
                   headers={"X-Razorpay-Signature": "0" * 64,
                             "Content-Type": "application/json"},
                   timeout=15)
        assert r.status_code == 401, r.text
        assert "signature" in r.text.lower()

    def test_good_signature_captures(self, s, user_headers):
        # 1) create a fresh order
        r = s.post(f"{API}/payments/orders", headers=user_headers,
                   json={"amount_paise": 2500}, timeout=15)
        assert r.status_code == 200
        order = r.json()["order"]
        provider_order_id = order["provider_order_id"]

        pre = _get_wallet_balance(s, user_headers)

        # 2) build good HMAC body
        body = self._make_body(provider_order_id, 2500)
        sig = hmac.new(WEBHOOK_SECRET_FOR_TEST.encode(),
                        body, hashlib.sha256).hexdigest()
        event_id = f"evt_iter32_{uuid.uuid4().hex[:12]}"

        r = s.post(f"{API}/payments/webhooks/razorpay", data=body,
                   headers={"X-Razorpay-Signature": sig,
                             "X-Razorpay-Event-Id": event_id,
                             "Content-Type": "application/json"},
                   timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True

        # Give the reconciler time (usually sync but be safe)
        time.sleep(0.5)
        post = _get_wallet_balance(s, user_headers)
        assert round(post - pre, 2) == 25.00, (pre, post)

        # 3) replay same body — must be idempotent
        r2 = s.post(f"{API}/payments/webhooks/razorpay", data=body,
                    headers={"X-Razorpay-Signature": sig,
                              "X-Razorpay-Event-Id": event_id,
                              "Content-Type": "application/json"},
                    timeout=15)
        assert r2.status_code == 200, r2.text
        j2 = r2.json()
        assert j2.get("idempotent") is True, j2

        post2 = _get_wallet_balance(s, user_headers)
        assert round(post2 - post, 2) == 0.00, (post, post2)


# ============================================================
# D. Refund lifecycle
# ============================================================
class TestRefundLifecycle:
    _cache: dict = {}

    def test_setup_paid_order(self, s, user_headers, admin_headers):
        # Create + demo-capture an order for ₹100
        r = s.post(f"{API}/payments/orders", headers=user_headers,
                   json={"amount_paise": 10000}, timeout=15)
        assert r.status_code == 200
        order_id = r.json()["order"]["order_id"]
        r = s.post(f"{API}/payments/demo/capture",
                   params={"order_id": order_id, "method": "upi"},
                   headers=user_headers, timeout=15)
        assert r.status_code == 200
        payment_id = r.json()["payment_id"]
        TestRefundLifecycle._cache["order_id"] = order_id
        TestRefundLifecycle._cache["payment_id"] = payment_id
        # Baseline = wallet balance BEFORE the ₹100 top-up so we can verify
        # a full refund returns the wallet to that pre-topup value.
        post_topup = _get_wallet_balance(s, user_headers)
        TestRefundLifecycle._cache["baseline_pre_topup"] = round(post_topup - 100.0, 2)

    def test_partial_refund_30pct(self, s, admin_headers, user_headers):
        pid = TestRefundLifecycle._cache["payment_id"]
        pre = _get_wallet_balance(s, user_headers)
        r = s.post(f"{API}/admin/payments/refunds", headers=admin_headers,
                   json={"payment_id": pid, "amount_paise": 3000,
                          "reason": "iter32_partial"}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["amount_paise"] == 3000
        assert j["status"] == "processed"
        post = _get_wallet_balance(s, user_headers)
        assert round(pre - post, 2) == 30.00, (pre, post)

    def test_partial_state(self, s, admin_headers):
        oid = TestRefundLifecycle._cache["order_id"]
        r = s.get(f"{API}/admin/payments/orders/{oid}",
                  headers=admin_headers, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["transaction"]["status"] == "partially_refunded", j["transaction"]
        assert j["order"]["status"] == "partially_refunded"

    def test_full_refund_remainder(self, s, admin_headers, user_headers):
        pid = TestRefundLifecycle._cache["payment_id"]
        pre = _get_wallet_balance(s, user_headers)
        # Refund the remaining 7000 paise (₹70)
        r = s.post(f"{API}/admin/payments/refunds", headers=admin_headers,
                   json={"payment_id": pid, "amount_paise": 7000,
                          "reason": "iter32_remainder"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "processed"
        post = _get_wallet_balance(s, user_headers)
        assert round(pre - post, 2) == 70.00, (pre, post)
        # Wallet is back to pre-topup baseline
        baseline = TestRefundLifecycle._cache["baseline_pre_topup"]
        assert round(post - baseline, 2) == 0.00, (baseline, post)
        # Order + tx now fully refunded
        oid = TestRefundLifecycle._cache["order_id"]
        r2 = s.get(f"{API}/admin/payments/orders/{oid}",
                   headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        jj = r2.json()
        assert jj["order"]["status"] == "refunded", jj["order"]
        assert jj["transaction"]["status"] == "refunded", jj["transaction"]

    def test_over_refund_rejected(self, s, admin_headers):
        pid = TestRefundLifecycle._cache["payment_id"]
        r = s.post(f"{API}/admin/payments/refunds", headers=admin_headers,
                   json={"payment_id": pid, "amount_paise": 100,
                          "reason": "iter32_over"}, timeout=15)
        assert r.status_code == 400, r.text
        assert "refund" in r.text.lower()


# ============================================================
# F. Reconciliation & audit
# ============================================================
class TestReconciliationAndAudit:
    def test_reconcile_returns_status(self, s, admin_headers):
        r = s.post(f"{API}/admin/payments/reconcile",
                   params={"window_hours": 24},
                   headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        # Either skipped in demo OR completed with counters
        assert (j.get("skipped") == "demo_mode_or_unconfigured"
                or "orders_scanned" in j or "healed" in j or "run_id" in j), j

    def test_reconciliation_status(self, s, admin_headers):
        r = s.get(f"{API}/admin/payments/reconciliation-status",
                  headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "interval_sec" in j

    def test_audit_log_contains_expected_events(self, s, admin_headers):
        r = s.get(f"{API}/admin/payments/audit-log",
                  params={"limit": 200},
                  headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        actions = [row["action"] for row in r.json()["items"]]
        for expected in ("payments.order.created",
                          "payments.payment.captured",
                          "payments.refund.created",
                          "payments.refund.applied",
                          "payments.config.updated"):
            assert expected in actions, (
                f"missing {expected} in audit log; seen={set(actions)}")


# ============================================================
# G. Dashboard aggregations
# ============================================================
class TestDashboard:
    def test_dashboard_shape(self, s, admin_headers):
        r = s.get(f"{API}/admin/payments/dashboard",
                  headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("gross_24h_paise", "gross_7d_paise", "refunds_24h_paise",
                  "pending_orders", "failed_orders_24h", "method_mix"):
            assert k in j, f"missing {k}: {list(j.keys())}"
        assert isinstance(j["method_mix"], list)
        # Because we captured payments this run, gross_24h should be > 0
        assert int(j["gross_24h_paise"]) > 0
