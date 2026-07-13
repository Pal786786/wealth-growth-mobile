"""Sprint 12.3 · Phase A — Enhanced finance audit trail.

Immutable audit log with IP / device / actor / before-value / after-value /
action / reference. Wraps the existing `admin_audit_logs` collection with a
richer schema stored in `finance_audit_trail`.

Never deleted. Only inserted.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import Request

from .engine import AUDIT_COLL

logger = logging.getLogger("finance_ledger.audit")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _client_meta(request: Optional[Request]) -> Dict[str, Any]:
    if not request:
        return {}
    try:
        client = request.client.host if request.client else None
    except Exception:
        client = None
    hdr = request.headers
    fwd = hdr.get("x-forwarded-for") or hdr.get("cf-connecting-ip") or ""
    ip = fwd.split(",")[0].strip() if fwd else client
    return {
        "ip": ip,
        "user_agent": hdr.get("user-agent"),
        "device_id": hdr.get("x-device-id") or hdr.get("x-client-id"),
        "app_version": hdr.get("x-app-version"),
        "platform": hdr.get("x-platform"),
    }


class AuditTrail:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        for spec, name in [
            ([("actor_id", 1), ("timestamp", -1)], "fa_actor_ts"),
            ([("resource_type", 1), ("resource_id", 1)], "fa_resource"),
            ([("action", 1), ("timestamp", -1)], "fa_action_ts"),
            ([("timestamp", -1)], "fa_ts"),
        ]:
            try:
                await self.db[AUDIT_COLL].create_index(spec, name=name)
            except Exception:
                pass

    async def record(
        self,
        *,
        actor_id: str,
        actor_type: str,     # 'user' | 'admin' | 'system'
        action: str,          # e.g. 'wallet.credit', 'withdrawal.approve'
        resource_type: str,
        resource_id: Optional[str] = None,
        before: Optional[Dict[str, Any]] = None,
        after: Optional[Dict[str, Any]] = None,
        reference_id: Optional[str] = None,
        request: Optional[Request] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        meta = _client_meta(request)
        row = {
            "actor_id": actor_id, "actor_type": actor_type,
            "action": action,
            "resource_type": resource_type, "resource_id": resource_id,
            "reference_id": reference_id,
            "before": before, "after": after,
            "ip": meta.get("ip"),
            "user_agent": meta.get("user_agent"),
            "device_id": meta.get("device_id"),
            "app_version": meta.get("app_version"),
            "platform": meta.get("platform"),
            "metadata": metadata or {},
            "timestamp": _now(),
        }
        try:
            await self.db[AUDIT_COLL].insert_one(row)
        except Exception as e:
            logger.warning("audit record failed: %s", e)
        return row

    async def query(
        self, *, actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action_prefix: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 100, skip: int = 0,
    ) -> Dict[str, Any]:
        q: Dict[str, Any] = {}
        if actor_id: q["actor_id"] = actor_id
        if resource_type: q["resource_type"] = resource_type
        if resource_id: q["resource_id"] = resource_id
        if action_prefix:
            q["action"] = {"$regex": f"^{action_prefix}"}
        if date_from or date_to:
            q["timestamp"] = {}
            if date_from:
                q["timestamp"]["$gte"] = date_from
            if date_to:
                q["timestamp"]["$lte"] = date_to
        total = await self.db[AUDIT_COLL].count_documents(q)
        rows = await self.db[AUDIT_COLL].find(q, {"_id": 0}).sort("timestamp", -1)\
                                          .skip(skip).limit(limit).to_list(limit)
        return {"items": rows, "total": total}


_TRAIL: Optional[AuditTrail] = None


def set_default_trail(t: AuditTrail) -> None:
    global _TRAIL
    _TRAIL = t


def get_default_trail() -> Optional[AuditTrail]:
    return _TRAIL


async def audit(**kwargs) -> Optional[Dict[str, Any]]:
    if _TRAIL is None:
        return None
    return await _TRAIL.record(**kwargs)
