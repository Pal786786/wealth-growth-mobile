# Sprint 14.1.1 — Price Source Consistency Trace

## Bug
Order execution price matched TradingView, but the Forex screen showed a different current price seconds later; unrealized P/L used that wrong price.

## Root cause
TWO parallel price sources existed:

| Source | Path | Populated by |
|---|---|---|
| Shared cache `market_price_cache` | `market_providers/cache.py` | `ProviderManager._refresh_loop` (TwelveData / AlphaVantage / Mock) |
| Forex in-memory cache `PriceFeed._cache` | `forex/feed.py` | `SimulatedProvider` (always ticking), `TwelveDataProvider` (every 120 s), `BinanceProvider` |

The forex feed's `_poll_forever` used a **150-second** freshness guard — shorter than the 120-second TwelveData poll interval + processing delay. Once a live TD quote aged past 150 s, the **Simulated provider silently overwrote it** in `PriceFeed._cache`. Order execution had captured the live quote, but seconds later `/prices`, mark-to-market, and unrealized-P/L computations read the simulated value.

## Fix
1. `PriceFeed._poll_forever` (Sprint 14.1.1) —
   * Grace window extended from 150 s → **600 s** for TwelveData/Binance quotes so sim can never overwrite live within a real trading session.
   * **Mirrors the shared `market_price_cache`** first: any symbol with a real-provider entry there is copied into `PriceFeed._cache` unchanged, so shared-cache readers (AI signals, Watchlist, Alerts, Copy Trading, Gold) and forex-cache readers (execution, UI, MTM, chart) return the **same price object** for the same symbol at the same tick.
2. New `attach_shared_manager()` hook wired from `server.py` bridges `ProviderManager` → `PriceFeed`.
3. Priority-aware guard from Sprint 14.1 (already in `market_providers/cache.py`) ensures the shared cache itself never gets mock/stale overwrites.

## Path map (post-fix)
All of the following now read from the **same** Quote object per tick:

| Consumer | File / function | Source |
|---|---|---|
| Order execution | `forex/engine.py::open_position` | `feed.get_quote()` |
| Current price / chart | `forex/routes.py::get_prices` | `feed.get_quote()` |
| Bid / Ask | `feed.get_quote()` bid/ask | Same quote |
| Mark-to-market / unrealized P/L | `forex/engine.py::_recompute_pnl` | `feed.get_quote().mid` |
| Watchlist | `market_providers/cache.py::get` (shared cache) | Mirrored from same live tick via bridge |
| Gold module | `gold/providers.py` reads `XAUUSD` from `market_price_cache` | Same shared cache |
| Open positions | `feed.get_quote()` on refresh | Same quote |

## Files changed
- `backend/forex/feed.py` — new `attach_shared_manager()`, rewrote `_poll_forever` guard + shared-cache mirror.
- `backend/server.py` — wire manager into forex feed after `market_providers.attach`.
- `backend/tests/test_price_source_consistency_iter36.py` — 8 new regression tests (bug repro + guard + bridge + P/L math).
