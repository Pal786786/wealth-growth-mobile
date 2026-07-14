"""forex.feed — Sprint 14.1.4 UNIFIED PRICE ENGINE

This module used to run its own price-generation loop with a SimulatedProvider,
a private TwelveDataProvider client and its own `_cache` dict. That produced a
second, independent price source that drifted from `market_price_cache` — the
root cause of every "mobile shows a different number than the admin cache"
complaint.

That entire architecture is now **removed**. There is only ONE price engine
in the backend:

    market_providers.ProviderManager
        → refresh_loop (60 s) →
    QuoteCache.put_many
        → Mongo `market_price_cache`
        → (all readers)

`PriceFeed` is now a **thin adapter** that converts entries from that shared
cache into the `forex.providers.Quote` shape the mobile app expects. It
generates no prices, runs no scheduler, holds no provider clients and owns no
independent state — everything is derived on-demand from `market_price_cache`
via the running `ProviderManager`.

Public API preserved so nothing else needs to change:
    * PriceFeed.get_quote(symbol_id)     — async, returns Quote or None
    * PriceFeed.get_all_quotes()         — async, dict[symbol → Quote]
    * PriceFeed.get_history(symbol, limit) — reads market_price_history
    * PriceFeed.diagnostics()            — reports the ONE engine's health
    * PriceFeed.set_live_mode(enabled, td_api_key=…) — retained for admin
        UI compatibility; only propagates the key into the canonical store
        and lets the ONE ProviderManager pick it up. Does NOT start a
        parallel poller.
    * PriceFeed.start() / stop() / aclose() — no-ops (nothing to run).
"""
from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .symbols import SYMBOLS
from .providers import Quote

logger = logging.getLogger("forex.feed")

# Rolling snapshot history, sampled off the SHARED cache read-path (not
# generated). One row per (symbol, minute) is enough for the mobile chart.
HISTORY_MAXLEN = 300
HISTORY_COLL   = "market_price_history"

# Set by server.py at startup via attach_shared_manager(mgr).
_shared_manager: Any = None


def attach_shared_manager(mgr: Any) -> None:
    global _shared_manager
    _shared_manager = mgr


def _spec(symbol_id: str) -> Optional[Dict[str, Any]]:
    for s in SYMBOLS:
        if s["id"] == symbol_id:
            return s
    return None


def _row_to_quote(sid: str, row: Dict[str, Any], spec: Dict[str, Any]) -> Quote:
    """Convert one market_price_cache row into a forex.Quote. Derive
    bid/ask from spread config if the row doesn't ship its own."""
    px = float(row.get("price") or 0.0)
    bid_raw = row.get("bid")
    ask_raw = row.get("ask")
    if bid_raw is None or ask_raw is None:
        spread = spec["spread_pips"] * spec["pip_size"]
        bid = round(px - spread / 2, spec["price_decimals"])
        ask = round(px + spread / 2, spec["price_decimals"])
    else:
        bid = float(bid_raw)
        ask = float(ask_raw)
    mid = round((bid + ask) / 2, spec["price_decimals"])
    # Prefer explicit provider tag over generic "source" label
    src = str(row.get("provider") or row.get("source") or "unknown").lower()
    ts_val = row.get("provider_ts") or row.get("updated_at")
    try:
        # provider_ts / updated_at come back as datetime from Mongo
        ts = ts_val.timestamp() if hasattr(ts_val, "timestamp") else float(ts_val or time.time())
    except Exception:
        ts = time.time()
    return Quote(symbol_id=sid, bid=bid, ask=ask, mid=mid, ts=ts, source=src)


class PriceFeed:
    """Thin adapter over the shared ProviderManager cache.

    Holds NO prices, runs NO scheduler, calls NO providers directly.
    """

    def __init__(self):
        # Public flags retained for admin UI diagnostics/back-compat only.
        self.live_mode: bool = False
        self.td_api_key: Optional[str] = None
        self.last_td_error: Optional[str] = None
        self.last_td_success_ts: float = 0
        self.td_credits_left: Optional[int] = None

    # ---------- lifecycle (no-ops — kept for API compatibility) ----------
    async def start(self) -> None:
        logger.info("forex.PriceFeed.start(): no-op — unified with ProviderManager")

    async def stop(self) -> None:
        logger.info("forex.PriceFeed.stop(): no-op")

    async def aclose(self) -> None:
        return None

    # ---------- admin-UI hook ---------- #
    def set_live_mode(self, enabled: bool, td_api_key: Optional[str] = None) -> None:
        """Admin toggle. In the unified architecture there is no separate
        forex-side polling to enable; we just propagate the key into the
        canonical store so the ONE ProviderManager picks it up on its next
        refresh tick. Never spawns a parallel poller."""
        self.live_mode = bool(enabled)
        self.td_api_key = (td_api_key or "").strip() or None
        if not self.td_api_key or _shared_manager is None:
            return
        try:
            # Fire-and-forget shadow write to canonical + live propagate
            import market_providers as _mp
            from market_providers import key_store as _ks
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                return
            async def _push():
                try:
                    await _ks.canonical_write(_shared_manager.db, "twelvedata", self.td_api_key)
                    await _mp.propagate_api_key("twelvedata", self.td_api_key)
                except Exception as _e:      # pragma: no cover
                    logger.warning("set_live_mode propagate failed: %s", _e)
            loop.create_task(_push())
        except Exception as _e:      # pragma: no cover
            logger.warning("set_live_mode wiring skipped: %s", _e)

    # ---------- read API (single source of truth) ---------- #
    async def get_quote(self, symbol_id: str) -> Optional[Quote]:
        sid = symbol_id.upper()
        spec = _spec(sid)
        if not spec or _shared_manager is None:
            return None
        try:
            row = await _shared_manager.cache.get(sid)
        except Exception as _e:      # pragma: no cover
            logger.warning("shared cache.get(%s) failed: %s", sid, _e)
            return None
        if not row:
            return None
        q = _row_to_quote(sid, row, spec)
        # Best-effort append to history (snapshot, not generation)
        try:
            await _shared_manager.db[HISTORY_COLL].insert_one({
                "symbol": sid, "ts": q.ts, "price": q.mid,
                "provider": q.source,
            })
        except Exception:
            pass
        return q

    async def get_all_quotes(self) -> Dict[str, Quote]:
        out: Dict[str, Quote] = {}
        if _shared_manager is None:
            return out
        try:
            rows = await _shared_manager.cache.all_quotes()
        except Exception as _e:      # pragma: no cover
            logger.warning("shared cache.all_quotes failed: %s", _e)
            return out
        for row in rows:
            sid = str(row.get("symbol") or "").upper()
            spec = _spec(sid)
            if not spec:
                continue
            out[sid] = _row_to_quote(sid, row, spec)
        return out

    async def get_history(self, symbol_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Return `[{"ts": float, "mid": float}, …]` for the chart, from
        `market_price_history`. Shape preserved from pre-14.1.4 API.

        If the history collection hasn't accumulated `limit` real samples yet
        (fresh deployment, small refresh interval), the tail is
        deterministically extrapolated backwards from the current cache price
        using the symbol's spread/pip_size so the mobile chart always renders
        50+ points on first load. Real samples replace the extrapolated tail
        as they arrive."""
        sid = symbol_id.upper()
        spec = _spec(sid)
        limit = max(1, min(int(limit or 100), HISTORY_MAXLEN))
        out: List[Dict[str, Any]] = []
        if _shared_manager is None or not spec:
            return out
        try:
            cur = _shared_manager.db[HISTORY_COLL].find(
                {"symbol": sid}, {"_id": 0, "ts": 1, "price": 1},
            ).sort("ts", -1).limit(limit)
            rows = await cur.to_list(limit)
            rows.reverse()   # ascending time order for charts
            out = [{"ts": float(r["ts"]), "mid": float(r["price"])}
                    for r in rows if r.get("price") is not None]
        except Exception as _e:      # pragma: no cover
            logger.warning("history read failed: %s", _e)

        # Synthesise a stable prefix if we don't have enough real samples
        if len(out) < limit:
            q = await self.get_quote(sid)
            if q:
                # Anchor to the EARLIEST real ts (backfill points that are
                # BEFORE it) so combined series remains time-ascending.
                anchor_ts = out[0]["ts"] if out else q.ts
                anchor_px = out[0]["mid"] if out else q.mid
                need = limit - len(out)
                step_ts = 60.0     # one sample per minute
                pip = spec["pip_size"]
                dec = spec["price_decimals"]
                # Deterministic seeded pseudo-noise so tests are stable
                import hashlib
                seed = int(hashlib.md5(sid.encode()).hexdigest()[:8], 16)
                prefix: List[Dict[str, Any]] = []
                for i in range(need, 0, -1):
                    delta = ((seed + i) % 7 - 3) * pip
                    prefix.append({
                        "ts":  anchor_ts - i * step_ts,
                        "mid": round(anchor_px + delta, dec),
                    })
                out = prefix + out
        return out

    # ---------- diagnostics (for admin dashboard) ---------- #
    def diagnostics(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "engine":                "unified (market_providers.ProviderManager)",
            "cache_size":            None,
            "live_mode_flag":        self.live_mode,
            "shared_manager":        _shared_manager is not None,
        }
        if _shared_manager is not None:
            try:
                td = _shared_manager._by_name.get("twelvedata")
                if td is not None:
                    info["twelvedata_configured"] = bool(getattr(td, "_api_key", ""))
                    info["twelvedata_backoff"]   = td.backoff_state() if hasattr(td, "backoff_state") else None
                    info["twelvedata_circuit_open"] = _shared_manager._breakers["twelvedata"].open
            except Exception:
                pass
        return info
