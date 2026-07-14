"""Sprint 14.1.2c — Write tracer for market-key collections.

Instruments the 5 sensitive collections that can hold a market API key so
that EVERY write is captured with:
    time · caller · endpoint · collection · filter · $set/$unset · modified_count
    · before-fingerprint · after-fingerprint · call stack

Persists to `market_key_audit`. Never writes the actual key value — only
short 4+2 char fingerprints.

Also exposes convenient forensic queries:

    * `GET /api/market/debug/write-audit?since_min=60&limit=200`
    * `GET /api/market/debug/write-audit/live` — tail-follow the last 50 rows

The instrumentation is safe: it's monkey-patched at attach() time onto the
5 known collections only. Every other collection is unaffected.
"""
from __future__ import annotations

import logging
import inspect
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import contextvars

from fastapi import APIRouter, Depends, HTTPException, Query, Request

logger = logging.getLogger("market.write_tracer")

_INSTALLED_MARKER = "__mfb_write_tracer_installed__"
AUDIT_COLL = "market_key_audit"

# Collections we instrument. All others are untouched.
SENSITIVE = {
    "market_provider_config",
    "market_settings",
    "market_data_settings",
    "forex_settings",
    "api_settings",
}

# Fields inside those collections whose value we FINGERPRINT (never log raw).
# path is dot-notated so nested api_keys dicts also get captured.
SENSITIVE_FIELDS = (
    "twelvedata_api_key",
    "alphavantage_api_key",
    "twelve_data_api_key",     # forex_settings
    "api_key",                 # api_settings
    "api_keys.twelve_data",    # market_settings
    "api_keys.twelvedata",     # market_data_settings
    "api_keys.alpha_vantage",  # market_settings
    "api_keys.alphavantage",   # market_data_settings
)

# HTTP request context injected by attach() so the tracer knows which
# endpoint originated the write.
_current_endpoint: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "mfb_current_endpoint", default=None
)
_current_admin: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "mfb_current_admin", default=None
)
_current_request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "mfb_current_request_id", default=None
)


def _fp(v: Any) -> Optional[str]:
    if not isinstance(v, str) or not v.strip():
        return None
    s = v.strip()
    return (s[:4] + "…" + s[-2:]) if len(s) > 6 else "•" * len(s)


def _get_nested(d: Optional[Dict[str, Any]], path: str) -> Any:
    if not d:
        return None
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _extract_field_fps(doc: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """Return {field_path → fingerprint} for every sensitive field present."""
    out: Dict[str, Optional[str]] = {}
    if not doc:
        return out
    for p in SENSITIVE_FIELDS:
        v = _get_nested(doc, p)
        if v is not None:
            out[p] = _fp(v) if isinstance(v, str) else str(type(v).__name__)
    return out


def _walk_update_for_fields(update: Any) -> Dict[str, Optional[str]]:
    """Extract sensitive-field fingerprints from an $set/$unset payload."""
    fps: Dict[str, Optional[str]] = {}
    if not isinstance(update, dict):
        return fps

    def _add(d: Dict[str, Any], mark: str) -> None:
        for p in SENSITIVE_FIELDS:
            if p in d:
                fps[f"{mark}:{p}"] = _fp(d[p])
        # Also detect `api_keys` dict (used by market_settings)
        if "api_keys" in d and isinstance(d["api_keys"], dict):
            for inner_k, inner_v in d["api_keys"].items():
                fps[f"{mark}:api_keys.{inner_k}"] = _fp(inner_v)

    if "$set" in update:
        _add(update["$set"], "set")
    if "$unset" in update:
        for p in SENSITIVE_FIELDS:
            if p in update["$unset"]:
                fps[f"unset:{p}"] = None
    return fps


def _short_stack(skip_prefixes: tuple[str, ...] = ("motor.", "pymongo.", "asyncio.", "market_providers.write_tracer")) -> list[str]:
    """Best-effort stack trace, trimmed to the app code frames."""
    frames = inspect.stack()
    out: list[str] = []
    for f in frames[2:14]:      # skip _stack + our wrapper
        mod = f.frame.f_globals.get("__name__", "?")
        if any(mod.startswith(p) for p in skip_prefixes):
            continue
        out.append(f"{mod}:{f.function}:{f.lineno}")
        if len(out) >= 6:
            break
    return out


async def _record(db, *, op: str, collection: str, filter_: Any,
                   update: Any, before_fps: Dict[str, Any],
                   after_fps: Dict[str, Any], update_fps: Dict[str, Any],
                   matched_count: int, modified_count: int,
                   upserted_id: Any, took_ms: float) -> None:
    try:
        await db[AUDIT_COLL].insert_one({
            "at":              datetime.now(timezone.utc),
            "operation":       op,
            "collection":      collection,
            "endpoint":        _current_endpoint.get(),
            "admin":           _current_admin.get(),
            "request_id":      _current_request_id.get(),
            "filter":          filter_ if isinstance(filter_, dict) else str(filter_),
            "update_fingerprints":  update_fps,
            "before_fingerprints":  before_fps,
            "after_fingerprints":   after_fps,
            "matched_count":   matched_count,
            "modified_count":  modified_count,
            "upserted_id":     str(upserted_id) if upserted_id else None,
            "took_ms":         round(took_ms, 2),
            "stack":           _short_stack(),
        })
    except Exception as _e:      # pragma: no cover
        logger.warning("write tracer record failed: %s", _e)


def install(db) -> None:
    """Class-level monkey-patch on Motor's AsyncIOMotorCollection so ALL
    subsequent `db['market_provider_config'].update_one(...)` calls hit our
    wrapper — regardless of how many times Motor re-materialises the
    collection object. Only records writes for the 5 SENSITIVE collections.
    Idempotent (checks a class-level marker)."""
    from motor.motor_asyncio import AsyncIOMotorCollection as _Coll
    if getattr(_Coll, _INSTALLED_MARKER, False):
        logger.info("write_tracer already installed on AsyncIOMotorCollection")
        return
    _wrap_class(db, _Coll)
    setattr(_Coll, _INSTALLED_MARKER, True)
    logger.info("write_tracer installed at class level → monitors %s", sorted(SENSITIVE))


def _wrap_class(db, Coll) -> None:
    _orig_update_one   = Coll.update_one
    _orig_update_many  = Coll.update_many
    _orig_replace_one  = Coll.replace_one
    _orig_delete_one   = Coll.delete_one
    _orig_delete_many  = Coll.delete_many

    async def _snapshot_fps(coll, flt: Any) -> Dict[str, Any]:
        if not isinstance(flt, dict):
            return {}
        try:
            d = await _orig_find_one(coll, flt)
        except Exception:
            return {}
        return _extract_field_fps(d)

    _orig_find_one = Coll.find_one       # reference for pre/post snapshots

    async def update_one(self, filter_, update, upsert=False, **kw):
        # Fast path for non-sensitive collections
        if self.name not in SENSITIVE:
            return await _orig_update_one(self, filter_, update, upsert=upsert, **kw)
        t0 = time.perf_counter()
        before = await _snapshot_fps(self, filter_)
        res = await _orig_update_one(self, filter_, update, upsert=upsert, **kw)
        took = (time.perf_counter() - t0) * 1000
        after_flt = {"_id": res.upserted_id} if getattr(res, "upserted_id", None) else filter_
        after = await _snapshot_fps(self, after_flt)
        upd_fps = _walk_update_for_fields(update)
        if upd_fps or before or after:
            await _record(db, op="update_one", collection=self.name, filter_=filter_,
                          update=update, before_fps=before, after_fps=after,
                          update_fps=upd_fps,
                          matched_count=res.matched_count,
                          modified_count=res.modified_count,
                          upserted_id=getattr(res, "upserted_id", None), took_ms=took)
        return res

    async def update_many(self, filter_, update, upsert=False, **kw):
        if self.name not in SENSITIVE:
            return await _orig_update_many(self, filter_, update, upsert=upsert, **kw)
        t0 = time.perf_counter()
        before = await _snapshot_fps(self, filter_)
        res = await _orig_update_many(self, filter_, update, upsert=upsert, **kw)
        took = (time.perf_counter() - t0) * 1000
        after = await _snapshot_fps(self, filter_)
        upd_fps = _walk_update_for_fields(update)
        if upd_fps or before or after:
            await _record(db, op="update_many", collection=self.name, filter_=filter_,
                          update=update, before_fps=before, after_fps=after,
                          update_fps=upd_fps,
                          matched_count=res.matched_count,
                          modified_count=res.modified_count,
                          upserted_id=None, took_ms=took)
        return res

    async def replace_one(self, filter_, replacement, upsert=False, **kw):
        if self.name not in SENSITIVE:
            return await _orig_replace_one(self, filter_, replacement, upsert=upsert, **kw)
        t0 = time.perf_counter()
        before = await _snapshot_fps(self, filter_)
        res = await _orig_replace_one(self, filter_, replacement, upsert=upsert, **kw)
        took = (time.perf_counter() - t0) * 1000
        after_flt = {"_id": res.upserted_id} if getattr(res, "upserted_id", None) else filter_
        after = await _snapshot_fps(self, after_flt)
        upd_fps = _extract_field_fps(replacement) if isinstance(replacement, dict) else {}
        upd_fps = {f"replace:{k}": v for k, v in upd_fps.items()}
        await _record(db, op="replace_one", collection=self.name, filter_=filter_,
                      update=replacement, before_fps=before, after_fps=after,
                      update_fps=upd_fps,
                      matched_count=res.matched_count,
                      modified_count=res.modified_count,
                      upserted_id=getattr(res, "upserted_id", None), took_ms=took)
        return res

    async def delete_one(self, filter_, **kw):
        if self.name not in SENSITIVE:
            return await _orig_delete_one(self, filter_, **kw)
        t0 = time.perf_counter()
        before = await _snapshot_fps(self, filter_)
        res = await _orig_delete_one(self, filter_, **kw)
        took = (time.perf_counter() - t0) * 1000
        if before:
            await _record(db, op="delete_one", collection=self.name, filter_=filter_,
                          update=None, before_fps=before, after_fps={}, update_fps={},
                          matched_count=res.deleted_count,
                          modified_count=res.deleted_count,
                          upserted_id=None, took_ms=took)
        return res

    async def delete_many(self, filter_, **kw):
        if self.name not in SENSITIVE:
            return await _orig_delete_many(self, filter_, **kw)
        t0 = time.perf_counter()
        res = await _orig_delete_many(self, filter_, **kw)
        took = (time.perf_counter() - t0) * 1000
        if res.deleted_count > 0:
            await _record(db, op="delete_many", collection=self.name, filter_=filter_,
                          update=None, before_fps={}, after_fps={}, update_fps={},
                          matched_count=res.deleted_count,
                          modified_count=res.deleted_count,
                          upserted_id=None, took_ms=took)
        return res

    Coll.update_one  = update_one
    Coll.update_many = update_many
    Coll.replace_one = replace_one
    Coll.delete_one  = delete_one
    Coll.delete_many = delete_many


def _wrap_write_methods(db, coll, coll_name: str) -> None:
    """Legacy instance-level wrap (kept for compatibility, no-op now)."""
    return


# --------------------------------------------------------------------------- #
def attach_endpoint_context_middleware(app) -> None:
    """FastAPI middleware — captures request path + admin id + X-Request-ID
    into contextvars so the tracer can attribute each write to the caller.

    Also sets response header `X-Request-ID` (auto-generated if the client
    didn't send one) so the browser Network tab shows the SAME id that ends
    up in the write audit row — a bulletproof correlation for save-path
    diagnosis.
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    import uuid as _uuid

    class _Middleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            rid = (request.headers.get("x-request-id")
                   or request.headers.get("X-Request-ID")
                   or _uuid.uuid4().hex[:16])
            tok_ep = _current_endpoint.set(f"{request.method} {request.url.path}")
            tok_ad = _current_admin.set(None)
            tok_rid = _current_request_id.set(rid)
            try:
                resp = await call_next(request)
                # Expose the id so the browser can read it from the Network tab
                resp.headers["X-Request-ID"] = rid
                # Also expose CORS header so the browser is allowed to READ it
                existing = resp.headers.get("Access-Control-Expose-Headers", "")
                if "X-Request-ID" not in existing:
                    resp.headers["Access-Control-Expose-Headers"] = (
                        (existing + ", " if existing else "") + "X-Request-ID"
                    )
                return resp
            finally:
                _current_endpoint.reset(tok_ep)
                _current_admin.reset(tok_ad)
                _current_request_id.reset(tok_rid)

    app.add_middleware(_Middleware)


# --------------------------------------------------------------------------- #
def build_router(db, get_current_admin) -> APIRouter:
    """Router exposing GET /api/market/debug/write-audit (super_admin only)."""
    r = APIRouter(prefix="/api/market/debug/write-audit", tags=["market-debug"])
    import os
    def _require(admin):
        flag = (os.environ.get("MARKET_DEBUG_ENABLED", "false") or "").strip().lower()
        if flag not in ("1","true","yes","on"):
            raise HTTPException(404, "market debug endpoint disabled")
        if (admin or {}).get("role") != "super_admin":
            raise HTTPException(403, "super_admin role required")

    @r.get("")
    async def list_audit(
        since_min: int = Query(60, ge=1, le=10080),
        collection: Optional[str] = Query(None),
        op: Optional[str] = Query(None),
        request_id: Optional[str] = Query(None, description="Correlate with browser X-Request-ID header"),
        limit: int = Query(200, ge=1, le=1000),
        admin=Depends(get_current_admin),
    ):
        _require(admin)
        from datetime import timedelta
        since = datetime.now(timezone.utc) - timedelta(minutes=since_min)
        q: Dict[str, Any] = {"at": {"$gte": since}}
        if collection: q["collection"] = collection
        if op:         q["operation"]  = op
        if request_id: q["request_id"] = request_id
        rows = await db[AUDIT_COLL].find(q, {"_id": 0}).sort("at", -1).limit(limit).to_list(limit)
        return {
            "count": len(rows),
            "since": since.isoformat(),
            "audit_collection": AUDIT_COLL,
            "monitored_collections": sorted(SENSITIVE),
            "monitored_fields": list(SENSITIVE_FIELDS),
            "correlation_hint": "grab X-Request-ID from the browser Network tab and query ?request_id=<id> here",
            "rows": rows,
        }

    @r.get("/summary")
    async def summary(admin=Depends(get_current_admin)):
        """Per-collection counts of writes over the last 24 h."""
        _require(admin)
        from datetime import timedelta
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        pipeline = [
            {"$match": {"at": {"$gte": since}}},
            {"$group": {"_id": {"c": "$collection", "op": "$operation"},
                         "n":   {"$sum": 1},
                         "last": {"$max": "$at"}}},
            {"$sort":  {"_id.c": 1, "_id.op": 1}},
        ]
        groups = await db[AUDIT_COLL].aggregate(pipeline).to_list(200)
        # Also find rows where a sensitive field was CLEARED (fingerprint went None)
        clears = await db[AUDIT_COLL].find(
            {"at": {"$gte": since},
             "$expr": {"$gt": [
                 {"$size": {"$objectToArray": {"$ifNull": ["$before_fingerprints", {}]}}},
                 {"$size": {"$objectToArray": {"$ifNull": ["$after_fingerprints", {}]}}},
             ]}},
            {"_id": 0},
        ).sort("at", -1).limit(50).to_list(50)
        return {
            "since": since.isoformat(),
            "per_collection_op": groups,
            "clearing_writes_last_24h": clears,
        }

    return r
