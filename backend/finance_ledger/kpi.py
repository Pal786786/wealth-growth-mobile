"""Sprint 12.3 · Phase B — Finance KPI aggregators + report data builders.

Read-only aggregation over the immutable finance_journal + per-provider
tables. Everything is fresh-per-call — no caching, no GridFS persistence.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("finance_ledger.kpi")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def resolve_range(range_key: Optional[str],
                    date_from: Optional[datetime],
                    date_to: Optional[datetime]) -> Tuple[datetime, datetime]:
    """Return (start_utc, end_utc) inclusive of end. `range_key` is one of
    today | week | month | quarter | year | custom."""
    now = _now()
    if date_from and date_to:
        return date_from, date_to
    if range_key == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if range_key == "week":
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if range_key == "month":
        start = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if range_key == "quarter":
        start = (now - timedelta(days=90)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if range_key == "year":
        start = (now - timedelta(days=365)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    # Default: last 30 days
    start = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


async def sum_by_txn_type(db, txn_type: str, start: datetime, end: datetime,
                           reference_type: Optional[str] = None,
                           extra_match: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """Sum amount + count of journal entries by txn_type in a date range."""
    match: Dict[str, Any] = {
        "txn_type": txn_type,
        "entry_date": {"$gte": start, "$lte": end},
        "is_reversed": {"$ne": True},
    }
    if reference_type:
        match["reference_type"] = reference_type
    if extra_match:
        match.update(extra_match)
    pipeline = [{"$match": match},
                 {"$group": {"_id": None,
                              "amount": {"$sum": "$amount"},
                              "count": {"$sum": 1}}}]
    doc = await db.finance_journal.aggregate(pipeline).to_list(1)
    if not doc:
        return {"amount": 0.0, "count": 0}
    return {"amount": float(doc[0]["amount"] or 0), "count": int(doc[0]["count"] or 0)}


async def compute_dashboard(db, range_key: str = "month",
                             date_from: Optional[datetime] = None,
                             date_to: Optional[datetime] = None) -> Dict[str, Any]:
    start, end = resolve_range(range_key, date_from, date_to)

    deposits    = await sum_by_txn_type(db, "razorpay_deposit", start, end)
    withdrawals = await sum_by_txn_type(db, "cashfree_withdrawal", start, end)
    fees        = await sum_by_txn_type(db, "fee", start, end)
    tax         = await sum_by_txn_type(db, "tax", start, end)
    forex_pnl   = await sum_by_txn_type(db, "forex_pnl", start, end)
    gold_buy    = await sum_by_txn_type(db, "gold_buy", start, end)
    gold_sell   = await sum_by_txn_type(db, "gold_sell", start, end)
    mf_buy      = await sum_by_txn_type(db, "mutual_fund_buy", start, end)
    mf_redeem   = await sum_by_txn_type(db, "mutual_fund_redeem", start, end)
    referral    = await sum_by_txn_type(db, "referral_bonus", start, end)
    cashback    = await sum_by_txn_type(db, "cashback", start, end)
    admin_adj   = await sum_by_txn_type(db, "admin_adjustment", start, end)

    # Wallet balance total (from denorm ledger)
    wallet_pipeline = [
        {"$match": {"coa_root": "assets", "account": {"$regex": "^assets:user_wallet:"}}},
        {"$group": {"_id": None, "total": {"$sum": "$balance"}}},
    ]
    doc = await db.finance_ledger_balances.aggregate(wallet_pipeline).to_list(1)
    total_wallet_balance = float(doc[0]["total"]) if doc else 0.0

    # Provider balances
    provider_balances: Dict[str, float] = {}
    async for b in db.finance_ledger_balances.find(
        {"account": {"$regex": "^assets:provider:"}}, {"_id": 0}
    ):
        prov = b["account"].split(":")[-1]
        provider_balances[prov] = float(b["balance"])

    # Platform liability (should ~= total_wallet_balance)
    liab = await db.finance_ledger_balances.find_one(
        {"account": "liab:users_wallets"}, {"_id": 0, "balance": 1}
    )
    platform_liability = float((liab or {}).get("balance", 0.0))

    # Pending / failed withdrawals count
    pending_wd = await db.withdrawal_requests.count_documents(
        {"status": {"$in": ["pending", "under_review", "approved", "processing"]}}
    )
    failed_pay = await db.payments_orders.count_documents({"status": "failed"})
    pending_settle = await db.withdrawal_requests.count_documents(
        {"status": "approved"}
    )

    # Provider status — best-effort ping via last settlement/txn timestamp
    razorpay_last = await db.payments_orders.find_one(
        {"status": "captured"}, {"_id": 0, "captured_at": 1},
        sort=[("captured_at", -1)],
    )
    cashfree_last = await db.withdrawal_settlements.find_one(
        {}, {"_id": 0, "created_at": 1},
        sort=[("created_at", -1)],
    ) if "withdrawal_settlements" in await db.list_collection_names() else None

    def _status(last_seen: Optional[datetime]) -> str:
        if not last_seen:
            return "unknown"
        if isinstance(last_seen, dict):
            last_seen = list(last_seen.values())[0]
        try:
            if last_seen and last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            hours_since = (_now() - last_seen).total_seconds() / 3600
            if hours_since < 24:
                return "healthy"
            if hours_since < 168:
                return "idle"
            return "stale"
        except Exception:
            return "unknown"

    # Net revenue: fees + forex_pnl - referral - cashback - admin_adj (neg side)
    net_revenue = fees["amount"] + forex_pnl["amount"] \
                    - referral["amount"] - cashback["amount"]

    # Daily deposit / withdrawal chart data (for the dashboard)
    days = min(30, max(1, int((end - start).days) + 1))
    per_day_deposits = await _daily_series(db, "razorpay_deposit", start, end)
    per_day_withdrawals = await _daily_series(db, "cashfree_withdrawal", start, end)

    return {
        "range": {"key": range_key, "start": start, "end": end},
        "kpis": {
            "total_deposits": deposits,
            "total_withdrawals": withdrawals,
            "wallet_balance": round(total_wallet_balance, 2),
            "platform_liability": round(platform_liability, 2),
            "provider_balance": provider_balances,
            "todays_revenue": round(fees["amount"] + forex_pnl["amount"], 2),
            "fees": fees, "gst": tax,
            "refunds": admin_adj,   # closest proxy — refunds usually posted as admin_adjustment
            "failed_payments": failed_pay,
            "pending_withdrawals": pending_wd,
            "pending_settlements": pending_settle,
            "net_revenue": round(net_revenue, 2),
        },
        "breakdown": {
            "gold_buy": gold_buy, "gold_sell": gold_sell,
            "mutual_fund_buy": mf_buy, "mutual_fund_redeem": mf_redeem,
            "forex_pnl": forex_pnl,
            "referral": referral, "cashback": cashback,
            "admin_adjustment": admin_adj,
        },
        "providers": {
            "razorpay": {"status": _status(razorpay_last.get("captured_at") if razorpay_last else None),
                          "last_seen": razorpay_last.get("captured_at") if razorpay_last else None},
            "cashfree": {"status": _status(cashfree_last.get("created_at") if cashfree_last else None),
                          "last_seen": cashfree_last.get("created_at") if cashfree_last else None},
        },
        "charts": {
            "deposits_vs_withdrawals": {
                "deposits": per_day_deposits,
                "withdrawals": per_day_withdrawals,
            },
        },
    }


async def _daily_series(db, txn_type: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    pipeline = [
        {"$match": {"txn_type": txn_type, "is_reversed": {"$ne": True},
                     "entry_date": {"$gte": start, "$lte": end}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$entry_date"}},
            "amount": {"$sum": "$amount"}, "count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    rows = await db.finance_journal.aggregate(pipeline).to_list(1000)
    return [{"date": r["_id"], "amount": round(float(r["amount"]), 2),
              "count": int(r["count"])} for r in rows]


# =============================================================== reports ==
async def build_report_data(db, report_type: str,
                              start: datetime, end: datetime,
                              *, provider: Optional[str] = None,
                              module: Optional[str] = None,
                              user_id: Optional[str] = None,
                              status: Optional[str] = None) -> Dict[str, Any]:
    """Aggregate data for a finance report. The same shape is fed into the
    PDF / Excel / CSV renderers."""
    filt: Dict[str, Any] = {
        "entry_date": {"$gte": start, "$lte": end},
        "is_reversed": {"$ne": True},
    }
    if provider:
        filt["metadata.provider"] = provider
    if user_id:
        filt["user_id"] = user_id
    if module:
        filt["reference_type"] = module

    type_map = {
        "deposit": "razorpay_deposit",
        "withdrawal": "cashfree_withdrawal",
        "gold": "gold_buy",   # buys are the accounting event
        "mf": "mutual_fund_buy",
        "forex": "forex_pnl",
        "fees": "fee",
        "tax": "tax",
    }
    txn = type_map.get(report_type)
    if txn:
        filt["txn_type"] = txn

    entries = await db.finance_journal.find(filt, {"_id": 0}).sort("entry_date", 1).to_list(10_000)

    # Summary KPIs (always over the whole range, ignoring filter type — for executive summary)
    dashboard = await compute_dashboard(db, "custom", date_from=start, date_to=end)

    # Reconciliation summary (latest snapshot)
    recon_pipeline = [{"$group": {"_id": {"module": "$module", "status": "$status"},
                                    "count": {"$sum": 1}}}]
    recon_rows = await db.finance_reconciliation.aggregate(recon_pipeline).to_list(1000)
    recon_summary: Dict[str, Dict[str, int]] = {}
    for r in recon_rows:
        mod = r["_id"]["module"]; st = r["_id"]["status"]
        recon_summary.setdefault(mod, {})[st] = r["count"]

    # Settlement summary
    settle_summary = await _settlement_summary(db)

    return {
        "report_type": report_type,
        "range": {"start": start, "end": end},
        "filters": {"provider": provider, "module": module,
                     "user_id": user_id, "status": status},
        "generated_at": _now(),
        "executive_summary": dashboard["kpis"],
        "breakdown": dashboard["breakdown"],
        "entries": entries,
        "entry_count": len(entries),
        "total_amount": round(sum(float(e["amount"]) for e in entries), 2),
        "reconciliation_summary": recon_summary,
        "settlement_summary": settle_summary,
    }


async def _settlement_summary(db) -> Dict[str, Any]:
    rz_pipeline = [
        {"$match": {"status": "captured"}},
        {"$group": {"_id": None, "count": {"$sum": 1},
                     "amount_paise": {"$sum": "$amount_paise"}}},
    ]
    rz_doc = await db.payments_orders.aggregate(rz_pipeline).to_list(1)
    rz = {"count": rz_doc[0]["count"] if rz_doc else 0,
           "amount": round((rz_doc[0]["amount_paise"] if rz_doc else 0) / 100, 2)}

    cf = {"count": 0, "amount": 0.0}
    if "withdrawal_settlements" in await db.list_collection_names():
        cf_pipeline = [
            {"$match": {"status": "success"}},
            {"$group": {"_id": None, "count": {"$sum": 1},
                         "amount": {"$sum": "$amount"}}},
        ]
        cf_doc = await db.withdrawal_settlements.aggregate(cf_pipeline).to_list(1)
        if cf_doc:
            cf = {"count": cf_doc[0]["count"], "amount": round(float(cf_doc[0]["amount"]), 2)}

    return {"razorpay": rz, "cashfree": cf}


# =============================================================== settlements
async def provider_settlements(db, provider: str, *,
                                 limit: int = 100, skip: int = 0,
                                 date_from: Optional[datetime] = None,
                                 date_to: Optional[datetime] = None) -> Dict[str, Any]:
    """Provider-wise settlement list.

    Razorpay: from `payments_orders` (captured) + payments_reconciliation collection if present.
    Cashfree: from `withdrawal_settlements`.
    """
    provider = provider.lower()
    if provider == "razorpay":
        q: Dict[str, Any] = {"status": "captured"}
        if date_from or date_to:
            q["captured_at"] = {}
            if date_from: q["captured_at"]["$gte"] = date_from
            if date_to:   q["captured_at"]["$lte"] = date_to
        total = await db.payments_orders.count_documents(q)
        cur = db.payments_orders.find(q, {"_id": 0}).sort("captured_at", -1)\
                                 .skip(skip).limit(limit)
        rows = []
        async for o in cur:
            rows.append({
                "settlement_id": o.get("provider_order_id") or o.get("order_id"),
                "reference_id": o.get("order_id"),
                "user_id": o.get("user_id"),
                "amount": round((o.get("amount_paise", 0) or 0) / 100, 2),
                "date": o.get("captured_at") or o.get("created_at"),
                "status": o.get("status"),
                "fees": 0.0, "gst": 0.0,
                "utr": o.get("provider_payment_id"),
                "delay_hours": _delay_hours(o.get("created_at"), o.get("captured_at")),
                "provider": "razorpay",
            })
        return {"items": rows, "total": total, "provider": "razorpay"}
    if provider == "cashfree":
        if "withdrawal_settlements" not in await db.list_collection_names():
            return {"items": [], "total": 0, "provider": "cashfree"}
        q = {}
        if date_from or date_to:
            q["created_at"] = {}
            if date_from: q["created_at"]["$gte"] = date_from
            if date_to:   q["created_at"]["$lte"] = date_to
        total = await db.withdrawal_settlements.count_documents(q)
        rows = []
        async for s in db.withdrawal_settlements.find(q, {"_id": 0})\
                          .sort("created_at", -1).skip(skip).limit(limit):
            rows.append({
                "settlement_id": s.get("settlement_id"),
                "reference_id": s.get("withdrawal_id"),
                "user_id": s.get("user_id"),
                "amount": round(float(s.get("amount", 0)), 2),
                "date": s.get("created_at"),
                "status": s.get("status"),
                "fees": 0.0, "gst": 0.0,
                "utr": s.get("utr"),
                "delay_hours": None,
                "provider": s.get("provider") or "cashfree",
            })
        return {"items": rows, "total": total, "provider": "cashfree"}
    raise ValueError(f"unknown provider: {provider}")


def _delay_hours(created_at: Optional[datetime], settled_at: Optional[datetime]) -> Optional[float]:
    if not created_at or not settled_at:
        return None
    try:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if settled_at.tzinfo is None:
            settled_at = settled_at.replace(tzinfo=timezone.utc)
        return round((settled_at - created_at).total_seconds() / 3600, 2)
    except Exception:
        return None
