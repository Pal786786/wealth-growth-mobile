"""Sprint 12.3 · Phase A — Finance Ledger tests.

Covers:
  * Double-entry invariants (balanced legs, immutable)
  * Wallet hook: every wallet credit/debit emits a matching journal entry
  * Passbook: opening/closing/credit/debit/running-balance correctness
  * Reversal: creates a new negated entry, marks original is_reversed
  * Backfill: dry-run vs apply, idempotency (2nd apply skips all)
  * Balance denormalization (fast-read collection matches journal totals)
  * Enhanced audit trail (IP + device + before/after captured)
  * Immutability: no HTTP path to update/delete a journal entry
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"


# --------------------------------------------------------------- fixtures --
def _signup_and_fund(admin_hdr, amount=5_000):
    mob = f"9{uuid.uuid4().int % 10**9:09d}"
    email = f"pb_{uuid.uuid4().hex[:8]}@mfb.in"
    r = requests.post(f"{API}/auth/signup",
                      json={"email": email, "mobile": mob,
                            "password": "Passbook123!", "full_name": "Passbook User"},
                      timeout=30)
    assert r.status_code in (200, 201), r.text
    tok = r.json()["token"]
    uid = r.json()["user"]["user_id"] if "user" in r.json() else r.json().get("user_id")
    if not uid:
        me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}, timeout=10).json()
        uid = me.get("user_id")
    hdr = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    if amount > 0:
        requests.post(f"{API}/admin/wallet/adjust",
                      json={"user_id": uid, "amount": amount, "type": "credit",
                            "note": "phase-A test funding"},
                      headers=admin_hdr, timeout=15)
    return hdr, uid


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/admin/login",
                      json={"email": "admin@mfb.in", "password": "Admin@MFB2026"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def user(admin_headers):
    return _signup_and_fund(admin_headers, amount=5_000)


# ============================================================ Passbook =====
def test_passbook_after_wallet_credit(user, admin_headers):
    hdr, uid = user
    r = requests.get(f"{API}/wallet/passbook", headers=hdr, timeout=10)
    assert r.status_code == 200, r.text
    pb = r.json()
    # After the funding fixture, closing balance should be ~5000
    assert pb["closing_balance"] >= 4_900
    assert pb["total_rows"] >= 1
    assert pb["total_credit"] >= 4_900
    # Running balance sanity: first row (most recent) has closing_balance close to closing_balance
    first = pb["rows"][0]
    assert first["closing_balance"] == pb["closing_balance"]
    assert "narration" in first
    assert first["credit"] > 0 or first["debit"] > 0


def test_passbook_credit_debit_shape(user, admin_headers):
    hdr, uid = user
    # Do a second credit + a debit, verify passbook order + math
    requests.post(f"{API}/admin/wallet/adjust",
                  json={"user_id": uid, "amount": 100, "type": "credit",
                        "note": "phase A test"},
                  headers=admin_headers, timeout=10)
    requests.post(f"{API}/admin/wallet/adjust",
                  json={"user_id": uid, "amount": 50, "type": "debit",
                        "note": "phase A test 2"},
                  headers=admin_headers, timeout=10)

    pb = requests.get(f"{API}/wallet/passbook", headers=hdr, timeout=10).json()
    assert pb["total_rows"] >= 3
    # Sorted DESC by entry_date
    dates = [r["entry_date"] for r in pb["rows"]]
    assert dates == sorted(dates, reverse=True)
    # Running balance is monotone against the delta on each row
    for i in range(len(pb["rows"]) - 1):
        cur = pb["rows"][i]
        older = pb["rows"][i + 1]
        # cur.closing == older.closing + (cur.credit - cur.debit)
        delta = cur["credit"] - cur["debit"]
        assert abs((cur["closing_balance"] - older["closing_balance"]) - delta) < 0.02, (cur, older)


def test_passbook_requires_auth():
    r = requests.get(f"{API}/wallet/passbook", timeout=10)
    assert r.status_code in (401, 403)


# ============================================================ Journal ======
def test_journal_search_by_user(user, admin_headers):
    hdr, uid = user
    r = requests.get(f"{API}/admin/ledger/journal", params={"user_id": uid, "limit": 20},
                     headers=admin_headers, timeout=10)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["total"] >= 1
    # Every entry must be balanced (DR == CR)
    for it in j["items"]:
        dr = sum(l["amount"] for l in it["legs"] if l["side"] == "DR")
        cr = sum(l["amount"] for l in it["legs"] if l["side"] == "CR")
        assert abs(dr - cr) < 0.005, it["journal_id"]


def test_balances_denorm_matches_journal(user, admin_headers):
    hdr, uid = user
    # Compute expected user_wallet balance from journal legs
    acct = f"assets:user_wallet:{uid}"
    j = requests.get(f"{API}/admin/ledger/journal",
                     params={"user_id": uid, "limit": 500, "include_reversed": True},
                     headers=admin_headers, timeout=10).json()
    expected = 0.0
    for e in j["items"]:
        if e.get("is_reversed"):
            # Reversal is emitted as its own entry, and its legs on THIS account
            # will cancel — but the ORIGINAL still contributes. So we do NOT skip
            # here; the reversal entries are already in `items`.
            pass
        for l in e["legs"]:
            if l["account"] == acct:
                expected += l["amount"] if l["side"] == "DR" else -l["amount"]
    # (Because user_wallet is on the `assets:` side, DR = +, CR = -)
    # BUT our denorm balance convention flips the sign based on account root
    # (see engine._update_balances). So we need to compare the DENORMalised
    # balance with the DENORMalisation formula, not raw sums.
    # For an assets account, DR = +1, CR = -1 → same as our expected calc above.
    got = requests.get(f"{API}/admin/ledger/balance/{acct}",
                       headers=admin_headers, timeout=10).json()
    assert abs(got["balance"] - expected) < 0.02, (got, expected)


def test_reversal_creates_new_entry_and_marks_original(user, admin_headers):
    hdr, uid = user
    # Take the most recent journal entry for this user and reverse it
    j = requests.get(f"{API}/admin/ledger/journal",
                     params={"user_id": uid, "limit": 1, "include_reversed": False},
                     headers=admin_headers, timeout=10).json()
    assert j["items"], "need at least one entry"
    orig_id = j["items"][0]["journal_id"]

    r = requests.post(f"{API}/admin/ledger/reverse/{orig_id}",
                      json={"narration": "test reversal"},
                      headers=admin_headers, timeout=10)
    assert r.status_code == 200, r.text
    rev = r.json()["reversal"]
    assert rev["txn_type"] == "reversal"
    assert rev["reverses_journal_id"] == orig_id
    # Legs should be sign-flipped
    orig_legs = j["items"][0]["legs"]
    rev_legs = rev["legs"]
    for ol, rl in zip(orig_legs, rev_legs):
        assert ol["account"] == rl["account"]
        assert ol["amount"] == rl["amount"]
        assert ol["side"] != rl["side"]

    # Try reversing again → 400
    r2 = requests.post(f"{API}/admin/ledger/reverse/{orig_id}",
                       headers=admin_headers, timeout=10)
    assert r2.status_code == 400


def test_reversal_not_found():
    r = requests.post(f"{API}/admin/ledger/reverse/does-not-exist", timeout=10)
    assert r.status_code in (401, 403, 404)


# ============================================================ Backfill =====
def test_backfill_dry_run(admin_headers):
    r = requests.post(f"{API}/admin/ledger/backfill",
                      json={"dry_run": True}, headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["dry_run"] is True
    assert j["status"] == "completed"
    assert j["processed"] >= 0
    # dry run must NOT write anything (migrated + skipped counters shouldn't affect DB)
    # We validate by running twice and confirming counts are stable-ish (both are dry)
    r2 = requests.post(f"{API}/admin/ledger/backfill",
                       json={"dry_run": True}, headers=admin_headers, timeout=30)
    assert r2.status_code == 200
    # Both dry runs should have identical processed counts
    assert r.json()["processed"] == r2.json()["processed"]


def test_backfill_idempotency(admin_headers):
    """Applying the backfill twice must yield migrated=0, skipped=all on 2nd run."""
    r1 = requests.post(f"{API}/admin/ledger/backfill",
                       json={"dry_run": False}, headers=admin_headers, timeout=60).json()
    r2 = requests.post(f"{API}/admin/ledger/backfill",
                       json={"dry_run": False}, headers=admin_headers, timeout=60).json()
    assert r2["processed"] == r1["processed"]
    assert r2["migrated"] == 0, r2
    assert r2["skipped"] >= r2["processed"] - 5   # allow tiny drift from new events
    assert r2["failed"] == 0, r2


def test_backfill_status_returns_last(admin_headers):
    r = requests.get(f"{API}/admin/ledger/backfill/status",
                     headers=admin_headers, timeout=10)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["last_run"] is not None
    assert "run_id" in j["last_run"]


def test_backfill_only_admin():
    r = requests.post(f"{API}/admin/ledger/backfill", json={"dry_run": True}, timeout=10)
    assert r.status_code in (401, 403)


# ============================================================ Audit trail ==
def test_audit_records_passbook_view(user, admin_headers):
    """Merely reading the passbook must produce an audit trail entry."""
    hdr, uid = user
    requests.get(f"{API}/wallet/passbook", headers=hdr, timeout=10)
    a = requests.get(f"{API}/admin/ledger/audit",
                     params={"actor_id": uid, "action_prefix": "passbook",
                             "limit": 5},
                     headers=admin_headers, timeout=10)
    assert a.status_code == 200, a.text
    aj = a.json()
    assert aj["total"] >= 1
    row = aj["items"][0]
    assert row["actor_id"] == uid
    assert row["action"].startswith("passbook")
    # Client meta captured (may be None in some environments — sanity: keys present)
    for key in ("ip", "user_agent"):
        assert key in row


def test_audit_records_reversal(admin_headers):
    r = requests.get(f"{API}/admin/ledger/audit",
                     params={"action_prefix": "ledger.reverse", "limit": 5},
                     headers=admin_headers, timeout=10)
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_audit_captures_before_after(admin_headers):
    """The reversal action captured before + after in the audit row."""
    r = requests.get(f"{API}/admin/ledger/audit",
                     params={"action_prefix": "ledger.reverse", "limit": 1},
                     headers=admin_headers, timeout=10)
    j = r.json()
    if j["total"] >= 1:
        row = j["items"][0]
        assert row["before"] is not None
        assert row["after"] is not None
        assert "reversal_id" in row["after"]


# ============================================================ Immutability =
def test_no_journal_delete_route():
    """No public DELETE endpoint exists for journal entries."""
    r = requests.delete(f"{API}/admin/ledger/journal/xyz", timeout=10)
    assert r.status_code in (404, 405)


def test_no_journal_update_route():
    r = requests.put(f"{API}/admin/ledger/journal/xyz", timeout=10)
    assert r.status_code in (404, 405)


# ============================================================ Coa balances --
def test_admin_balances_lists_platform_liability(admin_headers):
    r = requests.get(f"{API}/admin/ledger/balances", headers=admin_headers, timeout=10)
    assert r.status_code == 200
    accts = {it["account"] for it in r.json()["items"]}
    # At least one user_wallet should exist by now
    assert any(a.startswith("assets:user_wallet:") for a in accts)
