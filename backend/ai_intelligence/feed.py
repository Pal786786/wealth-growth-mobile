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
                end_index: int | None = None) -> List[Dict[str, float]]:
    """Return the last `count` candles ending at `end_index` (inclusive).

    Each candle: {t (bar_idx), open, high, low, close, volume}
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
    return candles


def current_price(symbol: str, timeframe: str = "M5") -> float:
    """Get the latest close price using the smallest timeframe (5-min bar)."""
    c = get_candles(symbol, timeframe, count=1)
    return float(c[-1]["close"]) if c else 0.0
