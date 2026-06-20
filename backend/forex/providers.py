"""Price providers — pluggable architecture.

Three providers exist:
  - SimulatedProvider — pure random-walk fallback. No external dep. Always works.
  - TwelveDataProvider — REST polling (forex + gold). Requires TWELVEDATA_API_KEY.
  - BinanceProvider — WebSocket (BTC/USDT). Public, no auth.

The Feed orchestrator picks the best provider per symbol. If a paid provider
fails, it falls back to Simulated silently so paper trading never breaks.
"""
from __future__ import annotations
import asyncio
import json
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import logging

import httpx

logger = logging.getLogger("forex.providers")


@dataclass
class Quote:
    symbol_id: str
    bid: float
    ask: float
    mid: float
    ts: float
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol_id": self.symbol_id,
            "bid": self.bid,
            "ask": self.ask,
            "mid": self.mid,
            "ts": self.ts,
            "source": self.source,
            "age_ms": int((time.time() - self.ts) * 1000),
        }


class SimulatedProvider:
    """Random-walk fallback — always returns a quote."""

    name = "simulated"

    def __init__(self, symbols: List[Dict[str, Any]]):
        self._state: Dict[str, float] = {s["id"]: s["starting_price"] for s in symbols}
        self._symbols = {s["id"]: s for s in symbols}
        # seed deterministically so testing is stable per process
        self._rng = random.Random(1729)

    def tick(self, symbol_id: str) -> Quote:
        spec = self._symbols[symbol_id]
        sigma = spec["volatility"]
        last = self._state[symbol_id]
        # Geometric Brownian motion-ish step
        delta = self._rng.gauss(0, sigma) * last
        new = max(0.0001, last + delta)
        self._state[symbol_id] = new
        spread = spec["spread_pips"] * spec["pip_size"]
        bid = round(new - spread / 2, spec["price_decimals"])
        ask = round(new + spread / 2, spec["price_decimals"])
        mid = round((bid + ask) / 2, spec["price_decimals"])
        return Quote(symbol_id=symbol_id, bid=bid, ask=ask, mid=mid, ts=time.time(), source=self.name)


class TwelveDataProvider:
    """Twelve Data REST polling. Free tier: 800 calls/day, 8 calls/min.

    Batches up to 4 forex symbols in one call. If unavailable or quota
    exhausted, raises so the Feed can fall back to Simulated.
    """

    name = "twelvedata"
    BASE = "https://api.twelvedata.com"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TWELVEDATA_API_KEY") or "demo"
        self._client: Optional[httpx.AsyncClient] = None
        self.credits_left: Optional[int] = None
        self.last_error: Optional[str] = None

    async def _ensure_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.BASE, timeout=8.0)
        return self._client

    async def aclose(self):
        if self._client:
            try:
                await self._client.aclose()
            except Exception:  # pragma: no cover
                pass

    async def fetch_quotes(self, symbols: List[Dict[str, Any]]) -> Dict[str, Quote]:
        """Returns {symbol_id: Quote} for the given symbol specs."""
        td_symbols = [s for s in symbols if s.get("twelve_data")]
        if not td_symbols:
            return {}
        client = await self._ensure_client()
        param = ",".join(s["twelve_data"] for s in td_symbols)
        try:
            resp = await client.get("/quote", params={"symbol": param, "apikey": self.api_key})
        except Exception as e:
            self.last_error = f"network: {e}"
            raise
        # Track quota header for diagnostics
        try:
            self.credits_left = int(resp.headers.get("api-credits-left", -1))
        except Exception:
            self.credits_left = None
        if resp.status_code == 429:
            self.last_error = "rate-limited (HTTP 429)"
            raise RuntimeError(self.last_error)
        if resp.status_code != 200:
            self.last_error = f"http {resp.status_code}: {resp.text[:160]}"
            raise RuntimeError(self.last_error)
        data = resp.json()
        # Multi-symbol returns {sym: {...}}; single returns {...}
        if not isinstance(data, dict):
            raise RuntimeError("unexpected payload")
        if "code" in data and data.get("status") == "error":
            self.last_error = f"api error: {data.get('message') or data}"
            raise RuntimeError(self.last_error)
        out: Dict[str, Quote] = {}
        single = "symbol" in data and "close" in data  # single-symbol shape
        items = {data["symbol"]: data} if single else data
        for spec in td_symbols:
            td_key = spec["twelve_data"]
            q = items.get(td_key)
            if not q:
                continue
            try:
                price = float(q.get("close") or q.get("price") or q.get("last"))
            except (TypeError, ValueError):
                continue
            spread = spec["spread_pips"] * spec["pip_size"]
            bid = round(price - spread / 2, spec["price_decimals"])
            ask = round(price + spread / 2, spec["price_decimals"])
            out[spec["id"]] = Quote(symbol_id=spec["id"], bid=bid, ask=ask, mid=price,
                                    ts=time.time(), source=self.name)
        return out


class BinanceProvider:
    """Public WebSocket for BTC/USDT — no auth required."""

    name = "binance"
    WS_URL = "wss://stream.binance.com:9443/ws"

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._latest: Dict[str, float] = {}
        self._stop = asyncio.Event()
        self.last_error: Optional[str] = None

    async def start(self):
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._stop.set()
        if self._task:
            try:
                self._task.cancel()
            except Exception:  # pragma: no cover
                pass

    async def _run(self):
        # Try websockets lib; if missing, raise so Feed falls back to simulated
        try:
            import websockets  # type: ignore
        except ImportError:
            self.last_error = "websockets library not installed"
            return
        url = f"{self.WS_URL}/btcusdt@ticker"
        backoff = 1.0
        while not self._stop.is_set():
            try:
                async with websockets.connect(url, ping_interval=20, close_timeout=5) as ws:
                    backoff = 1.0
                    async for msg in ws:
                        try:
                            payload = json.loads(msg)
                            price = float(payload.get("c") or payload.get("p") or 0)
                            if price > 0:
                                self._latest["BTCUSD"] = price
                        except Exception:
                            continue
                        if self._stop.is_set():
                            break
            except Exception as e:
                self.last_error = str(e)[:160]
                logger.warning("binance ws error: %s — retrying in %ss", self.last_error, backoff)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                    break
                except asyncio.TimeoutError:
                    backoff = min(backoff * 2, 30.0)

    def latest_price(self, symbol_id: str) -> Optional[float]:
        return self._latest.get(symbol_id)
