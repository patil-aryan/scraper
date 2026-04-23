# TikTok Scraper — Master Architecture Plan

> Goal: scrape **millions of TikTok creator profiles locally**, fast, cheap, and resilient. No reliance on paid scraping APIs.

---

## Table of Contents

1. [Goal & Current State](#1-goal--current-state)
2. [Why the Current Approach Caps at ~15k/night](#2-why-the-current-approach-caps-at-15knight)
3. [The Master Architecture](#3-the-master-architecture)
4. [Component-by-Component Breakdown](#4-component-by-component-breakdown)
5. [Open-Source Repos Catalog](#5-open-source-repos-catalog)
6. [Implementation Plan](#6-implementation-plan)
7. [Throughput & Cost Math](#7-throughput--cost-math)
8. [Proxy Strategy](#8-proxy-strategy)
9. [Maintenance Reality](#9-maintenance-reality)
10. [Decision Matrix](#10-decision-matrix)
11. [What NOT to Do](#11-what-not-to-do)
12. [Sources](#12-sources)

---

## 1. Goal & Current State

### Goal

Build a self-hosted, locally-running TikTok scraper capable of:
- **1M+ creator profiles per month** sustained
- **Zero recurring API fees** (proxy costs only — ~$30-100/mo)
- **Resilient** to TikTok's signing algorithm rotations
- **Searchable, enrichable** data fed into existing SQLite + React UI

### Current State (April 2026)

| Component | Tech | Status |
|-----------|------|--------|
| Discovery | TikTokApi 7.3.3 + Playwright (Chromium) | Working, **slow** |
| Sessions | Multi-token, 4 workers, supervisor pattern | Working |
| IP rotation | WireGuard + ProtonVPN (datacenter exits) | **Throttled** by TikTok |
| Token refresh | Separate Playwright process every 30min | Working |
| Storage | SQLite (WAL mode), comprehensive schema | Working |
| Enrichment | Per-creator profile + 50 videos | Working |
| UI | React + Vite + FastAPI, Notion-style | Working |
| **Throughput** | **~13-15k creators / 8 hours** | **Bottlenecked** |

---

## 2. Why the Current Approach Caps at ~15k/night

The bottleneck has **nothing to do with our code**. It's architectural and IP-related:

### Architectural ceiling (Playwright-based scraping)

| Layer | Cost | Impact |
|-------|------|--------|
| Browser launch per session | 10-30 seconds | Throughput floor |
| Memory per worker | 100-200 MB | Caps concurrency at ~4-8 workers/box |
| Bandwidth per page load | 3-15 MB | Burns proxy bandwidth |
| Session lifespan | 50-200 requests | Constant teardown/recreate |
| Per-request latency | 500ms-2s | Even on cache hits |

### IP-related ceiling (datacenter VPN)

| Issue | Detail |
|-------|--------|
| ProtonVPN exits | Datacenter ASNs, flagged by TikTok's classifier |
| Throttling | After ~30-50 req/min per IP: empty responses, 403s |
| Captcha walls | Datacenter IPs trigger CAPTCHAs ~10x more often |
| Session death | TikTok kills sessions originating from flagged IPs faster |

### Combined effect

Theoretical max: 4 workers × 8 req/sec × 7 unique creators/req × 3600s = **800k/hour**.
Actual: dupes, empty responses, session deaths, throttling drag this to **~2k/hour realistic**.

**The fix isn't more VPN configs. It's a different architecture.**

---

## 3. The Master Architecture

The unlock: **stop using Playwright as the scraper**. Use it only as a *signing oracle*. Then fan out to 50-200 plain async HTTP workers that hit TikTok's web JSON endpoints directly.

### High-level diagram

```
                    ┌─────────────────────────────────┐
                    │  msToken Refresher              │
                    │  (1 persistent Playwright       │
                    │   browser, refreshes every 8s)  │
                    └────────────────┬────────────────┘
                                     │ writes to
                                     ▼
                              tokens.txt (live pool)
                                     │ read by
                                     │
┌──────────────────────────────────────────────────────────────────┐
│                  SIGNING LAYER (3-tier fallback chain)            │
│                                                                   │
│   ┌──────────┐  fail   ┌──────────────┐  fail   ┌────────────┐ │
│   │ abogus.py├────────►│ carcabot Node├────────►│ TikTokApi  │ │
│   │ (Python) │         │ (localhost)  │         │ (Playwright│ │
│   │  ~5k/s   │         │  ~50/s       │         │  ~5/s)     │ │
│   └─────┬────┘         └──────┬───────┘         └─────┬──────┘ │
│         │                     │                        │        │
│         └─────────────────────┴────────────────────────┘        │
│                               │ returns signed URL              │
└───────────────────────────────┼──────────────────────────────────┘
                                ▼
                    ┌──────────────────────┐
                    │  Job Queue           │
                    │  (SQLite or Redis)   │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  50-200 aiohttp      │
                    │  async workers       │
                    │  + per-proxy         │
                    │   circuit breaker    │
                    └──────────┬───────────┘
                               │ rotates through
                               ▼
                    ┌──────────────────────┐
                    │  Proxy Pool          │
                    │  (residential/mobile)│
                    └──────────┬───────────┘
                               │
                               ▼
                    TikTok web JSON API
                    (/api/user/detail/, /api/challenge/item_list/, etc.)
                               │
                               ▼
            ┌──────────────────────────────────┐
            │  Parser                          │
            │  (uses TikTokApi data models)    │
            └──────────────────┬───────────────┘
                               │
                               ▼
            ┌──────────────────────────────────┐
            │  Existing SQLite + enrich + UI   │  ← unchanged
            └──────────────────────────────────┘
```

### Per-request cost comparison

| Approach | Time/req | Bandwidth/req | Throughput ceiling |
|----------|----------|---------------|---------------------|
| Current (TikTokApi + Playwright) | 5-30s | 3-15 MB | ~2k/hr realistic |
| Master architecture | 100-300ms | 15-30 KB | ~50k+/hr per box |
| **Improvement** | **~50-100x faster** | **~100x cheaper** | **~25x throughput** |

---

## 4. Component-by-Component Breakdown

### 4.1 msToken Refresher

**Purpose**: TikTok's web API requires a `msToken` cookie that rotates every ~10 seconds. We need fresh tokens always available.

**Implementation**:
- Modified `token_refresher.py` keeps ONE Chromium open permanently
- Every 8 seconds: read `msToken` from cookies → write to `tokens.txt` (atomic)
- Workers read freshest token on every request
- Existing Playwright code mostly reusable

**Cost**: ~150 MB RAM, near-zero CPU.

### 4.2 Signing Layer (3-tier chain)

**Purpose**: TikTok requires `X-Bogus`, `X-Gnarly`, and `_signature` URL parameters. These are computed by JavaScript that TikTok ships in their webapp.

**Three implementations, in priority order**:

#### Tier 1 — abogus.py (PRIMARY, fast)
- Pure Python, ~564 LOC
- No browser, no Node, just Python + `gmssl`
- Throughput: 2,000-10,000 signatures/sec on one CPU core
- **Failure mode**: breaks when TikTok rotates the signing algorithm (~every 2-6 months)
- **Source**: copied from Evil0ctal's repo

#### Tier 2 — carcabot tiktok-signature (SECONDARY, resilient)
- Node.js service running on localhost (e.g., :8080)
- Uses TikTok's **actual** signing JS via headless browser context
- Throughput: 20-80 signatures/sec per Node instance
- **Failure mode**: very rare — only if TikTok blocks the SDK from loading
- **Why include it**: when abogus breaks (2-6mo cycle), this still works because it's TikTok's own code

#### Tier 3 — TikTokApi Playwright session (TERTIARY, last resort)
- Uses davidteather's library directly
- Throughput: 5-10 signatures/sec (browser overhead)
- **Failure mode**: also subject to algorithm changes, but most production-tested
- **Why include it**: fallback of last resort if both above break simultaneously

#### Chain orchestration (`signers/chain.py`)

```python
class SignerChain:
    def __init__(self):
        self.primary = AbogusSigner()
        self.secondary = CarcabotClient()
        self.tertiary = TikTokApiSigner()
        self.failure_counts = {"primary": 0, "secondary": 0}
        self.recovery_timer = 0  # periodically retry primary

    async def sign(self, url: str) -> dict:
        if self.failure_counts["primary"] < 5:
            try:
                return await self.primary.sign(url)
            except SigningBroken:
                self.failure_counts["primary"] += 1

        if self.failure_counts["secondary"] < 5:
            try:
                return await self.secondary.sign(url)
            except SigningBroken:
                self.failure_counts["secondary"] += 1

        return await self.tertiary.sign(url)
```

Add a periodic re-test of primary/secondary so the chain self-heals.

### 4.3 Async Worker Pool

**Purpose**: do the actual HTTP fetching. Many workers, one signer.

**Implementation**:
- `aiohttp.ClientSession` with `asyncio.Semaphore(N)` for concurrency control
- Each worker: pull URL from queue → ask signer for headers → fetch through proxy → parse → upsert
- Per-proxy circuit breaker: 3 strikes → 10min cooldown
- Backoff on 429: exponential, capped at 60s

**Concurrency**: 50-200 workers per machine. Bottleneck is proxy pool size, not Python.

### 4.4 Proxy Pool

**Purpose**: rotate IPs to stay under TikTok's per-IP rate limits.

**Implementation**:
- Webshare/IPRoyal residential pool (rotating)
- Track per-proxy: success count, failure count, last_used
- Round-robin selection, weighted by success rate
- Auto-eject proxies with <50% success rate over last 100 requests

### 4.5 Parser

**Purpose**: convert TikTok's JSON responses to clean Python objects.

**Implementation**:
- Reuse `TikTokApi.api.user.User` and `TikTokApi.api.video.Video` dataclasses
- Store raw response blob in DB alongside parsed columns (insurance against schema drift)

### 4.6 Storage (unchanged)

Existing SQLite WAL setup handles 10k-30k batched inserts/sec. No changes needed.

### 4.7 UI (unchanged)

React frontend keeps working — it just queries `creators.db` via FastAPI. Architecture change is invisible to the UI layer.

---

## 5. Open-Source Repos Catalog

Researched April 2026. Ranked by usefulness to this project.

### Tier 1 — must-fork

| Repo | Stars | Last commit | Role | License |
|------|-------|-------------|------|---------|
| **[Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)** | ~10k | Mar 2025 | Pure-Python `abogus.py` signer (~564 LOC) — our primary signing path | Apache-2.0 |
| **[carcabot/tiktok-signature](https://github.com/carcabot/tiktok-signature)** | 939 | Active 2026 | Node.js sign server using TikTok's real SDK — our secondary signer | MIT |
| **[davidteather/TikTok-Api](https://github.com/davidteather/TikTok-Api)** | ~5k | Apr 2026 (v7.3.3) | Python wrapper + data models — our tertiary signer + parsing reference | MIT |

### Tier 2 — reference / when signing breaks

| Repo | Purpose |
|------|---------|
| **[justbeluga/tiktok-web-reverse-engineering](https://github.com/justbeluga/tiktok-web-reverse-engineering)** | Most current X-Gnarly reference (added 2025) — when X-Gnarly rotates, look here |
| **[justscrapeme/tiktok-web-reverse-engineering](https://github.com/justscrapeme/tiktok-web-reverse-engineering)** | Companion repo to above; `strData`/`eData` encrypt/decrypt |
| **[xtekky/TikTok-Web-Reverse](https://github.com/xtekky/TikTok-Web-Reverse)** | Pure-Python `X-Bogus` + `x-mssdk-info` + `/report` endpoints |
| **[int4444/tiktok-api](https://github.com/int4444/tiktok-api)** | Algorithm walkthrough: double-MD5, RC4, scrambled base64 — read when X-Bogus rotates |
| **[notemrovsky/tiktok-reverse-engineering](https://github.com/notemrovsky/tiktok-reverse-engineering)** | 77 opcodes mapped of TikTok's JS VM, bytecode disassembly — for advanced debugging |

### Tier 3 — Chinese Douyin repos (often most advanced)

Same crypto family as TikTok. Often more actively maintained (Douyin is bigger in China).

| Repo | Purpose |
|------|---------|
| **[erma0/douyin](https://github.com/erma0/douyin)** | Homepage / likes / hashtag / search collector |
| **[cv-cat/DouYin_Spider](https://github.com/cv-cat/DouYin_Spider)** | Full API + livestream scraping |
| **[ohpder/douyin](https://github.com/ohpder/douyin)** | Implementations of `a_bogus`, `__ac_signature`, `_signature`, `X-Bogus` + mobile family (X-Argus/Gorgon/Helios/Khronos/Ladon/Medusa) |
| **[shenydowa/douyin-sign](https://github.com/shenydowa/douyin-sign)** | `xgorgon` + device registration for mobile API |

### Tier 4 — historical reference (mostly broken)

| Repo | Status |
|------|--------|
| **[drawrowfly/tiktok-scraper](https://github.com/drawrowfly/tiktok-scraper)** | JS scraper, 1.4.33 — most functionality broken since SIGI migration; [self-deprecation notice](https://github.com/drawrowfly/tiktok-scraper/issues/695) |
| **[TikHub/TikHub-API-Python-SDK](https://github.com/TikHub/TikHub-API-Python-SDK)** | SDK is open-source; **the signer is NOT** — paid API client only |
| **[networkdynamics/pytok](https://github.com/networkdynamics/pytok)** | Academic Playwright-based scraper — useful for session management patterns |

---

## 6. Implementation Plan

### Phase 1 — Signing core (~2 hours)

1. **Pull `abogus.py`** from Evil0ctal repo, save as `signers/abogus.py`
2. **Test script**: sign `/api/user/detail/?uniqueId=charlidamelio`, fetch with `requests`, print JSON
3. **If JSON returns**: signing works. Move on.

### Phase 2 — Token refresher upgrade (~1 hour)

1. Modify `token_refresher.py` — keep Chromium persistent (don't relaunch every 30min)
2. Refresh msToken from cookies every 8s
3. Atomic write to `tokens.txt` so workers always read fresh tokens

### Phase 3 — Async worker rewrite (~2 hours)

1. New file `scraper_v2.py`
2. Pull from existing hashtag queue
3. Each worker: build URL → `chain.sign(url)` → `aiohttp.get(signed_url, proxy=p)` → parse → upsert
4. `asyncio.Semaphore(50)` for concurrency
5. Per-proxy circuit breaker

### Phase 4 — Add fallback signers (~2 hours)

1. Clone `carcabot/tiktok-signature`, `npm install`, run as `node server.js` on :8080
2. Write `signers/carcabot_client.py` — POSTs URL, parses returned signature
3. Write `signers/tiktokapi_signer.py` — wraps `davidteather/TikTok-Api` as Tier 3
4. Write `signers/chain.py` — orchestrates 3-tier fallback with circuit breakers

### Phase 5 — Proxy integration + testing (~1 hour)

1. Sign up Webshare $5 trial → get 10 proxies for testing
2. Add proxy rotator class with circuit breaker
3. Run with concurrency=5 first, scale to 50 once 429 rate <5%

### Phase 6 — Production launch

1. Upgrade to Webshare residential ($30/mo) or IPRoyal ($7 starter)
2. Queue all 200 hashtags
3. Walk away. Wake up to 100k+ creators.

**Realistic total: 1 focused day, 2 days if hitting bugs.**

---

## 7. Throughput & Cost Math

### Per-layer rates

| Layer | Realistic rate | Bottleneck? |
|-------|---------------|-------------|
| Pure-Python signing (abogus.py) | 2,000-10,000/sec | **Never** |
| Playwright signing oracle | 50-150/sec/browser | Only if we skimp on browsers |
| **Per residential IP** | **~30-60 req/min** | **YES — always** |
| Per mobile proxy IP | 200-500 req/min | Sometimes |
| SQLite WAL inserts | 10k-30k/sec batched | Never |
| aiohttp worker | 100+ req/sec | Never |

### Volume targets → infrastructure

| Goal | Sustained rate | Proxies needed | Time |
|------|---------------|----------------|------|
| 100k profiles | 14 req/sec | 15-25 residential OR 2-3 mobile | 2 hours |
| 1M profiles/day | 12 req/sec sustained | Same | 24 hours |
| 10M profiles/month | Same as above | Same | 30 days |

### Bandwidth cost

- ~15-30 KB per profile (JSON only — no Playwright)
- 1M profiles ≈ 25 GB
- Webshare residential: $1.40-3.50/GB
- **1M profiles ≈ $35-90 in bandwidth**

### Total cost projections

| Volume | Proxy plan | Total cost |
|--------|-----------|------------|
| 100k profiles | Webshare $5 trial | ~$5 |
| 1M profiles | Webshare residential 25GB | ~$35-90 |
| 10M profiles | Webshare residential 250GB | ~$350-900 |

Compare to paid APIs: Apify charges $1/1k = $10,000 for 10M. We're saving **~10-20x** at scale.

---

## 8. Proxy Strategy

### Recommended providers (April 2026 research)

| Provider | $/GB | TikTok-friendly? | Sticky? | Pool | Notes |
|----------|------|------------------|---------|------|-------|
| **Webshare Residential** | $2.80 / $1.12 (annual) | Yes (recommended in TikTokApi README) | Yes | 80M+ | Cheapest mainstream |
| **IPRoyal** | $7 (1GB) / ~$1.75 bulk | Yes | 7-day | Large | Traffic never expires — great for bursty jobs |
| **Decodo (ex-Smartproxy)** | $3.50 PAYG / ~$2.20 bulk | Has TikTok-optimized endpoint | 1-1440 min | 115M+ | Solid mid-tier |
| **Bright Data Residential** | $10.50 list / ~$4 volume | Best success rate | Yes | Largest | Overpriced for DIY |
| **Mobile proxies (iProxy/Proxidize)** | $6-80/proxy/mo | **Best for TikTok** | Yes | — | One mobile > 50 residential |

### Strategy

1. **Dev**: Webshare free 10 proxies. Some will work for signed JSON API (datacenter sometimes OK there).
2. **Production**: Webshare residential $30/mo OR IPRoyal $7 one-time.
3. **Scale-up**: add 1-2 mobile proxies for "always works" backbone.

### What to AVOID

- ❌ Free proxy lists (Spys.one, free-proxy.cz) — burned within hours
- ❌ Datacenter proxies for TikTok — same ASN problem as VPN
- ❌ "TikTok proxies" sold for account management ($1.39/IP) — wrong use case

---

## 9. Maintenance Reality

This is the honest part. Local DIY is not free — it's pay-in-time-instead-of-money.

### What breaks and how often

| Component | Frequency | Severity | Time to fix |
|-----------|-----------|----------|-------------|
| `X-Bogus` algorithm rotation | Every 2-6 months | High | 1-7 days community fix |
| `X-Gnarly` algorithm rotation | Every 2-6 months | High | Same |
| `msToken` cookie name change | Twice in 2024-25 | Medium | ~1 hour |
| JSON response schema drift | Every few weeks | Low | 5 min, if you stored raw blobs |
| Proxy pool degradation | Continuous | Low | Auto-handled by circuit breaker |
| CAPTCHA walls | When pushing too hard | Low | Slow down + rotate |

### Mitigation strategy

1. **Subscribe to Evil0ctal + justbeluga + justscrapeme repos** — when signing breaks, watch their commits
2. **Keep ALL 3 tier signers** — when abogus dies, carcabot + TikTokApi keep us running at 5-50% throughput
3. **Store raw response blobs** in DB — schema changes don't lose data
4. **Per-proxy circuit breaker** — auto-degrades bad proxies
5. **Slow-and-steady mode** — when CAPTCHAs spike, halve concurrency for 1 hour

### Realistic ongoing maintenance

- **Average month**: 4-8 hours
- **Algorithm rotation month**: 1-2 days of debugging
- **Total annual**: ~80-120 hours

---

## 10. Decision Matrix

When to use each approach.

| If you want... | Use this | Cost | Time |
|----------------|----------|------|------|
| 100k profiles ASAP, no engineering | **Apify dltik/tiktok-scraper** | $100-150 | 1 night |
| 100k profiles with contact info | **Bright Data Dataset** | $250 flat | Hours |
| 1M+ profiles, ongoing pipeline | **Master architecture (this doc)** | $30-100/mo proxies | 1 day to build |
| Just to learn how it works | **Read Evil0ctal abogus.py** | Free | Weekend |
| Maximum data, any cost | **Master architecture + bulk dataset** | $30/mo + $250 once | 1 day |

---

## 11. What NOT to Do

Hard-won learnings:

❌ **Don't use WireGuard/ProtonVPN** — datacenter ASNs flagged by TikTok
❌ **Don't use Playwright as the primary scraper** — 100x slower than HTTP+signing
❌ **Don't reverse-engineer X-Gorgon/X-Khronos yourself** unless scraping millions/month — maintenance dwarfs proxy costs
❌ **Don't buy datacenter proxies** "to save money" — same ASN problem as VPN
❌ **Don't use `clockworks/tiktok-scraper`** when `dltik/tiktok-scraper` returns same fields for 1/4 cost (if you go API route)
❌ **Don't forget `route.abort()`** if sticking with Playwright — blocks images/CSS/fonts, 5-10x bandwidth saving
❌ **Don't skip storing raw response blobs** — TikTok schema drift will lose you data
❌ **Don't pay for CAPTCHA solvers** — costs more than the data; just slow down
❌ **Don't run 1 huge worker pool** — split into discovery (5 workers) and detail (50 workers) queues
❌ **Don't rely on a single signer** — three-tier fallback is the difference between "down for a week" and "degraded for an hour"

---

## 12. Sources

### Open-source repos
- [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)
- [Evil0ctal abogus.py (the file we want)](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/main/crawlers/douyin/web/abogus.py)
- [carcabot/tiktok-signature](https://github.com/carcabot/tiktok-signature)
- [davidteather/TikTok-Api](https://github.com/davidteather/TikTok-Api)
- [justbeluga/tiktok-web-reverse-engineering](https://github.com/justbeluga/tiktok-web-reverse-engineering)
- [justscrapeme/tiktok-web-reverse-engineering](https://github.com/justscrapeme/tiktok-web-reverse-engineering)
- [xtekky/TikTok-Web-Reverse](https://github.com/xtekky/TikTok-Web-Reverse)
- [int4444/tiktok-api](https://github.com/int4444/tiktok-api)
- [notemrovsky/tiktok-reverse-engineering](https://github.com/notemrovsky/tiktok-reverse-engineering)
- [erma0/douyin](https://github.com/erma0/douyin)
- [cv-cat/DouYin_Spider](https://github.com/cv-cat/DouYin_Spider)
- [ohpder/douyin](https://github.com/ohpder/douyin)
- [shenydowa/douyin-sign](https://github.com/shenydowa/douyin-sign)
- [drawrowfly/tiktok-scraper (deprecated)](https://github.com/drawrowfly/tiktok-scraper/issues/695)
- [TikHub Python SDK](https://github.com/TikHub/TikHub-API-Python-SDK)
- [networkdynamics/pytok](https://github.com/networkdynamics/pytok)

### Technical references
- [Scrapfly: How To Scrape TikTok in 2026](https://scrapfly.io/blog/posts/how-to-scrape-tiktok-python-json)
- [Decodo: TikTok scraping guide 2026](https://decodo.com/blog/scrape-tiktok)
- [WebScraping.AI: TikTok rate limits](https://webscraping.ai/faq/tiktok-scraping/what-is-the-rate-limit-for-tiktok-s-api-and-how-does-it-affect-scraping)
- [TikTokApi msToken discussion #1101](https://github.com/davidteather/TikTok-Api/discussions/1101)

### Proxy provider research
- [Decodo Residential Pricing](https://decodo.com/proxies/residential-proxies/pricing)
- [IPRoyal Sticky Residential](https://iproyal.com/other-proxies/sticky-residential-proxy/)
- [Webshare Pricing](https://www.webshare.io/pricing)
- [Bright Data Residential](https://brightdata.com)
- [Proxyway Best Residential Proxies 2026](https://proxyway.com/best/residential-proxies)
- [iProxy Mobile TikTok Proxies](https://iproxy.online/tiktok-proxy)

### Paid API alternatives (if going that route)
- [TikHub.io Pricing](https://tikhub.io/pricing) — $0.0005/call at volume
- [Apify dltik/tiktok-scraper](https://apify.com/dltik/tiktok-scraper) — $1/1k profiles
- [ScrapeCreators](https://scrapecreators.com/tiktok-api) — $10 / 5k credits
- [Bright Data TikTok Influencers Dataset](https://brightdata.com/products/datasets/tiktok/influencers) — $250/100k records

---

*Document version: 1.0 — April 2026*
