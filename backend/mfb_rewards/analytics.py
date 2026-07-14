"""MFB Rewards — Analytics + Leaderboards."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import wallet as W

CATEGORIES = ["earners", "referrers", "investors", "traders"]
PERIODS    = ["weekly", "monthly", "all_time"]


def _period_bounds(period: str) -> Optional[datetime]:
    now = datetime.now(timezone.utc)
    if period == "weekly":
        return now - timedelta(days=7)
    if period == "monthly":
        return now - timedelta(days=30)
    return None    # all-time


async def _top_by_source(db, sources: List[str], since: Optional[datetime], limit: int) -> List[Dict[str, Any]]:
    match: Dict[str, Any] = {"source": {"$in": sources}, "amount": {"$gt": 0}}
    if since:
        match["created_at"] = {"$gte": since}
    pipe = [
        {"$match": match},
        {"$group": {"_id": "$user_id", "value": {"$sum": "$amount"}}},
        {"$sort": {"value": -1}},
        {"$limit": limit},
    ]
    result = []
    async for row in db[W.COLL_TX].aggregate(pipe):
        result.append({"user_id": row["_id"], "value": int(row["value"])})
    return result


async def _top_earners(db, since, limit=100):
    match: Dict[str, Any] = {"amount": {"$gt": 0}}
    if since:
        match["created_at"] = {"$gte": since}
    pipe = [
        {"$match": match},
        {"$group": {"_id": "$user_id", "value": {"$sum": "$amount"}}},
        {"$sort": {"value": -1}},
        {"$limit": limit},
    ]
    return [{"user_id": r["_id"], "value": int(r["value"])} async for r in db[W.COLL_TX].aggregate(pipe)]


async def _top_referrers(db, since, limit=100):
    if since:
        return await _top_by_source(db,
                                     ["referral_install", "referral_kyc", "referral_deposit"],
                                     since, limit)
    # all-time: use wallet.referral_count
    cur = db[W.COLL_WALLETS].find({"referral_count": {"$gt": 0}}, {"_id": 0, "user_id": 1, "referral_count": 1}) \
                             .sort("referral_count", -1).limit(limit)
    return [{"user_id": d["user_id"], "value": int(d.get("referral_count", 0))} async for d in cur]


async def _top_investors(db, since, limit=100):
    return await _top_by_source(db, ["mf_invest", "sip_success", "gold_buy"], since, limit)


async def _top_traders(db, since, limit=100):
    return await _top_by_source(db, ["forex_trade", "trading_milestone"], since, limit)


BUILDERS = {
    "earners":   _top_earners,
    "referrers": _top_referrers,
    "investors": _top_investors,
    "traders":   _top_traders,
}


async def rebuild_leaderboard(db, period: str, category: str, limit: int = 100) -> Dict[str, Any]:
    if period not in PERIODS:
        raise ValueError("invalid_period")
    if category not in CATEGORIES:
        raise ValueError("invalid_category")
    since = _period_bounds(period)
    builder = BUILDERS[category]
    rows = await builder(db, since, limit)
    for idx, r in enumerate(rows, start=1):
        r["rank"] = idx
    doc = {
        "period":       period,
        "category":     category,
        "entries":      rows,
        "generated_at": datetime.now(timezone.utc),
    }
    await db[W.COLL_LEADERBOARDS].update_one(
        {"period": period, "category": category},
        {"$set": doc},
        upsert=True,
    )
    return doc


async def rebuild_all(db) -> Dict[str, int]:
    cnt = 0
    for p in PERIODS:
        for c in CATEGORIES:
            await rebuild_leaderboard(db, p, c)
            cnt += 1
    return {"rebuilt": cnt}


async def get_leaderboard(db, period: str, category: str) -> Optional[Dict[str, Any]]:
    doc = await db[W.COLL_LEADERBOARDS].find_one({"period": period, "category": category}, {"_id": 0})
    return doc


# ------------------------- Analytics KPIs ------------------------------
async def kpis(db) -> Dict[str, Any]:
    pipe_issued = [{"$match": {"amount": {"$gt": 0}}},
                    {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]
    pipe_burned = [{"$match": {"amount": {"$lt": 0}}},
                    {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]
    issued = 0
    burned = 0
    async for r in db[W.COLL_TX].aggregate(pipe_issued):
        issued = int(r["total"])
    async for r in db[W.COLL_TX].aggregate(pipe_burned):
        burned = int(abs(r["total"]))

    now = datetime.now(timezone.utc)
    active_users = await db[W.COLL_TX].distinct("user_id",
                                                  {"created_at": {"$gte": now - timedelta(days=30)}})
    wallets = await db[W.COLL_WALLETS].estimated_document_count()
    daily_today = await db[W.COLL_DAILY_REWARDS].count_documents({
        "date": now.date().isoformat()
    })
    achievements_unlocked = await db[W.COLL_ACHIEVEMENTS].estimated_document_count()
    referrals_total = await db[W.COLL_REFERRALS].estimated_document_count()
    active_campaigns = await db[W.COLL_CAMPAIGNS].count_documents({"status": "active"})

    return {
        "total_issued":    issued,
        "total_burned":    burned,
        "circulating":     issued - burned,
        "active_users_30d": len(active_users),
        "total_wallets":   wallets,
        "daily_login_today": daily_today,
        "achievements_unlocked": achievements_unlocked,
        "referrals_total": referrals_total,
        "active_campaigns": active_campaigns,
    }


async def daily_series(db, days: int = 30) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    pipe = [
        {"$match": {"created_at": {"$gte": start}, "amount": {"$gt": 0}}},
        {"$group": {"_id": {
            "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
        }, "issued": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    out = []
    async for r in db[W.COLL_TX].aggregate(pipe):
        out.append({"date": r["_id"], "issued": int(r["issued"]), "count": int(r["count"])})
    return out


async def source_distribution(db) -> List[Dict[str, Any]]:
    pipe = [
        {"$match": {"amount": {"$gt": 0}}},
        {"$group": {"_id": "$source", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ]
    return [{"source": r["_id"], "total": int(r["total"]), "count": int(r["count"])}
            async for r in db[W.COLL_TX].aggregate(pipe)]
