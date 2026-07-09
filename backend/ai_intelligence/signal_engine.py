"""AI Intelligence — Signal Engine (Sprint 7C.1)

Consumes the TA engine output and produces a canonical AI trading signal with
all fields required by the spec:

  side (BUY/SELL), entry, stop_loss, tp1, tp2, tp3, risk_reward_ratio,
  confidence_pct, trend, signal_strength, timeframe, expiry_at,
  ai_explanation (deferred to ai_engine), technical_indicator_summary.

Signals are DETERMINISTIC for the current bar — same request within the same
bar returns the same signal. When a new bar opens, the signal refreshes.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from market_data.catalog import BY_ID
from . import feed
from . import ta_engine as ta

# How long an issued signal is considered valid, per timeframe
EXPIRY_BARS = {
    "M5": 6, "M15": 6, "M30": 6, "H1": 6, "H4": 4, "D1": 3,
}

# Default set of "top pick" symbols per asset class. All ~14 = fast to compute.
DEFAULT_UNIVERSE = [
    # Forex majors
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    # Metals
    "XAUUSD", "XAGUSD",
    # Indices
    "US30", "SPX500", "NAS100", "GER40",
    # Crypto
    "BTCUSD", "ETHUSD", "SOLUSD",
    # Energies / Commodities
    "USOIL",
]

# Public asset class map (used by /api/ai/signals?asset_class=...)
CATEGORY_TO_ASSET_CLASS = {
    "forex_majors": "forex", "forex_minors": "forex", "forex_exotics": "forex",
    "metals":       "metals", "energies":     "energies",
    "indices":      "indices", "crypto":      "crypto",
    "commodities":  "commodities",
}


def _score_from_indicators(ind: Dict[str, Any]) -> Dict[str, Any]:
    """Turn indicator readings into signed bull/bear score.

    Returns {score:int (−7..+7), confidence:0-100, strength:'weak|moderate|strong|very_strong', hits:list[str]}
    """
    hits: List[str] = []
    score = 0
    price = ind["price"]
    # 1. EMA structure
    if price > ind["ema20"] > ind["ema50"] > ind["ema200"]:
        score += 2
        hits.append("Perfect bullish EMA stack (20 > 50 > 200)")
    elif price < ind["ema20"] < ind["ema50"] < ind["ema200"]:
        score -= 2
        hits.append("Perfect bearish EMA stack (20 < 50 < 200)")
    else:
        if price > ind["ema20"]:
            score += 1
            hits.append("Price above EMA 20")
        else:
            score -= 1
            hits.append("Price below EMA 20")
        if ind["ema50"] > ind["ema200"]:
            score += 1
            hits.append("EMA 50 > EMA 200 (golden bias)")
        elif ind["ema50"] < ind["ema200"]:
            score -= 1
            hits.append("EMA 50 < EMA 200 (death bias)")

    # 2. RSI
    rsi = ind["rsi"]
    if rsi > 70:
        score -= 1
        hits.append(f"RSI overbought ({rsi:.1f})")
    elif rsi > 55:
        score += 1
        hits.append(f"RSI bullish ({rsi:.1f})")
    elif rsi < 30:
        score += 1
        hits.append(f"RSI oversold — mean-reversion buy ({rsi:.1f})")
    elif rsi < 45:
        score -= 1
        hits.append(f"RSI bearish ({rsi:.1f})")

    # 3. MACD histogram
    hist = ind["macd"]["hist"]
    if hist > 0:
        score += 1
        hits.append("MACD histogram positive")
    elif hist < 0:
        score -= 1
        hits.append("MACD histogram negative")

    # 4. ADX (trend strength)
    adx = ind["adx"]
    trend_dir = 1 if ind["trend"] == "bullish" else (-1 if ind["trend"] == "bearish" else 0)
    if adx > 25 and trend_dir != 0:
        score += trend_dir
        hits.append(f"ADX strong trend ({adx:.1f})")
    elif adx < 15:
        # weak trend — reduce absolute conviction
        score = int(score * 0.7)
        hits.append(f"ADX weak trend ({adx:.1f}) — conviction reduced")

    # 5. SuperTrend
    if ind["supertrend"]["direction"] == "up":
        score += 1
        hits.append("SuperTrend bullish")
    else:
        score -= 1
        hits.append("SuperTrend bearish")

    # 6. VWAP
    if price > ind["vwap"]:
        score += 1
        hits.append("Price above VWAP")
    else:
        score -= 1
        hits.append("Price below VWAP")

    # 7. Bollinger width (volatility gate)
    bb_w = ind["bollinger"]["width_pct"]
    if bb_w < 0.5:
        score = int(score * 0.6)
        hits.append(f"BB squeeze — very low vol ({bb_w:.2f}%) — reduced conviction")

    # Clamp
    score = max(-7, min(7, score))
    strength_map = {0: "weak", 1: "weak", 2: "moderate", 3: "moderate", 4: "strong",
                    5: "strong", 6: "very_strong", 7: "very_strong"}
    strength = strength_map[abs(score)]
    # Confidence: 50 + score * 6, clamped 30..92
    confidence = max(30, min(92, 50 + score * 6))
    return {"score": score, "confidence": confidence, "strength": strength, "hits": hits}


def _pip_size(symbol: str) -> float:
    inst = BY_ID.get(symbol.upper())
    if not inst:
        return 0.0001
    dp = int(inst.get("price_dp", 5))
    if dp >= 5:
        return 0.0001
    if dp == 4:
        return 0.0001
    if dp == 3:
        return 0.01
    if dp == 2:
        return 0.01
    return 0.1


def _round_price(symbol: str, x: float) -> float:
    inst = BY_ID.get(symbol.upper())
    dp = int(inst.get("price_dp", 5)) if inst else 5
    return round(x, dp)


def _compute_levels(side: str, price: float, atr: float,
                    payoff_ratios: List[float]) -> Dict[str, float]:
    """SL at 1.5x ATR, TP1/TP2/TP3 at 1x/2x/3x that risk."""
    risk = max(atr * 1.5, price * 0.0006)   # min 6 bps risk
    if side == "buy":
        sl = price - risk
        tps = [price + risk * r for r in payoff_ratios]
    else:
        sl = price + risk
        tps = [price - risk * r for r in payoff_ratios]
    return {"sl": sl, "tp1": tps[0], "tp2": tps[1], "tp3": tps[2], "risk": risk}


def generate_signal(symbol: str, timeframe: str = "H1",
                    include_summary: bool = True) -> Optional[Dict[str, Any]]:
    """Generate a signal for one symbol/timeframe. Returns None if invalid."""
    symbol = symbol.upper()
    inst = BY_ID.get(symbol)
    if not inst:
        return None
    candles = feed.get_candles(symbol, timeframe, count=250)
    if len(candles) < 60:
        return None
    ind = ta.compute(candles)
    if not ind:
        return None
    score = _score_from_indicators(ind)
    # Directional decision: use score sign (score 0 → HOLD/NEUTRAL)
    side = "buy" if score["score"] > 0 else ("sell" if score["score"] < 0 else "hold")
    price = ind["price"]
    atr = ind["atr"]
    if side == "hold":
        # Still return a hold recommendation but with neutral levels
        return _build_hold_signal(symbol, timeframe, ind, score, price, inst)
    levels = _compute_levels(side, price, atr, [1.0, 2.0, 3.0])
    tf_secs = feed.TF_SECONDS.get(timeframe, feed.TF_SECONDS[feed.DEFAULT_TF])
    expiry_bars = EXPIRY_BARS.get(timeframe, 6)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expiry_bars * tf_secs)
    signal = {
        "symbol": symbol,
        "display": inst.get("display", symbol),
        "asset_class": CATEGORY_TO_ASSET_CLASS.get(inst.get("category", ""), inst.get("category", "")),
        "category": inst.get("category"),
        "timeframe": timeframe,
        "side": side,
        "entry": _round_price(symbol, price),
        "stop_loss": _round_price(symbol, levels["sl"]),
        "tp1": _round_price(symbol, levels["tp1"]),
        "tp2": _round_price(symbol, levels["tp2"]),
        "tp3": _round_price(symbol, levels["tp3"]),
        "risk_reward_ratio": 3.0,
        "confidence_pct": score["confidence"],
        "trend": ind["trend"],
        "signal_strength": score["strength"],
        "expires_at": expires_at.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bar_index": feed.current_bar_index(timeframe),
        "risk_pips":  round(levels["risk"] / _pip_size(symbol), 1),
        "ai_explanation": None,   # filled by ai_engine on demand
        "reason_hits": score["hits"],
    }
    if include_summary:
        signal["indicators"] = ind
        signal["indicator_summary"] = ta.summarise(ind)
    return signal


def _build_hold_signal(symbol: str, timeframe: str, ind: Dict[str, Any],
                       score: Dict[str, Any], price: float, inst: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "display": inst.get("display", symbol),
        "asset_class": CATEGORY_TO_ASSET_CLASS.get(inst.get("category", ""), inst.get("category", "")),
        "category": inst.get("category"),
        "timeframe": timeframe,
        "side": "hold",
        "entry": _round_price(symbol, price),
        "stop_loss": None, "tp1": None, "tp2": None, "tp3": None,
        "risk_reward_ratio": 0.0,
        "confidence_pct": score["confidence"],
        "trend": ind["trend"],
        "signal_strength": score["strength"],
        "expires_at": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bar_index": feed.current_bar_index(timeframe),
        "ai_explanation": None,
        "reason_hits": score["hits"],
        "indicators": ind,
        "indicator_summary": ta.summarise(ind),
    }


def list_signals(timeframe: str = "H1", asset_class: Optional[str] = None,
                 min_confidence: int = 0, side: Optional[str] = None,
                 limit: int = 30) -> List[Dict[str, Any]]:
    """Return a paginated list of signals across the top universe.

    We don't include the full indicator dict here (kept for signal detail
    endpoint) to keep the response small.
    """
    universe = DEFAULT_UNIVERSE
    if asset_class:
        universe = [s for s in universe
                    if CATEGORY_TO_ASSET_CLASS.get(BY_ID.get(s, {}).get("category", ""), "") == asset_class
                    or asset_class == BY_ID.get(s, {}).get("category", "")]
    out: List[Dict[str, Any]] = []
    for sym in universe:
        s = generate_signal(sym, timeframe=timeframe, include_summary=False)
        if not s:
            continue
        if side and s["side"] != side:
            continue
        if s["confidence_pct"] < min_confidence:
            continue
        # Trim payload
        s.pop("reason_hits", None)
        s.pop("indicators", None)
        out.append(s)
    # Sort BUY/SELL first by confidence desc, HOLD last
    def _rank(sig):
        priority = 0 if sig["side"] in ("buy", "sell") else 1
        return (priority, -sig["confidence_pct"])
    out.sort(key=_rank)
    return out[:limit]


def signal_for(symbol: str, timeframe: str = "H1") -> Optional[Dict[str, Any]]:
    return generate_signal(symbol, timeframe=timeframe, include_summary=True)
