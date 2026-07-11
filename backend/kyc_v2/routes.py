"""KYC v2 API routes.

All endpoints live under `/api/kyc/v2/*` so they DON'T collide with the
existing `/api/kyc/*` in `kyc_module.py`.

User routes:
  POST /api/kyc/v2/pan/verify         {pan, name?, dob?}
  POST /api/kyc/v2/aadhaar/verify     {aadhaar_last4, name, dob}  (soft-verify)
  POST /api/kyc/v2/digilocker/start   {redirect_uri}
  POST /api/kyc/v2/digilocker/callback {code, state}
  POST /api/kyc/v2/ocr                {doc_type, image_b64}
  POST /api/kyc/v2/face-match         {id_photo_b64, selfie_b64}
  POST /api/kyc/v2/documents          {doc_type, image_b64, mime?}
  GET  /api/kyc/v2/summary             — timeline + verifications + gating snapshot
  GET  /api/kyc/v2/gate?action=       — evaluate any single action
  GET  /api/kyc/v2/compliance         — personal compliance report

Admin routes:
  GET  /api/admin/kyc/v2/verifications[?user_id&limit]
  GET  /api/admin/kyc/v2/gating-events[?user_id&limit]
  GET  /api/admin/kyc/v2/dashboard
  GET  /api/admin/kyc/v2/providers    — provider health / configured?
"""
from __future__ import annotations
import base64
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .gating import (
    GATED_ACTIONS, COMPLIANCE_LIMITS, is_kyc_gated_action,
    kyc_status, evaluate_gate, compliance_report,
)
from .providers.pan import get_pan_provider, NSDLPanProvider, DemoPanProvider
from .providers.digilocker import (
    get_digilocker_provider, DemoDigiLockerProvider, DigiLockerProviderReal,
)
from .providers.aux import get_ocr_provider, get_face_match_provider
from .storage import encrypt_blob, decrypt_blob, sha256_hex, encryption_status

logger = logging.getLogger("kyc_v2.routes")

VER_COLL = "kyc_verifications"
DOC_COLL = "kyc_v2_documents"
GATE_COLL = "kyc_gating_events"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return d


# ---------- request models ----------
class PanVerifyIn(BaseModel):
    pan: str = Field(..., min_length=10, max_length=10)
    name: Optional[str] = None
    dob: Optional[str] = None


class AadhaarSoftVerifyIn(BaseModel):
    aadhaar_last4: str = Field(..., min_length=4, max_length=4)
    name: str
    dob: Optional[str] = None


class DigiLockerStartIn(BaseModel):
    redirect_uri: str


class DigiLockerCallbackIn(BaseModel):
    code: str
    state: str


class OcrIn(BaseModel):
    doc_type: str
    image_b64: str


class FaceMatchIn(BaseModel):
    id_photo_b64: str
    selfie_b64: str


class DocumentUploadIn(BaseModel):
    doc_type: str
    image_b64: str
    mime: Optional[str] = "image/jpeg"


def _b64_decode(s: str) -> bytes:
    # Tolerate data-URLs like "data:image/jpeg;base64,..."
    if "," in s and s.startswith("data:"):
        s = s.split(",", 1)[1]
    return base64.b64decode(s)


def attach(app, db, get_current_user, get_current_admin):
    r = APIRouter(prefix="/api/kyc/v2", tags=["kyc-v2"])
    ar = APIRouter(prefix="/api/admin/kyc/v2", tags=["kyc-v2-admin"])

    async def _record_verification(user_id: str, kind: str,
                                     ok: bool, result: Dict[str, Any]):
        doc = {
            "verification_id": f"kv_{uuid.uuid4().hex[:14]}",
            "user_id": user_id, "kind": kind,
            "ok": bool(ok), "provider": result.get("provider", "unknown"),
            "status": result.get("status") or ("ok" if ok else "failed"),
            "summary": {k: v for k, v in result.items()
                         if k in ("pan", "official_name", "name_match",
                                    "aadhaar_last4", "aadhaar_hash", "score",
                                    "match", "reference_id", "doc_type",
                                    "confidence", "issued_at", "category")},
            "raw": result,
            "created_at": _now(),
        }
        await db[VER_COLL].insert_one(doc)
        return doc

    # =============== USER ===============
    @r.post("/pan/verify")
    async def pan_verify(body: PanVerifyIn, user=Depends(get_current_user)):
        provider = get_pan_provider()
        result = await provider.verify(body.pan, body.name, body.dob)
        rec = await _record_verification(user["user_id"], "pan",
                                          bool(result.get("ok")), result)
        # Auto-copy into kyc_profiles / users so the existing UI stays in sync
        if result.get("ok"):
            await db.kyc_profiles.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"pan": body.pan.upper(),
                           "pan_verified": True,
                           "pan_verified_at": _now(),
                           "pan_verified_provider": result.get("provider"),
                           "pan_name": result.get("official_name"),
                           "updated_at": _now()}},
                upsert=True,
            )
        rec.pop("_id", None)
        return {"result": result, "verification": _iso(rec)}

    @r.post("/aadhaar/verify")
    async def aadhaar_soft_verify(body: AadhaarSoftVerifyIn,
                                     user=Depends(get_current_user)):
        """Soft verification for users who don't want to link DigiLocker —
        we accept the last-4 + name + dob and mark it as `soft-verified`
        rather than the full Aadhaar KYC."""
        if not body.aadhaar_last4.isdigit():
            raise HTTPException(400, "aadhaar_last4 must be 4 digits")
        result = {
            "ok": True, "provider": "self-declared",
            "aadhaar_last4": body.aadhaar_last4,
            "aadhaar_hash": sha256_hex(body.aadhaar_last4.encode() +
                                          body.name.encode()),
            "name": body.name, "dob": body.dob,
            "status": "soft_verified",
            "note": "For full Aadhaar KYC link DigiLocker.",
        }
        rec = await _record_verification(user["user_id"], "aadhaar_soft",
                                          True, result)
        rec.pop("_id", None)
        return {"result": result, "verification": _iso(rec)}

    @r.post("/digilocker/start")
    async def digilocker_start(body: DigiLockerStartIn,
                                 user=Depends(get_current_user)):
        provider = get_digilocker_provider()
        state = f"st_{uuid.uuid4().hex[:16]}"
        # Persist state so we can bind it back to the user at callback
        await db.kyc_digilocker_states.insert_one({
            "state": state, "user_id": user["user_id"],
            "redirect_uri": body.redirect_uri, "created_at": _now(),
        })
        return await provider.issue_authorization(body.redirect_uri, state,
                                                   user["user_id"])

    @r.post("/digilocker/callback")
    async def digilocker_callback(body: DigiLockerCallbackIn,
                                     user=Depends(get_current_user)):
        provider = get_digilocker_provider()
        st_doc = await db.kyc_digilocker_states.find_one({"state": body.state})
        if not st_doc:
            raise HTTPException(400, "unknown state")
        if st_doc.get("user_id") != user["user_id"]:
            raise HTTPException(403, "state does not belong to caller")
        # 1. exchange code for access token
        tok = await provider.exchange_code(body.code, body.state)
        if not tok.get("ok"):
            return {"result": tok}
        # 2. fetch aadhaar
        aad = await provider.fetch_aadhaar(tok["access_token"])
        combined = {**tok, **aad}
        rec = await _record_verification(user["user_id"], "digilocker",
                                          bool(aad.get("ok")), combined)
        if aad.get("ok"):
            await db.kyc_profiles.update_one(
                {"user_id": user["user_id"]},
                {"$set": {
                    "aadhaar_hash": aad.get("aadhaar_hash"),
                    "aadhaar_last4": aad.get("aadhaar_last4"),
                    "aadhaar_verified": True,
                    "aadhaar_verified_at": _now(),
                    "aadhaar_verified_provider": aad.get("provider", "digilocker"),
                    "aadhaar_name": aad.get("name"),
                    "address": aad.get("address"),
                    "updated_at": _now(),
                }},
                upsert=True,
            )
        rec.pop("_id", None)
        # Cleanup the one-shot state
        await db.kyc_digilocker_states.delete_one({"state": body.state})
        return {"result": combined, "verification": _iso(rec)}

    @r.post("/ocr")
    async def ocr(body: OcrIn, user=Depends(get_current_user)):
        try:
            data = _b64_decode(body.image_b64)
        except Exception:
            raise HTTPException(400, "invalid image_b64")
        if len(data) > 8 * 1024 * 1024:
            raise HTTPException(413, "image too large (max 8MB)")
        provider = get_ocr_provider()
        result = await provider.parse(body.doc_type, data)
        rec = await _record_verification(user["user_id"], f"ocr:{body.doc_type}",
                                          bool(result.get("ok")), result)
        rec.pop("_id", None)
        return {"result": result, "verification": _iso(rec)}

    @r.post("/face-match")
    async def face_match(body: FaceMatchIn, user=Depends(get_current_user)):
        try:
            id_photo = _b64_decode(body.id_photo_b64)
            selfie = _b64_decode(body.selfie_b64)
        except Exception:
            raise HTTPException(400, "invalid base64")
        if len(id_photo) + len(selfie) > 12 * 1024 * 1024:
            raise HTTPException(413, "images too large")
        provider = get_face_match_provider()
        result = await provider.match(id_photo, selfie)
        rec = await _record_verification(user["user_id"], "face_match",
                                          bool(result.get("match")), result)
        rec.pop("_id", None)
        return {"result": result, "verification": _iso(rec)}

    @r.post("/documents")
    async def upload_document(body: DocumentUploadIn, user=Depends(get_current_user)):
        try:
            data = _b64_decode(body.image_b64)
        except Exception:
            raise HTTPException(400, "invalid image_b64")
        if len(data) > 8 * 1024 * 1024:
            raise HTTPException(413, "image too large (max 8MB)")
        ct, encrypted = encrypt_blob(data)
        doc_id = f"kd_{uuid.uuid4().hex[:14]}"
        doc = {
            "document_id": doc_id, "user_id": user["user_id"],
            "doc_type": body.doc_type, "mime": body.mime or "image/jpeg",
            "size_bytes": len(data),
            "sha256": sha256_hex(data),
            "encrypted": encrypted, "ciphertext_b64": ct,
            "uploaded_at": _now(),
        }
        await db[DOC_COLL].insert_one(doc)
        return {"document_id": doc_id, "size_bytes": len(data),
                "sha256": doc["sha256"], "encrypted": encrypted,
                "doc_type": body.doc_type}

    @r.get("/summary")
    async def summary(user=Depends(get_current_user)):
        st = await kyc_status(db, user["user_id"])
        prof = await db.kyc_profiles.find_one(
            {"user_id": user["user_id"]}, {"_id": 0}) or {}
        cur = db[VER_COLL].find({"user_id": user["user_id"]},
                                  {"_id": 0, "raw": 0}).sort("created_at", -1).limit(50)
        vers = [_iso(v) async for v in cur]
        docs_count = await db[DOC_COLL].count_documents({"user_id": user["user_id"]})
        gates = {a: (await evaluate_gate(db, user["user_id"], a)) for a in GATED_ACTIONS}
        compliance = await compliance_report(db, user["user_id"])
        return {
            "status": st, "kyc_required_for": list(GATED_ACTIONS.keys()),
            "gates": gates,
            "pan_verified": bool(prof.get("pan_verified")),
            "aadhaar_verified": bool(prof.get("aadhaar_verified")),
            "pan": prof.get("pan") if prof.get("pan_verified") else None,
            "aadhaar_last4": prof.get("aadhaar_last4"),
            "address": prof.get("address"),
            "verifications": vers,
            "documents_count": docs_count,
            "compliance": compliance,
            "encryption": encryption_status(),
        }

    @r.get("/gate")
    async def gate(action: str = Query(...), user=Depends(get_current_user)):
        if not is_kyc_gated_action(action):
            return {"required": False, "action": action,
                    "status": "not_gated",
                    "reason": "This action does not require KYC."}
        return await evaluate_gate(db, user["user_id"], action)

    @r.get("/compliance")
    async def compliance(user=Depends(get_current_user)):
        return await compliance_report(db, user["user_id"])

    # =============== ADMIN ===============
    @ar.get("/verifications")
    async def admin_verifications(
        user_id: Optional[str] = Query(None),
        kind: Optional[str] = Query(None),
        limit: int = Query(100, ge=1, le=500),
        admin=Depends(get_current_admin),
    ):
        q: Dict[str, Any] = {}
        if user_id: q["user_id"] = user_id
        if kind: q["kind"] = kind
        cur = db[VER_COLL].find(q, {"_id": 0, "raw": 0}).sort("created_at", -1).limit(limit)
        rows = [_iso(v) async for v in cur]
        return {"items": rows, "count": len(rows)}

    @ar.get("/gating-events")
    async def admin_gating_events(
        user_id: Optional[str] = Query(None),
        action: Optional[str] = Query(None),
        limit: int = Query(100, ge=1, le=500),
        admin=Depends(get_current_admin),
    ):
        q: Dict[str, Any] = {}
        if user_id: q["user_id"] = user_id
        if action: q["action"] = action
        cur = db[GATE_COLL].find(q, {"_id": 0}).sort("at", -1).limit(limit)
        rows = [_iso(v) async for v in cur]
        return {"items": rows, "count": len(rows)}

    @ar.get("/dashboard")
    async def admin_dashboard(admin=Depends(get_current_admin)):
        pan_ok = await db[VER_COLL].count_documents({"kind": "pan", "ok": True})
        aadhaar_ok = await db[VER_COLL].count_documents(
            {"kind": {"$in": ["digilocker", "aadhaar_soft"]}, "ok": True})
        face_ok = await db[VER_COLL].count_documents({"kind": "face_match", "ok": True})
        docs = await db[DOC_COLL].estimated_document_count()
        gates = await db[GATE_COLL].count_documents({})
        by_status = {}
        cur = db.kyc_profiles.aggregate([
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}])
        async for x in cur:
            by_status[x["_id"] or "unknown"] = x["count"]
        return {
            "pan_verified": pan_ok, "aadhaar_verified": aadhaar_ok,
            "face_matched": face_ok,
            "documents_stored": docs,
            "gating_events": gates,
            "profiles_by_status": by_status,
            "providers": {
                "pan": get_pan_provider().provider,
                "digilocker": get_digilocker_provider().provider,
                "ocr": get_ocr_provider().provider,
                "face_match": get_face_match_provider().provider,
            },
            "encryption": encryption_status(),
            "gated_actions": GATED_ACTIONS,
            "compliance_limits": COMPLIANCE_LIMITS,
        }

    @ar.get("/providers")
    async def admin_providers(admin=Depends(get_current_admin)):
        pan = get_pan_provider()
        digi = get_digilocker_provider()
        return {
            "pan": {"provider": pan.provider, "configured": pan.is_configured(),
                     "real_backend": pan.provider == "nsdl"},
            "digilocker": {"provider": digi.provider,
                            "configured": digi.is_configured(),
                            "real_backend": digi.provider == "digilocker"},
            "ocr": {"provider": get_ocr_provider().provider, "configured": True},
            "face_match": {"provider": get_face_match_provider().provider,
                            "configured": True},
            "encryption": encryption_status(),
        }

    app.include_router(r)
    app.include_router(ar)
    return {"user": r, "admin": ar}
