# Sprint 14.1.2 — LIVE Quote Ingestion Investigation

**Status:** Trace infrastructure + debug endpoint shipped, ingestion happy-path verified end-to-end via unit tests.

---

## The problem
TwelveData API key was reported as valid (test-connection green) but quotes never landed in `market_price_cache` — the admin UI still showed `source=MOCK`. Sprint 14.1 had already fixed the *overwrite* bugs; this investigation confirms the *ingestion* path.

## What was found via code review

Two places where a valid live batch could silently disappear:
1. **`twelvedata._fetch_quotes()`** – global batch errors (`{"status":"error", …}`) raised a plain `Exception` that tripped the circuit breaker, dropping the whole cycle without a visible log.
2. **`manager.refresh_once()`** – zero structured logging around the provider decision, so operators couldn't tell if TwelveData was even being CHOSEN vs. skipped (backoff / circuit breaker / not configured).

The unit test `test_twelvedata_quote_reaches_market_price_cache` now proves that with a valid key + a well-formed TwelveData response, the quote flows all the way through to `market_price_cache` with `provider=twelvedata` and `source=LIVE`.

## What was shipped

### 1. Structured trace logging at every stage
`market.providers.twelvedata` and `market.providers.manager` now emit **INFO-level** trace lines that identify:
  * which provider was chosen (or why each was skipped),
  * symbols requested vs. symbols parsed,
  * HTTP status + credits-left headers,
  * per-symbol drop reasons (per-symbol error / bad `close` field / no payload),
  * cache accept/reject counts.

Grep these in prod:
```bash
sudo tail -f /var/log/supervisor/backend.err.log \
  | grep -E "refresh_once|TD._fetch_quotes|_choose_provider|market_cache (ACCEPT|REJECT)"
```

### 2. `GET /api/market/debug/xauusd` (Super Admin only, feature-flagged)

Enable with `MARKET_DEBUG_ENABLED=true` in `backend/.env` (already added).

The endpoint performs a **live, isolated, single-symbol** fetch from TwelveData and returns a 9-stage trace:

| Stage             | What it exposes                                                                 |
|-------------------|---------------------------------------------------------------------------------|
| `locate_provider` | api-key fingerprint (first 4 + last 2), circuit-open flag, backoff state        |
| `read_db_config`  | key from Mongo vs. in-memory key **fingerprint match** (catches drift bugs)     |
| `symbol_map`      | canonical XAUUSD → provider symbol `XAU/USD`                                    |
| `http_fetch`      | HTTP status + `api-credits-left` headers + redacted body preview                |
| `json_parse`      | whitelisted response body (`code`, `message`, `close`, `percent_change`, …)     |
| `provider_parse` | Result of `_fetch_quotes([XAUUSD])` for JUST that symbol                        |
| `cache_write`     | If `dry_run=false`, actual accept/reject decision from the priority guard       |
| `mongo_read`      | Current Mongo document for XAUUSD (post-guard)                                  |
| `recent_writes`   | Last 8 audit rows for that symbol from `market_cache_writes`                    |

**Aliases**
* `GET /api/market/debug/xauusd`
* `GET /api/market/debug/quote?symbol=EURUSD&dry_run=false`

**Security**
* Requires super-admin JWT (403 for lesser roles).
* 404 when `MARKET_DEBUG_ENABLED != true`.
* API keys never appear in the response (regex-tested).
* Every call is logged to `admin_audit` with `action=market_debug_trace`.

### 3. Verdict codes returned in `result`
`OK`, `OK_DRY_RUN`, `OK_WRITTEN`, `REJECTED_BY_GUARD`, `PARSED_NONE`,
`NOT_CONFIGURED`, `RATE_LIMITED`, `PARSER_DROPPED_SYMBOL`, `ERROR_HTTP`,
`ERROR_JSON`, `ERROR_PROVIDER_MISSING`, `EXCEPTION_<Type>` — the operator can
tell at a glance where the drop occurred.

### 4. Test-suite hardening
* `tests/test_iter28_market_providers.py::test_refresh_interval_set_and_clamps` now wraps its state mutations in `try/finally` so a mid-test failure can no longer leak a `refresh_interval_sec=5` into subsequent tests.
* New: `tests/test_live_ingestion_iter42.py` — proves the happy-path end-to-end via an in-memory Mongo + monkey-patched httpx.
* New: `tests/test_market_debug_ingestion_iter42.py` — contract tests for the debug endpoint (auth, feature-flag, 9-stage envelope, key-leak protection, audit-trail).

## How to reproduce the drop in prod (with the debug endpoint)

```bash
# 1. Turn the flag on
export MARKET_DEBUG_ENABLED=true
sudo supervisorctl restart backend

# 2. Log in as super admin
TOKEN=$(curl -s -X POST $HOST/api/admin/login \
  -d '{"email":"admin@mfb.in","password":"…"}' -H 'Content-Type: application/json' \
  | jq -r .token)

# 3. Trace
curl -s "$HOST/api/market/debug/xauusd?dry_run=false" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

Interpret the trace `result`:
* `NOT_CONFIGURED` → key missing/blank in DB **or** in-memory copy — fix by re-saving the key in Admin → Market Providers.
* `RATE_LIMITED` → free-tier credit exhaustion (20-symbol batch × 1 credit each vs 8/min). Reduce universe size OR upgrade the TD plan OR raise `refresh_interval_sec`.
* `PARSER_DROPPED_SYMBOL` → TwelveData returned an unexpected key (symbol-map mismatch). Log `stages[3].details.body_preview` will show the actual response.
* `REJECTED_BY_GUARD` → priority/timestamp guard fired (fresh live row still cached). Expected during startup; check `mongo_read` stage to confirm.
* `OK_WRITTEN` → live pipeline confirmed working, admin UI will flip to LIVE within one refresh interval.
