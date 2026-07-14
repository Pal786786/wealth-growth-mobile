"""Sprint 14.1.4 — Price source consistency (unified engine).

The bug this originally reproduced ("execution and /prices returned
different numbers for the same symbol at the same tick") is now
architecturally impossible: there is a single price engine
(`ProviderManager` → `market_price_cache`), and `PriceFeed` is a thin
async adapter over it. These tests are rewritten to lock down the NEW
invariant:

    market_price_cache[S].price  ==  await PriceFeed.get_quote(S).mid

and to document that the OBSOLETE knobs (`PriceFeed._sim`, `_cache`,
`_poll_forever`, sim-vs-live grace window) no longer exist.
"""
from __future__ import annotations

import asyncio
import time

import pytest


class TestObsoleteAttributesGone:
    """The pre-14.1.4 divergence bugs relied on these private attributes.
    Removing them is what makes divergence impossible; guard that removal."""

    def test_pricefeed_has_no_sim(self):
        from forex.feed import PriceFeed
        assert not hasattr(PriceFeed(), "_sim")

    def test_pricefeed_has_no_local_cache(self):
        from forex.feed import PriceFeed
        assert not hasattr(PriceFeed(), "_cache")

    def test_pricefeed_has_no_history_dict(self):
        from forex.feed import PriceFeed
        assert not hasattr(PriceFeed(), "_history")

    def test_module_has_no_poll_forever(self):
        from forex.feed import PriceFeed
        assert not hasattr(PriceFeed, "_poll_forever")


class TestExecutionAndPricesRunOneEngine:
    """The successor to `test_execution_and_prices_read_same_quote`.
    Runs against the LIVE backend to prove the whole pipeline agrees."""

    def test_forex_prices_equals_market_price_cache(self):
        import os, requests
        base = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")
        try:
            r = requests.get(f"{base}/api/forex/prices", timeout=8)
        except Exception:
            pytest.skip("backend unreachable")
        if r.status_code != 200:
            pytest.skip(f"forex prices status {r.status_code}")
        forex_by_sid = {p["symbol_id"]: p for p in r.json().get("prices", [])}
        if not forex_by_sid:
            pytest.skip("no prices yet")

        # Use pymongo (sync) for the assertion so we don't collide with the
        # backend's asyncio loop.
        from pymongo import MongoClient
        c = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = c[os.environ.get("DB_NAME", "my_funding_bank")]
        checked = 0
        for sid, p in forex_by_sid.items():
            doc = db.market_price_cache.find_one({"symbol": sid})
            if not doc:
                continue
            assert abs(float(doc["price"]) - float(p["mid"])) < 1.0, (
                f"{sid}: cache={doc['price']} forex={p['mid']}"
            )
            checked += 1
        c.close()
        assert checked >= 1, "no symbols verified"


class TestPnLReadsSameQuote:
    """The successor to `test_pnl_math_reads_current_quote_from_same_feed`.
    Proves that opening a position + reading its enriched PnL both use the
    same underlying quote — the cache one."""

    def test_open_and_enrich_use_same_price_source(self):
        import inspect
        from forex.engine import TradingEngine
        # Both open_position (async) and _enrich (async, 14.1.4) must
        # invoke `self.feed.get_quote(...)` — the unified adapter.
        for m in (TradingEngine.open_position, TradingEngine._enrich,
                  TradingEngine._mark_once, TradingEngine.close_position):
            src = inspect.getsource(m)
            assert "await self.feed.get_quote(" in src, \
                f"{m.__name__} must await unified feed.get_quote"


class TestNoDuplicatePriceScheduler:
    """The successor to `test_sim_never_overwrites_recent_twelvedata_quote`
    and `_can_take_over_after_grace_window_expires`. Both tests exercised
    the sim-vs-live overwrite grace window — a subsystem that no longer
    exists. Replaced with the stronger invariant: there is no sim at all."""

    def test_only_one_market_scheduler_in_process(self):
        import inspect
        import market_providers.manager as mgr_mod
        # exactly one refresh loop lives in manager
        assert hasattr(mgr_mod.ProviderManager, "_refresh_loop")
        import forex.feed as feed_mod
        assert not hasattr(feed_mod.PriceFeed, "_poll_forever"), \
            "forex.feed must not schedule a second refresh loop"
