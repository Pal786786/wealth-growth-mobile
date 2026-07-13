"""Sprint 12.3 · Phase A + B — Finance Ledger HTTP surface.

Phase A user endpoints (passbook), admin endpoints (journal, balances,
reverse, audit, backfill).

Phase B admin endpoints:
    POST /api/admin/finance/reconcile                       — run reconciliation (read-only)
    GET  /api/admin/finance/mismatches                      — list mismatch queue
    POST /api/admin/finance/mismatches/{pair_key}/retry     — re-run recon for one item
    POST /api/admin/finance/mismatches/{pair_key}/resolve   — mark resolved w/ notes
    POST /api/admin/finance/mismatches/{pair_key}/ignore    — mark ignored w/ notes
    POST /api/admin/finance/mismatches/{pair_key}/note      — append admin note (audited)
    GET  /api/admin/finance/reconciliation/runs             — recon run history

    GET  /api/admin/finance/dashboard                       — KPIs (today | week | month | quarter | year | custom)
    GET  /api/admin/finance/settlements/{provider}          — Razorpay / Cashfree settlements

    GET  /api/admin/finance/reports/{report_type}.{fmt}     — pdf | xlsx | csv  (streaming)
    GET  /api/admin/finance/reports                         — list available report types
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Body, Request
from fastapi.responses import Response, StreamingResponse

from .engine import (
    Journal, JOURNAL_COLL, BALANCE_COLL,
    coa_user_wallet, get_default_journal,
)
from .audit import AuditTrail, audit, get_default_trail
from .backfill import Backfiller
from .reconciliation import Reconciler, RECON_COLL, RECON_RUNS_COLL
from .kpi import compute_dashboard, build_report_data, provider_settlements
from .reports import render_pdf, render_excel, render_csv

logger = logging.getLogger("finance_ledger.routes")


REPORT_TYPES = [
    "daily", "weekly", "monthly", "quarterly", "yearly",
    "deposit", "withdrawal", "gold", "mf", "forex", "fees", "tax",
]
REPORT_FORMATS = {"pdf": "application/pdf",
                    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "csv": "text/csv"}
REPORT_RANGE_DAYS = {"daily": 1, "weekly": 7, "monthly": 30,
                       "quarterly": 90, "yearly": 365}


def attach(app, db, get_current_user, get_current_admin):
    api = APIRouter()
    reconciler = Reconciler(db)

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

    # ============================================================ ADMIN — Phase A
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
        await audit(actor_id=adm["admin_id"], actor_type="admin",
                     action="ledger.reverse", resource_type="journal_entry",
                     resource_id=journal_id, before=original,
                     after={"reversal_id": reversed_entry["journal_id"], "narration": narration},
                     reference_id=original.get("reference_id"), request=request,
                     metadata={"reason": narration})
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
        return await t.query(actor_id=actor_id, resource_type=resource_type,
                              resource_id=resource_id, action_prefix=action_prefix,
                              date_from=_parse_dt(date_from), date_to=_parse_dt(date_to),
                              limit=limit, skip=skip)

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
        await audit(actor_id=adm["admin_id"], actor_type="admin",
                     action="ledger.backfill." + ("dry_run" if dry_run else "apply"),
                     resource_type="finance_backfill", resource_id=result["run_id"],
                     after={k: v for k, v in result.items() if k not in ("errors_sample",)},
                     request=request)
        return result

    @api.get("/admin/ledger/backfill/status")
    async def admin_backfill_status(adm=Depends(get_current_admin)):
        run = await db.finance_migrations.find_one(
            {}, {"_id": 0}, sort=[("created_at", -1)],
        )
        return {"last_run": run}

    # ============================================================ ADMIN — Phase B
    @api.post("/admin/finance/reconcile")
    async def admin_reconcile(
        request: Request,
        body: Dict[str, Any] = Body(default_factory=dict),
        adm=Depends(get_current_admin),
    ):
        modules = body.get("modules") or None
        summary = await reconciler.run(modules=modules, triggered_by=adm["admin_id"])
        await audit(actor_id=adm["admin_id"], actor_type="admin",
                     action="finance.reconcile.run",
                     resource_type="finance_reconciliation", resource_id=summary["run_id"],
                     after={k: v for k, v in summary.items() if k != "per_module"},
                     request=request)
        return summary

    @api.get("/admin/finance/mismatches")
    async def admin_mismatches(
        status: Optional[str] = None,
        module: Optional[str] = None,
        limit: int = Query(50, ge=1, le=500),
        skip: int = Query(0, ge=0),
        adm=Depends(get_current_admin),
    ):
        q: Dict[str, Any] = {}
        if status: q["status"] = status
        else: q["status"] = {"$in": ["mismatch", "manual_review", "pending"]}
        if module: q["module"] = module
        total = await db[RECON_COLL].count_documents(q)
        rows = await db[RECON_COLL].find(q, {"_id": 0}).sort("ran_at", -1)\
                                     .skip(skip).limit(limit).to_list(limit)
        return {"items": rows, "total": total}

    async def _load_recon(pair_key: str) -> Dict[str, Any]:
        row = await db[RECON_COLL].find_one({"pair_key": pair_key}, {"_id": 0})
        if not row:
            raise HTTPException(404, "Reconciliation record not found")
        return row

    @api.post("/admin/finance/mismatches/{pair_key:path}/retry")
    async def admin_mismatch_retry(
        pair_key: str, request: Request,
        adm=Depends(get_current_admin),
    ):
        row = await _load_recon(pair_key)
        summary = await reconciler.run(modules=[row["module"]],
                                          triggered_by=adm["admin_id"])
        refreshed = await db[RECON_COLL].find_one({"pair_key": pair_key}, {"_id": 0})
        await audit(actor_id=adm["admin_id"], actor_type="admin",
                     action="finance.mismatch.retry",
                     resource_type="finance_reconciliation", resource_id=pair_key,
                     before={"status": row["status"], "reason": row["reason"]},
                     after={"status": (refreshed or {}).get("status"),
                             "reason": (refreshed or {}).get("reason")},
                     request=request)
        return {"ok": True, "recon": refreshed, "run": summary["run_id"]}

    @api.post("/admin/finance/mismatches/{pair_key:path}/resolve")
    async def admin_mismatch_resolve(
        pair_key: str, request: Request,
        body: Dict[str, Any] = Body(default_factory=dict),
        adm=Depends(get_current_admin),
    ):
        row = await _load_recon(pair_key)
        note = (body.get("note") or body.get("notes") or "").strip()
        from datetime import datetime as _dt, timezone as _tz
        upd = {
            "status": "resolved_matched", "resolution": "resolved",
            "resolved_by": adm["admin_id"],
            "resolved_at": _dt.now(_tz.utc),
        }
        push = {"admin_notes": {"note": note, "by": adm["admin_id"],
                                 "at": _dt.now(_tz.utc),
                                 "action": "resolve"}} if note else None
        await db[RECON_COLL].update_one({"pair_key": pair_key},
                                           {"$set": upd, **({"$push": push} if push else {})})
        after = await db[RECON_COLL].find_one({"pair_key": pair_key}, {"_id": 0})
        await audit(actor_id=adm["admin_id"], actor_type="admin",
                     action="finance.mismatch.resolve",
                     resource_type="finance_reconciliation", resource_id=pair_key,
                     before={"status": row["status"], "reason": row["reason"]},
                     after={"status": after.get("status"), "note": note},
                     request=request)
        return {"ok": True, "recon": after}

    @api.post("/admin/finance/mismatches/{pair_key:path}/ignore")
    async def admin_mismatch_ignore(
        pair_key: str, request: Request,
        body: Dict[str, Any] = Body(default_factory=dict),
        adm=Depends(get_current_admin),
    ):
        row = await _load_recon(pair_key)
        note = (body.get("note") or "").strip()
        from datetime import datetime as _dt, timezone as _tz
        await db[RECON_COLL].update_one({"pair_key": pair_key},
            {"$set": {"status": "ignored", "resolution": "ignored",
                       "resolved_by": adm["admin_id"], "resolved_at": _dt.now(_tz.utc)},
             "$push": {"admin_notes": {"note": note, "by": adm["admin_id"],
                                          "at": _dt.now(_tz.utc), "action": "ignore"}}})
        after = await db[RECON_COLL].find_one({"pair_key": pair_key}, {"_id": 0})
        await audit(actor_id=adm["admin_id"], actor_type="admin",
                     action="finance.mismatch.ignore",
                     resource_type="finance_reconciliation", resource_id=pair_key,
                     before={"status": row["status"]}, after={"status": "ignored"},
                     request=request, metadata={"note": note})
        return {"ok": True, "recon": after}

    @api.post("/admin/finance/mismatches/{pair_key:path}/note")
    async def admin_mismatch_note(
        pair_key: str, request: Request,
        body: Dict[str, Any] = Body(...),
        adm=Depends(get_current_admin),
    ):
        note = (body.get("note") or "").strip()
        if not note:
            raise HTTPException(400, "note required")
        row = await _load_recon(pair_key)
        from datetime import datetime as _dt, timezone as _tz
        await db[RECON_COLL].update_one({"pair_key": pair_key},
            {"$push": {"admin_notes": {"note": note, "by": adm["admin_id"],
                                          "at": _dt.now(_tz.utc), "action": "note"}}})
        await audit(actor_id=adm["admin_id"], actor_type="admin",
                     action="finance.mismatch.note",
                     resource_type="finance_reconciliation", resource_id=pair_key,
                     metadata={"note": note}, request=request)
        return {"ok": True}

    @api.get("/admin/finance/reconciliation/runs")
    async def admin_recon_runs(limit: int = Query(20, ge=1, le=200),
                                 adm=Depends(get_current_admin)):
        rows = await db[RECON_RUNS_COLL].find({}, {"_id": 0})\
                    .sort("started_at", -1).limit(limit).to_list(limit)
        return {"items": rows, "total": len(rows)}

    @api.get("/admin/finance/dashboard")
    async def admin_dashboard(
        range: str = Query("month", regex="^(today|week|month|quarter|year|custom)$"),
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        adm=Depends(get_current_admin),
    ):
        return await compute_dashboard(db, range_key=range,
                                          date_from=_parse_dt(date_from),
                                          date_to=_parse_dt(date_to))

    @api.get("/admin/finance/settlements/{provider}")
    async def admin_settlements(provider: str,
                                  limit: int = Query(100, ge=1, le=500),
                                  skip: int = Query(0, ge=0),
                                  date_from: Optional[str] = None,
                                  date_to: Optional[str] = None,
                                  adm=Depends(get_current_admin)):
        try:
            return await provider_settlements(db, provider, limit=limit, skip=skip,
                                                 date_from=_parse_dt(date_from),
                                                 date_to=_parse_dt(date_to))
        except ValueError as e:
            raise HTTPException(400, str(e))

    @api.get("/admin/finance/reports")
    async def admin_report_list(adm=Depends(get_current_admin)):
        return {"types": REPORT_TYPES, "formats": list(REPORT_FORMATS.keys())}

    @api.get("/admin/finance/reports/{report_type}.{fmt}")
    async def admin_report_download(
        report_type: str, fmt: str, request: Request,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        provider: Optional[str] = None, module: Optional[str] = None,
        user_id: Optional[str] = None, status: Optional[str] = None,
        adm=Depends(get_current_admin),
    ):
        if report_type not in REPORT_TYPES:
            raise HTTPException(400, f"Unsupported report_type. Allowed: {REPORT_TYPES}")
        if fmt not in REPORT_FORMATS:
            raise HTTPException(400, f"Unsupported format. Allowed: {list(REPORT_FORMATS)}")
        df = _parse_dt(date_from); dt = _parse_dt(date_to)
        if not df or not dt:
            from datetime import datetime as _dt, timedelta as _td, timezone as _tz
            days = REPORT_RANGE_DAYS.get(report_type, 30)
            dt = dt or _dt.now(_tz.utc)
            df = df or (dt - _td(days=days))
        data = await build_report_data(db, report_type, df, dt,
                                          provider=provider, module=module,
                                          user_id=user_id, status=status)
        try:
            if fmt == "pdf":
                payload = render_pdf(data)
            elif fmt == "xlsx":
                payload = render_excel(data)
            else:
                payload = render_csv(data)
        except Exception as e:
            logger.exception("report render failed")
            raise HTTPException(500, f"report render failed: {e}")
        from datetime import datetime as _dt2
        fname = f"mfb_{report_type}_{_dt2.utcnow().strftime('%Y%m%d_%H%M%S')}.{fmt}"
        await audit(actor_id=adm["admin_id"], actor_type="admin",
                     action=f"finance.report.export.{fmt}",
                     resource_type="finance_report", resource_id=report_type,
                     metadata={"filters": {"date_from": str(df), "date_to": str(dt),
                                              "provider": provider, "module": module,
                                              "user_id": user_id, "status": status},
                                "bytes": len(payload)},
                     request=request)
        return Response(content=payload, media_type=REPORT_FORMATS[fmt], headers={
            "Content-Disposition": f'attachment; filename="{quote(fname)}"',
            "Cache-Control": "no-store",
            "X-Report-Rows": str(data.get("entry_count", 0)),
        })

    app.include_router(api, prefix="/api", tags=["finance-ledger"])

    # ensure reconciler indexes on startup
    @app.on_event("startup")
    async def _recon_indexes():
        try:
            await reconciler.ensure_indexes()
        except Exception as _e:
            logger.warning(f"reconciliation indexes failed: {_e}")


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
