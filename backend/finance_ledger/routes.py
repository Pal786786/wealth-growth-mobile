"""Sprint 12.3 · Phase A — Finance Ledger HTTP surface.

User endpoints:
    GET  /api/wallet/passbook                — running-balance passbook
    GET  /api/wallet/passbook/{journal_id}   — single journal entry view

Admin endpoints:
    GET  /api/admin/ledger/journal           — search all journal entries
    GET  /api/admin/ledger/balances          — all CoA balances
    GET  /api/admin/ledger/balance/{account} — one CoA balance
    POST /api/admin/ledger/reverse/{jid}     — write reverse entry
    GET  /api/admin/ledger/audit             — enhanced audit trail query
    POST /api/admin/ledger/backfill          — one-time migration (dry_run|apply)
    GET  /api/admin/ledger/backfill/status   — latest migration run
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body, Request

from .engine import (
    Journal, JOURNAL_COLL, BALANCE_COLL,
    coa_user_wallet, get_default_journal,
)
from .audit import AuditTrail, audit, get_default_trail
from .backfill import Backfiller

logger = logging.getLogger("finance_ledger.routes")


def attach(app, db, get_current_user, get_current_admin):
    api = APIRouter()

    async def _j() -> Journal:
        j = get_default_journal()
        if j is None:
            raise HTTPException(500, "ledger engine not initialised")
        return j

    async def _t() -> AuditTrail:
        t = get_default_trail()
        if t is None:
            raise HTTPException(500, "audit engine not initialised")
        return t

    # ============================================================ USER
    @api.get("/wallet/passbook")
    async def user_passbook(
        request: Request,
        limit: int = Query(50, ge=1, le=200),
        skip: int = Query(0, ge=0),
        date_from: Optional[str] = Query(None),
        date_to: Optional[str] = Query(None),
        user=Depends(get_current_user),
    ):
        df = _parse_dt(date_from)
        dt = _parse_dt(date_to)
        j = await _j()
        result = await j.user_passbook(user["user_id"], limit=limit, skip=skip,
                                         date_from=df, date_to=dt)
        # Light-weight audit — a user viewing their own passbook is not a
        # security-sensitive action but keep a trace so we can detect scraping.
        try:
            await audit(actor_id=user["user_id"], actor_type="user",
                         action="passbook.view", resource_type="user_passbook",
                         resource_id=user["user_id"], request=request,
                         metadata={"limit": limit, "skip": skip})
        except Exception:
            pass
        return result

    @api.get("/wallet/passbook/{journal_id}")
    async def user_journal_view(journal_id: str, user=Depends(get_current_user)):
        entry = await db[JOURNAL_COLL].find_one(
            {"journal_id": journal_id, "user_id": user["user_id"]}, {"_id": 0},
        )
        if not entry:
            raise HTTPException(404, "Journal entry not found")
        return entry

    # ============================================================ ADMIN
    @api.get("/admin/ledger/journal")
    async def admin_search_journal(
        limit: int = Query(50, ge=1, le=500),
        skip: int = Query(0, ge=0),
        user_id: Optional[str] = None,
        txn_type: Optional[str] = None,
        reference_id: Optional[str] = None,
        reference_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        include_reversed: bool = True,
        adm=Depends(get_current_admin),
    ):
        q: Dict[str, Any] = {}
        if user_id: q["user_id"] = user_id
        if txn_type: q["txn_type"] = txn_type
        if reference_id: q["reference_id"] = reference_id
        if reference_type: q["reference_type"] = reference_type
        if not include_reversed:
            q["is_reversed"] = {"$ne": True}
        df = _parse_dt(date_from); dt = _parse_dt(date_to)
        if df or dt:
            q["entry_date"] = {}
            if df: q["entry_date"]["$gte"] = df
            if dt: q["entry_date"]["$lte"] = dt
        total = await db[JOURNAL_COLL].count_documents(q)
        rows = await db[JOURNAL_COLL].find(q, {"_id": 0}).sort("entry_date", -1)\
                                       .skip(skip).limit(limit).to_list(limit)
        return {"items": rows, "total": total}

    @api.get("/admin/ledger/balances")
    async def admin_balances(adm=Depends(get_current_admin)):
        rows = await db[BALANCE_COLL].find({}, {"_id": 0}).sort("account", 1).to_list(2000)
        return {"items": rows, "total": len(rows)}

    @api.get("/admin/ledger/balance/{account:path}")
    async def admin_balance(account: str, adm=Depends(get_current_admin)):
        j = await _j()
        return {"account": account, "balance": await j.balance(account)}

    @api.post("/admin/ledger/reverse/{journal_id}")
    async def admin_reverse(
        journal_id: str, request: Request,
        body: Dict[str, Any] = Body(default_factory=dict),
        adm=Depends(get_current_admin),
    ):
        if adm.get("role") not in ("super_admin", "admin"):
            raise HTTPException(403, "Insufficient permissions")
        j = await _j()
        original = await db[JOURNAL_COLL].find_one({"journal_id": journal_id}, {"_id": 0})
        if not original:
            raise HTTPException(404, "Journal not found")
        narration = (body.get("narration") or f"Admin reversal by {adm['admin_id']}").strip()
        try:
            reversed_entry = await j.reverse(journal_id, posted_by=f"admin:{adm['admin_id']}",
                                              narration=narration)
        except ValueError as e:
            raise HTTPException(400, str(e))
        await audit(
            actor_id=adm["admin_id"], actor_type="admin",
            action="ledger.reverse", resource_type="journal_entry",
            resource_id=journal_id, before=original,
            after={"reversal_id": reversed_entry["journal_id"], "narration": narration},
            reference_id=original.get("reference_id"), request=request,
            metadata={"reason": narration},
        )
        return {"ok": True, "reversal": reversed_entry}

    @api.get("/admin/ledger/audit")
    async def admin_audit_query(
        limit: int = Query(100, ge=1, le=500),
        skip: int = Query(0, ge=0),
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action_prefix: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        adm=Depends(get_current_admin),
    ):
        t = await _t()
        return await t.query(
            actor_id=actor_id, resource_type=resource_type,
            resource_id=resource_id, action_prefix=action_prefix,
            date_from=_parse_dt(date_from), date_to=_parse_dt(date_to),
            limit=limit, skip=skip,
        )

    # ============================================================ BACKFILL
    @api.post("/admin/ledger/backfill")
    async def admin_backfill(
        request: Request,
        body: Dict[str, Any] = Body(default_factory=dict),
        adm=Depends(get_current_admin),
    ):
        if adm.get("role") not in ("super_admin", "admin"):
            raise HTTPException(403, "Insufficient permissions")
        dry_run = bool(body.get("dry_run", True))
        modules: Optional[List[str]] = body.get("modules") or None
        b = Backfiller(db)
        result = await b.run(dry_run=dry_run, modules=modules,
                              triggered_by=adm["admin_id"], request=request)
        await audit(
            actor_id=adm["admin_id"], actor_type="admin",
            action="ledger.backfill." + ("dry_run" if dry_run else "apply"),
            resource_type="finance_backfill", resource_id=result["run_id"],
            after={k: v for k, v in result.items() if k not in ("errors_sample",)},
            request=request,
        )
        return result

    @api.get("/admin/ledger/backfill/status")
    async def admin_backfill_status(adm=Depends(get_current_admin)):
        run = await db.finance_migrations.find_one(
            {}, {"_id": 0}, sort=[("created_at", -1)],
        )
        return {"last_run": run}

    app.include_router(api, prefix="/api", tags=["finance-ledger"])


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            from datetime import timezone as _tz
            return dt.replace(tzinfo=_tz.utc)
        except ValueError:
            continue
    return None
