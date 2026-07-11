"""Security helpers — HMAC signature verification + replay protection.

Razorpay signs webhook bodies with HMAC-SHA256(key=webhook_secret, msg=body).
We use the Razorpay SDK's `utility.verify_webhook_signature` when available and
fall back to a manual constant-time comparison.
"""
from __future__ import annotations
import hashlib
import hmac
import logging
from typing import Optional

logger = logging.getLogger("payments.security")


def hmac_sha256_hex(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    """Constant-time HMAC-SHA256 verify. Returns False for any mismatch."""
    if not signature or not secret or not body:
        return False
    try:
        expected = hmac_sha256_hex(secret, body)
        return hmac.compare_digest(expected, signature)
    except Exception:
        logger.warning("webhook signature verify raised", exc_info=True)
        return False


def verify_payment_signature(order_id: str, payment_id: str,
                              signature: str, key_secret: str) -> bool:
    """Verify the client-side payment signature Razorpay returns to the SDK.
    Formula: HMAC-SHA256(key=KEY_SECRET, msg=f"{order_id}|{payment_id}").
    """
    if not (order_id and payment_id and signature and key_secret):
        return False
    try:
        body = f"{order_id}|{payment_id}".encode("utf-8")
        expected = hmac.new(key_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception:
        logger.warning("payment signature verify raised", exc_info=True)
        return False


def payload_hash(body: bytes) -> str:
    """Content-addressed hash for replay protection."""
    return hashlib.sha256(body).hexdigest()
