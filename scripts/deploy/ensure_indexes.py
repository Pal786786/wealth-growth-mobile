#!/usr/bin/env python3
"""
My Funding Bank — MongoDB Index Validator / Creator
====================================================
Ensures all critical production indexes exist. Idempotent: safe to run
repeatedly. Use before every release.

Usage:
    python scripts/deploy/ensure_indexes.py            # create/verify
    python scripts/deploy/ensure_indexes.py --dry-run  # print plan only
    python scripts/deploy/ensure_indexes.py --report   # JSON output

Exit codes:
    0 – all indexes present (or created)
    1 – error while validating
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from pymongo import ASCENDING, DESCENDING, MongoClient, TEXT

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "mfb_prod")

# Format: collection -> [(name, keys, options)]
INDEX_PLAN: Dict[str, List[Tuple[str, list, dict]]] = {
    "users": [
        ("user_id_1", [("user_id", ASCENDING)], {"unique": True}),
        ("phone_1", [("phone", ASCENDING)], {"unique": True, "sparse": True}),
        ("email_1", [("email", ASCENDING)], {"unique": True, "sparse": True}),
        ("created_at_-1", [("created_at", DESCENDING)], {}),
    ],
    "wallets": [
        ("user_id_1", [("user_id", ASCENDING)], {"unique": True}),
        ("balance_-1", [("balance", DESCENDING)], {}),
    ],
    "wallet_transactions": [
        ("user_id_1_created_at_-1", [("user_id", ASCENDING), ("created_at", DESCENDING)], {}),
        ("tx_id_1", [("tx_id", ASCENDING)], {"unique": True}),
        ("status_1", [("status", ASCENDING)], {}),
        ("provider_reference_1", [("provider_reference", ASCENDING)], {"sparse": True}),
    ],
    "payments": [
        ("user_id_1_created_at_-1", [("user_id", ASCENDING), ("created_at", DESCENDING)], {}),
        ("order_id_1", [("order_id", ASCENDING)], {"unique": True, "sparse": True}),
        ("status_1", [("status", ASCENDING)], {}),
    ],
    "withdrawals": [
        ("user_id_1_created_at_-1", [("user_id", ASCENDING), ("created_at", DESCENDING)], {}),
        ("withdrawal_id_1", [("withdrawal_id", ASCENDING)], {"unique": True}),
        ("status_1", [("status", ASCENDING)], {}),
        ("provider_reference_1", [("provider_reference", ASCENDING)], {"sparse": True}),
    ],
    "finance_journal": [
        ("tx_id_1", [("tx_id", ASCENDING)], {"unique": True}),
        ("timestamp_-1", [("timestamp", DESCENDING)], {}),
        ("status_1", [("status", ASCENDING)], {}),
        ("legs.account_1", [("legs.account", ASCENDING)], {}),
    ],
    "finance_alerts": [
        ("alert_type_1_status_1", [("alert_type", ASCENDING), ("status", ASCENDING)], {}),
        ("created_at_-1", [("created_at", DESCENDING)], {}),
        ("severity_1", [("severity", ASCENDING)], {}),
    ],
    "kyc_records": [
        ("user_id_1", [("user_id", ASCENDING)], {"unique": True}),
        ("status_1", [("status", ASCENDING)], {}),
    ],
    "gold_orders": [
        ("user_id_1_created_at_-1", [("user_id", ASCENDING), ("created_at", DESCENDING)], {}),
        ("order_id_1", [("order_id", ASCENDING)], {"unique": True, "sparse": True}),
    ],
    "mutual_fund_orders": [
        ("user_id_1_created_at_-1", [("user_id", ASCENDING), ("created_at", DESCENDING)], {}),
        ("order_id_1", [("order_id", ASCENDING)], {"unique": True, "sparse": True}),
    ],
    "forex_orders": [
        ("user_id_1_created_at_-1", [("user_id", ASCENDING), ("created_at", DESCENDING)], {}),
        ("order_id_1", [("order_id", ASCENDING)], {"unique": True, "sparse": True}),
    ],
    "admin_logs": [
        ("admin_id_1_ts_-1", [("admin_id", ASCENDING), ("ts", DESCENDING)], {}),
        ("action_1", [("action", ASCENDING)], {}),
        ("ts_-1", [("ts", DESCENDING)], {"expireAfterSeconds": 60 * 60 * 24 * 365}),  # 1y TTL
    ],
    "notifications": [
        ("user_id_1_created_at_-1", [("user_id", ASCENDING), ("created_at", DESCENDING)], {}),
        ("read_1", [("read", ASCENDING)], {}),
    ],
    "otp_codes": [
        ("phone_1", [("phone", ASCENDING)], {}),
        ("expires_at_1", [("expires_at", ASCENDING)], {"expireAfterSeconds": 0}),
    ],
}


def ensure_indexes(dry_run: bool = False) -> Dict[str, Any]:
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=8000)
    db = client[DB_NAME]
    report: Dict[str, Any] = {"db": DB_NAME, "created": [], "existing": [], "errors": []}

    for coll_name, plans in INDEX_PLAN.items():
        coll = db[coll_name]
        try:
            existing = {ix["name"] for ix in coll.list_indexes()}
        except Exception as e:
            report["errors"].append(f"{coll_name}: cannot list indexes ({e})")
            continue

        for name, keys, opts in plans:
            if name in existing:
                report["existing"].append(f"{coll_name}.{name}")
                continue
            if dry_run:
                report["created"].append(f"[DRY] {coll_name}.{name}")
                continue
            try:
                coll.create_index(keys, name=name, background=True, **opts)
                report["created"].append(f"{coll_name}.{name}")
            except Exception as e:
                report["errors"].append(f"{coll_name}.{name}: {e}")

    client.close()
    return report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--report", action="store_true", help="JSON output")
    args = p.parse_args()

    report = ensure_indexes(dry_run=args.dry_run)

    if args.report:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"🗄️  DB: {report['db']}")
        print(f"   ✅ Existing indexes: {len(report['existing'])}")
        print(f"   ➕ Created indexes:  {len(report['created'])}")
        for c in report["created"]:
            print(f"      + {c}")
        if report["errors"]:
            print(f"   ❌ Errors: {len(report['errors'])}", file=sys.stderr)
            for e in report["errors"]:
                print(f"      - {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
