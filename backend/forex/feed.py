"""Price Feed orchestrator — polls providers and keeps an in-memory cache.

The FastAPI route handlers read from this cache; the paper-trading engine
also reads from this cache to mark-to-market.
"""
from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, Dict, Optional

from collections import deque

from .symbols import SYMBOLS
from .providers import Quote, SimulatedProvider, TwelveDataProvider, BinanceProvider

logger = logging.getLogger("forex.feed")

# Ring-buffer size for chart history (kept per symbol).
# 2s tick × 300 points ≈ last 10 minutes of price history.
HISTORY_MAXLEN = 300

# Sprint 14.1.1 — reference to the shared ProviderManager so PriceFeed can
# read from the SAME market_price_cache that AI Signals / Watchlist / Alerts /
# Copy Trading / Gold all use. Set by `attach_shared_manager()` from server.py.
_shared_manager: Any = None


def attach_shared_manager(mgr: Any) -> None:
    """Wire the shared market-data ProviderManager into the forex feed so that
    all consumers (execution, UI, mark-to-market, chart, watchlist) read from
    a single source of truth for live prices."""
    global _shared_manager
    _shared_manager = mgr


class PriceFeed:
    """In-memory price cache + background polling."""

    def __init__(self):
        self._sim = SimulatedProvider(SYMBOLS)
        self._td: Optional[TwelveDataProvider] = None
        self._binance = BinanceProvider()
        self._cache: Dict[str, Quote] = {}
        # Rolling price history per symbol — used by the mobile chart so that
        # the watchlist, order screen and chart all share ONE price source.
        self._history: Dict[str, "deque"] = {
            s["id"]: deque(maxlen=HISTORY_MAXLEN) for s in SYMBOLS
        }
        self._stop = asyncio.Event()
        self._poll_task: Optional[asyncio.Task] = None
        self.last_td_error: Optional[str] = None
        self.last_td_success_ts: float = 0
        self.td_credits_left: Optional[int] = None
        self.live_mode: bool = False  # flipped by admin to switch providers
        self.td_api_key: Optional[str] = None

    def set_live_mode(self, enabled: bool, td_api_key: Optional[str] = None):
        self.live_mode = bool(enabled)
        self.td_api_key = (td_api_key or "").strip() or None
        if self.live_mode and self.td_api_key:
            self._td = TwelveDataProvider(api_key=self.td_api_key)
        else:
            self._td = None
        # Start/stop Binance based on live mode (avoid retry spam in dev)
        try:
            loop = asyncio.get_event_loop()
            if self.live_mode:
                loop.create_task(self._binance.start())
            else:
                loop.create_task(self._binance.stop())
        except RuntimeError:
            pass

    async def start(self):
        if self._poll_task and not self._poll_task.done():
            return
        # Seed cache immediately with simulated quotes so first /prices call works,
        # and pre-populate a small history so the chart renders on first render.
        base_ts = time.time() - 120  # 60 points × 2s = ~2 minutes of priors
        for sym in SYMBOLS:
            for i in range(60):
                q = self._sim.tick(sym["id"])
                self._history[sym["id"]].append((base_ts + i * 2.0, q.mid))
            latest = self._sim.tick(sym["id"])
            self._cache[sym["id"]] = latest
            self._history[sym["id"]].append((latest.ts, latest.mid))
        # Binance WS only attempted in live mode (avoids region-blocked retry spam)
        if self.live_mode:
            await self._binance.start()
        self._stop.clear()
        self._poll_task = asyncio.create_task(self._poll_forever())

    async def stop(self):
        self._stop.set()
        if self._poll_task:
            try:
                await asyncio.wait_for(self._poll_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):  # pragma: no cover
                pass
        await self._binance.stop()
        if self._td:
            await self._td.aclose()

    async def _poll_forever(self):
        """Tick every 2s for simulated; refresh from Twelve Data every 120s if live mode on.

        Sprint 14.1.1 hardening — once a symbol has a LIVE quote (twelvedata /
        binance / shared market_price_cache) that is younger than 10 minutes,
        the simulated provider **must not** overwrite it. Previously the
        freshness guard was only 150 s, so once TwelveData throttled we
        silently reverted to sim prices, breaking order-vs-UI consistency.
        """
        td_interval = 120.0
        last_td_poll = 0.0
        LIVE_MAX_AGE_SEC = 600     # 10-minute grace — sim never wins during this window
        while not self._stop.is_set():
            now = time.time()
            # Pull a snapshot of the SHARED market cache so we can honour its
            # priority guard. Any symbol with a fresh entry there is preferred.
            shared_map: Dict[str, Any] = {}
            try:
                if _shared_manager is not None:
                    shared_all = await _shared_manager.cache.all_quotes()
                    for row in shared_all:
                        shared_map[row["symbol"].upper()] = row
            except Exception:
                shared_map = {}

            for sym in SYMBOLS:
                sid = sym["id"]
                existing = self._cache.get(sid)

                # 1. Honour the shared cache first — if it has a fresh, real-provider
                #    entry, mirror it into the forex feed so execution + UI + shared
                #    readers all use the SAME price.
                shared_row = shared_map.get(sid)
                if shared_row and shared_row.get("provider") not in (None, "mock", "sim"):
                    age = float(shared_row.get("age_sec") or 0)
                    if age <= LIVE_MAX_AGE_SEC:
                        px = float(shared_row.get("price"))
                        bid = float(shared_row.get("bid") or (px - (sym["spread_pips"] * sym["pip_size"]) / 2))
                        ask = float(shared_row.get("ask") or (px + (sym["spread_pips"] * sym["pip_size"]) / 2))
                        self._cache[sid] = Quote(
                            symbol_id=sid, bid=bid, ask=ask, mid=px, ts=now,
                            source=str(shared_row.get("provider") or "shared"),
                        )
                        self._history[sid].append((now, px))
                        continue

                # 2. Never let sim overwrite an in-process LIVE quote within the grace window
                if existing and existing.source in ("twelvedata", "binance") \
                        and (now - existing.ts) < LIVE_MAX_AGE_SEC:
                    continue

                # 3. BTC: prefer Binance
                if sid == "BTCUSD":
                    binance_px = self._binance.latest_price("BTCUSD")
                    if binance_px:
                        spread = sym["spread_pips"] * sym["pip_size"]
                        self._cache["BTCUSD"] = Quote(
                            symbol_id="BTCUSD",
                            bid=round(binance_px - spread/2, sym["price_decimals"]),
                            ask=round(binance_px + spread/2, sym["price_decimals"]),
                            mid=binance_px, ts=now, source="binance",
                        )
                        self._history["BTCUSD"].append((now, binance_px))
                        continue

                # 4. Fallback to simulated tick (only if no live quote at all)
                q = self._sim.tick(sid)
                self._cache[sid] = q
                self._history[sid].append((q.ts, q.mid))

            # Twelve Data refresh (only in live mode)
            if self.live_mode and self._td and (now - last_td_poll) >= td_interval:
                last_td_poll = now
                try:
                    quotes = await self._td.fetch_quotes(SYMBOLS)
                    for sid, q in quotes.items():
                        self._cache[sid] = q
                    self.last_td_error = None
                    self.last_td_success_ts = now
                    self.td_credits_left = self._td.credits_left
                except Exception as e:
                    self.last_td_error = str(e)[:200]
                    self.td_credits_left = getattr(self._td, "credits_left", None)

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                continue

    def get_quote(self, symbol_id: str) -> Optional[Quote]:
        return self._cache.get(symbol_id.upper())

    def get_all_quotes(self) -> Dict[str, Quote]:
        return dict(self._cache)

    def get_history(self, symbol_id: str, limit: int = 100) -> list:
        """Return the last N (timestamp, mid) points captured for this symbol."""
        buf = self._history.get(symbol_id.upper())
        if not buf:
            return []
        limit = max(1, min(limit, HISTORY_MAXLEN))
        pts = list(buf)[-limit:]
        return [{"ts": ts, "mid": mid} for ts, mid in pts]

    def diagnostics(self) -> Dict:
        return {
            "live_mode": self.live_mode,
            "td_key_set": bool(self.td_api_key),
            "last_td_error": self.last_td_error,
            "last_td_success_ts": self.last_td_success_ts,
            "td_credits_left": self.td_credits_left,
            "binance_last_error": self._binance.last_error,
            "cache_size": len(self._cache),
        }
