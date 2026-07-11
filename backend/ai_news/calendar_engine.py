"""Economic Calendar Engine — Sprint 7C.2

Maintains a curated list of upcoming high-impact macro events (Fed decisions,
NFP, CPI, ECB, RBI, etc.). On first startup we seed a realistic recurring
calendar for the next 90 days. Admin can CRUD any event.

A background hook (in NewsBroadcaster) surfaces countdown notifications for
HIGH-impact events firing in the next 15 minutes.

Collection: `ai_economic_events`
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai_news.calendar")

COLL = "ai_economic_events"

IMPACTS = ["low", "medium", "high"]
IMPACT_LABELS = {"low": "Low", "medium": "Medium", "high": "High"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------ Seed data ------------------ #

# Curated recurring macro events. `days_offset` is added to today.
_SEED_TEMPLATES = [
    # Format: (title, country, currency, impact, days_offset, hour_utc, category, description)
    ("FOMC Interest Rate Decision", "US", "USD", "high", 7, 18, "Central Banks",
     "Federal Reserve announces the target range for the federal funds rate."),
    ("US Non-Farm Payrolls (NFP)", "US", "USD", "high", 3, 12, "Employment",
     "Monthly change in the number of employed people (ex-farming)."),
    ("US CPI m/m", "US", "USD", "high", 12, 12, "Inflation",
     "Change in the price of goods and services purchased by consumers."),
    ("US Core CPI m/m", "US", "USD", "high", 12, 12, "Inflation",
     "CPI excluding food and energy — the Fed's preferred inflation gauge."),
    ("US Retail Sales m/m", "US", "USD", "medium", 15, 12, "Consumer",
     "Change in the total value of sales at the retail level."),
    ("US Unemployment Claims", "US", "USD", "medium", 2, 12, "Employment",
     "Number of individuals who filed for unemployment insurance for the first time."),
    ("US ISM Manufacturing PMI", "US", "USD", "medium", 5, 14, "Manufacturing",
     "Purchasing manager index in the manufacturing sector."),
    ("US GDP q/q", "US", "USD", "high", 18, 12, "Growth",
     "Annualized change in the value of all goods and services produced."),
    ("ECB Interest Rate Decision", "EU", "EUR", "high", 10, 12, "Central Banks",
     "European Central Bank monetary policy decision."),
    ("ECB Press Conference", "EU", "EUR", "high", 10, 12, "Central Banks",
     "ECB President explains the rate decision and outlook."),
    ("EU CPI y/y (Flash)", "EU", "EUR", "high", 14, 9, "Inflation",
     "Flash estimate of the change in consumer prices year-over-year."),
    ("German ZEW Economic Sentiment", "DE", "EUR", "medium", 8, 9, "Sentiment",
     "Analyst sentiment survey on German economy."),
    ("BoE Interest Rate Decision", "UK", "GBP", "high", 21, 11, "Central Banks",
     "Bank of England Monetary Policy Committee decision."),
    ("UK CPI y/y", "UK", "GBP", "high", 16, 6, "Inflation",
     "Change in consumer prices year-over-year."),
    ("UK Retail Sales m/m", "UK", "GBP", "medium", 20, 6, "Consumer",
     "Change in total retail sales."),
    ("BoJ Interest Rate Decision", "JP", "JPY", "high", 25, 3, "Central Banks",
     "Bank of Japan monetary policy decision."),
    ("Japan CPI y/y", "JP", "JPY", "medium", 22, 23, "Inflation",
     "Change in consumer prices year-over-year."),
    ("BoC Interest Rate Decision", "CA", "CAD", "high", 28, 14, "Central Banks",
     "Bank of Canada monetary policy decision."),
    ("Canada CPI m/m", "CA", "CAD", "medium", 17, 12, "Inflation",
     "Change in consumer prices month-over-month."),
    ("RBA Interest Rate Decision", "AU", "AUD", "high", 11, 4, "Central Banks",
     "Reserve Bank of Australia monetary policy decision."),
    ("Australia Employment Change", "AU", "AUD", "medium", 13, 1, "Employment",
     "Change in the number of employed people."),
    ("China CPI y/y", "CN", "CNY", "medium", 6, 1, "Inflation",
     "Change in consumer prices year-over-year."),
    ("China GDP q/q", "CN", "CNY", "high", 30, 2, "Growth",
     "Quarterly change in gross domestic product."),
    ("China PMI Manufacturing", "CN", "CNY", "medium", 4, 1, "Manufacturing",
     "Purchasing manager index in the manufacturing sector."),
    # India-specific (Sprint 7C.2 requirement)
    ("RBI Monetary Policy Decision", "IN", "INR", "high", 9, 4, "Central Banks",
     "Reserve Bank of India policy repo rate decision."),
    ("India CPI y/y", "IN", "INR", "high", 14, 12, "Inflation",
     "India Consumer Price Index change year-over-year."),
    ("India WPI Inflation", "IN", "INR", "medium", 15, 6, "Inflation",
     "Wholesale Price Index inflation reading."),
    ("India Industrial Production", "IN", "INR", "medium", 19, 6, "Manufacturing",
     "Change in the total value of industrial output."),
    ("India GDP q/q", "IN", "INR", "high", 27, 6, "Growth",
     "Quarterly change in India's gross domestic product."),
    ("India Trade Balance", "IN", "INR", "low", 24, 6, "Trade",
     "Difference in value between imported and exported goods."),
    ("OPEC+ Meeting", "GLOBAL", "USD", "high", 23, 12, "Energy",
     "OPEC+ meeting on oil production quotas."),
    ("US Crude Oil Inventories", "US", "USD", "medium", 1, 14, "Energy",
     "Weekly change in barrels of commercial crude oil held by US firms."),
]


def _seed_events(now: datetime) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for tpl in _SEED_TEMPLATES:
        title, country, currency, impact, days_offset, hour_utc, category, desc = tpl
        et = (now + timedelta(days=days_offset)).replace(
            hour=hour_utc, minute=30 if hour_utc % 2 else 0, second=0, microsecond=0)
        events.append({
            "event_id": f"ev_{uuid.uuid4().hex[:12]}",
            "title": title, "country": country, "currency": currency,
            "impact": impact, "category": category,
            "event_time": et,
            "actual": None, "forecast": None, "previous": None,
            "description": desc,
            "notified_at": None,
            "created_at": now,
        })
    return events


# ------------------ Seeder ------------------ #

class CalendarSeeder:
    def __init__(self, db):
        self.db = db

    async def ensure_seeded(self):
        count = await self.db[COLL].estimated_document_count()
        if count > 0:
            # Also purge past-events that are >2 days old to keep the list tidy
            await self.db[COLL].delete_many(
                {"event_time": {"$lt": _now() - timedelta(days=2)}}
            )
            return
        events = _seed_events(_now())
        if events:
            await self.db[COLL].insert_many(events)
            logger.info("seeded %d economic events", len(events))


# ------------------ CRUD ------------------ #

async def list_events(db, impact: Optional[str] = None,
                      country: Optional[str] = None,
                      currency: Optional[str] = None,
                      days_ahead: int = 30,
                      include_past: bool = False,
                      limit: int = 100) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    now = _now()
    horizon = now + timedelta(days=int(days_ahead))
    if include_past:
        q["event_time"] = {"$lte": horizon}
    else:
        q["event_time"] = {"$gte": now - timedelta(hours=1), "$lte": horizon}
    if impact:
        q["impact"] = impact
    if country:
        q["country"] = country.upper()
    if currency:
        q["currency"] = currency.upper()
    cur = db[COLL].find(q, {"_id": 0}).sort("event_time", 1).limit(int(limit))
    rows = [d async for d in cur]
    for d in rows:
        et = d.get("event_time")
        if isinstance(et, datetime):
            if et.tzinfo is None:
                et = et.replace(tzinfo=timezone.utc)
            secs = (et - now).total_seconds()
            d["countdown_sec"] = int(secs)
            d["event_time"] = et.isoformat()
        else:
            d["countdown_sec"] = None
        if isinstance(d.get("created_at"), datetime):
            ca = d["created_at"]
            if ca.tzinfo is None:
                ca = ca.replace(tzinfo=timezone.utc)
            d["created_at"] = ca.isoformat()
        if isinstance(d.get("notified_at"), datetime):
            na = d["notified_at"]
            if na.tzinfo is None:
                na = na.replace(tzinfo=timezone.utc)
            d["notified_at"] = na.isoformat()
    return rows


async def create_event(db, payload: Dict[str, Any]) -> Dict[str, Any]:
    impact = (payload.get("impact") or "medium").lower()
    if impact not in IMPACTS:
        raise ValueError(f"invalid impact; valid={IMPACTS}")
    et_raw = payload.get("event_time")
    if isinstance(et_raw, str):
        try:
            event_time = datetime.fromisoformat(et_raw.replace("Z", "+00:00"))
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)
        except Exception:
            raise ValueError("event_time must be ISO 8601")
    elif isinstance(et_raw, datetime):
        event_time = et_raw if et_raw.tzinfo else et_raw.replace(tzinfo=timezone.utc)
    else:
        raise ValueError("event_time required")
    doc = {
        "event_id": f"ev_{uuid.uuid4().hex[:12]}",
        "title": (payload.get("title") or "").strip()[:180] or "Untitled event",
        "country": (payload.get("country") or "").upper()[:6] or "GLOBAL",
        "currency": (payload.get("currency") or "").upper()[:6] or "USD",
        "impact": impact,
        "category": (payload.get("category") or "General")[:60],
        "event_time": event_time,
        "actual": payload.get("actual"),
        "forecast": payload.get("forecast"),
        "previous": payload.get("previous"),
        "description": (payload.get("description") or "")[:500],
        "notified_at": None,
        "created_at": _now(),
    }
    await db[COLL].insert_one(doc)
    doc.pop("_id", None)
    doc["event_time"] = doc["event_time"].isoformat()
    doc["created_at"] = doc["created_at"].isoformat()
    return doc


async def update_event(db, event_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    set_fields: Dict[str, Any] = {}
    for k in ("title", "country", "currency", "category", "description",
              "actual", "forecast", "previous"):
        if k in patch:
            set_fields[k] = patch[k]
    if "impact" in patch:
        v = str(patch["impact"]).lower()
        if v not in IMPACTS:
            raise ValueError(f"invalid impact")
        set_fields["impact"] = v
    if "event_time" in patch:
        raw = patch["event_time"]
        if isinstance(raw, str):
            et = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if et.tzinfo is None:
                et = et.replace(tzinfo=timezone.utc)
            set_fields["event_time"] = et
    if not set_fields:
        return await get_event(db, event_id)
    await db[COLL].update_one({"event_id": event_id}, {"$set": set_fields})
    return await get_event(db, event_id)


async def get_event(db, event_id: str) -> Optional[Dict[str, Any]]:
    d = await db[COLL].find_one({"event_id": event_id}, {"_id": 0})
    if not d:
        return None
    et = d.get("event_time")
    if isinstance(et, datetime):
        if et.tzinfo is None:
            et = et.replace(tzinfo=timezone.utc)
        d["countdown_sec"] = int((et - _now()).total_seconds())
        d["event_time"] = et.isoformat()
    if isinstance(d.get("created_at"), datetime):
        ca = d["created_at"]
        if ca.tzinfo is None:
            ca = ca.replace(tzinfo=timezone.utc)
        d["created_at"] = ca.isoformat()
    if isinstance(d.get("notified_at"), datetime):
        na = d["notified_at"]
        if na.tzinfo is None:
            na = na.replace(tzinfo=timezone.utc)
        d["notified_at"] = na.isoformat()
    return d


async def delete_event(db, event_id: str) -> bool:
    res = await db[COLL].delete_one({"event_id": event_id})
    return res.deleted_count > 0


# ------------------ Notification hook ------------------ #

async def pending_countdown_events(db, minutes_ahead: int = 15) -> List[Dict[str, Any]]:
    """Return HIGH-impact events firing in the next N minutes that haven't
    been notified yet."""
    now = _now()
    horizon = now + timedelta(minutes=int(minutes_ahead))
    cur = db[COLL].find({
        "impact": "high",
        "event_time": {"$gte": now, "$lte": horizon},
        "notified_at": None,
    }, {"_id": 0})
    return [d async for d in cur]


async def mark_notified(db, event_id: str):
    await db[COLL].update_one(
        {"event_id": event_id}, {"$set": {"notified_at": _now()}}
    )
