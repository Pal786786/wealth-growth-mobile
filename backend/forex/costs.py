"""Sprint 16.1 — Unified commission / trading-costs engine.

ONE calculation engine used by demo trading, copy trading, and (future) real /
AI trading. Settings live in forex_settings.trading_costs and are SNAPSHOTTED
onto every trade at open so later admin changes never affect old trades.

Fields stored with every trade (immutable after close):
    commission_type      fixed_per_lot | per_side | round_turn
    commission_rate      number (per lot)
    commission_currency  INR | USD
    commission_amount    final charged amount (INR)
    gross_pnl            raw market PnL (INR)
    swap_amount          0 for now (engine-ready)
    net_pnl              gross - commission - swap
"""
from __future__ import annotations
from typing import Any, Dict

from .symbols import USD_INR

VALID_TYPES = ("fixed_per_lot", "per_side", "round_turn")
VALID_CURRENCIES = ("INR", "USD")

DEFAULT_COSTS: Dict[str, Any] = {
    "commission_per_lot": 0.0,
    "commission_type": "fixed_per_lot",
    "commission_currency": "INR",
}


def costs_from_settings(cfg: Dict[str, Any]) -> Dict[str, Any]:
    tc = (cfg or {}).get("trading_costs") or {}
    ctype = tc.get("commission_type", DEFAULT_COSTS["commission_type"])
    ccur = tc.get("commission_currency", DEFAULT_COSTS["commission_currency"])
    return {
        "commission_per_lot": float(tc.get("commission_per_lot", 0.0) or 0.0),
        "commission_type": ctype if ctype in VALID_TYPES else "fixed_per_lot",
        "commission_currency": ccur if ccur in VALID_CURRENCIES else "INR",
    }


def snapshot_for_trade(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Immutable per-trade snapshot taken at order open."""
    c = costs_from_settings(cfg)
    return {
        "commission_type": c["commission_type"],
        "commission_rate": c["commission_per_lot"],
        "commission_currency": c["commission_currency"],
    }


def commission_inr(snapshot: Dict[str, Any], lot_size: float) -> float:
    """Total commission (INR) for a round trip of `lot_size` lots, from the
    trade's own snapshot — NEVER from current settings."""
    rate = float(snapshot.get("commission_rate", 0.0) or 0.0)
    ctype = snapshot.get("commission_type", "fixed_per_lot")
    base = rate * float(lot_size)
    if ctype == "per_side":
        base *= 2.0  # charged at open AND close
    if snapshot.get("commission_currency") == "USD":
        base *= USD_INR
    return round(base, 2)


def settle(snapshot: Dict[str, Any], lot_size: float, gross_pnl: float,
           swap_amount: float = 0.0) -> Dict[str, Any]:
    """Final immutable settlement numbers for a (partial) close."""
    commission = commission_inr(snapshot, lot_size)
    return {
        "gross_pnl": round(float(gross_pnl), 2),
        "commission_amount": commission,
        "swap_amount": round(float(swap_amount), 2),
        "net_pnl": round(float(gross_pnl) - commission - float(swap_amount), 2),
    }
