"""Provider abstraction — Sprint 7 Slice 1

BaseProvider: interface every market data provider implements.
MockProvider:  deterministic random-walk driven by the catalog seeds; always
               available even without any API keys.
TwelveDataProvider: real HTTPS/WebSocket adapter. Activates only when the admin
               has configured an API key. Stub for network calls — real HTTP
               calls only fire when key present so tests can run offline.

Future providers (AlphaVantage, Finnhub, Polygon, KiteConnect, Upstox) plug in
here without touching route or frontend code.
"""
from __future__ import annotations
import asyncio
import hashlib
import random
import time
from typing import Any, Dict, List, Optional

import httpx

from .catalog import BY_ID


class BaseProvider:
    """Abstract market data provider."""
    name: str = "base"
    # supports_websocket: some providers offer WS streaming (Polygon, Finnhub,
    # TwelveData paid); others only REST polling. The MarketTransport layer
    # reads this hint to decide whether to open a WS connection or fall back.
    supports_websocket: bool = False
    requires_key: bool = True

    async def health(self) -> Dict[str, Any]:
        return {"name": self.name, "ok": True, "note": "base"}

    async def quote(self, symbol_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    async def quotes(self, symbol_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Batch quote — default naive impl calls .quote() in parallel."""
        out: Dict[str, Dict[str, Any]] = {}
        results = await asyncio.gather(*[self.quote(s) for s in symbol_ids], return_exceptions=True)
        for sid, r in zip(symbol_ids, results):
            if isinstance(r, dict):
                out[sid] = r
        return out

    async def history(self, symbol_id: str, points: int = 60) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def close(self):
        pass


# ---------------------------------------------------------------------------
# Mock provider — deterministic random-walk driven by catalog seeds
# ---------------------------------------------------------------------------
class MockProvider(BaseProvider):
    name = "mock"
    supports_websocket = False
    requires_key = False

    def __init__(self):
        self._state: Dict[str, float] = {}   # symbol_id -> current price
        self._t0 = time.time()
        random.seed(42)

    async def health(self) -> Dict[str, Any]:
        return {"name": "mock", "ok": True, "symbols": len(BY_ID)}

    def _walk(self, meta: Dict[str, Any]) -> float:
        sid = meta["symbol_id"]
        px = self._state.get(sid) or meta["seed"]
        vol = float(meta.get("vol", 0.002))
        trend = float(meta.get("trend", 0.0))
        # step ~ 1s tick; small random walk with tiny drift
        step = (random.gauss(0, 1) * vol + trend) * px * 0.15
        px = max(px + step, meta["seed"] * 0.5)  # never crash to zero
        self._state[sid] = px
        return px

    async def quote(self, symbol_id: str) -> Optional[Dict[str, Any]]:
        meta = BY_ID.get(symbol_id.upper())
        if not meta:
            return None
        px = self._walk(meta)
        dp = int(meta.get("price_dp", 5))
        # tiny synthetic bid/ask spread
        spread_bp = 0.0002
        return {
            "symbol_id": meta["symbol_id"],
            "display": meta["display"],
            "name": meta["name"],
            "category": meta["category"],
            "currency": meta["currency"],
            "price_dp": dp,
            "mid": round(px, dp),
            "bid": round(px * (1 - spread_bp / 2), dp),
            "ask": round(px * (1 + spread_bp / 2), dp),
            "ts": time.time(),
            "source": "mock",
            "change_pct": round((px - meta["seed"]) / meta["seed"] * 100, 2),
        }

    async def history(self, symbol_id: str, points: int = 60) -> List[Dict[str, Any]]:
        meta = BY_ID.get(symbol_id.upper())
        if not meta:
            return []
        now = time.time()
        seed = int(hashlib.sha256((symbol_id + "hist").encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        px = meta["seed"]
        vol = float(meta.get("vol", 0.002))
        pts: List[Dict[str, Any]] = []
        for i in range(points):
            ts = now - (points - 1 - i) * 60
            step = rng.gauss(0, 1) * vol * px * 0.10
            px = max(px + step, meta["seed"] * 0.6)
            pts.append({"ts": ts, "mid": round(px, meta["price_dp"])})
        return pts


# ---------------------------------------------------------------------------
# TwelveData provider — activates only when API key is set in admin settings.
# ---------------------------------------------------------------------------
class TwelveDataProvider(BaseProvider):
    name = "twelvedata"
    supports_websocket = True  # supported on Grow plans and above
    requires_key = True
    BASE = "https://api.twelvedata.com"

    def __init__(self, api_key: str, request_timeout: float = 8.0):
        self.api_key = api_key
        self._timeout = request_timeout
        self._client = httpx.AsyncClient(timeout=request_timeout,
                                         headers={"Accept": "application/json"})
        self.last_error: Optional[str] = None
        self.last_success_at: Optional[float] = None

    async def health(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"name": "twelvedata", "ok": False, "error": "no_api_key"}
        try:
            r = await self._client.get(f"{self.BASE}/api_usage",
                                       params={"apikey": self.api_key})
            data = r.json() if r.status_code == 200 else {}
            self.last_success_at = time.time()
            return {"name": "twelvedata", "ok": r.status_code == 200,
                    "credits_used": data.get("current_usage"),
                    "credits_limit": data.get("plan_limit"),
                    "http": r.status_code}
        except Exception as e:
            self.last_error = str(e)[:160]
            return {"name": "twelvedata", "ok": False, "error": self.last_error}

    async def quote(self, symbol_id: str) -> Optional[Dict[str, Any]]:
        meta = BY_ID.get(symbol_id.upper())
        if not meta:
            return None
        td_sym = meta["provider_symbols"].get("twelvedata")
        if not td_sym or not self.api_key:
            return None
        try:
            r = await self._client.get(f"{self.BASE}/price",
                                       params={"symbol": td_sym, "apikey": self.api_key})
            if r.status_code != 200:
                self.last_error = f"HTTP {r.status_code}"
                return None
            data = r.json() or {}
            px = float(data.get("price") or 0)
            if px <= 0:
                self.last_error = "no_price_in_response"
                return None
            self.last_success_at = time.time()
            dp = int(meta.get("price_dp", 5))
            spread_bp = 0.0002
            return {
                "symbol_id": meta["symbol_id"],
                "display": meta["display"],
                "name": meta["name"],
                "category": meta["category"],
                "currency": meta["currency"],
                "price_dp": dp,
                "mid": round(px, dp),
                "bid": round(px * (1 - spread_bp / 2), dp),
                "ask": round(px * (1 + spread_bp / 2), dp),
                "ts": time.time(),
                "source": "twelvedata",
                "change_pct": None,
            }
        except Exception as e:
            self.last_error = str(e)[:160]
            return None

    async def history(self, symbol_id: str, points: int = 60) -> List[Dict[str, Any]]:
        meta = BY_ID.get(symbol_id.upper())
        if not meta or not self.api_key:
            return []
        td_sym = meta["provider_symbols"].get("twelvedata")
        if not td_sym:
            return []
        try:
            r = await self._client.get(f"{self.BASE}/time_series", params={
                "symbol": td_sym, "interval": "1min",
                "outputsize": points, "apikey": self.api_key,
            })
            if r.status_code != 200:
                return []
            data = r.json() or {}
            values = data.get("values") or []
            out: List[Dict[str, Any]] = []
            for v in reversed(values):  # oldest first
                try:
                    px = float(v.get("close") or v.get("open") or 0)
                    ts_iso = v.get("datetime") or ""
                    ts = time.time()
                    if ts_iso:
                        from datetime import datetime as _dt
                        try:
                            ts = _dt.strptime(ts_iso, "%Y-%m-%d %H:%M:%S").timestamp()
                        except Exception:
                            pass
                    if px > 0:
                        out.append({"ts": ts, "mid": round(px, meta["price_dp"])})
                except Exception:
                    continue
            return out
        except Exception as e:
            self.last_error = str(e)[:160]
            return []

    async def close(self):
        try:
            await self._client.aclose()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Registry — Admin picks the active provider by name
# ---------------------------------------------------------------------------
def build_provider(name: str, settings: Dict[str, Any]) -> BaseProvider:
    """Factory that returns a provider instance based on admin settings.

    settings shape:
        {
          "provider": "mock" | "twelvedata" | ...
          "api_keys": { "twelvedata": "...", "alpha_vantage": "...", "finnhub": "..." }
        }
    """
    keys = settings.get("api_keys") or {}
    name = (name or "mock").lower()
    if name == "twelvedata":
        key = keys.get("twelvedata") or ""
        if not key:
            return MockProvider()  # graceful fallback if key not set
        return TwelveDataProvider(api_key=key)
    # Placeholder future providers — extend here:
    # if name == "alpha_vantage": ...
    # if name == "finnhub": ...
    # if name == "polygon": ...
    return MockProvider()
