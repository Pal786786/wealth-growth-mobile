"""Copy Trading — In-process Event Bus (Sprint 7B.2)

Simple asyncio-based publish/subscribe bus. Broker-agnostic. The Master
Simulator emits `TRADE_OPENED` / `TRADE_MODIFIED` / `TRADE_CLOSED` events;
the Copy Engine subscribes and fans out to followers.

Why an in-process bus (and not Redis)? Because MVP + a single backend process.
When the app scales horizontally we swap this file for a Redis pub/sub (or
Kafka) shim — the public API (publish / subscribe) does not change.
"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("copy.events")

# Canonical event names
TRADE_OPENED = "trade.opened"
TRADE_MODIFIED = "trade.modified"
TRADE_CLOSED = "trade.closed"
SIM_STATE_CHANGED = "sim.state_changed"

Handler = Callable[["TradeEvent"], Awaitable[None]]


@dataclass
class TradeEvent:
    kind: str                       # TRADE_OPENED | TRADE_MODIFIED | TRADE_CLOSED
    trader_id: str
    master_id: str
    symbol: str
    side: str                       # buy | sell
    lot_size: float
    entry_price: float
    exit_price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    pnl_pct: Optional[float] = None
    source: str = "sim"             # sim | admin | broker
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    payload: Dict[str, Any] = field(default_factory=dict)


class EventBus:
    def __init__(self):
        self._subs: Dict[str, List[Handler]] = {}
        self._lock = asyncio.Lock()

    def subscribe(self, kind: str, handler: Handler) -> None:
        self._subs.setdefault(kind, []).append(handler)

    async def publish(self, event: TradeEvent) -> None:
        handlers = list(self._subs.get(event.kind, []))
        if not handlers:
            return
        # Run handlers concurrently; log but don't raise
        results = await asyncio.gather(
            *[self._safe_call(h, event) for h in handlers], return_exceptions=True
        )
        for r in results:
            if isinstance(r, Exception):
                logger.warning("bus handler failed: %s", r)

    @staticmethod
    async def _safe_call(handler: Handler, event: TradeEvent):
        try:
            await handler(event)
        except Exception as e:
            logger.exception("event handler crash on %s: %s", event.kind, e)
            raise


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
