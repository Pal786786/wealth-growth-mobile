"""Bank verification engine (Sprint 12.1) — provider dispatch, config, audit,
primary-account management. All state changes flow through this module so
existing withdrawal_module.py is untouched."""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .providers import resolve_provider, get_provider, REGISTRY

logger = logging.getLogger("bank_verification.engine")

CONFIG_COLL = "bank_verification_config"
HIST_COLL = "bank_verification_history"
AUDIT_COLL = "bank_verification_audit"

DEFAULT_CFG = {
    "provider": "demo",
    "env": "sandbox",         # sandbox | production
    "client_id": "",
    "client_secret": "",
    "webhook_secret": "",
    "min_name_match_score": 60,
    "auto_switch_on_failure": True,
    "dedup_window_hours": 24,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: Dict[str, Any]) -> Dict[str, Any]:
    d.pop("_id", None)
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return d


def _uid(p: str) -> str: return f"{p}_{uuid.uuid4().hex[:12]}"


class BankVerificationEngine:
    def __init__(self, db):
        self.db = db
        self.config: Dict[str, Any] = dict(DEFAULT_CFG)

    async def init_config(self):
        doc = await self.db[CONFIG_COLL].find_one({"_id": "active"}) or {}
        for k, v in doc.items():
            if k != "_id":
                self.config[k] = v
        await self.db[CONFIG_COLL].update_one(
            {"_id": "active"}, {"$setOnInsert": {**self.config, "created_at": _now()}}, upsert=True)

    async def ensure_indexes(self):
        try:
            await self.db[HIST_COLL].create_index("verification_id", unique=True)
            await self.db[HIST_COLL].create_index([("user_id", 1), ("created_at", -1)])
            await self.db[HIST_COLL].create_index([("bank_id", 1), ("created_at", -1)])
            await self.db[HIST_COLL].create_index("status")
            await self.db.bank_accounts.create_index([("user_id", 1), ("is_primary", 1)])
        except Exception as e:
            logger.warning("index warning: %s", e)

    def public_config(self) -> Dict[str, Any]:
        return {
            "provider": self.config.get("provider"),
            "env": self.config.get("env"),
            "configured": bool(self.config.get("client_id") and self.config.get("client_secret")),
            "min_name_match_score": self.config.get("min_name_match_score", 60),
        }

    async def patch_config(self, patch: Dict[str, Any], admin_id: str) -> Dict[str, Any]:
        allowed = set(DEFAULT_CFG.keys())
        upd = {k: v for k, v in patch.items() if k in allowed}
        if not upd: return self.config
        upd["updated_at"] = _now()
        await self.db[CONFIG_COLL].update_one({"_id": "active"}, {"$set": upd}, upsert=True)
        for k, v in upd.items():
            if k != "updated_at": self.config[k] = v
        await self._audit(admin_id, "admin", "bv.config.update", after={k: v for k, v in upd.items() if k != "client_secret"})
        return self.config

    async def test_connection(self) -> Dict[str, Any]:
        """Fire a dry-run request against the configured provider. For demo
        this always returns ok. For Cashfree this hits their sandbox with a
        stub account number and reports the result."""
        prov = resolve_provider(self.config)
        try:
            if prov.name == "cashfree":
                res = await prov.verify(account_number="1234567890", ifsc="HDFC0001234",
                                          holder_name="TEST")
                # We only care that credentials worked; sandbox may return INVALID.
                return {"ok": True, "provider": prov.name, "reachable": True,
                        "note": "Provider responded", "raw": res.get("raw")}
            return {"ok": True, "provider": prov.name, "reachable": True,
                    "note": "Demo provider — always reachable"}
        except Exception as e:
            return {"ok": False, "provider": prov.name, "reachable": False,
                    "error": str(e)}

    async def verify_bank(self, user_id: str, bank_id: str, force: bool = False) -> Dict[str, Any]:
        """Verify a bank account belonging to the given user via penny drop.
        Prevents duplicate verifications within the configured dedup window."""
        bank = await self.db.bank_accounts.find_one(
            {"bank_id": bank_id, "user_id": user_id, "deleted": {"$ne": True}})
        if not bank:
            raise ValueError("bank account not found")
        if bank.get("verified") and not force:
            return {"ok": True, "already_verified": True, "bank_id": bank_id,
                    "status": "verified"}
        # Dedup: last successful/pending attempt inside dedup window?
        if not force:
            window_h = int(self.config.get("dedup_window_hours", 24))
            from datetime import timedelta
            since = _now() - timedelta(hours=window_h)
            recent = await self.db[HIST_COLL].find_one(
                {"bank_id": bank_id, "created_at": {"$gte": since}},
                sort=[("created_at", -1)])
            if recent and recent.get("status") in ("verified", "pending"):
                r = dict(recent); r.pop("_id", None)
                return {"ok": True, "duplicate": True, "bank_id": bank_id,
                        "status": recent["status"], "history_id": recent["verification_id"],
                        "verified_at": (recent.get("created_at").isoformat() if isinstance(recent.get("created_at"), datetime) else recent.get("created_at"))}

        prov = resolve_provider(self.config)
        try:
            res = await prov.verify(
                account_number=bank["account_number"],
                ifsc=bank["ifsc"], holder_name=bank["holder_name"])
        except Exception as e:
            res = {"ok": False, "status": "error", "reason": str(e),
                   "provider": prov.name, "raw": {"error": str(e)},
                   "matched_name": None, "name_match_score": 0, "reference_id": None}

        # Post-process: name-match score gate
        min_score = int(self.config.get("min_name_match_score", 60))
        passes = bool(res.get("ok")) and int(res.get("name_match_score") or 0) >= min_score
        final_status = "verified" if passes else ("failed" if res.get("status") in ("failed", "invalid", "error") else "pending")

        hist = {
            "verification_id": _uid("bv"),
            "user_id": user_id,
            "bank_id": bank_id,
            "account_masked": (bank["account_number"][-4:] if bank.get("account_number") else ""),
            "ifsc": bank.get("ifsc"),
            "holder_name": bank.get("holder_name"),
            "provider": prov.name,
            "status": final_status,
            "matched_name": res.get("matched_name"),
            "name_match_score": res.get("name_match_score"),
            "reason": res.get("reason"),
            "reference_id": res.get("reference_id"),
            "raw": res.get("raw"),
            "created_at": _now(),
        }
        await self.db[HIST_COLL].insert_one(hist)

        # Update the bank account record with verification outcome
        upd: Dict[str, Any] = {"last_verification_id": hist["verification_id"],
                                "last_verification_status": final_status,
                                "last_verified_provider": prov.name,
                                "last_verified_at": _now()}
        if final_status == "verified":
            upd.update({
                "verified": True,
                "verification_method": f"penny_drop_{prov.name}",
                "verified_at": _now(),
                "verified_by": "system_penny_drop",
                "name_at_bank": res.get("matched_name"),
                "name_match_score": res.get("name_match_score"),
                "provider_reference_id": res.get("reference_id"),
            })
        await self.db.bank_accounts.update_one({"bank_id": bank_id}, {"$set": upd})
        await self._audit(user_id, "user", f"bv.verify.{final_status}", target=bank_id,
                            after={"status": final_status, "provider": prov.name,
                                    "score": res.get("name_match_score")})

        return {"ok": passes, "bank_id": bank_id, "status": final_status,
                "verification_id": hist["verification_id"],
                "provider": prov.name,
                "matched_name": res.get("matched_name"),
                "name_match_score": res.get("name_match_score"),
                "reference_id": res.get("reference_id"),
                "reason": res.get("reason")}

    async def set_primary(self, user_id: str, bank_id: str) -> Dict[str, Any]:
        bank = await self.db.bank_accounts.find_one(
            {"bank_id": bank_id, "user_id": user_id, "deleted": {"$ne": True}})
        if not bank: raise ValueError("bank account not found")
        if not bank.get("verified"):
            raise ValueError("account must be verified before becoming primary")
        # Unset any existing primary
        await self.db.bank_accounts.update_many(
            {"user_id": user_id, "is_primary": True},
            {"$set": {"is_primary": False}})
        await self.db.bank_accounts.update_one(
            {"bank_id": bank_id, "user_id": user_id},
            {"$set": {"is_primary": True, "primary_set_at": _now()}})
        await self._audit(user_id, "user", "bv.primary.set", target=bank_id)
        return {"ok": True, "bank_id": bank_id, "is_primary": True}

    async def history(self, user_id: Optional[str] = None, bank_id: Optional[str] = None,
                       limit: int = 100, skip: int = 0) -> List[Dict[str, Any]]:
        f: Dict[str, Any] = {}
        if user_id: f["user_id"] = user_id
        if bank_id: f["bank_id"] = bank_id
        cur = self.db[HIST_COLL].find(f, {"_id": 0, "raw": 0}).sort("created_at", -1).skip(skip).limit(limit)
        return [_iso(d) async for d in cur]

    async def _audit(self, actor_id: str, actor_type: str, action: str,
                      target: Optional[str] = None, after: Optional[Dict[str, Any]] = None):
        try:
            await self.db[AUDIT_COLL].insert_one({
                "audit_id": _uid("bva"), "actor_id": actor_id, "actor_type": actor_type,
                "action": action, "target": target, "after": after or {}, "at": _now(),
            })
        except Exception: pass
