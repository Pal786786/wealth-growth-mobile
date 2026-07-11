"""Webhook handler + replay protection."""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .security import verify_webhook_signature, payload_hash

logger = logging.getLogger("payments.webhooks")

WEBHOOK_COLL = "payments_webhooks"

# Events we handle
HANDLED_EVENTS = {
    "payment.captured", "payment.failed", "payment.authorized",
    "refund.created", "refund.processed", "refund.failed",
    "order.paid",
}


def _now():
    return datetime.now(timezone.utc)


async def process_webhook(engine, body: bytes, signature: str,
                          headers: Dict[str, str]) -> Dict[str, Any]:
    """Verify signature, dedupe (replay protection), then dispatch to engine.

    Returns a small dict for the HTTP response. Any thrown ValueError becomes
    a 400; any signature mismatch becomes a 401.
    """
    webhook_secret = engine.get_webhook_secret()
    if not webhook_secret or webhook_secret == "placeholder":
        # In demo mode we treat all incoming as trusted (for local E2E)
        if not engine.demo_mode:
            return {"ok": False, "status": 503, "reason": "webhook secret not set"}
    else:
        if not verify_webhook_signature(body, signature, webhook_secret):
            logger.warning("webhook signature mismatch", extra={
                "payload_hash": payload_hash(body)})
            return {"ok": False, "status": 401, "reason": "signature mismatch"}

    p_hash = payload_hash(body)
    # Replay protection: check by payload hash AND by Razorpay's x-razorpay-event-id
    event_id = headers.get("x-razorpay-event-id") or headers.get("X-Razorpay-Event-Id")
    dupe_q = {"$or": [{"payload_hash": p_hash}]}
    if event_id:
        dupe_q["$or"].append({"event_id": event_id})
    existing = await engine.db[WEBHOOK_COLL].find_one(dupe_q, {"_id": 0})
    if existing and existing.get("processed_at"):
        logger.info("webhook replay ignored", extra={
            "webhook_id": existing["webhook_id"],
            "event": existing.get("event"),
            "payload_hash": p_hash,
        })
        return {"ok": True, "idempotent": True, "webhook_id": existing["webhook_id"]}

    try:
        import json as _json
        data = _json.loads(body.decode("utf-8"))
    except Exception:
        return {"ok": False, "status": 400, "reason": "invalid json"}

    event = data.get("event", "")
    contains = data.get("contains", [])

    webhook_doc = {
        "webhook_id": f"wh_{uuid.uuid4().hex[:14]}",
        "provider": "razorpay",
        "event": event,
        "event_id": event_id,
        "payload_hash": p_hash,
        "signature_ok": True,
        "received_at": _now(),
        "processed_at": None,
        "contains": contains,
        "amount_paise": None,
        "provider_order_id": None,
        "provider_payment_id": None,
        "provider_refund_id": None,
        "error": None,
    }

    # Route based on event
    try:
        if event in ("payment.captured", "order.paid"):
            entity = _payment_entity(data) or {}
            provider_order_id = entity.get("order_id") or _order_id_from_order_event(data)
            provider_payment_id = entity.get("id") or ""
            amount = int(entity.get("amount") or 0)
            method = entity.get("method") or "other"
            webhook_doc.update({"provider_order_id": provider_order_id,
                                 "provider_payment_id": provider_payment_id,
                                 "amount_paise": amount})
            if provider_order_id and provider_payment_id:
                await engine.capture_payment(
                    provider_payment_id=provider_payment_id,
                    provider_order_id=provider_order_id,
                    amount_paise=amount, method=method,
                    raw_payment=entity,
                )
        elif event == "payment.failed":
            entity = _payment_entity(data) or {}
            webhook_doc.update({
                "provider_order_id": entity.get("order_id"),
                "provider_payment_id": entity.get("id"),
                "amount_paise": int(entity.get("amount") or 0),
            })
            await engine.fail_payment(
                provider_payment_id=entity.get("id", ""),
                provider_order_id=entity.get("order_id", ""),
                reason=entity.get("error_description", "payment failed"),
                raw=entity,
            )
        elif event == "refund.processed":
            entity = _refund_entity(data) or {}
            webhook_doc["provider_refund_id"] = entity.get("id")
            webhook_doc["amount_paise"] = int(entity.get("amount") or 0)
            await engine.refund_processed_webhook(entity.get("id", ""), entity)
        elif event == "refund.failed":
            entity = _refund_entity(data) or {}
            webhook_doc["provider_refund_id"] = entity.get("id")
            await engine.refund_failed_webhook(entity.get("id", ""), entity)
        elif event == "refund.created" or event == "payment.authorized":
            # Acknowledge but no wallet effect — wait for processed/captured
            pass
        else:
            logger.info("unhandled webhook event", extra={"event": event})
        webhook_doc["processed_at"] = _now()
    except Exception as e:
        logger.exception("webhook dispatch failed")
        webhook_doc["error"] = str(e)[:400]

    await engine.db[WEBHOOK_COLL].insert_one(webhook_doc)
    return {"ok": True, "event": event, "webhook_id": webhook_doc["webhook_id"],
            "replay": False}


def _payment_entity(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        return data["payload"]["payment"]["entity"]
    except Exception:
        return None


def _refund_entity(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        return data["payload"]["refund"]["entity"]
    except Exception:
        return None


def _order_id_from_order_event(data: Dict[str, Any]) -> Optional[str]:
    try:
        return data["payload"]["order"]["entity"]["id"]
    except Exception:
        return None
