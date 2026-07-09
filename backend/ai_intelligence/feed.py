"""AI Intelligence — Deterministic OHLCV synthesizer (Sprint 7C.1)

Given (symbol, timeframe), returns a deterministic candle series that looks
realistic enough for TA indicators. Uses SHA-256 seeded random walk so:
  * Same symbol+timeframe+bar_index → same candle (idempotent)
  * Different symbols get uncorrelated but plausible walks
  * Anchor price + volatility from `market_data.catalog.BY_ID`

Later this file can be swapped for a real provider (TwelveData, Alpha Vantage)
without changing signal_engine / ta_engine.
"""
from __future__ import annotations
import hashlib
import math
import time
from typing import Dict, List, Tuple

from market_data.catalog import BY_ID  # anchor prices + volatility

# Timeframe → seconds-per-bar
TF_SECONDS: Dict[str, int] = {
    "M5":  5 * 60,
    "M15": 15 * 60,
    "M30": 30 * 60,
    "H1":  60 * 60,
    "H4":  4 * 60 * 60,
    "D1":  24 * 60 * 60,
}
DEFAULT_TF = "H1"


def _hash_float(*parts) -> float:
    """Deterministic pseudo-random in [-1, +1] from any inputs."""
    key = ":".join(map(str, parts)).encode()
    h = hashlib.sha256(key).digest()
    # first 8 bytes → 64-bit uint → map to [-1, +1]
    n = int.from_bytes(h[:8], "big")
    return (n / 2**63) - 1.0


def _hash_pos(*parts) -> float:
    """Deterministic pseudo-random in [0, 1]."""
    return (_hash_float(*parts) + 1.0) / 2.0


def _instrument_meta(symbol: str) -> Tuple[float, float, int]:
    inst = BY_ID.get(symbol.upper())
    if not inst:
        # Fallback: use symbol hash to synthesise a plausible instrument
        anchor = 100.0 * (1 + _hash_pos(symbol) * 3)
        return anchor, 0.003, 5
    return float(inst.get("seed", 100.0)), float(inst.get("vol", 0.003)), int(inst.get("price_dp", 5))


def current_bar_index(timeframe: str, ts: float | None = None) -> int:
    seconds = TF_SECONDS.get(timeframe, TF_SECONDS[DEFAULT_TF])
    now = ts if ts is not None else time.time()
    return int(now // seconds)


def get_candles(symbol: str, timeframe: str = DEFAULT_TF, count: int = 250,
                end_index: int | None = None,
                skip_live: bool = False) -> List[Dict[str, float]]:
    """Return the last `count` candles ending at `end_index` (inclusive).

    Each candle: {t (bar_idx), open, high, low, close, volume}

    Sprint 7.5: If a live cached price is available from the ProviderManager,
    the LAST bar's close is replaced with the live price so signals/indicators
    stay aligned with the actual market. Historical bars remain synthetic since
    free-tier providers can't backfill 250 bars for 20 symbols cheaply.
    """
    if end_index is None:
        end_index = current_bar_index(timeframe)
    anchor, vol, _ = _instrument_meta(symbol)
    tf_secs = TF_SECONDS.get(timeframe, TF_SECONDS[DEFAULT_TF])
    # Compress volatility for longer timeframes so ranges don't explode
    tf_vol_factor = math.sqrt(tf_secs / 3600.0)   # base = 1h
    step_vol = vol * tf_vol_factor
    # Seed random walk with a per-symbol drift
    drift = _hash_float("drift", symbol) * step_vol * 0.15  # tiny bias
    # Start from an anchor-derived price at the earliest bar
    start_idx = end_index - count + 1
    # Longer-term regime (macro trend that rotates every ~500 bars)
    regime = math.sin(start_idx / 500.0 + _hash_float("regime", symbol) * math.pi)
    price = anchor * (1 + regime * 0.05)
    candles: List[Dict[str, float]] = []
    for i in range(count):
        idx = start_idx + i
        # Deterministic shock in ~normal distribution (sum of two [-1,+1])
        shock = (_hash_float(symbol, timeframe, idx, "s1") + _hash_float(symbol, timeframe, idx, "s2")) * 0.5
        # Occasional larger shock every ~30 bars
        if idx % 29 == 0:
            shock += _hash_float(symbol, timeframe, idx, "s3") * 0.4
        # Slow-moving mean-reversion pull toward anchor * regime to prevent unbounded drift
        target = anchor * (1 + math.sin((idx / 500.0) + _hash_float("regime", symbol) * math.pi) * 0.05)
        pull = (target - price) / target * 0.05          # 5% pull per bar toward target
        change = drift + shock * step_vol + pull
        new_close = max(price * 0.5, price * (1 + change))
        # Intra-bar high/low
        wick_up   = _hash_pos(symbol, timeframe, idx, "wu") * step_vol
        wick_down = _hash_pos(symbol, timeframe, idx, "wd") * step_vol
        high = max(price, new_close) * (1 + wick_up * 0.4)
        low  = min(price, new_close) * (1 - wick_down * 0.4)
        volume = int(1_000 + _hash_pos(symbol, idx, "vol") * 9_000)
        candles.append({
            "t": idx * tf_secs,
            "open": round(price, 8),
            "high": round(high, 8),
            "low":  round(low, 8),
            "close": round(new_close, 8),
            "volume": volume,
        })
        price = new_close

    # ---- Sprint 7.5 live overlay ----
    # If the manager has a cached live price for this symbol, splice it into
    # the last bar's close (and adjust that bar's high/low envelope).
    if not skip_live:
        live_price = _live_price_lookup(symbol)
        if live_price and candles:
            last = candles[-1]
            # Anchor last close to live; adjust high/low to bracket it
            last["close"] = round(live_price, 8)
            last["high"] = round(max(last["high"], live_price * 1.0005), 8)
            last["low"] = round(min(last["low"], live_price * 0.9995), 8)
    return candles


def _live_price_lookup(symbol: str) -> float | None:
    """Look up cached live price via the ProviderManager (blocking-safe).

    Runs synchronously by scheduling an async cache read via asyncio. Returns
    None if manager isn't running yet, the symbol isn't cached, or on any error
    — the synthetic price is used in those cases.
    """
    try:
        import asyncio
        import market_providers
        mgr = market_providers.get_manager()
        if not mgr:
            return None
        # We're in sync code inside an async event loop. Grab the running loop
        # and schedule the coroutine synchronously via run_coroutine_threadsafe
        # if applicable, else skip live lookup.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # Can't safely block on the running loop from sync context.
            # Fall back to sync-cache read via a small trick: use asyncio.run
            # on a separate coroutine that pulls the cached doc directly with
            # motor sync helpers — but motor is async only. Solution: rely on
            # a per-process quick-cache dict that is populated by the refresh
            # worker via `_publish_price` (see below).
            return _MEMO.get(symbol.upper())
    except Exception:
        return None
    return None


# In-process memo populated by the Provider Manager's refresh worker via
# `publish_price` for zero-latency sync reads. Bounded to universe size.
_MEMO: Dict[str, float] = {}


def publish_price(symbol: str, price: float) -> None:
    """Called by the ProviderManager AFTER a successful cache write.

    Keeps a tiny in-process dict so downstream sync code (TA / signals /
    watchlist) can look up prices without an async round-trip.
    """
    _MEMO[symbol.upper()] = float(price)


def all_memoized_prices() -> Dict[str, float]:
    return dict(_MEMO)


def current_price(symbol: str, timeframe: str = "M5") -> float:
    """Get the latest close price. Sprint 7.5: prefer in-process live memo."""
    live = _MEMO.get(symbol.upper())
    if live and live > 0:
        return live
    c = get_candles(symbol, timeframe, count=1)
    return float(c[-1]["close"]) if c else 0.0
