"""Payments routes — Sprint 8.

Public (auth required):
  GET  /api/payments/config
  POST /api/payments/orders           [Idempotency-Key header]
  GET  /api/payments/orders/{id}
  GET  /api/payments/orders
  POST /api/payments/verify           (client-side signature check helper)

Webhooks (public but HMAC-verified):
  POST /api/payments/webhooks/razorpay

Demo helpers (only usable when demo_mode=True):
  POST /api/payments/demo/capture     (simulates a payment.captured webhook)

Admin console:
  GET  /api/admin/payments/dashboard
  GET  /api/admin/payments/orders
  GET  /api/admin/payments/orders/{id}
  GET  /api/admin/payments/transactions
  GET  /api/admin/payments/refunds
  POST /api/admin/payments/refunds
  POST /api/admin/payments/orders/{id}/retry
  POST /api/admin/payments/reconcile
  GET  /api/admin/payments/reconciliation-status
  GET  /api/admin/payments/reconciliation-history
  GET  /api/admin/payments/audit-log
  GET  /api/admin/payments/config
  PUT  /api/admin/payments/config
"""
from __future__ import annotations
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request

from .engine import PaymentsEngine
from .models import (
    CreateOrderIn, VerifyPaymentIn, RefundIn, ConfigPatch, RetryOrderIn,
    OrderStatus,
)
from .providers.razorpay import RazorpayError
from .reconciliation import ReconciliationJob
from .security import verify_payment_signature
from .webhooks import process_webhook

logger = logging.getLogger("payments.routes")


def attach(app, db, get_current_user, get_current_admin,
           engine: PaymentsEngine, recon: ReconciliationJob):
    user_r = APIRouter(prefix="/api/payments", tags=["payments"])
    admin_r = APIRouter(prefix="/api/admin/payments", tags=["payments-admin"])

    # =============== PUBLIC / USER ===============
    @user_r.get("/config")
    async def get_config(_user=Depends(get_current_user)):
        return await engine.public_config()

    @user_r.post("/orders")
    async def create_order(
        body: CreateOrderIn,
        request: Request,
        idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
        user=Depends(get_current_user),
    ):
        try:
            order, created_new = await engine.create_order(
                user_id=user["user_id"], amount_paise=body.amount_paise,
                currency=body.currency, idempotency_key=idempotency_key,
                method_hint=body.method_hint, notes=body.notes,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        except RazorpayError as e:
            raise HTTPException(e.status, f"payment provider error: {e}")
        # Attach public config for the checkout call
        pub_cfg = await engine.public_config()
        return {
            "order": order, "created_new": created_new,
            "key_id_public": pub_cfg["key_id_public"],
            "provider_order_id": order["provider_order_id"],
            "checkout": {
                "key_id": pub_cfg["key_id_public"],
                "provider_order_id": order["provider_order_id"],
                "amount_paise": order["amount_paise"], "currency": order["currency"],
                "receipt": order["receipt"], "demo": order.get("is_demo", False),
                "mode": pub_cfg["mode"],
            },
        }

    @user_r.get("/orders/{order_id}")
    async def get_order(order_id: str, user=Depends(get_current_user)):
        order = await engine.get_order(order_id, user_id=user["user_id"])
        if not order:
            raise HTTPException(404, "order not found")
        return order

    @user_r.get("/orders")
    async def list_my_orders(
        status: Optional[str] = Query(None),
        limit: int = Query(30, ge=1, le=100),
        skip: int = Query(0, ge=0),
        user=Depends(get_current_user),
    ):
        rows = await engine.list_orders(user_id=user["user_id"],
                                         status=status, limit=limit, skip=skip)
        return {"items": rows, "count": len(rows)}

    @user_r.post("/verify")
    async def verify(body: VerifyPaymentIn, user=Depends(get_current_user)):
        """Client-side signature check (fast UX). Wallet credit ALWAYS happens
        via webhook, not here — this endpoint only tells the mobile app whether
        the checkout succeeded so it can navigate."""
        order = await engine.find_order_by_provider(body.razorpay_order_id)
        if not order:
            raise HTTPException(404, "order not found")
        if order["user_id"] != user["user_id"]:
            raise HTTPException(403, "forbidden")
        # Check signature against server-side secret
        ok = verify_payment_signature(
            body.razorpay_order_id, body.razorpay_payment_id,
            body.razorpay_signature, engine._key_secret,
        )
        # Also mark 'attempted' so the reconciler knows the client tried
        await engine.mark_attempted(order["order_id"], user["user_id"])
        return {"ok": bool(ok),
                "order_id": order["order_id"],
                "status": order["status"],
                "wallet_credit_pending_webhook": True}

    @user_r.post("/demo/capture")
    async def demo_capture(order_id: str = Query(...),
                             method: str = Query("upi"),
                             user=Depends(get_current_user)):
        """Only functional when demo_mode is on. Fires a synthetic
        payment.captured for the specified order (user must own the order)."""
        order = await engine.get_order(order_id, user_id=user["user_id"])
        if not order:
            raise HTTPException(404, "order not found")
        if not engine.demo_mode:
            raise HTTPException(400, "demo mode is disabled — use real checkout")
        try:
            return await engine.demo_simulate_capture(order_id, method=method)
        except ValueError as e:
            raise HTTPException(400, str(e))

    # =============== WEBHOOKS ===============
    webhook_r = APIRouter(prefix="/api/payments/webhooks", tags=["payments-webhooks"])

    @webhook_r.post("/razorpay")
    async def razorpay_webhook(request: Request,
                                 x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature")):
        body = await request.body()
        headers = {k.lower(): v for k, v in request.headers.items()}
        result = await process_webhook(engine, body,
                                        x_razorpay_signature or "",
                                        headers)
        if not result.get("ok"):
            code = result.get("status", 400)
            raise HTTPException(code, result.get("reason", "webhook error"))
        return result

    # =============== ADMIN ===============
    @admin_r.get("/config")
    async def admin_get_config(admin=Depends(get_current_admin)):
        cfg = await engine.public_config()
        # Provide additional flags visible only to admins
        cfg["has_key_secret"] = bool(engine._key_secret and engine._key_secret != "placeholder")
        return cfg

    @admin_r.put("/config")
    async def admin_patch_config(patch: ConfigPatch, admin=Depends(get_current_admin)):
        payload = {k: v for k, v in patch.dict().items() if v is not None}
        return await engine.patch_config(payload,
                                          admin_id=admin.get("admin_id") or "admin")

    @admin_r.get("/dashboard")
    async def admin_dashboard(admin=Depends(get_current_admin)):
        return await engine.dashboard()

    @admin_r.get("/orders")
    async def admin_orders(
        status: Optional[str] = Query(None),
        user_id: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=200),
        skip: int = Query(0, ge=0),
        admin=Depends(get_current_admin),
    ):
        rows = await engine.list_orders(user_id=user_id, status=status,
                                          limit=limit, skip=skip)
        return {"items": rows, "count": len(rows)}

    @admin_r.get("/orders/{order_id}")
    async def admin_order_detail(order_id: str, admin=Depends(get_current_admin)):
        order = await engine.get_order(order_id)
        if not order:
            raise HTTPException(404, "order not found")
        # Attach related tx / refunds
        tx = await engine.db["payments_transactions"].find_one(
            {"order_id": order_id}, {"_id": 0})
        refunds = []
        if tx:
            cur = engine.db["payments_refunds"].find(
                {"payment_id": tx["payment_id"]}, {"_id": 0}).sort("created_at", -1)
            refunds = [d async for d in cur]
            for r in refunds:
                for k in ("created_at", "processed_at"):
                    v = r.get(k)
                    if hasattr(v, "isoformat"):
                        r[k] = v.isoformat()
        if tx:
            for k in ("captured_at", "refunded_at"):
                v = tx.get(k)
                if hasattr(v, "isoformat"):
                    tx[k] = v.isoformat()
        return {"order": order, "transaction": tx, "refunds": refunds}

    @admin_r.get("/transactions")
    async def admin_transactions(
        user_id: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=200),
        skip: int = Query(0, ge=0),
        admin=Depends(get_current_admin),
    ):
        rows = await engine.list_transactions(user_id=user_id, limit=limit, skip=skip)
        return {"items": rows, "count": len(rows)}

    @admin_r.get("/refunds")
    async def admin_refunds(
        limit: int = Query(50, ge=1, le=200),
        skip: int = Query(0, ge=0),
        admin=Depends(get_current_admin),
    ):
        rows = await engine.list_refunds(limit=limit, skip=skip)
        return {"items": rows, "count": len(rows)}

    @admin_r.post("/refunds")
    async def admin_create_refund(body: RefundIn, admin=Depends(get_current_admin)):
        try:
            r = await engine.create_refund(
                admin_id=admin.get("admin_id") or "admin",
                payment_id=body.payment_id,
                amount_paise=body.amount_paise,
                reason=body.reason, notes=body.notes,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        except RazorpayError as e:
            raise HTTPException(e.status, f"provider refund error: {e}")
        # normalize datetimes
        for k in ("created_at", "processed_at"):
            v = r.get(k)
            if hasattr(v, "isoformat"):
                r[k] = v.isoformat()
        return r

    @admin_r.post("/orders/{order_id}/retry")
    async def admin_retry_order(order_id: str, body: RetryOrderIn,
                                  admin=Depends(get_current_admin)):
        try:
            r = await engine.retry_order(order_id,
                                          admin_id=admin.get("admin_id") or "admin",
                                          reason=body.reason)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except RazorpayError as e:
            raise HTTPException(e.status, f"provider error: {e}")
        return r

    @admin_r.post("/reconcile")
    async def admin_reconcile(
        window_hours: int = Query(24, ge=1, le=168),
        admin=Depends(get_current_admin),
    ):
        return await recon.run_once(
            triggered_by=f"admin:{admin.get('admin_id') or 'admin'}",
            window_hours=window_hours)

    @admin_r.get("/reconciliation-status")
    async def admin_reconciliation_status(admin=Depends(get_current_admin)):
        latest = await recon.latest_run()
        return {"latest": latest,
                "interval_sec": recon.interval_sec}

    @admin_r.get("/reconciliation-history")
    async def admin_reconciliation_history(
        limit: int = Query(20, ge=1, le=100),
        admin=Depends(get_current_admin),
    ):
        rows = await recon.recent_runs(limit=limit)
        return {"items": rows, "count": len(rows)}

    @admin_r.get("/audit-log")
    async def admin_audit_log(
        limit: int = Query(100, ge=1, le=500),
        admin=Depends(get_current_admin),
    ):
        rows = await engine.audit_trail(limit=limit)
        return {"items": rows, "count": len(rows)}

    app.include_router(user_r)
    app.include_router(webhook_r)
    app.include_router(admin_r)
    return {"user": user_r, "webhook": webhook_r, "admin": admin_r}
