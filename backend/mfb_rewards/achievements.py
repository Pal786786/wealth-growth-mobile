"""MFB Rewards — Achievements & Badges."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from . import wallet as W


# Definition table: code -> (title, description, evaluator key, tier)
BADGES: List[Dict[str, Any]] = [
    {"code": "first_deposit",     "title": "First Deposit",     "emoji": "💰", "tier": 1},
    {"code": "gold_investor",     "title": "Gold Investor",     "emoji": "🥇", "tier": 1},
    {"code": "sip_master",        "title": "SIP Master",         "emoji": "📈", "tier": 2},
    {"code": "top_referrer",      "title": "Top Referrer",      "emoji": "🤝", "tier": 2},
    {"code": "hundred_trades",    "title": "100 Trades",         "emoji": "📊", "tier": 3},
    {"code": "mfb_earned_1000",   "title": "1000 MFB Earned",    "emoji": "🪙", "tier": 2},
    {"code": "elite_member",      "title": "Elite Member",       "emoji": "🚀", "tier": 4},
    {"code": "whale",             "title": "Whale",              "emoji": "🐋", "tier": 4},
    {"code": "legend",            "title": "Legend",             "emoji": "👑", "tier": 5},
]


def list_definitions() -> List[Dict[str, Any]]:
    return list(BADGES)


async def already_unlocked(db, user_id: str, code: str) -> bool:
    doc = await db[W.COLL_ACHIEVEMENTS].find_one({"user_id": user_id, "code": code}, {"_id": 1})
    return doc is not None


async def unlock(db, user_id: str, code: str, *, reward: int = 0) -> Dict[str, Any]:
    if await already_unlocked(db, user_id, code):
        return {"skipped": True, "reason": "already_unlocked", "code": code}
    doc = {
        "achievement_id": W.gen_id("ach"),
        "user_id":        user_id,
        "code":           code,
        "reward_amount":  int(reward),
        "unlocked_at":    datetime.now(timezone.utc),
    }
    try:
        await db[W.COLL_ACHIEVEMENTS].insert_one(doc)
    except Exception as e:
        if "E11000" in str(e):
            return {"skipped": True, "reason": "already_unlocked", "code": code}
        raise
    doc.pop("_id", None)
    return doc


async def _count_source(db, user_id: str, source: str) -> int:
    return await db[W.COLL_TX].count_documents({"user_id": user_id, "source": source, "amount": {"$gt": 0}})


async def _count_trades(db, user_id: str) -> int:
    return await db[W.COLL_TX].count_documents({
        "user_id": user_id,
        "source": {"$in": ["wallet_topup", "gold_buy", "mf_invest", "sip_success", "forex_trade"]},
        "amount": {"$gt": 0},
    })


async def evaluate(db, user_id: str) -> List[Dict[str, Any]]:
    """Idempotently unlock any achievements the user now qualifies for.

    Returns list of newly unlocked docs. Called after every reward event.
    """
    from . import engine  # local import to avoid cycle
    newly: List[Dict[str, Any]] = []
    w = await W.get_wallet(db, user_id)

    async def _do(code: str, condition: bool):
        if not condition or await already_unlocked(db, user_id, code):
            return
        rate = await W.get_rate(db, f"achievement.{code}")
        reward = int(rate.get("amount", 0)) if rate else 0
        u = await unlock(db, user_id, code, reward=reward)
        if u.get("skipped"):
            return
        if reward > 0:
            await engine.award(user_id, f"achievement.{code}", u["achievement_id"],
                                amount=reward, reason=f"Achievement: {code}")
        newly.append(u)

    await _do("first_deposit",   await _count_source(db, user_id, "wallet_topup") >= 1)
    await _do("gold_investor",   await _count_source(db, user_id, "gold_buy")     >= 1)
    await _do("sip_master",      await _count_source(db, user_id, "sip_success")  >= 3)
    await _do("top_referrer",    int(w.get("referral_count", 0))                  >= 10)
    await _do("hundred_trades",  await _count_trades(db, user_id)                 >= 100)
    await _do("mfb_earned_1000", int(w.get("lifetime_earned", 0))                 >= 1000)
    await _do("elite_member",    int(w.get("level", 1))                           >= 70)
    await _do("whale",            int(w.get("level", 1))                           >= 85)
    await _do("legend",           int(w.get("level", 1))                           >= 95)

    return newly


async def list_user_badges(db, user_id: str) -> List[Dict[str, Any]]:
    cur = db[W.COLL_ACHIEVEMENTS].find({"user_id": user_id}, {"_id": 0}).sort("unlocked_at", -1)
    unlocked = {d["code"]: d async for d in cur}
    result = []
    for b in BADGES:
        u = unlocked.get(b["code"])
        result.append({
            **b,
            "unlocked":    bool(u),
            "unlocked_at": u["unlocked_at"] if u else None,
            "reward":     (u or {}).get("reward_amount", 0),
        })
    return result
