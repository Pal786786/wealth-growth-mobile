"""Mutual Fund Engine — Sprint 11.

Core responsibilities:
    * Fund catalog & explorer (search, filters, comparison)
    * NAV history (chart windows: 1M/3M/6M/1Y/3Y/5Y/MAX)
    * Order lifecycle: created → pending_payment → processing → allocated → completed → failed → redeemed
    * SIP CRUD + state machine (active/paused/cancelled/failed/completed) + execute-due + retry policy
    * Portfolio (XIRR, CAGR, absolute, Daily/Weekly/Monthly P/L, allocations)
    * Goal planning (SIP required, ETA, progress %)
    * Watchlist / favorites
    * Notifications fan-out (reuse notifications collection)
    * Redemption with KYC gate (per config)
    * Admin dashboard + KPIs
"""
from __future__ import annotations
import asyncio
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .providers import get_provider, MockMFProvider, AMFIProvider, PROVIDER_REGISTRY
from . import seed as seedmod

logger = logging.getLogger("mutual_funds.engine")

# Collections
FUNDS = "mf_funds"
NAV_HIST = "mf_nav_history"
INVESTMENTS = "mf_investments"       # Lumpsum orders
SIPS = "mf_sips"                      # SIP subscription docs
SIP_EXECS = "mf_sip_executions"       # each SIP execution attempt
HOLDINGS = "mf_holdings"              # aggregated per (user, fund)
GOALS = "mf_goals"
WATCHLIST = "mf_watchlist"
CONFIG_COLL = "mf_config"
AUDIT = "mf_audit_log"

DEFAULT_CONFIG = {
    "provider": "mock",
    "min_lumpsum_inr": 500.0,
    "min_sip_inr": 500.0,
    "sip_retry_max": 3,
    "sip_retry_hours": 24,
    "redemption_kyc_required": True,
    "maintenance_mode": False,
    "platform_fee_bps": 0,
    "nav_sync_interval_hours": 6,
}


CATEGORIES = ["equity", "debt", "hybrid", "index", "elss", "international",
              "gold", "liquid", "small_cap", "mid_cap", "large_cap"]

VALID_SIP_STATUS = {"active", "paused", "cancelled", "failed", "completed"}
VALID_ORDER_STATUS = {"created", "pending_payment", "processing", "allocated",
                      "completed", "failed", "redeemed"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: Dict[str, Any]) -> Dict[str, Any]:
    d.pop("_id", None)
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return d


def _uid(p: str) -> str: return f"{p}_{uuid.uuid4().hex[:12]}"


def _cagr(final: float, initial: float, years: float) -> Optional[float]:
    if initial <= 0 or years <= 0:
        return None
    try:
        return ((final / initial) ** (1.0 / years) - 1.0) * 100.0
    except Exception:
        return None


def _xirr(flows: List[Tuple[datetime, float]]) -> Optional[float]:
    """Compute XIRR (annualised) via bisection. flows[i] = (date, amount);
    outflows (investments) are negative, inflows (redemptions + current value) positive.
    Returns percentage, e.g. 12.5 for 12.5% p.a., or None if not converging."""
    if not flows or len(flows) < 2:
        return None
    t0 = min(f[0] for f in flows)

    def npv(rate: float) -> float:
        s = 0.0
        for d, a in flows:
            yrs = (d - t0).total_seconds() / (365.25 * 86400)
            s += a / ((1 + rate) ** yrs)
        return s

    lo, hi = -0.99, 5.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        # no sign change → root not bracketed
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        v = npv(mid)
        if abs(v) < 1e-6:
            return mid * 100.0
        if v * f_lo < 0:
            hi, f_hi = mid, v
        else:
            lo, f_lo = mid, v
    return ((lo + hi) / 2) * 100.0


class MutualFundEngine:
    def __init__(self, db):
        self.db = db
        self.config: Dict[str, Any] = dict(DEFAULT_CONFIG)

    # ---------------- lifecycle ---------------- #
    async def init_config(self):
        doc = await self.db[CONFIG_COLL].find_one({"_id": "active"}) or {}
        for k, v in doc.items():
            if k != "_id":
                self.config[k] = v
        await self.db[CONFIG_COLL].update_one(
            {"_id": "active"},
            {"$setOnInsert": {**self.config, "created_at": _now()}},
            upsert=True)
        await self._ensure_indexes()

    async def _ensure_indexes(self):
        """Production-grade indexes for hot query paths (stabilization sprint)."""
        try:
            await self.db[FUNDS].create_index("fund_id", unique=True)
            await self.db[FUNDS].create_index("scheme_code", unique=True)
            await self.db[FUNDS].create_index([("category", 1), ("aum_cr", -1)])
            await self.db[FUNDS].create_index([("amc", 1)])
            await self.db[FUNDS].create_index([("star_rating", -1)])
            await self.db[NAV_HIST].create_index([("fund_id", 1), ("as_of", 1)])
            await self.db[INVESTMENTS].create_index("order_id", unique=True)
            await self.db[INVESTMENTS].create_index([("user_id", 1), ("created_at", -1)])
            await self.db[INVESTMENTS].create_index([("user_id", 1), ("idempotency_key", 1)], sparse=True)
            await self.db[INVESTMENTS].create_index("status")
            await self.db[SIPS].create_index("sip_id", unique=True)
            await self.db[SIPS].create_index([("user_id", 1), ("status", 1)])
            await self.db[SIPS].create_index([("status", 1), ("next_run_at", 1)])
            await self.db[SIP_EXECS].create_index("exec_id", unique=True)
            await self.db[SIP_EXECS].create_index([("sip_id", 1), ("attempted_at", -1)])
            await self.db[SIP_EXECS].create_index([("user_id", 1), ("attempted_at", -1)])
            await self.db[HOLDINGS].create_index([("user_id", 1), ("fund_id", 1)], unique=True)
            await self.db[HOLDINGS].create_index("user_id")
            await self.db[GOALS].create_index("goal_id", unique=True)
            await self.db[GOALS].create_index([("user_id", 1), ("created_at", -1)])
            await self.db[WATCHLIST].create_index([("user_id", 1), ("fund_id", 1)], unique=True)
        except Exception as e:
            logger.warning("mf index creation warning: %s", e)

    async def count_funds(self) -> int:
        return await self.db[FUNDS].count_documents({})

    async def seed_if_needed(self):
        if await self.count_funds() > 0:
            return
        funds = seedmod.build_seed()
        await self.db[FUNDS].insert_many(funds)
        # NAV history — 400 days for each fund
        nav_docs: List[Dict[str, Any]] = []
        for f in funds:
            nav_docs.extend(seedmod.build_nav_history(f, days=400))
        if nav_docs:
            await self.db[NAV_HIST].insert_many(nav_docs)
        logger.info("mutual_funds seeded %d funds + %d nav rows", len(funds), len(nav_docs))

    # ---------------- funds / explorer ---------------- #
    async def list_funds(self, *, q: Optional[str] = None, amc: Optional[str] = None,
                          category: Optional[str] = None, risk: Optional[str] = None,
                          min_rating: Optional[int] = None,
                          sort: str = "aum_desc",
                          limit: int = 50, skip: int = 0) -> Dict[str, Any]:
        filt: Dict[str, Any] = {}
        if q:
            filt["$or"] = [{"name": {"$regex": q, "$options": "i"}},
                           {"amc": {"$regex": q, "$options": "i"}},
                           {"scheme_code": {"$regex": q, "$options": "i"}}]
        if amc: filt["amc"] = amc
        if category: filt["category"] = category
        if risk: filt["risk"] = risk
        if min_rating: filt["star_rating"] = {"$gte": int(min_rating)}
        total = await self.db[FUNDS].count_documents(filt)
        sort_map = {
            "aum_desc": [("aum_cr", -1)],
            "aum_asc":  [("aum_cr",  1)],
            "return_1y_desc": [("returns.y1", -1)],
            "return_1y_asc":  [("returns.y1",  1)],
            "return_3y_desc": [("returns.y3", -1)],
            "return_5y_desc": [("returns.y5", -1)],
            "expense_asc":    [("expense_ratio", 1)],
            "name_asc":       [("name", 1)],
            "rating_desc":    [("star_rating", -1)],
        }
        sort_by = sort_map.get(sort, sort_map["aum_desc"])
        cur = self.db[FUNDS].find(filt, {"_id": 0, "holdings": 0, "sector_allocation": 0,
                                          "documents": 0}).sort(sort_by).skip(skip).limit(limit)
        items = [_iso(d) async for d in cur]
        return {"items": items, "total": total}

    async def get_fund(self, fund_id: str) -> Optional[Dict[str, Any]]:
        f = await self.db[FUNDS].find_one({"fund_id": fund_id}, {"_id": 0})
        return _iso(f) if f else None

    async def get_fund_by_code(self, scheme_code: str) -> Optional[Dict[str, Any]]:
        f = await self.db[FUNDS].find_one({"scheme_code": scheme_code}, {"_id": 0})
        return _iso(f) if f else None

    async def nav_history(self, fund_id: str, window: str) -> List[Dict[str, Any]]:
        buckets = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365, "3Y": 365 * 3,
                    "5Y": 365 * 5, "MAX": 3650}
        d = buckets.get(window.upper(), 30)
        since = _now() - timedelta(days=d)
        cur = self.db[NAV_HIST].find({"fund_id": fund_id, "as_of": {"$gte": since}},
                                      {"_id": 0}).sort("as_of", 1)
        return [_iso(x) async for x in cur]

    async def amcs(self) -> List[str]:
        return sorted(await self.db[FUNDS].distinct("amc"))

    async def compare(self, fund_ids: List[str]) -> List[Dict[str, Any]]:
        if not fund_ids: return []
        cur = self.db[FUNDS].find({"fund_id": {"$in": fund_ids[:4]}}, {"_id": 0})
        return [_iso(d) async for d in cur]

    # ---------------- Watchlist ---------------- #
    async def watchlist_add(self, user_id: str, fund_id: str) -> Dict[str, Any]:
        fund = await self.get_fund(fund_id)
        if not fund: raise ValueError("fund not found")
        await self.db[WATCHLIST].update_one(
            {"user_id": user_id, "fund_id": fund_id},
            {"$setOnInsert": {"user_id": user_id, "fund_id": fund_id, "added_at": _now()}},
            upsert=True)
        return {"ok": True, "fund_id": fund_id}

    async def watchlist_remove(self, user_id: str, fund_id: str):
        await self.db[WATCHLIST].delete_one({"user_id": user_id, "fund_id": fund_id})
        return {"ok": True}

    async def watchlist(self, user_id: str) -> List[Dict[str, Any]]:
        cur = self.db[WATCHLIST].find({"user_id": user_id}, {"_id": 0})
        wl = [d async for d in cur]
        ids = [w["fund_id"] for w in wl]
        if not ids: return []
        fcur = self.db[FUNDS].find({"fund_id": {"$in": ids}}, {"_id": 0, "holdings": 0,
                                                                 "sector_allocation": 0, "documents": 0})
        funds = {f["fund_id"]: _iso(f) async for f in fcur}
        return [{**funds[w["fund_id"]], "added_at": w["added_at"].isoformat()}
                for w in wl if w["fund_id"] in funds]

    # ---------------- Investment / order lifecycle ---------------- #
    def _validate_order_status(self, status: str):
        if status not in VALID_ORDER_STATUS:
            raise ValueError(f"invalid status {status}")

    async def _debit_wallet(self, user_id: str, amount: float, description: str,
                             ref_id: str, category: str = "mutual_funds"):
        w = await self.db.wallets.find_one({"user_id": user_id}, {"balance": 1}) or {}
        bal = float(w.get("balance") or 0)
        if bal < amount:
            raise ValueError(f"insufficient wallet balance ₹{bal:.2f} < ₹{amount:.2f}")
        await self.db.wallets.update_one(
            {"user_id": user_id}, {"$inc": {"balance": -amount}}, upsert=True)
        try:
            await self.db.wallet_transactions.insert_one({
                "tx_id": _uid("tx"), "user_id": user_id, "kind": "debit",
                "category": category, "amount": amount, "description": description,
                "status": "success", "ref_id": ref_id, "created_at": _now()})
        except Exception: pass

    async def _credit_wallet(self, user_id: str, amount: float, description: str,
                              ref_id: str, category: str = "mutual_funds"):
        await self.db.wallets.update_one(
            {"user_id": user_id}, {"$inc": {"balance": amount}}, upsert=True)
        try:
            await self.db.wallet_transactions.insert_one({
                "tx_id": _uid("tx"), "user_id": user_id, "kind": "credit",
                "category": category, "amount": amount, "description": description,
                "status": "success", "ref_id": ref_id, "created_at": _now()})
        except Exception: pass

    async def _notify(self, user_id: str, title: str, body: str, kind: str, meta: Dict[str, Any]):
        try:
            await self.db.notifications.insert_one({
                "notif_id": _uid("nf"), "user_id": user_id, "title": title, "body": body,
                "read": False, "created_at": _now(),
                "deeplink": meta.get("deeplink", "/mutual-funds"),
                "category": kind, "metadata": meta})
        except Exception: pass

    async def _audit(self, actor_id: str, actor_type: str, action: str,
                      target_id: str = "", after: Optional[Dict[str, Any]] = None):
        try:
            await self.db[AUDIT].insert_one({
                "audit_id": _uid("aug"), "actor_id": actor_id, "actor_type": actor_type,
                "action": action, "target_id": target_id, "after": after or {}, "at": _now()})
        except Exception: pass

    async def invest_lumpsum(self, user_id: str, fund_id: str, amount: float,
                              idempotency_key: Optional[str] = None,
                              goal_id: Optional[str] = None,
                              payment_source: str = "wallet") -> Dict[str, Any]:
        """Full order lifecycle in one call (wallet payment). Non-wallet paths would
        park the order at pending_payment until webhook completion."""
        if self.config.get("maintenance_mode"):
            raise ValueError("mutual funds trading is under maintenance")
        amount = round(float(amount), 2)
        if amount < float(self.config["min_lumpsum_inr"]):
            raise ValueError(f"minimum lumpsum is ₹{self.config['min_lumpsum_inr']}")
        fund = await self.get_fund(fund_id)
        if not fund: raise ValueError("fund not found")
        if idempotency_key:
            existing = await self.db[INVESTMENTS].find_one(
                {"user_id": user_id, "idempotency_key": idempotency_key}, {"_id": 0})
            if existing:
                return _iso(existing)

        order_id = _uid("mfo")
        nav = float(fund["current_nav"])
        units = round(amount / nav, 4)

        order = {
            "order_id": order_id, "user_id": user_id, "fund_id": fund_id,
            "scheme_code": fund["scheme_code"], "fund_name": fund["name"],
            "kind": "lumpsum", "amount": amount, "units": units, "nav": nav,
            "payment_source": payment_source, "goal_id": goal_id,
            "idempotency_key": idempotency_key,
            "status": "created", "status_history": [{"status": "created", "at": _now()}],
            "created_at": _now(), "updated_at": _now(),
        }
        await self.db[INVESTMENTS].insert_one(order)

        # 2. Pending payment
        await self._patch_order(order_id, status="pending_payment")

        # 3. Debit wallet (or fail here)
        try:
            await self._debit_wallet(user_id, amount, f"MF Lumpsum: {fund['name']}", order_id)
        except ValueError as e:
            await self._patch_order(order_id, status="failed", extra={"failure_reason": str(e)})
            raise

        # 4. Processing
        await self._patch_order(order_id, status="processing")

        # 5. Allocated + create/update holdings
        await self._patch_order(order_id, status="allocated", extra={"units_allocated": units, "nav_used": nav})
        await self._apply_holding(user_id, fund_id, fund, units, amount, nav, cashflow_kind="buy")

        # 6. Completed
        await self._patch_order(order_id, status="completed")

        final = await self.db[INVESTMENTS].find_one({"order_id": order_id}, {"_id": 0})
        await self._notify(user_id, "🎯 Investment successful",
                            f"₹{amount:,.0f} invested in {fund['name']} · {units} units @ NAV ₹{nav}",
                            "investments", {"order_id": order_id, "fund_id": fund_id,
                                                "deeplink": f"/mutual-funds/{fund_id}"})
        await self._audit(user_id, "user", "mf.invest.lumpsum", order_id,
                          after={"amount": amount, "units": units, "nav": nav})
        return _iso(final or order)

    async def _patch_order(self, order_id: str, status: Optional[str] = None,
                            extra: Optional[Dict[str, Any]] = None):
        if status: self._validate_order_status(status)
        upd: Dict[str, Any] = {"updated_at": _now()}
        if status: upd["status"] = status
        if extra: upd.update(extra)
        push = {"status_history": {"status": status, "at": _now()}} if status else {}
        await self.db[INVESTMENTS].update_one({"order_id": order_id},
                                                {"$set": upd,
                                                 **({"$push": push} if push else {})})

    async def _apply_holding(self, user_id: str, fund_id: str, fund: Dict[str, Any],
                              units: float, amount: float, nav: float,
                              cashflow_kind: str):
        h = await self.db[HOLDINGS].find_one({"user_id": user_id, "fund_id": fund_id}) or {}
        prev_units = float(h.get("units") or 0)
        prev_invested = float(h.get("total_invested") or 0)
        if cashflow_kind == "buy":
            new_units = round(prev_units + units, 4)
            new_invested = round(prev_invested + amount, 2)
        else:  # redeem
            new_units = round(prev_units - units, 4)
            proportion = (units / prev_units) if prev_units else 0
            new_invested = round(prev_invested * (1 - proportion), 2)
        avg_nav = round(new_invested / new_units, 4) if new_units > 0 else 0.0
        flows = h.get("cashflows") or []
        flows.append({"date": _now(), "amount": (-amount if cashflow_kind == "buy" else amount),
                       "units": (units if cashflow_kind == "buy" else -units), "nav": nav})
        await self.db[HOLDINGS].update_one(
            {"user_id": user_id, "fund_id": fund_id},
            {"$set": {"user_id": user_id, "fund_id": fund_id,
                       "fund_name": fund["name"], "amc": fund["amc"],
                       "category": fund["category"], "risk": fund["risk"],
                       "units": new_units, "total_invested": new_invested,
                       "avg_nav": avg_nav, "cashflows": flows[-200:],
                       "updated_at": _now()}},
            upsert=True)

    # ---------------- SIP ---------------- #
    async def create_sip(self, user_id: str, fund_id: str, amount: float,
                          day_of_month: int = 5, frequency: str = "monthly",
                          goal_id: Optional[str] = None,
                          payment_source: str = "wallet") -> Dict[str, Any]:
        if self.config.get("maintenance_mode"):
            raise ValueError("mutual funds trading is under maintenance")
        amount = round(float(amount), 2)
        if amount < float(self.config["min_sip_inr"]):
            raise ValueError(f"minimum SIP is ₹{self.config['min_sip_inr']}")
        if frequency not in ("monthly", "weekly", "quarterly"):
            raise ValueError("frequency must be monthly | weekly | quarterly")
        if not 1 <= day_of_month <= 28:
            raise ValueError("day_of_month must be 1..28")
        fund = await self.get_fund(fund_id)
        if not fund: raise ValueError("fund not found")
        sip = {
            "sip_id": _uid("sip"), "user_id": user_id, "fund_id": fund_id,
            "scheme_code": fund["scheme_code"], "fund_name": fund["name"],
            "amount": amount, "day_of_month": day_of_month, "frequency": frequency,
            "goal_id": goal_id, "payment_source": payment_source,
            "status": "active", "retry_count": 0,
            "created_at": _now(), "updated_at": _now(),
            "next_run_at": self._next_run(day_of_month, frequency),
            "start_date": _now(),
            "last_execution_at": None, "success_count": 0, "failure_count": 0,
        }
        await self.db[SIPS].insert_one(sip)
        await self._notify(user_id, "📅 SIP scheduled",
                            f"₹{amount:,.0f} · {frequency} · {fund['name']} · runs {day_of_month} of month",
                            "sip",
                            {"sip_id": sip["sip_id"], "deeplink": "/mutual-funds/sips"})
        await self._audit(user_id, "user", "mf.sip.create", sip["sip_id"], after=sip)
        return _iso(sip)

    def _next_run(self, day_of_month: int, frequency: str) -> datetime:
        now = _now()
        if frequency == "monthly":
            year, month = now.year, now.month
            if now.day >= day_of_month:
                month += 1
                if month > 12: month, year = 1, year + 1
            return datetime(year, month, min(day_of_month, 28), 9, 0, tzinfo=timezone.utc)
        if frequency == "weekly":
            return now + timedelta(days=7)
        if frequency == "quarterly":
            return now + timedelta(days=90)
        return now + timedelta(days=30)

    async def modify_sip(self, user_id: str, sip_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        sip = await self.db[SIPS].find_one({"sip_id": sip_id, "user_id": user_id})
        if not sip: raise ValueError("SIP not found")
        allowed = {"amount", "day_of_month", "frequency"}
        set_fields = {k: v for k, v in patch.items() if k in allowed and v is not None}
        if not set_fields: return _iso({**sip, "_id": None}) if False else _iso({k: v for k, v in sip.items() if k != "_id"})
        if "amount" in set_fields:
            set_fields["amount"] = round(float(set_fields["amount"]), 2)
            if set_fields["amount"] < float(self.config["min_sip_inr"]):
                raise ValueError(f"minimum SIP is ₹{self.config['min_sip_inr']}")
        if "day_of_month" in set_fields:
            if not 1 <= int(set_fields["day_of_month"]) <= 28:
                raise ValueError("day_of_month must be 1..28")
            set_fields["next_run_at"] = self._next_run(int(set_fields["day_of_month"]),
                                                        set_fields.get("frequency", sip["frequency"]))
        set_fields["updated_at"] = _now()
        await self.db[SIPS].update_one({"sip_id": sip_id}, {"$set": set_fields})
        updated = await self.db[SIPS].find_one({"sip_id": sip_id}, {"_id": 0})
        await self._audit(user_id, "user", "mf.sip.modify", sip_id, after=set_fields)
        return _iso(updated or {})

    async def set_sip_status(self, user_id: str, sip_id: str, status: str) -> Dict[str, Any]:
        if status not in VALID_SIP_STATUS:
            raise ValueError(f"invalid status {status}")
        sip = await self.db[SIPS].find_one({"sip_id": sip_id, "user_id": user_id})
        if not sip: raise ValueError("SIP not found")
        await self.db[SIPS].update_one({"sip_id": sip_id},
                                         {"$set": {"status": status, "updated_at": _now()}})
        updated = await self.db[SIPS].find_one({"sip_id": sip_id}, {"_id": 0})
        await self._notify(user_id, f"SIP {status}", f"{sip['fund_name']} · ₹{sip['amount']:,.0f}", "sip",
                            {"sip_id": sip_id, "deeplink": "/mutual-funds/sips"})
        await self._audit(user_id, "user", f"mf.sip.{status}", sip_id, after={"status": status})
        return _iso(updated or {})

    async def list_sips(self, user_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        f: Dict[str, Any] = {"user_id": user_id}
        if status: f["status"] = status
        cur = self.db[SIPS].find(f, {"_id": 0}).sort("created_at", -1)
        return [_iso(d) async for d in cur]

    async def execute_due_sips(self, actor: str = "system", dry_run: bool = False) -> Dict[str, Any]:
        """Execute all SIPs whose next_run_at <= now. Returns summary."""
        due = self.db[SIPS].find({"status": "active", "next_run_at": {"$lte": _now()}}, {"_id": 0})
        summary = {"considered": 0, "success": 0, "failed": 0, "retried": 0, "results": []}
        async for sip in due:
            summary["considered"] += 1
            if dry_run:
                summary["results"].append({"sip_id": sip["sip_id"], "action": "would_run"})
                continue
            try:
                res = await self._execute_single_sip(sip)
                if res["ok"]:
                    summary["success"] += 1
                else:
                    summary["failed"] += 1
                    if res.get("will_retry"):
                        summary["retried"] += 1
                summary["results"].append({"sip_id": sip["sip_id"], **res})
            except Exception as e:
                summary["failed"] += 1
                summary["results"].append({"sip_id": sip["sip_id"], "ok": False, "error": str(e)})
        await self._audit(actor, "admin" if actor != "system" else "system",
                          "mf.sip.execute_due", after={"summary": {k: v for k, v in summary.items() if k != "results"}})
        return summary

    async def _execute_single_sip(self, sip: Dict[str, Any]) -> Dict[str, Any]:
        user_id = sip["user_id"]
        fund = await self.get_fund(sip["fund_id"])
        if not fund:
            await self.db[SIPS].update_one({"sip_id": sip["sip_id"]},
                                             {"$set": {"status": "failed",
                                                        "failure_reason": "fund not found",
                                                        "updated_at": _now()}})
            return {"ok": False, "reason": "fund not found"}
        amount = float(sip["amount"])
        nav = float(fund["current_nav"])
        units = round(amount / nav, 4)
        exec_id = _uid("sipx")
        exec_doc: Dict[str, Any] = {
            "exec_id": exec_id, "sip_id": sip["sip_id"], "user_id": user_id,
            "fund_id": sip["fund_id"], "amount": amount, "nav": nav, "units": units,
            "attempted_at": _now(), "status": "processing",
            "attempt": int(sip.get("retry_count", 0)) + 1,
        }
        await self.db[SIP_EXECS].insert_one(exec_doc)
        # Simulate wallet debit
        try:
            await self._debit_wallet(user_id, amount, f"SIP: {fund['name']}", exec_id)
        except ValueError as e:
            # Failure path: retry policy
            retry_count = int(sip.get("retry_count", 0)) + 1
            will_retry = retry_count < int(self.config["sip_retry_max"])
            next_run = _now() + timedelta(hours=int(self.config["sip_retry_hours"])) if will_retry else self._next_run(sip["day_of_month"], sip["frequency"])
            new_status = sip["status"] if will_retry else "failed"
            await self.db[SIPS].update_one({"sip_id": sip["sip_id"]},
                {"$set": {"retry_count": retry_count if will_retry else 0,
                           "next_run_at": next_run,
                           "status": new_status,
                           "failure_count": int(sip.get("failure_count", 0)) + 1,
                           "last_execution_at": _now(),
                           "last_failure_reason": str(e),
                           "updated_at": _now()}})
            await self.db[SIP_EXECS].update_one({"exec_id": exec_id},
                {"$set": {"status": "failed", "reason": str(e), "completed_at": _now()}})
            await self._notify(user_id, "⚠️ SIP failed",
                                f"{fund['name']} · ₹{amount:,.0f} · {str(e)}{' · Will retry.' if will_retry else ''}",
                                "sip",
                                {"sip_id": sip["sip_id"], "exec_id": exec_id, "deeplink": "/mutual-funds/sips"})
            return {"ok": False, "reason": str(e), "will_retry": will_retry, "retry_count": retry_count}

        # Success: allocate + advance
        await self._apply_holding(user_id, sip["fund_id"], fund, units, amount, nav, "buy")
        await self.db[SIP_EXECS].update_one({"exec_id": exec_id},
            {"$set": {"status": "completed", "completed_at": _now()}})
        await self.db[SIPS].update_one({"sip_id": sip["sip_id"]},
            {"$set": {"retry_count": 0,
                       "success_count": int(sip.get("success_count", 0)) + 1,
                       "last_execution_at": _now(),
                       "next_run_at": self._next_run(sip["day_of_month"], sip["frequency"]),
                       "updated_at": _now()}})
        await self._notify(user_id, "✅ SIP executed",
                            f"{fund['name']} · ₹{amount:,.0f} · {units} units @ NAV ₹{nav}",
                            "sip",
                            {"sip_id": sip["sip_id"], "exec_id": exec_id, "deeplink": "/mutual-funds/sips"})
        return {"ok": True, "exec_id": exec_id, "units": units}

    # ---------------- Redemption ---------------- #
    async def redeem(self, user_id: str, fund_id: str, units: float,
                      idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        units = round(float(units), 4)
        if units <= 0: raise ValueError("units must be > 0")
        if self.config.get("redemption_kyc_required"):
            kyc = await self.db.kyc_profiles.find_one({"user_id": user_id}) or {}
            if kyc.get("status") not in ("approved", "verified", "success"):
                raise ValueError("KYC approval required for redemption")
        h = await self.db[HOLDINGS].find_one({"user_id": user_id, "fund_id": fund_id})
        if not h or float(h.get("units") or 0) < units:
            raise ValueError(f"insufficient units held ({(h or {}).get('units', 0)})")
        fund = await self.get_fund(fund_id)
        if not fund: raise ValueError("fund not found")
        if idempotency_key:
            existing = await self.db[INVESTMENTS].find_one(
                {"user_id": user_id, "idempotency_key": idempotency_key, "kind": "redeem"},
                {"_id": 0})
            if existing: return _iso(existing)
        nav = float(fund["current_nav"])
        proceeds = round(units * nav, 2)
        avg = float(h.get("avg_nav") or 0)
        cost_basis = round(units * avg, 2)
        pnl = round(proceeds - cost_basis, 2)
        order_id = _uid("mfr")
        order = {
            "order_id": order_id, "user_id": user_id, "fund_id": fund_id,
            "scheme_code": fund["scheme_code"], "fund_name": fund["name"],
            "kind": "redeem", "amount": proceeds, "units": units, "nav": nav,
            "realized_pnl": pnl, "cost_basis": cost_basis,
            "idempotency_key": idempotency_key,
            "status": "created", "status_history": [{"status": "created", "at": _now()}],
            "created_at": _now(), "updated_at": _now(),
        }
        await self.db[INVESTMENTS].insert_one(order)
        await self._patch_order(order_id, status="processing")
        await self._apply_holding(user_id, fund_id, fund, units, proceeds, nav, "redeem")
        await self._credit_wallet(user_id, proceeds, f"MF Redemption: {fund['name']}", order_id)
        await self._patch_order(order_id, status="redeemed")
        await self._patch_order(order_id, status="completed")
        await self._notify(user_id, ("💰 Redemption profit" if pnl >= 0 else "💰 Redemption at loss"),
                            f"{fund['name']} · Received ₹{proceeds:,.0f} · P/L ₹{pnl:+,.0f}",
                            "investments",
                            {"order_id": order_id, "deeplink": f"/mutual-funds/{fund_id}"})
        await self._audit(user_id, "user", "mf.redeem", order_id,
                          after={"units": units, "proceeds": proceeds, "pnl": pnl})
        final = await self.db[INVESTMENTS].find_one({"order_id": order_id}, {"_id": 0})
        return _iso(final or order)

    # ---------------- Orders / Transactions ---------------- #
    async def user_orders(self, user_id: str, kind: Optional[str] = None,
                           limit: int = 100, skip: int = 0) -> List[Dict[str, Any]]:
        f: Dict[str, Any] = {"user_id": user_id}
        if kind in ("lumpsum", "redeem"): f["kind"] = kind
        cur = self.db[INVESTMENTS].find(f, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
        return [_iso(d) async for d in cur]

    async def sip_executions(self, user_id: str, sip_id: Optional[str] = None,
                              limit: int = 100) -> List[Dict[str, Any]]:
        f: Dict[str, Any] = {"user_id": user_id}
        if sip_id: f["sip_id"] = sip_id
        cur = self.db[SIP_EXECS].find(f, {"_id": 0}).sort("attempted_at", -1).limit(limit)
        return [_iso(d) async for d in cur]

    # ---------------- Portfolio & analytics ---------------- #
    async def portfolio(self, user_id: str) -> Dict[str, Any]:
        h_cur = self.db[HOLDINGS].find({"user_id": user_id, "units": {"$gt": 0.0001}},
                                        {"_id": 0})
        holdings: List[Dict[str, Any]] = [d async for d in h_cur]
        # Enrich with fund NAV + returns
        fund_ids = [h["fund_id"] for h in holdings]
        fmap: Dict[str, Dict[str, Any]] = {}
        if fund_ids:
            fcur = self.db[FUNDS].find({"fund_id": {"$in": fund_ids}}, {"_id": 0, "current_nav": 1,
                                                                            "fund_id": 1, "returns": 1,
                                                                            "amc": 1, "category": 1,
                                                                            "risk": 1, "name": 1})
            async for f in fcur:
                fmap[f["fund_id"]] = f

        total_invested = 0.0
        total_current = 0.0
        all_flows: List[Tuple[datetime, float]] = []
        by_amc: Dict[str, float] = {}
        by_cat: Dict[str, float] = {}
        by_risk: Dict[str, float] = {}
        by_asset: Dict[str, float] = {}
        enriched: List[Dict[str, Any]] = []

        for h in holdings:
            f = fmap.get(h["fund_id"]) or {}
            nav = float(f.get("current_nav") or h.get("avg_nav") or 0)
            units = float(h.get("units") or 0)
            invested = float(h.get("total_invested") or 0)
            current = round(units * nav, 2)
            pnl = round(current - invested, 2)
            pnl_pct = round((pnl / invested) * 100, 2) if invested else 0.0
            total_invested += invested
            total_current += current
            # Cashflows for XIRR
            for cf in (h.get("cashflows") or []):
                d = cf["date"] if isinstance(cf["date"], datetime) else datetime.fromisoformat(str(cf["date"]).replace("Z", "+00:00"))
                all_flows.append((d if d.tzinfo else d.replace(tzinfo=timezone.utc), float(cf["amount"])))
            amc = f.get("amc") or "Other"
            cat = f.get("category") or "other"
            risk = f.get("risk") or "moderate"
            by_amc[amc] = by_amc.get(amc, 0) + current
            by_cat[cat] = by_cat.get(cat, 0) + current
            by_risk[risk] = by_risk.get(risk, 0) + current
            asset = ("equity" if cat in ("equity", "large_cap", "mid_cap", "small_cap", "elss", "index", "international")
                     else "debt" if cat in ("debt", "liquid")
                     else "hybrid" if cat == "hybrid"
                     else "gold" if cat == "gold" else "other")
            by_asset[asset] = by_asset.get(asset, 0) + current
            enriched.append({
                **h, "current_nav": nav, "current_value": current,
                "unrealized_pnl": pnl, "unrealized_pnl_pct": pnl_pct,
                "returns_1y": (f.get("returns") or {}).get("y1"),
                "returns_3y": (f.get("returns") or {}).get("y3"),
            })

        # Add current value as positive flow for XIRR
        if total_current > 0:
            all_flows.append((_now(), total_current))
        xirr = _xirr(all_flows) if all_flows else None
        # Overall CAGR (needs first cashflow date)
        first_dt = min((f[0] for f in all_flows), default=None) if all_flows else None
        yrs = ((_now() - first_dt).total_seconds() / (365.25 * 86400)) if first_dt else 0
        cagr = _cagr(total_current, total_invested, yrs) if total_invested else None
        absolute = round(((total_current - total_invested) / total_invested) * 100, 2) if total_invested else 0.0

        # Period P/L (approx via nav_history)
        def _pl(days: int) -> float:
            past = _now() - timedelta(days=days)
            past_value = 0.0
            for h in holdings:
                fh = fmap.get(h["fund_id"]) or {}
                # look up nav then. Approx using return %
                r = (fh.get("returns") or {}).get({30: "m1", 90: "m3", 180: "m6", 1: "m1"}.get(days, "m1"))
                if r is None or fh.get("current_nav") is None:
                    continue
                past_nav = float(fh["current_nav"]) / (1 + (r / 100))
                past_value += float(h["units"]) * past_nav
            return round(total_current - past_value, 2) if past_value else 0.0

        # Weekly ≈ 7d; Monthly ≈ 30d
        daily_pl = _pl(1)
        weekly_pl = _pl(7)
        monthly_pl = _pl(30)

        # Top / worst performer
        for e in enriched:
            e["_perf"] = e["unrealized_pnl_pct"]
        top = max(enriched, key=lambda x: x["_perf"], default=None)
        worst = min(enriched, key=lambda x: x["_perf"], default=None)
        for e in enriched: e.pop("_perf", None)

        def _alloc_pct(d: Dict[str, float]) -> List[Dict[str, Any]]:
            total = sum(d.values()) or 1
            return [{"name": k, "value": round(v, 2), "pct": round(v / total * 100, 2)}
                    for k, v in sorted(d.items(), key=lambda kv: -kv[1])]

        return {
            "as_of": _now().isoformat(),
            "total_invested": round(total_invested, 2),
            "current_value": round(total_current, 2),
            "unrealized_pnl": round(total_current - total_invested, 2),
            "unrealized_pnl_pct": absolute,
            "xirr_pct": round(xirr, 2) if xirr is not None else None,
            "cagr_pct": round(cagr, 2) if cagr is not None else None,
            "absolute_return_pct": absolute,
            "daily_pl": daily_pl, "weekly_pl": weekly_pl, "monthly_pl": monthly_pl,
            "dividend_income": 0.0,  # future-ready
            "holdings": enriched,
            "allocations": {
                "asset": _alloc_pct(by_asset),
                "amc": _alloc_pct(by_amc),
                "category": _alloc_pct(by_cat),
                "risk": _alloc_pct(by_risk),
            },
            "top_performer": top, "worst_performer": worst,
            "count_funds": len(enriched),
        }

    # ---------------- Goals ---------------- #
    async def create_goal(self, user_id: str, name: str, kind: str, target_amount: float,
                           target_date: datetime, priority: str = "medium",
                           expected_return_pct: float = 12.0, linked_funds: Optional[List[str]] = None) -> Dict[str, Any]:
        target_amount = round(float(target_amount), 2)
        if target_amount <= 0: raise ValueError("target amount must be > 0")
        goal = {
            "goal_id": _uid("gol"),
            "user_id": user_id, "name": name, "kind": kind,
            "target_amount": target_amount, "target_date": target_date,
            "priority": priority,
            "expected_return_pct": float(expected_return_pct),
            "linked_funds": linked_funds or [],
            "created_at": _now(), "updated_at": _now(),
        }
        await self.db[GOALS].insert_one(goal)
        await self._audit(user_id, "user", "mf.goal.create", goal["goal_id"], after=goal)
        return _iso(goal)

    async def update_goal(self, user_id: str, goal_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {"name", "target_amount", "target_date", "priority",
                   "expected_return_pct", "linked_funds"}
        set_fields = {k: v for k, v in patch.items() if k in allowed and v is not None}
        if not set_fields: raise ValueError("nothing to update")
        set_fields["updated_at"] = _now()
        r = await self.db[GOALS].update_one({"goal_id": goal_id, "user_id": user_id},
                                              {"$set": set_fields})
        if r.matched_count == 0: raise ValueError("goal not found")
        g = await self.db[GOALS].find_one({"goal_id": goal_id}, {"_id": 0})
        await self._audit(user_id, "user", "mf.goal.update", goal_id, after=set_fields)
        return _iso(g or {})

    async def delete_goal(self, user_id: str, goal_id: str) -> Dict[str, Any]:
        r = await self.db[GOALS].delete_one({"goal_id": goal_id, "user_id": user_id})
        return {"ok": r.deleted_count > 0}

    async def list_goals(self, user_id: str) -> List[Dict[str, Any]]:
        cur = self.db[GOALS].find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1)
        goals = [d async for d in cur]
        # Enrich with progress
        port = await self.portfolio(user_id)
        pmap: Dict[str, Dict[str, Any]] = {}
        # allocate portfolio value to linked funds
        for h in port["holdings"]:
            pmap[h["fund_id"]] = h
        out = []
        for g in goals:
            current = 0.0
            for fid in g.get("linked_funds", []):
                if fid in pmap:
                    current += float(pmap[fid]["current_value"])
            remaining = max(0.0, float(g["target_amount"]) - current)
            progress = round((current / float(g["target_amount"])) * 100, 2) if g["target_amount"] else 0
            # Estimate SIP required
            tgt_dt = g["target_date"] if isinstance(g["target_date"], datetime) else datetime.fromisoformat(str(g["target_date"]).replace("Z", "+00:00"))
            tgt_dt = tgt_dt if tgt_dt.tzinfo else tgt_dt.replace(tzinfo=timezone.utc)
            months_left = max(1, int((tgt_dt - _now()).days / 30))
            r = float(g.get("expected_return_pct", 12.0)) / 100 / 12
            # FV of annuity: PMT = FV * r / ((1+r)^n - 1)
            try:
                required_sip = remaining * r / ((1 + r) ** months_left - 1) if r > 0 else remaining / months_left
            except Exception:
                required_sip = remaining / months_left
            out.append({**_iso(g),
                          "current_amount": round(current, 2),
                          "remaining_amount": round(remaining, 2),
                          "progress_pct": progress,
                          "months_left": months_left,
                          "required_monthly_sip": round(max(0, required_sip), 2),
                          "estimated_completion": tgt_dt.isoformat()})
        return out

    # ---------------- Admin: KPIs & analytics ---------------- #
    async def admin_dashboard(self) -> Dict[str, Any]:
        total_aum = await self.db[HOLDINGS].aggregate(
            [{"$group": {"_id": None, "invested": {"$sum": "$total_invested"}}}]).to_list(1)
        active_users = len(await self.db[HOLDINGS].distinct("user_id"))
        active_sips = await self.db[SIPS].count_documents({"status": "active"})
        paused_sips = await self.db[SIPS].count_documents({"status": "paused"})
        failed_sips = await self.db[SIPS].count_documents({"status": "failed"})
        total_orders = await self.db[INVESTMENTS].count_documents({})
        completed_orders = await self.db[INVESTMENTS].count_documents({"status": "completed"})
        pending_redemptions = await self.db[INVESTMENTS].count_documents({"kind": "redeem", "status": {"$in": ["created", "pending_payment", "processing"]}})
        # SIP success/failure rates
        sip_execs_total = await self.db[SIP_EXECS].count_documents({})
        sip_execs_success = await self.db[SIP_EXECS].count_documents({"status": "completed"})
        sip_execs_failed = await self.db[SIP_EXECS].count_documents({"status": "failed"})
        # AUM by AMC / category
        by_amc = await self.db[HOLDINGS].aggregate([
            {"$group": {"_id": "$amc", "invested": {"$sum": "$total_invested"}}},
            {"$sort": {"invested": -1}}, {"$limit": 8}]).to_list(8)
        by_cat = await self.db[HOLDINGS].aggregate([
            {"$group": {"_id": "$category", "invested": {"$sum": "$total_invested"}}},
            {"$sort": {"invested": -1}}]).to_list(20)
        # Top funds by invested value
        top_funds = await self.db[HOLDINGS].aggregate([
            {"$group": {"_id": {"fund_id": "$fund_id", "fund_name": "$fund_name"},
                         "invested": {"$sum": "$total_invested"},
                         "users": {"$addToSet": "$user_id"}}},
            {"$project": {"_id": 0, "fund_id": "$_id.fund_id",
                            "fund_name": "$_id.fund_name", "invested": 1,
                            "unique_users": {"$size": "$users"}}},
            {"$sort": {"invested": -1}}, {"$limit": 10}]).to_list(10)
        # Top SIPs
        top_sips = await self.db[SIPS].aggregate([
            {"$match": {"status": "active"}},
            {"$sort": {"amount": -1}}, {"$limit": 10},
            {"$project": {"_id": 0}}]).to_list(10)
        # Avg holding period
        cf_docs = self.db[HOLDINGS].find({"units": {"$gt": 0}}, {"_id": 0, "cashflows": 1})
        holdings_periods = []
        async for h in cf_docs:
            flows = h.get("cashflows") or []
            if flows:
                first = flows[0].get("date")
                if isinstance(first, datetime):
                    dt = first
                else:
                    try: dt = datetime.fromisoformat(str(first).replace("Z", "+00:00"))
                    except Exception: continue
                dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                holdings_periods.append((_now() - dt).days)
        avg_hold_days = round(sum(holdings_periods) / len(holdings_periods), 1) if holdings_periods else 0.0

        # Avg SIP amount, Avg investment size
        sip_avg = await self.db[SIPS].aggregate([{"$group": {"_id": None, "avg": {"$avg": "$amount"}}}]).to_list(1)
        inv_avg = await self.db[INVESTMENTS].aggregate([{"$match": {"kind": "lumpsum"}},
                                                          {"$group": {"_id": None, "avg": {"$avg": "$amount"}}}]).to_list(1)

        provider = get_provider(self.db, self.config["provider"])
        return {
            "config": self.config,
            "totals": {
                "aum": round((total_aum[0]["invested"] if total_aum else 0), 2),
                "active_investors": active_users,
                "total_funds": await self.count_funds(),
                "active_sips": active_sips, "paused_sips": paused_sips, "failed_sips": failed_sips,
                "total_orders": total_orders, "completed_orders": completed_orders,
                "pending_redemptions": pending_redemptions,
                "sip_success_rate": round((sip_execs_success / sip_execs_total) * 100, 2) if sip_execs_total else 0.0,
                "sip_failure_rate": round((sip_execs_failed / sip_execs_total) * 100, 2) if sip_execs_total else 0.0,
                "avg_sip_amount": round((sip_avg[0]["avg"] if sip_avg else 0), 2),
                "avg_investment_size": round((inv_avg[0]["avg"] if inv_avg else 0), 2),
                "avg_holding_days": avg_hold_days,
                "highest_aum_amc": (by_amc[0]["_id"] if by_amc else None),
                "fastest_growing_category": (by_cat[0]["_id"] if by_cat else None),
            },
            "by_amc": [{"name": r["_id"], "invested": round(r["invested"], 2)} for r in by_amc],
            "by_category": [{"name": r["_id"], "invested": round(r["invested"], 2)} for r in by_cat],
            "top_funds": top_funds, "top_sips": top_sips,
            "provider_status": {
                "active": provider.name, "real": getattr(provider, "real", False),
                "configured": provider.is_configured(),
                "registry": list(PROVIDER_REGISTRY),
                "last_sync": None,
            },
        }

    async def admin_orders(self, kind: Optional[str] = None,
                            status: Optional[str] = None,
                            user_id: Optional[str] = None,
                            limit: int = 200, skip: int = 0) -> List[Dict[str, Any]]:
        f: Dict[str, Any] = {}
        if kind: f["kind"] = kind
        if status: f["status"] = status
        if user_id: f["user_id"] = user_id
        cur = self.db[INVESTMENTS].find(f, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
        return [_iso(d) async for d in cur]

    async def admin_sips(self, status: Optional[str] = None,
                          limit: int = 200) -> List[Dict[str, Any]]:
        f = {"status": status} if status else {}
        cur = self.db[SIPS].find(f, {"_id": 0}).sort("created_at", -1).limit(limit)
        return [_iso(d) async for d in cur]

    async def admin_investors(self, limit: int = 200) -> List[Dict[str, Any]]:
        cur = self.db[HOLDINGS].aggregate([
            {"$group": {"_id": "$user_id",
                         "invested": {"$sum": "$total_invested"},
                         "funds": {"$sum": 1}}},
            {"$sort": {"invested": -1}}, {"$limit": limit},
            {"$project": {"_id": 0, "user_id": "$_id", "invested": 1, "funds": 1}}])
        return await cur.to_list(limit)

    async def upsert_fund(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        if "fund_id" in patch and patch["fund_id"]:
            await self.db[FUNDS].update_one({"fund_id": patch["fund_id"]},
                                              {"$set": {**patch, "updated_at": _now()}}, upsert=True)
            return await self.get_fund(patch["fund_id"]) or {}
        # New fund
        patch = {**patch, "fund_id": _uid("mf"), "created_at": _now(), "updated_at": _now()}
        await self.db[FUNDS].insert_one(patch)
        return await self.get_fund(patch["fund_id"]) or {}

    async def patch_config(self, patch: Dict[str, Any], admin_id: str) -> Dict[str, Any]:
        allowed = set(DEFAULT_CONFIG.keys())
        set_fields = {k: v for k, v in patch.items() if k in allowed and v is not None}
        if not set_fields: return self.config
        set_fields["updated_at"] = _now()
        await self.db[CONFIG_COLL].update_one({"_id": "active"}, {"$set": set_fields}, upsert=True)
        for k, v in set_fields.items():
            if k != "updated_at": self.config[k] = v
        await self._audit(admin_id, "admin", "mf.config.update", after=set_fields)
        return self.config
