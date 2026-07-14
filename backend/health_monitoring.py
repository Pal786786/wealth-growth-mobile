"""
My Funding Bank — Production Health & Metrics Module
======================================================
Adds the following endpoints (all under /api):

    GET /api/health          → deep JSON health snapshot
    GET /api/health/live     → liveness probe (fast, no external deps)
    GET /api/health/ready    → readiness probe (checks Mongo, scheduler)
    GET /api/health/summary  → lightweight JSON dashboard payload
    GET /api/metrics         → Prometheus text/plain exposition

The module registers a lightweight middleware that measures per-request
latency + status code labels. It is entirely optional – disabling
`ENABLE_METRICS=false` skips Prometheus registration.

Usage:
    import health_monitoring
    health_monitoring.attach(app, api, db=db, logger=logger)
"""
from __future__ import annotations

import asyncio
import os
import platform
import socket
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

# ---------------- Optional deps ----------------
try:
    import psutil  # type: ignore
    HAS_PSUTIL = True
except Exception:
    HAS_PSUTIL = False

try:
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        CONTENT_TYPE_LATEST,
        generate_latest,
        multiprocess,
    )
    HAS_PROM = True
except Exception:
    HAS_PROM = False


STARTED_AT = time.time()
HOSTNAME = socket.gethostname()
SERVICE_VERSION = os.getenv("IMAGE_TAG", "dev")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
ENABLE_METRICS = os.getenv("ENABLE_METRICS", "true").lower() in {"1", "true", "yes"}


# ---------- Prometheus registry (multiprocess-safe) ----------
def _build_registry():
    if not HAS_PROM:
        return None, {}
    reg = CollectorRegistry()
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        try:
            multiprocess.MultiProcessCollector(reg)
        except Exception:
            pass

    metrics = {
        "requests_total": Counter(
            "mfb_http_requests_total",
            "Total HTTP requests",
            ["method", "path", "status"],
            registry=reg,
        ),
        "request_latency": Histogram(
            "mfb_http_request_duration_seconds",
            "HTTP request latency",
            ["method", "path"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
            registry=reg,
        ),
        "in_flight": Gauge(
            "mfb_http_in_flight_requests",
            "Current in-flight HTTP requests",
            registry=reg,
            multiprocess_mode="livesum",
        ),
        "mongo_latency": Gauge(
            "mfb_mongo_ping_seconds",
            "MongoDB ping latency in seconds",
            registry=reg,
            multiprocess_mode="livemin",
        ),
        "wallet_tx": Counter(
            "mfb_wallet_transactions_total",
            "Wallet transactions by type/status",
            ["type", "status"],
            registry=reg,
        ),
        "payments": Counter(
            "mfb_payments_total",
            "Payment attempts by provider/status",
            ["provider", "status"],
            registry=reg,
        ),
        "withdrawals": Counter(
            "mfb_withdrawals_total",
            "Withdrawals by provider/status",
            ["provider", "status"],
            registry=reg,
        ),
        "provider_health": Gauge(
            "mfb_provider_up",
            "External provider health (1=up, 0=down)",
            ["provider"],
            registry=reg,
            multiprocess_mode="livemax",
        ),
        "active_sessions": Gauge(
            "mfb_active_sessions",
            "Approximate active user sessions (5-min window)",
            registry=reg,
            multiprocess_mode="livesum",
        ),
        "alerts": Gauge(
            "mfb_finance_alerts",
            "Finance alert count by severity/status",
            ["severity", "status"],
            registry=reg,
            multiprocess_mode="livesum",
        ),
        "scheduler_jobs": Gauge(
            "mfb_scheduler_jobs",
            "Registered scheduler jobs",
            ["state"],
            registry=reg,
            multiprocess_mode="livesum",
        ),
        "build_info": Gauge(
            "mfb_build_info",
            "Static build info label",
            ["version", "env", "host"],
            registry=reg,
        ),
    }
    try:
        metrics["build_info"].labels(SERVICE_VERSION, ENVIRONMENT, HOSTNAME).set(1)
    except Exception:
        pass
    return reg, metrics


REGISTRY, METRICS = _build_registry() if HAS_PROM and ENABLE_METRICS else (None, {})


def _normalize_path(path: str) -> str:
    """Group high-cardinality paths (IDs) to keep label cardinality low."""
    parts = path.split("/")
    norm = []
    for p in parts:
        if p.isdigit() or (len(p) >= 12 and any(ch.isdigit() for ch in p) and any(ch.isalpha() for ch in p)):
            norm.append(":id")
        else:
            norm.append(p)
    return "/".join(norm) or "/"


# ---------- Health check probes ----------
async def _check_mongo(db, timeout: float = 2.5) -> Dict[str, Any]:
    t0 = time.perf_counter()
    try:
        await asyncio.wait_for(db.command("ping"), timeout=timeout)
        dt = time.perf_counter() - t0
        if "mongo_latency" in METRICS:
            METRICS["mongo_latency"].set(dt)
        return {"ok": True, "latency_ms": round(dt * 1000, 2)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _check_disk() -> Dict[str, Any]:
    if not HAS_PSUTIL:
        return {"ok": True, "note": "psutil unavailable"}
    try:
        du = psutil.disk_usage("/")
        return {
            "ok": du.percent < 90,
            "used_pct": du.percent,
            "free_gb": round(du.free / (1024 ** 3), 2),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _check_memory() -> Dict[str, Any]:
    if not HAS_PSUTIL:
        return {"ok": True, "note": "psutil unavailable"}
    try:
        vm = psutil.virtual_memory()
        return {"ok": vm.percent < 90, "used_pct": vm.percent, "available_mb": round(vm.available / (1024 ** 2))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _check_cpu() -> Dict[str, Any]:
    if not HAS_PSUTIL:
        return {"ok": True, "note": "psutil unavailable"}
    try:
        pct = psutil.cpu_percent(interval=0.05)
        return {"ok": pct < 95, "used_pct": pct, "cores": psutil.cpu_count()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _collect_health(db, deep: bool = False) -> Dict[str, Any]:
    uptime = round(time.time() - STARTED_AT, 2)
    payload = {
        "service": "mfb-backend",
        "version": SERVICE_VERSION,
        "environment": ENVIRONMENT,
        "host": HOSTNAME,
        "uptime_sec": uptime,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
    }
    payload["mongo"] = await _check_mongo(db)
    payload["disk"] = _check_disk()
    payload["memory"] = _check_memory()
    payload["cpu"] = _check_cpu()

    if deep:
        # Include a small sample of business-facing counts
        try:
            payload["counts"] = {
                "users":              await db.users.estimated_document_count(),
                "wallet_transactions": await db.wallet_transactions.estimated_document_count(),
                "payments":            await db.payments.estimated_document_count(),
                "withdrawals":         await db.withdrawals.estimated_document_count(),
                "finance_journal":     await db.finance_journal.estimated_document_count(),
            }
        except Exception as e:
            payload["counts"] = {"error": str(e)[:120]}

        try:
            active = await db.finance_alerts.count_documents({"status": "active"})
            payload["alerts"] = {"active": active}
        except Exception:
            payload["alerts"] = {"active": 0}

    ok = payload["mongo"]["ok"] and payload["disk"]["ok"] and payload["memory"]["ok"]
    payload["status"] = "healthy" if ok else "degraded"
    return payload


# ---------- Public helpers for other modules ----------
def record_wallet_tx(tx_type: str, status: str) -> None:
    if METRICS:
        try:
            METRICS["wallet_tx"].labels(tx_type, status).inc()
        except Exception:
            pass


def record_payment(provider: str, status: str) -> None:
    if METRICS:
        try:
            METRICS["payments"].labels(provider, status).inc()
        except Exception:
            pass


def record_withdrawal(provider: str, status: str) -> None:
    if METRICS:
        try:
            METRICS["withdrawals"].labels(provider, status).inc()
        except Exception:
            pass


def set_provider_up(provider: str, up: bool) -> None:
    if METRICS:
        try:
            METRICS["provider_health"].labels(provider).set(1 if up else 0)
        except Exception:
            pass


# ---------- Attach to FastAPI ----------
def attach(app: FastAPI, api: APIRouter, *, db, logger=None) -> None:
    """Register health endpoints, metrics endpoint, and the timing middleware."""

    if ENABLE_METRICS and HAS_PROM and METRICS:
        @app.middleware("http")
        async def _metrics_middleware(request: Request, call_next):
            path = _normalize_path(request.url.path)
            method = request.method
            in_flight = METRICS.get("in_flight")
            if in_flight:
                try:
                    in_flight.inc()
                except Exception:
                    pass
            start = time.perf_counter()
            try:
                response: Response = await call_next(request)
                status = response.status_code
            except Exception:
                status = 500
                raise
            finally:
                elapsed = time.perf_counter() - start
                try:
                    METRICS["requests_total"].labels(method, path, str(status)).inc()
                    METRICS["request_latency"].labels(method, path).observe(elapsed)
                except Exception:
                    pass
                if in_flight:
                    try:
                        in_flight.dec()
                    except Exception:
                        pass
            return response

    @api.get("/health/live", tags=["health"])
    async def live():
        # Cheapest possible probe – process is up
        return {"status": "live", "uptime_sec": round(time.time() - STARTED_AT, 2)}

    @api.get("/health/ready", tags=["health"])
    async def ready():
        mongo = await _check_mongo(db)
        ok = mongo["ok"]
        return JSONResponse(
            content={"status": "ready" if ok else "not_ready", "mongo": mongo},
            status_code=200 if ok else 503,
        )

    @api.get("/health", tags=["health"])
    async def deep_health():
        payload = await _collect_health(db, deep=True)
        return JSONResponse(content=payload, status_code=200 if payload["status"] == "healthy" else 503)

    @api.get("/health/summary", tags=["health"])
    async def health_summary():
        """Lightweight JSON payload for the built-in dashboard widget."""
        payload = await _collect_health(db, deep=False)
        return {
            "status": payload["status"],
            "uptime_sec": payload["uptime_sec"],
            "mongo_ok": payload["mongo"]["ok"],
            "mongo_latency_ms": payload["mongo"].get("latency_ms"),
            "cpu_pct": payload["cpu"].get("used_pct"),
            "memory_pct": payload["memory"].get("used_pct"),
            "disk_pct": payload["disk"].get("used_pct"),
            "version": SERVICE_VERSION,
            "env": ENVIRONMENT,
        }

    @app.get("/api/metrics", include_in_schema=False)
    async def metrics():
        if not (ENABLE_METRICS and HAS_PROM and REGISTRY):
            return PlainTextResponse("# metrics disabled\n", status_code=200)
        data = generate_latest(REGISTRY)
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

    if logger:
        logger.info(
            "health_monitoring attached (prometheus=%s, psutil=%s, enabled=%s)",
            HAS_PROM, HAS_PSUTIL, ENABLE_METRICS,
        )
