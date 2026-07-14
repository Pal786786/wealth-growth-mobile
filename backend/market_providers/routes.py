"""Live Market — Admin routes (Sprint 7.5)

All endpoints are admin-only. Consumers read prices via the shared cache,
they never hit these routes.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .manager import ProviderManager


class ManualProviderIn(BaseModel):
    provider: Optional[str] = None       # None → clear override (auto-select)


class AutoFallbackIn(BaseModel):
    enabled: bool


class RefreshIntervalIn(BaseModel):
    seconds: int


class UniverseIn(BaseModel):
    symbols: List[str]


class ApiKeyIn(BaseModel):
    provider: str      # 'twelvedata' | 'alphavantage'
    key: str


def attach(app, manager: ProviderManager, get_current_admin):
    r = APIRouter(prefix="/api/market_providers", tags=["market-providers"])

    @r.get("/status")
    async def status(admin=Depends(get_current_admin)):
        return await manager.status()

    @r.get("/quotes")
    async def all_quotes(admin=Depends(get_current_admin)):
        return {"quotes": await manager.cache.all_quotes()}

    @r.get("/quote/{symbol}")
    async def one_quote(symbol: str, admin=Depends(get_current_admin)):
        doc = await manager.cache.get(symbol)
        if not doc:
            raise HTTPException(404, "no cached quote for that symbol")
        return doc

    @r.post("/refresh")
    async def refresh_now(admin=Depends(get_current_admin)):
        return await manager.refresh_once()

    @r.get("/health")
    async def health(admin=Depends(get_current_admin), provider: Optional[str] = None):
        return await manager.health_check(provider)

    @r.get("/history")
    async def history(limit: int = 100, admin=Depends(get_current_admin)):
        return {"history": await manager.recent_history(limit=limit)}

    @r.put("/manual-provider")
    async def set_manual(body: ManualProviderIn, admin=Depends(get_current_admin)):
        try:
            await manager.set_manual_provider(body.provider)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return await manager.status()

    @r.put("/auto-fallback")
    async def set_fallback(body: AutoFallbackIn, admin=Depends(get_current_admin)):
        await manager.set_auto_fallback(body.enabled)
        return {"auto_fallback": body.enabled}

    @r.put("/refresh-interval")
    async def set_interval(body: RefreshIntervalIn, admin=Depends(get_current_admin)):
        await manager.set_refresh_interval(body.seconds)
        return {"refresh_interval_sec": manager.refresh_interval_sec}

    @r.put("/universe")
    async def set_universe(body: UniverseIn, admin=Depends(get_current_admin)):
        await manager.set_universe(body.symbols)
        return {"universe": manager.universe}

    @r.put("/api-key")
    async def set_key(body: ApiKeyIn, admin=Depends(get_current_admin)):
        try:
            result = await manager.set_api_key(body.provider, body.key)
        except ValueError as e:
            raise HTTPException(400, str(e))
        # `result` already contains {provider, configured, test_ok, test_result}
        return result

    @r.delete("/cache")
    async def clear_cache(admin=Depends(get_current_admin)):
        await manager.cache.clear()
        return {"cleared": True}

    app.include_router(r)
    return r
