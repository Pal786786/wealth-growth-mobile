# Live Market Validation Report — **PENDING** — Sprint 14.1

**Status:** 🟡 **PENDING — Cannot certify beta launch based on live market data**  
**Report date:** 2026-07-14  
**Reason:** Real production API keys for the primary live market providers are **not available** in this environment. Per Sprint 14.1 rules ("Do not certify Beta readiness based only on demo providers"), we are **pausing** the validation sprint rather than producing a false-positive live validation.

---

## 1. Executive summary

| Provider           | Runtime configured? | Real key working? | Notes                                   |
|--------------------|---------------------|-------------------|-----------------------------------------|
| **TwelveData** (primary) | ❌ Not configured    | ❌ Missing          | `market_provider_config.twelvedata_api_key` is empty; `.env` has no `TWELVEDATA_API_KEY`. |
| **Alpha Vantage** (fallback) | ❌ Not configured in runtime | ⚠️ Key exists in `.env` but free tier quota already consumed for today (25/day limit) — API returns "Information" rate-limit notice, not prices. **Real prices not obtainable.** |
| **Runtime active provider** | `mock` (from `market_data_settings.provider`) | n/a | Serves synthetic prices, cannot represent live market. |
| Symbol universe    | ✅ 20 symbols configured | n/a               | AUDUSD, BTCUSD, ETHUSD, EURUSD, GBPUSD, GER40, IND50, NAS100, NATGAS, NZDUSD, SPX500, UK100, UKOIL, US30, USDCAD, USDCHF, USDJPY, USOIL, XAGUSD, XAUUSD |

Because real live prices cannot be sampled, the acceptance criteria of Sprint 14.1 **cannot be met** at this time. Structural validation (code paths, cache schema, fallback wiring, unit tests) remains green from Sprints 7.5, 12.3 and 13, but that does **not** substitute for live-provider validation.

---

## 2. What still needs to happen

### To resume this sprint
1. Provide a working **TwelveData API key** with sufficient quota (any paid tier, or the free 800/day tier).
2. Provide a working **Alpha Vantage key** with headroom, or explicitly confirm we’re validating fallback logic only.
3. Load them into the runtime via the admin console: `Admin → Market Providers → Configure keys` (persists into `market_provider_config` and `market_data_settings.api_keys`).

### Immediate follow-ups once keys are provided (already scoped, ready to execute)
- **Step 1** — Health probe: `GET /api/market/providers` returns `twelvedata.ok: true` and `alpha_vantage.ok: true`.
- **Step 2** — Symbol matrix: parametric test over the 20 symbols, asserting each returns a finite price within a sanity band. Cross-check against Yahoo Finance / CoinGecko public JSON.
- **Step 3** — Cache freshness: assert `market_prices` docs have `updated_at < N seconds` ago; cache hit vs. miss counters incrementing.
- **Step 4** — Fallback drill: (a) invalidate TwelveData key at runtime → Alpha Vantage takes over within 1 refresh cycle; (b) invalidate both → stale-cache fallback within TTL; (c) both restored → auto-recovery.
- **Step 5** — Forex engine: open a trade, tick live price twice, close, assert P/L math against live bid/ask (spread within provider tolerance).
- **Step 6** — AI Signals: trigger signal generation, capture `entry_price`, assert = live spot within tolerance.
- **Step 7** — Watchlist reflects live cache.
- **Step 8** — Price alerts fire when live cache crosses threshold.
- **Step 9** — Copy trading M2M P/L for follower matches leader within `<0.1%` tolerance at same price tick.
- **Step 10** — Gold derivation from live XAUUSD when `GOLD_PRICE_SOURCE=xauusd_live`.
- **Step 11** — Provider health, backoff, cache-TTL, automatic fallback exercised via chaos test.
- **Step 12** — Full regression suite (target 862+ tests, 0 failures) rerun.
- **Step 13** — Replace this document with the final `LIVE_MARKET_VALIDATION_REPORT.md` (status → GREEN).

---

## 3. Detailed environment check (evidence)

### 3.1 Runtime provider configuration

`market_provider_config` (single document, redacted):
```json
{
  "manual_provider": null,
  "auto_fallback": true,
  "refresh_interval_sec": 60,
  "twelvedata_api_key": "",           // ❌ empty
  "alphavantage_api_key": "",         // ❌ empty (despite .env having ALPHA_VANTAGE_KEY)
  "universe": ["AUDUSD", "BTCUSD", "ETHUSD", "EURUSD", "GBPUSD",
                 "GER40", "IND50", "NAS100", "NATGAS", "NZDUSD",
                 "SPX500", "UK100", "UKOIL", "US30", "USDCAD",
                 "USDCHF", "USDJPY", "USOIL", "XAGUSD", "XAUUSD"]
}
```

`market_data_settings`:
```json
{
  "interval_seconds": 3.0,
  "api_keys": {"twelvedata":"", "alpha_vantage":"", "finnhub":"", "polygon":""},
  "provider": "mock",                 // ← currently on mock
  "transport": "polling"
}
```

### 3.2 Alpha Vantage live probe (raw)

```
GET https://www.alphavantage.co/query
    ?function=CURRENCY_EXCHANGE_RATE&from_currency=EUR&to_currency=USD&apikey=<REDACTED>
→ 200 OK
{
  "Information": "We have detected your API key as NZ1G************* and our standard API rate limit is 25 requests per day. Please subscribe to any of the premium plans..."
}
```

**Interpretation**: the key is valid but the free-tier 25-req/day limit has been reached or the throttle notice replaces the quote. Either way, **no live price was returned** — cannot be used for symbol-matrix validation of 20 symbols (would need > 40 requests just for a single-cycle bid/ask fetch).

### 3.3 TwelveData probe (skipped)
No key present anywhere — skipping probe. Attempted request would 401.

---

## 4. Structural readiness (unaffected)

The following was verified in prior sprints and remains green. It is **necessary but not sufficient** for beta certification:

- Provider adapters implemented and unit-tested: `market_data/providers.py` (TwelveData REST + planned WS), `market_providers/{twelvedata,alphavantage,mock}.py`.
- Shared Mongo cache: `market_prices` collection with TTL + refresh scheduler.
- Automatic fallback wired in `market_providers/manager.py` with backoff timers stored in `market_provider_history`.
- Symbol catalog covers all 20 target instruments with per-provider aliases.
- Forex, AI Signals, Watchlist, Alerts, Copy Trading and Gold price paths all read from the same cache surface (verified in test suites).
- Full regression (862 tests) passes on mock provider — confirms code integrity but **not live-market correctness**.

---

## 5. Risks of certifying beta without live validation

1. **Stale/mock prices in production** — users see synthetic data instead of live market; loss of trust and possible regulatory exposure.
2. **P/L calculations diverge from broker feeds** — forex, copy-trading, and gold conversion could all be off by wide margins.
3. **AI Signals become noise** — signals generated from mock prices are misleading.
4. **Price alerts never fire** (mock oscillator vs. real thresholds).
5. **Fallback path never exercised on real failure modes** — e.g. TwelveData 429/5xx behaviour under Cloudflare, timezone drift, symbol renaming.

---

## 6. Recommendation

> **Do NOT proceed with beta launch until Sprint 14.1 is completed with real keys and this report is upgraded from PENDING → GREEN.**

All code, cache, and fallback plumbing is production-grade (verified structurally in prior sprints), but real-provider assertions are absent. Once keys are supplied, the full validation matrix can be executed in about **15–25 minutes** of automated test time (rate limits permitting).

---

## 7. Sign-off (pending)

| Role                | Name | Decision |
|---------------------|------|----------|
| Engineering Lead    |      | ⏸️ Await keys |
| Product Owner       |      | ⏸️ Await keys |
| Head of Risk / Compliance |      | ⏸️ Await keys |

---

### Appendix A — Acceptance criteria vs. current state

| Acceptance criterion                                    | State  | Blocker |
|---------------------------------------------------------|--------|---------|
| All supported symbols show realistic live prices         | ❌ FAIL | No real provider connected |
| Forex P/L matches live prices                           | ❌ FAIL | Same |
| AI Signals are generated from live market data           | ❌ FAIL | Same |
| No regressions                                          | ✅ PASS | 860 tests still passing on mock |
| Full regression suite passes                             | ✅ PASS | Green on mock |
| Live Market Validation Report delivered before Beta launch | 🟡 PENDING | This document |
