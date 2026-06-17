"""Insurance Claims Workflow — User submission + Admin approval pipeline.

Flow:
    submitted → under_review → (approved | rejected | info_requested)

Key features:
- User submits claims against active policies (with optional base64-encoded documents)
- Admins review queue with search/filter, see full history and timeline
- Approve / Reject / Request-info actions, each with mandatory admin note
- On approval: claim_amount is credited to user wallet + cashback transaction logged
- Every status change persisted to claim.history[] + admin_audit collection
- User receives in-app notification + push (via security_extras.send_push_logged)
- Role-based: super_admin/admin can approve/reject; finance_manager/support can view
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("mfb.insurance_claims")

_db = None
_get_current_user = None
_get_current_admin = None
_add_tx = None
_log_action = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


CLAIM_STATUSES = ("submitted", "under_review", "approved", "rejected", "info_requested")
CLAIM_TYPES = ("hospitalization", "outpatient", "accident", "theft", "damage", "death", "trip_cancel", "trip_delay", "other")


# ============================================================================
# Schemas
# ============================================================================
class ClaimSubmitReq(BaseModel):
    policy_id: str
    claim_type: str = Field(..., description="hospitalization|outpatient|accident|theft|damage|death|trip_cancel|trip_delay|other")
    claim_amount: float = Field(..., gt=0)
    incident_date: Optional[str] = None
    description: str = Field(..., min_length=10, max_length=2000)
    documents: Optional[List[Dict[str, str]]] = None  # [{name, base64, mime}]


class ClaimDecisionReq(BaseModel):
    admin_note: str = Field(..., min_length=3, max_length=1000)
    approved_amount: Optional[float] = None  # only for "approve"; defaults to claim_amount


class ClaimInfoReq(BaseModel):
    admin_note: str = Field(..., min_length=3, max_length=1000)


# ============================================================================
# Helpers
# ============================================================================
async def _send_status_notification(claim: Dict[str, Any], title: str, body: str, deeplink: str = "/insurance"):
    """Persist in-app notification + best-effort push delivery."""
    user_id = claim["user_id"]
    notif_id = _gid("nf")
    await _db.notifications.insert_one({
        "notif_id": notif_id,
        "user_id": user_id,
        "title": title,
        "body": body,
        "deeplink": deeplink,
        "category": "claim",
        "claim_id": claim["claim_id"],
        "read": False,
        "created_at": _now(),
    })
    # Push (fire-and-forget; security_extras already logs success/failure)
    try:
        import security_extras  # type: ignore
        await security_extras.send_push_logged(
            recipients=[user_id],
            data={
                "title": title,
                "message": body,
                "action_url": deeplink,
                "claim_id": claim["claim_id"],
                "category": "claim",
            },
            batch_id=f"claim-{claim['claim_id']}",
        )
    except Exception as e:
        logger.warning(f"Push notification failed for claim {claim['claim_id']}: {e}")


async def _append_history(claim_id: str, event: str, by: str, by_id: str, note: Optional[str] = None,
                          extra: Optional[Dict[str, Any]] = None):
    entry = {
        "event": event,
        "by": by,  # "user" | "admin"
        "by_id": by_id,
        "note": note,
        "at": _now(),
        **(extra or {}),
    }
    await _db.insurance_claims.update_one(
        {"claim_id": claim_id},
        {"$push": {"history": entry}},
    )


def _stats_pipeline() -> List[Dict[str, Any]]:
    return [
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "amount_sum": {"$sum": "$claim_amount"},
            "approved_payout": {"$sum": {"$cond": [{"$eq": ["$status", "approved"]}, "$approved_amount", 0]}},
        }},
    ]


# ============================================================================
# User Endpoints  ( /api/insurance/claims )
# ============================================================================
def _attach_user_routes(api: APIRouter):
    r = APIRouter(prefix="/insurance/claims", tags=["insurance-claims"])

    @r.post("")
    async def submit_claim(req: ClaimSubmitReq, user: Dict[str, Any] = Depends(_get_current_user)):
        if req.claim_type not in CLAIM_TYPES:
            raise HTTPException(400, f"Invalid claim_type. Allowed: {', '.join(CLAIM_TYPES)}")
        policy = await _db.policies.find_one({"policy_id": req.policy_id, "user_id": user["user_id"]}, {"_id": 0})
        if not policy:
            raise HTTPException(404, "Policy not found or does not belong to you")
        if policy.get("status") != "active":
            raise HTTPException(400, f"Policy status is '{policy.get('status')}'. Only active policies can have claims.")
        # Rate-limit: max 1 pending claim per policy at a time
        existing = await _db.insurance_claims.count_documents({
            "policy_id": req.policy_id,
            "status": {"$in": ["submitted", "under_review", "info_requested"]},
        })
        if existing >= 1:
            raise HTTPException(429, "You already have a pending claim on this policy. Please wait for the decision.")
        if req.claim_amount > float(policy.get("cover") or 0):
            raise HTTPException(400, f"Claim amount exceeds policy cover (₹{policy.get('cover')}).")

        # Compact docs (drop oversized base64 > 200KB each)
        docs_in = []
        for d in (req.documents or [])[:5]:
            b64 = (d.get("base64") or "")
            if len(b64) > 280_000:
                continue
            docs_in.append({
                "name": (d.get("name") or "document")[:80],
                "mime": (d.get("mime") or "application/octet-stream")[:80],
                "base64": b64,
            })

        claim_id = _gid("clm")
        doc = {
            "claim_id": claim_id,
            "policy_id": req.policy_id,
            "plan_name": policy.get("plan_name", ""),
            "plan_type": policy.get("type", "health"),
            "user_id": user["user_id"],
            "user_name": user.get("full_name", ""),
            "user_email": user.get("email", ""),
            "user_mobile": user.get("mobile", ""),
            "claim_type": req.claim_type,
            "claim_amount": float(req.claim_amount),
            "approved_amount": 0.0,
            "currency": "INR",
            "incident_date": req.incident_date or "",
            "description": req.description.strip(),
            "documents": docs_in,
            "status": "submitted",
            "admin_note": "",
            "decided_by_admin_id": None,
            "decided_at": None,
            "created_at": _now(),
            "updated_at": _now(),
            "history": [{
                "event": "submitted",
                "by": "user",
                "by_id": user["user_id"],
                "note": "Claim submitted by policyholder",
                "at": _now(),
            }],
        }
        await _db.insurance_claims.insert_one(doc)
        doc.pop("_id", None)

        # Notify admin team (in-app only — broadcast disabled to avoid spam)
        try:
            await _db.notifications.insert_one({
                "notif_id": _gid("nf"),
                "user_id": "__admin_pool__",  # synthetic — surfaced in admin dashboard widget
                "title": "New Insurance Claim",
                "body": f"{user.get('full_name', 'A user')} filed a {req.claim_type} claim of ₹{req.claim_amount:.0f} on {policy.get('plan_name')}",
                "category": "admin_alert",
                "claim_id": claim_id,
                "read": False,
                "created_at": _now(),
            })
        except Exception:
            pass

        return {"ok": True, "claim_id": claim_id, "status": "submitted", "claim": _slim(doc)}

    @r.get("")
    async def my_claims(user: Dict[str, Any] = Depends(_get_current_user), status: Optional[str] = None, limit: int = 50):
        q: Dict[str, Any] = {"user_id": user["user_id"]}
        if status and status in CLAIM_STATUSES:
            q["status"] = status
        rows = await _db.insurance_claims.find(q, {"_id": 0, "documents": 0}).sort("created_at", -1).limit(min(limit, 100)).to_list(min(limit, 100))
        # Stats for the user
        agg = await _db.insurance_claims.aggregate([
            {"$match": {"user_id": user["user_id"]}},
            *_stats_pipeline(),
        ]).to_list(20)
        stats: Dict[str, Any] = {s: 0 for s in CLAIM_STATUSES}
        approved_payout = 0.0
        for a in agg:
            stats[a["_id"]] = a["count"]
            approved_payout += a.get("approved_payout", 0)
        return {"items": rows, "stats": stats, "total_approved_payout": round(approved_payout, 2)}

    @r.get("/{claim_id}")
    async def claim_detail(claim_id: str, user: Dict[str, Any] = Depends(_get_current_user)):
        doc = await _db.insurance_claims.find_one({"claim_id": claim_id, "user_id": user["user_id"]}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Claim not found")
        # Hide raw base64 in list/detail by default; strip large blobs
        for d in (doc.get("documents") or []):
            if len((d.get("base64") or "")) > 0:
                d["has_file"] = True
                d.pop("base64", None)
        return doc

    api.include_router(r)


def _slim(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Return claim without heavy fields (documents/history) for list/post responses."""
    return {k: v for k, v in doc.items() if k not in ("documents", "history", "_id")}


# ============================================================================
# Admin Endpoints  ( /api/admin/insurance/claims )
# ============================================================================
def _attach_admin_routes(api: APIRouter):
    r = APIRouter(prefix="/admin/insurance", tags=["admin-insurance-claims"])

    def _ensure_view(adm):
        if adm["role"] not in ("super_admin", "admin", "finance_manager", "support_manager"):
            raise HTTPException(403, "Forbidden")

    def _ensure_decide(adm):
        if adm["role"] not in ("super_admin", "admin"):
            raise HTTPException(403, "Only super_admin or admin can approve/reject claims")

    @r.get("/claims")
    async def list_claims(adm=Depends(_get_current_admin), status: Optional[str] = None,
                          plan_type: Optional[str] = None, search: Optional[str] = None,
                          limit: int = 100):
        _ensure_view(adm)
        q: Dict[str, Any] = {}
        if status and status in CLAIM_STATUSES:
            q["status"] = status
        if plan_type:
            q["plan_type"] = plan_type
        if search:
            q["$or"] = [
                {"claim_id": {"$regex": search, "$options": "i"}},
                {"user_name": {"$regex": search, "$options": "i"}},
                {"user_email": {"$regex": search, "$options": "i"}},
                {"user_mobile": {"$regex": search, "$options": "i"}},
                {"plan_name": {"$regex": search, "$options": "i"}},
            ]
        rows = await _db.insurance_claims.find(q, {"_id": 0, "documents": 0, "history": 0}) \
            .sort("created_at", -1).limit(min(limit, 500)).to_list(min(limit, 500))
        return {"items": rows, "total": len(rows)}

    @r.get("/claims/stats")
    async def claims_stats(adm=Depends(_get_current_admin)):
        _ensure_view(adm)
        agg = await _db.insurance_claims.aggregate(_stats_pipeline()).to_list(20)
        by_status: Dict[str, Dict[str, Any]] = {s: {"count": 0, "amount": 0.0, "approved_payout": 0.0} for s in CLAIM_STATUSES}
        for a in agg:
            by_status[a["_id"]] = {
                "count": a["count"],
                "amount": round(a.get("amount_sum", 0), 2),
                "approved_payout": round(a.get("approved_payout", 0), 2),
            }
        total = sum(v["count"] for v in by_status.values())
        approved = by_status.get("approved", {}).get("count", 0)
        rejected = by_status.get("rejected", {}).get("count", 0)
        pending = by_status["submitted"]["count"] + by_status["under_review"]["count"] + by_status["info_requested"]["count"]
        approval_rate = round((approved / (approved + rejected) * 100), 1) if (approved + rejected) > 0 else 0
        return {
            "total": total,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "approval_rate": approval_rate,
            "total_approved_payout": by_status["approved"]["approved_payout"],
            "by_status": by_status,
        }

    @r.get("/claims/{claim_id}")
    async def claim_detail_admin(claim_id: str, adm=Depends(_get_current_admin)):
        _ensure_view(adm)
        doc = await _db.insurance_claims.find_one({"claim_id": claim_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Claim not found")
        # Mark file presence; strip raw base64 from list responses unless ?include_docs=1
        for d in (doc.get("documents") or []):
            if d.get("base64"):
                d["has_file"] = True
        return doc

    @r.get("/claims/{claim_id}/document/{index}")
    async def claim_document(claim_id: str, index: int, adm=Depends(_get_current_admin)):
        """Return a single document base64 — kept separate to avoid bloating list responses."""
        _ensure_view(adm)
        doc = await _db.insurance_claims.find_one({"claim_id": claim_id}, {"_id": 0, "documents": 1})
        if not doc:
            raise HTTPException(404, "Claim not found")
        docs = doc.get("documents") or []
        if index < 0 or index >= len(docs):
            raise HTTPException(404, "Document not found")
        await _log_action(adm["admin_id"], "claim.document.view",
                          target=claim_id, meta={"index": index})
        return docs[index]

    async def _set_status(claim_id: str, new_status: str, adm: Dict[str, Any], note: str,
                          approved_amount: Optional[float] = None) -> Dict[str, Any]:
        doc = await _db.insurance_claims.find_one({"claim_id": claim_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Claim not found")
        if doc["status"] in ("approved", "rejected"):
            raise HTTPException(400, f"Claim is already {doc['status']} and cannot be re-decided")
        update: Dict[str, Any] = {
            "status": new_status,
            "admin_note": note,
            "decided_by_admin_id": adm["admin_id"] if new_status in ("approved", "rejected") else doc.get("decided_by_admin_id"),
            "decided_at": _now() if new_status in ("approved", "rejected") else doc.get("decided_at"),
            "updated_at": _now(),
        }
        if new_status == "approved":
            update["approved_amount"] = float(approved_amount if approved_amount is not None else doc["claim_amount"])
        await _db.insurance_claims.update_one({"claim_id": claim_id}, {"$set": update})
        await _append_history(claim_id, new_status, by="admin", by_id=adm["admin_id"], note=note,
                              extra={"approved_amount": update.get("approved_amount")} if new_status == "approved" else None)
        await _log_action(adm["admin_id"], f"claim.{new_status}",
                          target=claim_id, meta={"note": note, "approved_amount": update.get("approved_amount")})

        # Re-fetch updated claim for downstream side effects
        fresh = await _db.insurance_claims.find_one({"claim_id": claim_id}, {"_id": 0})
        return fresh

    @r.post("/claims/{claim_id}/under-review")
    async def move_to_review(claim_id: str, body: ClaimInfoReq, adm=Depends(_get_current_admin)):
        _ensure_decide(adm)
        claim = await _set_status(claim_id, "under_review", adm, body.admin_note)
        await _send_status_notification(
            claim,
            title="Claim Under Review",
            body=f"Your claim {claim_id} is now being reviewed by our team.",
        )
        return {"ok": True, "claim": _slim(claim)}

    @r.post("/claims/{claim_id}/approve")
    async def approve_claim(claim_id: str, body: ClaimDecisionReq, adm=Depends(_get_current_admin)):
        _ensure_decide(adm)
        claim = await _set_status(claim_id, "approved", adm, body.admin_note, body.approved_amount)
        # Credit the user's wallet with approved amount
        payout = float(claim.get("approved_amount") or 0)
        if payout > 0:
            await _db.wallets.update_one({"user_id": claim["user_id"]}, {"$inc": {"balance": payout}}, upsert=True)
            if _add_tx:
                await _add_tx(claim["user_id"], "credit", "insurance_claim", payout,
                              f"Claim payout: {claim['plan_name']} ({claim['claim_type']})",
                              "success", claim["plan_name"])
        await _send_status_notification(
            claim,
            title="Claim Approved ✅",
            body=f"Your claim of ₹{payout:.0f} has been approved and credited to your wallet.",
        )
        return {"ok": True, "claim": _slim(claim), "payout_credited": payout}

    @r.post("/claims/{claim_id}/reject")
    async def reject_claim(claim_id: str, body: ClaimDecisionReq, adm=Depends(_get_current_admin)):
        _ensure_decide(adm)
        claim = await _set_status(claim_id, "rejected", adm, body.admin_note)
        await _send_status_notification(
            claim,
            title="Claim Rejected",
            body=f"Your claim {claim_id} was rejected. Reason: {body.admin_note[:120]}",
        )
        return {"ok": True, "claim": _slim(claim)}

    @r.post("/claims/{claim_id}/request-info")
    async def request_info(claim_id: str, body: ClaimInfoReq, adm=Depends(_get_current_admin)):
        _ensure_decide(adm)
        claim = await _set_status(claim_id, "info_requested", adm, body.admin_note)
        await _send_status_notification(
            claim,
            title="More Information Needed",
            body=f"We need more details for claim {claim_id}. {body.admin_note[:120]}",
        )
        return {"ok": True, "claim": _slim(claim)}

    api.include_router(r)


# ============================================================================
# Public attach()
# ============================================================================
def attach(api: APIRouter, db, get_current_user_fn, get_current_admin_fn, add_tx_fn, log_action_fn):
    global _db, _get_current_user, _get_current_admin, _add_tx, _log_action
    _db = db
    _get_current_user = get_current_user_fn
    _get_current_admin = get_current_admin_fn
    _add_tx = add_tx_fn
    _log_action = log_action_fn
    _attach_user_routes(api)
    _attach_admin_routes(api)
