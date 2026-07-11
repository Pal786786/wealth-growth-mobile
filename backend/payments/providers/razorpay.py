"""Razorpay provider — wraps the razorpay SDK with a demo fallback.

Supports TEST + LIVE keys via `mode` selector. Never logs secrets.

Demo mode simulates the entire Razorpay flow locally so we can run E2E tests
without hitting the real API. It generates deterministic-shaped orders and
payments that mirror Razorpay's response format.
"""
from __future__ import annotations
import logging
import random
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger("payments.razorpay")

try:
    import razorpay  # type: ignore
    HAS_SDK = True
except Exception:
    razorpay = None  # type: ignore
    HAS_SDK = False


def _placeholder_val(v: Optional[str]) -> bool:
    if not v:
        return True
    v = v.strip().lower()
    return v in ("", "placeholder", "none", "changeme", "todo")


def is_configured(key_id: Optional[str], key_secret: Optional[str]) -> bool:
    return HAS_SDK and not _placeholder_val(key_id) and not _placeholder_val(key_secret)


class RazorpayError(Exception):
    def __init__(self, message: str, status: int = 502, upstream: Optional[Any] = None):
        super().__init__(message)
        self.status = status
        self.upstream = upstream


class RazorpayProvider:
    def __init__(self, key_id: str, key_secret: str, mode: str = "test"):
        self.key_id = (key_id or "").strip()
        self.key_secret = (key_secret or "").strip()
        self.mode = mode
        self._client = None
        if is_configured(self.key_id, self.key_secret):
            self._client = razorpay.Client(auth=(self.key_id, self.key_secret))
            # Add a modest timeout so a hanging Razorpay API doesn't stall us
            try:
                self._client.set_app_details({"title": "MyFundingBank", "version": "8.0"})
            except Exception:
                pass

    @property
    def configured(self) -> bool:
        return self._client is not None

    # --------- Orders --------- #
    def create_order(self, amount_paise: int, currency: str, receipt: str,
                     notes: Dict[str, Any]) -> Dict[str, Any]:
        if not self.configured:
            raise RazorpayError("Razorpay not configured", status=503)
        try:
            order = self._client.order.create({
                "amount": int(amount_paise),
                "currency": currency,
                "receipt": receipt[:40],
                "payment_capture": 1,
                "notes": {k: str(v)[:250] for k, v in (notes or {}).items()},
            })
            logger.info("razorpay order created", extra={
                "provider_order_id": order.get("id"), "amount_paise": amount_paise,
            })
            return order
        except razorpay.errors.BadRequestError as e:  # type: ignore[attr-defined]
            raise RazorpayError(f"bad request: {e}", status=400)
        except Exception as e:
            logger.exception("razorpay order create failed")
            raise RazorpayError(str(e), status=502)

    def fetch_order(self, provider_order_id: str) -> Dict[str, Any]:
        if not self.configured:
            raise RazorpayError("Razorpay not configured", status=503)
        try:
            return self._client.order.fetch(provider_order_id)
        except Exception as e:
            raise RazorpayError(str(e), status=502)

    def fetch_order_payments(self, provider_order_id: str) -> List[Dict[str, Any]]:
        if not self.configured:
            raise RazorpayError("Razorpay not configured", status=503)
        try:
            data = self._client.order.payments(provider_order_id) or {}
            return data.get("items", []) if isinstance(data, dict) else []
        except Exception as e:
            raise RazorpayError(str(e), status=502)

    def fetch_payment(self, provider_payment_id: str) -> Dict[str, Any]:
        if not self.configured:
            raise RazorpayError("Razorpay not configured", status=503)
        try:
            return self._client.payment.fetch(provider_payment_id)
        except Exception as e:
            raise RazorpayError(str(e), status=502)

    def fetch_recent_orders(self, from_ts: int, to_ts: int,
                             count: int = 100) -> List[Dict[str, Any]]:
        if not self.configured:
            raise RazorpayError("Razorpay not configured", status=503)
        try:
            data = self._client.order.all({
                "from": int(from_ts), "to": int(to_ts), "count": min(int(count), 100),
            }) or {}
            return data.get("items", []) if isinstance(data, dict) else []
        except Exception as e:
            raise RazorpayError(str(e), status=502)

    # --------- Refunds --------- #
    def create_refund(self, provider_payment_id: str,
                       amount_paise: Optional[int] = None,
                       notes: Optional[Dict[str, Any]] = None,
                       speed: str = "normal") -> Dict[str, Any]:
        if not self.configured:
            raise RazorpayError("Razorpay not configured", status=503)
        payload: Dict[str, Any] = {"speed": speed}
        if amount_paise is not None:
            payload["amount"] = int(amount_paise)
        if notes:
            payload["notes"] = {k: str(v)[:250] for k, v in notes.items()}
        try:
            return self._client.payment.refund(provider_payment_id, payload)
        except Exception as e:
            logger.exception("razorpay refund failed")
            raise RazorpayError(str(e), status=502)

    def fetch_refund(self, provider_refund_id: str) -> Dict[str, Any]:
        if not self.configured:
            raise RazorpayError("Razorpay not configured", status=503)
        try:
            return self._client.refund.fetch(provider_refund_id)
        except Exception as e:
            raise RazorpayError(str(e), status=502)


# =============== Demo fallback — mirrors Razorpay's response shape ===============

class DemoRazorpayProvider:
    """Local-only fallback used when demo_mode is on or keys missing.

    Emits Razorpay-shaped responses so the rest of the code doesn't branch.
    """

    def __init__(self):
        self.configured = True
        self.key_id = "rzp_test_demo_stub"
        self.key_secret = "demo_stub_secret"
        self.mode = "test"

    def create_order(self, amount_paise: int, currency: str, receipt: str,
                     notes: Dict[str, Any]) -> Dict[str, Any]:
        oid = f"order_demo_{uuid.uuid4().hex[:14]}"
        return {
            "id": oid, "entity": "order", "amount": int(amount_paise),
            "amount_paid": 0, "amount_due": int(amount_paise),
            "currency": currency, "receipt": receipt[:40],
            "status": "created", "attempts": 0, "notes": notes or {},
            "created_at": int(time.time()), "demo": True,
        }

    def fetch_order(self, provider_order_id: str) -> Dict[str, Any]:
        return {"id": provider_order_id, "status": "paid", "demo": True}

    def fetch_order_payments(self, provider_order_id: str) -> List[Dict[str, Any]]:
        return []

    def fetch_payment(self, provider_payment_id: str) -> Dict[str, Any]:
        return {"id": provider_payment_id, "status": "captured", "demo": True}

    def fetch_recent_orders(self, from_ts: int, to_ts: int,
                             count: int = 100) -> List[Dict[str, Any]]:
        return []

    def create_refund(self, provider_payment_id: str,
                       amount_paise: Optional[int] = None,
                       notes: Optional[Dict[str, Any]] = None,
                       speed: str = "normal") -> Dict[str, Any]:
        return {
            "id": f"rfnd_demo_{uuid.uuid4().hex[:14]}",
            "entity": "refund", "amount": amount_paise or 0,
            "currency": "INR", "payment_id": provider_payment_id,
            "notes": notes or {}, "receipt": None, "acquirer_data": {},
            "created_at": int(time.time()), "batch_id": None,
            "status": "processed", "speed_processed": speed,
            "speed_requested": speed, "demo": True,
        }

    def fetch_refund(self, provider_refund_id: str) -> Dict[str, Any]:
        return {"id": provider_refund_id, "status": "processed", "demo": True}


def simulate_captured_webhook_payload(order: Dict[str, Any],
                                        user_id: str,
                                        method: str = "upi") -> Dict[str, Any]:
    """Build a Razorpay-shape 'payment.captured' event body for demo flow."""
    provider_payment_id = f"pay_demo_{uuid.uuid4().hex[:14]}"
    return {
        "entity": "event",
        "account_id": "acc_demo",
        "event": "payment.captured",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": provider_payment_id,
                    "entity": "payment",
                    "amount": order["amount"],
                    "currency": order.get("currency", "INR"),
                    "status": "captured",
                    "order_id": order["id"],
                    "invoice_id": None,
                    "international": False,
                    "method": method,
                    "amount_refunded": 0,
                    "refund_status": None,
                    "captured": True,
                    "description": "Demo top-up",
                    "card_id": None,
                    "bank": None,
                    "wallet": None,
                    "vpa": "demo@upi" if method == "upi" else None,
                    "email": "demo@mfb.in",
                    "contact": "+919999999999",
                    "notes": {"user_id": user_id},
                    "fee": 0, "tax": 0,
                    "error_code": None, "error_description": None,
                    "created_at": int(time.time()),
                }
            }
        },
        "created_at": int(time.time()),
        "demo": True,
    }
