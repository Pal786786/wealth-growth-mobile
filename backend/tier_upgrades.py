"""Tier Upgrade detection & notifications.

Fires when a user's loyalty points cross a tier threshold.

Key features:
- Idempotent: stores user.tier_id and only fires on actual upgrade
- Anti-spam: notification & audit only on real tier change (never on downgrades or
  re-entries to a previously-held tier within 24h via a separate cooldown)
- Triggers automatically from award_cashback() — covers recharge, bills, travel,
  insurance, referral bonuses, admin grants, and approved claims
- Persistent tier_upgrades collection enables admin analytics & user history
- Notifies via in-app + push (security_extras.send_push_logged)
- Logs every upgrade to admin_audit for compliance
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger("mfb.tier_upgrades")

_db = None
_get_current_user = None
_get_current_admin = None
_TIERS: List[Dict[str, Any]] = []


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gid() -> str:
    return f"tup_{uuid.uuid4().hex[:12]}"


# ============================================================================
# Tier Benefits Catalogue (richer than rate/color alone)
# ============================================================================
TIER_BENEFITS: Dict[str, Dict[str, Any]] = {
    "bronze": {
        "tagline": "Welcome to the family!",
        "cashback_rate_pct": 0.5,
        "points_multiplier": 1.0,
        "perks": [
            "0.5% cashback on every spend",
            "Basic email support",
            "Birthday wish from us 🎂",
        ],
        "emoji": "🥉",
    },
    "silver": {
        "tagline": "You're moving up — keep going!",
        "cashback_rate_pct": 0.8,
        "points_multiplier": 1.0,
        "perks": [
            "0.8% cashback on every spend",
            "Priority email support",
            "Free virtual debit card",
            "Birthday bonus ₹100",
        ],
        "emoji": "🥈",
    },
    "gold": {
        "tagline": "You've struck Gold! 🌟",
        "cashback_rate_pct": 1.2,
        "points_multiplier": 2.0,
        "perks": [
            "1.2% cashback on every spend",
            "2× points on travel & insurance",
            "24/7 chat support",
            "Birthday bonus ₹250",
            "Lower minimum balance",
        ],
        "emoji": "🥇",
    },
    "platinum": {
        "tagline": "Elite status unlocked! 💎",
        "cashback_rate_pct": 1.8,
        "points_multiplier": 3.0,
        "perks": [
            "1.8% cashback on every spend",
            "3× points on travel & insurance",
            "Dedicated relationship manager",
            "2 free airport lounge visits / yr",
            "Zero ATM withdrawal charges",
            "Birthday bonus ₹500",
        ],
        "emoji": "💎",
    },
    "diamond": {
        "tagline": "The pinnacle of luxury banking 👑",
        "cashback_rate_pct": 2.5,
        "points_multiplier": 5.0,
        "perks": [
            "2.5% cashback on every spend",
            "5× points on travel & insurance",
            "Premium 24/7 concierge service",
            "Unlimited free transfers (IMPS/NEFT/UPI)",
            "Exclusive curated investment products",
            "Unlimited airport lounge access",
            "Birthday bonus ₹1,000",
        ],
        "emoji": "👑",
    },
}


async def _live_tiers() -> List[Dict[str, Any]]:
    """Returns the active tier list — DB-backed via tier_config, fallback to startup _TIERS."""
    try:
        import tier_config as _tc  # type: ignore
        return await _tc.get_tiers()
    except Exception:
        return _TIERS


def _tier_index(tier_id: str, tier_list: Optional[List[Dict[str, Any]]] = None) -> int:
    """Returns 0-based rank index. -1 if unknown."""
    tl = tier_list or _TIERS
    for i, t in enumerate(tl):
        if t["id"] == tier_id:
            return i
    return -1


def _enrich_tier(tier: Dict[str, Any]) -> Dict[str, Any]:
    """For DB-backed tiers, perks are already inside `tier['perks']`. We just compute
    derived display fields (cashback_rate_pct, emoji defaults)."""
    if not tier:
        return {}
    rate_pct = round(float(tier.get("rate", 0)) * 100, 2)
    perks = tier.get("perks") or []
    # Normalize perks to plain strings of only enabled items for mobile display
    perk_strs: List[str] = []
    for p in perks:
        if isinstance(p, str):
            perk_strs.append(p)
        elif isinstance(p, dict) and p.get("enabled", True):
            perk_strs.append(p.get("text", ""))
    return {
        **tier,
        "cashback_rate_pct": rate_pct,
        "points_multiplier": float(tier.get("points_multiplier", 1.0)),
        "tagline": tier.get("tagline", f"You're now {tier.get('name','')}!"),
        "emoji": tier.get("emoji", ""),
        "perks": [p for p in perk_strs if p],
    }


# ============================================================================
# Core: check_and_upgrade
# ============================================================================
async def check_and_upgrade(user_id: str, trigger: str = "transaction",
                            trigger_detail: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Detects tier change and, only if the user moved UP a tier, persists the
    upgrade, notifies the user, and writes an audit log entry.

    Reads tier definitions LIVE from MongoDB (tier_config) so admin edits apply
    instantly without redeploy.

    Returns the upgrade event dict if one was fired, else None.
    """
    if _db is None:
        return None
    tier_list = await _live_tiers()
    if not tier_list:
        return None
    u = await _db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, "user_id": 1, "full_name": 1, "reward_points": 1, "tier_id": 1, "last_tier_event_at": 1},
    )
    if not u:
        return None

    points = int(u.get("reward_points", 0) or 0)
    # Compute new tier from points
    new_tier: Dict[str, Any] = tier_list[0]
    for t in tier_list:
        if points >= t["min"]:
            new_tier = t

    old_tier_id = u.get("tier_id") or "bronze"
    new_tier_id = new_tier["id"]

    if old_tier_id != new_tier_id:
        await _db.users.update_one(
            {"user_id": user_id},
            {"$set": {"tier_id": new_tier_id, "tier_updated_at": _now()}},
        )

    if _tier_index(new_tier_id, tier_list) <= _tier_index(old_tier_id, tier_list):
        return None

    recent_dup = await _db.tier_upgrades.find_one(
        {"user_id": user_id, "new_tier_id": new_tier_id,
         "at": {"$gte": _now() - timedelta(hours=24)}},
        {"_id": 1},
    )
    if recent_dup:
        return None

    old_tier_full = next((t for t in tier_list if t["id"] == old_tier_id), tier_list[0])
    enriched_new = _enrich_tier(new_tier)
    enriched_old = _enrich_tier(old_tier_full)

    upgrade_id = _gid()
    event = {
        "upgrade_id": upgrade_id,
        "user_id": user_id,
        "user_name": u.get("full_name", ""),
        "old_tier_id": old_tier_id,
        "old_tier_name": old_tier_full["name"],
        "new_tier_id": new_tier_id,
        "new_tier_name": new_tier["name"],
        "points_at_upgrade": points,
        "trigger": trigger,
        "trigger_detail": trigger_detail or "",
        "at": _now(),
        "seen_by_user": False,
    }
    await _db.tier_upgrades.insert_one(event)

    # In-app notification
    await _db.notifications.insert_one({
        "notif_id": f"nf_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "title": f"You're now {new_tier['name']} {enriched_new.get('emoji', '')}",
        "body": enriched_new.get("tagline", f"You've been upgraded to {new_tier['name']}!"),
        "deeplink": f"/tier-upgrade?id={upgrade_id}",
        "category": "tier_upgrade",
        "upgrade_id": upgrade_id,
        "read": False,
        "created_at": _now(),
    })

    # Push (best-effort)
    try:
        import security_extras  # type: ignore
        await security_extras.send_push_logged(
            recipients=[user_id],
            data={
                "title": f"Congrats! You're {new_tier['name']} {enriched_new.get('emoji', '')}",
                "message": f"Tier upgrade unlocked: {enriched_new.get('cashback_rate_pct', 0)}% cashback + new perks.",
                "action_url": f"/tier-upgrade?id={upgrade_id}",
                "category": "tier_upgrade",
                "upgrade_id": upgrade_id,
            },
            batch_id=f"tier-{upgrade_id}",
        )
    except Exception as e:
        logger.warning(f"Tier upgrade push failed for {user_id}: {e}")

    # Audit log (best-effort, never blocks the upgrade)
    try:
        from admin import _log_action  # type: ignore
        await _log_action(
            admin_id="__system__",
            action="tier.upgrade",
            target=user_id,
            meta={
                "old_tier": old_tier_id, "new_tier": new_tier_id,
                "trigger": trigger, "points": points,
            },
        )
    except Exception:
        pass

    return event


# ============================================================================
# User endpoints
# ============================================================================
def _attach_user_routes(api: APIRouter):
    r = APIRouter(prefix="/rewards/tier", tags=["tier-upgrades"])

    @r.get("/benefits")
    async def all_tier_benefits():
        live = await _live_tiers()
        return {"tiers": [_enrich_tier(t) for t in live]}

    @r.get("/history")
    async def my_upgrade_history(user: Dict[str, Any] = Depends(_get_current_user), limit: int = 20):
        rows = await _db.tier_upgrades.find(
            {"user_id": user["user_id"]},
            {"_id": 0},
        ).sort("at", -1).limit(min(limit, 100)).to_list(min(limit, 100))
        return {"items": rows, "total": len(rows)}

    @r.get("/upgrade/{upgrade_id}")
    async def upgrade_detail(upgrade_id: str, user: Dict[str, Any] = Depends(_get_current_user)):
        doc = await _db.tier_upgrades.find_one({"upgrade_id": upgrade_id, "user_id": user["user_id"]}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Upgrade event not found")
        live = await _live_tiers()
        old_full = next((t for t in live if t["id"] == doc["old_tier_id"]), live[0])
        new_full = next((t for t in live if t["id"] == doc["new_tier_id"]), live[0])
        doc["old_tier"] = _enrich_tier(old_full)
        doc["new_tier"] = _enrich_tier(new_full)
        await _db.tier_upgrades.update_one({"upgrade_id": upgrade_id}, {"$set": {"seen_by_user": True}})
        return doc

    api.include_router(r)


# ============================================================================
# Admin endpoints
# ============================================================================
def _attach_admin_routes(api: APIRouter):
    r = APIRouter(prefix="/admin/tier-upgrades", tags=["admin-tier-upgrades"])

    def _ensure(adm):
        if adm["role"] not in ("super_admin", "admin", "finance_manager", "support_manager"):
            raise HTTPException(403, "Forbidden")

    @r.get("")
    async def list_upgrades(adm=Depends(_get_current_admin),
                            tier: Optional[str] = None, search: Optional[str] = None,
                            limit: int = 200):
        _ensure(adm)
        q: Dict[str, Any] = {}
        if tier:
            q["new_tier_id"] = tier
        if search:
            q["$or"] = [
                {"user_name": {"$regex": search, "$options": "i"}},
                {"user_id": {"$regex": search, "$options": "i"}},
            ]
        rows = await _db.tier_upgrades.find(q, {"_id": 0}).sort("at", -1).limit(min(limit, 500)).to_list(min(limit, 500))
        return {"items": rows, "total": len(rows)}

    @r.get("/analytics")
    async def analytics(adm=Depends(_get_current_admin)):
        _ensure(adm)
        # Users per tier (computed live from users.tier_id; default bronze)
        users_total = await _db.users.count_documents({})
        per_tier: Dict[str, int] = {t["id"]: 0 for t in _TIERS}
        agg = await _db.users.aggregate([
            {"$group": {"_id": {"$ifNull": ["$tier_id", "bronze"]}, "c": {"$sum": 1}}},
        ]).to_list(20)
        for a in agg:
            per_tier[a["_id"]] = a["c"]
        # Tier migration counts
        mig_agg = await _db.tier_upgrades.aggregate([
            {"$group": {"_id": {"old": "$old_tier_id", "new": "$new_tier_id"}, "c": {"$sum": 1}}},
        ]).to_list(50)
        migrations = [{"old": m["_id"]["old"], "new": m["_id"]["new"], "count": m["c"]} for m in mig_agg]
        # Last 30 days trend (daily counts)
        since = _now() - timedelta(days=30)
        trend_agg = await _db.tier_upgrades.aggregate([
            {"$match": {"at": {"$gte": since}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$at"}},
                "c": {"$sum": 1},
            }},
            {"$sort": {"_id": 1}},
        ]).to_list(60)
        trend = [{"date": t["_id"], "count": t["c"]} for t in trend_agg]
        # Top triggers
        trig_agg = await _db.tier_upgrades.aggregate([
            {"$group": {"_id": "$trigger", "c": {"$sum": 1}}},
            {"$sort": {"c": -1}},
        ]).to_list(20)
        return {
            "users_total": users_total,
            "users_per_tier": [
                {"tier_id": t["id"], "tier_name": t["name"], "count": per_tier.get(t["id"], 0), "color": t.get("color")}
                for t in (await _live_tiers())
            ],
            "migrations": migrations,
            "trend_30d": trend,
            "by_trigger": [{"trigger": tr["_id"] or "unknown", "count": tr["c"]} for tr in trig_agg],
            "total_upgrades": await _db.tier_upgrades.count_documents({}),
            "tiers": [_enrich_tier(t) for t in (await _live_tiers())],
        }

    @r.get("/user/{user_id}")
    async def user_tier_history(user_id: str, adm=Depends(_get_current_admin)):
        _ensure(adm)
        u = await _db.users.find_one({"user_id": user_id}, {"_id": 0, "user_id": 1, "full_name": 1, "reward_points": 1, "tier_id": 1})
        if not u:
            raise HTTPException(404, "User not found")
        rows = await _db.tier_upgrades.find({"user_id": user_id}, {"_id": 0}).sort("at", -1).limit(50).to_list(50)
        live = await _live_tiers()
        cur_tier = next((t for t in live if t["id"] == (u.get("tier_id") or "bronze")), live[0])
        return {
            "user": u,
            "current_tier": _enrich_tier(cur_tier),
            "history": rows,
            "total_upgrades": len(rows),
        }

    api.include_router(r)


# ============================================================================
# attach
# ============================================================================
def attach(api: APIRouter, db, get_current_user_fn, get_current_admin_fn, tiers_list: List[Dict[str, Any]]):
    global _db, _get_current_user, _get_current_admin, _TIERS
    _db = db
    _get_current_user = get_current_user_fn
    _get_current_admin = get_current_admin_fn
    _TIERS = tiers_list
    _attach_user_routes(api)
    _attach_admin_routes(api)
