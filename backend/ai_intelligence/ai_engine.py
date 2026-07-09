"""AI Intelligence — Claude Reasoning Engine (Sprint 7C.1)

Uses Emergent LLM key + Claude Sonnet 4.5 (via emergentintegrations) to
generate a short, structured "why" narrative for a signal.

Design:
  * NEVER called during list/scan (would be too slow & expensive)
  * Called on-demand when user opens signal detail
  * Cached in mongo `ai_signal_explanations` by (symbol, timeframe, bar_index) for reuse
  * Falls back to a deterministic template if the LLM is unavailable
"""
from __future__ import annotations
import logging
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv

try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
    HAS_LLM = True
except Exception:
    LlmChat = UserMessage = None  # type: ignore
    HAS_LLM = False

load_dotenv()
logger = logging.getLogger("ai.intel.engine")

EMERGENT_KEY = (os.environ.get("EMERGENT_LLM_KEY") or "").strip()
MODEL_PROVIDER = "anthropic"
MODEL_NAME = "claude-sonnet-4-5-20250929"

SYSTEM_PROMPT = (
    "You are the My Funding Bank AI trading analyst. Given a technical signal "
    "package for one instrument, produce a concise 3-sentence rationale that "
    "explains WHY the signal was generated, referencing 2-3 specific indicator "
    "readings. Also include a one-line 'risk note' warning about the biggest "
    "downside. Return plain text only (no markdown). Keep total length under "
    "500 characters. Never give financial advice — end with 'Not investment advice.'"
)


def _fallback_narrative(sig: Dict[str, Any]) -> str:
    """Deterministic explanation when LLM is unavailable."""
    hits = sig.get("reason_hits") or []
    reasons = "; ".join(hits[:3]) if hits else "mixed indicators"
    side_upper = sig["side"].upper()
    conf = sig["confidence_pct"]
    strength = sig["signal_strength"].replace("_", " ")
    return (
        f"Technical setup: {reasons}. {side_upper} signal generated with "
        f"{conf}% confidence and {strength} strength based on the current "
        f"{sig['timeframe']} bar. Risk note: signal invalidates if price crosses "
        f"the {'stop-loss' if sig.get('stop_loss') else 'invalidation'} zone; "
        f"broader macro news can override technicals. Not investment advice."
    )


async def _call_llm(sig: Dict[str, Any]) -> Optional[str]:
    if not (HAS_LLM and EMERGENT_KEY):
        return None
    try:
        session = f"ai-signal-{sig['symbol']}-{sig['timeframe']}-{sig.get('bar_index',0)}"
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=session,
            system_message=SYSTEM_PROMPT,
        ).with_model(MODEL_PROVIDER, MODEL_NAME)
        ind = sig.get("indicators") or {}
        prompt = (
            f"Symbol: {sig['symbol']} ({sig.get('display')}) — {sig['timeframe']}\n"
            f"Side: {sig['side'].upper()} | Confidence: {sig['confidence_pct']}% | Strength: {sig['signal_strength']}\n"
            f"Trend: {sig['trend']}\n"
            f"Entry: {sig['entry']} | SL: {sig.get('stop_loss')} | TP1: {sig.get('tp1')} | TP2: {sig.get('tp2')} | TP3: {sig.get('tp3')}\n"
            f"Indicators: EMA20={ind.get('ema20')} EMA50={ind.get('ema50')} EMA200={ind.get('ema200')} "
            f"RSI={ind.get('rsi')} MACD_hist={ind.get('macd',{}).get('hist')} ADX={ind.get('adx')} "
            f"SuperTrend={ind.get('supertrend',{}).get('direction')} VWAP={ind.get('vwap')}\n"
            f"Bull/bear reasons: {'; '.join(sig.get('reason_hits',[]) or [])}\n"
            "Write the 3-sentence rationale now."
        )
        response = await chat.send_message(UserMessage(text=prompt))
        text = (getattr(response, "content", None) or str(response)).strip()
        return text or None
    except Exception as e:
        logger.warning("Claude signal narrative failed: %s", e)
        return None


async def explanation_for(db, sig: Dict[str, Any]) -> str:
    """Return AI explanation for a signal, using mongo cache."""
    cache_key = f"{sig['symbol']}|{sig['timeframe']}|{sig.get('bar_index', 0)}"
    doc = await db.ai_signal_explanations.find_one({"_id": cache_key}, {"_id": 0, "text": 1})
    if doc and doc.get("text"):
        return doc["text"]
    text = await _call_llm(sig)
    if not text:
        text = _fallback_narrative(sig)
    try:
        await db.ai_signal_explanations.update_one(
            {"_id": cache_key},
            {"$set": {"text": text, "symbol": sig["symbol"], "timeframe": sig["timeframe"],
                      "bar_index": sig.get("bar_index"), "cached_at": __import__("datetime").datetime.utcnow()}},
            upsert=True,
        )
    except Exception:
        pass
    return text
