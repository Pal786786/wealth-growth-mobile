"""AI News & Analytics — Routes (Sprint 7C.2)

Public (auth required unless noted):
  News:
    GET  /api/ai/news[?category&sentiment&high_impact_only&limit]
    GET  /api/ai/news/{news_id}
  Economic Calendar:
    GET  /api/ai/calendar[?impact&country&currency&days_ahead&include_past]
    GET  /api/ai/calendar/meta
  Market Summary:
    GET  /api/ai/summary?type=intraday|daily|weekly
    GET  /api/ai/summary/history[?type&limit]
  Signal Analytics:
    GET  /api/ai/analytics/overview[?window_days]
    GET  /api/ai/analytics/by-symbol[?window_days&limit]
    GET  /api/ai/analytics/by-timeframe[?window_days]
    GET  /api/ai/analytics/history[?limit&outcome]

Admin console:
    POST   /api/ai/admin/news/generate       {categories?, per_category?}
    PUT    /api/ai/admin/news/{news_id}       {title,summary,body,high_impact,is_published}
    DELETE /api/ai/admin/news/{news_id}
    POST   /api/ai/admin/calendar             (create event)
    PUT    /api/ai/admin/calendar/{event_id}
    DELETE /api/ai/admin/calendar/{event_id}
    POST   /api/ai/admin/summary/generate?type=
    DELETE /api/ai/admin/summary/{summary_id}
    POST   /api/ai/admin/analytics/tick       (force analytics tick)
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from . import news_engine, calendar_engine, summary_engine, analytics_engine

logger = logging.getLogger("ai_news.routes")


class NewsPatch(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    body: Optional[str] = None
    high_impact: Optional[bool] = None
    is_published: Optional[bool] = None
    sentiment: Optional[str] = None


class NewsGenerateIn(BaseModel):
    categories: Optional[List[str]] = None
    per_category: int = 3


class CalendarIn(BaseModel):
    title: str
    country: str = "GLOBAL"
    currency: str = "USD"
    impact: str = "medium"
    category: str = "General"
    event_time: str
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    description: Optional[str] = None


class CalendarPatch(BaseModel):
    title: Optional[str] = None
    country: Optional[str] = None
    currency: Optional[str] = None
    impact: Optional[str] = None
    category: Optional[str] = None
    event_time: Optional[str] = None
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    description: Optional[str] = None


def attach(app, db, get_current_user, get_current_admin,
           analytics: analytics_engine.AnalyticsEngine,
           broadcaster: news_engine.NewsBroadcaster):
    r = APIRouter(prefix="/api/ai", tags=["ai-news-analytics"])

    # =============== NEWS ===============
    @r.get("/news")
    async def list_news(
        category: Optional[str] = Query(None),
        sentiment: Optional[str] = Query(None),
        high_impact_only: bool = Query(False),
        limit: int = Query(30, ge=1, le=100),
        _user=Depends(get_current_user),
    ):
        items = await news_engine.list_news(
            db, category=category, sentiment=sentiment,
            high_impact_only=high_impact_only, limit=limit,
        )
        return {"items": items, "count": len(items),
                "categories": news_engine.CATEGORIES,
                "category_labels": news_engine.CATEGORY_LABELS}

    @r.get("/news/{news_id}")
    async def get_news(news_id: str, _user=Depends(get_current_user)):
        item = await news_engine.get_news(db, news_id)
        if not item:
            raise HTTPException(404, "news item not found")
        return item

    # =============== CALENDAR ===============
    @r.get("/calendar/meta")
    async def calendar_meta(_user=Depends(get_current_user)):
        return {
            "impacts": calendar_engine.IMPACTS,
            "impact_labels": calendar_engine.IMPACT_LABELS,
        }

    @r.get("/calendar")
    async def list_calendar(
        impact: Optional[str] = Query(None),
        country: Optional[str] = Query(None),
        currency: Optional[str] = Query(None),
        days_ahead: int = Query(30, ge=1, le=90),
        include_past: bool = Query(False),
        limit: int = Query(100, ge=1, le=200),
        _user=Depends(get_current_user),
    ):
        rows = await calendar_engine.list_events(
            db, impact=impact, country=country, currency=currency,
            days_ahead=days_ahead, include_past=include_past, limit=limit)
        return {"events": rows, "count": len(rows)}

    # =============== MARKET SUMMARY ===============
    @r.get("/summary")
    async def get_summary(
        type: str = Query("daily", regex="^(intraday|daily|weekly)$"),
        _user=Depends(get_current_user),
    ):
        latest = await summary_engine.latest_summary(db, type)
        if not latest:
            latest = await summary_engine.generate_summary(db, type)
        return {"summary": latest}

    @r.get("/summary/history")
    async def summary_history(
        type: Optional[str] = Query(None, regex="^(intraday|daily|weekly)?$"),
        limit: int = Query(20, ge=1, le=100),
        _user=Depends(get_current_user),
    ):
        rows = await summary_engine.summary_history(db, summary_type=type or None,
                                                     limit=limit)
        return {"items": rows, "count": len(rows)}

    # =============== SIGNAL ANALYTICS ===============
    @r.get("/analytics/overview")
    async def analytics_overview(
        window_days: Optional[int] = Query(None, ge=1, le=365),
        _user=Depends(get_current_user),
    ):
        return await analytics_engine.overview(db, window_days=window_days)

    @r.get("/analytics/by-symbol")
    async def analytics_by_symbol(
        window_days: Optional[int] = Query(None, ge=1, le=365),
        limit: int = Query(30, ge=1, le=100),
        _user=Depends(get_current_user),
    ):
        rows = await analytics_engine.by_symbol(db, window_days=window_days, limit=limit)
        return {"rows": rows, "count": len(rows)}

    @r.get("/analytics/by-timeframe")
    async def analytics_by_timeframe(
        window_days: Optional[int] = Query(None, ge=1, le=365),
        _user=Depends(get_current_user),
    ):
        rows = await analytics_engine.by_timeframe(db, window_days=window_days)
        return {"rows": rows, "count": len(rows)}

    @r.get("/analytics/history")
    async def analytics_history(
        limit: int = Query(40, ge=1, le=200),
        outcome: Optional[str] = Query(None),
        _user=Depends(get_current_user),
    ):
        rows = await analytics_engine.signal_history(db, limit=limit, outcome=outcome)
        return {"items": rows, "count": len(rows)}

    # =============== ADMIN CONSOLE ===============
    @r.post("/admin/news/generate")
    async def admin_news_generate(body: NewsGenerateIn, admin=Depends(get_current_admin)):
        n = await news_engine.generate_news_batch(
            db, categories=body.categories, per_category=int(body.per_category))
        return {"generated": n}

    @r.put("/admin/news/{news_id}")
    async def admin_news_patch(news_id: str, patch: NewsPatch,
                                admin=Depends(get_current_admin)):
        set_fields = {k: v for k, v in patch.dict().items() if v is not None}
        if not set_fields:
            item = await news_engine.get_news(db, news_id)
            if not item:
                raise HTTPException(404)
            return item
        res = await db[news_engine.COLL].update_one(
            {"news_id": news_id}, {"$set": set_fields})
        if res.matched_count == 0:
            raise HTTPException(404, "news item not found")
        item = await news_engine.get_news(db, news_id)
        return item

    @r.delete("/admin/news/{news_id}")
    async def admin_news_delete(news_id: str, admin=Depends(get_current_admin)):
        res = await db[news_engine.COLL].delete_one({"news_id": news_id})
        if res.deleted_count == 0:
            raise HTTPException(404, "news item not found")
        return {"deleted": True}

    @r.post("/admin/calendar")
    async def admin_calendar_create(body: CalendarIn,
                                     admin=Depends(get_current_admin)):
        try:
            item = await calendar_engine.create_event(db, body.dict())
        except ValueError as e:
            raise HTTPException(400, str(e))
        return item

    @r.put("/admin/calendar/{event_id}")
    async def admin_calendar_patch(event_id: str, patch: CalendarPatch,
                                    admin=Depends(get_current_admin)):
        try:
            item = await calendar_engine.update_event(
                db, event_id, {k: v for k, v in patch.dict().items() if v is not None})
        except ValueError as e:
            raise HTTPException(400, str(e))
        if not item:
            raise HTTPException(404, "event not found")
        return item

    @r.delete("/admin/calendar/{event_id}")
    async def admin_calendar_delete(event_id: str,
                                     admin=Depends(get_current_admin)):
        ok = await calendar_engine.delete_event(db, event_id)
        if not ok:
            raise HTTPException(404, "event not found")
        return {"deleted": True}

    @r.post("/admin/summary/generate")
    async def admin_summary_generate(
        type: str = Query("daily", regex="^(intraday|daily|weekly)$"),
        admin=Depends(get_current_admin),
    ):
        try:
            item = await summary_engine.generate_summary(db, type)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return item

    @r.delete("/admin/summary/{summary_id}")
    async def admin_summary_delete(summary_id: str,
                                    admin=Depends(get_current_admin)):
        ok = await summary_engine.delete_summary(db, summary_id)
        if not ok:
            raise HTTPException(404, "summary not found")
        return {"deleted": True}

    @r.post("/admin/analytics/tick")
    async def admin_analytics_tick(admin=Depends(get_current_admin)):
        return await analytics.tick_once()

    @r.get("/admin/news")
    async def admin_news_list(
        category: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=200),
        admin=Depends(get_current_admin),
    ):
        q: Dict[str, Any] = {}
        if category and category != "all":
            q["category"] = category
        cur = db[news_engine.COLL].find(q, {"_id": 0}).sort("published_at", -1).limit(limit)
        rows = [d async for d in cur]
        for d in rows:
            for k in ("published_at", "broadcast_at"):
                if isinstance(d.get(k), object) and hasattr(d.get(k), "isoformat"):
                    d[k] = d[k].isoformat()
        return {"items": rows, "count": len(rows)}

    @r.get("/admin/console")
    async def admin_console(admin=Depends(get_current_admin)):
        """Aggregated dashboard payload for the admin AI Console."""
        news_count = await db[news_engine.COLL].estimated_document_count()
        pending_broadcast = await db[news_engine.COLL].count_documents(
            {"high_impact": True, "broadcast_at": None, "is_published": True})
        events_upcoming = await db[calendar_engine.COLL].count_documents(
            {"event_time": {"$gte": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc)}})
        summary_last = await summary_engine.latest_summary(db, "daily")
        ov = await analytics_engine.overview(db, window_days=30)
        return {
            "news": {
                "total": news_count,
                "pending_broadcast": pending_broadcast,
                "broadcaster_interval_sec": broadcaster.interval_sec,
            },
            "calendar": {
                "upcoming_events": events_upcoming,
            },
            "summary": {
                "latest_daily": summary_last,
            },
            "analytics": ov,
        }

    app.include_router(r)
    return r
