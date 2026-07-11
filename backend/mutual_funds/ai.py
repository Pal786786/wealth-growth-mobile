"""AI Advisor for Mutual Funds — reuses Emergent LLM key via emergentintegrations.

Endpoints delegate here for:
  * Analyze My Portfolio
  * Suggest Better Funds
  * Suggest SIP Increase
  * Tax Saving Suggestions
  * Risk Analysis
  * Diversification Advice
  * Top Funds / Best SIP / Goal-plan (used by user AI console)
"""
from __future__ import annotations
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mutual_funds.ai")

MODEL_MAP = {
    "claude": "claude-sonnet-4-5-20250929",
    "openai": "gpt-4o-mini",
}

SYSTEM_PROMPT = (
    "You are a SEBI-registered mutual funds advisor for the 'My Funding Bank' app in India. "
    "You are analytical, cautious, and always disclose that recommendations are educational, "
    "not investment advice. Speak in short bullet points. Prefer INR (₹). "
    "When suggesting funds, only refer to the funds already visible in the user's context; "
    "do NOT invent scheme names. Every response ends with a one-line risk disclaimer."
)


async def _ask_claude(user_prompt: str, context: Dict[str, Any]) -> str:
    """Try Claude via emergentintegrations; fall back to a stub if unavailable."""
    key = os.getenv("EMERGENT_LLM_KEY") or os.getenv("EMERGENTLLM_KEY") or os.getenv("EMERGENT_LLM")
    if not key:
        logger.warning("no EMERGENT_LLM_KEY, using stub advisor")
        return _stub_response(user_prompt, context)
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=key, session_id=f"mf-ai-{context.get('user_id', 'anon')}",
                       system_message=SYSTEM_PROMPT).with_model("anthropic", MODEL_MAP["claude"])
        content = f"{user_prompt}\n\n---\nCONTEXT (JSON):\n{json.dumps(context, default=str)[:6000]}"
        reply = await chat.send_message(UserMessage(text=content))
        return str(reply)
    except Exception as e:
        logger.warning("Claude call failed: %s", e)
        return _stub_response(user_prompt, context)


def _stub_response(prompt: str, ctx: Dict[str, Any]) -> str:
    holdings = ctx.get("holdings") or []
    if "analyze" in prompt.lower():
        return ("• Portfolio has {} holdings across {} AMCs.\n"
                "• Cost basis ₹{:,.0f} · current value ₹{:,.0f}.\n"
                "• Consider periodic rebalancing if any single fund exceeds 25%.\n"
                "This is educational content, not investment advice."
                ).format(len(holdings),
                          len({h.get("amc") for h in holdings if h.get("amc")}),
                          ctx.get("total_invested", 0), ctx.get("current_value", 0))
    if "suggest" in prompt.lower() and "sip" in prompt.lower():
        return ("• Consider increasing your SIP by 10% annually.\n"
                "• Split equally between a large-cap index fund and a flexi-cap.\n"
                "This is educational content, not investment advice.")
    if "tax" in prompt.lower():
        return ("• Use ELSS funds (up to ₹1.5L u/s 80C) for tax deduction and 3-year lock-in.\n"
                "• Redemption after 12 months attracts 10% LTCG above ₹1L gains.\n"
                "This is educational content, not investment advice.")
    if "risk" in prompt.lower():
        return ("• Your portfolio risk skews {} based on current allocation.\n"
                "• Diversify with 10-15% in debt/liquid to lower drawdown.\n"
                "This is educational content, not investment advice."
                ).format("moderate")
    return ("• I couldn't parse the question. Try: 'analyze my portfolio', 'suggest funds',\n"
            "  'tax saving', 'risk analysis' or 'diversification advice'.\n"
            "This is educational content, not investment advice.")


async def advise(kind: str, context: Dict[str, Any]) -> Dict[str, Any]:
    prompts = {
        "analyze_portfolio": "Analyze my mutual fund portfolio, highlight concentration risk, "
                              "over/underperformers, expense drag, and rebalancing recommendations.",
        "suggest_funds":     "Based on my holdings, recommend 3 better-fit funds from the list in context. "
                              "Explain WHY in 1 line each.",
        "sip_increase":      "Suggest by how much I could increase my SIP given my portfolio value and "
                              "trailing return trend. Suggest step-up % and split.",
        "tax_saving":        "Give me tax saving tips relevant to Indian mutual-fund investors including "
                              "ELSS, LTCG, and STCG considerations.",
        "risk_analysis":     "Analyze the risk profile of my portfolio (concentration, category, market cap "
                              "and drawdown). Rate low/moderate/high with rationale.",
        "diversification":   "Give me actionable diversification advice for my portfolio (asset, AMC, "
                              "category, market-cap, geography).",
        "top_funds":         "Recommend the top 5 mutual funds from the list in context for long-term "
                              "wealth creation.",
        "best_sip":          "Recommend the best 3 SIPs I could start today with ₹5,000 monthly.",
        "goal_plan":         "For each of my goals in context, recommend an approximate SIP amount and "
                              "fund allocation strategy.",
    }
    prompt = prompts.get(kind) or kind
    text = await _ask_claude(prompt, context)
    return {"kind": kind, "answer": text}
