"""Push notifications — Emergent-managed FCM relay.

Architecture:
- Frontend registers device token via POST /api/register-push
- Backend relays to SuprSend (Emergent push service) via EMERGENT_PUSH_KEY
- Backend send_push() helper used by event handlers (signup, admin broadcast, etc.)
- Demo-safe: if EMERGENT_PUSH_KEY is "placeholder" / missing, calls silently no-op
"""
from __future__ import annotations

import os
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

PUSH_BASE_URL = "https://integrations.emergentagent.com"
PUSH_KEY = os.environ.get("EMERGENT_PUSH_KEY", "placeholder")
PUSH_ENABLED = bool(PUSH_KEY) and PUSH_KEY != "placeholder"

_client = httpx.AsyncClient(
    base_url=PUSH_BASE_URL,
    headers={"X-Push-Key": PUSH_KEY},
    timeout=10.0,
)

logger = logging.getLogger("mfb.push")
_db = None
_get_current_user = None


class RegisterPushBody(BaseModel):
    user_id: str
    platform: str
    device_token: str


class CategoryPrefs(BaseModel):
    transactions: Optional[bool] = True
    rewards: Optional[bool] = True
    promotional: Optional[bool] = True
    security: Optional[bool] = True


async def send_push(recipients: list[str], data: dict, idempotency_key: Optional[str] = None) -> None:
    """Send push to up to 100 recipients. Silently no-ops if push isn't configured.
    Wrap callers in try/except — push failure should NEVER block primary operation."""
    if not recipients:
        return
    if not PUSH_ENABLED:
        logger.info(f"[push] not configured — would send '{data.get('title')}' to {len(recipients)} recipients")
        return
    if len(recipients) > 100:
        raise ValueError("max 100 recipients per /trigger call; chunk before sending")
    if "title" not in data or "message" not in data:
        raise ValueError("data must include title and message")
    payload: dict = {"recipients": recipients, "data": data}
    if idempotency_key:
        payload["$idempotency_key"] = idempotency_key
    try:
        resp = await _client.post("/api/v1/push/trigger", json=payload)
        if resp.status_code == 401:
            logger.error("EMERGENT_PUSH_KEY rejected — check backend env")
            return
        if resp.status_code >= 500:
            logger.warning(f"Push provider 5xx: {resp.status_code}")
            return
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Push send failed (non-blocking): {e}")


def attach(api: APIRouter, db, get_current_user):
    global _db, _get_current_user
    _db = db
    _get_current_user = get_current_user

    @api.post("/register-push", status_code=201)
    async def register_push(body: RegisterPushBody):
        """Register device token. Stores locally + relays upstream when configured."""
        # Always store locally so we can filter by category prefs
        await _db.push_tokens.update_one(
            {"user_id": body.user_id, "device_token": body.device_token},
            {"$set": {
                "user_id": body.user_id,
                "platform": body.platform,
                "device_token": body.device_token,
            }},
            upsert=True,
        )
        if not PUSH_ENABLED:
            return {"status": "stored_demo", "push_enabled": False}
        try:
            resp = await _client.post("/api/v1/push/users/register", json=body.model_dump())
            if resp.status_code == 401:
                raise HTTPException(500, "EMERGENT_PUSH_KEY missing or invalid")
            if resp.status_code >= 500:
                raise HTTPException(502, "Push provider unavailable")
            resp.raise_for_status()
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Push register relay failed: {e}")
            return {"status": "stored_local", "push_enabled": True, "relay": "failed"}
        return {"status": "registered", "push_enabled": True}

    @api.get("/notifications/preferences-legacy", include_in_schema=False)
    async def get_prefs(user: dict = Depends(get_current_user)):
        doc = await _db.notification_prefs.find_one({"user_id": user["user_id"]}, {"_id": 0})
        if not doc:
            doc = {"user_id": user["user_id"], "transactions": True, "rewards": True, "promotional": True, "security": True}
        return {
            "transactions": doc.get("transactions", True),
            "rewards": doc.get("rewards", True),
            "promotional": doc.get("promotional", True),
            "security": doc.get("security", True),
            "push_enabled": PUSH_ENABLED,
        }

    @api.put("/notifications/preferences-legacy", include_in_schema=False)
    async def update_prefs(body: CategoryPrefs, user: dict = Depends(get_current_user)):
        update = {k: v for k, v in body.model_dump().items() if v is not None}
        update["user_id"] = user["user_id"]
        await _db.notification_prefs.update_one(
            {"user_id": user["user_id"]}, {"$set": update}, upsert=True
        )
        return {"success": True, **update}

    @api.get("/admin/push-status")
    async def push_status(admin=Depends(_get_current_user)):
        """Auth-gated admin status — used by Admin UI to show FCM configuration state."""
        token_count = await _db.push_tokens.count_documents({})
        return {
            "configured": PUSH_ENABLED,
            "status": "live" if PUSH_ENABLED else "demo",
            "registered_devices": token_count,
            "message": "Push notifications active" if PUSH_ENABLED
                      else "FCM Not Configured — upload google-services.json and deploy to activate",
        }
