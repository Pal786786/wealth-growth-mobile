"""TwelveData Provider — Sprint 7.5

Free tier (as of 2026): 8 credits/min, 800 credits/day. Uses batch quote
endpoint `/quote?symbol=A,B,C` (1 credit per symbol). Symbol mapping is
handled internally so consumers keep using our canonical names (EURUSD,
XAUUSD, US30, BTCUSD, USOIL …).
"""
from __future__ import annotations
import logging
import os
from typing import Dict, List

import httpx
from .base import Provider, Quote, RateLimitError, ProviderNotConfigured

logger = logging.getLogger("market.providers.twelvedata")

BASE_URL = "https://api.twelvedata.com"

# Canonical symbol → TwelveData symbol
SYMBOL_MAP: Dict[str, str] = {
    # Forex majors
    "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY",
    "USDCHF": "USD/CHF", "USDCAD": "USD/CAD", "AUDUSD": "AUD/USD",
    "NZDUSD": "NZD/USD", "EURGBP": "EUR/GBP", "EURJPY": "EUR/JPY", "GBPJPY": "GBP/JPY",
    # Metals
    "XAUUSD": "XAU/USD", "XAGUSD": "XAG/USD",
    # Indices
    "US30": "DJI", "SPX500": "SPX", "NAS100": "NDX",
    "GER40": "DAX", "UK100": "UKX", "JPN225": "N225", "IND50": "NIFTY",
    # Crypto
    "BTCUSD": "BTC/USD", "ETHUSD": "ETH/USD",
    "SOLUSD": "SOL/USD", "XRPUSD": "XRP/USD", "ADAUSD": "ADA/USD",
    # Commodities / energy
    "USOIL": "WTI/USD", "UKOIL": "BRENT/USD", "NATGAS": "NG=F", "COPPER": "HG=F",
}


class TwelveDataProvider(Provider):
    name = "twelvedata"
    priority = 100      # highest priority

    def __init__(self, api_key: str = ""):
        super().__init__()
        self._api_key = (api_key or os.environ.get("TWELVEDATA_API_KEY") or "").strip()
        self.stats.daily_credits_limit = 800

    async def is_configured(self) -> bool:
        return bool(self._api_key)

    async def _fetch_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        if not self._api_key:
            raise ProviderNotConfigured("TWELVEDATA_API_KEY not set")
        canon = [s.upper() for s in symbols]
        td_syms = [SYMBOL_MAP.get(s, s) for s in canon]
        params = {"symbol": ",".join(td_syms), "apikey": self._api_key}
        async with httpx.AsyncClient(timeout=6.0) as client:
            r = await client.get(f"{BASE_URL}/quote", params=params)
            if r.status_code == 429:
                raise RateLimitError("TwelveData rate limit hit")
            r.raise_for_status()
            data = r.json()
        # TwelveData batch response is dict[symbol → dict] OR single dict if 1 symbol.
        out: Dict[str, Quote] = {}
        if isinstance(data, dict) and "symbol" in data and "close" in data:
            # single-symbol response
            data = {data["symbol"]: data}
        for i, td_sym in enumerate(td_syms):
            payload = data.get(td_sym) if isinstance(data, dict) else None
            if not payload:
                continue
            if payload.get("status") == "error":
                # code 429 arrives as JSON body too
                if "credits" in (payload.get("message") or "").lower():
                    raise RateLimitError(payload.get("message", "rate limit"))
                continue
            try:
                price = float(payload["close"])
            except (KeyError, ValueError, TypeError):
                continue
            change_pct = None
            try:
                change_pct = float(payload.get("percent_change") or 0) or None
            except (ValueError, TypeError):
                pass
            out[canon[i]] = Quote(
                symbol=canon[i], price=price,
                change_pct=change_pct, provider=self.name, raw=payload,
            )
        return out

    def set_api_key(self, key: str):
        self._api_key = (key or "").strip()
