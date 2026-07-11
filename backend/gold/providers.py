"""Gold provider abstraction — Mock + stubs for Augmont / MMTC-PAMP / SafeGold.

Each provider returns a canonical `{ok, price_per_gram_inr, buy_price, sell_price,
spread_bps, provider, source, quoted_at}`. Real backends can be plugged in
without changing engine logic.
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger("gold.providers")

# Grams per troy ounce (XAUUSD is per ounce)
GRAMS_PER_OZ = 31.1035
# INR/USD reference fallback
INR_USD_FALLBACK = 83.5


def _now():
    return datetime.now(timezone.utc)


class GoldProvider(Protocol):
    name: str
    real: bool
    def is_configured(self) -> bool: ...
    async def price_per_gram(self) -> Dict[str, Any]: ...


class MockGoldProvider:
    name = "mock"
    real = False

    def is_configured(self) -> bool:
        return True

    async def price_per_gram(self) -> Dict[str, Any]:
        # Deterministic ± 15 INR/g band around ₹6500/g so tests are stable but the
        # UI still shows a live-looking oscillation.
        seed = int(time.time() // 60)
        rnd = random.Random(seed)
        base = 6500.0
        drift = round(rnd.uniform(-15, 15), 2)
        return {
            "ok": True, "provider": self.name, "source": "mock",
            "price_per_gram_inr": round(base + drift, 2),
            "quoted_at": _now().isoformat(),
        }


class LiveMarketGoldProvider:
    """Derives ₹/g from the Live Market cache (XAUUSD * INR/USD / grams)."""
    name = "live_market"
    real = True

    def __init__(self, db):
        self.db = db

    def is_configured(self) -> bool:
        return True

    async def price_per_gram(self) -> Dict[str, Any]:
        try:
            xau = await self.db.market_price_cache.find_one(
                {"symbol": "XAUUSD"}, {"_id": 0, "price": 1, "updated_at": 1})
            usd_inr = await self.db.market_price_cache.find_one(
                {"symbol": "USDINR"}, {"_id": 0, "price": 1})
        except Exception:
            xau = usd_inr = None
        if not (xau and xau.get("price")):
            return {"ok": False, "provider": self.name, "source": "live_market",
                    "error": "XAUUSD not in cache"}
        rate = (usd_inr or {}).get("price") or INR_USD_FALLBACK
        per_gram = xau["price"] * rate / GRAMS_PER_OZ
        return {
            "ok": True, "provider": self.name, "source": "live_market",
            "price_per_gram_inr": round(per_gram, 2),
            "quoted_at": (xau.get("updated_at").isoformat()
                            if hasattr(xau.get("updated_at"), "isoformat")
                            else str(xau.get("updated_at") or _now().isoformat())),
            "xau_usd": xau["price"], "usd_inr": rate,
        }


class _StubRealProvider:
    """Base for real gold providers awaiting API keys.

    When not configured, delegates to LiveMarketGoldProvider so users still get
    a plausible price.
    """
    name = "stub"
    real = True

    def __init__(self, db, env_key: str):
        self.db = db
        self._api_key = (os.environ.get(env_key) or "").strip()

    def is_configured(self) -> bool:
        return bool(self._api_key and self._api_key != "placeholder")

    async def price_per_gram(self) -> Dict[str, Any]:
        if not self.is_configured():
            r = await LiveMarketGoldProvider(self.db).price_per_gram()
            r["provider"] = self.name
            r["source"] = f"{self.name}:fallback_live_market"
            return r
        return {"ok": False, "provider": self.name,
                "error": "real backend not yet implemented — stub only"}


class AugmontProvider(_StubRealProvider):
    name = "augmont"
    def __init__(self, db):
        super().__init__(db, "AUGMONT_API_KEY")


class MmtcPampProvider(_StubRealProvider):
    name = "mmtc_pamp"
    def __init__(self, db):
        super().__init__(db, "MMTC_PAMP_API_KEY")


class SafeGoldProvider(_StubRealProvider):
    name = "safegold"
    def __init__(self, db):
        super().__init__(db, "SAFEGOLD_API_KEY")


PROVIDER_REGISTRY = {
    "mock": lambda db: MockGoldProvider(),
    "live_market": lambda db: LiveMarketGoldProvider(db),
    "augmont": lambda db: AugmontProvider(db),
    "mmtc_pamp": lambda db: MmtcPampProvider(db),
    "safegold": lambda db: SafeGoldProvider(db),
}


def get_provider(db, name: str) -> Any:
    factory = PROVIDER_REGISTRY.get((name or "live_market").lower())
    if not factory:
        return LiveMarketGoldProvider(db)
    return factory(db)
