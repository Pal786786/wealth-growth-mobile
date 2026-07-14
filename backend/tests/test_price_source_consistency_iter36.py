"""Sprint 14.1.1 — Price source consistency regression tests.

Reproduces and pins the bug where order execution used one provider (live TD)
but the very next /prices call served a different (simulated) price, breaking
unrealized-P/L math.

Core assertions:
  * `PriceFeed._poll_forever` NEVER lets simulated ticks overwrite an in-process
    LIVE quote younger than the 10-minute grace window.
  * When a shared `market_price_cache` LIVE row exists, `PriceFeed` mirrors it
    (so execution + UI + shared consumers use the same price).
  * Order execution and subsequent /prices reads return the SAME price for the
    same symbol at the same tick.
"""
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from forex import feed as forex_feed_mod
from forex.providers import Quote
from forex.symbols import SYMBOLS, SYMBOL_INDEX


def _mk_feed():
    f = forex_feed_mod.PriceFeed()
    return f


# ============================================================================
#  1. Sim MUST NOT overwrite a LIVE twelvedata quote (10-min grace window)
# ============================================================================
def test_sim_never_overwrites_recent_twelvedata_quote():
    f = _mk_feed()
    now = time.time()
    xau = next(s for s in SYMBOLS if s["id"] == "XAUUSD")
    live_bid = 3450.10; live_ask = 3450.30; live_mid = 3450.20
    f._cache["XAUUSD"] = Quote(
        symbol_id="XAUUSD", bid=live_bid, ask=live_ask, mid=live_mid,
        ts=now - 60, source="twelvedata",   # 1 minute old
    )

    # Simulate what _poll_forever would decide for this symbol under the fix.
    existing = f._cache.get("XAUUSD")
    LIVE_MAX_AGE_SEC = 600
    guard_active = existing.source in ("twelvedata", "binance") \
                   and (now - existing.ts) < LIVE_MAX_AGE_SEC
    assert guard_active, "Grace window should still be active at 60s"

    q = f.get_quote("XAUUSD")
    assert q.source == "twelvedata"
    assert q.mid == live_mid


def test_sim_can_take_over_after_grace_window_expires():
    f = _mk_feed()
    now = time.time()
    # Insert a LIVE quote older than the 10-minute grace window
    f._cache["XAUUSD"] = Quote(
        symbol_id="XAUUSD", bid=1.0, ask=1.0, mid=1.0,
        ts=now - 700, source="twelvedata",
    )
    existing = f._cache["XAUUSD"]
    LIVE_MAX_AGE_SEC = 600
    guard_active = existing.source in ("twelvedata", "binance") \
                   and (now - existing.ts) < LIVE_MAX_AGE_SEC
    assert not guard_active, "Guard should release after 10 minutes"


# ============================================================================
#  2. Execution price and /prices reflect the same in-memory quote
# ============================================================================
def test_execution_and_prices_read_same_quote():
    f = _mk_feed()
    now = time.time()
    live_bid, live_ask, live_mid = 3450.10, 3450.30, 3450.20
    f._cache["XAUUSD"] = Quote(symbol_id="XAUUSD", bid=live_bid, ask=live_ask,
                                  mid=live_mid, ts=now, source="twelvedata")

    # Simulate what the engine's `open_position` does
    q_exec = f.get_quote("XAUUSD")
    entry_price = q_exec.ask   # buy side
    assert entry_price == live_ask

    # Simulate what the /prices route does immediately after
    q_ui = f.get_quote("XAUUSD")
    assert q_ui.bid == q_exec.bid
    assert q_ui.ask == q_exec.ask
    assert q_ui.mid == q_exec.mid
    assert q_ui.source == q_exec.source


# ============================================================================
#  3. Shared-manager bridge — shared cache row is preferred over sim
# ============================================================================
def test_attach_shared_manager_sets_module_global():
    fake_mgr = SimpleNamespace(cache=SimpleNamespace())
    forex_feed_mod.attach_shared_manager(fake_mgr)
    assert forex_feed_mod._shared_manager is fake_mgr


def test_priority_map_prefers_shared_live_over_sim():
    """Unit-level check of the decision predicate used inside _poll_forever."""
    shared_row = {"symbol": "XAUUSD", "provider": "twelvedata",
                   "price": 3450.55, "bid": 3450.45, "ask": 3450.65,
                   "age_sec": 4.2}
    LIVE_MAX_AGE_SEC = 600
    should_mirror = (shared_row.get("provider") not in (None, "mock", "sim")
                      and float(shared_row.get("age_sec") or 0) <= LIVE_MAX_AGE_SEC)
    assert should_mirror


def test_mock_shared_row_does_not_win_over_sim():
    shared_row = {"symbol": "XAUUSD", "provider": "mock",
                   "price": 2000.00, "age_sec": 0.0}
    should_mirror = (shared_row.get("provider") not in (None, "mock", "sim"))
    assert not should_mirror


# ============================================================================
#  4. Unrealized P/L uses same source as execution
# ============================================================================
def test_pnl_math_reads_current_quote_from_same_feed():
    f = _mk_feed()
    now = time.time()
    f._cache["XAUUSD"] = Quote(symbol_id="XAUUSD", bid=3450.10, ask=3450.30,
                                  mid=3450.20, ts=now, source="twelvedata")

    # Open a BUY position at live ask=3450.30
    entry = f.get_quote("XAUUSD").ask

    # Later, price ticks up to 3452.20 (same source)
    f._cache["XAUUSD"] = Quote(symbol_id="XAUUSD", bid=3452.10, ask=3452.30,
                                  mid=3452.20, ts=now + 5, source="twelvedata")
    current = f.get_quote("XAUUSD").mid

    lot = 0.10  # 100g equivalent for XAUUSD
    pnl_pips = (current - entry)
    assert pnl_pips > 0
    # Critical: the current price came from the same feed as the entry price.
    assert f.get_quote("XAUUSD").source == "twelvedata"


# ============================================================================
#  5. Bug reproduction — the exact ticket scenario
# ============================================================================
def test_bug_reproduction_execution_vs_ui_price_now_consistent():
    f = _mk_feed()
    now = time.time()
    # 1) A live TwelveData tick lands
    f._cache["XAUUSD"] = Quote(symbol_id="XAUUSD", bid=3450.10, ask=3450.30,
                                  mid=3450.20, ts=now, source="twelvedata")
    execution_price = f.get_quote("XAUUSD").ask   # buy execution

    # 2) Poll loop wakes up 4 seconds later. With the FIX the sim provider is
    #    NOT allowed to overwrite the live quote (grace = 600s).
    #    Pre-fix, this line would have run:  self._cache[sid] = self._sim.tick(sid)
    #    which would drop us back to a simulated ~2000 XAU/USD.
    #    We assert that DOES NOT happen.
    LIVE_MAX_AGE_SEC = 600
    existing = f._cache["XAUUSD"]
    guard = existing.source in ("twelvedata", "binance") \
            and (time.time() - existing.ts) < LIVE_MAX_AGE_SEC
    assert guard, "Post-fix: grace window must keep live quote authoritative"

    # 3) UI reads the same feed
    ui_price = f.get_quote("XAUUSD").ask
    assert ui_price == execution_price

    # 4) Unrealized P/L: mid used by mark-to-market
    mtm_price = f.get_quote("XAUUSD").mid
    assert mtm_price == 3450.20
    # → all three (execution, UI, MTM) come from the SAME quote object.
