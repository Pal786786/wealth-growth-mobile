"""Transport abstraction — Sprint 7 Slice 1

MarketTransport decouples the DELIVERY MECHANISM from the DATA PROVIDER.

  PollingTransport   — asks the provider on a schedule and returns snapshots
  WebSocketTransport — pushes ticks to subscribers as they arrive (uses either
                       the provider's native WS or synthesized ticks from a
                       polling loop).

The UI subscribes via a single WS endpoint `/api/market_data/ws/stream` and
never knows which underlying transport is active. Admin can flip.

For Slice 1 we ship the two classes and wire both. Real WS provider integration
(TwelveData's ws) is a Slice 1.5 concern — for now we synthesize the tick loop
from the provider's REST/quote endpoint at a configurable interval.
"""
from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Optional, Set

from .providers import BaseProvider


class MarketTransport:
    """Base interface. Implementations manage the stream loop and dispatch."""
    name: str = "base"

    async def start(self): ...
    async def stop(self): ...

    async def subscribe(self, symbol_ids: List[str], sink) -> None:
        """Register `sink` (async callable receiving quote dict) for the given symbols."""
        raise NotImplementedError

    async def unsubscribe(self, symbol_ids: List[str], sink) -> None:
        raise NotImplementedError

    async def status(self) -> Dict[str, Any]:
        return {"name": self.name, "running": False}


class PollingTransport(MarketTransport):
    name = "polling"

    def __init__(self, provider: BaseProvider, interval_seconds: float = 3.0):
        self.provider = provider
        self.interval = max(0.5, float(interval_seconds))
        self._subs: Dict[str, Set] = {}      # symbol_id -> set of sinks
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._last_quotes: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def start(self):
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except Exception:
                pass
        self._task = None

    async def subscribe(self, symbol_ids: List[str], sink) -> None:
        async with self._lock:
            for sid in symbol_ids:
                sid = sid.upper()
                self._subs.setdefault(sid, set()).add(sink)
        # Immediately push last-known quote if we have one
        for sid in symbol_ids:
            q = self._last_quotes.get(sid.upper())
            if q:
                try:
                    await sink(q)
                except Exception:
                    pass

    async def unsubscribe(self, symbol_ids: List[str], sink) -> None:
        async with self._lock:
            for sid in symbol_ids:
                sid = sid.upper()
                if sid in self._subs:
                    self._subs[sid].discard(sink)
                    if not self._subs[sid]:
                        del self._subs[sid]

    async def _loop(self):
        while not self._stop.is_set():
            try:
                async with self._lock:
                    active = list(self._subs.keys())
                if active:
                    quotes = await self.provider.quotes(active)
                    for sid, q in quotes.items():
                        self._last_quotes[sid] = q
                        sinks = list(self._subs.get(sid, set()))
                        for sink in sinks:
                            try:
                                await sink(q)
                            except Exception:
                                pass
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                continue

    async def status(self) -> Dict[str, Any]:
        return {
            "name": "polling",
            "running": self._task is not None and not self._task.done(),
            "subscribed_symbols": len(self._subs),
            "interval_seconds": self.interval,
            "provider": self.provider.name,
        }


class WebSocketTransport(MarketTransport):
    """Placeholder for real provider-side WebSocket streaming.

    For MVP we fall back to polling if the provider does not support WS
    natively. When a provider (e.g. TwelveData paid) supports WS, extend
    this class to open the socket and forward messages to subscribers.
    """
    name = "websocket"

    def __init__(self, provider: BaseProvider, fallback_interval: float = 2.0):
        self.provider = provider
        # If the provider doesn't support real WS, we still work by wrapping
        # PollingTransport internally at a tighter interval. The UI just
        # sees a stream.
        self._inner = PollingTransport(provider, interval_seconds=fallback_interval)

    async def start(self): await self._inner.start()
    async def stop(self): await self._inner.stop()
    async def subscribe(self, symbol_ids, sink): await self._inner.subscribe(symbol_ids, sink)
    async def unsubscribe(self, symbol_ids, sink): await self._inner.unsubscribe(symbol_ids, sink)
    async def status(self) -> Dict[str, Any]:
        base = await self._inner.status()
        base.update({"name": "websocket", "mode": "polling-fallback" if not self.provider.supports_websocket else "native"})
        return base


def build_transport(name: str, provider: BaseProvider, interval_seconds: float = 3.0) -> MarketTransport:
    """Factory — Admin picks by name."""
    name = (name or "polling").lower()
    if name == "websocket":
        return WebSocketTransport(provider, fallback_interval=max(1.0, interval_seconds / 2))
    return PollingTransport(provider, interval_seconds=interval_seconds)
