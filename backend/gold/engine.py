"""Gold Investment Engine.

Holds config (provider, spread, min-buy, trading hours, maintenance), executes
buys / sells against the wallet, maintains holdings & P/L, records notifications
and audit logs.
"""
from __future__ import annotations
import asyncio
import logging
import random
import time
import uuid
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .providers import get_provider, MockGoldProvider, LiveMarketGoldProvider

logger = logging.getLogger("gold.engine")

CONFIG_COLL = "gold_config"
TX_COLL = "gold_transactions"
HOLDINGS_COLL = "gold_holdings"
AUDIT_COLL = "gold_audit_log"
PRICE_COLL = "gold_price_history"

DEFAULT_CONFIG = {
    "provider": "live_market",       # mock | live_market | augmont | mmtc_pamp | safegold
    "spread_bps": 200,               # 2% total spread → 100bps around mid on each side
    "min_buy_inr": 10.0,
    "max_buy_inr": 200000.0,
    "maintenance_mode": False,
    "trading_hours": {"open_utc": "00:00", "close_utc": "23:59"},  # 24/7 by default
    "manual_price_inr_per_gram": None,  # If set, overrides everything
    "gst_bps": 300,                  # 3% GST on purchases (informational)
    "maker_fee_bps": 50,             # 0.5%
    "redemption_kyc_required": True,
}


def _now():
    return datetime.now(timezone.utc)


def _iso(o):
    for k, v in list(o.items()):
        if isinstance(v, datetime):
            o[k] = (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return o


def _parse_hhmm(s: str) -> dtime:
    hh, mm = s.split(":")
    return dtime(int(hh), int(mm))


class GoldEngine:
    def __init__(self, db):
        self.db = db
        self.config: Dict[str, Any] = dict(DEFAULT_CONFIG)

    async def init_config(self):
        doc = await self.db[CONFIG_COLL].find_one({"_id": "active"})
        if doc:
            for k, v in doc.items():
                if k != "_id":
                    self.config[k] = v
        await self.db[CONFIG_COLL].update_one(
            {"_id": "active"}, {"$setOnInsert": {**self.config, "created_at": _now()}},
            upsert=True)

    async def patch_config(self, patch: Dict[str, Any], admin_id: str) -> Dict[str, Any]:
        allowed = {"provider", "spread_bps", "min_buy_inr", "max_buy_inr",
                    "maintenance_mode", "trading_hours",
                    "manual_price_inr_per_gram", "gst_bps", "maker_fee_bps",
                    "redemption_kyc_required"}
        set_fields = {k: v for k, v in patch.items() if k in allowed and v is not None}
        if not set_fields:
            return self.config
        set_fields["updated_at"] = _now()
        await self.db[CONFIG_COLL].update_one({"_id": "active"},
                                                {"$set": set_fields}, upsert=True)
        for k, v in set_fields.items():
            if k != "updated_at":
                self.config[k] = v
        await self._audit(admin_id, "admin", "gold.config.updated",
                          after={k: v for k, v in set_fields.items() if k != "updated_at"})
        return self.config

    # ------------- pricing ------------- #
    async def current_price(self) -> Dict[str, Any]:
        # Manual override wins
        if self.config.get("manual_price_inr_per_gram"):
            return {
                "ok": True, "provider": "manual", "source": "admin_override",
                "price_per_gram_inr": float(self.config["manual_price_inr_per_gram"]),
                "quoted_at": _now().isoformat(),
            }
        provider = get_provider(self.db, self.config["provider"])
        result = await provider.price_per_gram()
        # Fallback chain: chosen → live_market → mock
        if not result.get("ok") and provider.name != "mock":
            fallback = await LiveMarketGoldProvider(self.db).price_per_gram()
            if fallback.get("ok"):
                fallback["note"] = f"chosen provider '{provider.name}' unavailable, using live_market"
                return fallback
            mock = await MockGoldProvider().price_per_gram()
            mock["note"] = f"all real providers unavailable, using mock"
            return mock
        return result

    async def quote(self) -> Dict[str, Any]:
        price = await self.current_price()
        mid = float(price.get("price_per_gram_inr") or 0)
        half_bps = float(self.config.get("spread_bps", 200)) / 2.0
        buy = round(mid * (1 + half_bps / 10000.0), 2)
        sell = round(mid * (1 - half_bps / 10000.0), 2)
        return {**price, "buy_price": buy, "sell_price": sell,
                "mid_price": round(mid, 2),
                "spread_bps": self.config.get("spread_bps", 200),
                "maintenance_mode": bool(self.config.get("maintenance_mode")),
                "trading_open": self._trading_window_open()}

    def _trading_window_open(self) -> bool:
        th = self.config.get("trading_hours") or {}
        try:
            open_t = _parse_hhmm(th.get("open_utc", "00:00"))
            close_t = _parse_hhmm(th.get("close_utc", "23:59"))
        except Exception:
            return True
        now_t = _now().time()
        if open_t <= close_t:
            return open_t <= now_t <= close_t
        return now_t >= open_t or now_t <= close_t

    def _guardrails(self, amount_inr: Optional[float] = None,
                     grams: Optional[float] = None):
        if self.config.get("maintenance_mode"):
            raise ValueError("Gold trading is under maintenance")
        if not self._trading_window_open():
            raise ValueError("Gold trading is outside the configured trading window")
        if amount_inr is not None:
            if amount_inr < self.config["min_buy_inr"]:
                raise ValueError(f"minimum purchase is ₹{self.config['min_buy_inr']}")
            if amount_inr > self.config["max_buy_inr"]:
                raise ValueError(f"maximum purchase is ₹{self.config['max_buy_inr']}")
        if grams is not None and grams <= 0:
            raise ValueError("grams must be > 0")

    # ------------- transactions ------------- #
    async def buy(self, user_id: str, amount_inr: float,
                   idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        amount_inr = round(float(amount_inr), 2)
        self._guardrails(amount_inr=amount_inr)
        # Idempotency
        if idempotency_key:
            existing = await self.db[TX_COLL].find_one(
                {"user_id": user_id, "idempotency_key": idempotency_key}, {"_id": 0})
            if existing:
                return _iso(existing)
        q = await self.quote()
        if not q.get("ok") or not q.get("buy_price"):
            raise ValueError("unable to fetch gold price")
        buy_price = float(q["buy_price"])
        grams = round(amount_inr / buy_price, 4)
        # Wallet debit
        wallet = await self.db.wallets.find_one({"user_id": user_id}, {"balance": 1}) or {}
        bal = float(wallet.get("balance") or 0)
        if bal < amount_inr:
            raise ValueError(f"insufficient wallet balance ₹{bal:.2f} < ₹{amount_inr:.2f}")
        await self.db.wallets.update_one(
            {"user_id": user_id}, {"$inc": {"balance": -amount_inr}}, upsert=True)
        # Record tx
        tx = {
            "tx_id": f"gld_{uuid.uuid4().hex[:14]}",
            "user_id": user_id, "side": "buy",
            "amount_inr": amount_inr, "grams": grams,
            "price_per_gram": buy_price, "mid_price": q["mid_price"],
            "spread_bps": q["spread_bps"], "provider": q["provider"],
            "idempotency_key": idempotency_key,
            "status": "completed", "created_at": _now(),
        }
        await self.db[TX_COLL].insert_one(tx)
        tx.pop("_id", None)
        # Update holdings (weighted-average cost)
        h = await self.db[HOLDINGS_COLL].find_one({"user_id": user_id}) or {
            "user_id": user_id, "grams": 0.0, "total_invested": 0.0}
        new_grams = float(h.get("grams", 0.0)) + grams
        new_invested = float(h.get("total_invested", 0.0)) + amount_inr
        await self.db[HOLDINGS_COLL].update_one(
            {"user_id": user_id},
            {"$set": {"grams": round(new_grams, 6),
                       "total_invested": round(new_invested, 2),
                       "avg_buy_price": round(new_invested / new_grams, 2)
                       if new_grams else 0.0,
                       "updated_at": _now()}},
            upsert=True,
        )
        # Legacy wallet_transactions for wallet UI
        try:
            await self.db.wallet_transactions.insert_one({
                "tx_id": f"tx_{uuid.uuid4().hex[:12]}",
                "user_id": user_id, "kind": "debit", "category": "gold",
                "amount": amount_inr, "description": f"Gold purchase {grams:.4f}g @ ₹{buy_price}/g",
                "status": "success", "gold_tx_id": tx["tx_id"],
                "created_at": _now(),
            })
        except Exception: pass
        # Notification
        try:
            await self.db.notifications.insert_one({
                "notif_id": f"nf_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "title": "🥇 Gold purchased",
                "body": f"{grams:.4f}g bought for ₹{amount_inr:.2f} @ ₹{buy_price}/g",
                "read": False, "created_at": _now(),
                "deeplink": "/gold", "category": "gold",
                "metadata": {"gold_tx_id": tx["tx_id"], "grams": grams,
                              "amount_inr": amount_inr},
            })
        except Exception: pass
        await self._audit(user_id, "user", "gold.buy",
                          target_id=tx["tx_id"],
                          after={"amount_inr": amount_inr, "grams": grams,
                                  "price": buy_price})
        return _iso(tx)

    async def sell(self, user_id: str, grams: float,
                    idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        grams = round(float(grams), 6)
        self._guardrails(grams=grams)
        if idempotency_key:
            existing = await self.db[TX_COLL].find_one(
                {"user_id": user_id, "idempotency_key": idempotency_key}, {"_id": 0})
            if existing:
                return _iso(existing)
        h = await self.db[HOLDINGS_COLL].find_one({"user_id": user_id})
        held = float((h or {}).get("grams", 0.0))
        if held < grams:
            raise ValueError(f"insufficient gold: hold {held:.4f}g")
        q = await self.quote()
        if not q.get("ok"):
            raise ValueError("unable to fetch gold price")
        sell_price = float(q["sell_price"])
        proceeds = round(grams * sell_price, 2)
        # Wallet credit
        await self.db.wallets.update_one(
            {"user_id": user_id}, {"$inc": {"balance": proceeds}}, upsert=True)
        # Deduct grams; recompute avg cost realized P/L proportional to grams sold
        avg = float((h or {}).get("avg_buy_price", 0.0))
        cost_basis = round(grams * avg, 2)
        pnl = round(proceeds - cost_basis, 2)
        new_grams = round(held - grams, 6)
        new_invested = round(max(0.0, float((h or {}).get("total_invested", 0.0)) - cost_basis), 2)
        await self.db[HOLDINGS_COLL].update_one(
            {"user_id": user_id},
            {"$set": {"grams": new_grams, "total_invested": new_invested,
                       "avg_buy_price": round(new_invested / new_grams, 2) if new_grams else 0.0,
                       "updated_at": _now()}},
            upsert=True,
        )
        tx = {
            "tx_id": f"gld_{uuid.uuid4().hex[:14]}",
            "user_id": user_id, "side": "sell",
            "amount_inr": proceeds, "grams": grams,
            "price_per_gram": sell_price, "mid_price": q["mid_price"],
            "spread_bps": q["spread_bps"], "provider": q["provider"],
            "idempotency_key": idempotency_key,
            "realized_pnl_inr": pnl, "cost_basis_inr": cost_basis,
            "status": "completed", "created_at": _now(),
        }
        await self.db[TX_COLL].insert_one(tx)
        tx.pop("_id", None)
        try:
            await self.db.wallet_transactions.insert_one({
                "tx_id": f"tx_{uuid.uuid4().hex[:12]}",
                "user_id": user_id, "kind": "credit", "category": "gold",
                "amount": proceeds, "description": f"Gold sold {grams:.4f}g @ ₹{sell_price}/g (P/L ₹{pnl})",
                "status": "success", "gold_tx_id": tx["tx_id"], "created_at": _now()})
        except Exception: pass
        try:
            await self.db.notifications.insert_one({
                "notif_id": f"nf_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "title": ("💰 Gold sold with profit" if pnl >= 0 else "💰 Gold sold at loss"),
                "body": f"Sold {grams:.4f}g for ₹{proceeds:.2f}. P/L ₹{pnl:+,.2f}",
                "read": False, "created_at": _now(),
                "deeplink": "/gold", "category": "gold",
                "metadata": {"gold_tx_id": tx["tx_id"], "grams": grams, "pnl": pnl}})
        except Exception: pass
        await self._audit(user_id, "user", "gold.sell", target_id=tx["tx_id"],
                          after={"grams": grams, "proceeds": proceeds, "pnl": pnl})
        return _iso(tx)

    async def holdings(self, user_id: str) -> Dict[str, Any]:
        h = await self.db[HOLDINGS_COLL].find_one({"user_id": user_id},
                                                    {"_id": 0}) or {
            "user_id": user_id, "grams": 0.0, "total_invested": 0.0,
            "avg_buy_price": 0.0}
        q = await self.quote()
        mid = float(q.get("mid_price") or 0)
        sell = float(q.get("sell_price") or 0)
        current_value = round(float(h.get("grams", 0.0)) * sell, 2)
        unrealized_pnl = round(current_value - float(h.get("total_invested", 0.0)), 2)
        # 24h gain from price history
        y = _now() - timedelta(days=1)
        yday = await self.db[PRICE_COLL].find_one({"quoted_at": {"$lte": y}},
                                                     {"_id": 0, "mid": 1},
                                                     sort=[("quoted_at", -1)])
        daily_gain = None
        daily_gain_pct = None
        if yday and yday.get("mid"):
            daily_gain = round((mid - yday["mid"]) * float(h.get("grams", 0.0)), 2)
            if yday["mid"]:
                daily_gain_pct = round((mid - yday["mid"]) / yday["mid"] * 100.0, 3)
        return {
            **h,
            "current_price_per_gram": mid,
            "current_sell_price_per_gram": sell,
            "current_value_inr": current_value,
            "unrealized_pnl_inr": unrealized_pnl,
            "unrealized_pnl_pct": round(
                (unrealized_pnl / float(h["total_invested"])) * 100.0, 3)
            if h.get("total_invested") else 0.0,
            "daily_gain_inr": daily_gain, "daily_gain_pct": daily_gain_pct,
            "as_of": _now().isoformat(),
        }

    async def transactions(self, user_id: str, side: Optional[str] = None,
                            search: Optional[str] = None,
                            limit: int = 50, skip: int = 0) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {"user_id": user_id}
        if side in ("buy", "sell"): q["side"] = side
        if search:
            q["$or"] = [{"tx_id": {"$regex": search, "$options": "i"}},
                        {"provider": {"$regex": search, "$options": "i"}}]
        cur = self.db[TX_COLL].find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
        return [_iso(d) async for d in cur]

    async def snapshot_price(self):
        """Store a price sample every call (used by admin chart)."""
        q = await self.quote()
        if not q.get("ok"): return
        await self.db[PRICE_COLL].insert_one({
            "quoted_at": _now(),
            "mid": q["mid_price"], "buy": q["buy_price"], "sell": q["sell_price"],
            "provider": q["provider"], "source": q.get("source"),
        })

    async def chart(self, window: str = "1D") -> List[Dict[str, Any]]:
        # Auto-seed a synthetic curve when history is thin
        await self._ensure_chart_seed(window)
        buckets = {"1D": timedelta(days=1), "1W": timedelta(days=7),
                    "1M": timedelta(days=30), "3M": timedelta(days=90),
                    "1Y": timedelta(days=365), "ALL": timedelta(days=3650)}
        since = _now() - buckets.get(window.upper(), timedelta(days=1))
        cur = self.db[PRICE_COLL].find(
            {"quoted_at": {"$gte": since}}, {"_id": 0}).sort("quoted_at", 1)
        rows = [_iso(d) async for d in cur]
        return rows

    async def _ensure_chart_seed(self, window: str):
        cnt = await self.db[PRICE_COLL].estimated_document_count()
        if cnt >= 200:
            await self.snapshot_price()
            return
        # Seed 400 points over the past year with a smooth random walk anchored
        # to the current mid price so the chart looks realistic.
        cur_q = await self.quote()
        mid = float(cur_q.get("mid_price") or 6500)
        now = _now()
        rnd = random.Random(42)
        samples = []
        v = mid * 0.85  # start 15% below current
        step = (mid - v) / 400
        for i in range(400):
            v += step + rnd.uniform(-8, 8)
            ts = now - timedelta(days=(400 - i) * 365 / 400)
            samples.append({
                "quoted_at": ts, "mid": round(v, 2),
                "buy": round(v * 1.01, 2), "sell": round(v * 0.99, 2),
                "provider": "seed", "source": "seed",
            })
        if samples:
            await self.db[PRICE_COLL].insert_many(samples)

    # ------------- admin ------------- #
    async def dashboard(self) -> Dict[str, Any]:
        buys = await self.db[TX_COLL].aggregate([
            {"$match": {"side": "buy"}},
            {"$group": {"_id": None, "count": {"$sum": 1},
                         "sum_inr": {"$sum": "$amount_inr"},
                         "sum_grams": {"$sum": "$grams"}}}]).to_list(1)
        sells = await self.db[TX_COLL].aggregate([
            {"$match": {"side": "sell"}},
            {"$group": {"_id": None, "count": {"$sum": 1},
                         "sum_inr": {"$sum": "$amount_inr"},
                         "sum_grams": {"$sum": "$grams"},
                         "sum_pnl": {"$sum": "$realized_pnl_inr"}}}]).to_list(1)
        active = await self.db[TX_COLL].distinct("user_id")
        buy_gross = buys[0] if buys else {"count": 0, "sum_inr": 0, "sum_grams": 0}
        sell_gross = sells[0] if sells else {"count": 0, "sum_inr": 0, "sum_grams": 0, "sum_pnl": 0}
        # Revenue = spread captured on both sides (bps)
        spread_frac = self.config.get("spread_bps", 200) / 20000.0
        revenue = round((buy_gross["sum_inr"] + sell_gross["sum_inr"]) * spread_frac, 2)
        provider = get_provider(self.db, self.config["provider"])
        return {
            "config": self.config,
            "totals": {
                "total_buy_inr": round(buy_gross["sum_inr"], 2),
                "total_buy_grams": round(buy_gross["sum_grams"], 4),
                "buy_tx_count": buy_gross["count"],
                "total_sell_inr": round(sell_gross["sum_inr"], 2),
                "total_sell_grams": round(sell_gross["sum_grams"], 4),
                "sell_tx_count": sell_gross["count"],
                "realized_pnl_users_inr": round(sell_gross.get("sum_pnl", 0), 2),
                "platform_revenue_inr": revenue,
                "active_investors": len(active),
            },
            "quote": await self.quote(),
            "provider_status": {
                "active": provider.name, "real": getattr(provider, "real", False),
                "configured": provider.is_configured(),
                "registry": list(["mock", "live_market", "augmont", "mmtc_pamp", "safegold"]),
            },
        }

    async def admin_transactions(self, user_id: Optional[str] = None,
                                    side: Optional[str] = None,
                                    limit: int = 100, skip: int = 0) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {}
        if user_id: q["user_id"] = user_id
        if side: q["side"] = side
        cur = self.db[TX_COLL].find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
        return [_iso(d) async for d in cur]

    async def admin_users(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self.db[HOLDINGS_COLL].find({}, {"_id": 0}).sort("total_invested", -1).limit(limit)
        return [_iso(d) async for d in cur]

    async def audit(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self.db[AUDIT_COLL].find({}, {"_id": 0}).sort("at", -1).limit(limit)
        return [_iso(d) async for d in cur]

    async def _audit(self, actor_id: str, actor_type: str, action: str,
                       target_id: str = "", after: Optional[Dict[str, Any]] = None):
        await self.db[AUDIT_COLL].insert_one({
            "audit_id": f"aug_{uuid.uuid4().hex[:12]}",
            "actor_id": actor_id, "actor_type": actor_type,
            "action": action, "target_id": target_id,
            "after": after or {}, "at": _now(),
        })
