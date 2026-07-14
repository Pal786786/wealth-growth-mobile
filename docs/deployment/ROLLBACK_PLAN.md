# My Funding Bank — Rollback Plan (Strategic)

_Companion to `ROLLBACK_PROCEDURE.md` (which is the tactical runbook). This
document describes the classes of rollback we support and the invariants we
rely on to make them safe._

---

## 1. Rollback tiers

| Tier | Trigger                            | Method                       | RTO       | Data loss  |
|------|------------------------------------|------------------------------|-----------|------------|
| T1   | Backwards-compat regression        | Image swap (`.last_good_tag`)| < 2 min   | none       |
| T2   | Config-only regression             | Revert env & restart         | < 5 min   | none       |
| T3   | Migration failure                  | Image swap + reverse migration| < 15 min | none if reverse migration is idempotent |
| T4   | Data corruption / destructive bug  | Image swap + restore backup  | 15–30 min | up to 24 h (RPO) |
| T5   | Complete disaster (server lost)    | Rebuild from backups on new host | 60 min | up to 24 h (RPO) |

Our target **RTO ≤ 30 min**, **RPO ≤ 24 h** (default daily backup cadence). Reduce RPO by lowering the `BACKUP_CRON` interval and enabling S3 replication.

---

## 2. Invariants that keep rollbacks safe

1. **Backwards-compatible migrations**: every DB change must be additive for at least one release. Field renames are done via *dual-write* migrations across two releases.
2. **Feature flags gate risky code paths** so a rollback = flag off. Ships with `settings/feature_flags` collection.
3. **Idempotent endpoints** for all payments/withdrawals/finance journal writes.
4. **Signed backups** (optional GPG) so tampering is detectable.
5. **Pre-deploy backup**: the deploy pipeline runs `mongo_backup.sh` immediately before promotion to production.
6. `.last_good_tag` is written **only after** the post-deploy smoke test succeeds.

---

## 3. Ownership & escalation

| Time since incident | Owner                | Action |
|---------------------|----------------------|--------|
| 0–10 min            | On-call engineer     | Perform T1 rollback |
| 10–30 min           | Engineering lead     | Approve T3/T4 rollback |
| 30–60 min           | Head of Engineering  | Trigger incident review meeting |
| > 60 min unresolved | CTO                  | Communicate publicly |

---

## 4. Post-rollback

- Freeze deploys until a fix is merged & CI is green.
- File a post-mortem within 48 hours (blameless).
- Add a regression test that would have caught the bug.
- Update this document with any new invariant discovered.
