"""Super-app modules: Travel (Bus/Train + Cancellation), Insurance (Calculator + Compare),
Rewards (Cashback Engine + Admin Controls).

All modules operate in DEMO mode using realistic data — no external API keys required.
Demo catalogs live in MongoDB so admins can edit them without code changes.
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

_db = None
_get_current_user = None
_add_tx = None
_logger = None


def _now():
    return datetime.now(timezone.utc)


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# =========================================================================
# Demo Catalogs (seeded on startup if collection is empty)
# =========================================================================

BUSES_SEED = [
    {"id": "bus_001", "operator": "VRL Travels", "type": "AC Sleeper", "from": "Bengaluru", "to": "Hyderabad",
     "depart": "21:30", "arrive": "06:45", "duration": "9h 15m", "price": 1299, "seats_left": 12, "rating": 4.4},
    {"id": "bus_002", "operator": "SRS Travels", "type": "Volvo AC", "from": "Mumbai", "to": "Pune",
     "depart": "07:00", "arrive": "10:30", "duration": "3h 30m", "price": 449, "seats_left": 8, "rating": 4.2},
    {"id": "bus_003", "operator": "RedBus Express", "type": "Non-AC Sleeper", "from": "Delhi", "to": "Jaipur",
     "depart": "23:00", "arrive": "05:15", "duration": "6h 15m", "price": 799, "seats_left": 22, "rating": 4.1},
    {"id": "bus_004", "operator": "KSRTC Airavat", "type": "Volvo Multi-Axle", "from": "Bengaluru", "to": "Chennai",
     "depart": "22:00", "arrive": "05:00", "duration": "7h", "price": 999, "seats_left": 5, "rating": 4.5},
    {"id": "bus_005", "operator": "Orange Travels", "type": "AC Seater", "from": "Kolkata", "to": "Bhubaneswar",
     "depart": "20:30", "arrive": "05:00", "duration": "8h 30m", "price": 899, "seats_left": 14, "rating": 4.0},
]

TRAINS_SEED = [
    {"id": "trn_001", "number": "12951", "name": "Mumbai Rajdhani", "from": "Mumbai Central", "to": "New Delhi",
     "depart": "16:55", "arrive": "08:35+1", "duration": "15h 40m", "classes": ["3A", "2A", "1A"],
     "prices": {"3A": 2380, "2A": 3415, "1A": 5810}, "available": True, "rating": 4.6},
    {"id": "trn_002", "number": "12259", "name": "Sealdah Duronto", "from": "Sealdah", "to": "New Delhi",
     "depart": "20:05", "arrive": "12:05+1", "duration": "16h", "classes": ["3A", "2A", "1A"],
     "prices": {"3A": 1985, "2A": 2890, "1A": 4925}, "available": True, "rating": 4.4},
    {"id": "trn_003", "number": "22691", "name": "Bengaluru Rajdhani", "from": "KSR Bengaluru", "to": "Hazrat Nizamuddin",
     "depart": "20:00", "arrive": "05:55+2", "duration": "33h 55m", "classes": ["3A", "2A", "1A"],
     "prices": {"3A": 3245, "2A": 4720, "1A": 8040}, "available": True, "rating": 4.5},
    {"id": "trn_004", "number": "12009", "name": "Shatabdi Express", "from": "Mumbai Central", "to": "Ahmedabad",
     "depart": "06:25", "arrive": "13:25", "duration": "7h", "classes": ["CC", "EC"],
     "prices": {"CC": 970, "EC": 1855}, "available": True, "rating": 4.7},
    {"id": "trn_005", "number": "12626", "name": "Kerala Express", "from": "Thiruvananthapuram", "to": "New Delhi",
     "depart": "11:15", "arrive": "20:50+2", "duration": "57h 35m", "classes": ["SL", "3A", "2A"],
     "prices": {"SL": 850, "3A": 2275, "2A": 3275}, "available": True, "rating": 4.0},
]


async def seed_demo_catalogs():
    """Seed bus & train demo data once if collection is empty."""
    if await _db.buses.count_documents({}) == 0:
        await _db.buses.insert_many([{**b, "_seed": True} for b in BUSES_SEED])
    if await _db.trains.count_documents({}) == 0:
        await _db.trains.insert_many([{**t, "_seed": True} for t in TRAINS_SEED])


# =========================================================================
# TRAVEL EXTENSIONS — Bus / Train / Cancellation
# =========================================================================

def _public_bus(b): return {k: v for k, v in b.items() if k not in ("_id", "_seed")}
def _public_train(t): return {k: v for k, v in t.items() if k not in ("_id", "_seed")}


class CancelReq(BaseModel):
    reason: Optional[str] = "User cancelled"


def _attach_travel(api: APIRouter):
    travel = APIRouter(prefix="/travel", tags=["travel-extra"])

    @travel.get("/buses")
    async def list_buses(from_loc: Optional[str] = None, to_loc: Optional[str] = None):
        q: Dict[str, Any] = {}
        if from_loc:
            q["from"] = {"$regex": f"^{from_loc}$", "$options": "i"}
        if to_loc:
            q["to"] = {"$regex": f"^{to_loc}$", "$options": "i"}
        rows = await _db.buses.find(q, {"_id": 0, "_seed": 0}).to_list(100)
        return rows or [_public_bus(b) for b in BUSES_SEED]

    @travel.get("/trains")
    async def list_trains(from_loc: Optional[str] = None, to_loc: Optional[str] = None):
        q: Dict[str, Any] = {}
        if from_loc:
            q["from"] = {"$regex": from_loc, "$options": "i"}
        if to_loc:
            q["to"] = {"$regex": to_loc, "$options": "i"}
        rows = await _db.trains.find(q, {"_id": 0, "_seed": 0}).to_list(100)
        return rows or [_public_train(t) for t in TRAINS_SEED]

    @travel.post("/cancel/{booking_id}")
    async def cancel_booking(booking_id: str, req: CancelReq, user: Dict[str, Any] = Depends(_get_current_user)):
        bk = await _db.bookings.find_one({"booking_id": booking_id, "user_id": user["user_id"]}, {"_id": 0})
        if not bk:
            raise HTTPException(status_code=404, detail="Booking not found")
        if bk["status"] == "cancelled":
            raise HTTPException(status_code=400, detail="Already cancelled")
        # Refund policy — 90% if cancelled >= 24h before travel, 50% otherwise
        try:
            tdate = datetime.fromisoformat(bk["travel_date"])
        except Exception:
            tdate = _now() + timedelta(days=7)
        hrs_left = (tdate - _now().replace(tzinfo=None)).total_seconds() / 3600
        refund_pct = 0.9 if hrs_left >= 24 else 0.5
        refund_amt = round(bk["amount"] * refund_pct, 2)

        await _db.bookings.update_one(
            {"booking_id": booking_id},
            {"$set": {"status": "cancelled", "cancelled_at": _now(),
                      "refund_amount": refund_amt, "refund_pct": refund_pct,
                      "cancel_reason": req.reason}},
        )
        await _db.wallets.update_one({"user_id": user["user_id"]}, {"$inc": {"balance": refund_amt}})
        if _add_tx:
            await _add_tx(user["user_id"], "credit", "refund", refund_amt,
                          f"Refund: {bk['title']} ({int(refund_pct*100)}%)", "success", bk["title"])
        return {
            "success": True, "booking_id": booking_id, "status": "cancelled",
            "refund_amount": refund_amt, "refund_pct": int(refund_pct * 100),
            "message": f"Refund of ₹{refund_amt:.0f} ({int(refund_pct*100)}%) credited to wallet",
        }

    api.include_router(travel)


# =========================================================================
# INSURANCE EXTENSIONS — Premium Calculator + Comparison
# =========================================================================

class QuoteReq(BaseModel):
    plan_type: str   # health|life|motor|travel
    age: Optional[int] = 30
    cover: Optional[float] = 500000
    sum_assured: Optional[float] = None
    smoker: Optional[bool] = False
    vehicle_age: Optional[int] = 3
    trip_days: Optional[int] = 7


def _attach_insurance(api: APIRouter):
    ins = APIRouter(prefix="/insurance", tags=["insurance-extra"])

    @ins.post("/quote")
    async def premium_quote(req: QuoteReq):
        """Returns estimated annual premium for given inputs. Pure demo formula."""
        cover = float(req.cover or req.sum_assured or 500000)
        pt = req.plan_type.lower()
        base = 0.0
        breakdown: List[Dict[str, Any]] = []

        if pt == "health":
            base = cover * 0.012  # 1.2% base
            age_loading = 0
            if req.age and req.age > 35:
                age_loading = base * ((req.age - 35) * 0.025)
            smoker_loading = base * 0.20 if req.smoker else 0
            base += age_loading + smoker_loading
            breakdown = [
                {"label": "Base premium", "amount": round(cover * 0.012)},
                {"label": f"Age loading ({req.age} yrs)", "amount": round(age_loading)},
                {"label": "Smoker loading", "amount": round(smoker_loading)},
            ]
        elif pt == "life":
            base = cover * 0.0035
            if req.age and req.age > 30:
                base += base * ((req.age - 30) * 0.04)
            if req.smoker:
                base *= 1.5
            breakdown = [
                {"label": "Term premium (1Cr equivalent)", "amount": round(cover * 0.0035)},
                {"label": f"Age factor ({req.age} yrs)", "amount": round(base - cover * 0.0035)},
            ]
        elif pt == "motor":
            idv = cover
            base = idv * 0.028
            age_disc = base * min(0.4, (req.vehicle_age or 0) * 0.04)
            base = max(base - age_disc, idv * 0.012)
            breakdown = [
                {"label": "Own damage + 3rd party", "amount": round(idv * 0.028)},
                {"label": f"Vehicle age discount ({req.vehicle_age} yrs)", "amount": -round(age_disc)},
            ]
        elif pt == "travel":
            base = (req.trip_days or 7) * 85
            if (req.age or 0) >= 60:
                base *= 1.4
            breakdown = [
                {"label": f"Per-day premium ({req.trip_days} days × ₹85)", "amount": round((req.trip_days or 7) * 85)},
                {"label": "Senior loading" if (req.age or 0) >= 60 else "", "amount": round(base - (req.trip_days or 7) * 85) if (req.age or 0) >= 60 else 0},
            ]
        else:
            raise HTTPException(status_code=400, detail="Unknown plan_type")

        gst = round(base * 0.18)
        total = round(base + gst)
        return {
            "plan_type": pt,
            "cover": cover,
            "estimated_premium": round(base),
            "gst": gst,
            "total_annual_premium": total,
            "monthly_emi": round(total / 12),
            "breakdown": [b for b in breakdown if b.get("amount") not in (0, None) and b.get("label")],
            "disclaimer": "Indicative quote — actual premium varies by insurer underwriting.",
            "mode": "demo",
        }

    @ins.get("/compare")
    async def compare_plans(plan_type: str, ids: str):
        """Compare 2-4 plans side-by-side. ids = comma-separated plan IDs."""
        id_list = [i.strip() for i in ids.split(",") if i.strip()][:4]
        # Read from app's INSURANCE_PLANS static list via DB-cached docs
        # Fall back to scanning the user's policies catalog endpoint.
        plans: List[Dict[str, Any]] = []
        for pid in id_list:
            # First try a saved override
            doc = await _db.insurance_overrides.find_one({"id": pid}, {"_id": 0})
            if doc:
                plans.append(doc)
                continue
            # Else look in server's static seed via a stored copy
            seed = await _db.insurance_seed.find_one({"id": pid}, {"_id": 0})
            if seed:
                plans.append(seed)
        if not plans:
            raise HTTPException(status_code=404, detail="No plans found")
        # Build comparison matrix
        keys = ["name", "cover", "premium", "claim_ratio", "network_hospitals", "tax_benefit", "features"]
        return {
            "plan_type": plan_type,
            "plans": plans,
            "matrix_keys": keys,
        }

    api.include_router(ins)


async def seed_insurance_catalog(insurance_plans: List[Dict[str, Any]]):
    """Stash the static INSURANCE_PLANS into MongoDB so admin/compare can read it."""
    if await _db.insurance_seed.count_documents({}) == 0:
        enriched = []
        for p in insurance_plans:
            enriched.append({
                **p,
                "claim_ratio": p.get("claim_ratio", round(random.uniform(94, 99), 1)),
                "network_hospitals": p.get("network_hospitals", random.choice([4500, 6800, 10000, 12500])),
                "tax_benefit": p.get("tax_benefit", "Section 80D up to ₹25,000" if p["type"] == "health" else "Section 80C up to ₹1.5L"),
                "features": p.get("features", ["Cashless claim", "Lifetime renewal", "No medical test till 45"]),
            })
        await _db.insurance_seed.insert_many(enriched)


# =========================================================================
# REWARDS ENGINE — Cashback Auto-Award + Admin Controls
# =========================================================================

# Tier thresholds for the loyalty system
TIERS = [
    {"id": "bronze", "name": "Bronze", "min": 0, "rate": 0.005, "color": "#CD7F32"},
    {"id": "silver", "name": "Silver", "min": 500, "rate": 0.008, "color": "#94A3B8"},
    {"id": "gold", "name": "Gold", "min": 2000, "rate": 0.012, "color": "#F59E0B"},
    {"id": "platinum", "name": "Platinum", "min": 5000, "rate": 0.018, "color": "#0EA5E9"},
    {"id": "diamond", "name": "Diamond", "min": 10000, "rate": 0.025, "color": "#A78BFA"},
]


def _tier_for(points: int) -> Dict[str, Any]:
    cur = TIERS[0]
    nxt = None
    for i, t in enumerate(TIERS):
        if points >= t["min"]:
            cur = t
            nxt = TIERS[i + 1] if i + 1 < len(TIERS) else None
    return {"current": cur, "next": nxt}


async def award_cashback(user_id: str, spend_amount: float, category: str = "general") -> Dict[str, Any]:
    """Award cashback + points after a successful debit transaction.
    Called by other endpoints (recharge/bill/travel/insurance).
    Returns {points_added, cashback_amount, tier}.
    """
    if spend_amount <= 0:
        return {"points_added": 0, "cashback_amount": 0}
    u = await _db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not u:
        return {"points_added": 0, "cashback_amount": 0}
    points = u.get("reward_points", 0)
    tier = _tier_for(points)["current"]
    cashback_amt = round(spend_amount * tier["rate"], 2)
    # 1 point per ₹10 spent + bonus 2x on travel/insurance
    pts_earned = int(spend_amount / 10)
    if category in ("travel", "insurance"):
        pts_earned *= 2
    new_points = points + pts_earned
    await _db.users.update_one({"user_id": user_id}, {"$set": {"reward_points": new_points}})
    if cashback_amt > 0:
        await _db.wallets.update_one({"user_id": user_id}, {"$inc": {"balance": cashback_amt}})
        if _add_tx:
            await _add_tx(user_id, "credit", "cashback", cashback_amt,
                          f"{tier['name']} tier cashback ({int(tier['rate']*1000)/10}%)",
                          "success", f"Cashback on {category}")
    return {"points_added": pts_earned, "cashback_amount": cashback_amt, "tier": tier["id"]}


def _attach_rewards(api: APIRouter):
    rw = APIRouter(prefix="/rewards", tags=["rewards-extra"])

    @rw.get("/tier")
    async def my_tier(user: Dict[str, Any] = Depends(_get_current_user)):
        u = await _db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
        info = _tier_for(u.get("reward_points", 0))
        return {
            "current": info["current"],
            "next": info["next"],
            "current_points": u.get("reward_points", 0),
            "progress_pct": (
                100 if not info["next"]
                else min(100, round(
                    ((u.get("reward_points", 0) - info["current"]["min"]) /
                     max(1, info["next"]["min"] - info["current"]["min"])) * 100
                ))
            ),
        }

    @rw.post("/redeem")
    async def redeem_points(amount: int, user: Dict[str, Any] = Depends(_get_current_user)):
        """Redeem 100 points = ₹10 cash to wallet."""
        if amount < 100 or amount % 100 != 0:
            raise HTTPException(status_code=400, detail="Min 100 points, in multiples of 100")
        u = await _db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
        if u.get("reward_points", 0) < amount:
            raise HTTPException(status_code=400, detail="Insufficient points")
        cash = amount / 10  # 10:1 ratio
        await _db.users.update_one({"user_id": user["user_id"]}, {"$inc": {"reward_points": -amount}})
        await _db.wallets.update_one({"user_id": user["user_id"]}, {"$inc": {"balance": cash}})
        if _add_tx:
            await _add_tx(user["user_id"], "credit", "redeem", cash,
                          f"Redeemed {amount} points", "success", f"{amount} pts")
        return {"success": True, "cash_credited": cash, "points_remaining": u.get("reward_points", 0) - amount}

    api.include_router(rw)


# =========================================================================
# ADMIN endpoints for managing the new catalogs
# =========================================================================

def _attach_admin(api: APIRouter, get_current_admin):
    adm = APIRouter(prefix="/admin/super", tags=["admin-super-app"])

    def _ensure(admin):
        if admin["role"] not in ("super_admin", "admin", "investment_manager", "finance_manager"):
            raise HTTPException(status_code=403, detail="Forbidden")

    @adm.get("/bookings")
    async def all_bookings(admin=Depends(get_current_admin), limit: int = 100):
        _ensure(admin)
        rows = await _db.bookings.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
        return rows

    @adm.get("/policies")
    async def all_policies(admin=Depends(get_current_admin), limit: int = 100):
        _ensure(admin)
        rows = await _db.policies.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
        return rows

    @adm.get("/rewards-summary")
    async def rewards_summary(admin=Depends(get_current_admin)):
        _ensure(admin)
        total_points = await _db.users.aggregate([{"$group": {"_id": None, "t": {"$sum": "$reward_points"}}}]).to_list(1)
        cashback = await _db.transactions.aggregate([
            {"$match": {"category": "cashback"}},
            {"$group": {"_id": None, "t": {"$sum": "$amount"}, "c": {"$sum": 1}}},
        ]).to_list(1)
        top_referrers = await _db.users.aggregate([
            {"$lookup": {"from": "users", "localField": "referral_code",
                         "foreignField": "referred_by", "as": "ref_users"}},
            {"$project": {"_id": 0, "full_name": 1, "referral_code": 1,
                          "count": {"$size": "$ref_users"}, "reward_points": 1}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]).to_list(10)
        return {
            "total_points_in_circulation": (total_points[0]["t"] if total_points else 0),
            "total_cashback_paid": round((cashback[0]["t"] if cashback else 0), 2),
            "cashback_count": cashback[0]["c"] if cashback else 0,
            "top_referrers": top_referrers,
            "tiers": TIERS,
        }

    class BonusReq(BaseModel):
        user_id: str
        points: int = 0
        cashback: float = 0
        note: Optional[str] = "Admin bonus"

    @adm.post("/grant-bonus")
    async def grant_bonus(req: BonusReq, admin=Depends(get_current_admin)):
        _ensure(admin)
        if req.points <= 0 and req.cashback <= 0:
            raise HTTPException(status_code=400, detail="Provide points or cashback > 0")
        if req.points:
            await _db.users.update_one({"user_id": req.user_id}, {"$inc": {"reward_points": req.points}})
        if req.cashback > 0:
            await _db.wallets.update_one({"user_id": req.user_id}, {"$inc": {"balance": req.cashback}})
            if _add_tx:
                await _add_tx(req.user_id, "credit", "cashback", req.cashback, req.note, "success", "Admin bonus")
        return {"success": True, "user_id": req.user_id, "points": req.points, "cashback": req.cashback}

    api.include_router(adm)


# =========================================================================
# attach()
# =========================================================================

def attach(api: APIRouter, db, get_current_user_fn, add_tx_fn, get_current_admin_fn, insurance_plans_seed, logger=None):
    global _db, _get_current_user, _add_tx, _logger
    _db = db
    _get_current_user = get_current_user_fn
    _add_tx = add_tx_fn
    _logger = logger

    _attach_travel(api)
    _attach_insurance(api)
    _attach_rewards(api)
    _attach_admin(api, get_current_admin_fn)
    return {"insurance_seed": insurance_plans_seed}
