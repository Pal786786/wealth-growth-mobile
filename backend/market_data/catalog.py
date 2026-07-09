"""
Instrument Catalog — Sprint 7 Slice 1
-------------------------------------
Scalable symbol registry organised by category. Frontend renders any symbol
returned by the /catalog endpoint without code changes — new instruments just
need to be added here.

Categories are open-ended; the frontend simply reads whatever categories the
API surfaces. Future NSE / BSE / ETF / stocks providers add themselves here.

Each instrument has:
  symbol_id  — internal unique key (uppercase, no slashes)
  display    — human-friendly ticker (e.g. "EUR/USD")
  name       — full instrument name
  category   — one of CATEGORIES (open-ended)
  currency   — quote currency for display formatting
  seed       — starting price for the mock random-walk provider
  vol        — annualised volatility hint for mock provider
  trend      — mock drift factor (tiny positive/negative bias)
  price_dp   — decimals of precision to render
  provider_symbols — cross-provider aliases (e.g. {"twelvedata": "EUR/USD", "binance": "EURUSDT"})
  extras     — pip size, contract size, unit, etc. (optional)

Notes:
  - This module never touches Mongo or emits ticks — it is a pure catalog.
  - Prices used in the mock provider start at seed and drift; not meant to be
    accurate live values.
"""
from __future__ import annotations
from typing import Dict, List, Any, Optional

# Category id → display metadata. Order here defines the default browse order.
CATEGORIES: List[Dict[str, str]] = [
    {"id": "forex_majors",  "label": "Forex Majors",   "icon": "banknote",     "desc": "USD-quoted major pairs"},
    {"id": "forex_minors",  "label": "Forex Minors",   "icon": "banknote",     "desc": "Cross pairs without USD"},
    {"id": "forex_exotics", "label": "Forex Exotics",  "icon": "banknote",     "desc": "Emerging-market pairs"},
    {"id": "metals",        "label": "Metals",         "icon": "coins",        "desc": "Precious & industrial metals"},
    {"id": "energies",      "label": "Energies",       "icon": "flame",        "desc": "Oil, gas, refined products"},
    {"id": "indices",       "label": "Indices",        "icon": "line-chart",   "desc": "Global stock indices"},
    {"id": "crypto",        "label": "Crypto",         "icon": "bitcoin",      "desc": "Digital assets"},
    {"id": "commodities",   "label": "Commodities",    "icon": "wheat",        "desc": "Soft commodities & agri"},
    {"id": "stocks",        "label": "Stocks",         "icon": "building",     "desc": "Equities (future)"},
    {"id": "etfs",          "label": "ETFs",           "icon": "briefcase",    "desc": "Exchange traded funds (future)"},
]

def _mk(symbol_id: str, display: str, name: str, category: str, currency: str,
        seed: float, vol: float, dp: int = 5, trend: float = 0.0,
        twelvedata: Optional[str] = None, binance: Optional[str] = None,
        alpha_vantage: Optional[str] = None, extras: Optional[dict] = None) -> Dict[str, Any]:
    return {
        "symbol_id": symbol_id, "display": display, "name": name, "category": category,
        "currency": currency, "seed": seed, "vol": vol, "trend": trend, "price_dp": dp,
        "provider_symbols": {
            "twelvedata": twelvedata or display,
            "binance": binance,
            "alpha_vantage": alpha_vantage or display.replace("/", ""),
        },
        "extras": extras or {},
    }

# ---------------------------------------------------------------------------
# FOREX MAJORS (7)
# ---------------------------------------------------------------------------
FOREX_MAJORS: List[Dict[str, Any]] = [
    _mk("EURUSD", "EUR/USD", "Euro / US Dollar",           "forex_majors", "USD", 1.1450, 0.0025, dp=5, twelvedata="EUR/USD"),
    _mk("GBPUSD", "GBP/USD", "British Pound / US Dollar",  "forex_majors", "USD", 1.3450, 0.0030, dp=5, twelvedata="GBP/USD"),
    _mk("USDJPY", "USD/JPY", "US Dollar / Japanese Yen",   "forex_majors", "JPY", 158.50, 0.0025, dp=3, twelvedata="USD/JPY"),
    _mk("USDCHF", "USD/CHF", "US Dollar / Swiss Franc",    "forex_majors", "CHF", 0.9020, 0.0022, dp=5, twelvedata="USD/CHF"),
    _mk("USDCAD", "USD/CAD", "US Dollar / Canadian Dollar","forex_majors", "CAD", 1.3720, 0.0022, dp=5, twelvedata="USD/CAD"),
    _mk("AUDUSD", "AUD/USD", "Australian Dollar / US Dollar","forex_majors","USD",0.6620, 0.0028, dp=5, twelvedata="AUD/USD"),
    _mk("NZDUSD", "NZD/USD", "New Zealand Dollar / US Dollar","forex_majors","USD",0.6070,0.0030, dp=5, twelvedata="NZD/USD"),
]

# ---------------------------------------------------------------------------
# FOREX MINORS (cross pairs, no USD) — 20
# ---------------------------------------------------------------------------
FOREX_MINORS: List[Dict[str, Any]] = [
    _mk("EURGBP", "EUR/GBP", "Euro / British Pound",       "forex_minors", "GBP", 0.8510, 0.0020, dp=5, twelvedata="EUR/GBP"),
    _mk("EURJPY", "EUR/JPY", "Euro / Japanese Yen",        "forex_minors", "JPY", 181.60, 0.0028, dp=3, twelvedata="EUR/JPY"),
    _mk("EURCHF", "EUR/CHF", "Euro / Swiss Franc",         "forex_minors", "CHF", 1.0320, 0.0022, dp=5, twelvedata="EUR/CHF"),
    _mk("EURAUD", "EUR/AUD", "Euro / Australian Dollar",   "forex_minors", "AUD", 1.7290, 0.0028, dp=5, twelvedata="EUR/AUD"),
    _mk("EURCAD", "EUR/CAD", "Euro / Canadian Dollar",     "forex_minors", "CAD", 1.5710, 0.0025, dp=5, twelvedata="EUR/CAD"),
    _mk("EURNZD", "EUR/NZD", "Euro / New Zealand Dollar",  "forex_minors", "NZD", 1.8860, 0.0030, dp=5, twelvedata="EUR/NZD"),
    _mk("GBPJPY", "GBP/JPY", "British Pound / Japanese Yen","forex_minors","JPY", 213.20, 0.0035, dp=3, twelvedata="GBP/JPY"),
    _mk("GBPCHF", "GBP/CHF", "British Pound / Swiss Franc","forex_minors", "CHF", 1.2130, 0.0025, dp=5, twelvedata="GBP/CHF"),
    _mk("GBPAUD", "GBP/AUD", "British Pound / Australian Dollar","forex_minors","AUD",2.0320,0.0032, dp=5, twelvedata="GBP/AUD"),
    _mk("GBPCAD", "GBP/CAD", "British Pound / Canadian Dollar","forex_minors","CAD",1.8460,0.0030, dp=5, twelvedata="GBP/CAD"),
    _mk("GBPNZD", "GBP/NZD", "British Pound / NZ Dollar",  "forex_minors", "NZD", 2.2140, 0.0035, dp=5, twelvedata="GBP/NZD"),
    _mk("AUDJPY", "AUD/JPY", "Australian Dollar / Japanese Yen","forex_minors","JPY",104.90,0.0030, dp=3, twelvedata="AUD/JPY"),
    _mk("AUDCHF", "AUD/CHF", "Australian Dollar / Swiss Franc","forex_minors","CHF",0.5970,0.0028, dp=5, twelvedata="AUD/CHF"),
    _mk("AUDCAD", "AUD/CAD", "Australian Dollar / Canadian Dollar","forex_minors","CAD",0.9080,0.0024, dp=5, twelvedata="AUD/CAD"),
    _mk("AUDNZD", "AUD/NZD", "Australian Dollar / NZ Dollar","forex_minors","NZD",1.0900, 0.0022, dp=5, twelvedata="AUD/NZD"),
    _mk("NZDJPY", "NZD/JPY", "New Zealand Dollar / Japanese Yen","forex_minors","JPY",96.20,0.0032, dp=3, twelvedata="NZD/JPY"),
    _mk("NZDCHF", "NZD/CHF", "New Zealand Dollar / Swiss Franc","forex_minors","CHF",0.5480,0.0028, dp=5, twelvedata="NZD/CHF"),
    _mk("NZDCAD", "NZD/CAD", "New Zealand Dollar / Canadian Dollar","forex_minors","CAD",0.8330,0.0026, dp=5, twelvedata="NZD/CAD"),
    _mk("CADJPY", "CAD/JPY", "Canadian Dollar / Japanese Yen","forex_minors","JPY",115.50,0.0028, dp=3, twelvedata="CAD/JPY"),
    _mk("CADCHF", "CAD/CHF", "Canadian Dollar / Swiss Franc","forex_minors","CHF",0.6570,0.0024, dp=5, twelvedata="CAD/CHF"),
    _mk("CHFJPY", "CHF/JPY", "Swiss Franc / Japanese Yen", "forex_minors", "JPY", 175.70, 0.0028, dp=3, twelvedata="CHF/JPY"),
]

# ---------------------------------------------------------------------------
# FOREX EXOTICS (emerging-market pairs) — 15
# ---------------------------------------------------------------------------
FOREX_EXOTICS: List[Dict[str, Any]] = [
    _mk("USDTRY", "USD/TRY", "US Dollar / Turkish Lira",     "forex_exotics", "TRY", 39.85, 0.010, dp=4, twelvedata="USD/TRY"),
    _mk("USDZAR", "USD/ZAR", "US Dollar / South African Rand","forex_exotics","ZAR",18.65, 0.008, dp=4, twelvedata="USD/ZAR"),
    _mk("USDMXN", "USD/MXN", "US Dollar / Mexican Peso",     "forex_exotics", "MXN", 20.10, 0.007, dp=4, twelvedata="USD/MXN"),
    _mk("USDSGD", "USD/SGD", "US Dollar / Singapore Dollar", "forex_exotics", "SGD", 1.3380, 0.0018, dp=5, twelvedata="USD/SGD"),
    _mk("USDHKD", "USD/HKD", "US Dollar / Hong Kong Dollar", "forex_exotics", "HKD", 7.7850, 0.0005, dp=5, twelvedata="USD/HKD"),
    _mk("USDCNH", "USD/CNH", "US Dollar / Chinese Yuan",     "forex_exotics", "CNH", 7.1450, 0.0018, dp=5, twelvedata="USD/CNH"),
    _mk("USDINR", "USD/INR", "US Dollar / Indian Rupee",     "forex_exotics", "INR", 84.20, 0.0022, dp=4, twelvedata="USD/INR"),
    _mk("USDTHB", "USD/THB", "US Dollar / Thai Baht",        "forex_exotics", "THB", 34.65, 0.0028, dp=4, twelvedata="USD/THB"),
    _mk("USDPHP", "USD/PHP", "US Dollar / Philippine Peso",  "forex_exotics", "PHP", 56.90, 0.0028, dp=4, twelvedata="USD/PHP"),
    _mk("USDMYR", "USD/MYR", "US Dollar / Malaysian Ringgit","forex_exotics", "MYR", 4.4230, 0.0024, dp=5, twelvedata="USD/MYR"),
    _mk("USDPLN", "USD/PLN", "US Dollar / Polish Zloty",     "forex_exotics", "PLN", 3.9720, 0.0032, dp=5, twelvedata="USD/PLN"),
    _mk("USDCZK", "USD/CZK", "US Dollar / Czech Koruna",     "forex_exotics", "CZK", 23.10, 0.0032, dp=4, twelvedata="USD/CZK"),
    _mk("USDHUF", "USD/HUF", "US Dollar / Hungarian Forint", "forex_exotics", "HUF", 361.20, 0.0038, dp=3, twelvedata="USD/HUF"),
    _mk("USDSEK", "USD/SEK", "US Dollar / Swedish Krona",    "forex_exotics", "SEK", 10.640, 0.0030, dp=4, twelvedata="USD/SEK"),
    _mk("USDNOK", "USD/NOK", "US Dollar / Norwegian Krone",  "forex_exotics", "NOK", 10.930, 0.0032, dp=4, twelvedata="USD/NOK"),
]

# ---------------------------------------------------------------------------
# METALS (4)
# ---------------------------------------------------------------------------
METALS: List[Dict[str, Any]] = [
    _mk("XAUUSD", "XAU/USD", "Gold / US Dollar",        "metals", "USD", 4070.00, 0.0008, dp=2, twelvedata="XAU/USD", extras={"unit": "per oz"}),
    _mk("XAGUSD", "XAG/USD", "Silver / US Dollar",      "metals", "USD",  48.20,  0.0018, dp=3, twelvedata="XAG/USD", extras={"unit": "per oz"}),
    _mk("XPTUSD", "XPT/USD", "Platinum / US Dollar",    "metals", "USD",  1050.0, 0.0015, dp=2, twelvedata="XPT/USD", extras={"unit": "per oz"}),
    _mk("XPDUSD", "XPD/USD", "Palladium / US Dollar",   "metals", "USD",  1130.0, 0.0022, dp=2, twelvedata="XPD/USD", extras={"unit": "per oz"}),
]

# ---------------------------------------------------------------------------
# ENERGIES (3)
# ---------------------------------------------------------------------------
ENERGIES: List[Dict[str, Any]] = [
    _mk("USOIL",  "US Oil",  "WTI Crude Oil",           "energies", "USD",  78.40, 0.0025, dp=2, twelvedata="WTI/USD", extras={"unit": "per barrel"}),
    _mk("UKOIL",  "UK Oil",  "Brent Crude Oil",         "energies", "USD",  82.10, 0.0025, dp=2, twelvedata="BCO/USD", extras={"unit": "per barrel"}),
    _mk("NATGAS", "Nat Gas", "Natural Gas",             "energies", "USD",   3.15, 0.0055, dp=3, twelvedata="NG",      extras={"unit": "per MMBtu"}),
]

# ---------------------------------------------------------------------------
# INDICES (10)
# ---------------------------------------------------------------------------
INDICES: List[Dict[str, Any]] = [
    _mk("US30",   "US30",   "Dow Jones Industrial Avg",  "indices", "USD", 45200.0, 0.0028, dp=1, twelvedata="DJI"),
    _mk("NAS100", "NAS100", "Nasdaq 100",                "indices", "USD", 21400.0, 0.0035, dp=1, twelvedata="NDX"),
    _mk("SPX500", "SPX500", "S&P 500",                   "indices", "USD",  6120.0, 0.0028, dp=1, twelvedata="SPX"),
    _mk("GER40",  "GER40",  "Germany DAX 40",            "indices", "EUR", 20450.0, 0.0028, dp=1, twelvedata="DAX"),
    _mk("UK100",  "UK100",  "UK FTSE 100",               "indices", "GBP",  8420.0, 0.0025, dp=1, twelvedata="UKX"),
    _mk("FRA40",  "FRA40",  "France CAC 40",             "indices", "EUR",  7830.0, 0.0028, dp=1, twelvedata="CAC"),
    _mk("JPN225", "JPN225", "Nikkei 225",                "indices", "JPY", 40200.0, 0.0032, dp=1, twelvedata="N225"),
    _mk("HK50",   "HK50",   "Hong Kong Hang Seng",       "indices", "HKD", 20120.0, 0.0035, dp=1, twelvedata="HSI"),
    _mk("AUS200", "AUS200", "Australia ASX 200",         "indices", "AUD",  8340.0, 0.0028, dp=1, twelvedata="XJO"),
    _mk("IND50",  "IND50",  "India Nifty 50",            "indices", "INR", 25700.0, 0.0028, dp=1, twelvedata="NIFTY"),
]

# ---------------------------------------------------------------------------
# CRYPTO (30 top by market cap)
# ---------------------------------------------------------------------------
CRYPTO: List[Dict[str, Any]] = [
    _mk("BTCUSD",  "BTC/USD",  "Bitcoin",         "crypto", "USD", 102000.0, 0.0030, dp=2, twelvedata="BTC/USD", binance="btcusdt"),
    _mk("ETHUSD",  "ETH/USD",  "Ethereum",        "crypto", "USD",   3820.0, 0.0038, dp=2, twelvedata="ETH/USD", binance="ethusdt"),
    _mk("BNBUSD",  "BNB/USD",  "Binance Coin",    "crypto", "USD",    738.0, 0.0035, dp=2, twelvedata="BNB/USD", binance="bnbusdt"),
    _mk("SOLUSD",  "SOL/USD",  "Solana",          "crypto", "USD",    248.0, 0.0055, dp=2, twelvedata="SOL/USD", binance="solusdt"),
    _mk("XRPUSD",  "XRP/USD",  "XRP",             "crypto", "USD",    2.42, 0.0048, dp=4, twelvedata="XRP/USD", binance="xrpusdt"),
    _mk("ADAUSD",  "ADA/USD",  "Cardano",         "crypto", "USD",    1.18, 0.0055, dp=4, twelvedata="ADA/USD", binance="adausdt"),
    _mk("DOGEUSD", "DOGE/USD", "Dogecoin",        "crypto", "USD",    0.42, 0.0065, dp=5, twelvedata="DOGE/USD", binance="dogeusdt"),
    _mk("MATICUSD","MATIC/USD","Polygon",         "crypto", "USD",    0.68, 0.0058, dp=4, twelvedata="MATIC/USD", binance="maticusdt"),
    _mk("DOTUSD",  "DOT/USD",  "Polkadot",        "crypto", "USD",   10.20, 0.0055, dp=3, twelvedata="DOT/USD", binance="dotusdt"),
    _mk("AVAXUSD", "AVAX/USD", "Avalanche",       "crypto", "USD",   58.20, 0.0060, dp=3, twelvedata="AVAX/USD", binance="avaxusdt"),
    _mk("LINKUSD", "LINK/USD", "Chainlink",       "crypto", "USD",   32.80, 0.0055, dp=3, twelvedata="LINK/USD", binance="linkusdt"),
    _mk("LTCUSD",  "LTC/USD",  "Litecoin",        "crypto", "USD",  148.00, 0.0045, dp=2, twelvedata="LTC/USD", binance="ltcusdt"),
    _mk("ATOMUSD", "ATOM/USD", "Cosmos",          "crypto", "USD",    9.85, 0.0058, dp=3, twelvedata="ATOM/USD", binance="atomusdt"),
    _mk("NEARUSD", "NEAR/USD", "NEAR Protocol",   "crypto", "USD",    7.10, 0.0062, dp=3, twelvedata="NEAR/USD", binance="nearusdt"),
    _mk("SHIBUSD", "SHIB/USD", "Shiba Inu",       "crypto", "USD", 0.000038, 0.0080, dp=8, twelvedata="SHIB/USD", binance="shibusdt"),
    _mk("TRXUSD",  "TRX/USD",  "TRON",            "crypto", "USD",    0.31, 0.0055, dp=5, twelvedata="TRX/USD", binance="trxusdt"),
    _mk("UNIUSD",  "UNI/USD",  "Uniswap",         "crypto", "USD",   16.80, 0.0055, dp=3, twelvedata="UNI/USD", binance="uniusdt"),
    _mk("XLMUSD",  "XLM/USD",  "Stellar",         "crypto", "USD",    0.44, 0.0060, dp=5, twelvedata="XLM/USD", binance="xlmusdt"),
    _mk("BCHUSD",  "BCH/USD",  "Bitcoin Cash",    "crypto", "USD",   620.00, 0.0050, dp=2, twelvedata="BCH/USD", binance="bchusdt"),
    _mk("ETCUSD",  "ETC/USD",  "Ethereum Classic","crypto", "USD",   32.40, 0.0055, dp=3, twelvedata="ETC/USD", binance="etcusdt"),
    _mk("APTUSD",  "APT/USD",  "Aptos",           "crypto", "USD",   14.20, 0.0060, dp=3, twelvedata="APT/USD", binance="aptusdt"),
    _mk("FILUSD",  "FIL/USD",  "Filecoin",        "crypto", "USD",    7.85, 0.0058, dp=3, twelvedata="FIL/USD", binance="filusdt"),
    _mk("ARBUSD",  "ARB/USD",  "Arbitrum",        "crypto", "USD",    1.12, 0.0065, dp=4, twelvedata="ARB/USD", binance="arbusdt"),
    _mk("OPUSD",   "OP/USD",   "Optimism",        "crypto", "USD",    2.85, 0.0065, dp=4, twelvedata="OP/USD",  binance="opusdt"),
    _mk("APEUSD",  "APE/USD",  "ApeCoin",         "crypto", "USD",    1.98, 0.0070, dp=4, twelvedata="APE/USD", binance="apeusdt"),
    _mk("SANDUSD", "SAND/USD", "The Sandbox",     "crypto", "USD",    0.86, 0.0070, dp=4, twelvedata="SAND/USD", binance="sandusdt"),
    _mk("AAVEUSD", "AAVE/USD", "Aave",            "crypto", "USD",  242.00, 0.0055, dp=2, twelvedata="AAVE/USD", binance="aaveusdt"),
    _mk("ALGOUSD", "ALGO/USD", "Algorand",        "crypto", "USD",    0.42, 0.0060, dp=4, twelvedata="ALGO/USD", binance="algousdt"),
    _mk("MANAUSD", "MANA/USD", "Decentraland",    "crypto", "USD",    0.68, 0.0075, dp=4, twelvedata="MANA/USD", binance="manausdt"),
    _mk("VETUSD",  "VET/USD",  "VeChain",         "crypto", "USD",    0.052, 0.0060, dp=5, twelvedata="VET/USD", binance="vetusdt"),
]

# ---------------------------------------------------------------------------
# COMMODITIES (soft / agri) — 6
# ---------------------------------------------------------------------------
COMMODITIES: List[Dict[str, Any]] = [
    _mk("COFFEE", "Coffee",  "Coffee C Arabica",        "commodities", "USD", 315.20, 0.0038, dp=2, twelvedata="KC=F"),
    _mk("SUGAR",  "Sugar",   "Sugar No.11",             "commodities", "USD",  22.15, 0.0032, dp=2, twelvedata="SB=F"),
    _mk("COCOA",  "Cocoa",   "Cocoa Futures",           "commodities", "USD", 8420.0, 0.0055, dp=1, twelvedata="CC=F"),
    _mk("COTTON", "Cotton",  "Cotton Futures",          "commodities", "USD",  74.20, 0.0028, dp=2, twelvedata="CT=F"),
    _mk("CORN",   "Corn",    "Corn Futures",            "commodities", "USD", 465.00, 0.0025, dp=2, twelvedata="ZC=F"),
    _mk("WHEAT",  "Wheat",   "Wheat Futures",           "commodities", "USD", 580.00, 0.0030, dp=2, twelvedata="ZW=F"),
]

# ---------------------------------------------------------------------------
# Full catalog
# ---------------------------------------------------------------------------
ALL_INSTRUMENTS: List[Dict[str, Any]] = (
    FOREX_MAJORS + FOREX_MINORS + FOREX_EXOTICS + METALS + ENERGIES + INDICES + CRYPTO + COMMODITIES
)
# Keyed lookup for O(1) resolves
BY_ID: Dict[str, Dict[str, Any]] = {inst["symbol_id"]: inst for inst in ALL_INSTRUMENTS}


def by_category(category: str) -> List[Dict[str, Any]]:
    return [i for i in ALL_INSTRUMENTS if i["category"] == category]


def category_stats() -> List[Dict[str, Any]]:
    """Return each category with instrument count."""
    counts: Dict[str, int] = {}
    for i in ALL_INSTRUMENTS:
        counts[i["category"]] = counts.get(i["category"], 0) + 1
    return [
        {**c, "count": counts.get(c["id"], 0)}
        for c in CATEGORIES
    ]


def search_catalog(q: str, limit: int = 25) -> List[Dict[str, Any]]:
    """Simple case-insensitive search across symbol_id, display and name."""
    if not q:
        return []
    q_upper = q.upper().strip()
    q_lower = q.lower().strip()
    hits: List[Dict[str, Any]] = []
    exact: List[Dict[str, Any]] = []
    prefix: List[Dict[str, Any]] = []
    substr: List[Dict[str, Any]] = []
    for inst in ALL_INSTRUMENTS:
        sid = inst["symbol_id"]
        disp = inst["display"].upper()
        name = inst["name"].lower()
        if sid == q_upper or disp == q_upper:
            exact.append(inst)
        elif sid.startswith(q_upper) or disp.startswith(q_upper) or name.startswith(q_lower):
            prefix.append(inst)
        elif q_upper in sid or q_upper in disp or q_lower in name:
            substr.append(inst)
    hits = exact + prefix + substr
    return hits[:limit]


def paginate(items: List[Dict[str, Any]], page: int, limit: int) -> Dict[str, Any]:
    """Standard offset pagination."""
    page = max(1, int(page or 1))
    limit = max(1, min(int(limit or 50), 200))
    total = len(items)
    start = (page - 1) * limit
    end = start + limit
    slice_ = items[start:end]
    return {
        "items": slice_,
        "page": page,
        "limit": limit,
        "total": total,
        "has_more": end < total,
        "total_pages": (total + limit - 1) // limit if limit else 1,
    }
