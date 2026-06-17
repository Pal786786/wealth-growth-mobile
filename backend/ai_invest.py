"""AI Investment Suggestions — uses Emergent LLM key (Claude Sonnet 4.6) to
generate personalized Buy/Hold/Sell recommendations based on a user's portfolio,
wallet, KYC status, recent activity, and live market quotes.

Endpoint: GET /api/invest/ai-suggestions
- Cached per-user for 30 minutes in MongoDB to keep token spend predictable.
- Always returns 200 with a JSON suggestion payload — falls back to a deterministic
  rule-based suggestion if the LLM fails or no key is configured (demo mode).
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from dotenv import load_dotenv

load_dotenv()

_db = None
_get_current_user = None
_get_stocks = None
_logger = None

CACHE_TTL_MIN = 30
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "").strip()

SYSTEM_PROMPT = """You are a SEBI-aware Indian investment co-pilot for the "My Funding Bank" fintech app.
You give personalised, plain-English recommendations on Indian equities, gold (sovereign / digital),
and SIPs in mutual funds. You are conservative, risk-aware, and ALWAYS include a friendly disclaimer.

You MUST reply with a single JSON object only — no markdown, no commentary, no code fences.
JSON shape:
{
  "overall_summary": "1-2 sentence plain-English headline",
  "risk_score": 1-5,                 // 1 = very conservative, 5 = aggressive
  "risk_label": "Conservative|Moderate|Balanced|Growth|Aggressive",
  "recommendations": [
    {"symbol": "RELIANCE", "name": "Reliance Industries", "action": "buy|hold|sell",
     "confidence": "low|med|high", "reason": "short reason in 1 sentence"}
  ],
  "suggested_sip": {                  // optional, null if user already has good SIP
    "amount": 2000,
    "scheme_type": "Large Cap Equity|Hybrid|Index|Liquid|Gold ETF",
    "reason": "..."
  },
  "next_steps": ["short actionable bullet 1", "..."],
  "disclaimer": "..."
}

Rules:
- Never invent prices or numbers beyond what is provided in the context.
- Recommend SELL only when context shows the user holds that asset.
- Suggested SIP amount must be <= 25% of wallet_balance, min ₹500, multiples of ₹100.
- Always include the disclaimer field.
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rule_based_fallback(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic suggestion used when LLM is unavailable. Mirrors LLM output shape."""
    quotes: List[Dict[str, Any]] = ctx.get("market", {}).get("stocks", []) or []
    holdings = {h["symbol"]: h for h in (ctx.get("portfolio") or [])}

    recs: List[Dict[str, Any]] = []
    # Pick the 2 biggest dippers as BUY and 1 biggest gainer as HOLD/SELL (if held)
    sorted_by_chg = sorted(quotes, key=lambda q: q.get("change", 0))
    for q in sorted_by_chg[:2]:
        recs.append({
            "symbol": q["symbol"], "name": q.get("name", q["symbol"]),
            "action": "buy", "confidence": "med",
            "reason": f"Down {abs(q.get('change',0)):.2f}% — possible value entry on the dip.",
        })
    for q in sorted_by_chg[-1:]:
        held = q["symbol"] in holdings
        recs.append({
            "symbol": q["symbol"], "name": q.get("name", q["symbol"]),
            "action": "sell" if held and q.get("change", 0) > 2 else "hold",
            "confidence": "med",
            "reason": f"Up {q.get('change',0):.2f}% today — {'consider booking partial profit.' if held else 'wait for a pullback.'}",
        })

    wallet = ctx.get("wallet_balance", 0) or 0
    sip = None
    if wallet >= 2000:
        amount = max(500, min(5000, int((wallet * 0.10) // 100) * 100))
        sip = {
            "amount": amount,
            "scheme_type": "Index" if wallet < 25000 else "Large Cap Equity",
            "reason": "Start small with an index SIP for steady long-term compounding.",
        }
    return {
        "overall_summary": "Markets look mixed today. Consider buying on dips and trimming high-fliers.",
        "risk_score": 3,
        "risk_label": "Balanced",
        "recommendations": recs,
        "suggested_sip": sip,
        "next_steps": [
            "Top up your wallet for a regular monthly SIP.",
            "Complete KYC to unlock equity & mutual fund investing." if ctx.get("kyc_status") != "verified" else "Diversify across at least 4–5 stocks.",
        ],
        "disclaimer": "These are not investment advice. Markets are subject to risk. Please read scheme docs carefully.",
        "mode": "demo",
    }


def _extract_json(text: str) -> Dict[str, Any]:
    """Pull the first JSON object out of a LLM response (handles code fences / chatter)."""
    if not text:
        raise ValueError("empty response")
    # Strip code fences if any
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    # Find the first {...} block
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("no json object found")
    return json.loads(m.group(0))


async def _build_context(user: Dict[str, Any]) -> Dict[str, Any]:
    # Live (cached) market data
    try:
        market_stocks = await _get_stocks()
    except Exception:
        market_stocks = []
    # Gold price override
    gold = await _db.app_settings.find_one({"_key": "gold_rate"}, {"_id": 0}) if _db is not None else None
    gold_price = (gold or {}).get("price_per_gram", 7800)

    # User portfolio (sums by symbol)
    investments = await _db.investments.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(50)
    by_symbol: Dict[str, Dict[str, Any]] = {}
    for inv in investments:
        sym = inv.get("symbol") or inv.get("asset_type", "GOLD")
        agg = by_symbol.setdefault(sym, {"symbol": sym, "asset_type": inv.get("asset_type"), "invested": 0.0, "units": 0.0})
        agg["invested"] += float(inv.get("amount", 0) or 0)
        agg["units"] += float(inv.get("units", 0) or 0)
    portfolio = list(by_symbol.values())

    # Recent transactions (last 5)
    txns_cursor = _db.transactions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).limit(5)
    txns_recent = [
        {"type": t.get("type"), "amount": t.get("amount"), "description": t.get("description"),
         "status": t.get("status")}
        async for t in txns_cursor
    ]

    return {
        "user": {
            "name": user.get("name") or "Investor",
            "kyc_status": user.get("kyc_status", "pending"),
        },
        "wallet_balance": float(user.get("wallet_balance", 0) or 0),
        "portfolio": portfolio,
        "recent_transactions": txns_recent,
        "market": {
            "stocks": [
                {"symbol": s["symbol"], "name": s.get("name", s["symbol"]),
                 "price": s.get("price"), "change": s.get("change")}
                for s in market_stocks
            ],
            "gold_price_per_gram": gold_price,
        },
        "kyc_status": user.get("kyc_status", "pending"),
    }


async def _ask_llm(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Call Claude Sonnet 4.6 via Emergent LLM key. Returns parsed JSON or raises."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore

    chat = LlmChat(
        api_key=EMERGENT_KEY,
        session_id=f"ai-suggest-{uuid.uuid4().hex[:8]}",
        system_message=SYSTEM_PROMPT,
    ).with_model("anthropic", "claude-sonnet-4-6")

    user_payload = json.dumps(ctx, default=str, ensure_ascii=False)
    user_msg = UserMessage(
        text=(
            "Here is the user's current snapshot. Generate a personalised set of "
            "recommendations as the JSON schema described in the system prompt.\n\n"
            f"USER_SNAPSHOT:\n{user_payload}"
        ),
    )
    reply = await chat.send_message(user_msg)
    return _extract_json(reply)


# ---------- Router ----------
def attach(parent_router: APIRouter, db, get_current_user, get_stocks_fn, logger=None):
    """Wire dependencies and mount the /api/invest/ai-suggestions endpoint."""
    global _db, _get_current_user, _get_stocks, _logger
    _db = db
    _get_current_user = get_current_user
    _get_stocks = get_stocks_fn
    _logger = logger

    router = APIRouter(prefix="/invest", tags=["ai-investments"])

    @router.get("/ai-suggestions")
    async def ai_suggestions(refresh: bool = False, user: Dict[str, Any] = Depends(get_current_user)):
        # Lookup cache (per user, last 30 min) unless refresh=true
        cache_key = {"user_id": user["user_id"]}
        if not refresh:
            cached = await _db.ai_suggestions.find_one(cache_key, {"_id": 0})
            if cached and cached.get("expires_at"):
                exp = cached["expires_at"]
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp > _now():
                    return {**cached["payload"], "cached": True, "generated_at": cached.get("generated_at")}

        ctx = await _build_context(user)

        if not EMERGENT_KEY:
            payload = _rule_based_fallback(ctx)
        else:
            try:
                payload = await _ask_llm(ctx)
                payload.setdefault("disclaimer",
                                   "These are not investment advice. Markets are subject to risk.")
                payload["mode"] = "live"
            except Exception as e:
                if _logger:
                    _logger.exception(f"AI suggestion fallback: {e}")
                payload = _rule_based_fallback(ctx)

        payload.setdefault("mode", "demo")
        payload["generated_at"] = _now().isoformat()
        payload["risk_label"] = payload.get("risk_label") or "Balanced"

        await _db.ai_suggestions.update_one(
            cache_key,
            {"$set": {
                "user_id": user["user_id"],
                "payload": payload,
                "generated_at": _now(),
                "expires_at": _now() + timedelta(minutes=CACHE_TTL_MIN),
            }},
            upsert=True,
        )
        return {**payload, "cached": False}

    parent_router.include_router(router)
