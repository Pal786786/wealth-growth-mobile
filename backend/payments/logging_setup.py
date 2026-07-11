"""Structured JSON logging for the payments subsystem.

Never logs secrets (key_secret, webhook_secret, signatures, card numbers).
"""
from __future__ import annotations
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

_SENSITIVE_KEYS = {
    "key_secret", "webhook_secret", "signature", "password",
    "authorization", "token", "card_number", "cvv", "otp",
    "razorpay_key_secret", "razorpay_webhook_secret",
}
_SENSITIVE_PATTERN = re.compile(
    r"([A-Za-z0-9_-]{20,})|(rzp_[a-z]+_[A-Za-z0-9]+)", re.MULTILINE)


def _redact_value(v):
    if isinstance(v, str) and len(v) > 8:
        return v[:4] + "***" + v[-2:]
    return "***"


def _sanitize(obj):
    if isinstance(obj, dict):
        out = {}
        for k, val in obj.items():
            lk = str(k).lower()
            if lk in _SENSITIVE_KEYS or lk.endswith("_secret") or lk.endswith("_signature"):
                out[k] = _redact_value(val)
            else:
                out[k] = _sanitize(val)
        return out
    if isinstance(obj, (list, tuple)):
        return [_sanitize(x) for x in obj]
    return obj


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "msg": record.getMessage(),
        }
        # Attach extra fields (payment_id, order_id, request_id, etc.)
        for k, v in record.__dict__.items():
            if k in ("args", "msg", "levelname", "levelno", "pathname", "filename",
                     "module", "exc_info", "exc_text", "stack_info", "lineno",
                     "funcName", "created", "msecs", "relativeCreated", "thread",
                     "threadName", "processName", "process", "name",
                     "taskName", "message"):
                continue
            payload[k] = v
        payload = _sanitize(payload)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_configured = False


def configure_payments_logging():
    global _configured
    if _configured:
        return
    _configured = True
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    for name in ("payments", "payments.engine", "payments.webhooks",
                 "payments.reconciliation", "payments.razorpay", "payments.security"):
        lg = logging.getLogger(name)
        # Only attach once; avoid duplication under uvicorn reload
        if not any(isinstance(h, logging.StreamHandler) and
                   isinstance(h.formatter, _JsonFormatter) for h in lg.handlers):
            lg.addHandler(handler)
        lg.setLevel(logging.INFO)
        lg.propagate = False


def audit_log(logger_obj: logging.Logger, event: str, **fields):
    """Structured event log helper."""
    logger_obj.info(event, extra=_sanitize({"event": event, **fields}))
