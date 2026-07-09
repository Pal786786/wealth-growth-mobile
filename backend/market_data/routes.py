"""Market Data routes — Sprint 7 Slice 1

Endpoints under /api/market_data/*:
  GET  /categories                 -> list categories with counts
  GET  /catalog                    -> paginated symbol browser (filter/search)
  GET  /symbols/{symbol_id}        -> single instrument metadata
  GET  /quote/{symbol_id}          -> current quote via active provider
  GET  /quotes?symbols=...         -> batch quotes
  GET  /history/{symbol_id}        -> historical points (mid over time)

  GET  /favorites                  -> user's favorites list (persisted)
  POST /favorites/{symbol_id}      -> add favorite
  DEL  /favorites/{symbol_id}      -> remove favorite
  POST /recently-viewed/{sym}      -> log a view
  GET  /recently-viewed            -> last 20 viewed symbols

  WS   /ws/stream                  -> live price stream (subscribe/unsubscribe)

  Admin:
  GET  /admin/status               -> provider + transport diagnostics
  PUT  /admin/settings             -> update provider, transport, api keys

Note:
  KYC gate is NOT applied — market browsing is public per business flow.
"""
from __future__ import annotations
import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from . import catalog as catmod
from .providers import build_provider, BaseProvider
from .transports import build_transport, MarketTransport

# --------- injected globals ---------
_db = None
_get_current_user: Optional[Callable] = None
_get_current_admin: Optional[Callable] = None
_provider: Optional[BaseProvider] = None
_transport: Optional[MarketTransport] = None
_settings_cache: Dict[str, Any] = {}
_settings_cache_at: float = 0

DEFAULT_SETTINGS: Dict[str, Any] = {
    "provider": "mock",              # "mock" | "twelvedata"
    "transport": "polling",          # "polling" | "websocket"
    "interval_seconds": 3.0,
    "api_keys": {"twelvedata": "", "alpha_vantage": "", "finnhub": "", "polygon": ""},
    "enabled_categories": ["forex_majors", "forex_minors", "metals", "energies", "indices", "crypto", "commodities"],
}


async def _get_settings(force: bool = False) -> Dict[str, Any]:
    global _settings_cache, _settings_cache_at
    if not force and _settings_cache and time.time() - _settings_cache_at < 15:
        return _settings_cache
    doc = await _db.market_data_settings.find_one({"_id": "default"}) or {}
    merged = {**DEFAULT_SETTINGS, **{k: v for k, v in doc.items() if k != "_id"}}
    if "api_keys" in doc:
        merged["api_keys"] = {**DEFAULT_SETTINGS["api_keys"], **(doc.get("api_keys") or {})}
    _settings_cache = merged
    _settings_cache_at = time.time()
    return merged


async def _reload_pipeline():
    """Rebuild provider + transport from current admin settings."""
    global _provider, _transport
    s = await _get_settings(force=True)
    # stop old
    try:
        if _transport:
            await _transport.stop()
    except Exception:
        pass
    try:
        if _provider:
            await _provider.close()
    except Exception:
        pass
    _provider = build_provider(s["provider"], s)
    _transport = build_transport(s["transport"], _provider, interval_seconds=s.get("interval_seconds", 3.0))
    await _transport.start()


# ---------------------------------------------------------------------------
# Attach
# ---------------------------------------------------------------------------
def attach(app, db, get_current_user, get_current_admin, logger=None) -> APIRouter:
    global _db, _get_current_user, _get_current_admin
    _db = db
    _get_current_user = get_current_user
    _get_current_admin = get_current_admin

    api = APIRouter(prefix="/api/market_data", tags=["market-data"])
    admin_r = APIRouter(prefix="/api/admin/market_data", tags=["market-data-admin"])

    # ---------------- public catalog ----------------
    @api.get("/categories")
    async def list_categories():
        return {"categories": catmod.category_stats()}

    @api.get("/catalog")
    async def get_catalog(
        category: Optional[str] = Query(None, description="Filter by category id"),
        search: Optional[str] = Query(None, description="Search across id/display/name"),
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=200),
    ):
        if search:
            items = catmod.search_catalog(search, limit=500)
        elif category:
            items = catmod.by_category(category)
        else:
            items = list(catmod.ALL_INSTRUMENTS)
        return catmod.paginate(items, page=page, limit=limit)

    @api.get("/symbols/{symbol_id}")
    async def get_symbol(symbol_id: str):
        meta = catmod.BY_ID.get(symbol_id.upper())
        if not meta:
            raise HTTPException(404, "Symbol not found")
        return meta

    # ---------------- live quotes ----------------
    @api.get("/quote/{symbol_id}")
    async def get_quote(symbol_id: str):
        if not _provider:
            raise HTTPException(503, "provider not ready")
        q = await _provider.quote(symbol_id)
        if not q:
            raise HTTPException(404, "no quote available")
        return q

    @api.get("/quotes")
    async def get_quotes(symbols: str = Query(..., description="comma-separated symbol ids")):
        if not _provider:
            raise HTTPException(503, "provider not ready")
        sids = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if not sids:
            return {"quotes": []}
        if len(sids) > 100:
            raise HTTPException(400, "too many symbols (max 100)")
        result = await _provider.quotes(sids)
        return {"quotes": list(result.values()), "ts": time.time()}

    @api.get("/history/{symbol_id}")
    async def get_history(symbol_id: str, points: int = Query(60, ge=10, le=300)):
        if not _provider:
            raise HTTPException(503, "provider not ready")
        pts = await _provider.history(symbol_id, points=points)
        return {"symbol_id": symbol_id.upper(), "points": pts}

    # ---------------- favorites (persisted per user) ----------------
    @api.get("/favorites")
    async def get_favorites(user=Depends(get_current_user)):
        doc = await _db.market_favorites.find_one({"user_id": user["user_id"]}, {"_id": 0}) or {}
        symbols = doc.get("symbols") or []
        # Enrich with catalog meta
        items = [catmod.BY_ID[s] for s in symbols if s in catmod.BY_ID]
        return {"symbols": symbols, "items": items}

    @api.post("/favorites/{symbol_id}")
    async def add_favorite(symbol_id: str, user=Depends(get_current_user)):
        sid = symbol_id.upper()
        if sid not in catmod.BY_ID:
            raise HTTPException(404, "unknown symbol")
        await _db.market_favorites.update_one(
            {"user_id": user["user_id"]},
            {"$addToSet": {"symbols": sid},
             "$set": {"updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        return {"ok": True, "symbol_id": sid}

    @api.delete("/favorites/{symbol_id}")
    async def del_favorite(symbol_id: str, user=Depends(get_current_user)):
        sid = symbol_id.upper()
        await _db.market_favorites.update_one(
            {"user_id": user["user_id"]},
            {"$pull": {"symbols": sid},
             "$set": {"updated_at": datetime.now(timezone.utc)}},
        )
        return {"ok": True, "symbol_id": sid}

    # ---------------- recently viewed ----------------
    RV_MAX = 20

    @api.post("/recently-viewed/{symbol_id}")
    async def add_recent(symbol_id: str, user=Depends(get_current_user)):
        sid = symbol_id.upper()
        if sid not in catmod.BY_ID:
            raise HTTPException(404, "unknown symbol")
        now = datetime.now(timezone.utc)
        # Pull existing entry, push new to front, cap at RV_MAX
        await _db.market_recent.update_one(
            {"user_id": user["user_id"]},
            {"$pull": {"entries": {"symbol_id": sid}}},
            upsert=True,
        )
        await _db.market_recent.update_one(
            {"user_id": user["user_id"]},
            {"$push": {"entries": {"$each": [{"symbol_id": sid, "at": now}],
                                    "$position": 0,
                                    "$slice": RV_MAX}}},
        )
        return {"ok": True}

    @api.get("/recently-viewed")
    async def list_recent(user=Depends(get_current_user)):
        doc = await _db.market_recent.find_one({"user_id": user["user_id"]}, {"_id": 0}) or {}
        entries = doc.get("entries") or []
        items = [catmod.BY_ID[e["symbol_id"]] for e in entries if e.get("symbol_id") in catmod.BY_ID]
        return {"entries": entries, "items": items}

    # ---------------- WebSocket stream ----------------
    @api.websocket("/ws/stream")
    async def ws_stream(ws: WebSocket):
        """Client protocol:
          send  {"action": "subscribe",   "symbols": ["EURUSD","BTCUSD"]}
          send  {"action": "unsubscribe", "symbols": ["EURUSD"]}
          recv  {"type":"quote", ...quote fields...}
          recv  {"type":"error","message":"..."}
        Auth is optional here (public market data). Add token check if needed.
        """
        await ws.accept()
        symbols: set = set()
        outbound: asyncio.Queue = asyncio.Queue(maxsize=200)

        async def sink(q: Dict[str, Any]):
            try:
                await outbound.put({"type": "quote", **q})
            except asyncio.QueueFull:
                pass  # drop if slow client

        async def pump():
            while True:
                item = await outbound.get()
                try:
                    await ws.send_json(item)
                except Exception:
                    break

        pump_task = asyncio.create_task(pump())
        try:
            while True:
                msg = await ws.receive_json()
                action = (msg.get("action") or "").lower()
                syms = [s.upper() for s in (msg.get("symbols") or []) if isinstance(s, str)]
                syms = [s for s in syms if s in catmod.BY_ID][:100]
                if action == "subscribe" and _transport:
                    new = [s for s in syms if s not in symbols]
                    if new:
                        symbols.update(new)
                        await _transport.subscribe(new, sink)
                        await ws.send_json({"type": "subscribed", "symbols": new})
                elif action == "unsubscribe" and _transport:
                    to_remove = [s for s in syms if s in symbols]
                    if to_remove:
                        symbols.difference_update(to_remove)
                        await _transport.unsubscribe(to_remove, sink)
                        await ws.send_json({"type": "unsubscribed", "symbols": to_remove})
                elif action == "ping":
                    await ws.send_json({"type": "pong", "ts": time.time()})
                else:
                    await ws.send_json({"type": "error", "message": f"unknown action {action!r}"})
        except WebSocketDisconnect:
            pass
        except Exception as e:
            try:
                await ws.send_json({"type": "error", "message": str(e)[:200]})
            except Exception:
                pass
        finally:
            if _transport and symbols:
                try:
                    await _transport.unsubscribe(list(symbols), sink)
                except Exception:
                    pass
            pump_task.cancel()

    # ---------------- ADMIN ----------------
    class AdminSettings(BaseModel):
        provider: Optional[str] = None
        transport: Optional[str] = None
        interval_seconds: Optional[float] = None
        api_keys: Optional[Dict[str, str]] = None
        enabled_categories: Optional[List[str]] = None

    @admin_r.get("/status")
    async def admin_status(admin=Depends(get_current_admin)):
        s = await _get_settings(force=True)
        health = None
        if _provider:
            try:
                health = await _provider.health()
            except Exception as e:
                health = {"ok": False, "error": str(e)[:180]}
        tstat = await _transport.status() if _transport else None
        return {
            "settings": s,
            "provider_health": health,
            "transport_status": tstat,
            "catalog_size": len(catmod.ALL_INSTRUMENTS),
            "categories": catmod.category_stats(),
        }

    @admin_r.put("/settings")
    async def admin_put_settings(body: AdminSettings, admin=Depends(get_current_admin)):
        patch: Dict[str, Any] = {k: v for k, v in body.model_dump(exclude_none=True).items()}
        if not patch:
            raise HTTPException(400, "no fields to update")
        # merge api_keys instead of overwrite
        if "api_keys" in patch:
            cur = await _get_settings(force=True)
            patch["api_keys"] = {**(cur.get("api_keys") or {}), **patch["api_keys"]}
        await _db.market_data_settings.update_one(
            {"_id": "default"},
            {"$set": {**patch, "updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        await _reload_pipeline()
        s = await _get_settings(force=True)
        return {"ok": True, "settings": s}

    @admin_r.post("/test-provider")
    async def admin_test_provider(admin=Depends(get_current_admin)):
        if not _provider:
            raise HTTPException(503, "provider not ready")
        return {"ok": True, "health": await _provider.health()}

    # Start the pipeline on attach
    @app.on_event("startup")
    async def _startup():
        await _reload_pipeline()

    @app.on_event("shutdown")
    async def _shutdown():
        try:
            if _transport:
                await _transport.stop()
            if _provider:
                await _provider.close()
        except Exception:
            pass

    app.include_router(api)
    app.include_router(admin_r)
    return api
