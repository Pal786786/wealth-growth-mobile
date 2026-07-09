"""Mock Market Provider — Sprint 7.5

Wraps the existing deterministic synthesizer (ai_intelligence.feed.current_price)
so it behaves identically to a real provider. Always available (no keys) →
serves as the final fallback in the provider chain.
"""
from __future__ import annotations
from typing import Dict, List

from .base import Provider, Quote


class MockProvider(Provider):
    name = "mock"
    priority = 300     # lowest priority — only reached if all real providers fail

    async def _fetch_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        # Import lazily to avoid a hard import cycle if ai_intelligence loads first
        from ai_intelligence import feed
        out: Dict[str, Quote] = {}
        for sym in symbols:
            # Read directly from the deterministic synthesizer (skip live memo,
            # otherwise we'd feed our own previous output back).
            candles = feed.get_candles(sym.upper(), "M5", count=1, skip_live=True)
            if not candles:
                continue
            price = float(candles[-1]["close"])
            if price <= 0:
                continue
            # Fake tight bid/ask spread of 0.02%
            spread = price * 0.0001
            out[sym.upper()] = Quote(
                symbol=sym.upper(), price=price,
                bid=round(price - spread, 8), ask=round(price + spread, 8),
                provider=self.name,
            )
        return out
