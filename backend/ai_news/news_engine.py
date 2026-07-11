"""AI News Engine — Sprint 7C.2

Generates categorized AI market news items using Claude Sonnet 4.5
(via emergentintegrations). Fall-back is a deterministic template driven
by current cached prices from `market_provider_cache`.

Categories:
  forex, crypto, indices, commodities, indian_market, global

Storage: `ai_news_items` collection. AI-generated items are cached; admin can
CRUD and force regenerate.

Broadcaster: background task that scans for `high_impact=True` items that
haven't been broadcast yet and creates notifications for all active users.
"""
from __future__ import annotations
import asyncio
import logging
import os
import random
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
    HAS_LLM = True
except Exception:
    LlmChat = UserMessage = None  # type: ignore
    HAS_LLM = False

load_dotenv()
logger = logging.getLogger("ai_news.engine")

EMERGENT_KEY = (os.environ.get("EMERGENT_LLM_KEY") or "").strip()
MODEL_PROVIDER = "anthropic"
MODEL_NAME = "claude-sonnet-4-5-20250929"

CATEGORIES = ["forex", "crypto", "indices", "commodities", "indian_market", "global"]
CATEGORY_LABELS = {
    "forex": "Forex", "crypto": "Crypto", "indices": "Indices",
    "commodities": "Commodities", "indian_market": "Indian Market", "global": "Global Macro",
}

# Symbols we tie each category to when reading cache for context
CATEGORY_SYMBOLS = {
    "forex": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"],
    "crypto": ["BTCUSD", "ETHUSD"],
    "indices": ["US30", "NAS100", "SPX500", "GER40", "UK100"],
    "commodities": ["XAUUSD", "XAGUSD", "USOIL", "UKOIL", "NATGAS"],
    "indian_market": ["IND50"],
    "global": ["XAUUSD", "BTCUSD", "SPX500", "USDJPY"],
}

COLL = "ai_news_items"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sentiment_from_movement(change_pct: Optional[float]) -> str:
    if change_pct is None:
        return "neutral"
    if change_pct >= 1.0:
        return "bullish"
    if change_pct >= 0.3:
        return "mildly_bullish"
    if change_pct <= -1.0:
        return "bearish"
    if change_pct <= -0.3:
        return "mildly_bearish"
    return "neutral"


# ------------------ Deterministic templates ------------------ #

_FALLBACK_HEADLINES = {
    "forex": [
        "Dollar {trend} as {pair} tests key {level}",
        "{pair} {movement} on shifting rate expectations",
        "Yen carry trades face pressure as {pair} moves {direction}",
    ],
    "crypto": [
        "Bitcoin {movement} through ${price}k as spot flows {direction}",
        "Ethereum {movement} following {pair} volatility spike",
        "Crypto majors {direction} amid liquidity rotation",
    ],
    "indices": [
        "{pair} {movement} on renewed risk appetite",
        "Tech-heavy {pair} leads global equities {direction}",
        "Wall Street futures {direction} ahead of key data",
    ],
    "commodities": [
        "Gold {movement} to ${price} as safe-haven bid {direction}",
        "Crude oil {direction} on OPEC+ signals",
        "Silver tracks gold with {movement} through key resistance",
    ],
    "indian_market": [
        "Nifty {movement} tracking global cues; banking pack in focus",
        "Sensex {direction} as FIIs realign positioning",
        "IT stocks buoy Nifty as USD/INR consolidates",
    ],
    "global": [
        "Risk assets {direction} as macro backdrop shifts",
        "Gold vs. Bitcoin decouple as {pair} takes centre stage",
        "Global bond yields {direction} following central-bank guidance",
    ],
}


def _fallback_body(category: str, symbol: str, price: Optional[float],
                   change_pct: Optional[float]) -> Dict[str, str]:
    move = "climbs" if (change_pct or 0) >= 0 else "slips"
    dir_word = "higher" if (change_pct or 0) >= 0 else "lower"
    trend_word = "firms" if (change_pct or 0) >= 0 else "softens"
    price_disp = f"{price:,.2f}" if price else "—"
    headline_tmpl = random.choice(_FALLBACK_HEADLINES.get(category, _FALLBACK_HEADLINES["global"]))
    headline = (headline_tmpl
                .replace("{pair}", symbol)
                .replace("{price}", ("%.1f" % (price / 1000)) if (price and price > 1000) else (price_disp if price else "key level"))
                .replace("{level}", price_disp)
                .replace("{movement}", move)
                .replace("{direction}", dir_word)
                .replace("{trend}", trend_word))
    pct_txt = f"{change_pct:+.2f}%" if change_pct is not None else "—"
    summary = (
        f"{symbol} is trading around {price_disp} ({pct_txt} on the day). "
        f"Traders are watching order flow around the current level while broader "
        f"{CATEGORY_LABELS.get(category, category)} sentiment stays {_sentiment_from_movement(change_pct).replace('_',' ')}."
    )
    body = (
        summary + " " +
        f"Volatility remains contained but positioning suggests continued "
        f"{dir_word} pressure if key levels break. Watch the next major macro "
        f"release for a decisive catalyst."
    )
    return {"title": headline, "summary": summary, "body": body}


# ------------------ Generation ------------------ #

async def _read_cache_snapshot(db, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """Read latest prices/change for context symbols from the shared cache."""
    out: Dict[str, Dict[str, Any]] = {}
    cur = db.market_price_cache.find({"symbol": {"$in": [s.upper() for s in symbols]}}, {"_id": 0})
    async for d in cur:
        out[d["symbol"]] = d
    return out


async def _generate_ai(category: str, snapshots: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, str]]:
    if not (HAS_LLM and EMERGENT_KEY):
        return None
    try:
        session = f"news-{category}-{int(_now().timestamp() // 3600)}"
        system = (
            "You are the My Funding Bank market news editor. Write ONE concise financial "
            "news item for the given category based on live snapshots. Return STRICT JSON "
            "with keys: title (12-14 words), summary (2 sentences, <240 chars), body (4-5 "
            "sentences, <900 chars), sentiment (bullish|mildly_bullish|neutral|mildly_bearish|bearish), "
            "tags (array of 3-5 short lowercase tags). NEVER give investment advice. Do not "
            "invent fictional data — only use the provided snapshots."
        )
        chat = LlmChat(api_key=EMERGENT_KEY, session_id=session,
                       system_message=system).with_model(MODEL_PROVIDER, MODEL_NAME)
        rows = []
        for sym, d in snapshots.items():
            rows.append(f"{sym}: price={d.get('price')}, 24h_change_pct={d.get('change_pct')}")
        prompt = (
            f"Category: {CATEGORY_LABELS.get(category, category)}.\n"
            f"Snapshots:\n" + "\n".join(rows) + "\n\nReturn ONLY the JSON object."
        )
        resp = await chat.send_message(UserMessage(text=prompt))
        text = (getattr(resp, "content", None) or str(resp)).strip()
        # Clean up common markdown fences
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        import json as _json
        data = _json.loads(text)
        return {
            "title": str(data.get("title", ""))[:200],
            "summary": str(data.get("summary", ""))[:400],
            "body": str(data.get("body", ""))[:1500],
            "sentiment": str(data.get("sentiment", "neutral")),
            "tags": [str(t)[:24] for t in (data.get("tags") or [])][:6],
        }
    except Exception as e:
        logger.info("AI news generation fell back to template (%s): %s", category, e)
        return None


async def generate_news_batch(db, categories: Optional[List[str]] = None,
                              per_category: int = 3) -> int:
    """Regenerate a fresh set of AI news items per category. Returns count."""
    categories = categories or CATEGORIES
    total = 0
    for cat in categories:
        syms = CATEGORY_SYMBOLS.get(cat, ["BTCUSD"])
        snap = await _read_cache_snapshot(db, syms)
        for i in range(per_category):
            focus = syms[i % len(syms)]
            focus_data = snap.get(focus, {})
            price = focus_data.get("price")
            change_pct = focus_data.get("change_pct")
            ai_content = await _generate_ai(cat, {focus: focus_data} if focus_data else snap)
            if not ai_content:
                fb = _fallback_body(cat, focus, price, change_pct)
                ai_content = {
                    "title": fb["title"], "summary": fb["summary"], "body": fb["body"],
                    "sentiment": _sentiment_from_movement(change_pct),
                    "tags": [cat, focus.lower(), "markets"],
                }
            high_impact = (change_pct is not None and abs(change_pct) >= 1.5) or i == 0
            doc = {
                "news_id": f"nw_{uuid.uuid4().hex[:12]}",
                "category": cat, "category_label": CATEGORY_LABELS.get(cat, cat),
                "title": ai_content["title"], "summary": ai_content["summary"],
                "body": ai_content["body"], "sentiment": ai_content["sentiment"],
                "tags": ai_content["tags"], "symbols": [focus],
                "symbol_snapshot": {"symbol": focus, "price": price, "change_pct": change_pct},
                "published_at": _now(),
                "is_ai_generated": bool(HAS_LLM and EMERGENT_KEY),
                "is_published": True,
                "high_impact": bool(high_impact),
                "broadcast_at": None,
            }
            await db[COLL].insert_one(doc)
            total += 1
    # Prune to last 200 items
    total_docs = await db[COLL].estimated_document_count()
    if total_docs > 200:
        old = db[COLL].find({}, {"_id": 1}).sort("published_at", -1).skip(200)
        ids = [d["_id"] async for d in old]
        if ids:
            await db[COLL].delete_many({"_id": {"$in": ids}})
    return total


async def list_news(db, category: Optional[str] = None,
                    sentiment: Optional[str] = None,
                    high_impact_only: bool = False,
                    limit: int = 30) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"is_published": True}
    if category and category != "all":
        q["category"] = category
    if sentiment:
        q["sentiment"] = sentiment
    if high_impact_only:
        q["high_impact"] = True
    cur = db[COLL].find(q, {"_id": 0}).sort("published_at", -1).limit(int(limit))
    rows = [d async for d in cur]
    for d in rows:
        if isinstance(d.get("published_at"), datetime):
            d["published_at"] = d["published_at"].isoformat()
        d.pop("broadcast_at", None)
    return rows


async def get_news(db, news_id: str) -> Optional[Dict[str, Any]]:
    d = await db[COLL].find_one({"news_id": news_id}, {"_id": 0})
    if not d:
        return None
    if isinstance(d.get("published_at"), datetime):
        d["published_at"] = d["published_at"].isoformat()
    if isinstance(d.get("broadcast_at"), datetime):
        d["broadcast_at"] = d["broadcast_at"].isoformat()
    return d


async def ensure_seed(db) -> None:
    """On first startup, seed if the collection is empty."""
    count = await db[COLL].estimated_document_count()
    if count > 0:
        return
    await generate_news_batch(db, per_category=2)


# ------------------ Broadcaster (notifications) ------------------ #

class NewsBroadcaster:
    """Background task that broadcasts high-impact news to all users."""

    def __init__(self, db, interval_sec: int = 120):
        self.db = db
        self.interval_sec = int(interval_sec)
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self):
        if self._task and not self._task.done():
            return
        await ensure_seed(self.db)
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("NewsBroadcaster started (interval=%ds)", self.interval_sec)

    async def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self):
        # Give the system a couple of seconds to warm up on first start
        await asyncio.sleep(3)
        while not self._stop.is_set():
            try:
                await self._broadcast_once()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("broadcast loop error: %s", e)
            await asyncio.sleep(self.interval_sec)

    async def _active_user_ids(self) -> List[str]:
        # Grab up to 500 recently active users
        cur = self.db.users.find({}, {"user_id": 1, "_id": 0}).limit(500)
        return [u["user_id"] async for u in cur if u.get("user_id")]

    async def _broadcast_once(self):
        cur = self.db[COLL].find(
            {"high_impact": True, "is_published": True, "broadcast_at": None},
            {"_id": 0}
        ).sort("published_at", -1).limit(5)
        items = [d async for d in cur]
        if not items:
            return
        user_ids = await self._active_user_ids()
        if not user_ids:
            for it in items:
                await self.db[COLL].update_one(
                    {"news_id": it["news_id"]}, {"$set": {"broadcast_at": _now()}}
                )
            return
        for it in items:
            deeplink = f"/ai/news/{it['news_id']}"
            for uid in user_ids:
                await self.db.notifications.insert_one({
                    "notif_id": f"nf_{uuid.uuid4().hex[:12]}",
                    "user_id": uid,
                    "title": f"📰 {it['category_label']} · High Impact",
                    "body": it["title"],
                    "read": False, "created_at": _now(),
                    "deeplink": deeplink, "category": "market_news",
                    "metadata": {"news_id": it["news_id"], "category": it["category"]},
                })
            await self.db[COLL].update_one(
                {"news_id": it["news_id"]}, {"$set": {"broadcast_at": _now()}}
            )
            logger.info("broadcast news %s to %d users", it["news_id"], len(user_ids))
