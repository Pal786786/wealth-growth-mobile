"""Sprint 15.1 — Demo Account Reset & Virtual Wallet Recharge.

Resets a user's DEMO trading account (forex paper trading + copied demo
trades) back to the admin-configured default balance. Real-money wallets
(`wallets`, `transactions`, `wallet_ledger`) are NEVER touched.

What a reset does (atomic per-collection, idempotent):
  1. Close all open demo forex positions (close_reason="demo_reset").
  2. Cancel all pending demo forex orders.
  3. Archive (not delete) all previous demo positions/orders/history under a
     reset_id so a fresh trading session starts clean.
  4. Close + archive copied demo trades (copy_follower_trades) and archive
     copy_daily_stats. Copy relationships (follows, lot multiplier, risk
     settings) stay untouched so future copied trades keep flowing.
  5. Reset forex_balances to `forex_settings.default_demo_balance` (INR).
  6. Record the reset in `demo_reset_history` + a `demo_reset` event in the
     new session's forex_history.

Endpoints:
  POST /api/demo/reset                    (user — resets own demo account)
  GET  /api/demo/reset/history            (user — own reset history)
  POST /api/admin/demo/reset/{user_id}    (admin — resets a user's demo account)
  GET  /api/admin/demo/reset/history      (admin — all resets, ?user_id= filter)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from forex.engine import DEFAULT_DEMO_BALANCE

logger = logging.getLogger("demo_reset")

NOT_ARCHIVED = {"$ne": True}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(d: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in d.items() if k != "_id"}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


async def perform_demo_reset(db, user_id: str, initiator_kind: str,
                             initiator_id: str, initiator_label: str = "") -> Dict[str, Any]:
    """Full demo account reset. Raises ValueError on guard failures."""
    cfg = await db.forex_settings.find_one({"_id": "active"}) or {}
    if not cfg.get("demo_mode", True):
        raise ValueError("Demo reset is only available for demo accounts. Real accounts are never affected.")
    default_balance = float(cfg.get("default_demo_balance", DEFAULT_DEMO_BALANCE))

    now = _now()
    reset_id = f"rst_{uuid.uuid4().hex[:12]}"

    bal_doc = await db.forex_balances.find_one({"user_id": user_id}) or {}
    previous_balance = float(bal_doc.get("balance", 0.0))

    # 1. Close all open demo forex positions at their last marked price.
    open_count = await db.forex_positions.count_documents({"user_id": user_id, "status": "open"})
    if open_count:
        await db.forex_positions.update_many(
            {"user_id": user_id, "status": "open"},
            [{"$set": {
                "status": "closed",
                "close_price": "$current_price",
                "close_reason": "demo_reset",
                "closed_at": now,
            }}],
        )

    # 2. Cancel any pending (non-filled, non-cancelled) demo orders.
    pending_res = await db.forex_orders.update_many(
        {"user_id": user_id, "status": {"$nin": ["filled", "cancelled"]}},
        {"$set": {"status": "cancelled", "cancel_reason": "demo_reset", "cancelled_at": now}},
    )
    orders_cancelled = int(pending_res.modified_count)

    # 3. Archive all previous demo trading data (never delete).
    for coll in ("forex_positions", "forex_orders", "forex_history"):
        await db[coll].update_many(
            {"user_id": user_id, "archived": NOT_ARCHIVED},
            {"$set": {"archived": True, "reset_id": reset_id}},
        )

    # 4. Copy trading — close copied open demo trades flat, archive all copied
    #    trade history + daily stats. Copy relationships remain untouched.
    copy_open = await db.copy_follower_trades.count_documents({"user_id": user_id, "status": "open"})
    if copy_open:
        await db.copy_follower_trades.update_many(
            {"user_id": user_id, "status": "open"},
            [{"$set": {
                "status": "closed",
                "closed_at": now,
                "exit_price": "$entry_price",
                "pnl_usd": 0.0,
                "pnl_pct": 0.0,
                "close_reason": "demo_reset",
            }}],
        )
    await db.copy_follower_trades.update_many(
        {"user_id": user_id, "archived": NOT_ARCHIVED},
        {"$set": {"archived": True, "reset_id": reset_id}},
    )
    await db.copy_daily_stats.update_many(
        {"user_id": user_id, "archived": NOT_ARCHIVED},
        {"$set": {"archived": True, "reset_id": reset_id}},
    )

    # 5. Reset demo wallet balance → equity/margin/free-margin derive from it.
    await db.forex_balances.update_one(
        {"user_id": user_id},
        {"$set": {
            "balance": default_balance,
            "currency": "INR",
            "updated_at": now,
            "session_started_at": now,
            "last_reset_id": reset_id,
        }},
        upsert=True,
    )

    # 6. Record the reset.
    record = {
        "reset_id": reset_id,
        "user_id": user_id,
        "initiated_by": {"kind": initiator_kind, "id": initiator_id, "label": initiator_label},
        "previous_balance": round(previous_balance, 2),
        "new_balance": round(default_balance, 2),
        "currency": "INR",
        "positions_closed": int(open_count),
        "orders_cancelled": orders_cancelled,
        "copy_trades_closed": int(copy_open),
        "ts": now,
    }
    await db.demo_reset_history.insert_one(dict(record))
    # Visible marker at the top of the NEW session's trade history.
    await db.forex_history.insert_one({
        "user_id": user_id,
        "event": "demo_reset",
        "reset_id": reset_id,
        "previous_balance": round(previous_balance, 2),
        "new_balance": round(default_balance, 2),
        "initiated_by": record["initiated_by"],
        "ts": now,
    })
    logger.info("demo reset %s for user %s by %s:%s (%.2f -> %.2f, %d pos, %d copy)",
                reset_id, user_id, initiator_kind, initiator_id,
                previous_balance, default_balance, open_count, copy_open)
    return _serialize(record)


def attach(api: APIRouter, db, get_current_user_fn, get_current_admin_fn, log_action_fn):
    user_router = APIRouter(prefix="/demo", tags=["demo-reset"])
    admin_router = APIRouter(prefix="/admin/demo", tags=["demo-reset-admin"])

    @user_router.post("/reset")
    async def user_demo_reset(user=Depends(get_current_user_fn)):
        try:
            record = await perform_demo_reset(
                db, user["user_id"], "user", user["user_id"],
                user.get("full_name") or user.get("email") or user["user_id"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        return record

    @user_router.get("/reset/history")
    async def user_reset_history(limit: int = 50, user=Depends(get_current_user_fn)):
        cur = db.demo_reset_history.find({"user_id": user["user_id"]}).sort("ts", -1).limit(min(max(limit, 1), 200))
        return {"items": [_serialize(d) async for d in cur]}

    @admin_router.post("/reset/{user_id}")
    async def admin_demo_reset(user_id: str, admin_user=Depends(get_current_admin_fn)):
        target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "user_id": 1, "full_name": 1})
        if not target:
            raise HTTPException(404, "User not found")
        try:
            record = await perform_demo_reset(
                db, user_id, "admin", admin_user["admin_id"],
                admin_user.get("name") or admin_user.get("email") or admin_user["admin_id"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        try:
            await log_action_fn(admin_user["admin_id"], "demo_account_reset", target=user_id,
                                meta={"reset_id": record["reset_id"],
                                      "previous_balance": record["previous_balance"],
                                      "new_balance": record["new_balance"]})
        except Exception:  # pragma: no cover
            pass
        return record

    @admin_router.get("/reset/history")
    async def admin_reset_history(user_id: Optional[str] = None, limit: int = 100,
                                  admin_user=Depends(get_current_admin_fn)):
        q: Dict[str, Any] = {}
        if user_id:
            q["user_id"] = user_id
        cur = db.demo_reset_history.find(q).sort("ts", -1).limit(min(max(limit, 1), 500))
        return {"items": [_serialize(d) async for d in cur]}

    api.include_router(user_router)
    api.include_router(admin_router)
