"""Seed 40+ realistic mock funds spanning all 11 categories.
NAV history is generated as a smooth random walk anchored to `current_nav`.
"""
from __future__ import annotations
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def _uid(prefix: str) -> str: return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _returns(base: float, vol: float, rnd: random.Random) -> Dict[str, float]:
    """Generate plausible period-returns for a fund."""
    m1 = round(rnd.gauss(base / 12, vol / 6), 2)
    m3 = round(rnd.gauss(base / 4, vol / 4), 2)
    m6 = round(rnd.gauss(base / 2, vol / 3), 2)
    y1 = round(rnd.gauss(base, vol), 2)
    y3 = round(rnd.gauss(base + 2, vol * 0.6), 2)
    y5 = round(rnd.gauss(base + 3, vol * 0.5), 2)
    return {"m1": m1, "m3": m3, "m6": m6, "y1": y1, "y3": y3, "y5": y5}


# (name, amc, category, sub, risk, base_return, vol, expense, exit, aum_cr, nav, stars)
FUND_TEMPLATES = [
    # Large Cap
    ("Axis Bluechip Fund - Direct Growth", "Axis Mutual Fund", "large_cap", "Large Cap", "moderate", 14, 12, 0.55, "1% before 1yr", 42800, 62.4, 5),
    ("SBI Bluechip Fund - Direct", "SBI Mutual Fund", "large_cap", "Large Cap", "moderate", 13, 11, 0.75, "1% before 1yr", 51200, 78.9, 4),
    ("Mirae Asset Large Cap - Direct", "Mirae Asset Mutual Fund", "large_cap", "Large Cap", "moderate", 15, 13, 0.5, "1% before 1yr", 37600, 92.1, 5),
    ("HDFC Top 100 Fund", "HDFC Mutual Fund", "large_cap", "Large Cap", "moderate", 12, 12, 1.05, "1% before 1yr", 26900, 933.5, 4),
    # Mid Cap
    ("Kotak Emerging Equity - Direct", "Kotak Mutual Fund", "mid_cap", "Mid Cap", "high", 18, 18, 0.6, "1% before 1yr", 33400, 100.4, 5),
    ("Axis Midcap Fund - Direct", "Axis Mutual Fund", "mid_cap", "Mid Cap", "high", 20, 20, 0.55, "1% before 1yr", 25100, 88.6, 5),
    ("PGIM India Midcap Opportunities", "PGIM Mutual Fund", "mid_cap", "Mid Cap", "high", 22, 22, 0.45, "1% before 1yr", 9200, 62.8, 4),
    # Small Cap
    ("Nippon Small Cap Fund - Direct", "Nippon India Mutual Fund", "small_cap", "Small Cap", "very_high", 26, 26, 0.7, "1% before 1yr", 41300, 168.5, 5),
    ("SBI Small Cap Fund - Direct", "SBI Mutual Fund", "small_cap", "Small Cap", "very_high", 24, 25, 0.75, "1% before 1yr", 21200, 152.3, 4),
    ("Axis Small Cap Fund - Direct", "Axis Mutual Fund", "small_cap", "Small Cap", "very_high", 23, 24, 0.55, "1% before 1yr", 18400, 88.9, 5),
    # ELSS
    ("Mirae Asset Tax Saver - Direct", "Mirae Asset Mutual Fund", "elss", "ELSS", "high", 17, 15, 0.6, "Lock-in 3yr", 19900, 42.6, 5),
    ("Axis Long Term Equity - Direct", "Axis Mutual Fund", "elss", "ELSS", "high", 15, 15, 0.85, "Lock-in 3yr", 32800, 96.4, 4),
    ("Quant Tax Plan - Direct", "Quant Mutual Fund", "elss", "ELSS", "very_high", 27, 24, 0.75, "Lock-in 3yr", 6100, 425.1, 5),
    # Index
    ("UTI Nifty 50 Index - Direct", "UTI Mutual Fund", "index", "Index - Nifty 50", "moderate", 13, 12, 0.20, "0.25% before 15d", 24500, 148.9, 4),
    ("ICICI Prudential Nifty Index - Direct", "ICICI Prudential Mutual Fund", "index", "Index - Nifty 50", "moderate", 13, 12, 0.17, "0.25% before 15d", 8600, 232.4, 4),
    ("Motilal Oswal Nasdaq 100 - Direct", "Motilal Oswal Mutual Fund", "index", "Index - International", "high", 20, 20, 0.55, "1% before 3d", 4200, 32.7, 5),
    # Debt
    ("HDFC Corporate Bond - Direct", "HDFC Mutual Fund", "debt", "Corporate Bond", "low", 7.5, 3, 0.35, "Nil", 31700, 30.4, 4),
    ("ICICI Prudential Short Term - Direct", "ICICI Prudential Mutual Fund", "debt", "Short Duration", "low", 7, 2.5, 0.4, "Nil", 18100, 55.2, 4),
    ("SBI Magnum Medium Duration - Direct", "SBI Mutual Fund", "debt", "Medium Duration", "low", 7.5, 3, 0.75, "Nil", 8300, 45.9, 3),
    # Liquid
    ("Aditya Birla SL Liquid - Direct", "Aditya Birla Sun Life Mutual Fund", "liquid", "Liquid", "low", 6.5, 0.5, 0.2, "Nil", 41200, 383.7, 4),
    ("Axis Liquid Fund - Direct", "Axis Mutual Fund", "liquid", "Liquid", "low", 6.5, 0.5, 0.15, "Nil", 32900, 2673.4, 4),
    # Hybrid
    ("ICICI Prudential Balanced Adv - Direct", "ICICI Prudential Mutual Fund", "hybrid", "Balanced Advantage", "moderate", 12, 8, 0.85, "1% before 1yr", 51500, 62.3, 5),
    ("HDFC Balanced Advantage - Direct", "HDFC Mutual Fund", "hybrid", "Balanced Advantage", "moderate", 11, 8, 0.85, "1% before 1yr", 88400, 431.2, 4),
    ("SBI Equity Hybrid - Direct", "SBI Mutual Fund", "hybrid", "Aggressive Hybrid", "moderate", 13, 10, 0.75, "1% before 1yr", 63700, 271.6, 5),
    # International
    ("Franklin US Opportunities - Direct", "Franklin Templeton Mutual Fund", "international", "US Equity", "high", 18, 20, 1.0, "1% before 3yr", 3800, 63.1, 4),
    ("PGIM India Global Equity Opp - Direct", "PGIM Mutual Fund", "international", "Global Equity", "high", 15, 20, 1.15, "1% before 3mo", 1400, 42.8, 3),
    # Gold Funds
    ("Nippon India Gold Savings - Direct", "Nippon India Mutual Fund", "gold", "Gold FoF", "moderate", 11, 12, 0.15, "1% before 1yr", 1800, 26.4, 4),
    ("HDFC Gold Fund - Direct", "HDFC Mutual Fund", "gold", "Gold FoF", "moderate", 11, 12, 0.2, "1% before 1yr", 2200, 22.8, 4),
    # More Large/Mid/Small
    ("Canara Robeco Bluechip - Direct", "Canara Robeco Mutual Fund", "large_cap", "Large Cap", "moderate", 13, 12, 0.4, "1% before 1yr", 12200, 55.7, 5),
    ("Motilal Oswal Focused 25 - Direct", "Motilal Oswal Mutual Fund", "large_cap", "Focused Large Cap", "moderate", 14, 13, 0.9, "1% before 1yr", 1800, 45.3, 3),
    ("Invesco India Midcap - Direct", "Invesco Mutual Fund", "mid_cap", "Mid Cap", "high", 19, 19, 0.72, "1% before 1yr", 4100, 145.6, 4),
    ("Tata Digital India - Direct", "Tata Mutual Fund", "equity", "Sectoral - Tech", "very_high", 24, 26, 0.35, "0.25% before 30d", 9500, 51.6, 5),
    ("SBI Contra Fund - Direct", "SBI Mutual Fund", "equity", "Value/Contra", "high", 18, 17, 0.65, "1% before 1yr", 22400, 350.4, 5),
    ("Parag Parikh Flexi Cap - Direct", "PPFAS Mutual Fund", "equity", "Flexi Cap", "high", 20, 15, 0.7, "2% before 365d", 71800, 79.6, 5),
    ("Quant Active Fund - Direct", "Quant Mutual Fund", "equity", "Multi Cap", "very_high", 28, 25, 0.6, "1% before 1yr", 8400, 685.2, 5),
    # Sectoral/thematic
    ("ICICI Prudential Technology - Direct", "ICICI Prudential Mutual Fund", "equity", "Sectoral - Tech", "very_high", 22, 25, 1.1, "1% before 1yr", 12200, 191.5, 5),
    ("Nippon India Banking - Direct", "Nippon India Mutual Fund", "equity", "Sectoral - Banking", "high", 16, 20, 1.05, "1% before 1yr", 6300, 542.7, 4),
    # More debt
    ("Nippon India Ultra Short Duration - Direct", "Nippon India Mutual Fund", "debt", "Ultra Short Duration", "low", 6.8, 1.5, 0.2, "Nil", 8600, 3821.4, 4),
    ("Kotak Corporate Bond - Direct", "Kotak Mutual Fund", "debt", "Corporate Bond", "low", 7.2, 3, 0.3, "Nil", 12400, 3512.8, 4),
    # More liquid
    ("HDFC Liquid Fund - Direct", "HDFC Mutual Fund", "liquid", "Liquid", "low", 6.4, 0.5, 0.2, "Nil", 46800, 4622.3, 4),
]

SECTORS = ["Financial Services", "IT", "Consumer Goods", "Energy", "Healthcare", "Automobile", "Metals", "Telecom", "Construction", "Chemicals"]

STOCK_POOL = [
    "HDFC Bank", "ICICI Bank", "Reliance Industries", "TCS", "Infosys", "Wipro",
    "L&T", "SBI", "Kotak Bank", "Bharti Airtel", "Bajaj Finance", "Asian Paints",
    "Nestle India", "Sun Pharma", "Tata Steel", "Tata Motors", "Maruti Suzuki",
    "M&M", "Adani Ports", "Titan", "HUL", "ITC", "ONGC", "NTPC", "PowerGrid",
    "Britannia", "Divi's Labs", "UPL", "Cipla", "Dr Reddy's",
]

MANAGERS = ["Rajeev Thakkar", "Kayzad Eghlim", "Neelesh Surana", "Sailesh Raj Bhan",
              "Anand Radhakrishnan", "Sohini Andani", "R Srinivasan", "Chirag Setalvad",
              "Prashant Jain", "Kalpen Parekh", "Ankit Goel", "Sanjay Chawla",
              "Vinit Sambre", "Trideep Bhattacharya"]


def build_seed(count: Optional[int] = None) -> List[Dict[str, Any]]:
    rnd = random.Random(11)
    funds: List[Dict[str, Any]] = []
    tmpls = FUND_TEMPLATES if not count else FUND_TEMPLATES[:count]
    for i, (name, amc, cat, sub, risk, base, vol, expense, exit_load, aum, nav, stars) in enumerate(tmpls):
        rets = _returns(base, vol, rnd)
        # Portfolio holdings
        picks = rnd.sample(STOCK_POOL, k=min(10, len(STOCK_POOL))) if cat not in ("debt", "liquid") else []
        remaining = 100.0
        holdings = []
        for j, s in enumerate(picks):
            w = round(rnd.uniform(3.0, min(12.0, remaining - (len(picks) - j - 1))), 2) if j < len(picks) - 1 else round(remaining, 2)
            remaining = max(0, round(remaining - w, 2))
            holdings.append({"name": s, "weight": w})
        # Sector allocation
        sec_pool = rnd.sample(SECTORS, k=min(6, len(SECTORS)))
        rem = 100.0
        sectors = []
        for j, s in enumerate(sec_pool):
            w = round(rnd.uniform(8.0, 25.0), 2) if j < len(sec_pool) - 1 else round(rem, 2)
            rem = max(0, round(rem - w, 2))
            sectors.append({"name": s, "weight": w})
        funds.append({
            "fund_id": _uid("mf"),
            "scheme_code": f"1{1000 + i:04d}",
            "isin": f"INF{rnd.randint(100000000, 999999999)}",
            "name": name,
            "amc": amc,
            "category": cat,
            "sub_category": sub,
            "risk": risk,
            "expense_ratio": expense,
            "exit_load": exit_load,
            "aum_cr": aum,
            "min_lumpsum": 500 if cat in ("liquid", "debt") else 500,
            "min_sip": 500,
            "star_rating": stars,
            "fund_manager": rnd.choice(MANAGERS),
            "launch_date": (datetime(2005, 1, 1) + timedelta(days=rnd.randint(0, 6500))).isoformat(),
            "benchmark": {"large_cap": "Nifty 100 TRI", "mid_cap": "Nifty Midcap 150 TRI",
                            "small_cap": "Nifty Smallcap 250 TRI", "index": "Nifty 50 TRI",
                            "elss": "Nifty 500 TRI", "debt": "CRISIL Corporate Bond Index",
                            "liquid": "CRISIL Liquid Fund Index", "hybrid": "CRISIL Hybrid 50+50",
                            "international": "S&P 500 TRI", "gold": "Domestic Gold Price",
                            "equity": "Nifty 500 TRI"}.get(cat, "Nifty 500 TRI"),
            "objective": f"To generate {'capital appreciation' if cat != 'debt' else 'stable income'} by investing in {sub} securities.",
            "current_nav": nav,
            "returns": rets,
            "holdings": holdings,
            "sector_allocation": sectors,
            "documents": [
                {"kind": "SID", "url": "https://www.amfiindia.com/", "label": "Scheme Information Document"},
                {"kind": "KIM", "url": "https://www.amfiindia.com/", "label": "Key Info Memorandum"},
                {"kind": "FactSheet", "url": "https://www.amfiindia.com/", "label": "Fact Sheet"},
            ],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
    return funds


def build_nav_history(fund: Dict[str, Any], days: int = 400) -> List[Dict[str, Any]]:
    rnd = random.Random(hash(fund["fund_id"]) & 0xFFFFFFFF)
    now = datetime.now(timezone.utc)
    curr = fund["current_nav"]
    y1_ret_pct = fund["returns"]["y1"] / 100.0
    # start value approx 1yr ago: curr / (1+y1)
    start = curr / max(0.01, 1 + y1_ret_pct)
    # If days > 365, extend further back
    if days > 365:
        start = start / max(0.01, 1 + (fund["returns"]["y3"] / 100.0) * (days - 365) / (365 * 3))
    step = (curr - start) / days
    vol_daily = curr * (fund["returns"]["y1"] / 100.0) / 250  # approx daily vol
    v = start
    out = []
    for i in range(days):
        drift = step
        shock = rnd.gauss(0, vol_daily * 0.5)
        v = max(0.1, v + drift + shock)
        ts = now - timedelta(days=(days - i))
        out.append({"fund_id": fund["fund_id"], "scheme_code": fund["scheme_code"],
                    "nav": round(v, 4), "as_of": ts})
    # ensure last matches current_nav
    out[-1]["nav"] = curr
    return out
