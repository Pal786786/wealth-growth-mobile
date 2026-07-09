"""Sprint 7B.1 — Copy Trading trader engine.

DETERMINISTIC seeded personas + statistics generator.

Design constraint from the user: the SAME trader must return the SAME numbers
(ROI, win rate, drawdown, equity curve, trade history) across app restarts.

We achieve this by:
  1. Each persona has a fixed integer `seed`. That seed drives a private
     `random.Random(seed)` for that trader.
  2. The generator function is pure — given (seed, params) it always returns
     the same series. No `time.time()` or wall-clock drift inside the RNG path.
  3. Equity curve is computed by simulating N closed trades using per-persona
     characteristics (win rate, avg win, avg loss, holding time). The result
     is cached in-process; nothing is persisted per-user (only per-persona).

Persona templates encode WHO the trader is (name, country, style, bio, xp).
Metrics like win-rate and Sharpe are DERIVED from a small set of "true
parameters" so they're internally consistent (a 78% win-rate trader with a
1.5 payoff ratio inherently has a good profit factor).
"""
from __future__ import annotations
import hashlib
import math
import random
import time
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Persona templates — 28 traders
# ---------------------------------------------------------------------------
# Fields:
#   id, name, country_code, country_name, style, experience_years, bio,
#   avatar_seed (drives dicebear url), verified (bool),
#   truth: {
#     win_rate:    fraction 0..1
#     payoff_ratio: avg_win / |avg_loss|
#     trades_per_month: int
#     avg_holding_hours: float
#     annual_vol_pct: annualised volatility of monthly returns
#     annual_target_roi_pct: rough annualised drift on equity
#     drawdown_cap_pct: rough max drawdown to enforce
#     avg_lot: float
#   }
_STYLES = ["Scalping", "Day Trading", "Swing", "Position", "Trend Following",
           "Mean Reversion", "News Trader", "Breakout", "Grid", "Arbitrage"]

_PERSONAS: List[Dict[str, Any]] = [
    # -- Elite tier (verified, high ROI, low drawdown) ------------------------
    {"id":"marcus_wolfe","name":"Marcus Wolfe","country_code":"US","country_name":"United States","style":"Swing","experience_years":11,"bio":"Ex-hedge fund PM. Rules-based swing trading on majors + gold.","seed":101,"verified":True,
     "truth":{"win_rate":0.66,"payoff_ratio":1.85,"trades_per_month":22,"avg_holding_hours":38,"annual_vol_pct":0.14,"annual_target_roi_pct":0.72,"drawdown_cap_pct":0.09,"avg_lot":1.4}},
    {"id":"elena_petrov","name":"Elena Petrov","country_code":"GB","country_name":"United Kingdom","style":"Trend Following","experience_years":9,"bio":"Systematic trend follower. Multi-asset diversified book.","seed":102,"verified":True,
     "truth":{"win_rate":0.52,"payoff_ratio":2.6,"trades_per_month":14,"avg_holding_hours":168,"annual_vol_pct":0.17,"annual_target_roi_pct":0.58,"drawdown_cap_pct":0.11,"avg_lot":1.1}},
    {"id":"aarav_menon","name":"Aarav Menon","country_code":"IN","country_name":"India","style":"Breakout","experience_years":7,"bio":"NSE options background. Now trades global forex breakouts.","seed":103,"verified":True,
     "truth":{"win_rate":0.58,"payoff_ratio":1.95,"trades_per_month":38,"avg_holding_hours":18,"annual_vol_pct":0.19,"annual_target_roi_pct":0.85,"drawdown_cap_pct":0.13,"avg_lot":0.9}},
    {"id":"lin_wei","name":"Lin Wei","country_code":"SG","country_name":"Singapore","style":"Position","experience_years":13,"bio":"CFA. Macro-driven position trader. FX + metals + indices.","seed":104,"verified":True,
     "truth":{"win_rate":0.63,"payoff_ratio":1.65,"trades_per_month":9,"avg_holding_hours":312,"annual_vol_pct":0.12,"annual_target_roi_pct":0.46,"drawdown_cap_pct":0.08,"avg_lot":2.2}},
    {"id":"hana_tanaka","name":"Hana Tanaka","country_code":"JP","country_name":"Japan","style":"Scalping","experience_years":6,"bio":"Tokyo session scalper. USDJPY, EURJPY, GBPJPY specialist.","seed":105,"verified":True,
     "truth":{"win_rate":0.71,"payoff_ratio":1.35,"trades_per_month":180,"avg_holding_hours":0.6,"annual_vol_pct":0.15,"annual_target_roi_pct":0.62,"drawdown_cap_pct":0.10,"avg_lot":0.6}},
    {"id":"dieter_klein","name":"Dieter Klein","country_code":"DE","country_name":"Germany","style":"Mean Reversion","experience_years":10,"bio":"Statistical arbitrage on European indices + DAX.","seed":106,"verified":True,
     "truth":{"win_rate":0.68,"payoff_ratio":1.4,"trades_per_month":48,"avg_holding_hours":8,"annual_vol_pct":0.11,"annual_target_roi_pct":0.42,"drawdown_cap_pct":0.07,"avg_lot":1.0}},

    # -- Strong tier (mixed verified) -----------------------------------------
    {"id":"sofia_bianchi","name":"Sofia Bianchi","country_code":"IT","country_name":"Italy","style":"Day Trading","experience_years":5,"bio":"London-Milan overlap sessions. High-conviction day trades.","seed":107,"verified":True,
     "truth":{"win_rate":0.55,"payoff_ratio":1.75,"trades_per_month":72,"avg_holding_hours":4.2,"annual_vol_pct":0.22,"annual_target_roi_pct":0.68,"drawdown_cap_pct":0.15,"avg_lot":0.7}},
    {"id":"omar_hassan","name":"Omar Hassan","country_code":"AE","country_name":"United Arab Emirates","style":"News Trader","experience_years":8,"bio":"Fundamentals + NFP + CB decisions. Fast in, fast out.","seed":108,"verified":True,
     "truth":{"win_rate":0.49,"payoff_ratio":2.8,"trades_per_month":16,"avg_holding_hours":3,"annual_vol_pct":0.24,"annual_target_roi_pct":0.72,"drawdown_cap_pct":0.16,"avg_lot":1.3}},
    {"id":"lucas_moreno","name":"Lucas Moreno","country_code":"ES","country_name":"Spain","style":"Swing","experience_years":6,"bio":"IBEX + majors swing. Weekly bias, daily entries.","seed":109,"verified":False,
     "truth":{"win_rate":0.61,"payoff_ratio":1.55,"trades_per_month":18,"avg_holding_hours":52,"annual_vol_pct":0.16,"annual_target_roi_pct":0.44,"drawdown_cap_pct":0.10,"avg_lot":0.8}},
    {"id":"chloe_dubois","name":"Chloé Dubois","country_code":"FR","country_name":"France","style":"Trend Following","experience_years":7,"bio":"CTA-style trend follower. Long CAC40, gold, oil.","seed":110,"verified":True,
     "truth":{"win_rate":0.46,"payoff_ratio":3.1,"trades_per_month":12,"avg_holding_hours":220,"annual_vol_pct":0.19,"annual_target_roi_pct":0.55,"drawdown_cap_pct":0.14,"avg_lot":1.2}},
    {"id":"jack_oconnor","name":"Jack O'Connor","country_code":"IE","country_name":"Ireland","style":"Position","experience_years":12,"bio":"Old-school macro. Slow, patient, high conviction.","seed":111,"verified":True,
     "truth":{"win_rate":0.64,"payoff_ratio":1.7,"trades_per_month":6,"avg_holding_hours":720,"annual_vol_pct":0.10,"annual_target_roi_pct":0.38,"drawdown_cap_pct":0.06,"avg_lot":2.8}},
    {"id":"nikita_volkov","name":"Nikita Volkov","country_code":"RU","country_name":"Russia","style":"Grid","experience_years":4,"bio":"Algorithmic grid + martingale variants. USDCHF specialist.","seed":112,"verified":False,
     "truth":{"win_rate":0.78,"payoff_ratio":0.85,"trades_per_month":150,"avg_holding_hours":6,"annual_vol_pct":0.28,"annual_target_roi_pct":0.65,"drawdown_cap_pct":0.22,"avg_lot":0.4}},

    # -- Rising tier (mostly non-verified, mixed risk) ------------------------
    {"id":"maya_patel","name":"Maya Patel","country_code":"IN","country_name":"India","style":"Day Trading","experience_years":3,"bio":"CFA level II. Discretionary intraday on USD pairs.","seed":113,"verified":False,
     "truth":{"win_rate":0.53,"payoff_ratio":1.6,"trades_per_month":55,"avg_holding_hours":5,"annual_vol_pct":0.23,"annual_target_roi_pct":0.48,"drawdown_cap_pct":0.16,"avg_lot":0.5}},
    {"id":"tom_richards","name":"Tom Richards","country_code":"AU","country_name":"Australia","style":"Swing","experience_years":5,"bio":"AUD-crosses specialist. Weekly newsletter with 1200 subs.","seed":114,"verified":True,
     "truth":{"win_rate":0.6,"payoff_ratio":1.45,"trades_per_month":16,"avg_holding_hours":90,"annual_vol_pct":0.18,"annual_target_roi_pct":0.42,"drawdown_cap_pct":0.12,"avg_lot":0.9}},
    {"id":"raul_gomez","name":"Raúl Gómez","country_code":"MX","country_name":"Mexico","style":"Scalping","experience_years":4,"bio":"USDMXN + EURUSD scalper. Manual only.","seed":115,"verified":False,
     "truth":{"win_rate":0.72,"payoff_ratio":1.1,"trades_per_month":220,"avg_holding_hours":0.3,"annual_vol_pct":0.20,"annual_target_roi_pct":0.55,"drawdown_cap_pct":0.14,"avg_lot":0.3}},
    {"id":"kwame_asante","name":"Kwame Asante","country_code":"GH","country_name":"Ghana","style":"Breakout","experience_years":3,"bio":"London breakout specialist. GBP + gold focus.","seed":116,"verified":False,
     "truth":{"win_rate":0.44,"payoff_ratio":2.9,"trades_per_month":32,"avg_holding_hours":24,"annual_vol_pct":0.25,"annual_target_roi_pct":0.52,"drawdown_cap_pct":0.18,"avg_lot":0.6}},
    {"id":"anita_johansson","name":"Anita Johansson","country_code":"SE","country_name":"Sweden","style":"Mean Reversion","experience_years":6,"bio":"Volatility-based mean reversion. EU session.","seed":117,"verified":True,
     "truth":{"win_rate":0.7,"payoff_ratio":1.2,"trades_per_month":58,"avg_holding_hours":10,"annual_vol_pct":0.13,"annual_target_roi_pct":0.36,"drawdown_cap_pct":0.09,"avg_lot":0.8}},
    {"id":"pieter_van_dijk","name":"Pieter van Dijk","country_code":"NL","country_name":"Netherlands","style":"Trend Following","experience_years":8,"bio":"Discretionary trend. Multi-week holding periods.","seed":118,"verified":True,
     "truth":{"win_rate":0.48,"payoff_ratio":2.5,"trades_per_month":10,"avg_holding_hours":180,"annual_vol_pct":0.17,"annual_target_roi_pct":0.47,"drawdown_cap_pct":0.13,"avg_lot":1.0}},

    # -- Emerging / edge cases (some higher risk) -----------------------------
    {"id":"jose_silva","name":"José Silva","country_code":"BR","country_name":"Brazil","style":"Day Trading","experience_years":2,"bio":"Aggressive day trader. Crypto + US indices.","seed":119,"verified":False,
     "truth":{"win_rate":0.51,"payoff_ratio":1.4,"trades_per_month":88,"avg_holding_hours":4,"annual_vol_pct":0.32,"annual_target_roi_pct":0.68,"drawdown_cap_pct":0.24,"avg_lot":0.4}},
    {"id":"ahmed_farah","name":"Ahmed Farah","country_code":"EG","country_name":"Egypt","style":"News Trader","experience_years":5,"bio":"CB decision specialist. Fed / ECB / BoE events.","seed":120,"verified":False,
     "truth":{"win_rate":0.42,"payoff_ratio":3.4,"trades_per_month":8,"avg_holding_hours":1.5,"annual_vol_pct":0.28,"annual_target_roi_pct":0.60,"drawdown_cap_pct":0.20,"avg_lot":1.5}},
    {"id":"grace_kim","name":"Grace Kim","country_code":"KR","country_name":"South Korea","style":"Breakout","experience_years":4,"bio":"Asian session breakouts. Nikkei + KOSPI + AUD/JPY.","seed":121,"verified":True,
     "truth":{"win_rate":0.57,"payoff_ratio":1.8,"trades_per_month":42,"avg_holding_hours":16,"annual_vol_pct":0.18,"annual_target_roi_pct":0.50,"drawdown_cap_pct":0.12,"avg_lot":0.7}},
    {"id":"faisal_khan","name":"Faisal Khan","country_code":"PK","country_name":"Pakistan","style":"Scalping","experience_years":3,"bio":"Ultra short-term. EUR/USD + GBP/USD only.","seed":122,"verified":False,
     "truth":{"win_rate":0.74,"payoff_ratio":1.0,"trades_per_month":260,"avg_holding_hours":0.25,"annual_vol_pct":0.16,"annual_target_roi_pct":0.32,"drawdown_cap_pct":0.10,"avg_lot":0.3}},
    {"id":"isabella_costa","name":"Isabella Costa","country_code":"PT","country_name":"Portugal","style":"Position","experience_years":9,"bio":"Value-driven long-term positions. Metals + oil.","seed":123,"verified":True,
     "truth":{"win_rate":0.62,"payoff_ratio":2.0,"trades_per_month":5,"avg_holding_hours":600,"annual_vol_pct":0.12,"annual_target_roi_pct":0.38,"drawdown_cap_pct":0.08,"avg_lot":2.0}},

    # -- Younger / lower AUM ---------------------------------------------------
    {"id":"leo_martins","name":"Leo Martins","country_code":"CA","country_name":"Canada","style":"Swing","experience_years":2,"bio":"Emerging swing trader. Focus on CAD + oil correlations.","seed":124,"verified":False,
     "truth":{"win_rate":0.54,"payoff_ratio":1.5,"trades_per_month":20,"avg_holding_hours":48,"annual_vol_pct":0.20,"annual_target_roi_pct":0.38,"drawdown_cap_pct":0.14,"avg_lot":0.5}},
    {"id":"amelie_martin","name":"Amélie Martin","country_code":"CH","country_name":"Switzerland","style":"Trend Following","experience_years":3,"bio":"Systematic trend follower. Diversified basket.","seed":125,"verified":False,
     "truth":{"win_rate":0.47,"payoff_ratio":2.4,"trades_per_month":15,"avg_holding_hours":200,"annual_vol_pct":0.19,"annual_target_roi_pct":0.42,"drawdown_cap_pct":0.14,"avg_lot":0.9}},
    {"id":"raj_kapoor","name":"Raj Kapoor","country_code":"IN","country_name":"India","style":"Day Trading","experience_years":4,"bio":"Indian trader now on global forex. Consistent monthly gains.","seed":126,"verified":True,
     "truth":{"win_rate":0.59,"payoff_ratio":1.65,"trades_per_month":50,"avg_holding_hours":6,"annual_vol_pct":0.17,"annual_target_roi_pct":0.46,"drawdown_cap_pct":0.11,"avg_lot":0.7}},
    {"id":"nora_hansen","name":"Nora Hansen","country_code":"NO","country_name":"Norway","style":"Mean Reversion","experience_years":5,"bio":"Overlay strategy on majors. Small size, high frequency.","seed":127,"verified":False,
     "truth":{"win_rate":0.75,"payoff_ratio":0.95,"trades_per_month":110,"avg_holding_hours":3,"annual_vol_pct":0.13,"annual_target_roi_pct":0.30,"drawdown_cap_pct":0.09,"avg_lot":0.4}},
    {"id":"david_park","name":"David Park","country_code":"US","country_name":"United States","style":"Breakout","experience_years":6,"bio":"NYC-based breakout trader. High conviction, low frequency.","seed":128,"verified":True,
     "truth":{"win_rate":0.45,"payoff_ratio":3.2,"trades_per_month":10,"avg_holding_hours":50,"annual_vol_pct":0.22,"annual_target_roi_pct":0.58,"drawdown_cap_pct":0.15,"avg_lot":1.1}},
]


def _rng(trader_id: str) -> random.Random:
    """Return a deterministic RNG for a trader — reproducible across restarts."""
    persona = _persona_by_id(trader_id)
    seed = persona["seed"] if persona else int(hashlib.sha256(trader_id.encode()).hexdigest(), 16) % (2**32)
    return random.Random(seed)


def _persona_by_id(trader_id: str) -> Optional[Dict[str, Any]]:
    for p in _PERSONAS:
        if p["id"] == trader_id:
            return p
    return None


# ---------------------------------------------------------------------------
# Statistics generator (deterministic given persona.seed)
# ---------------------------------------------------------------------------
def _generate_monthly_returns(persona: Dict[str, Any], months: int = 12) -> List[float]:
    """Return `months` monthly returns (as fractions, e.g. 0.048 = +4.8%)."""
    rng = random.Random(persona["seed"] * 7 + 1)
    truth = persona["truth"]
    monthly_target = truth["annual_target_roi_pct"] / 12.0
    monthly_vol = truth["annual_vol_pct"] / math.sqrt(12)
    out: List[float] = []
    for _ in range(months):
        r = rng.gauss(monthly_target, monthly_vol)
        # Cap drawdown months a bit (winners feel bigger)
        if r < -truth["drawdown_cap_pct"] * 0.55:
            r = -truth["drawdown_cap_pct"] * 0.55 * (0.5 + rng.random() * 0.5)
        out.append(r)
    return out


def _generate_equity_curve(persona: Dict[str, Any], months: int = 12, start_balance: float = 100000.0) -> List[Dict[str, float]]:
    """Daily equity+balance curve for the last `months` months."""
    truth = persona["truth"]
    rng = random.Random(persona["seed"] * 13 + 5)
    days = months * 30
    daily_target = truth["annual_target_roi_pct"] / 365
    daily_vol = truth["annual_vol_pct"] / math.sqrt(365)
    balance = start_balance
    equity = start_balance
    curve: List[Dict[str, float]] = []
    peak = start_balance
    trough_gap = 0.0
    for i in range(days):
        # Balance closes daily
        r = rng.gauss(daily_target, daily_vol)
        balance *= (1 + r)
        # Equity oscillates around balance (open floating P&L)
        float_swing = rng.gauss(0, daily_vol * 0.6) * balance
        equity = balance + float_swing
        peak = max(peak, balance)
        trough_gap = max(trough_gap, (peak - min(balance, equity)) / peak)
        # Enforce configured drawdown cap softly
        if trough_gap > truth["drawdown_cap_pct"] * 1.1:
            # rebound
            balance *= 1 + abs(rng.gauss(daily_target * 3, daily_vol * 0.3))
        curve.append({"day": i, "balance": round(balance, 2), "equity": round(equity, 2)})
    return curve


def _stats_from_truth(persona: Dict[str, Any], curve: List[Dict[str, float]], monthly: List[float]) -> Dict[str, Any]:
    truth = persona["truth"]
    rng = random.Random(persona["seed"] * 17 + 11)
    start_bal = curve[0]["balance"] if curve else 100000.0
    end_bal   = curve[-1]["balance"] if curve else start_bal
    total_roi = (end_bal - start_bal) / start_bal
    monthly_roi = monthly[-1] if monthly else 0.0
    weekly_roi = monthly_roi / 4.3   # rough approximation
    # Max drawdown from curve
    peak = start_bal
    max_dd = 0.0
    for pt in curve:
        peak = max(peak, pt["balance"])
        max_dd = max(max_dd, (peak - pt["balance"]) / peak)
    # Sharpe = mean/std of monthly returns * sqrt(12)
    if monthly:
        mean_m = sum(monthly) / len(monthly)
        var_m = sum((r - mean_m) ** 2 for r in monthly) / max(1, len(monthly) - 1)
        std_m = math.sqrt(var_m)
        sharpe = (mean_m / std_m * math.sqrt(12)) if std_m > 1e-9 else 0.0
    else:
        sharpe = 0.0
    # Profit factor from truth + noise
    profit_factor = (truth["win_rate"] * truth["payoff_ratio"]) / max(1e-9, (1 - truth["win_rate"]))
    # Recovery factor = total ROI / max drawdown
    recovery = (total_roi / max_dd) if max_dd > 1e-6 else total_roi * 10
    # Followers derived from stats + seed
    quality_score = (total_roi * 100) * 0.6 + (1 - max_dd) * 40 + (1 if persona["verified"] else 0) * 15
    followers = int(400 + max(0, quality_score) * (rng.uniform(120, 220)))
    aum = int(50_000 + followers * rng.uniform(180, 720))
    n_trades = int(truth["trades_per_month"] * 12 * rng.uniform(0.95, 1.05))
    win_trades = int(n_trades * truth["win_rate"])
    lose_trades = n_trades - win_trades
    return {
        "total_roi_pct": round(total_roi * 100, 2),
        "monthly_roi_pct": round(monthly_roi * 100, 2),
        "weekly_roi_pct": round(weekly_roi * 100, 2),
        "annual_roi_pct": round(total_roi * 100, 2),
        "win_rate_pct": round(truth["win_rate"] * 100, 1),
        "profit_factor": round(profit_factor, 2),
        "sharpe_ratio": round(sharpe, 2),
        "recovery_factor": round(recovery, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "avg_holding_hours": round(truth["avg_holding_hours"], 1),
        "avg_lot_size": round(truth["avg_lot"], 2),
        "avg_win_usd": round(start_bal * 0.006 * truth["payoff_ratio"] * rng.uniform(0.9, 1.1), 2),
        "avg_loss_usd": round(-start_bal * 0.006 * rng.uniform(0.9, 1.1), 2),
        "expectancy_usd": round(start_bal * 0.006 * (truth["win_rate"] * truth["payoff_ratio"] - (1 - truth["win_rate"])), 2),
        "followers": followers,
        "aum_usd": aum,
        "total_trades": n_trades,
        "winning_trades": win_trades,
        "losing_trades": lose_trades,
    }


def _risk_score(persona: Dict[str, Any], stats: Dict[str, Any]) -> Dict[str, Any]:
    """Risk score 1-10 derived from drawdown, win rate, volatility, position size, holding time.

    Higher score = riskier. Tier bucketed at 4 and 7.
    Deterministic per persona (no RNG).
    """
    truth = persona["truth"]
    # Component scores 0..1 (higher = riskier)
    dd_score  = min(1.0, truth["drawdown_cap_pct"] / 0.30)        # cap 30% → 1.0
    wr_score  = 1.0 - truth["win_rate"]                             # low win rate = riskier
    vol_score = min(1.0, truth["annual_vol_pct"] / 0.35)          # 35% vol → 1.0
    lot_score = min(1.0, truth["avg_lot"] / 3.0)                    # 3 lots → 1.0
    hold_score = 1.0 - min(1.0, truth["avg_holding_hours"] / 72)  # ultra-short = riskier
    # Weighted sum
    raw = (dd_score * 0.35 + wr_score * 0.20 + vol_score * 0.20 +
           lot_score * 0.10 + hold_score * 0.15)
    score = 1 + round(raw * 9)  # 1..10
    score = max(1, min(10, int(score)))
    tier = "Conservative" if score <= 4 else "Moderate" if score <= 7 else "Aggressive"
    return {"risk_score": score, "risk_tier": tier,
            "components": {"drawdown": round(dd_score, 2), "win_rate": round(wr_score, 2),
                           "volatility": round(vol_score, 2), "position_size": round(lot_score, 2),
                           "holding_time": round(hold_score, 2)}}


# In-memory cache — deterministic content
_CACHE: Dict[str, Dict[str, Any]] = {}


def get_trader(trader_id: str, include_curve: bool = False) -> Optional[Dict[str, Any]]:
    persona = _persona_by_id(trader_id)
    if not persona:
        return None
    cached = _CACHE.get(persona["id"])
    if not cached:
        monthly = _generate_monthly_returns(persona, months=12)
        curve = _generate_equity_curve(persona, months=12)
        stats = _stats_from_truth(persona, curve, monthly)
        risk = _risk_score(persona, stats)
        avatar_url = f"https://api.dicebear.com/7.x/avataaars/svg?seed={persona['seed']}"
        # Downsample curve for lightweight payloads (max ~120 points)
        step = max(1, len(curve) // 120)
        light_curve = curve[::step]
        joined_days_ago = 90 + (persona["seed"] % 900)
        cached = {
            **{k: persona[k] for k in ["id","name","country_code","country_name","style","experience_years","bio","verified"]},
            "avatar_url": avatar_url,
            "joined_days_ago": joined_days_ago,
            "stats": stats,
            "risk": risk,
            "monthly_returns_pct": [round(r * 100, 2) for r in monthly],
            "equity_curve": light_curve,
        }
        _CACHE[persona["id"]] = cached
    if include_curve:
        return cached
    # summary — drop heavy fields
    out = {k: v for k, v in cached.items() if k != "equity_curve"}
    return out


def list_traders() -> List[Dict[str, Any]]:
    return [get_trader(p["id"]) for p in _PERSONAS]  # summary version


def list_trader_ids() -> List[str]:
    return [p["id"] for p in _PERSONAS]


# ---------------------------------------------------------------------------
# Trades (open + closed history) — also deterministic
# ---------------------------------------------------------------------------
_SYMBOLS_BY_STYLE = {
    "Scalping":         ["EURUSD","GBPUSD","USDJPY","EURJPY"],
    "Day Trading":      ["EURUSD","GBPUSD","XAUUSD","BTCUSD","US30"],
    "Swing":            ["XAUUSD","EURUSD","GBPUSD","USOIL"],
    "Position":         ["XAUUSD","USOIL","SPX500","NAS100"],
    "Trend Following":  ["XAUUSD","USOIL","BTCUSD","SPX500","GER40"],
    "Mean Reversion":   ["EURUSD","GBPUSD","EURGBP","AUDUSD"],
    "News Trader":      ["EURUSD","GBPUSD","XAUUSD","US30"],
    "Breakout":         ["XAUUSD","BTCUSD","US30","NAS100"],
    "Grid":             ["USDCHF","EURCHF","EURGBP","AUDCAD"],
    "Arbitrage":        ["EURUSD","EURGBP","EURJPY","GBPJPY"],
}

def _trader_symbols(persona: Dict[str, Any]) -> List[str]:
    return _SYMBOLS_BY_STYLE.get(persona["style"], ["EURUSD","GBPUSD","XAUUSD"])


def open_trades(trader_id: str) -> List[Dict[str, Any]]:
    persona = _persona_by_id(trader_id)
    if not persona:
        return []
    rng = random.Random(persona["seed"] * 23 + 3)
    truth = persona["truth"]
    n_open = min(6, max(0, int(rng.uniform(0, 5))))
    syms = _trader_symbols(persona)
    trades: List[Dict[str, Any]] = []
    now = time.time()
    for i in range(n_open):
        sym = syms[rng.randint(0, len(syms) - 1)]
        side = "buy" if rng.random() < 0.55 else "sell"
        entry_hours_ago = rng.uniform(0.2, max(0.5, truth["avg_holding_hours"] * 0.8))
        entry_price = _mock_price_for_symbol(sym) * rng.uniform(0.995, 1.005)
        current_price = _mock_price_for_symbol(sym) * rng.uniform(0.995, 1.005)
        lot = round(truth["avg_lot"] * rng.uniform(0.7, 1.3), 2)
        pnl_pct = ((current_price - entry_price) / entry_price) * (1 if side == "buy" else -1) * 100
        trades.append({
            "id": f"{trader_id}_open_{i+1}",
            "symbol": sym, "side": side, "lot_size": lot,
            "entry_price": round(entry_price, 4), "current_price": round(current_price, 4),
            "pnl_pct": round(pnl_pct, 2),
            "opened_at": now - entry_hours_ago * 3600,
        })
    return trades


def closed_trades(trader_id: str, limit: int = 40) -> List[Dict[str, Any]]:
    persona = _persona_by_id(trader_id)
    if not persona:
        return []
    rng = random.Random(persona["seed"] * 29 + 7)
    truth = persona["truth"]
    syms = _trader_symbols(persona)
    trades: List[Dict[str, Any]] = []
    now = time.time()
    for i in range(limit):
        sym = syms[rng.randint(0, len(syms) - 1)]
        side = "buy" if rng.random() < 0.55 else "sell"
        is_win = rng.random() < truth["win_rate"]
        base_pct = 0.002 * truth["payoff_ratio"] if is_win else -0.002
        base_pct *= rng.uniform(0.5, 1.6)
        entry_price = _mock_price_for_symbol(sym)
        exit_price = entry_price * (1 + base_pct * (1 if side == "buy" else -1))
        lot = round(truth["avg_lot"] * rng.uniform(0.6, 1.3), 2)
        # pnl_usd approximation (100 units per point for a 5-dp instrument-ish)
        pnl_usd = round((exit_price - entry_price) * lot * 10000 * (1 if side == "buy" else -1), 2)
        closed_hours_ago = i * truth["avg_holding_hours"] * rng.uniform(0.9, 1.2)
        trades.append({
            "id": f"{trader_id}_closed_{i+1}",
            "symbol": sym, "side": side, "lot_size": lot,
            "entry_price": round(entry_price, 4), "exit_price": round(exit_price, 4),
            "pnl_pct": round(base_pct * 100, 3), "pnl_usd": pnl_usd,
            "is_win": is_win,
            "opened_at": now - (closed_hours_ago + truth["avg_holding_hours"]) * 3600,
            "closed_at": now - closed_hours_ago * 3600,
        })
    return trades


def _mock_price_for_symbol(sym: str) -> float:
    # Anchor prices roughly matching Sprint 7 Slice 1 catalog
    anchors = {
        "EURUSD": 1.145, "GBPUSD": 1.345, "USDJPY": 158.5, "USDCHF": 0.902,
        "USDCAD": 1.372, "AUDUSD": 0.662, "NZDUSD": 0.607,
        "EURGBP": 0.851, "EURJPY": 181.6, "EURCHF": 1.032, "EURAUD": 1.729,
        "GBPJPY": 213.2, "AUDCAD": 0.908, "AUDJPY": 104.9,
        "XAUUSD": 4070, "XAGUSD": 48.2,
        "USOIL": 78.4, "UKOIL": 82.1,
        "SPX500": 6120, "NAS100": 21400, "US30": 45200, "GER40": 20450, "JPN225": 40200,
        "BTCUSD": 102000, "ETHUSD": 3820, "SOLUSD": 248,
    }
    return anchors.get(sym, 100.0)
