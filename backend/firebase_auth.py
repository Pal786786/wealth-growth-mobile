"""Firebase Phone Authentication — backend ID-token verifier.

Verifies Firebase ID tokens issued by Firebase Phone Auth WITHOUT requiring
a service-account JSON (uses Google's public x509 certificate endpoint).

This is sufficient for the typical mobile-to-backend handshake:
1. Mobile: signInWithPhoneNumber() → user enters OTP → confirm() → returns ID token
2. Mobile: POST /api/auth/firebase/verify  with the ID token
3. Backend: verifies signature using Google's public keys, project_id audience match
4. Backend: upserts user (by phone_number), issues MFB JWT, returns

Provider switch:
- Configured via API Management → SMS Provider → provider field: msg91|twilio|firebase|demo
- Demo OTP fallback always available when admin sets force_demo=true
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
import jwt
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("mfb.firebase_auth")

_db = None
_create_jwt = None  # MFB JWT issuer fn
_now_fn = lambda: datetime.now(timezone.utc)

# Public certificates URL — Firebase rotates these every few hours
GOOGLE_PUBLIC_CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
)
ISSUER_PREFIX = "https://securetoken.google.com/"

# In-memory cert cache (keyed by 'kid' header). Rotates every ~6h.
_certs_cache: Dict[str, Any] = {"keys": {}, "expires_at": 0}
_certs_lock = asyncio.Lock()


async def _get_firebase_certs() -> Dict[str, Any]:
    """Fetch + cache Google's public certs used to sign Firebase ID tokens."""
    now = time.time()
    async with _certs_lock:
        if _certs_cache["keys"] and now < _certs_cache["expires_at"]:
            return _certs_cache["keys"]
        async with httpx.AsyncClient(timeout=8) as http:
            r = await http.get(GOOGLE_PUBLIC_CERTS_URL)
            r.raise_for_status()
            certs_pem = r.json()  # {kid: PEM_x509_certificate}
            # Cache TTL from Cache-Control max-age header if present, else 3600s
            ttl = 3600
            cc = r.headers.get("cache-control", "")
            if "max-age=" in cc:
                try:
                    ttl = int(cc.split("max-age=")[1].split(",")[0].strip())
                except Exception:
                    pass
            # Convert PEM x509 → public key objects
            keys = {}
            for kid, pem in certs_pem.items():
                try:
                    cert = x509.load_pem_x509_certificate(pem.encode("utf-8"), default_backend())
                    keys[kid] = cert.public_key()
                except Exception as e:
                    logger.warning(f"Failed to parse Firebase cert {kid}: {e}")
            _certs_cache["keys"] = keys
            _certs_cache["expires_at"] = now + ttl
            return keys


async def _firebase_project_id() -> Optional[str]:
    """Read project_id from API Management (SMS Provider config extras)."""
    doc = await _db.api_settings.find_one({"api_name": "sms_provider"}, {"_id": 0, "extra": 1, "api_key": 1, "force_demo": 1})
    if not doc:
        return None
    return (doc.get("extra") or {}).get("firebase_project_id") or None


async def verify_firebase_id_token(id_token: str) -> Dict[str, Any]:
    """Verifies a Firebase ID token and returns the decoded claims.

    Raises HTTPException(401) on any failure.
    """
    project_id = await _firebase_project_id()
    if not project_id:
        raise HTTPException(503, "Firebase Phone Auth is not configured. Set 'firebase_project_id' in API Management → SMS Provider.")
    # Get unverified header to find the right key
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"Malformed token: {e}")

    kid = header.get("kid")
    if not kid:
        raise HTTPException(401, "Token missing 'kid' header")

    keys = await _get_firebase_certs()
    public_key = keys.get(kid)
    if not public_key:
        # Force refresh in case the cache is stale
        _certs_cache["expires_at"] = 0
        keys = await _get_firebase_certs()
        public_key = keys.get(kid)
        if not public_key:
            raise HTTPException(401, "Token signed by unknown key")

    issuer = f"{ISSUER_PREFIX}{project_id}"
    try:
        claims = jwt.decode(
            id_token,
            public_key,
            algorithms=["RS256"],
            audience=project_id,
            issuer=issuer,
            options={"require": ["exp", "iat", "auth_time", "sub", "aud", "iss"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Firebase ID token expired")
    except jwt.InvalidAudienceError:
        raise HTTPException(401, f"Token audience mismatch (expected {project_id})")
    except jwt.InvalidIssuerError:
        raise HTTPException(401, f"Token issuer mismatch (expected {issuer})")
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"Token verification failed: {e}")

    # Additional checks required by Firebase docs
    if claims.get("auth_time", 0) > time.time():
        raise HTTPException(401, "Token auth_time is in the future")
    if not claims.get("sub"):
        raise HTTPException(401, "Token missing subject (uid)")
    return claims


# ============================================================================
# Endpoints
# ============================================================================
class FirebaseVerifyReq(BaseModel):
    id_token: str = Field(..., min_length=20)
    full_name: Optional[str] = None
    referral_code: Optional[str] = None


def attach(api: APIRouter, db, create_jwt_fn, now_fn=None):
    global _db, _create_jwt, _now_fn
    _db = db
    _create_jwt = create_jwt_fn
    if now_fn:
        _now_fn = now_fn

    r = APIRouter(prefix="/auth/firebase", tags=["firebase-auth"])

    @r.get("/status")
    async def status():
        """Mobile pre-flight: check if Firebase provider is enabled before triggering signInWithPhoneNumber."""
        doc = await _db.api_settings.find_one({"api_name": "sms_provider"}, {"_id": 0})
        if not doc:
            return {"enabled": False, "provider": "demo", "project_id": None}
        extra = doc.get("extra") or {}
        provider = (extra.get("provider") or "").lower()
        project_id = extra.get("firebase_project_id")
        force_demo = bool(doc.get("force_demo"))
        return {
            "enabled": provider == "firebase" and bool(project_id) and not force_demo,
            "provider": "demo" if force_demo else (provider or "demo"),
            "project_id": project_id,
            "force_demo": force_demo,
        }

    @r.post("/verify")
    async def firebase_verify(req: FirebaseVerifyReq):
        """Verify Firebase ID token → create/login MFB user → return MFB JWT."""
        claims = await verify_firebase_id_token(req.id_token)
        firebase_uid = claims["sub"]
        phone = (claims.get("phone_number") or "").lstrip("+91").lstrip("+")
        if not phone:
            raise HTTPException(400, "Firebase token has no phone_number (was sign-in not via phone OTP?)")
        # Find existing user by mobile OR firebase_uid
        u = await _db.users.find_one({"$or": [{"mobile": phone}, {"firebase_uid": firebase_uid}]}, {"_id": 0})
        is_new = False
        if not u:
            # Create new user
            user_id = f"usr_{uuid.uuid4().hex[:12]}"
            referral_code = f"MFB{uuid.uuid4().hex[:6].upper()}"
            u = {
                "user_id": user_id,
                "mobile": phone,
                "email": claims.get("email") or "",
                "full_name": req.full_name or claims.get("name") or "",
                "firebase_uid": firebase_uid,
                "auth_provider": "firebase",
                "referral_code": referral_code,
                "referred_by": req.referral_code or "",
                "reward_points": 0,
                "tier_id": "bronze",
                "kyc_status": "pending",
                "created_at": _now_fn(),
                "updated_at": _now_fn(),
            }
            await _db.users.insert_one(u)
            # Seed wallet
            await _db.wallets.update_one(
                {"user_id": user_id},
                {"$setOnInsert": {"user_id": user_id, "balance": 0, "currency": "INR", "created_at": _now_fn()}},
                upsert=True,
            )
            is_new = True
        else:
            # Backfill firebase_uid if user existed via OTP/email before
            if not u.get("firebase_uid"):
                await _db.users.update_one(
                    {"user_id": u["user_id"]},
                    {"$set": {"firebase_uid": firebase_uid, "auth_provider": "firebase", "updated_at": _now_fn()}},
                )
        # Issue MFB JWT
        token = _create_jwt({"user_id": u["user_id"], "mobile": u["mobile"]})
        # Strip internal _id if present
        u.pop("_id", None)
        return {
            "token": token,
            "user": u,
            "is_new_user": is_new,
            "auth_provider": "firebase",
        }

    api.include_router(r)
