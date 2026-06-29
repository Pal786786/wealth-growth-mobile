"""Wallet v2 module — double-entry ledger, payments, analytics, admin.

Extends the existing wallet (collections: wallets, transactions) WITHOUT touching
any existing endpoints or schemas. Adds:

  Collections (new):
    • wallet_ledger        — double-entry: every txn -> two rows (debit + credit)
    • payment_intents      — Stripe checkout sessions (idempotent by session_id)
    • webhook_events       — idempotency log for inbound webhooks
    • cashback_log         — cashback / reward credit events

  User endpoints (auth):
    GET    /api/wallet/v2/summary          Available + pending + totals
    GET    /api/wallet/v2/transactions     Filters: q, type, category, status, from, to, limit
    GET    /api/wallet/v2/transaction/{id} Detail
    GET    /api/wallet/v2/receipt/{id}     PDF receipt (download)
    GET    /api/wallet/v2/statement.pdf    Statement PDF (period filter)
    GET    /api/wallet/v2/statement.xlsx   Statement Excel
    GET    /api/wallet/v2/analytics        Daily/weekly/monthly chart data
    GET    /api/wallet/v2/cashback         Cashback / reward history
    POST   /api/wallet/v2/payments/create  Create Stripe Checkout Session
    POST   /api/wallet/v2/payments/confirm Confirm via session_id (idempotent)
    POST   /api/wallet/v2/payments/webhook Stripe webhook (signature-verified)

  Admin endpoints:
    GET    /api/admin/wallet/transactions       Search + filters
    GET    /api/admin/wallet/transactions.csv   CSV export
    GET    /api/admin/wallet/payment-logs       Payment intents + webhook events
    GET    /api/admin/wallet/analytics          Platform-wide analytics
    POST   /api/admin/wallet/adjust             Manual wallet adjustment (audited)

Idempotency:
  Every payment intent has a stable session_id. confirm() is safe to call any
  number of times — second call returns the same result, no double-credit.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field

import wallet_pdf

logger = logging.getLogger("mfb.wallet_v2")

_db = None
_get_current_user = None
_get_current_admin = None

FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN",
                                 "https://wealth-growth-mobile.preview.emergentagent.com")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

MIN_TOPUP = 100.0
MAX_TOPUP = 200_000.0
RATE_LIMIT_TOPUP_PER_HOUR = 10  # per user


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_id(p: str) -> str:
    return f"{p}_{secrets.token_hex(6)}"


# ---------- Pydantic models ----------
class CreatePaymentReq(BaseModel):
    amount: float = Field(..., gt=0, le=MAX_TOPUP)
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None

class ConfirmPaymentReq(BaseModel):
    session_id: str

class AdminAdjustReq(BaseModel):
    user_id: str
    amount: float  # positive = credit, negative = debit
    reason: str


# ---------- Double-entry ledger helpers ----------
async def _post_ledger(tx_id: str, user_id: str, amount: float, category: str,
                      debit_account: str, credit_account: str,
                      description: str, provider: Optional[str] = None,
                      reference_id: Optional[str] = None):
    """Records a balanced pair (debit + credit) for ONE business transaction."""
    base = {
        "tx_id": tx_id,
        "user_id": user_id,
        "amount": float(amount),
        "category": category,
        "description": description,
        "provider": provider,
        "reference_id": reference_id,
        "created_at": _now(),
    }
    await _db.wallet_ledger.insert_many([
        {**base, "_entry": "debit", "account": debit_account, "side": "DR"},
        {**base, "_entry": "credit", "account": credit_account, "side": "CR"},
    ])


async def _credit_wallet(user_id: str, amount: float, category: str, description: str,
                        provider: Optional[str] = None,
                        reference_id: Optional[str] = None,
                        counterparty: Optional[str] = None) -> Dict[str, Any]:
    """Credits user wallet. Creates ledger entries + a unified `transactions` row
    so existing UI / admin keeps working. Returns the canonical tx doc."""
    tx_id = _gen_id("tx")
    # Update wallet aggregate
    await _db.wallets.update_one(
        {"user_id": user_id},
        {"$inc": {"balance": amount, "total_credits": amount}},
        upsert=True,
    )
    # Ledger
    await _post_ledger(
        tx_id, user_id, amount, category,
        debit_account=f"external:{provider or 'system'}",
        credit_account=f"user:wallet:{user_id}",
        description=description, provider=provider, reference_id=reference_id,
    )
    # Canonical tx row (compatible with existing /api/wallet/transactions)
    tx = {
        "tx_id": tx_id, "user_id": user_id, "type": "credit", "category": category,
        "amount": float(amount), "description": description, "status": "success",
        "counterparty": counterparty, "provider": provider, "reference_id": reference_id,
        "created_at": _now(),
    }
    await _db.transactions.insert_one(tx)
    tx.pop("_id", None)
    return tx


async def _debit_wallet(user_id: str, amount: float, category: str, description: str,
                       provider: Optional[str] = None,
                       reference_id: Optional[str] = None,
                       counterparty: Optional[str] = None) -> Dict[str, Any]:
    tx_id = _gen_id("tx")
    await _db.wallets.update_one(
        {"user_id": user_id},
        {"$inc": {"balance": -amount, "total_debits": amount}},
        upsert=True,
    )
    await _post_ledger(
        tx_id, user_id, amount, category,
        debit_account=f"user:wallet:{user_id}",
        credit_account=f"external:{provider or 'system'}",
        description=description, provider=provider, reference_id=reference_id,
    )
    tx = {
        "tx_id": tx_id, "user_id": user_id, "type": "debit", "category": category,
        "amount": float(amount), "description": description, "status": "success",
        "counterparty": counterparty, "provider": provider, "reference_id": reference_id,
        "created_at": _now(),
    }
    await _db.transactions.insert_one(tx)
    tx.pop("_id", None)
    return tx


# ---------- Filter helper ----------
def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _build_tx_query(user_id: Optional[str], q: Optional[str], ttype: Optional[str],
                   category: Optional[str], status: Optional[str],
                   d_from: Optional[str], d_to: Optional[str]) -> Dict[str, Any]:
    query: Dict[str, Any] = {}
    if user_id:
        query["user_id"] = user_id
    if ttype and ttype != "all":
        query["type"] = ttype
    if category and category != "all":
        query["category"] = category
    if status and status != "all":
        query["status"] = status
    if q:
        query["$or"] = [
            {"description": {"$regex": q, "$options": "i"}},
            {"counterparty": {"$regex": q, "$options": "i"}},
            {"tx_id": {"$regex": q, "$options": "i"}},
        ]
    df = _parse_iso(d_from); dt_ = _parse_iso(d_to)
    if df or dt_:
        rng: Dict[str, Any] = {}
        if df: rng["$gte"] = df
        if dt_: rng["$lte"] = dt_
        query["created_at"] = rng
    return query


# ============================================================================
#  Attach to FastAPI
# ============================================================================
def attach(api: APIRouter, db, get_current_user, get_current_admin, log_action):
    global _db, _get_current_user, _get_current_admin
    _db = db
    _get_current_user = get_current_user
    _get_current_admin = get_current_admin

    user = APIRouter(prefix="/wallet/v2", tags=["wallet-v2"])
    admin = APIRouter(prefix="/admin/wallet", tags=["wallet-v2-admin"])

    # ----- USER -----
    @user.get("/summary")
    async def summary(u=Depends(get_current_user)):
        uid = u["user_id"]
        w = await db.wallets.find_one({"user_id": uid}, {"_id": 0}) or {}
        # Pending balance = sum of pending withdrawals (Phase 2). Phase 1: 0.
        pending = await db.transactions.aggregate([
            {"$match": {"user_id": uid, "status": "pending", "type": "debit"}},
            {"$group": {"_id": None, "s": {"$sum": "$amount"}}},
        ]).to_list(1)
        deposits = await db.transactions.aggregate([
            {"$match": {"user_id": uid, "type": "credit",
                        "category": {"$in": ["topup", "deposit", "refund"]},
                        "status": "success"}},
            {"$group": {"_id": None, "s": {"$sum": "$amount"}}},
        ]).to_list(1)
        withdrawals = await db.transactions.aggregate([
            {"$match": {"user_id": uid, "type": "debit",
                        "category": {"$in": ["withdraw", "send", "recharge", "billpay", "booking"]},
                        "status": "success"}},
            {"$group": {"_id": None, "s": {"$sum": "$amount"}}},
        ]).to_list(1)
        cashback = await db.transactions.aggregate([
            {"$match": {"user_id": uid, "category": {"$in": ["cashback", "reward", "bonus", "referral"]},
                        "type": "credit", "status": "success"}},
            {"$group": {"_id": None, "s": {"$sum": "$amount"}}},
        ]).to_list(1)
        return {
            "available_balance": float(w.get("balance", 0.0)),
            "pending_balance": float(pending[0]["s"]) if pending else 0.0,
            "total_deposits": float(deposits[0]["s"]) if deposits else 0.0,
            "total_withdrawals": float(withdrawals[0]["s"]) if withdrawals else 0.0,
            "total_earnings": float(cashback[0]["s"]) if cashback else 0.0,
            "currency": w.get("currency", "INR"),
        }

    @user.get("/transactions")
    async def list_txs(
        u=Depends(get_current_user),
        q: Optional[str] = None, type: Optional[str] = None,
        category: Optional[str] = None, status: Optional[str] = None,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        limit: int = 100, skip: int = 0,
    ):
        query = _build_tx_query(u["user_id"], q, type, category, status, date_from, date_to)
        cur = db.transactions.find(query, {"_id": 0, "user_id": 0}).sort("created_at", -1).skip(max(skip, 0)).limit(min(limit, 200))
        items = await cur.to_list(min(limit, 200))
        total = await db.transactions.count_documents(query)
        return {"items": items, "total": total}

    @user.get("/transaction/{tx_id}")
    async def tx_detail(tx_id: str, u=Depends(get_current_user)):
        tx = await db.transactions.find_one({"tx_id": tx_id, "user_id": u["user_id"]}, {"_id": 0})
        if not tx:
            raise HTTPException(404, "Transaction not found")
        ledger = await db.wallet_ledger.find({"tx_id": tx_id}, {"_id": 0}).to_list(10)
        return {"transaction": tx, "ledger": ledger}

    @user.get("/receipt/{tx_id}")
    async def receipt(tx_id: str, u=Depends(get_current_user)):
        tx = await db.transactions.find_one({"tx_id": tx_id, "user_id": u["user_id"]}, {"_id": 0})
        if not tx:
            raise HTTPException(404, "Transaction not found")
        w = await db.wallets.find_one({"user_id": u["user_id"]}, {"_id": 0}) or {}
        pdf = wallet_pdf.build_receipt_pdf(tx, u, float(w.get("balance", 0.0)))
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="MFB_Receipt_{tx_id}.pdf"'})

    @user.get("/statement.pdf")
    async def statement_pdf(u=Depends(get_current_user),
                            date_from: Optional[str] = None,
                            date_to: Optional[str] = None):
        q = _build_tx_query(u["user_id"], None, None, None, "success", date_from, date_to)
        txs = await db.transactions.find(q, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
        s = await _statement_summary(u["user_id"], date_from, date_to)
        label = _period_label(date_from, date_to)
        pdf = wallet_pdf.build_statement_pdf(txs, u, s, label)
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="MFB_Statement.pdf"'})

    @user.get("/statement.xlsx")
    async def statement_xlsx(u=Depends(get_current_user),
                             date_from: Optional[str] = None,
                             date_to: Optional[str] = None):
        q = _build_tx_query(u["user_id"], None, None, None, "success", date_from, date_to)
        txs = await db.transactions.find(q, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
        s = await _statement_summary(u["user_id"], date_from, date_to)
        label = _period_label(date_from, date_to)
        xlsx = wallet_pdf.build_statement_xlsx(txs, u, s, label)
        return Response(content=xlsx,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": 'attachment; filename="MFB_Statement.xlsx"'})

    @user.get("/analytics")
    async def analytics(u=Depends(get_current_user),
                        period: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
                        days: int = 30):
        # bucket by date for last N days
        cutoff = _now() - timedelta(days=days)
        cur = db.transactions.find({"user_id": u["user_id"], "created_at": {"$gte": cutoff},
                                    "status": "success"}, {"_id": 0}).sort("created_at", 1)
        rows = await cur.to_list(2000)
        # Build buckets
        buckets: Dict[str, Dict[str, float]] = defaultdict(lambda: {"credits": 0.0, "debits": 0.0})
        for tx in rows:
            dt = tx["created_at"]
            if period == "daily":
                key = dt.strftime("%Y-%m-%d")
            elif period == "weekly":
                key = dt.strftime("%Y-W%U")
            else:
                key = dt.strftime("%Y-%m")
            if tx["type"] == "credit":
                buckets[key]["credits"] += float(tx["amount"])
            else:
                buckets[key]["debits"] += float(tx["amount"])
        series = [{"period": k, **v} for k, v in sorted(buckets.items())]
        # Category breakdown
        cat_tot: Dict[str, float] = defaultdict(float)
        for tx in rows:
            cat_tot[tx.get("category") or "other"] += float(tx["amount"])
        return {"period": period, "series": series,
                "by_category": [{"category": k, "amount": v} for k, v in sorted(cat_tot.items(), key=lambda x: -x[1])]}

    @user.get("/cashback")
    async def cashback(u=Depends(get_current_user), limit: int = 50):
        items = await db.transactions.find(
            {"user_id": u["user_id"], "type": "credit",
             "category": {"$in": ["cashback", "reward", "bonus", "referral"]}},
            {"_id": 0, "user_id": 0},
        ).sort("created_at", -1).limit(min(limit, 200)).to_list(min(limit, 200))
        total = sum(float(x["amount"]) for x in items)
        return {"items": items, "total": total, "count": len(items)}

    # ----- PAYMENTS -----
    @user.post("/payments/create")
    async def create_payment(body: CreatePaymentReq, u=Depends(get_current_user)):
        if body.amount < MIN_TOPUP:
            raise HTTPException(400, f"Minimum top-up is ₹{MIN_TOPUP:.0f}")
        # Rate limit
        hour_ago = _now() - timedelta(hours=1)
        recent = await db.payment_intents.count_documents(
            {"user_id": u["user_id"], "created_at": {"$gte": hour_ago}})
        if recent >= RATE_LIMIT_TOPUP_PER_HOUR:
            raise HTTPException(429, "Too many payment attempts. Try again in an hour.")

        success_url = body.success_url or f"{FRONTEND_ORIGIN}/wallet?status=success&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = body.cancel_url or f"{FRONTEND_ORIGIN}/wallet?status=cancel"
        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": "inr",
                        "product_data": {"name": "MFB Wallet Top-up",
                                          "description": f"Add ₹{body.amount:.2f} to your My Funding Bank wallet"},
                        "unit_amount": int(round(body.amount * 100)),
                    },
                    "quantity": 1,
                }],
                success_url=success_url,
                cancel_url=cancel_url,
                client_reference_id=u["user_id"],
                metadata={"user_id": u["user_id"], "purpose": "wallet_topup"},
            )
        except Exception as e:
            logger.exception("Stripe create session failed")
            raise HTTPException(502, f"Payment gateway error: {str(e)[:120]}")

        intent_id = _gen_id("pi")
        await db.payment_intents.insert_one({
            "intent_id": intent_id, "session_id": session.id, "user_id": u["user_id"],
            "amount": float(body.amount), "status": "created", "provider": "stripe",
            "created_at": _now(),
        })
        return {"intent_id": intent_id, "session_id": session.id,
                "checkout_url": session.url, "publishable_key": None}

    @user.post("/payments/confirm")
    async def confirm_payment(body: ConfirmPaymentReq, u=Depends(get_current_user)):
        pi = await db.payment_intents.find_one({"session_id": body.session_id, "user_id": u["user_id"]}, {"_id": 0})
        if not pi:
            raise HTTPException(404, "Payment intent not found")
        if pi["status"] == "completed":
            return {"status": "already_credited", "intent_id": pi["intent_id"]}

        try:
            session = stripe.checkout.Session.retrieve(body.session_id)
        except Exception as e:
            raise HTTPException(502, f"Stripe verify failed: {str(e)[:120]}")

        if session.payment_status != "paid":
            await db.payment_intents.update_one(
                {"intent_id": pi["intent_id"]},
                {"$set": {"status": session.payment_status or "unknown",
                          "verified_at": _now()}})
            return {"status": session.payment_status, "intent_id": pi["intent_id"]}

        # Idempotent credit
        tx = await _credit_wallet(
            user_id=u["user_id"], amount=float(pi["amount"]), category="topup",
            description=f"Wallet top-up via Stripe · {pi['session_id'][:18]}",
            provider="stripe", reference_id=session.id,
        )
        await db.payment_intents.update_one(
            {"intent_id": pi["intent_id"]},
            {"$set": {"status": "completed", "completed_at": _now(),
                      "tx_id": tx["tx_id"], "stripe_payment_intent": session.payment_intent}})
        return {"status": "completed", "tx_id": tx["tx_id"], "intent_id": pi["intent_id"]}

    @user.post("/payments/webhook")
    async def webhook(request: Request):
        """Stripe webhook with signature verification. Idempotent via event.id."""
        payload = await request.body()
        sig = request.headers.get("stripe-signature", "")
        if STRIPE_WEBHOOK_SECRET:
            try:
                event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
            except Exception as e:
                raise HTTPException(400, f"Webhook signature failed: {str(e)[:120]}")
        else:
            # Demo mode: accept without verification but log loudly
            try:
                event = json.loads(payload)
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            logger.warning("[wallet.webhook] STRIPE_WEBHOOK_SECRET not set — signature NOT verified")

        event_id = (event.get("id") if isinstance(event, dict) else event.get("id", ""))
        if not event_id:
            return {"ok": True, "skipped": "no_event_id"}
        # Idempotency
        dup = await db.webhook_events.find_one({"event_id": event_id})
        if dup:
            return {"ok": True, "duplicate": True}
        await db.webhook_events.insert_one({
            "event_id": event_id, "provider": "stripe",
            "type": event.get("type") if isinstance(event, dict) else event.get("type", ""),
            "received_at": _now(),
        })
        if (isinstance(event, dict) and event.get("type") == "checkout.session.completed") \
                or (not isinstance(event, dict) and event.get("type") == "checkout.session.completed"):
            obj = (event["data"]["object"] if isinstance(event, dict) else event.data.object)
            session_id = obj.get("id") if isinstance(obj, dict) else obj.id
            pi = await db.payment_intents.find_one({"session_id": session_id})
            if pi and pi["status"] != "completed":
                tx = await _credit_wallet(
                    user_id=pi["user_id"], amount=float(pi["amount"]),
                    category="topup",
                    description=f"Wallet top-up via Stripe · webhook · {session_id[:14]}",
                    provider="stripe", reference_id=session_id,
                )
                await db.payment_intents.update_one(
                    {"intent_id": pi["intent_id"]},
                    {"$set": {"status": "completed", "completed_at": _now(),
                              "tx_id": tx["tx_id"]}})
        return {"ok": True}

    # ----- ADMIN -----
    @admin.get("/transactions")
    async def admin_list(adm=Depends(get_current_admin),
                         q: Optional[str] = None, type: Optional[str] = None,
                         category: Optional[str] = None, status: Optional[str] = None,
                         date_from: Optional[str] = None, date_to: Optional[str] = None,
                         user_id: Optional[str] = None,
                         limit: int = 100, skip: int = 0):
        query = _build_tx_query(user_id, q, type, category, status, date_from, date_to)
        items = await db.transactions.find(query, {"_id": 0}).sort("created_at", -1).skip(max(skip, 0)).limit(min(limit, 500)).to_list(min(limit, 500))
        total = await db.transactions.count_documents(query)
        return {"items": items, "total": total}

    @admin.get("/transactions.csv")
    async def admin_csv(adm=Depends(get_current_admin),
                        q: Optional[str] = None, type: Optional[str] = None,
                        category: Optional[str] = None, status: Optional[str] = None,
                        date_from: Optional[str] = None, date_to: Optional[str] = None,
                        user_id: Optional[str] = None):
        query = _build_tx_query(user_id, q, type, category, status, date_from, date_to)
        items = await db.transactions.find(query, {"_id": 0}).sort("created_at", -1).limit(10000).to_list(10000)
        csv_bytes = wallet_pdf.build_admin_tx_csv(items)
        await log_action(adm["admin_id"], "wallet.csv_export", target="transactions",
                         meta={"count": len(items)})
        return Response(content=csv_bytes, media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="MFB_Transactions.csv"'})

    @admin.get("/payment-logs")
    async def payment_logs(adm=Depends(get_current_admin), limit: int = 100,
                            status: Optional[str] = None):
        q: Dict[str, Any] = {}
        if status and status != "all":
            q["status"] = status
        intents = await db.payment_intents.find(q, {"_id": 0}).sort("created_at", -1).limit(min(limit, 500)).to_list(min(limit, 500))
        webhooks = await db.webhook_events.find({}, {"_id": 0}).sort("received_at", -1).limit(50).to_list(50)
        stats = {
            "intents_total": await db.payment_intents.count_documents({}),
            "intents_completed": await db.payment_intents.count_documents({"status": "completed"}),
            "intents_pending": await db.payment_intents.count_documents({"status": "created"}),
            "webhooks_total": await db.webhook_events.count_documents({}),
        }
        return {"intents": intents, "webhooks": webhooks, "stats": stats}

    @admin.get("/analytics")
    async def admin_analytics(adm=Depends(get_current_admin), days: int = 30):
        cutoff = _now() - timedelta(days=days)
        rows = await db.transactions.find(
            {"created_at": {"$gte": cutoff}, "status": "success"}, {"_id": 0}
        ).to_list(20000)
        buckets: Dict[str, Dict[str, float]] = defaultdict(lambda: {"credits": 0.0, "debits": 0.0, "count": 0})
        for tx in rows:
            key = tx["created_at"].strftime("%Y-%m-%d")
            if tx["type"] == "credit":
                buckets[key]["credits"] += float(tx["amount"])
            else:
                buckets[key]["debits"] += float(tx["amount"])
            buckets[key]["count"] += 1
        series = [{"date": k, **v} for k, v in sorted(buckets.items())]
        return {
            "series": series,
            "totals": {
                "credits": sum(b["credits"] for b in buckets.values()),
                "debits": sum(b["debits"] for b in buckets.values()),
                "count": sum(b["count"] for b in buckets.values()),
            },
        }

    @admin.post("/adjust")
    async def adjust(body: AdminAdjustReq, adm=Depends(get_current_admin)):
        if adm["role"] not in ("super_admin", "admin"):
            raise HTTPException(403, "Only super_admin/admin can adjust wallets")
        if body.amount == 0:
            raise HTTPException(400, "Amount cannot be zero")
        user = await db.users.find_one({"user_id": body.user_id}, {"_id": 0, "user_id": 1})
        if not user:
            raise HTTPException(404, "User not found")
        if body.amount > 0:
            tx = await _credit_wallet(
                body.user_id, float(body.amount), "admin_credit",
                f"Admin adjustment: {body.reason}", provider="admin",
                reference_id=adm["admin_id"])
        else:
            tx = await _debit_wallet(
                body.user_id, float(-body.amount), "admin_debit",
                f"Admin adjustment: {body.reason}", provider="admin",
                reference_id=adm["admin_id"])
        await log_action(adm["admin_id"], "wallet.adjust", target=body.user_id,
                         meta={"amount": body.amount, "reason": body.reason,
                               "tx_id": tx["tx_id"]})
        return {"ok": True, "tx": tx}

    api.include_router(user)
    api.include_router(admin)


# ---------- Helpers ----------
async def _statement_summary(user_id: str, date_from: Optional[str],
                             date_to: Optional[str]) -> Dict[str, float]:
    df = _parse_iso(date_from); dt_ = _parse_iso(date_to)
    match: Dict[str, Any] = {"user_id": user_id, "status": "success"}
    if df or dt_:
        rng: Dict[str, Any] = {}
        if df: rng["$gte"] = df
        if dt_: rng["$lte"] = dt_
        match["created_at"] = rng
    txs = await _db.transactions.find(match, {"_id": 0}).to_list(5000)
    deposits = sum(float(t["amount"]) for t in txs
                   if t["type"] == "credit" and t.get("category") in ("topup", "deposit", "refund"))
    withdrawals = sum(float(t["amount"]) for t in txs
                      if t["type"] == "debit")
    cashback = sum(float(t["amount"]) for t in txs
                   if t.get("category") in ("cashback", "reward", "bonus", "referral"))
    closing = float((await _db.wallets.find_one({"user_id": user_id}, {"_id": 0}) or {}).get("balance", 0))
    # Opening = closing - (credits - debits) in period
    period_credits = sum(float(t["amount"]) for t in txs if t["type"] == "credit")
    period_debits = sum(float(t["amount"]) for t in txs if t["type"] == "debit")
    opening = closing - (period_credits - period_debits)
    return {
        "opening_balance": opening, "closing_balance": closing,
        "total_deposits": deposits, "total_withdrawals": withdrawals,
        "total_cashback": cashback,
    }


def _period_label(date_from: Optional[str], date_to: Optional[str]) -> str:
    df = _parse_iso(date_from); dt_ = _parse_iso(date_to)
    if df and dt_:
        return f"Period: {df.strftime('%d %b %Y')} — {dt_.strftime('%d %b %Y')}"
    if df:
        return f"From: {df.strftime('%d %b %Y')}"
    if dt_:
        return f"Until: {dt_.strftime('%d %b %Y')}"
    return f"All-time (generated {_now().strftime('%d %b %Y')})"
