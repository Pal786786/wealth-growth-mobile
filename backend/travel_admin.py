"""Travel Cancellation & Refund Workflow.

Flow:
  booking → cancelled (refund_pending) → refund_approved → refund_processed
                                       └→ refund_rejected

- Admin can cancel any booking (Support/Admin/Super)
- Refund engine: 100/90/75/50/0% presets + manual override
- Two-step refund: pending → approved → processed (auto wallet credit)
- Audit trail: booking.cancelled, refund.approved, refund.rejected, refund.processed
- User notifications on each state change (in-app + push)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("mfb.travel_admin")

_db = None
_get_current_admin = None
_get_current_user = None
_add_tx = None
_log_action = None


def _now():
    return datetime.now(timezone.utc)


def _gid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


BOOKING_STATUSES = ("booked", "confirmed", "completed", "cancelled", "pending")
REFUND_STATUSES = ("none", "pending", "approved", "rejected", "processed")
REFUND_PRESETS = {"full": 100, "high": 90, "partial_75": 75, "partial_50": 50, "none": 0}


# ============================================================================
# Schemas
# ============================================================================
class AdminCancelReq(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    refund_preset: Optional[str] = Field("high", description="full|high|partial_75|partial_50|none")
    refund_amount_override: Optional[float] = None  # if set, overrides preset


class RefundDecisionReq(BaseModel):
    admin_note: str = Field(..., min_length=3, max_length=500)
    refund_amount_override: Optional[float] = None  # only honored on approve


# ============================================================================
# Helpers
# ============================================================================
async def _notify(user_id: str, title: str, body: str, deeplink: str = "/travel"):
    await _db.notifications.insert_one({
        "notif_id": _gid("nf"),
        "user_id": user_id,
        "title": title,
        "body": body,
        "deeplink": deeplink,
        "category": "travel_refund",
        "read": False,
        "created_at": _now(),
    })
    try:
        import security_extras  # type: ignore
        await security_extras.send_push_logged(
            recipients=[user_id],
            data={"title": title, "message": body, "action_url": deeplink, "category": "travel_refund"},
            batch_id=f"travel-{_gid('p')}",
        )
    except Exception as e:
        logger.warning(f"Travel notification push failed: {e}")


async def _append_history(booking_id: str, event: str, by: str, by_id: str,
                          note: Optional[str] = None, extra: Optional[Dict[str, Any]] = None):
    entry = {"event": event, "by": by, "by_id": by_id, "note": note, "at": _now()}
    if extra:
        entry.update(extra)
    await _db.bookings.update_one({"booking_id": booking_id}, {"$push": {"history": entry}})


# ============================================================================
# Admin Endpoints  ( /api/admin/travel )
# ============================================================================
def _attach_admin_routes(api: APIRouter):
    r = APIRouter(prefix="/admin/travel", tags=["admin-travel"])

    def _ensure_view(adm):
        if adm["role"] not in ("super_admin", "admin", "finance_manager", "support_manager"):
            raise HTTPException(403, "Forbidden")

    def _ensure_cancel(adm):
        # Support can request cancellation. Admin & super_admin can also cancel.
        if adm["role"] not in ("super_admin", "admin", "support_manager"):
            raise HTTPException(403, "Only support/admin/super_admin can cancel bookings")

    def _ensure_refund_decision(adm):
        # Finance & admin & super_admin can approve / reject refunds
        if adm["role"] not in ("super_admin", "admin", "finance_manager"):
            raise HTTPException(403, "Only finance/admin/super_admin can approve refunds")

    @r.get("/bookings")
    async def list_bookings(adm=Depends(_get_current_admin),
                            status: Optional[str] = None,
                            booking_type: Optional[str] = None,
                            refund_status: Optional[str] = None,
                            search: Optional[str] = None,
                            limit: int = 200):
        _ensure_view(adm)
        q: Dict[str, Any] = {}
        if status:
            q["status"] = status
        if booking_type:
            q["booking_type"] = booking_type
        if refund_status and refund_status != "none":
            q["refund_status"] = refund_status
        if search:
            q["$or"] = [
                {"booking_id": {"$regex": search, "$options": "i"}},
                {"user_id": {"$regex": search, "$options": "i"}},
                {"user_name": {"$regex": search, "$options": "i"}},
                {"user_mobile": {"$regex": search, "$options": "i"}},
                {"title": {"$regex": search, "$options": "i"}},
            ]
        rows = await _db.bookings.find(q, {"_id": 0}).sort("created_at", -1).limit(min(limit, 500)).to_list(min(limit, 500))
        # Enrich with user_name / user_mobile if not stored
        user_ids = list({b.get("user_id") for b in rows if b.get("user_id") and not b.get("user_name")})
        if user_ids:
            users = await _db.users.find({"user_id": {"$in": user_ids}},
                                         {"_id": 0, "user_id": 1, "full_name": 1, "mobile": 1, "email": 1}).to_list(500)
            user_map = {u["user_id"]: u for u in users}
            for b in rows:
                if not b.get("user_name"):
                    u = user_map.get(b.get("user_id"), {})
                    b["user_name"] = u.get("full_name")
                    b["user_mobile"] = u.get("mobile")
                    b["user_email"] = u.get("email")
        return {"items": rows, "total": len(rows)}

    @r.get("/analytics")
    async def analytics(adm=Depends(_get_current_admin)):
        _ensure_view(adm)
        total = await _db.bookings.count_documents({})
        cancelled = await _db.bookings.count_documents({"status": "cancelled"})
        pending_refunds = await _db.bookings.count_documents({"refund_status": "pending"})
        approved_refunds = await _db.bookings.count_documents({"refund_status": "approved"})
        processed_refunds = await _db.bookings.count_documents({"refund_status": "processed"})
        # Sum of paid refunds
        paid_agg = await _db.bookings.aggregate([
            {"$match": {"refund_status": "processed"}},
            {"$group": {"_id": None, "total": {"$sum": "$refund_amount"}}},
        ]).to_list(1)
        paid = round(paid_agg[0]["total"], 2) if paid_agg else 0
        pending_amt_agg = await _db.bookings.aggregate([
            {"$match": {"refund_status": {"$in": ["pending", "approved"]}}},
            {"$group": {"_id": None, "total": {"$sum": "$refund_amount"}}},
        ]).to_list(1)
        pending_amount = round(pending_amt_agg[0]["total"], 2) if pending_amt_agg else 0
        # Booking type breakdown
        by_type_agg = await _db.bookings.aggregate([
            {"$group": {"_id": "$booking_type", "count": {"$sum": 1},
                        "revenue": {"$sum": "$amount"}}},
            {"$sort": {"count": -1}},
        ]).to_list(20)
        by_type = [{"type": (b["_id"] or "unknown"), "count": b["count"], "revenue": round(b.get("revenue", 0), 2)} for b in by_type_agg]
        # Recent cancellations
        recent = await _db.bookings.find({"status": "cancelled"}, {"_id": 0, "history": 0}).sort("cancelled_at", -1).limit(5).to_list(5)
        return {
            "total_bookings": total,
            "cancelled_bookings": cancelled,
            "active_bookings": total - cancelled,
            "pending_refunds": pending_refunds,
            "approved_refunds": approved_refunds,
            "processed_refunds": processed_refunds,
            "refund_amount_paid": paid,
            "refund_amount_in_pipeline": pending_amount,
            "by_type": by_type,
            "recent_cancellations": recent,
        }

    @r.get("/bookings/{booking_id}")
    async def booking_detail(booking_id: str, adm=Depends(_get_current_admin)):
        _ensure_view(adm)
        bk = await _db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
        if not bk:
            raise HTTPException(404, "Booking not found")
        if not bk.get("user_name"):
            u = await _db.users.find_one({"user_id": bk.get("user_id")},
                                         {"_id": 0, "full_name": 1, "mobile": 1, "email": 1})
            if u:
                bk["user_name"] = u.get("full_name")
                bk["user_mobile"] = u.get("mobile")
                bk["user_email"] = u.get("email")
        return bk

    def _compute_refund_amount(booking_amount: float, preset: Optional[str],
                               override: Optional[float]) -> tuple[float, int]:
        """Returns (amount, pct)."""
        if override is not None:
            amt = max(0.0, min(float(override), float(booking_amount)))
            pct = round((amt / booking_amount) * 100) if booking_amount > 0 else 0
            return round(amt, 2), pct
        p = (preset or "high").lower()
        pct = REFUND_PRESETS.get(p, REFUND_PRESETS["high"])
        return round(booking_amount * (pct / 100.0), 2), pct

    @r.post("/bookings/{booking_id}/cancel")
    async def admin_cancel(booking_id: str, body: AdminCancelReq, adm=Depends(_get_current_admin)):
        _ensure_cancel(adm)
        bk = await _db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
        if not bk:
            raise HTTPException(404, "Booking not found")
        if bk.get("status") == "cancelled":
            raise HTTPException(400, "Booking is already cancelled")
        if bk.get("status") == "completed":
            raise HTTPException(400, "Cannot cancel a completed booking")

        refund_amount, refund_pct = _compute_refund_amount(
            float(bk.get("amount") or 0), body.refund_preset, body.refund_amount_override,
        )
        update = {
            "status": "cancelled",
            "cancelled_at": _now(),
            "cancelled_by_admin_id": adm["admin_id"],
            "cancel_reason": body.reason,
            "refund_amount": refund_amount,
            "refund_pct": refund_pct,
            "refund_preset": body.refund_preset,
            "refund_status": "pending" if refund_amount > 0 else "none",
            "updated_at": _now(),
        }
        await _db.bookings.update_one({"booking_id": booking_id}, {"$set": update})
        await _append_history(booking_id, "booking.cancelled", by="admin", by_id=adm["admin_id"],
                              note=body.reason,
                              extra={"refund_amount": refund_amount, "refund_pct": refund_pct})
        await _log_action(adm["admin_id"], "booking.cancelled", target=booking_id,
                          meta={"reason": body.reason, "refund_amount": refund_amount, "refund_pct": refund_pct})

        # User notification
        body_msg = (
            f"Your {bk.get('booking_type','booking')} '{bk.get('title','')}' has been cancelled. "
            f"Refund of ₹{refund_amount:.0f} ({refund_pct}%) is pending approval."
            if refund_amount > 0 else
            f"Your {bk.get('booking_type','booking')} '{bk.get('title','')}' has been cancelled. No refund is applicable per policy."
        )
        await _notify(bk["user_id"], "Booking Cancelled", body_msg)
        return {"ok": True, "booking_id": booking_id, "refund_amount": refund_amount, "refund_pct": refund_pct,
                "refund_status": update["refund_status"]}

    @r.post("/bookings/{booking_id}/refund/approve")
    async def approve_refund(booking_id: str, body: RefundDecisionReq, adm=Depends(_get_current_admin)):
        _ensure_refund_decision(adm)
        bk = await _db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
        if not bk:
            raise HTTPException(404, "Booking not found")
        if bk.get("refund_status") not in ("pending",):
            raise HTTPException(400, f"Refund cannot be approved from status '{bk.get('refund_status')}'")

        new_amount = bk.get("refund_amount", 0)
        if body.refund_amount_override is not None:
            new_amount = max(0.0, min(float(body.refund_amount_override), float(bk.get("amount") or 0)))
            new_amount = round(new_amount, 2)
        pct = round((new_amount / bk["amount"]) * 100) if bk.get("amount") else 0

        await _db.bookings.update_one({"booking_id": booking_id}, {"$set": {
            "refund_status": "approved",
            "refund_amount": new_amount,
            "refund_pct": pct,
            "refund_approved_by": adm["admin_id"],
            "refund_approved_at": _now(),
            "refund_admin_note": body.admin_note,
            "updated_at": _now(),
        }})
        await _append_history(booking_id, "refund.approved", by="admin", by_id=adm["admin_id"],
                              note=body.admin_note, extra={"refund_amount": new_amount})
        await _log_action(adm["admin_id"], "refund.approved", target=booking_id,
                          meta={"amount": new_amount, "note": body.admin_note})
        await _notify(bk["user_id"], "Refund Approved",
                      f"Your refund of ₹{new_amount:.0f} for '{bk.get('title','')}' has been approved and will be credited shortly.")
        return {"ok": True, "refund_status": "approved", "refund_amount": new_amount}

    @r.post("/bookings/{booking_id}/refund/reject")
    async def reject_refund(booking_id: str, body: RefundDecisionReq, adm=Depends(_get_current_admin)):
        _ensure_refund_decision(adm)
        bk = await _db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
        if not bk:
            raise HTTPException(404, "Booking not found")
        if bk.get("refund_status") not in ("pending", "approved"):
            raise HTTPException(400, f"Refund cannot be rejected from status '{bk.get('refund_status')}'")
        await _db.bookings.update_one({"booking_id": booking_id}, {"$set": {
            "refund_status": "rejected",
            "refund_rejected_by": adm["admin_id"],
            "refund_rejected_at": _now(),
            "refund_admin_note": body.admin_note,
            "updated_at": _now(),
        }})
        await _append_history(booking_id, "refund.rejected", by="admin", by_id=adm["admin_id"], note=body.admin_note)
        await _log_action(adm["admin_id"], "refund.rejected", target=booking_id, meta={"note": body.admin_note})
        await _notify(bk["user_id"], "Refund Rejected",
                      f"Your refund request for '{bk.get('title','')}' was rejected. Reason: {body.admin_note[:120]}")
        return {"ok": True, "refund_status": "rejected"}

    @r.post("/bookings/{booking_id}/refund/process")
    async def process_refund(booking_id: str, adm=Depends(_get_current_admin)):
        """Final step — credits the wallet and marks refund processed."""
        _ensure_refund_decision(adm)
        bk = await _db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
        if not bk:
            raise HTTPException(404, "Booking not found")
        if bk.get("refund_status") != "approved":
            raise HTTPException(400, "Only approved refunds can be processed")
        amt = float(bk.get("refund_amount") or 0)
        if amt <= 0:
            raise HTTPException(400, "Refund amount is zero")

        # Credit wallet
        await _db.wallets.update_one({"user_id": bk["user_id"]}, {"$inc": {"balance": amt}}, upsert=True)
        if _add_tx:
            await _add_tx(bk["user_id"], "credit", "refund", amt,
                          f"Refund: {bk.get('title','booking')} ({bk.get('refund_pct',0)}%)",
                          "success", bk.get("title", "Refund"))
        await _db.bookings.update_one({"booking_id": booking_id}, {"$set": {
            "refund_status": "processed",
            "refund_processed_by": adm["admin_id"],
            "refund_processed_at": _now(),
            "updated_at": _now(),
        }})
        await _append_history(booking_id, "refund.processed", by="admin", by_id=adm["admin_id"],
                              note="Wallet credited", extra={"amount": amt})
        await _log_action(adm["admin_id"], "refund.processed", target=booking_id, meta={"amount": amt})
        await _log_action(adm["admin_id"], "wallet.credit", target=bk["user_id"],
                          meta={"amount": amt, "reason": f"refund:{booking_id}"})
        await _notify(bk["user_id"], "Refund Credited ✅",
                      f"₹{amt:.0f} has been credited to your MFB Wallet for '{bk.get('title','')}'.")
        return {"ok": True, "refund_status": "processed", "credited": amt}

    api.include_router(r)


# ============================================================================
# User Endpoints (extra detail/history)
# ============================================================================
def _attach_user_routes(api: APIRouter):
    r = APIRouter(prefix="/travel/bookings", tags=["travel-user"])

    @r.get("/{booking_id}")
    async def my_booking_detail(booking_id: str, user: Dict[str, Any] = Depends(_get_current_user)):
        bk = await _db.bookings.find_one(
            {"booking_id": booking_id, "user_id": user["user_id"]},
            {"_id": 0, "user_id": 0},
        )
        if not bk:
            raise HTTPException(404, "Booking not found")
        return bk

    api.include_router(r)


def attach(api: APIRouter, db, get_current_user_fn, get_current_admin_fn, add_tx_fn, log_action_fn):
    global _db, _get_current_user, _get_current_admin, _add_tx, _log_action
    _db = db
    _get_current_user = get_current_user_fn
    _get_current_admin = get_current_admin_fn
    _add_tx = add_tx_fn
    _log_action = log_action_fn
    _attach_admin_routes(api)
    _attach_user_routes(api)
