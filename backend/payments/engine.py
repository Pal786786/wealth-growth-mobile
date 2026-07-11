"""Payments Engine — Sprint 8

Owns:
  * Order lifecycle (created → attempted → captured/failed → refunded)
  * Idempotency-Key handling
  * Wallet credit (ONLY after webhook signature verification)
  * Refund creation + wallet debit on refund.processed
  * Audit log
  * Config persistence (mode, keys, demo toggle, min/max)

Collections:
  * payments_orders          — all orders
  * payments_transactions    — successful payments
  * payments_refunds         — refunds
  * payments_webhooks        — replay-protection log
  * payments_audit_log       — immutable audit trail
  * payments_config          — singleton {_id: 'active'}
"""
from __future__ import annotations
import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from .logging_setup import audit_log
from .models import (
    OrderStatus, RefundStatus, PaymentMethod,
    MIN_TOPUP_PAISE, MAX_TOPUP_PAISE,
)
from .providers.razorpay import (
    RazorpayProvider, DemoRazorpayProvider, RazorpayError, is_configured,
    simulate_captured_webhook_payload,
)

load_dotenv()
logger = logging.getLogger("payments.engine")

ORDER_COLL = "payments_orders"
TX_COLL = "payments_transactions"
REFUND_COLL = "payments_refunds"
WEBHOOK_COLL = "payments_webhooks"
AUDIT_COLL = "payments_audit_log"
CONFIG_COLL = "payments_config"

ORDER_EXPIRY_MIN = 15


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dtiso(o: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in list(o.items()):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            o[k] = v.isoformat()
    return o


class PaymentsEngine:
    def __init__(self, db):
        self.db = db
        # Config loaded from mongo on init_config()
        self.mode: str = os.environ.get("RAZORPAY_MODE", "test")
        self.demo_mode: bool = False
        self.min_topup_paise: int = MIN_TOPUP_PAISE
        self.max_topup_paise: int = MAX_TOPUP_PAISE
        self._key_id: str = os.environ.get("RAZORPAY_KEY_ID", "")
        self._key_secret: str = os.environ.get("RAZORPAY_KEY_SECRET", "")
        self._webhook_secret: str = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")

    # --------------- config --------------- #
    async def init_config(self):
        doc = await self.db[CONFIG_COLL].find_one({"_id": "active"}) or {}
        self.mode = doc.get("mode", self.mode)
        self.demo_mode = bool(doc.get("demo_mode", False))
        self.min_topup_paise = int(doc.get("min_topup_paise", self.min_topup_paise))
        self.max_topup_paise = int(doc.get("max_topup_paise", self.max_topup_paise))
        # Sensitive keys stored ONLY here on the server side
        self._key_id = doc.get("key_id") or self._key_id
        self._key_secret = doc.get("key_secret") or self._key_secret
        self._webhook_secret = doc.get("webhook_secret") or self._webhook_secret
        # Force demo if creds are placeholders
        if not is_configured(self._key_id, self._key_secret):
            self.demo_mode = True
        # Persist so the singleton exists
        await self.db[CONFIG_COLL].update_one(
            {"_id": "active"}, {"$setOnInsert": {
                "created_at": _now(),
                "mode": self.mode, "demo_mode": self.demo_mode,
                "min_topup_paise": self.min_topup_paise,
                "max_topup_paise": self.max_topup_paise,
            }}, upsert=True,
        )

    async def patch_config(self, patch: Dict[str, Any], admin_id: str) -> Dict[str, Any]:
        set_fields: Dict[str, Any] = {"updated_at": _now()}
        for k in ("demo_mode", "mode", "min_topup_paise", "max_topup_paise",
                  "key_id", "key_secret", "webhook_secret"):
            if patch.get(k) is not None:
                set_fields[k] = patch[k]
        await self.db[CONFIG_COLL].update_one(
            {"_id": "active"}, {"$set": set_fields}, upsert=True)
        # Refresh in-memory state (only for keys that were included)
        if "mode" in set_fields:
            self.mode = set_fields["mode"]
        if "demo_mode" in set_fields:
            self.demo_mode = bool(set_fields["demo_mode"])
        if "min_topup_paise" in set_fields:
            self.min_topup_paise = int(set_fields["min_topup_paise"])
        if "max_topup_paise" in set_fields:
            self.max_topup_paise = int(set_fields["max_topup_paise"])
        if "key_id" in set_fields:
            self._key_id = set_fields["key_id"]
        if "key_secret" in set_fields:
            self._key_secret = set_fields["key_secret"]
        if "webhook_secret" in set_fields:
            self._webhook_secret = set_fields["webhook_secret"]
        # If creds went missing, force demo
        if not is_configured(self._key_id, self._key_secret):
            self.demo_mode = True
            await self.db[CONFIG_COLL].update_one(
                {"_id": "active"}, {"$set": {"demo_mode": True}})
        await self._audit(admin_id, "admin", "payments.config.updated",
                          target_type="config", target_id="active",
                          after={k: ("***" if k in ("key_secret", "webhook_secret") else v)
                                 for k, v in set_fields.items() if k != "updated_at"})
        return await self.public_config()

    async def public_config(self) -> Dict[str, Any]:
        cfg_doc = await self.db[CONFIG_COLL].find_one({"_id": "active"}) or {}
        return {
            "mode": self.mode,
            "demo_mode": self.demo_mode,
            "configured": is_configured(self._key_id, self._key_secret),
            "key_id_public": self._key_id if is_configured(self._key_id, self._key_secret) else "",
            "min_topup_paise": self.min_topup_paise,
            "max_topup_paise": self.max_topup_paise,
            "has_webhook_secret": bool(self._webhook_secret and self._webhook_secret != "placeholder"),
            "provider": "razorpay",
            "currency": "INR",
            "payment_methods": ["upi", "card", "netbanking"],
            "last_updated_at": _dtiso({"t": cfg_doc.get("updated_at")}).get("t"),
        }

    def _provider(self):
        if self.demo_mode or not is_configured(self._key_id, self._key_secret):
            return DemoRazorpayProvider()
        return RazorpayProvider(self._key_id, self._key_secret, self.mode)

    def get_webhook_secret(self) -> str:
        return self._webhook_secret

    # --------------- audit --------------- #
    async def _audit(self, actor_id: str, actor_type: str, action: str,
                     target_type: str = "", target_id: str = "",
                     before: Optional[Dict[str, Any]] = None,
                     after: Optional[Dict[str, Any]] = None,
                     meta: Optional[Dict[str, Any]] = None):
        doc = {
            "audit_id": f"au_{uuid.uuid4().hex[:14]}",
            "actor_id": actor_id, "actor_type": actor_type,
            "action": action,
            "target_type": target_type, "target_id": target_id,
            "before": before, "after": after, "meta": meta or {},
            "at": _now(),
        }
        await self.db[AUDIT_COLL].insert_one(doc)
        audit_log(logger, action, actor_id=actor_id, actor_type=actor_type,
                  target_id=target_id, target_type=target_type)

    # --------------- order lifecycle --------------- #
    async def create_order(self, user_id: str, amount_paise: int,
                            currency: str = "INR",
                            idempotency_key: Optional[str] = None,
                            method_hint: Optional[str] = None,
                            notes: Optional[Dict[str, Any]] = None,
                            ) -> Tuple[Dict[str, Any], bool]:
        """Returns (order_doc, created_new_bool).

        If `idempotency_key` matches an existing order for the same user, we
        return that order unchanged (created_new=False) to make retries safe.
        """
        if amount_paise < self.min_topup_paise:
            raise ValueError(f"amount must be >= {self.min_topup_paise} paise")
        if amount_paise > self.max_topup_paise:
            raise ValueError(f"amount must be <= {self.max_topup_paise} paise")
        if currency != "INR":
            raise ValueError("only INR is supported")
        idempotency_key = (idempotency_key or "").strip() or None

        # Idempotency check
        if idempotency_key:
            existing = await self.db[ORDER_COLL].find_one(
                {"user_id": user_id, "idempotency_key": idempotency_key}, {"_id": 0})
            if existing:
                return existing, False

        order_id = f"mfb_ord_{uuid.uuid4().hex[:16]}"
        receipt = order_id[:40]
        provider = self._provider()
        try:
            provider_order = provider.create_order(
                amount_paise=amount_paise, currency=currency, receipt=receipt,
                notes={"user_id": user_id, "mfb_order_id": order_id,
                       "method_hint": method_hint or ""})
        except RazorpayError as e:
            await self._audit(user_id, "user", "payments.order.create_failed",
                              target_type="order", target_id=order_id,
                              meta={"error": str(e), "status": e.status})
            raise

        doc = {
            "order_id": order_id,
            "provider": "razorpay",
            "provider_order_id": provider_order.get("id"),
            "user_id": user_id,
            "amount_paise": int(amount_paise),
            "amount_refunded_paise": 0,
            "currency": currency,
            "status": OrderStatus.CREATED.value,
            "method_hint": method_hint,
            "notes": notes or {},
            "idempotency_key": idempotency_key,
            "is_demo": bool(getattr(provider, "key_id", "").startswith("rzp_test_demo_stub")),
            "receipt": receipt,
            "created_at": _now(),
            "updated_at": _now(),
            "expires_at": _now() + timedelta(minutes=ORDER_EXPIRY_MIN),
        }
        await self.db[ORDER_COLL].insert_one(doc)
        doc.pop("_id", None)
        await self._audit(user_id, "user", "payments.order.created",
                          target_type="order", target_id=order_id,
                          after={"amount_paise": amount_paise, "currency": currency})
        logger.info("order created", extra={"order_id": order_id, "user_id": user_id,
                                             "amount_paise": amount_paise,
                                             "provider_order_id": doc["provider_order_id"],
                                             "is_demo": doc["is_demo"]})
        return doc, True

    async def get_order(self, order_id: str,
                         user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        q: Dict[str, Any] = {"order_id": order_id}
        if user_id:
            q["user_id"] = user_id
        doc = await self.db[ORDER_COLL].find_one(q, {"_id": 0})
        return _dtiso(doc) if doc else None

    async def list_orders(self, user_id: Optional[str] = None,
                           status: Optional[str] = None,
                           limit: int = 30, skip: int = 0) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {}
        if user_id:
            q["user_id"] = user_id
        if status:
            q["status"] = status
        cur = self.db[ORDER_COLL].find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
        rows = [d async for d in cur]
        return [_dtiso(d) for d in rows]

    async def find_order_by_provider(self,
                                       provider_order_id: str) -> Optional[Dict[str, Any]]:
        return await self.db[ORDER_COLL].find_one({"provider_order_id": provider_order_id},
                                                    {"_id": 0})

    async def _mark_status(self, order_id: str, status: str,
                             extra: Optional[Dict[str, Any]] = None):
        set_fields = {"status": status, "updated_at": _now()}
        if extra:
            set_fields.update(extra)
        await self.db[ORDER_COLL].update_one(
            {"order_id": order_id}, {"$set": set_fields})

    async def mark_attempted(self, order_id: str, user_id: str):
        await self._mark_status(order_id, OrderStatus.ATTEMPTED.value)
        await self._audit(user_id, "user", "payments.order.attempted",
                          target_type="order", target_id=order_id)

    # --------------- capture (webhook) --------------- #
    async def capture_payment(self, provider_payment_id: str,
                                provider_order_id: str,
                                amount_paise: int, method: str,
                                raw_payment: Dict[str, Any]) -> Dict[str, Any]:
        """Called by webhook handler AFTER signature verification passes.

        Idempotent — safe to call multiple times for the same payment_id.
        Credits the wallet in a single Mongo update.
        """
        order = await self.find_order_by_provider(provider_order_id)
        if not order:
            logger.warning("webhook capture for unknown order", extra={
                "provider_order_id": provider_order_id,
                "provider_payment_id": provider_payment_id,
            })
            return {"ok": False, "reason": "order not found"}

        user_id = order["user_id"]
        # Idempotency — short-circuit if we've already processed this payment
        existing = await self.db[TX_COLL].find_one(
            {"provider_payment_id": provider_payment_id}, {"_id": 0})
        if existing and existing.get("status") == "captured":
            logger.info("capture idempotent replay", extra={
                "payment_id": existing["payment_id"], "user_id": user_id})
            return {"ok": True, "idempotent": True, "payment_id": existing["payment_id"]}

        payment_id = f"mfb_pay_{uuid.uuid4().hex[:16]}"
        tx_doc = {
            "payment_id": payment_id,
            "order_id": order["order_id"],
            "provider": "razorpay",
            "provider_payment_id": provider_payment_id,
            "provider_order_id": provider_order_id,
            "user_id": user_id,
            "amount_paise": int(amount_paise),
            "amount_refunded_paise": 0,
            "currency": order.get("currency", "INR"),
            "method": (method or "other").lower(),
            "status": "captured",
            "captured_at": _now(),
            "raw": {k: raw_payment.get(k) for k in
                     ("vpa", "bank", "wallet", "card_id", "international",
                      "description", "fee", "tax", "contact", "email")
                     if k in raw_payment},
        }
        await self.db[TX_COLL].insert_one(tx_doc)
        tx_doc.pop("_id", None)

        await self._mark_status(order["order_id"], OrderStatus.CAPTURED.value,
                                extra={"captured_at": _now(),
                                       "payment_id": payment_id})

        # Credit wallet + write transaction to legacy `wallet_transactions` for
        # visibility in the existing wallet UI. Only after signature verified.
        amount_inr = round(amount_paise / 100.0, 2)
        await self.db.wallets.update_one(
            {"user_id": user_id},
            {"$inc": {"balance": amount_inr}},
            upsert=True,
        )
        try:
            await self.db.wallet_transactions.insert_one({
                "tx_id": f"tx_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "kind": "credit", "category": "topup",
                "amount": amount_inr,
                "description": f"Wallet top-up via {tx_doc['method']} (Razorpay)",
                "status": "success",
                "payment_id": payment_id,
                "provider_payment_id": provider_payment_id,
                "created_at": _now(),
            })
        except Exception as e:
            logger.warning("legacy wallet_transactions insert failed: %s", e)

        await self._audit(user_id, "user", "payments.payment.captured",
                          target_type="payment", target_id=payment_id,
                          after={"amount_paise": amount_paise, "method": tx_doc["method"],
                                 "order_id": order["order_id"]})

        # Optional: send a notification the wallet was credited
        try:
            await self.db.notifications.insert_one({
                "notif_id": f"nf_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "title": "💰 Wallet top-up successful",
                "body": f"₹{amount_inr:,.2f} credited via {tx_doc['method']}",
                "read": False, "created_at": _now(),
                "deeplink": "/wallet", "category": "payment",
                "metadata": {"payment_id": payment_id, "amount_paise": amount_paise},
            })
        except Exception:
            pass

        logger.info("payment captured", extra={"payment_id": payment_id,
                                                "order_id": order["order_id"],
                                                "user_id": user_id,
                                                "amount_paise": amount_paise,
                                                "method": tx_doc["method"]})
        return {"ok": True, "payment_id": payment_id}

    async def fail_payment(self, provider_payment_id: str, provider_order_id: str,
                             reason: str, raw: Dict[str, Any]):
        order = await self.find_order_by_provider(provider_order_id)
        if not order:
            return
        # Track the failure but leave order status alone if already captured
        if order.get("status") == OrderStatus.CAPTURED.value:
            return
        await self._mark_status(order["order_id"], OrderStatus.FAILED.value,
                                extra={"last_failure_reason": (reason or "")[:200],
                                       "failed_at": _now(),
                                       "last_failed_provider_payment_id": provider_payment_id})
        await self._audit(order["user_id"], "user", "payments.payment.failed",
                          target_type="order", target_id=order["order_id"],
                          meta={"provider_payment_id": provider_payment_id, "reason": reason})
        logger.info("payment failed", extra={"order_id": order["order_id"],
                                              "provider_payment_id": provider_payment_id,
                                              "reason": reason})

    # --------------- Retry --------------- #
    async def retry_order(self, order_id: str, admin_id: str,
                           reason: Optional[str] = None) -> Dict[str, Any]:
        """Admin-initiated retry: creates a NEW Razorpay order copying amount /
        user of the failed one."""
        src = await self.get_order(order_id)
        if not src:
            raise ValueError("order not found")
        if src["status"] not in (OrderStatus.FAILED.value, OrderStatus.EXPIRED.value):
            raise ValueError(f"order is {src['status']}; only failed/expired can be retried")
        new_order, _ = await self.create_order(
            user_id=src["user_id"],
            amount_paise=int(src["amount_paise"]),
            currency=src.get("currency", "INR"),
            idempotency_key=f"retry_{order_id}_{uuid.uuid4().hex[:6]}",
            method_hint=src.get("method_hint"),
            notes={"retry_of": order_id, "reason": (reason or "")[:200]},
        )
        await self._audit(admin_id, "admin", "payments.order.retried",
                          target_type="order", target_id=new_order["order_id"],
                          meta={"retry_of": order_id, "reason": reason})
        return new_order

    # --------------- Refunds --------------- #
    async def create_refund(self, admin_id: str, payment_id: str,
                             amount_paise: Optional[int],
                             reason: str,
                             notes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        tx = await self.db[TX_COLL].find_one({"payment_id": payment_id}, {"_id": 0})
        if not tx:
            raise ValueError("payment not found")
        if tx["status"] not in ("captured", "partially_refunded"):
            raise ValueError(f"cannot refund a {tx['status']} payment")
        refundable = int(tx["amount_paise"]) - int(tx.get("amount_refunded_paise") or 0)
        if refundable <= 0:
            raise ValueError("payment already fully refunded")
        amount = int(amount_paise) if amount_paise else refundable
        if amount <= 0 or amount > refundable:
            raise ValueError(f"refund amount must be 1..{refundable} paise")

        provider = self._provider()
        try:
            provider_refund = provider.create_refund(
                tx["provider_payment_id"], amount_paise=amount,
                notes={"reason": reason, **(notes or {})})
        except RazorpayError as e:
            await self._audit(admin_id, "admin", "payments.refund.failed_at_provider",
                              target_type="payment", target_id=payment_id,
                              meta={"error": str(e)})
            raise

        refund_id = f"mfb_rfnd_{uuid.uuid4().hex[:16]}"
        refund_doc = {
            "refund_id": refund_id,
            "provider": "razorpay",
            "provider_refund_id": provider_refund.get("id"),
            "payment_id": payment_id,
            "provider_payment_id": tx["provider_payment_id"],
            "user_id": tx["user_id"],
            "amount_paise": amount,
            "reason": (reason or "")[:200],
            "notes": notes or {},
            "status": provider_refund.get("status", RefundStatus.PENDING.value),
            "initiated_by": admin_id,
            "created_at": _now(),
            "processed_at": _now() if provider_refund.get("status") == "processed" else None,
        }
        await self.db[REFUND_COLL].insert_one(refund_doc)
        refund_doc.pop("_id", None)

        # If provider processed synchronously (very common for full refunds in
        # test mode), apply the wallet debit immediately. Otherwise wait for
        # the refund.processed webhook.
        if provider_refund.get("status") == "processed":
            await self._apply_refund_side_effects(tx, refund_doc, admin_id)

        await self._audit(admin_id, "admin", "payments.refund.created",
                          target_type="refund", target_id=refund_id,
                          after={"amount_paise": amount, "payment_id": payment_id})
        logger.info("refund created", extra={"refund_id": refund_id,
                                              "payment_id": payment_id,
                                              "amount_paise": amount,
                                              "status": refund_doc["status"]})
        return refund_doc

    async def _apply_refund_side_effects(self, tx: Dict[str, Any],
                                           refund: Dict[str, Any],
                                           admin_id: str):
        """Debit wallet, update tx counters, mark order refunded/partial."""
        amount_inr = round(refund["amount_paise"] / 100.0, 2)
        user_id = tx["user_id"]
        # Debit wallet balance
        await self.db.wallets.update_one(
            {"user_id": user_id}, {"$inc": {"balance": -amount_inr}}, upsert=True)
        # Track refunded amount on the tx
        new_refunded = int(tx.get("amount_refunded_paise") or 0) + int(refund["amount_paise"])
        fully_refunded = new_refunded >= int(tx["amount_paise"])
        await self.db[TX_COLL].update_one(
            {"payment_id": tx["payment_id"]},
            {"$set": {"amount_refunded_paise": new_refunded,
                       "status": "refunded" if fully_refunded else "partially_refunded",
                       "refunded_at": _now()}}
        )
        # Update the parent order's status + amount_refunded
        order = await self.db[ORDER_COLL].find_one({"order_id": tx["order_id"]}, {"_id": 0})
        if order:
            new_ord_ref = int(order.get("amount_refunded_paise") or 0) + int(refund["amount_paise"])
            new_status = (OrderStatus.REFUNDED.value
                           if new_ord_ref >= int(order["amount_paise"])
                           else OrderStatus.PARTIALLY_REFUNDED.value)
            await self._mark_status(order["order_id"], new_status,
                                    extra={"amount_refunded_paise": new_ord_ref,
                                           "refunded_at": _now()})
        # Legacy wallet_transactions entry
        try:
            await self.db.wallet_transactions.insert_one({
                "tx_id": f"tx_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "kind": "debit", "category": "refund",
                "amount": amount_inr,
                "description": f"Refund for payment {tx['payment_id']}",
                "status": "success",
                "refund_id": refund["refund_id"],
                "created_at": _now(),
            })
        except Exception:
            pass
        # Notify user
        try:
            await self.db.notifications.insert_one({
                "notif_id": f"nf_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "title": "↩️ Refund processed",
                "body": f"₹{amount_inr:,.2f} refunded to your wallet",
                "read": False, "created_at": _now(),
                "deeplink": "/wallet", "category": "payment",
                "metadata": {"refund_id": refund["refund_id"], "amount_paise": refund["amount_paise"]},
            })
        except Exception:
            pass
        await self._audit(admin_id, "system", "payments.refund.applied",
                          target_type="refund", target_id=refund["refund_id"],
                          after={"amount_inr": amount_inr, "fully_refunded": fully_refunded})

    async def refund_processed_webhook(self, provider_refund_id: str,
                                         raw_refund: Dict[str, Any]) -> Dict[str, Any]:
        rfnd = await self.db[REFUND_COLL].find_one(
            {"provider_refund_id": provider_refund_id}, {"_id": 0})
        if not rfnd:
            return {"ok": False, "reason": "refund not found"}
        if rfnd["status"] == "processed":
            return {"ok": True, "idempotent": True}
        tx = await self.db[TX_COLL].find_one({"payment_id": rfnd["payment_id"]}, {"_id": 0})
        if not tx:
            return {"ok": False, "reason": "payment not found"}
        await self.db[REFUND_COLL].update_one(
            {"refund_id": rfnd["refund_id"]},
            {"$set": {"status": "processed", "processed_at": _now()}})
        await self._apply_refund_side_effects(tx, rfnd, admin_id="system")
        return {"ok": True}

    async def refund_failed_webhook(self, provider_refund_id: str,
                                     raw_refund: Dict[str, Any]):
        await self.db[REFUND_COLL].update_one(
            {"provider_refund_id": provider_refund_id},
            {"$set": {"status": "failed", "processed_at": _now(),
                       "error": raw_refund.get("error_description", "")[:250]}})

    # --------------- Query helpers --------------- #
    async def list_transactions(self, user_id: Optional[str] = None,
                                  limit: int = 50, skip: int = 0) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {}
        if user_id:
            q["user_id"] = user_id
        cur = self.db[TX_COLL].find(q, {"_id": 0}).sort("captured_at", -1).skip(skip).limit(limit)
        return [_dtiso(d) async for d in cur]

    async def list_refunds(self, limit: int = 50, skip: int = 0) -> List[Dict[str, Any]]:
        cur = self.db[REFUND_COLL].find({}, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
        return [_dtiso(d) async for d in cur]

    async def audit_trail(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self.db[AUDIT_COLL].find({}, {"_id": 0}).sort("at", -1).limit(limit)
        return [_dtiso(d) async for d in cur]

    async def dashboard(self) -> Dict[str, Any]:
        """Aggregated dashboard payload for admin."""
        now = _now()
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)

        async def _sum(coll, match, field="amount_paise"):
            pipeline = [{"$match": match},
                        {"$group": {"_id": None, "sum": {"$sum": f"${field}"},
                                     "count": {"$sum": 1}}}]
            r = await self.db[coll].aggregate(pipeline).to_list(1)
            return (r[0]["sum"] if r else 0), (r[0]["count"] if r else 0)

        gross_24h_paise, gross_24h_count = await _sum(TX_COLL, {
            "status": {"$in": ["captured", "partially_refunded"]},
            "captured_at": {"$gte": day_ago}})
        gross_7d_paise, gross_7d_count = await _sum(TX_COLL, {
            "status": {"$in": ["captured", "partially_refunded"]},
            "captured_at": {"$gte": week_ago}})
        refunds_24h_paise, refunds_24h_count = await _sum(REFUND_COLL, {
            "status": "processed", "processed_at": {"$gte": day_ago}})
        pending_orders = await self.db[ORDER_COLL].count_documents({
            "status": {"$in": [OrderStatus.CREATED.value, OrderStatus.ATTEMPTED.value]}})
        failed_orders_24h = await self.db[ORDER_COLL].count_documents({
            "status": OrderStatus.FAILED.value,
            "failed_at": {"$gte": day_ago}})

        # Method mix over 7 days
        method_pipeline = [
            {"$match": {"captured_at": {"$gte": week_ago},
                        "status": {"$in": ["captured", "partially_refunded", "refunded"]}}},
            {"$group": {"_id": "$method", "count": {"$sum": 1},
                         "sum_paise": {"$sum": "$amount_paise"}}},
            {"$sort": {"sum_paise": -1}},
        ]
        method_mix = await self.db[TX_COLL].aggregate(method_pipeline).to_list(20)

        return {
            "config": await self.public_config(),
            "gross_24h_paise": int(gross_24h_paise), "gross_24h_count": gross_24h_count,
            "gross_7d_paise": int(gross_7d_paise), "gross_7d_count": gross_7d_count,
            "refunds_24h_paise": int(refunds_24h_paise), "refunds_24h_count": refunds_24h_count,
            "pending_orders": pending_orders,
            "failed_orders_24h": failed_orders_24h,
            "method_mix": [
                {"method": (m["_id"] or "unknown"),
                 "count": m["count"], "sum_paise": int(m["sum_paise"])}
                for m in method_mix
            ],
        }

    # --------------- Demo helpers --------------- #
    async def demo_simulate_capture(self, order_id: str, method: str = "upi") -> Dict[str, Any]:
        """Only usable in demo mode: fabricates a `payment.captured` event and
        pipes it through the normal capture path."""
        if not self.demo_mode:
            raise ValueError("demo mode is disabled")
        order = await self.get_order(order_id)
        if not order:
            raise ValueError("order not found")
        # Rebuild raw as if from webhook
        payload = simulate_captured_webhook_payload(
            order={"id": order["provider_order_id"], "amount": order["amount_paise"],
                    "currency": order.get("currency", "INR")},
            user_id=order["user_id"], method=method)
        payment_entity = payload["payload"]["payment"]["entity"]
        result = await self.capture_payment(
            provider_payment_id=payment_entity["id"],
            provider_order_id=payment_entity["order_id"],
            amount_paise=payment_entity["amount"],
            method=payment_entity["method"],
            raw_payment=payment_entity,
        )
        return {"ok": result.get("ok", False), "payment_id": result.get("payment_id"),
                "demo_payment_entity": payment_entity}
