"""Sprint 14.1.2 — LIVE Quote Ingestion Debug Endpoint

Feature-flagged, super-admin-only diagnostic that traces a single symbol's
journey through the TwelveData pipeline:

    HTTP → parser (Quote) → ProviderManager.cache.put_many() → Mongo document

Every stage returns a structured payload so the operator can see exactly where
(and why) a live quote is being dropped before it reaches `market_price_cache`.

Security:
  * Requires super_admin JWT.
  * Disabled unless MARKET_DEBUG_ENABLED=true in the environment.
  * API keys and full raw provider bodies are REDACTED before return.
  * Every invocation is logged to `admin_audit` via `_log_action`.

Usage:
    GET /api/market/debug/xauusd
    GET /api/market/debug/quote?symbol=EURUSD
    GET /api/market/debug/quote?symbol=XAUUSD&dry_run=false   # actually writes

By default (dry_run=true) the endpoint reads the current Mongo document but
does NOT rewrite the cache. Set `dry_run=false` to attempt a real cache write
so the priority/timestamp guard can also be exercised.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .base import ProviderNotConfigured, Quote, RateLimitError
from .twelvedata import BASE_URL, SYMBOL_MAP, TwelveDataProvider, _redact_api_key

logger = logging.getLogger("market.providers.debug")

# Fields we NEVER return to the client (even to a super admin) — provider
# response bodies may echo the key back or embed subscription info.
_RESP_FIELD_ALLOWLIST = {
    "symbol", "name", "exchange", "mic_code", "currency", "datetime",
    "timestamp", "open", "high", "low", "close", "volume", "previous_close",
    "change", "percent_change", "average_volume", "is_market_open",
    "fifty_two_week", "extended_change", "extended_percent_change",
    "extended_price", "extended_timestamp", "rolling_1_day_change",
    "rolling_7_day_change", "rolling_period_change",
    # error markers we DO want to see
    "status", "message", "code",
}


def _redact_payload(payload: Any) -> Any:
    """Whitelist-filter provider payload before returning. Keeps only well-known
    market fields so we can never leak api-key echoes / subscription metadata."""
    if isinstance(payload, dict):
        return {k: v for k, v in payload.items() if k in _RESP_FIELD_ALLOWLIST}
    return payload


def _is_debug_enabled() -> bool:
    return (os.environ.get("MARKET_DEBUG_ENABLED", "false") or "").strip().lower() \
           in ("1", "true", "yes", "on")


def attach(app, manager, get_current_admin, log_action=None):
    """Register the /api/market/debug/... router.

    `manager`      — the singleton ProviderManager (has `.cache` and `.providers`)
    `log_action`   — optional callable(admin_id, action, target, meta) for audit
    """
    r = APIRouter(prefix="/api/market/debug", tags=["market-debug"])

    def _require_super(admin: Dict[str, Any]) -> Dict[str, Any]:
        if not _is_debug_enabled():
            raise HTTPException(
                status_code=404, detail="market debug endpoint disabled",
            )
        if (admin or {}).get("role") != "super_admin":
            raise HTTPException(
                status_code=403, detail="super_admin role required",
            )
        return admin

    async def _audit(admin: Dict[str, Any], symbol: str, meta: Dict[str, Any]) -> None:
        if not log_action:
            return
        try:
            await log_action(
                admin.get("admin_id") or "unknown",
                "market_debug_trace",
                target=f"symbol={symbol}",
                meta={k: v for k, v in meta.items() if k not in ("raw_response_preview",)},
            )
        except Exception as _e:  # pragma: no cover
            logger.warning("audit log failed: %s", _e)

    # -------------------------------------------------------------------- #
    # /api/market/debug/config
    # -------------------------------------------------------------------- #
    @r.get("/config")
    async def debug_config(admin=Depends(get_current_admin)):
        """Diagnostic view of the runtime → Mongo → provider wiring.
        NEVER exposes API keys. Answers "which DB / which collection / which
        provider status is this backend actually using?".
        """
        _require_super(admin)
        import os as _os
        # DB identity
        db = manager.db
        db_name = getattr(db, "name", "?")
        client = getattr(db, "client", None)
        addr = "?"
        try:
            if client is not None:
                addr = str(client.address) if getattr(client, "address", None) else str(client.nodes)
        except Exception:
            pass

        # Fingerprint every place a market API key can live (values redacted).
        from . import key_store as _ks
        key_locations: list[dict] = []

        async def _snapshot(coll: str, flt: dict, path: str, provider_hint: str) -> None:
            try:
                d = await db[coll].find_one(flt)
            except Exception as _e:
                key_locations.append({
                    "collection": coll, "filter": flt, "path": path,
                    "provider_hint": provider_hint,
                    "error": f"{type(_e).__name__}: {_e}",
                })
                return
            v = _ks._get_nested(d, path) if d else None
            key_locations.append({
                "collection":   coll,
                "filter":       flt,
                "path":         path,
                "provider_hint": provider_hint,
                "present":      bool(v),
                "length":       len(v) if v else 0,
                "fingerprint":  (v[:4] + "…" + v[-2:]) if v and len(v) > 6 else None,
            })

        # Canonical
        await _snapshot(_ks.CANONICAL_COLL, {"_id": _ks.CANONICAL_ID},
                        "twelvedata_api_key",  "twelvedata (CANONICAL)")
        await _snapshot(_ks.CANONICAL_COLL, {"_id": _ks.CANONICAL_ID},
                        "alphavantage_api_key", "alphavantage (CANONICAL)")
        # Legacy chain
        for prov, chain in _ks.LEGACY_LOCATIONS.items():
            for coll, flt, path in chain:
                await _snapshot(coll, flt, path, f"{prov} (legacy)")

        # Provider runtime state
        providers_state = []
        for p in manager.providers:
            entry = {
                "name":          p.name,
                "priority":      getattr(p, "priority", None),
                "configured":    await p.is_configured(),
                "circuit_open":  manager._breakers[p.name].open,
                "backed_off":    p.is_backed_off(),
                "backoff_state": p.backoff_state() if hasattr(p, "backoff_state") else None,
            }
            fp = getattr(p, "_api_key", "")
            entry["api_key_fingerprint"] = (fp[:4] + "…" + fp[-2:]) if fp and len(fp) > 6 else None
            providers_state.append(entry)

        return {
            "runtime": {
                "mongo_url_env_present": bool(_os.environ.get("MONGO_URL")),
                "mongo_host":            addr,
                "db_name":               db_name,
                "db_name_env":           _os.environ.get("DB_NAME"),
                "market_debug_enabled":  _is_debug_enabled(),
                "canonical_collection":  _ks.CANONICAL_COLL,
                "canonical_id":          _ks.CANONICAL_ID,
                "backend_pid":           _os.getpid(),
                "hostname":              _os.uname().nodename,
            },
            "key_locations":   key_locations,
            "providers_state": providers_state,
            "universe":        manager.universe,
            "refresh_interval_sec": manager.refresh_interval_sec,
        }

    # -------------------------------------------------------------------- #
    # /api/market/debug/xauusd     (shorthand)
    # -------------------------------------------------------------------- #
    @r.get("/xauusd")
    async def debug_xauusd(
        dry_run: bool = Query(True, description="If false, attempts a real cache write"),
        admin=Depends(get_current_admin),
    ):
        _require_super(admin)
        return await _trace_symbol("XAUUSD", dry_run=dry_run, admin=admin)

    # -------------------------------------------------------------------- #
    # /api/market/debug/quote?symbol=EURUSD
    # -------------------------------------------------------------------- #
    @r.get("/quote")
    async def debug_quote(
        symbol: str = Query("XAUUSD", min_length=3, max_length=12),
        dry_run: bool = Query(True),
        admin=Depends(get_current_admin),
    ):
        _require_super(admin)
        return await _trace_symbol(symbol.upper(), dry_run=dry_run, admin=admin)

    async def _trace_symbol(sym: str, *, dry_run: bool,
                              admin: Dict[str, Any]) -> Dict[str, Any]:
        """Full end-to-end trace for a single symbol."""
        started_at = datetime.now(timezone.utc)
        trace: Dict[str, Any] = {
            "symbol":       sym,
            "dry_run":      dry_run,
            "started_at":   started_at.isoformat(),
            "debug_enabled": _is_debug_enabled(),
            "stages":       [],
        }

        def _stage(name: str, ok: bool, **details) -> None:
            trace["stages"].append({
                "stage":  name,
                "ok":     bool(ok),
                "at":     datetime.now(timezone.utc).isoformat(),
                "details": details,
            })

        # ---- Stage 1: Locate TwelveData provider on the running manager ---
        td: Optional[TwelveDataProvider] = None
        for p in manager.providers:
            if p.name == "twelvedata":
                td = p       # type: ignore[assignment]
                break
        if td is None:
            _stage("locate_provider", False, error="twelvedata provider not registered")
            trace["result"] = "ERROR_PROVIDER_MISSING"
            await _audit(admin, sym, trace)
            return trace

        api_key_present = bool(td._api_key)  # type: ignore[attr-defined]
        key_finger = (td._api_key[:4] + "…" + td._api_key[-2:]) if api_key_present else None  # type: ignore[attr-defined]
        _stage("locate_provider", True,
               provider="twelvedata", api_key_configured=api_key_present,
               api_key_fingerprint=key_finger,
               circuit_open=manager._breakers["twelvedata"].open,
               backoff=td.backoff_state())

        # ---- Stage 2: DB config vs in-memory key sanity check -------------
        db_key = ""
        try:
            doc = await manager.db[manager._CONF_COLL].find_one({"_id": "active"})
            db_key = (doc or {}).get("twelvedata_api_key", "") or ""
        except Exception as _e:
            _stage("read_db_config", False, error=f"{type(_e).__name__}: {_e}")
        else:
            _stage("read_db_config", True,
                   db_key_present=bool(db_key),
                   db_key_fingerprint=(db_key[:4] + "…" + db_key[-2:]) if db_key else None,
                   matches_in_memory=(db_key.strip() == (td._api_key or "").strip()))  # type: ignore[attr-defined]

        # ---- Stage 3: Symbol → TwelveData mapping ------------------------
        td_sym = SYMBOL_MAP.get(sym, sym)
        _stage("symbol_map", True, canonical=sym, twelvedata_symbol=td_sym)

        # ---- Stage 4: Raw HTTP fetch (single symbol, isolated) ------------
        raw_status = None
        raw_body_preview: Optional[str] = None
        raw_headers_pub: Dict[str, str] = {}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=8.0) as client:
                params = {"symbol": td_sym, "apikey": td._api_key or "MISSING"}  # type: ignore[attr-defined]
                hr = await client.get(f"{BASE_URL}/quote", params=params)
            raw_status = hr.status_code
            raw_body_preview = _redact_api_key(hr.text[:1000], td._api_key or "")  # type: ignore[attr-defined]
            for h in ("api-credits-left", "api-daily-credits-left",
                      "X-RateLimit-Remaining", "content-type"):
                v = hr.headers.get(h)
                if v is not None:
                    raw_headers_pub[h] = v
            _stage("http_fetch", raw_status < 400, status_code=raw_status,
                   headers=raw_headers_pub,
                   body_preview=raw_body_preview[:600] if raw_body_preview else None)
        except Exception as _e:
            _stage("http_fetch", False, error=f"{type(_e).__name__}: {_e}")
            trace["result"] = "ERROR_HTTP"
            await _audit(admin, sym, trace)
            return trace

        # ---- Stage 5: JSON parse ----------------------------------------
        parsed_body: Any = None
        try:
            import json as _json
            parsed_body = _json.loads(raw_body_preview) if raw_body_preview else None
        except Exception as _e:
            _stage("json_parse", False, error=f"{type(_e).__name__}: {_e}")
            trace["result"] = "ERROR_JSON"
            await _audit(admin, sym, trace)
            return trace
        redacted_body = _redact_payload(parsed_body)
        _stage("json_parse", True, redacted_body=redacted_body)

        # ---- Stage 6: Provider parser (`_fetch_quotes` for JUST this symbol)
        parsed_quote: Optional[Dict[str, Any]] = None
        parser_error: Optional[str] = None
        try:
            quotes = await td._fetch_quotes([sym])  # type: ignore[attr-defined]
            q = quotes.get(sym)
            if q is not None:
                parsed_quote = {
                    "symbol": q.symbol, "price": q.price,
                    "bid": q.bid, "ask": q.ask, "change_pct": q.change_pct,
                    "provider": q.provider,
                    "ts": q.ts.isoformat() if isinstance(q.ts, datetime) else str(q.ts),
                }
                _stage("provider_parse", True, quote=parsed_quote)
            else:
                _stage("provider_parse", False,
                       error=f"no quote returned by parser for {sym} "
                             f"(parser returned {list(quotes.keys())})")
                parser_error = "PARSER_DROPPED_SYMBOL"
        except RateLimitError as _e:
            _stage("provider_parse", False, error=f"RateLimitError: {_e}",
                   backoff=td.backoff_state())
            parser_error = "RATE_LIMITED"
        except ProviderNotConfigured as _e:
            _stage("provider_parse", False, error=f"ProviderNotConfigured: {_e}")
            parser_error = "NOT_CONFIGURED"
        except Exception as _e:
            msg = str(_e)
            _stage("provider_parse", False, error=f"{type(_e).__name__}: {msg}")
            # Map common HTTP-status errors to explicit verdicts so the
            # operator can tell at a glance whether the key is invalid,
            # over quota, or a transient network problem.
            if raw_status == 401 or "401" in msg or "apikey" in msg.lower():
                parser_error = "INVALID_API_KEY"
            elif raw_status == 429 or "429" in msg or "rate limit" in msg.lower():
                parser_error = "RATE_LIMITED"
            elif raw_status and raw_status >= 500:
                parser_error = "PROVIDER_5XX"
            else:
                parser_error = f"EXCEPTION_{type(_e).__name__}"

        # ---- Stage 7: Cache write attempt --------------------------------
        cache_result: Dict[str, Any] = {"attempted": False}
        if parsed_quote and not dry_run:
            try:
                q_obj = Quote(
                    symbol=parsed_quote["symbol"],
                    price=float(parsed_quote["price"]),
                    provider="twelvedata",
                    change_pct=parsed_quote.get("change_pct"),
                )
                res = await manager.cache.put_many({sym: q_obj})
                cache_result = {
                    "attempted": True,
                    "accepted":  res.get("accepted", 0),
                    "rejected":  res.get("rejected", 0),
                }
                _stage("cache_write", True, **cache_result)
            except Exception as _e:
                _stage("cache_write", False, error=f"{type(_e).__name__}: {_e}")
                cache_result = {"attempted": True, "error": f"{type(_e).__name__}: {_e}"}
        else:
            _stage("cache_write",
                   True if parsed_quote else False,
                   skipped=True,
                   reason=("dry_run=true (no write attempted)" if parsed_quote
                            else "no parsed_quote — nothing to write"))

        # ---- Stage 8: Mongo document snapshot ----------------------------
        mongo_doc = await manager.cache.get(sym)
        if mongo_doc and isinstance(mongo_doc.get("updated_at"), datetime):
            mongo_doc["updated_at"] = mongo_doc["updated_at"].isoformat()
        if mongo_doc and isinstance(mongo_doc.get("provider_ts"), datetime):
            mongo_doc["provider_ts"] = mongo_doc["provider_ts"].isoformat()
        _stage("mongo_read", mongo_doc is not None, doc=mongo_doc)

        # ---- Stage 9: Recent cache-write audit for this symbol -----------
        recent = await manager.cache.recent_writes(symbol=sym, limit=8)
        _stage("recent_writes", True, count=len(recent), rows=recent)

        # ---- Verdict -----------------------------------------------------
        if parser_error:
            trace["result"] = parser_error
        elif not parsed_quote:
            trace["result"] = "PARSED_NONE"
        elif dry_run:
            trace["result"] = "OK_DRY_RUN"
        elif cache_result.get("accepted", 0) >= 1:
            trace["result"] = "OK_WRITTEN"
        elif cache_result.get("rejected", 0) >= 1:
            trace["result"] = "REJECTED_BY_GUARD"
        else:
            trace["result"] = "OK"

        trace["ended_at"] = datetime.now(timezone.utc).isoformat()
        await _audit(admin, sym, {"result": trace["result"], "dry_run": dry_run,
                                    "stages_count": len(trace["stages"])})
        logger.info("market debug trace symbol=%s result=%s dry_run=%s",
                    sym, trace["result"], dry_run)
        return trace

    app.include_router(r)
    return r
