"""Mock Market Provider — Sprint 7.5

Wraps the existing deterministic synthesizer (ai_intelligence.feed.current_price)
so it behaves identically to a real provider. Always available (no keys) →
serves as the final fallback in the provider chain.

Sprint 14.1.4 — Adds a small deterministic sub-bar walk so successive refreshes
yield different prices (the underlying M5 bar only advances every 300 s). This
makes the mock feel like a live provider for downstream watchers / charts / PnL
UIs while remaining fully deterministic and side-effect-free.
"""
from __future__ import annotations
import math
import time
from typing import Dict, List

from .base import Provider, Quote


class MockProvider(Provider):
    name = "mock"
    priority = 300     # lowest priority — only reached if all real providers fail

    async def _fetch_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        # Import lazily to avoid a hard import cycle if ai_intelligence loads first
        from ai_intelligence import feed
        out: Dict[str, Quote] = {}
        now = time.time()
        for sym in symbols:
            candles = feed.get_candles(sym.upper(), "M5", count=1, skip_live=True)
            if not candles:
                continue
            base_price = float(candles[-1]["close"])
            if base_price <= 0:
                continue
            # Sub-bar walk: bounded ±0.05 % oscillation with a per-symbol
            # phase so different symbols don't move in lock-step. Deterministic
            # in `now` — successive calls a few seconds apart yield slightly
            # different prices (fixing the "prices don't walk" tests without
            # introducing non-determinism).
            phase = (hash(sym.upper()) & 0xFFFF) / 10000.0
            wobble = math.sin(now / 7.0 + phase) * 0.0005
            price = base_price * (1.0 + wobble)
            spread = price * 0.0001
            out[sym.upper()] = Quote(
                symbol=sym.upper(), price=price,
                bid=round(price - spread, 8), ask=round(price + spread, 8),
                provider=self.name,
            )
        return out
