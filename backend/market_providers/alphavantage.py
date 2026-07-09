"""Alpha Vantage Provider — Sprint 7.5

Free tier: 5 req/min, 25 req/day. Only used when TwelveData fails.
Because AV has strict limits and no batch endpoint, we ONLY use it as a
fallback for the top ~10 most critical symbols; other symbols will fall
through to Mock automatically.

Realtime FX: /query?function=CURRENCY_EXCHANGE_RATE&from=EUR&to=USD
Realtime Crypto: /query?function=CURRENCY_EXCHANGE_RATE&from=BTC&to=USD
Global equities / indices: /query?function=GLOBAL_QUOTE&symbol=SPX
"""
from __future__ import annotations
import logging
import os
from typing import Dict, List

import httpx
from .base import Provider, Quote, RateLimitError, ProviderNotConfigured

logger = logging.getLogger("market.providers.alphavantage")

BASE_URL = "https://www.alphavantage.co/query"

# Categorise our canonical symbols
FX_PAIRS = {
    "EURUSD": ("EUR", "USD"), "GBPUSD": ("GBP", "USD"), "USDJPY": ("USD", "JPY"),
    "USDCHF": ("USD", "CHF"), "USDCAD": ("USD", "CAD"), "AUDUSD": ("AUD", "USD"),
    "NZDUSD": ("NZD", "USD"), "EURGBP": ("EUR", "GBP"),
    "XAUUSD": ("XAU", "USD"), "XAGUSD": ("XAG", "USD"),
}
CRYPTO_PAIRS = {
    "BTCUSD": ("BTC", "USD"), "ETHUSD": ("ETH", "USD"),
    "SOLUSD": ("SOL", "USD"), "XRPUSD": ("XRP", "USD"), "ADAUSD": ("ADA", "USD"),
}
EQUITY_SYMBOLS = {
    "US30": "DIA", "SPX500": "SPY", "NAS100": "QQQ",
}


class AlphaVantageProvider(Provider):
    name = "alphavantage"
    priority = 200

    def __init__(self, api_key: str = ""):
        super().__init__()
        self._api_key = (api_key or os.environ.get("ALPHA_VANTAGE_API_KEY") or "").strip()
        self.stats.daily_credits_limit = 25

    async def is_configured(self) -> bool:
        return bool(self._api_key)

    async def _fetch_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        if not self._api_key:
            raise ProviderNotConfigured("ALPHA_VANTAGE_API_KEY not set")
        out: Dict[str, Quote] = {}
        # Serial requests — AV doesn't support batch
        async with httpx.AsyncClient(timeout=6.0) as client:
            for sym in symbols:
                sym_u = sym.upper()
                try:
                    q = await self._fetch_one(client, sym_u)
                    if q:
                        out[sym_u] = q
                except RateLimitError:
                    raise
                except Exception as e:
                    logger.debug("AV %s failed: %s", sym_u, e)
                    continue
        return out

    async def _fetch_one(self, client: httpx.AsyncClient, sym: str) -> Quote | None:
        if sym in FX_PAIRS:
            frm, to = FX_PAIRS[sym]
            r = await client.get(BASE_URL, params={
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": frm, "to_currency": to, "apikey": self._api_key,
            })
            r.raise_for_status()
            data = r.json()
            block = data.get("Realtime Currency Exchange Rate") or {}
            if "Note" in data:
                raise RateLimitError(data["Note"])
            try:
                price = float(block.get("5. Exchange Rate"))
            except (TypeError, ValueError):
                return None
            bid = float(block["8. Bid Price"]) if "8. Bid Price" in block else None
            ask = float(block["9. Ask Price"]) if "9. Ask Price" in block else None
            return Quote(symbol=sym, price=price, bid=bid, ask=ask, provider=self.name, raw=block)
        if sym in CRYPTO_PAIRS:
            frm, to = CRYPTO_PAIRS[sym]
            r = await client.get(BASE_URL, params={
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": frm, "to_currency": to, "apikey": self._api_key,
            })
            r.raise_for_status()
            data = r.json()
            block = data.get("Realtime Currency Exchange Rate") or {}
            if "Note" in data:
                raise RateLimitError(data["Note"])
            try:
                price = float(block.get("5. Exchange Rate"))
            except (TypeError, ValueError):
                return None
            return Quote(symbol=sym, price=price, provider=self.name, raw=block)
        if sym in EQUITY_SYMBOLS:
            r = await client.get(BASE_URL, params={
                "function": "GLOBAL_QUOTE", "symbol": EQUITY_SYMBOLS[sym],
                "apikey": self._api_key,
            })
            r.raise_for_status()
            data = r.json()
            if "Note" in data:
                raise RateLimitError(data["Note"])
            block = data.get("Global Quote") or {}
            try:
                price = float(block.get("05. price"))
            except (TypeError, ValueError):
                return None
            return Quote(symbol=sym, price=price, provider=self.name, raw=block)
        return None    # unsupported → let manager fall to next provider

    def set_api_key(self, key: str):
        self._api_key = (key or "").strip()
