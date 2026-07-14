#!/usr/bin/env python3
"""
My Funding Bank — Production Environment Variable Validator
=============================================================
Validates presence, format, and sanity of environment variables before
the backend container is allowed to start.

Exit codes:
    0  – all required vars present and well-formed
    1  – one or more validation errors (see stderr)
    2  – warnings only (non-fatal). Fatal by default; pass --warn-only
         to convert errors to warnings.

Usage:
    python scripts/deploy/validate_env.py             # strict (prod)
    python scripts/deploy/validate_env.py --warn-only # for CI dry-runs
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass  # dotenv is optional here – real envs come from the platform


@dataclass
class Rule:
    key: str
    required: bool = True
    kind: str = "str"      # str | int | bool | url | email | secret
    min_len: int = 1
    max_len: int = 8192
    pattern: Optional[str] = None
    allowed: Optional[list] = None
    validator: Optional[Callable[[str], Optional[str]]] = None
    description: str = ""


RULES: List[Rule] = [
    # ---------------- Runtime ----------------
    Rule("ENVIRONMENT", allowed=["production", "staging", "development"], description="App runtime environment"),
    Rule("LOG_LEVEL", allowed=["debug", "info", "warning", "error", "critical"], description="Backend log level"),
    Rule("WEB_CONCURRENCY", kind="int", description="Gunicorn workers (>=2)", validator=lambda v: None if int(v) >= 2 else "must be >= 2"),

    # ---------------- Domains / URLs ----------------
    Rule("DOMAIN_NAME", pattern=r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", description="Public API domain"),
    Rule("ADMIN_DOMAIN", pattern=r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", description="Admin panel domain"),
    Rule("CERTBOT_EMAIL", kind="email", description="Let's Encrypt registration email"),

    # ---------------- MongoDB ----------------
    Rule("MONGO_URL", kind="url", min_len=20, description="MongoDB connection string"),
    Rule("DB_NAME", pattern=r"^[a-zA-Z0-9_-]+$", description="MongoDB database name"),
    Rule("MONGO_ROOT_USER", required=False, description="Mongo root user (docker compose only)"),
    Rule("MONGO_ROOT_PASSWORD", required=False, kind="secret", min_len=12, description="Mongo root password (>=12 chars)"),

    # ---------------- Auth ----------------
    Rule("JWT_SECRET", kind="secret", min_len=32, description="JWT signing secret (>=32 chars)"),
    Rule("JWT_ALGORITHM", allowed=["HS256", "HS384", "HS512"], required=False, description="JWT algorithm"),

    # ---------------- Backups ----------------
    Rule("BACKUP_STORAGE", allowed=["local", "s3"], description="Backup destination"),
    Rule("BACKUP_RETENTION_DAYS", kind="int", validator=lambda v: None if 1 <= int(v) <= 365 else "1..365", description="Backup retention window"),
    Rule("BACKUP_ENCRYPT", kind="bool", required=False, description="Encrypt backups with GPG"),

    # ---------------- Optional 3rd-party (warn if missing) ----------------
    Rule("RAZORPAY_KEY_ID", required=False, description="Razorpay Key ID"),
    Rule("RAZORPAY_KEY_SECRET", required=False, kind="secret", description="Razorpay Secret"),
    Rule("CASHFREE_APP_ID", required=False, description="Cashfree Payments App ID"),
    Rule("CASHFREE_SECRET_KEY", required=False, kind="secret", description="Cashfree Payments Secret"),
    Rule("CASHFREE_PAYOUT_CLIENT_ID", required=False, description="Cashfree Payouts Client ID"),
    Rule("CASHFREE_PAYOUT_CLIENT_SECRET", required=False, kind="secret", description="Cashfree Payouts Secret"),
    Rule("TWELVEDATA_API_KEY", required=False, kind="secret", description="TwelveData market provider"),
    Rule("EMERGENT_LLM_KEY", required=False, kind="secret", description="Emergent LLM key (Claude/GPT/Gemini)"),
]

# Values considered placeholders / unsafe defaults.
UNSAFE_TOKENS = {
    "change-me", "changeme", "please-change", "secret", "password",
    "admin", "test", "example", "placeholder", "foo", "bar",
}


def _looks_placeholder(value: str) -> bool:
    v = value.strip().lower()
    return any(tok in v for tok in UNSAFE_TOKENS)


def _check_email(v: str) -> Optional[str]:
    return None if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v) else "invalid email"


def _check_url(v: str) -> Optional[str]:
    return None if re.match(r"^[a-z][a-z0-9+.-]*://", v) else "invalid URL scheme"


def _check_bool(v: str) -> Optional[str]:
    return None if v.strip().lower() in {"true", "false", "1", "0", "yes", "no"} else "not a boolean"


def _check_int(v: str) -> Optional[str]:
    try:
        int(v)
        return None
    except ValueError:
        return "not an integer"


KIND_CHECKS = {
    "email": _check_email,
    "url": _check_url,
    "bool": _check_bool,
    "int": _check_int,
}


def validate(rules: List[Rule], environment: str) -> tuple[list, list]:
    errors: List[str] = []
    warnings: List[str] = []

    for r in rules:
        raw = os.getenv(r.key)
        if raw is None or raw == "":
            msg = f"{r.key}: missing ({r.description})"
            if r.required:
                errors.append(msg)
            else:
                warnings.append(msg)
            continue

        v = raw.strip()
        if len(v) < r.min_len:
            errors.append(f"{r.key}: too short (min={r.min_len})")
            continue
        if len(v) > r.max_len:
            errors.append(f"{r.key}: too long (max={r.max_len})")
            continue
        if r.pattern and not re.match(r.pattern, v):
            errors.append(f"{r.key}: does not match pattern {r.pattern!r}")
            continue
        if r.allowed and v not in r.allowed:
            errors.append(f"{r.key}: '{v}' not in allowed {r.allowed}")
            continue
        check = KIND_CHECKS.get(r.kind)
        if check:
            err = check(v)
            if err:
                errors.append(f"{r.key}: {err}")
                continue
        if r.validator:
            err = r.validator(v)
            if err:
                errors.append(f"{r.key}: {err}")
                continue
        if r.kind == "secret" and environment == "production" and _looks_placeholder(v):
            errors.append(f"{r.key}: placeholder-looking secret in production")
            continue

    return errors, warnings


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--warn-only", action="store_true", help="never exit non-zero")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args()

    env = os.getenv("ENVIRONMENT", "development")
    errors, warnings = validate(RULES, env)

    if args.json:
        import json
        print(json.dumps({"environment": env, "errors": errors, "warnings": warnings}, indent=2))
    else:
        if errors:
            print("\n❌  ENV VALIDATION ERRORS:", file=sys.stderr)
            for e in errors:
                print(f"   - {e}", file=sys.stderr)
        if warnings:
            print("\n⚠️   ENV VALIDATION WARNINGS:")
            for w in warnings:
                print(f"   - {w}")
        if not errors and not warnings:
            print("✅ Environment looks good.")

    if errors and not args.warn_only:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
