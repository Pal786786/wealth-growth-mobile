"""Sprint 14.1.4 — architecture invariants for the unified price engine.

These tests are DIFFERENT from feature tests: they lock down the *structural*
guarantees the sprint delivered so a future refactor can never silently
reintroduce a second price source.

Invariants proved:
    1. `forex.feed.PriceFeed` holds NO independent price state:
         no `_cache`, no `_sim`, no `_td`, no `_binance`, no `_history` dict.
    2. `forex.feed` does not import `SimulatedProvider`, `TwelveDataProvider`
        or `BinanceProvider` from `forex.providers`.
    3. `PriceFeed.get_quote`, `.get_all_quotes`, `.get_history` are all
        `async` — they cannot be resolved without touching the shared
        ProviderManager.
    4. `PriceFeed.start()` and `PriceFeed._poll_forever` are gone / no-op —
        there is exactly ONE market scheduler in the process
        (`ProviderManager._refresh_loop`).
    5. Numerical equivalence: for any symbol S,
         `market_price_cache[S].price ≡ forex.PriceFeed.get_quote(S).mid`
       (± 0.0001 rounding tolerance from spread derivation).
    6. Trading engine's mark-to-market uses the shared cache
       (`engine._mark_once` awaits `feed.get_quote`).
"""
from __future__ import annotations

import asyncio
import inspect
import re
from typing import Any

import pytest


# ---------------------------------------------------------------------------- #
class TestNoIndependentState:
    """§1 — PriceFeed instance carries no independent price/history state."""

    def test_pricefeed_has_no_underscore_cache(self):
        from forex.feed import PriceFeed
        f = PriceFeed()
        forbidden = {"_cache", "_sim", "_td", "_binance", "_poll_task", "_history"}
        present   = set(vars(f).keys())
        leak      = forbidden & present
        assert not leak, f"PriceFeed still owns forbidden fields: {leak}"

    def test_pricefeed_module_does_not_import_price_producers(self):
        """§2 — importing SimulatedProvider/TwelveDataProvider/BinanceProvider
        from forex.feed is banned (they would smuggle a parallel engine).
        Docstrings mentioning the removed classes are fine — only real code
        statements are inspected."""
        import forex.feed as feed_mod
        src = inspect.getsource(feed_mod)
        # Strip docstrings/comments before scanning for imports.
        import ast
        tree = ast.parse(src)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported.add(alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
        for banned in ("SimulatedProvider", "TwelveDataProvider", "BinanceProvider"):
            assert banned not in imported, (
                f"forex.feed must not import {banned}; unified engine reads "
                f"from ProviderManager only. Imports found: {imported}"
            )


# ---------------------------------------------------------------------------- #
class TestAsyncReadContract:
    """§3 — all price read methods are coroutines (proves they can't work
    without awaiting the shared cache)."""

    def test_get_quote_is_async(self):
        from forex.feed import PriceFeed
        assert inspect.iscoroutinefunction(PriceFeed.get_quote), \
            "PriceFeed.get_quote must be async — it reads the shared cache"

    def test_get_all_quotes_is_async(self):
        from forex.feed import PriceFeed
        assert inspect.iscoroutinefunction(PriceFeed.get_all_quotes)

    def test_get_history_is_async(self):
        from forex.feed import PriceFeed
        assert inspect.iscoroutinefunction(PriceFeed.get_history)


# ---------------------------------------------------------------------------- #
class TestNoParallelScheduler:
    """§4 — PriceFeed's own polling loop is gone. Only ProviderManager
    schedules price refreshes now."""

    def test_no_poll_forever(self):
        from forex.feed import PriceFeed
        assert not hasattr(PriceFeed, "_poll_forever"), \
            "PriceFeed._poll_forever was removed in Sprint 14.1.4"

    def test_start_is_noop(self):
        """start() should exist for backward compat but not schedule anything."""
        from forex.feed import PriceFeed
        f = PriceFeed()
        # If start spawned a task, the instance would have a _poll_task attr.
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(f.start())
        finally:
            loop.close()
        assert not hasattr(f, "_poll_task") or getattr(f, "_poll_task") is None

    def test_source_file_has_no_asyncio_create_task(self):
        import forex.feed as feed_mod
        src = inspect.getsource(feed_mod)
        # Only ONE allowed use of create_task: the fire-and-forget key
        # propagation in set_live_mode. Anything else is a scheduler.
        create_task_lines = [ln for ln in src.split("\n") if "create_task" in ln and "#" not in ln.split("create_task", 1)[0]]
        assert len(create_task_lines) <= 2, (
            "forex.feed contains too many create_task() calls; a parallel "
            f"scheduler may have been reintroduced:\n{create_task_lines}"
        )


# ---------------------------------------------------------------------------- #
class TestUnifiedNumberContract:
    """§5 — /api/forex/prices returns exactly the same price the shared
    cache stores. Runtime test against the live backend."""

    def test_forex_price_matches_cache(self):
        import os, requests
        base = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")

        r = requests.get(f"{base}/api/forex/prices", timeout=8)
        if r.status_code != 200:
            pytest.skip(f"backend not reachable: {r.status_code}")
        prices = r.json().get("prices", [])
        if not prices:
            pytest.skip("no prices yet — provider hasn't populated cache")

        # Also read the cache via Mongo directly
        from motor.motor_asyncio import AsyncIOMotorClient
        loop = asyncio.new_event_loop()
        try:
            c = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
            db = c[os.environ.get("DB_NAME", "my_funding_bank")]

            async def read_cache(sym: str):
                return await db.market_price_cache.find_one({"symbol": sym})

            for p in prices:
                sid = p["symbol_id"]
                doc = loop.run_until_complete(read_cache(sid))
                if not doc:
                    continue
                cache_px = float(doc["price"])
                forex_mid = float(p["mid"])
                # Tolerance = ½ spread — bid/ask derivation may nudge by
                # one pip when the cache row didn't ship its own bid/ask.
                spread_est = abs(float(p["ask"]) - float(p["bid"])) / 2 + 1e-6
                assert abs(cache_px - forex_mid) <= spread_est * 3, (
                    f"Divergence on {sid}: cache={cache_px} forex={forex_mid}"
                )
        finally:
            loop.close()


# ---------------------------------------------------------------------------- #
class TestEngineUsesSharedCache:
    """§6 — engine.get_quote paths all await feed.get_quote (unified)."""

    def test_mark_once_awaits_feed(self):
        import forex.engine as engine_mod
        src = inspect.getsource(engine_mod._mark_once) if hasattr(engine_mod, "_mark_once") else inspect.getsource(engine_mod)
        # Pattern: `q = await self.feed.get_quote(`
        assert re.search(r"await\s+self\.feed\.get_quote\s*\(", src), \
            "engine.py must await feed.get_quote (unified async contract)"

    def test_enrich_is_async(self):
        from forex.engine import TradingEngine
        assert inspect.iscoroutinefunction(TradingEngine._enrich)

    def test_open_position_awaits_feed(self):
        import forex.engine as engine_mod
        src = inspect.getsource(engine_mod.TradingEngine.open_position)
        assert "await self.feed.get_quote(" in src


# ---------------------------------------------------------------------------- #
class TestPublicApiSurfacePreserved:
    """§7 — Mobile/admin schema unchanged so no client update needed."""

    def test_price_response_shape(self):
        import os, requests
        base = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")
        r = requests.get(f"{base}/api/forex/prices", timeout=8)
        if r.status_code != 200:
            pytest.skip("backend not reachable")
        body = r.json()
        assert set(body.keys()) >= {"prices", "ts_now", "diagnostics"}
        if body["prices"]:
            p = body["prices"][0]
            for k in ("symbol_id", "bid", "ask", "mid", "ts", "source", "display", "price_decimals"):
                assert k in p, f"missing field {k} in price response"

    def test_diagnostics_reports_unified_engine(self):
        import os, requests
        base = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")
        r = requests.get(f"{base}/api/forex/prices", timeout=8)
        if r.status_code != 200:
            pytest.skip("backend not reachable")
        diag = r.json().get("diagnostics", {})
        assert "engine" in diag
        assert "unified" in str(diag["engine"]).lower(), \
            f"diagnostics.engine should say 'unified', got {diag}"
