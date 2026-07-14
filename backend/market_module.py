"""Sprint 6 — Market Intelligence
Provider-agnostic layer serving:
  - Real-time quote board (dashboard)
  - Per-user watchlist
  - Market news feed
  - Economic calendar
  - Symbol search
Providers implement the same interface. `mock` provider guarantees availability without keys.
"""
from __future__ import annotations

import asyncio
import hashlib
import math
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field

# --------------------- injected globals ---------------------
_db = None
_get_current_user: Optional[Callable] = None
_get_current_admin: Optional[Callable] = None
_logger = None

# --------------------- Instrument registry ---------------------
CATEGORIES = ["index", "commodity", "forex", "crypto", "stock"]

INSTRUMENTS: Dict[str, Dict[str, Any]] = {
    "NIFTY50":   {"symbol": "NIFTY50",   "name": "Nifty 50",     "category": "index",     "currency": "INR", "seed": 24800.0, "vol": 0.007, "trend": 0.0002},
    "SENSEX":    {"symbol": "SENSEX",    "name": "Sensex",       "category": "index",     "currency": "INR", "seed": 82100.0, "vol": 0.006, "trend": 0.0002},
    "BANKNIFTY": {"symbol": "BANKNIFTY", "name": "Bank Nifty",   "category": "index",     "currency": "INR", "seed": 52400.0, "vol": 0.009, "trend": 0.00015},
    "GOLD":      {"symbol": "GOLD",      "name": "Gold (24K)",   "category": "commodity", "currency": "INR", "seed": 7250.0, "vol": 0.004, "trend": 0.0003, "unit": "per gm"},
    "SILVER":    {"symbol": "SILVER",    "name": "Silver",       "category": "commodity", "currency": "INR", "seed": 92000.0, "vol": 0.006, "trend": 0.0001, "unit": "per kg"},
    "CRUDE":     {"symbol": "CRUDE",     "name": "Crude Oil",    "category": "commodity", "currency": "USD", "seed": 79.5, "vol": 0.012, "trend": 0.0, "unit": "per barrel"},
    "USDINR":    {"symbol": "USDINR",    "name": "USD / INR",    "category": "forex",     "currency": "INR", "seed": 83.42, "vol": 0.002, "trend": 0.00005},
    "EURUSD":    {"symbol": "EURUSD",    "name": "EUR / USD",    "category": "forex",     "currency": "USD", "seed": 1.0870, "vol": 0.0025, "trend": 0.0},
    "GBPUSD":    {"symbol": "GBPUSD",    "name": "GBP / USD",    "category": "forex",     "currency": "USD", "seed": 1.2680, "vol": 0.0025, "trend": 0.0},
    "BTCUSD":    {"symbol": "BTCUSD",    "name": "Bitcoin",      "category": "crypto",    "currency": "USD", "seed": 97500.0, "vol": 0.03, "trend": 0.0006},
    "ETHUSD":    {"symbol": "ETHUSD",    "name": "Ethereum",     "category": "crypto",    "currency": "USD", "seed": 3450.0, "vol": 0.035, "trend": 0.0005},
    # additional searchable equities
    "RELIANCE":  {"symbol": "RELIANCE",  "name": "Reliance Industries", "category": "stock", "currency": "INR", "seed": 2960.0, "vol": 0.014, "trend": 0.0003},
    "TCS":       {"symbol": "TCS",       "name": "Tata Consultancy Services", "category": "stock", "currency": "INR", "seed": 4210.0, "vol": 0.013, "trend": 0.0002},
    "HDFCBANK":  {"symbol": "HDFCBANK",  "name": "HDFC Bank",   "category": "stock", "currency": "INR", "seed": 1685.0, "vol": 0.015, "trend": 0.00025},
    "INFY":      {"symbol": "INFY",      "name": "Infosys",     "category": "stock", "currency": "INR", "seed": 1935.0, "vol": 0.013, "trend": 0.0002},
    "ITC":       {"symbol": "ITC",       "name": "ITC",         "category": "stock", "currency": "INR", "seed": 465.0, "vol": 0.012, "trend": 0.0002},
}

DEFAULT_DASHBOARD = ["NIFTY50", "SENSEX", "BANKNIFTY", "GOLD", "SILVER", "CRUDE",
                     "USDINR", "EURUSD", "GBPUSD", "BTCUSD", "ETHUSD"]

DEFAULT_SETTINGS = {
    "provider": "mock",
    "refresh_seconds": 30,
    "cache_seconds": 15,
    "maintenance": False,
    "enabled_instruments": DEFAULT_DASHBOARD,
    "api_keys": {"alpha_vantage": "", "twelve_data": "", "polygon": ""},
    "news_provider": "mock",
    "calendar_provider": "mock",
}

_settings_cache: Dict[str, Any] = {}
_settings_cache_at: float = 0.0
_quote_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}  # symbol -> (expires_ts, data)

def _now() -> datetime: return datetime.utcnow()

async def get_settings(force=False) -> Dict[str, Any]:
    global _settings_cache, _settings_cache_at
    if not force and _settings_cache and time.time() - _settings_cache_at < 15:
        return _settings_cache
    doc = await _db.market_settings.find_one({"_id": "default"}) or {}
    merged = {**DEFAULT_SETTINGS, **{k: v for k, v in doc.items() if k != "_id"}}
    if "api_keys" in doc:
        merged["api_keys"] = {**DEFAULT_SETTINGS["api_keys"], **(doc.get("api_keys") or {})}
    _settings_cache = merged
    _settings_cache_at = time.time()
    return merged

# --------------------- Provider adapter ---------------------
class BaseProvider:
    name = "base"
    async def quote(self, symbol: str) -> Optional[Dict[str, Any]]: raise NotImplementedError
    async def history(self, symbol: str, points: int = 30) -> List[Dict[str, Any]]: raise NotImplementedError
    async def search(self, q: str) -> List[Dict[str, Any]]: raise NotImplementedError


class MockProvider(BaseProvider):
    """Deterministic-ish random-walk provider using time as a seed so prices evolve realistically."""
    name = "mock"

    def _walk(self, meta: Dict[str, Any], t_min: int) -> float:
        seed = int(hashlib.md5(f"{meta['symbol']}-{t_min}".encode()).hexdigest()[:8], 16)
        r = random.Random(seed)
        # normalize t_min to days-from-now to keep drift bounded
        t_days = (t_min - int(time.time() // 60)) / 1440.0
        drift = meta.get("trend", 0.0) * t_days
        noise = sum(r.gauss(0, 1) for _ in range(3)) * meta.get("vol", 0.01) * 0.35
        price = meta["seed"] * math.exp(max(-0.4, min(0.4, drift + noise)))
        return round(price, 4 if meta.get("category") == "forex" else 2)

    async def quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        m = INSTRUMENTS.get(symbol)
        if not m:
            return None
        now = _now()
        t_min = int(now.timestamp() // 60)
        cur = self._walk(m, t_min)
        prev = self._walk(m, t_min - 1440)  # 1 day ago
        change = round(cur - prev, 4)
        change_pct = round(((cur - prev) / prev * 100) if prev else 0, 2)
        trend = "up" if change > 0 else "down" if change < 0 else "flat"
        day_low = round(min(cur, prev) * (1 - m.get("vol", 0.01) * 0.5), 4)
        day_high = round(max(cur, prev) * (1 + m.get("vol", 0.01) * 0.5), 4)
        return {
            "symbol": symbol, "name": m["name"], "category": m["category"],
            "currency": m["currency"], "unit": m.get("unit"),
            "price": cur, "prev_close": prev, "change": change, "change_pct": change_pct,
            "trend": trend, "day_low": day_low, "day_high": day_high,
            "updated_at": now.isoformat(), "provider": self.name,
        }

    async def history(self, symbol: str, points: int = 30) -> List[Dict[str, Any]]:
        m = INSTRUMENTS.get(symbol)
        if not m:
            return []
        t_now = int(_now().timestamp() // 60)
        step = 30  # 30-min bars
        rows = []
        for i in range(points):
            t_min = t_now - (points - 1 - i) * step
            p = self._walk(m, t_min)
            rows.append({"t": t_min * 60, "close": p})
        return rows

    async def search(self, q: str) -> List[Dict[str, Any]]:
        ql = (q or "").lower().strip()
        if not ql:
            return []
        out = []
        for sym, m in INSTRUMENTS.items():
            if ql in sym.lower() or ql in m["name"].lower() or ql in m["category"].lower():
                out.append({"symbol": sym, "name": m["name"], "category": m["category"], "currency": m["currency"]})
        return out[:20]


PROVIDERS: Dict[str, BaseProvider] = {"mock": MockProvider()}


def _get_provider(settings: Dict[str, Any]) -> BaseProvider:
    return PROVIDERS.get(settings.get("provider") or "mock", PROVIDERS["mock"])


# --------------------- News + calendar ---------------------
def _mock_news() -> List[Dict[str, Any]]:
    now = _now()
    stories = [
        ("markets", "Nifty scales fresh high on FII buying", "Domestic indices closed at record levels as foreign inflows continued for the fifth consecutive session, led by banking and IT stocks.", "MFB Newsroom"),
        ("markets", "Bank Nifty outperforms broader market", "Bank Nifty rallied 1.4% intraday supported by HDFC Bank and Kotak Mahindra after strong quarterly updates.", "MFB Newsroom"),
        ("economy", "RBI keeps repo rate unchanged at 6.50%", "The Reserve Bank of India held policy rates steady in its bi-monthly review, retaining its stance on withdrawal of accommodation.", "Reuters"),
        ("economy", "India Q2 GDP expands 7.2%", "Manufacturing and services sectors drove growth, beating consensus of 6.9%. Full year FY26 forecast raised to 7.1%.", "PTI"),
        ("gold", "Gold hits new life-time high in Indian markets", "Spot gold in Mumbai crossed ₹7,300/gm as USD softness and festive buying combined to lift bullion.", "MCX"),
        ("gold", "Silver premium widens versus gold", "The gold-silver ratio dropped to 78 as industrial demand pushed silver higher.", "MFB Newsroom"),
        ("forex", "Rupee stable at ₹83.4 vs dollar", "The Indian rupee held tight against the greenback with RBI's dollar-selling capping upside.", "MFB Newsroom"),
        ("forex", "EUR/USD tests key resistance", "Euro rallied 0.4% as European PMIs surprised on the upside; traders eye ECB commentary.", "FX Times"),
        ("crypto", "Bitcoin holds above $97,000", "Institutional inflows into spot BTC ETFs remain strong; open interest at record highs.", "CoinDesk"),
        ("crypto", "Ethereum staking hits new milestone", "Total ETH staked crosses 34M ETH; Layer-2 activity accelerates ahead of upcoming upgrade.", "MFB Newsroom"),
    ]
    out = []
    for i, (cat, head, summary, source) in enumerate(stories):
        out.append({
            "id": f"n_{i}_{int(now.timestamp())//3600}",
            "category": cat, "headline": head, "summary": summary,
            "source": source, "published_at": (now - timedelta(minutes=15 + i * 47)).isoformat(),
            "url": f"https://newsroom.mfb.in/{cat}/{i}",
            "provider": "mock",
        })
    out.sort(key=lambda x: x["published_at"], reverse=True)
    return out


def _mock_calendar() -> List[Dict[str, Any]]:
    now = _now()
    items = [
        {"country": "IN", "event": "RBI Monetary Policy Statement", "type": "rate",     "impact": "high",   "when_offset_days": 6, "prior": "6.50%",  "forecast": "6.50%"},
        {"country": "IN", "event": "CPI Inflation YoY",             "type": "cpi",      "impact": "high",   "when_offset_days": 2, "prior": "4.83%",  "forecast": "4.72%"},
        {"country": "IN", "event": "Industrial Production YoY",     "type": "gdp",      "impact": "medium", "when_offset_days": 3, "prior": "5.2%",   "forecast": "5.6%"},
        {"country": "US", "event": "FOMC Rate Decision",            "type": "rate",     "impact": "high",   "when_offset_days": 4, "prior": "5.50%",  "forecast": "5.25%"},
        {"country": "US", "event": "Non-Farm Payrolls",             "type": "employment","impact":"high",   "when_offset_days": 8, "prior": "205K",   "forecast": "180K"},
        {"country": "US", "event": "Core PCE Price Index",          "type": "cpi",      "impact": "high",   "when_offset_days": 9, "prior": "2.8%",   "forecast": "2.7%"},
        {"country": "EU", "event": "ECB Interest Rate Decision",    "type": "rate",     "impact": "high",   "when_offset_days": 5, "prior": "4.25%",  "forecast": "4.00%"},
        {"country": "UK", "event": "BoE Bank Rate",                 "type": "rate",     "impact": "medium", "when_offset_days": 7, "prior": "5.00%",  "forecast": "5.00%"},
    ]
    out = []
    for i, it in enumerate(items):
        when = (now + timedelta(days=it["when_offset_days"])).replace(hour=14, minute=0, second=0, microsecond=0)
        out.append({
            "id": f"e_{i}_{int(now.timestamp())//86400}",
            **it,
            "when": when.isoformat(),
        })
    out.sort(key=lambda x: x["when"])
    return out


# --------------------- Cached quote fetch ---------------------
async def cached_quote(symbol: str, settings: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    settings = settings or await get_settings()
    ttl = int(settings.get("cache_seconds") or 15)
    exp, data = _quote_cache.get(symbol, (0, None))
    now_ts = time.time()
    if data and exp > now_ts:
        return data
    provider = _get_provider(settings)
    q = await provider.quote(symbol)
    if q:
        _quote_cache[symbol] = (now_ts + ttl, q)
    return q


# --------------------- Helper for AI advisor integration ---------------------
async def get_market_snapshot(limit: int = 6) -> Dict[str, Any]:
    """Compact snapshot for AI system prompt (safe for JSON injection)."""
    try:
        settings = await get_settings()
        symbols = (settings.get("enabled_instruments") or DEFAULT_DASHBOARD)[:limit]
        quotes = []
        for s in symbols:
            q = await cached_quote(s, settings)
            if q:
                quotes.append({"symbol": q["symbol"], "name": q["name"], "price": q["price"],
                               "change_pct": q["change_pct"], "trend": q["trend"]})
        return {"as_of": _now().isoformat(), "quotes": quotes}
    except Exception as e:
        if _logger: _logger.warning(f"market snapshot error: {e}")
        return {"as_of": _now().isoformat(), "quotes": []}


# --------------------- Pydantic models ---------------------
class WatchAdd(BaseModel):
    symbol: str

class WatchPin(BaseModel):
    symbol: str
    pinned: bool = True

class AdminSettingsPatch(BaseModel):
    provider: Optional[str] = None
    refresh_seconds: Optional[int] = None
    cache_seconds: Optional[int] = None
    maintenance: Optional[bool] = None
    enabled_instruments: Optional[List[str]] = None
    api_keys: Optional[Dict[str, str]] = None
    news_provider: Optional[str] = None
    calendar_provider: Optional[str] = None


# --------------------- Routers ---------------------
user_router = APIRouter(prefix="/market", tags=["market"])
admin_router = APIRouter(prefix="/admin/market", tags=["market-admin"])

async def _user_dep(request: Request):
    if _get_current_user is None:
        raise HTTPException(status_code=503, detail="Auth not attached")
    return await _get_current_user(request.headers.get("authorization"))

async def _admin_dep(request: Request):
    if _get_current_admin is None:
        raise HTTPException(status_code=503, detail="Admin auth not attached")
    return await _get_current_admin(request.headers.get("authorization"))


def _check_maintenance(settings: Dict[str, Any]):
    if settings.get("maintenance"):
        raise HTTPException(status_code=503, detail="Market feed is under maintenance. Please try again shortly.")


@user_router.get("/dashboard")
async def dashboard():
    settings = await get_settings()
    _check_maintenance(settings)
    symbols = settings.get("enabled_instruments") or DEFAULT_DASHBOARD
    items = []
    for s in symbols:
        q = await cached_quote(s, settings)
        if q:
            items.append(q)
    return {"items": items, "provider": settings.get("provider"), "as_of": _now().isoformat()}


@user_router.get("/quotes")
async def quotes(symbols: str = Query(..., description="comma separated symbols")):
    settings = await get_settings()
    _check_maintenance(settings)
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    out = []
    for s in syms:
        q = await cached_quote(s, settings)
        if q: out.append(q)
    return {"items": out}


@user_router.get("/quote/{symbol}")
async def quote(symbol: str):
    settings = await get_settings()
    _check_maintenance(settings)
    q = await cached_quote(symbol.upper(), settings)
    if not q:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return q


@user_router.get("/history/{symbol}")
async def history(symbol: str, points: int = 30):
    settings = await get_settings()
    _check_maintenance(settings)
    provider = _get_provider(settings)
    data = await provider.history(symbol.upper(), points=max(6, min(points, 96)))
    if not data:
        raise HTTPException(status_code=404, detail="No history")
    return {"symbol": symbol.upper(), "points": data}


@user_router.get("/search")
async def search(q: str):
    settings = await get_settings()
    provider = _get_provider(settings)
    return {"items": await provider.search(q)}


# ----- watchlist (per user) -----
@user_router.get("/watchlist")
async def get_watchlist(user: Dict[str, Any] = Depends(_user_dep)):
    settings = await get_settings()
    doc = await _db.market_watchlists.find_one({"user_id": user["user_id"]}) or {"symbols": [], "pinned": []}
    symbols = doc.get("symbols") or []
    pinned = set(doc.get("pinned") or [])
    quotes = []
    for s in symbols:
        q = await cached_quote(s, settings)
        if q:
            quotes.append({**q, "pinned": s in pinned})
    # sort pinned first
    quotes.sort(key=lambda x: (not x.get("pinned"), x["symbol"]))
    return {"items": quotes, "pinned": list(pinned)}


@user_router.post("/watchlist/add")
async def add_watch(body: WatchAdd, user: Dict[str, Any] = Depends(_user_dep)):
    sym = body.symbol.strip().upper()
    if sym not in INSTRUMENTS:
        raise HTTPException(status_code=400, detail="Unknown symbol")
    doc = await _db.market_watchlists.find_one({"user_id": user["user_id"]}) or {"user_id": user["user_id"], "symbols": [], "pinned": []}
    if sym in doc["symbols"]:
        return {"ok": True, "duplicate": True}
    doc["symbols"].append(sym)
    doc["updated_at"] = _now()
    await _db.market_watchlists.update_one({"user_id": user["user_id"]}, {"$set": doc}, upsert=True)
    return {"ok": True, "symbol": sym}


@user_router.delete("/watchlist/{symbol}")
async def remove_watch(symbol: str, user: Dict[str, Any] = Depends(_user_dep)):
    sym = symbol.strip().upper()
    r = await _db.market_watchlists.update_one(
        {"user_id": user["user_id"]},
        {"$pull": {"symbols": sym, "pinned": sym}, "$set": {"updated_at": _now()}}
    )
    return {"ok": True, "modified": r.modified_count}


@user_router.post("/watchlist/pin")
async def pin_watch(body: WatchPin, user: Dict[str, Any] = Depends(_user_dep)):
    sym = body.symbol.strip().upper()
    if body.pinned:
        await _db.market_watchlists.update_one(
            {"user_id": user["user_id"]},
            {"$addToSet": {"pinned": sym}, "$set": {"updated_at": _now(), "user_id": user["user_id"]}},
            upsert=True,
        )
    else:
        await _db.market_watchlists.update_one(
            {"user_id": user["user_id"]}, {"$pull": {"pinned": sym}}
        )
    return {"ok": True}


# ----- news & calendar -----
@user_router.get("/news")
async def news(category: Optional[str] = None, limit: int = 20):
    settings = await get_settings()
    provider = (settings.get("news_provider") or "mock").lower()
    items = _mock_news()  # only mock provider implemented for now
    if category and category != "all":
        items = [x for x in items if x["category"] == category]
    return {"items": items[:limit], "provider": provider, "categories": ["markets", "economy", "gold", "forex", "crypto"]}


@user_router.get("/calendar")
async def calendar(country: Optional[str] = None, impact: Optional[str] = None, limit: int = 30):
    settings = await get_settings()
    provider = (settings.get("calendar_provider") or "mock").lower()
    items = _mock_calendar()
    if country: items = [x for x in items if x["country"] == country.upper()]
    if impact: items = [x for x in items if x["impact"] == impact]
    return {"items": items[:limit], "provider": provider}


# --------------------- Admin ---------------------
@admin_router.get("/status")
async def admin_status(admin: Dict[str, Any] = Depends(_admin_dep)):
    settings = await get_settings(force=True)
    total_watchers = await _db.market_watchlists.count_documents({})
    return {
        "settings": {k: v for k, v in settings.items() if k != "api_keys"},
        "api_keys_masked": {k: (bool(v) and f"{'*' * max(0, len(v)-4)}{v[-4:]}") or "" for k, v in (settings.get("api_keys") or {}).items()},
        "providers_registered": list(PROVIDERS.keys()),
        "instruments": list(INSTRUMENTS.keys()),
        "cache_entries": len(_quote_cache),
        "watchers": total_watchers,
    }


@admin_router.put("/settings")
async def admin_put_settings(body: AdminSettingsPatch, admin: Dict[str, Any] = Depends(_admin_dep)):
    patch = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="Nothing to update")
    if "provider" in patch and patch["provider"] not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider. Registered: {list(PROVIDERS.keys())}")
    if "enabled_instruments" in patch:
        bad = [s for s in patch["enabled_instruments"] if s not in INSTRUMENTS]
        if bad:
            raise HTTPException(status_code=400, detail=f"Unknown instruments: {bad}")
    await _db.market_settings.update_one({"_id": "default"}, {"$set": patch}, upsert=True)
    # Sprint 14.1.2b — shadow-write into the canonical market_provider_config
    # collection so keys saved from this legacy admin page also reach the
    # running ProviderManager (which never reads market_settings).
    try:
        from market_providers import key_store as _ks
        import market_providers as _mp
        _keys = (patch.get("api_keys") or {}) if isinstance(patch.get("api_keys"), dict) else {}
        for _fld, _prov in (("twelve_data", "twelvedata"),
                             ("twelvedata", "twelvedata"),
                             ("alpha_vantage", "alphavantage"),
                             ("alphavantage", "alphavantage")):
            _v = (_keys.get(_fld) or "").strip()
            if _v:
                await _ks.canonical_write(_db, _prov, _v)
                await _mp.propagate_api_key(_prov, _v)
    except Exception:
        pass
    # bust cache
    _quote_cache.clear()
    return {"ok": True, "settings": await get_settings(force=True)}


@admin_router.post("/refresh")
async def force_refresh(admin: Dict[str, Any] = Depends(_admin_dep)):
    _quote_cache.clear()
    return {"ok": True, "cleared": True}


@admin_router.get("/instruments")
async def list_instruments(admin: Dict[str, Any] = Depends(_admin_dep)):
    return {"items": [{"symbol": s, **m} for s, m in INSTRUMENTS.items()]}


# --------------------- attach ---------------------
def attach(api: APIRouter, *, db, get_current_user: Callable, get_current_admin: Callable, logger=None):
    global _db, _get_current_user, _get_current_admin, _logger
    _db = db
    _get_current_user = get_current_user
    _get_current_admin = get_current_admin
    _logger = logger
    api.include_router(user_router)
    api.include_router(admin_router)
