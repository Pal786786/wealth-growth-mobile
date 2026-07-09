"""AI Intelligence — Technical Analysis Engine (Sprint 7C.1)

Computes 10 indicators on a candle series:
  EMA 20 / EMA 50 / EMA 200, RSI, MACD, ATR, Bollinger Bands, ADX, SuperTrend, VWAP

Every function is pure (candle list → number/tuple). No external dependencies.
The output is small numeric dicts consumable by the Signal Engine, the AI
narrative generator (Claude), and the Frontend.
"""
from __future__ import annotations
import math
from typing import Any, Dict, List


def _ema(values: List[float], period: int) -> List[float]:
    if not values or period <= 0 or len(values) < period:
        return []
    k = 2 / (period + 1)
    ema: List[float] = []
    # Seed: simple average of first `period` values
    seed = sum(values[:period]) / period
    ema.append(seed)
    for v in values[period:]:
        ema.append(v * k + ema[-1] * (1 - k))
    # Left-pad with None so index aligns with `values`. But callers use last-value semantics.
    return ema


def _sma(values: List[float], period: int) -> List[float]:
    if len(values) < period:
        return []
    out = []
    running = sum(values[:period])
    out.append(running / period)
    for i in range(period, len(values)):
        running += values[i] - values[i - period]
        out.append(running / period)
    return out


def _rsi(values: List[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50.0
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains += max(0.0, change)
        losses += max(0.0, -change)
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        gain = max(0.0, change)
        loss = max(0.0, -change)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _macd(values: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, float]:
    if len(values) < slow + signal:
        return {"macd": 0.0, "signal": 0.0, "hist": 0.0}
    ema_fast = _ema(values, fast)
    ema_slow = _ema(values, slow)
    # Align lengths
    n = min(len(ema_fast), len(ema_slow))
    macd_line = [ema_fast[-n + i] - ema_slow[-n + i] for i in range(n)]
    signal_line = _ema(macd_line, signal)
    if not signal_line:
        return {"macd": macd_line[-1], "signal": 0.0, "hist": macd_line[-1]}
    return {
        "macd":   macd_line[-1],
        "signal": signal_line[-1],
        "hist":   macd_line[-1] - signal_line[-1],
    }


def _atr(candles: List[Dict[str, float]], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    trs: List[float] = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        low = candles[i]["low"]
        pc = candles[i - 1]["close"]
        tr = max(h - low, abs(h - pc), abs(low - pc))
        trs.append(tr)
    # Wilder's smoothing
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def _bollinger(values: List[float], period: int = 20, mult: float = 2.0) -> Dict[str, float]:
    if len(values) < period:
        return {"upper": 0.0, "middle": 0.0, "lower": 0.0, "width_pct": 0.0}
    window = values[-period:]
    mid = sum(window) / period
    var = sum((v - mid) ** 2 for v in window) / period
    sd = math.sqrt(var)
    upper = mid + sd * mult
    lower = mid - sd * mult
    width_pct = (upper - lower) / mid * 100.0 if mid else 0.0
    return {"upper": upper, "middle": mid, "lower": lower, "width_pct": width_pct}


def _adx(candles: List[Dict[str, float]], period: int = 14) -> float:
    """Standard Wilder ADX. Returns the last value (0-100)."""
    if len(candles) < period * 2 + 1:
        return 0.0
    plus_dm: List[float] = []
    minus_dm: List[float] = []
    trs: List[float] = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        low = candles[i]["low"]
        ph = candles[i - 1]["high"]
        pl = candles[i - 1]["low"]
        pc = candles[i - 1]["close"]
        up_move = h - ph
        down_move = pl - low
        plus_dm.append(up_move if (up_move > down_move and up_move > 0) else 0.0)
        minus_dm.append(down_move if (down_move > up_move and down_move > 0) else 0.0)
        trs.append(max(h - low, abs(h - pc), abs(low - pc)))
    # Smooth
    def _smooth(vals, per):
        s = sum(vals[:per])
        out = [s]
        for v in vals[per:]:
            s = s - s / per + v
            out.append(s)
        return out
    tr_s = _smooth(trs, period)
    pdm_s = _smooth(plus_dm, period)
    mdm_s = _smooth(minus_dm, period)
    dx_series: List[float] = []
    for i in range(len(tr_s)):
        if tr_s[i] == 0:
            dx_series.append(0.0)
            continue
        pdi = 100 * pdm_s[i] / tr_s[i]
        mdi = 100 * mdm_s[i] / tr_s[i]
        denom = pdi + mdi
        dx = 100 * abs(pdi - mdi) / denom if denom else 0.0
        dx_series.append(dx)
    if len(dx_series) < period:
        return 0.0
    adx = sum(dx_series[:period]) / period
    for v in dx_series[period:]:
        adx = (adx * (period - 1) + v) / period
    return adx


def _supertrend(candles: List[Dict[str, float]], period: int = 10, mult: float = 3.0) -> Dict[str, Any]:
    """Returns {value, direction: 'up'|'down'} — last-bar SuperTrend."""
    if len(candles) < period + 1:
        return {"value": 0.0, "direction": "up"}
    # Compute ATR on the fly using the same length as the candles list, then
    # produce a walking supertrend.
    atr_arr: List[float] = [0.0] * period
    trs: List[float] = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        low = candles[i]["low"]
        pc = candles[i - 1]["close"]
        trs.append(max(h - low, abs(h - pc), abs(low - pc)))
    atr = sum(trs[:period]) / period
    atr_arr.append(atr)
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
        atr_arr.append(atr)
    # Build supertrend walking forward
    st = 0.0
    direction = "up"
    for i in range(period, len(candles)):
        hl2 = (candles[i]["high"] + candles[i]["low"]) / 2
        upper = hl2 + mult * atr_arr[i]
        lower = hl2 - mult * atr_arr[i]
        close = candles[i]["close"]
        prev_close = candles[i - 1]["close"]
        if close > st and prev_close <= st:
            direction = "up"
            st = lower
        elif close < st and prev_close >= st:
            direction = "down"
            st = upper
        elif direction == "up":
            st = max(lower, st) if st else lower
        else:
            st = min(upper, st) if st else upper
    return {"value": st, "direction": direction}


def _vwap(candles: List[Dict[str, float]]) -> float:
    if not candles:
        return 0.0
    num = 0.0
    den = 0.0
    for c in candles:
        typ = (c["high"] + c["low"] + c["close"]) / 3
        num += typ * c["volume"]
        den += c["volume"]
    return num / den if den else candles[-1]["close"]


def _volatility(values: List[float], period: int = 20) -> float:
    """Std-dev of pct returns over the last `period` bars → %."""
    if len(values) < period + 1:
        return 0.0
    rets = []
    for i in range(len(values) - period, len(values)):
        prev = values[i - 1]
        if prev:
            rets.append((values[i] - prev) / prev)
    if not rets:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return math.sqrt(var) * 100.0


def compute(candles: List[Dict[str, float]]) -> Dict[str, Any]:
    """Compute the full indicator pack.
    Returns numbers rounded to 6 decimals + convenience labels.
    """
    closes = [c["close"] for c in candles]
    if not closes:
        return {}
    price = closes[-1]

    ema20  = _ema(closes, 20)
    ema50  = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    ema20_v  = ema20[-1]  if ema20  else price
    ema50_v  = ema50[-1]  if ema50  else price
    ema200_v = ema200[-1] if ema200 else price

    rsi = _rsi(closes, 14)
    macd = _macd(closes)
    atr = _atr(candles, 14)
    bb = _bollinger(closes, 20, 2.0)
    adx = _adx(candles, 14)
    st = _supertrend(candles, 10, 3.0)
    vwap = _vwap(candles[-60:])   # rolling VWAP over ~60 bars
    vol_pct = _volatility(closes, 20)

    def rd(x, n=6):
        try:
            return round(float(x), n)
        except (TypeError, ValueError):
            return 0.0

    # Trend: majority vote of EMA structure
    up_votes = 0
    if price > ema20_v:
        up_votes += 1
    if ema20_v > ema50_v:
        up_votes += 1
    if ema50_v > ema200_v:
        up_votes += 1
    if st["direction"] == "up":
        up_votes += 1
    trend = "bullish" if up_votes >= 3 else ("bearish" if up_votes <= 1 else "neutral")

    return {
        "price": rd(price),
        "ema20": rd(ema20_v), "ema50": rd(ema50_v), "ema200": rd(ema200_v),
        "rsi": rd(rsi, 2),
        "macd": {"macd": rd(macd["macd"]), "signal": rd(macd["signal"]), "hist": rd(macd["hist"])},
        "atr": rd(atr),
        "bollinger": {"upper": rd(bb["upper"]), "middle": rd(bb["middle"]),
                      "lower": rd(bb["lower"]), "width_pct": rd(bb["width_pct"], 3)},
        "adx": rd(adx, 2),
        "supertrend": {"value": rd(st["value"]), "direction": st["direction"]},
        "vwap": rd(vwap),
        "volatility_pct": rd(vol_pct, 3),
        "trend": trend,
    }


def summarise(ind: Dict[str, Any]) -> List[Dict[str, str]]:
    """Return human-readable indicator summary rows for the UI."""
    if not ind:
        return []
    price = ind["price"]
    rows = [
        _row("EMA 20",  f"{ind['ema20']}",  _cmp_line(price, ind["ema20"])),
        _row("EMA 50",  f"{ind['ema50']}",  _cmp_line(price, ind["ema50"])),
        _row("EMA 200", f"{ind['ema200']}", _cmp_line(price, ind["ema200"])),
        _row("RSI (14)", f"{ind['rsi']}", "overbought" if ind["rsi"] > 70 else ("oversold" if ind["rsi"] < 30 else "neutral")),
        _row("MACD",     f"{ind['macd']['macd']:+.4f}", "bullish" if ind['macd']['hist'] > 0 else "bearish"),
        _row("ATR (14)", f"{ind['atr']:.4f}", "volatile" if ind['atr'] > 0 else "quiet"),
        _row("Bollinger %B", f"{_bb_percent_b(price, ind['bollinger']):.2f}",
             "upper band" if _bb_percent_b(price, ind['bollinger']) > 0.9 else ("lower band" if _bb_percent_b(price, ind['bollinger']) < 0.1 else "mid-band")),
        _row("ADX (14)", f"{ind['adx']}", "strong trend" if ind["adx"] > 25 else "weak trend"),
        _row("SuperTrend", f"{ind['supertrend']['value']}", ind['supertrend']['direction']),
        _row("VWAP",     f"{ind['vwap']}", _cmp_line(price, ind["vwap"])),
    ]
    return rows


def _row(name: str, value: str, verdict: str) -> Dict[str, str]:
    return {"name": name, "value": value, "verdict": verdict}


def _cmp_line(price: float, ref: float) -> str:
    if not ref:
        return "neutral"
    diff_pct = (price - ref) / ref * 100
    if diff_pct > 0.1:
        return "above (bullish)"
    if diff_pct < -0.1:
        return "below (bearish)"
    return "neutral"


def _bb_percent_b(price: float, bb: Dict[str, float]) -> float:
    if bb["upper"] == bb["lower"]:
        return 0.5
    return (price - bb["lower"]) / (bb["upper"] - bb["lower"])
