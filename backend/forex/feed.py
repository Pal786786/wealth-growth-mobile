"""Price Feed orchestrator — polls providers and keeps an in-memory cache.

The FastAPI route handlers read from this cache; the paper-trading engine
also reads from this cache to mark-to-market.
"""
from __future__ import annotations
import asyncio
import logging
import time
from typing import Dict, Optional

from .symbols import SYMBOLS
from .providers import Quote, SimulatedProvider, TwelveDataProvider, BinanceProvider

logger = logging.getLogger("forex.feed")


class PriceFeed:
    """In-memory price cache + background polling."""

    def __init__(self):
        self._sim = SimulatedProvider(SYMBOLS)
        self._td: Optional[TwelveDataProvider] = None
        self._binance = BinanceProvider()
        self._cache: Dict[str, Quote] = {}
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
        # Seed cache immediately with simulated quotes so first /prices call works
        for sym in SYMBOLS:
            self._cache[sym["id"]] = self._sim.tick(sym["id"])
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
        """Tick every 2s for simulated; refresh from Twelve Data every 120s if live mode on."""
        td_interval = 120.0
        last_td_poll = 0.0
        while not self._stop.is_set():
            now = time.time()
            # Always tick simulated to provide a fluid UI experience
            for sym in SYMBOLS:
                # If we have a recent Twelve Data quote (<150s old), don't overwrite with sim
                existing = self._cache.get(sym["id"])
                if existing and existing.source == "twelvedata" and (now - existing.ts) < 150:
                    continue
                # BTC: prefer Binance live price if available
                if sym["id"] == "BTCUSD":
                    binance_px = self._binance.latest_price("BTCUSD")
                    if binance_px:
                        spread = sym["spread_pips"] * sym["pip_size"]
                        self._cache["BTCUSD"] = Quote(
                            symbol_id="BTCUSD",
                            bid=round(binance_px - spread/2, sym["price_decimals"]),
                            ask=round(binance_px + spread/2, sym["price_decimals"]),
                            mid=binance_px,
                            ts=now,
                            source="binance",
                        )
                        continue
                self._cache[sym["id"]] = self._sim.tick(sym["id"])

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
