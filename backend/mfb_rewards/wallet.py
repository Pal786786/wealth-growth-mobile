"""MFB Rewards — wallet + settings model helpers.

All DB access is centralised here so tests can mock a single surface.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# ----------------------------- Constants -----------------------------------
COLL_WALLETS       = "mfb_reward_wallets"
COLL_TX            = "mfb_reward_transactions"
COLL_CAMPAIGNS     = "mfb_campaigns"
COLL_REFERRALS     = "mfb_referrals"
COLL_ACHIEVEMENTS  = "mfb_achievements"
COLL_DAILY_REWARDS = "mfb_daily_rewards"
COLL_LEADERBOARDS  = "mfb_leaderboards"
COLL_SETTINGS      = "mfb_reward_settings"

# Default reward rates (INR-denominated events return MFB per ₹100)
DEFAULT_SETTINGS: Dict[str, Any] = {
    "rate.signup":            {"amount": 100,  "unit": "flat",     "description": "Signup bonus"},
    "rate.kyc_complete":      {"amount": 300,  "unit": "flat",     "description": "KYC approval"},
    "rate.wallet_topup":      {"amount": 1,    "unit": "per_100",  "description": "Per ₹100 wallet top-up"},
    "rate.gold_buy":          {"amount": 2,    "unit": "per_100",  "description": "Per ₹100 gold buy"},
    "rate.mf_invest":         {"amount": 3,    "unit": "per_100",  "description": "Per ₹100 mutual fund investment"},
    "rate.sip_success":       {"amount": 150,  "unit": "flat",     "description": "Successful SIP execution"},
    "rate.daily_login":       {"amount": 20,   "unit": "flat",     "description": "Daily login (base day 1)"},
    "rate.referral_install":  {"amount": 500,  "unit": "flat",     "description": "Referred user installs"},
    "rate.referral_kyc":      {"amount": 1000, "unit": "flat",     "description": "Referred user completes KYC"},
    "rate.referral_deposit":  {"amount": 1500, "unit": "flat",     "description": "Referred user first deposit"},
    "rate.forex_trade":       {"amount": 1,    "unit": "per_100",  "description": "Per ₹100 forex trade volume"},
    "rate.trading_milestone": {"amount": 250,  "unit": "flat",     "description": "Trading milestone bonus"},

    # Daily streak curve (day1..day7). Missed day resets to day 1.
    "streak.curve": {"amount": [20, 30, 40, 70, 110, 170, 250], "unit": "vector",
                     "description": "7-day login streak reward curve"},

    # Achievement rewards
    "achievement.first_deposit":    {"amount": 100,  "unit": "flat"},
    "achievement.gold_investor":    {"amount": 200,  "unit": "flat"},
    "achievement.sip_master":       {"amount": 500,  "unit": "flat"},
    "achievement.top_referrer":     {"amount": 2000, "unit": "flat"},
    "achievement.hundred_trades":   {"amount": 1000, "unit": "flat"},
    "achievement.mfb_earned_1000":  {"amount": 500,  "unit": "flat"},
    "achievement.elite_member":     {"amount": 3000, "unit": "flat"},
    "achievement.whale":            {"amount": 5000, "unit": "flat"},
    "achievement.legend":           {"amount": 10000,"unit": "flat"},

    # Global feature flags
    "flag.enabled":            {"value": True,  "description": "Master switch for reward engine"},
    "flag.referrals_enabled":  {"value": True,  "description": "Enable referrals"},
    "flag.streak_enabled":     {"value": True,  "description": "Enable daily streak"},
    "flag.leaderboard_enabled":{"value": True,  "description": "Enable leaderboards"},
}

# Tier thresholds (min_level → tier name & emoji)
TIER_TABLE = [
    (95, "Legend",   "👑"),
    (85, "Whale",    "🐋"),
    (70, "Elite",    "🚀"),
    (50, "Diamond",  "💠"),
    (35, "Platinum", "🔷"),
    (20, "Gold",     "🥇"),
    (10, "Silver",   "🥈"),
    (0,  "Bronze",   "🥉"),
]
LEVEL_CAP = 100


# ----------------------------- Utilities -----------------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def xp_to_level(xp: int) -> int:
    if xp <= 0:
        return 1
    return min(LEVEL_CAP, max(1, int(math.floor(math.sqrt(xp / 100)))))


def level_to_tier(level: int) -> Dict[str, str]:
    for min_lvl, name, emoji in TIER_TABLE:
        if level >= min_lvl:
            return {"name": name, "emoji": emoji, "min_level": min_lvl}
    return {"name": "Bronze", "emoji": "🥉", "min_level": 0}


def next_level_xp(current_xp: int) -> Dict[str, int]:
    lvl = xp_to_level(current_xp)
    next_xp = ((lvl) ** 2) * 100 if lvl < LEVEL_CAP else current_xp
    return {
        "current_level": lvl,
        "current_xp":    current_xp,
        "next_level":    min(LEVEL_CAP, lvl + 1),
        "next_level_xp": next_xp,
        "progress_pct":  0 if next_xp == current_xp else max(0, min(100, int((current_xp / next_xp) * 100))),
    }


# ----------------------------- Settings -----------------------------------
async def seed_default_settings(db) -> Dict[str, int]:
    """Idempotently insert default rate settings; leaves existing keys untouched."""
    coll = db[COLL_SETTINGS]
    inserted = 0
    for key, value in DEFAULT_SETTINGS.items():
        exists = await coll.find_one({"key": key}, {"_id": 1})
        if not exists:
            await coll.insert_one({
                "key": key,
                "value": value,
                "updated_by": "system",
                "updated_at": now_utc(),
            })
            inserted += 1
    return {"seeded": inserted, "total": len(DEFAULT_SETTINGS)}


async def get_setting(db, key: str) -> Optional[Dict[str, Any]]:
    doc = await db[COLL_SETTINGS].find_one({"key": key}, {"_id": 0})
    return doc


async def get_rate(db, key: str) -> Dict[str, Any]:
    doc = await get_setting(db, key)
    if doc:
        return doc.get("value", {})
    return DEFAULT_SETTINGS.get(key, {})


async def set_setting(db, key: str, value: Any, updated_by: str = "admin") -> Dict[str, Any]:
    await db[COLL_SETTINGS].update_one(
        {"key": key},
        {"$set": {"value": value, "updated_by": updated_by, "updated_at": now_utc()},
         "$setOnInsert": {"key": key}},
        upsert=True,
    )
    return {"key": key, "value": value}


async def list_settings(db) -> list:
    cur = db[COLL_SETTINGS].find({}, {"_id": 0}).sort("key", 1)
    return [doc async for doc in cur]


# ----------------------------- Wallet CRUD --------------------------------
def _new_wallet_doc(user_id: str, referral_code: Optional[str] = None) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "balance": 0,
        "lifetime_earned": 0,
        "lifetime_spent": 0,
        "pending_rewards": 0,
        "locked_rewards": 0,
        "referral_count": 0,
        "referral_code": referral_code or f"MFB{user_id[-6:].upper()}",
        "referred_by": None,
        "xp": 0,
        "level": 1,
        "tier": "Bronze",
        "streak_current": 0,
        "streak_best": 0,
        "streak_last_date": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }


async def ensure_wallet(db, user_id: str, *, referred_by: Optional[str] = None,
                       referral_code: Optional[str] = None) -> Dict[str, Any]:
    """Idempotently create-or-return the reward wallet for a user."""
    coll = db[COLL_WALLETS]
    existing = await coll.find_one({"user_id": user_id}, {"_id": 0})
    if existing:
        return existing
    doc = _new_wallet_doc(user_id, referral_code=referral_code)
    if referred_by:
        doc["referred_by"] = referred_by
    try:
        await coll.insert_one(doc)
    except Exception:
        existing = await coll.find_one({"user_id": user_id}, {"_id": 0})
        if existing:
            return existing
        raise
    doc.pop("_id", None)
    return doc


async def get_wallet(db, user_id: str) -> Dict[str, Any]:
    return await ensure_wallet(db, user_id)


async def apply_delta(db, user_id: str, *, delta: int, xp_delta: int = 0) -> Dict[str, Any]:
    """Atomically credit/debit a wallet, updating xp/level/tier snapshots.

    Balance is stored as an integer number of MFB Tokens.
    Passing a negative `delta` performs a spend.
    `xp_delta` (never negative) tracks lifetime XP separately.
    Returns the updated wallet document.
    """
    coll = db[COLL_WALLETS]
    inc: Dict[str, int] = {"balance": int(delta)}
    if delta > 0:
        inc["lifetime_earned"] = int(delta)
    elif delta < 0:
        inc["lifetime_spent"] = int(-delta)
    if xp_delta > 0:
        inc["xp"] = int(xp_delta)

    updated = await coll.find_one_and_update(
        {"user_id": user_id},
        {"$inc": inc, "$set": {"updated_at": now_utc()}},
        return_document=True,
        projection={"_id": 0},
    )
    if not updated:
        # Auto-provision then retry once (edge-case)
        await ensure_wallet(db, user_id)
        updated = await coll.find_one_and_update(
            {"user_id": user_id},
            {"$inc": inc, "$set": {"updated_at": now_utc()}},
            return_document=True,
            projection={"_id": 0},
        )

    # Recompute level/tier
    xp = updated.get("xp", 0)
    lvl = xp_to_level(xp)
    tier = level_to_tier(lvl)["name"]
    if updated.get("level") != lvl or updated.get("tier") != tier:
        await coll.update_one(
            {"user_id": user_id},
            {"$set": {"level": lvl, "tier": tier}},
        )
        updated["level"] = lvl
        updated["tier"] = tier
    return updated


async def inc_referral_count(db, user_id: str, by: int = 1) -> None:
    await db[COLL_WALLETS].update_one({"user_id": user_id},
                                       {"$inc": {"referral_count": by},
                                        "$set": {"updated_at": now_utc()}})


# ----------------------------- Transaction ledger -------------------------
async def record_tx(db, *, user_id: str, amount: int, source: str, reference_id: Optional[str],
                    reason: str, tx_type: str = "credit", balance_after: int = 0,
                    meta: Optional[Dict[str, Any]] = None,
                    idempotency_key: Optional[str] = None) -> Dict[str, Any]:
    """Insert a reward transaction; enforces idempotency via unique index on
    (source, reference_id, user_id) when reference_id is provided.

    Every TX carries the migration-ready fields:
        internal_token_id     – UUID (this record’s canonical ID)
        future_blockchain_id  – None until migration
        migration_status      – "internal"
    """
    doc = {
        "tx_id":                gen_id("rtx"),
        "internal_token_id":    uuid.uuid4().hex,
        "future_blockchain_id": None,
        "migration_status":     "internal",
        "user_id":              user_id,
        "amount":               int(amount),
        "balance_after":        int(balance_after),
        "type":                 tx_type,
        "source":               source,
        "reference_id":         reference_id,
        "idempotency_key":      idempotency_key or (f"{source}:{reference_id}:{user_id}" if reference_id else None),
        "reason":               reason,
        "meta":                 meta or {},
        "status":               "completed",
        "created_at":           now_utc(),
    }
    try:
        await db[COLL_TX].insert_one(doc)
    except Exception as e:
        # Duplicate idempotency key → return existing
        if "E11000" in str(e):
            existing = await db[COLL_TX].find_one({"idempotency_key": doc["idempotency_key"]},
                                                    {"_id": 0})
            if existing:
                return existing
        raise
    doc.pop("_id", None)
    return doc


async def already_awarded(db, user_id: str, source: str, reference_id: str) -> bool:
    key = f"{source}:{reference_id}:{user_id}"
    existing = await db[COLL_TX].find_one({"idempotency_key": key}, {"_id": 1})
    return existing is not None


async def ensure_indexes(db) -> None:
    """Ensure indexes used by the module. Runs on startup + first test."""
    await db[COLL_WALLETS].create_index("user_id", unique=True, background=True)
    await db[COLL_WALLETS].create_index("referral_code", unique=True, sparse=True, background=True)
    await db[COLL_WALLETS].create_index([("lifetime_earned", -1)], background=True)
    await db[COLL_WALLETS].create_index([("xp", -1)], background=True)

    await db[COLL_TX].create_index("tx_id", unique=True, background=True)
    await db[COLL_TX].create_index("internal_token_id", unique=True, background=True)
    await db[COLL_TX].create_index("idempotency_key", unique=True, sparse=True, background=True)
    await db[COLL_TX].create_index([("user_id", 1), ("created_at", -1)], background=True)
    await db[COLL_TX].create_index("source", background=True)

    await db[COLL_CAMPAIGNS].create_index("campaign_id", unique=True, background=True)
    await db[COLL_CAMPAIGNS].create_index("status", background=True)
    await db[COLL_CAMPAIGNS].create_index([("start_date", -1)], background=True)

    await db[COLL_REFERRALS].create_index("referral_id", unique=True, background=True)
    await db[COLL_REFERRALS].create_index("code", background=True)
    await db[COLL_REFERRALS].create_index([("referrer_id", 1), ("status", 1)], background=True)
    await db[COLL_REFERRALS].create_index("referred_id", sparse=True, background=True)

    await db[COLL_ACHIEVEMENTS].create_index([("user_id", 1), ("code", 1)], unique=True, background=True)
    await db[COLL_ACHIEVEMENTS].create_index([("unlocked_at", -1)], background=True)

    await db[COLL_DAILY_REWARDS].create_index([("user_id", 1), ("date", 1)], unique=True, background=True)

    await db[COLL_LEADERBOARDS].create_index([("period", 1), ("category", 1)], unique=True, background=True)
    await db[COLL_SETTINGS].create_index("key", unique=True, background=True)
