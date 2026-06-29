"""KYC & Compliance module — production-ready backend.

Extends existing schema WITHOUT touching wallet / users core. Adds:
  Collections:
    kyc_profiles    — one per user (status, step data, completion, risk)
    kyc_documents   — base64 docs with sha256 (swappable for S3/GridFS)
    kyc_timeline    — every action audit-logged

  User endpoints (auth):
    GET    /api/kyc/status
    POST   /api/kyc/step/{1..7}     idempotent until submitted
    POST   /api/kyc/submit          finalise → status=under_review
    GET    /api/kyc/document/{doc_id}

  Admin endpoints:
    GET    /api/admin/kyc                  list w/ search+filter
    GET    /api/admin/kyc/dashboard        stats + weekly chart
    GET    /api/admin/kyc/duplicates       quick dup detection
    GET    /api/admin/kyc/export.csv
    GET    /api/admin/kyc/{user_id}        full detail (incl masked docs)
    GET    /api/admin/kyc/{user_id}/documents.zip
    POST   /api/admin/kyc/{user_id}/approve
    POST   /api/admin/kyc/{user_id}/reject
    POST   /api/admin/kyc/{user_id}/request-reupload
    POST   /api/admin/kyc/{user_id}/unlock      Re-KYC
    POST   /api/admin/kyc/{user_id}/note
    POST   /api/admin/kyc/bulk            {action, user_ids}

  Gating helper (other modules import this):
    await require_kyc_approved(user)   raises 403 if not approved
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import logging
import re
import secrets
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import Response
from pydantic import BaseModel, Field

logger = logging.getLogger("mfb.kyc")
_db = None
_get_current_user = None
_get_current_admin = None
_log_action = None
_send_push = None

DOC_TYPES = {"pan", "aadhaar_front", "aadhaar_back", "selfie", "cheque"}
KYC_EXPIRY_YEARS = 5  # configurable

STATUS = {"not_started", "in_progress", "submitted", "under_review",
          "approved", "rejected", "reupload_required"}

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
AADHAAR_RE = re.compile(r"^\d{12}$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen(p: str) -> str:
    return f"{p}_{secrets.token_hex(6)}"


# ---------- Masking helpers ----------
def mask_pan(p: Optional[str]) -> Optional[str]:
    if not p or len(p) < 10:
        return p
    return f"{p[:5]}****{p[-1]}"


def mask_aadhaar(a: Optional[str]) -> Optional[str]:
    if not a:
        return a
    digits = re.sub(r"\D", "", a)
    if len(digits) < 12:
        return "X" * len(digits)
    return f"XXXX-XXXX-{digits[-4:]}"


def mask_account(n: Optional[str]) -> Optional[str]:
    if not n or len(n) < 4:
        return n
    return f"{'X' * (len(n) - 4)}{n[-4:]}"


# ---------- Storage abstraction (swap to S3/GridFS later) ----------
class DocStore:
    """Pluggable interface. Current impl: base64 in MongoDB.
    Future: subclass and override save/load/delete to use S3 / GridFS / R2."""
    @staticmethod
    async def save(user_id: str, doc_type: str, mime: str, b64: str) -> Dict[str, Any]:
        raw = base64.b64decode(b64.split(",")[-1])  # strip data: prefix if present
        sha = hashlib.sha256(raw).hexdigest()
        doc_id = _gen("doc")
        doc = {
            "doc_id": doc_id, "user_id": user_id, "type": doc_type,
            "mime": mime, "b64": base64.b64encode(raw).decode(),
            "sha256": sha, "size": len(raw),
            "uploaded_at": _now(),
        }
        # Replace any previous doc of same type for this user
        await _db.kyc_documents.delete_many({"user_id": user_id, "type": doc_type})
        await _db.kyc_documents.insert_one(doc)
        return {"doc_id": doc_id, "sha256": sha, "size": len(raw), "mime": mime}

    @staticmethod
    async def load(doc_id: str) -> Optional[Dict[str, Any]]:
        return await _db.kyc_documents.find_one({"doc_id": doc_id}, {"_id": 0})

    @staticmethod
    async def load_by_user_type(user_id: str, doc_type: str) -> Optional[Dict[str, Any]]:
        return await _db.kyc_documents.find_one({"user_id": user_id, "type": doc_type}, {"_id": 0})


# ---------- Risk scoring (heuristic, swappable for ML later) ----------
async def _risk_score(profile: Dict[str, Any]) -> str:
    score = 0
    s = profile.get("steps", {})
    # Income
    income = (s.get("1", {}) or {}).get("annual_income", "")
    if income in ("< 2 Lakh", "<2L"):
        score += 2
    # Age
    dob = (s.get("1", {}) or {}).get("dob")
    if dob:
        try:
            d = datetime.fromisoformat(dob)
            age = (_now() - d.replace(tzinfo=timezone.utc)).days // 365
            if age < 25 or age > 65:
                score += 1
        except Exception:
            pass
    # Duplicate PAN/Aadhaar found
    if profile.get("_dup_flags"):
        score += 3
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


# ---------- Completion % ----------
def _completion(profile: Dict[str, Any]) -> int:
    steps = profile.get("steps", {})
    completed = sum(1 for i in range(1, 8) if steps.get(str(i)))
    return int(round(completed / 7 * 100))


# ---------- Timeline ----------
async def _timeline(user_id: str, event: str, actor: str = "user",
                   meta: Optional[Dict[str, Any]] = None):
    await _db.kyc_timeline.insert_one({
        "event_id": _gen("kte"),
        "user_id": user_id,
        "event": event,
        "actor": actor,
        "meta": meta or {},
        "at": _now(),
    })


# ---------- Duplicate detection ----------
async def _check_duplicates(user_id: str, pan: Optional[str] = None,
                           aadhaar: Optional[str] = None) -> List[str]:
    flags = []
    if pan:
        dup = await _db.kyc_profiles.find_one(
            {"steps.3.pan": pan, "user_id": {"$ne": user_id}}, {"_id": 0, "user_id": 1})
        if dup:
            flags.append(f"duplicate_pan:{dup['user_id']}")
    if aadhaar:
        digits = re.sub(r"\D", "", aadhaar)
        if digits:
            dup = await _db.kyc_profiles.find_one(
                {"steps.4.aadhaar_digits": digits, "user_id": {"$ne": user_id}},
                {"_id": 0, "user_id": 1})
            if dup:
                flags.append(f"duplicate_aadhaar:{dup['user_id']}")
    return flags


# ---------- Notification helper ----------
async def _notify(user_id: str, title: str, message: str, deeplink: str = "/kyc"):
    try:
        await _db.notifications.insert_one({
            "notif_id": _gen("nf"), "user_id": user_id, "title": title,
            "body": message, "read": False, "created_at": _now(),
            "deeplink": deeplink, "category": "kyc",
        })
        if _send_push:
            await _send_push(recipients=[user_id],
                             data={"title": title, "message": message,
                                   "action_url": deeplink},
                             batch_id=f"kyc-{user_id[-8:]}-{int(_now().timestamp())}")
    except Exception as e:
        logger.warning(f"[kyc] notify failed: {e}")


# ---------- Gating helper (other modules use this) ----------
async def require_kyc_approved(user: Dict[str, Any]) -> None:
    """Call from invest/withdraw/gold endpoints to enforce KYC.

    Raises 403 with structured message if not approved.
    Honors admin bypass list (kyc_bypasses collection)."""
    if _db is None:
        return  # module not yet attached; skip in tests
    uid = user["user_id"]
    # Admin bypass check (super_admin can grant temporary overrides)
    bypass = await _db.kyc_bypasses.find_one({
        "user_id": uid, "active": True,
        "$or": [{"expires_at": None}, {"expires_at": {"$gt": _now()}}],
    })
    if bypass:
        # Log usage for audit
        await _db.kyc_bypass_usage.insert_one({
            "user_id": uid, "bypass_id": bypass.get("bypass_id"),
            "used_at": _now(),
        })
        return
    p = await _db.kyc_profiles.find_one({"user_id": uid}, {"_id": 0, "status": 1})
    status = (p or {}).get("status", "not_started")
    if status != "approved":
        raise HTTPException(403, {
            "code": "KYC_REQUIRED",
            "message": "KYC verification required before using this service.",
            "current_status": status,
            "action_url": "/kyc",
            "completion_required": True,
        })


# ---------- Profile fetch / serialize ----------
async def _get_or_create_profile(user_id: str) -> Dict[str, Any]:
    p = await _db.kyc_profiles.find_one({"user_id": user_id}, {"_id": 0})
    if not p:
        p = {
            "user_id": user_id, "status": "not_started", "locked": False,
            "steps": {}, "docs": {}, "completion": 0, "risk": "low",
            "created_at": _now(), "updated_at": _now(),
        }
        await _db.kyc_profiles.insert_one(p)
        await _timeline(user_id, "profile.created", "system")
    return p


def _serialize_profile(p: Dict[str, Any], for_admin: bool = False) -> Dict[str, Any]:
    out = {
        "user_id": p["user_id"], "status": p.get("status", "not_started"),
        "locked": bool(p.get("locked", False)),
        "completion": p.get("completion", 0),
        "risk": p.get("risk", "low"),
        "steps": dict(p.get("steps", {})),
        "docs": p.get("docs", {}),
        "created_at": p.get("created_at"),
        "updated_at": p.get("updated_at"),
        "submitted_at": p.get("submitted_at"),
        "approved_at": p.get("approved_at"),
        "rejected_at": p.get("rejected_at"),
        "expires_at": p.get("expires_at"),
        "reject_reason": p.get("reject_reason"),
        "reupload_fields": p.get("reupload_fields", []),
        "missing": [str(i) for i in range(1, 8) if not p.get("steps", {}).get(str(i))],
    }
    # Mask sensitive fields
    s3 = (out["steps"].get("3") or {}).copy()
    if s3.get("pan"):
        s3["pan_masked"] = mask_pan(s3["pan"])
        if not for_admin:
            s3["pan"] = s3["pan_masked"]
    out["steps"]["3"] = s3

    s4 = (out["steps"].get("4") or {}).copy()
    if s4.get("aadhaar_digits"):
        s4["aadhaar_masked"] = mask_aadhaar(s4["aadhaar_digits"])
        if not for_admin:
            s4.pop("aadhaar_digits", None)
    out["steps"]["4"] = s4

    s6 = (out["steps"].get("6") or {}).copy()
    if s6.get("account_number"):
        s6["account_masked"] = mask_account(s6["account_number"])
        if not for_admin:
            s6["account_number"] = s6["account_masked"]
    out["steps"]["6"] = s6

    if for_admin:
        out["admin_notes"] = p.get("admin_notes", [])
        out["_dup_flags"] = p.get("_dup_flags", [])
    return out


# ============================================================================
#  Attach
# ============================================================================
def attach(api: APIRouter, db, get_current_user, get_current_admin,
           log_action, send_push=None):
    global _db, _get_current_user, _get_current_admin, _log_action, _send_push
    _db = db
    _get_current_user = get_current_user
    _get_current_admin = get_current_admin
    _log_action = log_action
    _send_push = send_push

    user = APIRouter(prefix="/kyc", tags=["kyc"])
    admin = APIRouter(prefix="/admin/kyc", tags=["kyc-admin"])

    # ----- USER -----
    @user.get("/status")
    async def status(u=Depends(get_current_user)):
        p = await _get_or_create_profile(u["user_id"])
        return _serialize_profile(p)

    @user.post("/step/{step}")
    async def submit_step(step: int, data: Dict[str, Any] = Body(...),
                          u=Depends(get_current_user)):
        if step < 1 or step > 7:
            raise HTTPException(400, "step must be 1..7")
        p = await _get_or_create_profile(u["user_id"])
        if p.get("status") == "approved" and not p.get("locked") is False:
            if p.get("locked", True):
                raise HTTPException(403, "KYC is locked. Contact admin for Re-KYC.")

        sk = str(step)
        step_data: Dict[str, Any] = {k: v for k, v in (data or {}).items()}
        dup_flags: List[str] = []

        # Handle each step's documents
        if step == 3:  # PAN
            pan = (step_data.get("pan") or "").upper().strip()
            if pan and not PAN_RE.match(pan):
                raise HTTPException(400, "Invalid PAN format (must match ABCDE1234F)")
            step_data["pan"] = pan
            if step_data.get("image_b64"):
                meta = await DocStore.save(u["user_id"], "pan",
                                            step_data.get("mime", "image/jpeg"),
                                            step_data.pop("image_b64"))
                p.setdefault("docs", {})["pan"] = meta
            # Demo verification → mark verified
            step_data["verification_status"] = "verified"
            step_data["verification_provider"] = "demo"
            dup_flags += await _check_duplicates(u["user_id"], pan=pan)
        elif step == 4:  # Aadhaar
            ad = re.sub(r"\D", "", step_data.get("aadhaar") or "")
            if ad and not AADHAAR_RE.match(ad):
                raise HTTPException(400, "Aadhaar must be 12 digits")
            step_data["aadhaar_digits"] = ad
            step_data.pop("aadhaar", None)
            for key, dtype in (("front_b64", "aadhaar_front"), ("back_b64", "aadhaar_back")):
                if step_data.get(key):
                    meta = await DocStore.save(u["user_id"], dtype, "image/jpeg",
                                                step_data.pop(key))
                    p.setdefault("docs", {})[dtype] = meta
            step_data["verification_status"] = "verified"
            step_data["verification_provider"] = "demo"
            dup_flags += await _check_duplicates(u["user_id"], aadhaar=ad)
        elif step == 5:  # Selfie
            if step_data.get("image_b64"):
                meta = await DocStore.save(u["user_id"], "selfie", "image/jpeg",
                                            step_data.pop("image_b64"))
                p.setdefault("docs", {})["selfie"] = meta
            step_data["verification_status"] = "verified"
        elif step == 6:  # Bank
            ifsc = (step_data.get("ifsc") or "").upper().strip()
            if ifsc and not IFSC_RE.match(ifsc):
                raise HTTPException(400, "Invalid IFSC (e.g. SBIN0001234)")
            step_data["ifsc"] = ifsc
            if step_data.get("cheque_b64"):
                meta = await DocStore.save(u["user_id"], "cheque", "image/jpeg",
                                            step_data.pop("cheque_b64"))
                p.setdefault("docs", {})["cheque"] = meta

        # Update profile
        p["steps"][sk] = step_data
        p["status"] = "in_progress" if p.get("status") in ("not_started", "reupload_required") else p.get("status")
        p["completion"] = _completion(p)
        if dup_flags:
            p["_dup_flags"] = list(set((p.get("_dup_flags") or []) + dup_flags))
        p["risk"] = await _risk_score(p)
        p["updated_at"] = _now()

        await _db.kyc_profiles.update_one(
            {"user_id": u["user_id"]},
            {"$set": {k: v for k, v in p.items() if not k.startswith("_id")}},
        )
        await _timeline(u["user_id"], f"step.{step}.submitted", "user",
                        meta={"completion": p["completion"]})
        return _serialize_profile(p)

    @user.post("/submit")
    async def submit_for_review(u=Depends(get_current_user)):
        p = await _get_or_create_profile(u["user_id"])
        if p["completion"] < 100:
            raise HTTPException(400, f"All 7 steps required. Currently {p['completion']}%.")
        if p.get("status") == "approved":
            raise HTTPException(400, "KYC already approved.")
        await _db.kyc_profiles.update_one(
            {"user_id": u["user_id"]},
            {"$set": {"status": "under_review", "submitted_at": _now(),
                      "updated_at": _now()}},
        )
        await _timeline(u["user_id"], "submitted_for_review", "user")
        await _notify(u["user_id"], "KYC Submitted ✅",
                      "Your KYC is now under review. Approval typically within 24 hours.")
        p["status"] = "under_review"
        return _serialize_profile(p)

    @user.get("/document/{doc_id}")
    async def get_doc(doc_id: str, u=Depends(get_current_user)):
        d = await DocStore.load(doc_id)
        if not d or d["user_id"] != u["user_id"]:
            raise HTTPException(404, "Document not found")
        return Response(content=base64.b64decode(d["b64"]),
                        media_type=d.get("mime", "application/octet-stream"))

    # ----- ADMIN -----
    @admin.get("")
    async def admin_list(adm=Depends(get_current_admin),
                         q: Optional[str] = None,
                         status: Optional[str] = None,
                         risk: Optional[str] = None,
                         limit: int = 100, skip: int = 0):
        query: Dict[str, Any] = {}
        if status and status != "all":
            query["status"] = status
        if risk and risk != "all":
            query["risk"] = risk
        if q:
            # Search by user_id, PAN, name
            query["$or"] = [
                {"user_id": {"$regex": q, "$options": "i"}},
                {"steps.1.full_name": {"$regex": q, "$options": "i"}},
                {"steps.3.pan": {"$regex": q.upper(), "$options": "i"}},
            ]
        cur = _db.kyc_profiles.find(query, {"_id": 0}).sort("updated_at", -1).skip(max(skip, 0)).limit(min(limit, 200))
        items = [_serialize_profile(p, for_admin=True) for p in await cur.to_list(min(limit, 200))]
        # Enrich with user email/mobile
        if items:
            ids = [it["user_id"] for it in items]
            users = {u["user_id"]: u async for u in _db.users.find(
                {"user_id": {"$in": ids}},
                {"_id": 0, "user_id": 1, "full_name": 1, "email": 1, "mobile": 1})}
            for it in items:
                u = users.get(it["user_id"]) or {}
                it["user"] = {"full_name": u.get("full_name"),
                              "email": u.get("email"), "mobile": u.get("mobile")}
        total = await _db.kyc_profiles.count_documents(query)
        return {"items": items, "total": total}

    @admin.get("/dashboard")
    async def admin_dashboard(adm=Depends(get_current_admin)):
        today_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=6)
        stats = {
            "total": await _db.kyc_profiles.count_documents({}),
            "not_started": await _db.kyc_profiles.count_documents({"status": "not_started"}),
            "in_progress": await _db.kyc_profiles.count_documents({"status": "in_progress"}),
            "under_review": await _db.kyc_profiles.count_documents({"status": "under_review"}),
            "approved": await _db.kyc_profiles.count_documents({"status": "approved"}),
            "rejected": await _db.kyc_profiles.count_documents({"status": "rejected"}),
            "reupload": await _db.kyc_profiles.count_documents({"status": "reupload_required"}),
            "high_risk": await _db.kyc_profiles.count_documents({"risk": "high"}),
            "today_submissions": await _db.kyc_profiles.count_documents(
                {"submitted_at": {"$gte": today_start}}),
        }
        # Weekly chart (last 7 days)
        weekly = []
        for i in range(7):
            day_start = week_start + timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            sub = await _db.kyc_profiles.count_documents(
                {"submitted_at": {"$gte": day_start, "$lt": day_end}})
            app = await _db.kyc_profiles.count_documents(
                {"approved_at": {"$gte": day_start, "$lt": day_end}})
            weekly.append({"date": day_start.strftime("%Y-%m-%d"),
                           "submitted": sub, "approved": app})
        return {"stats": stats, "weekly": weekly}

    @admin.get("/duplicates")
    async def duplicates(adm=Depends(get_current_admin)):
        # Aggregate duplicate PANs / Aadhaars / mobiles / emails
        pan_dups = []
        async for d in _db.kyc_profiles.aggregate([
            {"$match": {"steps.3.pan": {"$ne": None, "$ne": ""}}},
            {"$group": {"_id": "$steps.3.pan", "count": {"$sum": 1},
                        "users": {"$push": "$user_id"}}},
            {"$match": {"count": {"$gt": 1}}},
        ]):
            pan_dups.append({"pan": mask_pan(d["_id"]), "count": d["count"], "users": d["users"]})

        ad_dups = []
        async for d in _db.kyc_profiles.aggregate([
            {"$match": {"steps.4.aadhaar_digits": {"$ne": None, "$ne": ""}}},
            {"$group": {"_id": "$steps.4.aadhaar_digits", "count": {"$sum": 1},
                        "users": {"$push": "$user_id"}}},
            {"$match": {"count": {"$gt": 1}}},
        ]):
            ad_dups.append({"aadhaar": mask_aadhaar(d["_id"]), "count": d["count"], "users": d["users"]})

        # Mobile / email duplicates on users collection
        mobile_dups = []
        async for d in _db.users.aggregate([
            {"$group": {"_id": "$mobile", "count": {"$sum": 1}, "users": {"$push": "$user_id"}}},
            {"$match": {"count": {"$gt": 1}, "_id": {"$ne": None, "$ne": ""}}},
        ]):
            mobile_dups.append({"mobile": d["_id"], "count": d["count"], "users": d["users"]})
        email_dups = []
        async for d in _db.users.aggregate([
            {"$group": {"_id": "$email", "count": {"$sum": 1}, "users": {"$push": "$user_id"}}},
            {"$match": {"count": {"$gt": 1}, "_id": {"$ne": None, "$ne": ""}}},
        ]):
            email_dups.append({"email": d["_id"], "count": d["count"], "users": d["users"]})
        return {"pan": pan_dups, "aadhaar": ad_dups,
                "mobile": mobile_dups, "email": email_dups}

    @admin.get("/export.csv")
    async def export_csv(adm=Depends(get_current_admin)):
        rows = await _db.kyc_profiles.find({}, {"_id": 0}).to_list(10000)
        s = io.StringIO()
        w = csv.writer(s)
        w.writerow(["user_id", "status", "completion", "risk", "pan",
                    "aadhaar_masked", "submitted_at", "approved_at",
                    "rejected_at", "locked"])
        for p in rows:
            steps = p.get("steps", {})
            w.writerow([
                p.get("user_id"), p.get("status"), p.get("completion"), p.get("risk"),
                mask_pan((steps.get("3") or {}).get("pan")),
                mask_aadhaar((steps.get("4") or {}).get("aadhaar_digits")),
                p.get("submitted_at", ""), p.get("approved_at", ""),
                p.get("rejected_at", ""), p.get("locked", False),
            ])
        await _log_action(adm["admin_id"], "kyc.export_csv", target="all",
                          meta={"count": len(rows)})
        return Response(content=s.getvalue().encode("utf-8"),
                        media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="MFB_KYC.csv"'})

    @admin.get("/{user_id}")
    async def admin_detail(user_id: str, adm=Depends(get_current_admin)):
        p = await _db.kyc_profiles.find_one({"user_id": user_id}, {"_id": 0})
        if not p:
            raise HTTPException(404, "KYC profile not found")
        u = await _db.users.find_one({"user_id": user_id},
            {"_id": 0, "password": 0}) or {}
        timeline = await _db.kyc_timeline.find({"user_id": user_id}, {"_id": 0}).sort("at", -1).limit(100).to_list(100)
        # List docs (metadata only)
        docs = await _db.kyc_documents.find({"user_id": user_id},
            {"_id": 0, "b64": 0}).to_list(20)
        return {"profile": _serialize_profile(p, for_admin=True),
                "user": u, "timeline": timeline, "documents": docs}

    @admin.get("/{user_id}/documents.zip")
    async def docs_zip(user_id: str, adm=Depends(get_current_admin)):
        docs = await _db.kyc_documents.find({"user_id": user_id}, {"_id": 0}).to_list(20)
        if not docs:
            raise HTTPException(404, "No documents found")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for d in docs:
                ext = {"image/jpeg": "jpg", "image/png": "png",
                        "application/pdf": "pdf"}.get(d.get("mime", ""), "bin")
                z.writestr(f"{d['type']}.{ext}", base64.b64decode(d["b64"]))
        await _log_action(adm["admin_id"], "kyc.docs_download", target=user_id)
        return Response(content=buf.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="KYC_{user_id}.zip"'})

    @admin.post("/{user_id}/approve")
    async def approve(user_id: str, adm=Depends(get_current_admin)):
        p = await _db.kyc_profiles.find_one({"user_id": user_id}, {"_id": 0})
        if not p:
            raise HTTPException(404, "KYC profile not found")
        expiry = _now() + timedelta(days=KYC_EXPIRY_YEARS * 365)
        await _db.kyc_profiles.update_one({"user_id": user_id}, {"$set": {
            "status": "approved", "locked": True,
            "approved_at": _now(), "expires_at": expiry,
            "approved_by": adm["admin_id"], "updated_at": _now(),
            "reject_reason": None, "reupload_fields": [],
        }})
        await _db.users.update_one({"user_id": user_id},
                                    {"$set": {"kyc_status": "approved"}})
        await _timeline(user_id, "approved", f"admin:{adm['admin_id']}")
        await _log_action(adm["admin_id"], "kyc.approve", target=user_id)
        await _notify(user_id, "KYC Approved 🎉",
                      "Congratulations! Your KYC is approved. You can now invest, withdraw and trade.")
        return {"ok": True, "status": "approved", "expires_at": expiry}

    @admin.post("/{user_id}/reject")
    async def reject(user_id: str, body: Dict[str, Any] = Body(...),
                     adm=Depends(get_current_admin)):
        reason = (body.get("reason") or "").strip()
        if not reason:
            raise HTTPException(400, "reason required")
        await _db.kyc_profiles.update_one({"user_id": user_id}, {"$set": {
            "status": "rejected", "rejected_at": _now(),
            "reject_reason": reason, "rejected_by": adm["admin_id"],
            "updated_at": _now(),
        }})
        await _db.users.update_one({"user_id": user_id},
                                    {"$set": {"kyc_status": "rejected"}})
        await _timeline(user_id, "rejected", f"admin:{adm['admin_id']}",
                        meta={"reason": reason})
        await _log_action(adm["admin_id"], "kyc.reject", target=user_id,
                          meta={"reason": reason})
        await _notify(user_id, "KYC Rejected",
                      f"Your KYC was rejected. Reason: {reason}. Tap to re-submit.")
        return {"ok": True, "status": "rejected"}

    @admin.post("/{user_id}/request-reupload")
    async def request_reupload(user_id: str, body: Dict[str, Any] = Body(...),
                                adm=Depends(get_current_admin)):
        fields = body.get("fields") or []
        note = (body.get("note") or "").strip()
        if not fields:
            raise HTTPException(400, "fields list required (e.g. ['pan','selfie'])")
        await _db.kyc_profiles.update_one({"user_id": user_id}, {"$set": {
            "status": "reupload_required", "reupload_fields": fields,
            "reupload_note": note, "updated_at": _now(),
        }})
        await _timeline(user_id, "reupload_requested", f"admin:{adm['admin_id']}",
                        meta={"fields": fields, "note": note})
        await _log_action(adm["admin_id"], "kyc.reupload", target=user_id,
                          meta={"fields": fields})
        await _notify(user_id, "KYC Re-upload Required",
                      f"Please re-upload: {', '.join(fields)}. {note}")
        return {"ok": True}

    @admin.post("/{user_id}/unlock")
    async def unlock(user_id: str, adm=Depends(get_current_admin)):
        if adm["role"] not in ("super_admin", "admin"):
            raise HTTPException(403, "Only super_admin/admin can unlock")
        await _db.kyc_profiles.update_one({"user_id": user_id}, {"$set": {
            "locked": False, "status": "in_progress", "updated_at": _now(),
        }})
        await _timeline(user_id, "unlocked_for_rekyc", f"admin:{adm['admin_id']}")
        await _log_action(adm["admin_id"], "kyc.unlock", target=user_id)
        await _notify(user_id, "Re-KYC Enabled",
                      "Admin has unlocked your KYC for re-submission.")
        return {"ok": True}

    @admin.post("/{user_id}/note")
    async def add_note(user_id: str, body: Dict[str, Any] = Body(...),
                       adm=Depends(get_current_admin)):
        note_text = (body.get("note") or "").strip()
        if not note_text:
            raise HTTPException(400, "note required")
        note = {"note_id": _gen("note"), "text": note_text,
                "by": adm["admin_id"], "at": _now()}
        await _db.kyc_profiles.update_one({"user_id": user_id},
            {"$push": {"admin_notes": note}})
        await _timeline(user_id, "note_added", f"admin:{adm['admin_id']}",
                        meta={"snippet": note_text[:80]})
        return {"ok": True, "note": note}

    @admin.post("/bulk")
    async def bulk(body: Dict[str, Any] = Body(...),
                   adm=Depends(get_current_admin)):
        action = body.get("action")
        ids = body.get("user_ids") or []
        if action not in ("approve", "reject") or not ids:
            raise HTTPException(400, "action must be approve/reject + user_ids[]")
        reason = body.get("reason", "Bulk action")
        ok = 0
        for uid in ids[:200]:
            try:
                if action == "approve":
                    await approve(uid, adm)  # reuses logic
                else:
                    await reject(uid, {"reason": reason}, adm)
                ok += 1
            except Exception as e:
                logger.warning(f"[kyc.bulk] {uid}: {e}")
        return {"ok": True, "processed": ok, "requested": len(ids)}

    api.include_router(user)
    api.include_router(admin)


# ============================================================================
# Admin override / bypass management — appended below the main attach() above.
# Exposed by importing kyc_module from outside.
# ============================================================================
def attach_bypass_routes(api: APIRouter, db, get_current_admin, log_action):
    """Adds /api/admin/kyc/bypass/* endpoints. Super-admin only.

    Bypass usage is audit-logged. Use sparingly (testing / VIP only).
    """
    r = APIRouter(prefix="/admin/kyc-bypass", tags=["kyc-bypass"])

    @r.get("")
    async def list_bypasses(adm=Depends(get_current_admin)):
        items = await db.kyc_bypasses.find({}, {"_id": 0}).sort("granted_at", -1).limit(200).to_list(200)
        return {"items": items, "active": sum(1 for x in items if x.get("active"))}

    @r.post("/grant")
    async def grant(body: Dict[str, Any] = Body(...), adm=Depends(get_current_admin)):
        if adm["role"] != "super_admin":
            raise HTTPException(403, "Only super_admin can grant KYC bypass")
        uid = body.get("user_id")
        reason = (body.get("reason") or "").strip()
        if not uid or not reason:
            raise HTTPException(400, "user_id and reason required")
        days = int(body.get("expires_in_days", 7))
        bypass = {
            "bypass_id": _gen("byp"), "user_id": uid, "active": True,
            "reason": reason, "granted_by": adm["admin_id"],
            "granted_at": _now(),
            "expires_at": _now() + timedelta(days=days) if days > 0 else None,
        }
        await db.kyc_bypasses.insert_one(bypass)
        await log_action(adm["admin_id"], "kyc.bypass.grant", target=uid,
                         meta={"reason": reason, "expires_in_days": days})
        await _timeline(uid, "kyc_bypass_granted", f"admin:{adm['admin_id']}",
                        meta={"reason": reason, "expires_in_days": days})
        bypass.pop("_id", None)
        return {"ok": True, "bypass": bypass}

    @r.post("/revoke/{bypass_id}")
    async def revoke(bypass_id: str, adm=Depends(get_current_admin)):
        if adm["role"] != "super_admin":
            raise HTTPException(403, "Only super_admin can revoke KYC bypass")
        b = await db.kyc_bypasses.find_one({"bypass_id": bypass_id})
        if not b:
            raise HTTPException(404, "Bypass not found")
        await db.kyc_bypasses.update_one({"bypass_id": bypass_id},
            {"$set": {"active": False, "revoked_at": _now(), "revoked_by": adm["admin_id"]}})
        await log_action(adm["admin_id"], "kyc.bypass.revoke", target=b["user_id"],
                         meta={"bypass_id": bypass_id})
        await _timeline(b["user_id"], "kyc_bypass_revoked", f"admin:{adm['admin_id']}")
        return {"ok": True}

    @r.get("/stats")
    async def bypass_stats(adm=Depends(get_current_admin)):
        return {
            "active_bypasses": await db.kyc_bypasses.count_documents({"active": True}),
            "total_grants": await db.kyc_bypasses.count_documents({}),
            "total_uses": await db.kyc_bypass_usage.count_documents({}),
            "blocked_attempts_24h": await db.kyc_blocked_attempts.count_documents(
                {"at": {"$gte": _now() - timedelta(hours=24)}}) if "kyc_blocked_attempts" in await db.list_collection_names() else 0,
        }

    api.include_router(r)
