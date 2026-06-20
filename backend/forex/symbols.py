"""Forex symbols registry — single source of truth.

MVP uses 5 symbols (XAUUSD, EURUSD, GBPUSD, USDJPY, BTCUSD). Each entry
defines display info, the format used by Twelve Data and Binance, and
contract specifications used by the paper-trading engine for P&L calc.
"""
from __future__ import annotations
from typing import Dict, List, Optional, Any

USD_INR = 83.0  # display conversion (admin will be able to override later)

# Spec: 1 lot trades `contract_size` units; P&L_USD = (close-open) * contract_size * lot_size * dir
SYMBOLS: List[Dict[str, Any]] = [
    {
        "id": "XAUUSD",
        "display": "XAU/USD",
        "name": "Gold / US Dollar",
        "asset_class": "metals",
        "twelve_data": "XAU/USD",
        "binance": None,
        "pip_size": 0.01,
        "contract_size": 100,        # 100 oz per lot
        "starting_price": 2340.50,
        "volatility": 0.0008,
        "spread_pips": 15,            # default spread (admin editable)
        "price_decimals": 2,
    },
    {
        "id": "EURUSD",
        "display": "EUR/USD",
        "name": "Euro / US Dollar",
        "asset_class": "forex",
        "twelve_data": "EUR/USD",
        "binance": None,
        "pip_size": 0.0001,
        "contract_size": 100000,
        "starting_price": 1.0850,
        "volatility": 0.00025,
        "spread_pips": 1,
        "price_decimals": 5,
    },
    {
        "id": "GBPUSD",
        "display": "GBP/USD",
        "name": "British Pound / US Dollar",
        "asset_class": "forex",
        "twelve_data": "GBP/USD",
        "binance": None,
        "pip_size": 0.0001,
        "contract_size": 100000,
        "starting_price": 1.2680,
        "volatility": 0.00030,
        "spread_pips": 2,
        "price_decimals": 5,
    },
    {
        "id": "USDJPY",
        "display": "USD/JPY",
        "name": "US Dollar / Japanese Yen",
        "asset_class": "forex",
        "twelve_data": "USD/JPY",
        "binance": None,
        "pip_size": 0.01,
        "contract_size": 100000,
        "starting_price": 157.20,
        "volatility": 0.00025,
        "spread_pips": 1,
        "price_decimals": 3,
    },
    {
        "id": "BTCUSD",
        "display": "BTC/USD",
        "name": "Bitcoin / US Dollar",
        "asset_class": "crypto",
        "twelve_data": "BTC/USD",
        "binance": "btcusdt",
        "pip_size": 1.0,
        "contract_size": 1,
        "starting_price": 67400.0,
        "volatility": 0.0025,
        "spread_pips": 25,
        "price_decimals": 2,
    },
]

SYMBOL_INDEX: Dict[str, Dict[str, Any]] = {s["id"]: s for s in SYMBOLS}


def get_symbol(symbol_id: str) -> Optional[Dict[str, Any]]:
    return SYMBOL_INDEX.get(symbol_id.upper())
