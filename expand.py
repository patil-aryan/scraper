"""
expand.py — similar-creator network expansion

Instead of scraping hashtags, this mines @mentions from your existing in-range
creators' video captions, then validates each mentioned @handle by hitting their
profile page. Creators who collab, duet, or tag each other cluster by niche +
audience size — so mentions are a much higher-signal discovery channel than
hashtags (expected ~80-90% in-range hit rate vs hashtags' ~55%).

Pipeline:
  1. Mine desc_text of videos from creators in 10k-1M → extract @mentions
  2. Filter out known brand/platform handles
  3. Dedupe against creators we already have
  4. For each new @handle: api.user(handle).info() → parse profile
  5. Store in creators table, extract contact info from bio

Re-run this script after each hashtag discovery phase to compound the pool.
"""
import asyncio
import contextlib
import logging
import os
import random
import re
import signal
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

try:
    from TikTokApi import TikTokApi
    from TikTokApi.exceptions import (
        EmptyResponseException,
        InvalidResponseException,
        NotFoundException,
    )
except ImportError:
    print("Run: pip install -r requirements.txt")
    sys.exit(1)

import contacts

load_dotenv()

MS_TOKENS = [t.strip() for t in os.getenv("MS_TOKEN", "").split(",") if t.strip()]
PROXY_SERVER = os.getenv("PROXY_SERVER", "").strip()
PROXY_USER = os.getenv("PROXY_USER", "").strip()
PROXY_PASS = os.getenv("PROXY_PASS", "").strip()

DB_PATH = Path(__file__).parent / "creators.db"
LOG_PATH = Path(__file__).parent / "expand.log"

NUM_SESSIONS = int(os.getenv("EXPAND_NUM_SESSIONS", "4"))
HANDLES_PER_BROWSER = int(os.getenv("HANDLES_PER_BROWSER", "40"))
FOLLOWER_MIN = int(os.getenv("FOLLOWER_MIN", "10000"))
FOLLOWER_MAX = int(os.getenv("FOLLOWER_MAX", "2000000"))
REQUEST_TIMEOUT = 45
HEARTBEAT_INTERVAL = 120

# Known brand/platform/celeb handles to skip — expand as you see noise
BRAND_DENYLIST = {
    "tiktok", "target", "walmart", "sephora", "ulta", "amazon", "disney",
    "apple", "google", "microsoft", "nike", "adidas", "zara", "shein",
    "nyx", "huda", "charlotte", "saie", "rare", "medicube", "ysl", "aldi",
    "the", "one", "sol", "makeup", "summer", "dollar", "patrick",
    "traderjoes", "trader_joes", "costco", "kirkland", "ikea",
    "netflix", "spotify", "youtube", "instagram", "facebook", "snapchat",
    "drunkelephant", "glossier", "fentybeauty", "rarebeauty", "colourpop",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("expand")


MENTION_RE = re.compile(r"@([a-zA-Z0-9_.]{3,30})")


SCHEMA = """
CREATE TABLE IF NOT EXISTS expand_queue (
    handle        TEXT PRIMARY KEY,
    status        TEXT DEFAULT 'pending',
    mention_count INTEGER DEFAULT 1,
    attempts      INTEGER DEFAULT 0,
    last_error    TEXT,
    last_update   REAL
);
CREATE INDEX IF NOT EXISTS idx_expand_status ON expand_queue(status);
"""


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript(SCHEMA)


def _build_proxy_spec(session_id: int):
    if not PROXY_SERVER:
        return None
    user, password = PROXY_USER, PROXY_PASS
    sticky = f"session-x{session_id}{int(time.time())%100000}"
    if "session-" in password:
        password = re.sub(r"session-[a-zA-Z0-9]+", sticky, password)
    elif "session-" in user:
        user = re.sub(r"session-[a-zA-Z0-9]+", sticky, user)
    return {"server": PROXY_SERVER, "username": user, "password": password}


def mine_mentions_into_queue():
    """Scan existing videos for @mentions from in-range creators, push to expand_queue."""
    from collections import Counter
    with db() as conn:
        existing = {r[0].lower() for r in conn.execute("SELECT unique_id FROM creators WHERE unique_id IS NOT NULL") if r[0]}
        already_queued = {r[0] for r in conn.execute("SELECT handle FROM expand_queue")}

        rows = conn.execute("""
            SELECT v.desc_text FROM videos v
            JOIN creators c ON c.sec_uid=v.sec_uid
            WHERE c.follower_count BETWEEN ? AND ?
              AND v.desc_text IS NOT NULL AND v.desc_text != ''
        """, (FOLLOWER_MIN, FOLLOWER_MAX)).fetchall()

        c: Counter = Counter()
        for (desc,) in rows:
            for m in MENTION_RE.findall(desc):
                ml = m.lower()
                if (
                    len(ml) >= 4                 # skip 3-char noise
                    and ml not in existing        # don't re-fetch
                    and ml not in already_queued  # don't re-queue
                    and ml not in BRAND_DENYLIST
                    and not ml.isdigit()
                ):
                    c[ml] += 1

        new_handles = [(h, n) for h, n in c.items() if n >= 1]
        log.info(f"Mined {len(new_handles):,} new handles from {len(rows):,} videos")

        # Keep ones mentioned 2+ times first — much higher signal
        new_handles.sort(key=lambda x: -x[1])
        conn.executemany(
            "INSERT OR IGNORE INTO expand_queue(handle, mention_count) VALUES (?,?)",
            new_handles,
        )
    log.info(f"Queue seeded: {len(new_handles):,} new handles")


def load_queue():
    with db() as conn:
        conn.execute("UPDATE expand_queue SET status='pending' WHERE status='running'")
        rows = conn.execute("""
            SELECT handle, mention_count FROM expand_queue
             WHERE status IN ('pending','failed')
               AND COALESCE(attempts, 0) < 3
          ORDER BY mention_count DESC, handle ASC
        """).fetchall()
    random.shuffle(rows)
    log.info(f"Queue loaded: {len(rows):,} handles pending")
    return rows


def mark_queue(handle, status, error=None):
    with db() as conn:
        conn.execute("""
            UPDATE expand_queue
            SET status=?, attempts=COALESCE(attempts,0)+?, last_error=?, last_update=?
            WHERE handle=?
        """, (status, 1 if status in ("done", "failed", "skip") else 0,
              str(error)[:300] if error else None, time.time(), handle))


CREATOR_UPSERT_SQL = """
INSERT INTO creators(sec_uid, unique_id, nickname, signature, verified,
    follower_count, following_count, heart_count, video_count, region,
    avatar_url, email, instagram, youtube, twitter, website,
    first_seen, last_seen)
VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(sec_uid) DO UPDATE SET
    follower_count=excluded.follower_count,
    following_count=excluded.following_count,
    heart_count=excluded.heart_count,
    video_count=excluded.video_count,
    region=COALESCE(NULLIF(excluded.region,''), creators.region),
    email=CASE WHEN excluded.email<>'' THEN excluded.email ELSE creators.email END,
    instagram=CASE WHEN excluded.instagram<>'' THEN excluded.instagram ELSE creators.instagram END,
    youtube=CASE WHEN excluded.youtube<>'' THEN excluded.youtube ELSE creators.youtube END,
    twitter=CASE WHEN excluded.twitter<>'' THEN excluded.twitter ELSE creators.twitter END,
    website=CASE WHEN excluded.website<>'' THEN excluded.website ELSE creators.website END,
    last_seen=excluded.last_seen
"""


def store_creator_from_video(video_dict: dict):
    """Parse one of the creator's videos and upsert author info into creators table.
    The video endpoint (/api/post/item_list/) returns rich author data; /api/user/detail/
    is behind X-Gnarly and broken in TikTokApi 7.3.3 — so we use the video route."""
    author = video_dict.get("author") or {}
    author_stats = video_dict.get("authorStats") or {}
    sec_uid = author.get("secUid") or author.get("sec_uid")
    if not sec_uid:
        return None, None
    follower_count = author_stats.get("followerCount") or author_stats.get("follower_count") or 0
    contact = contacts.extract_contacts(author)
    now = time.time()
    row = (
        sec_uid,
        author.get("uniqueId") or author.get("unique_id"),
        author.get("nickname"),
        author.get("signature"),
        1 if author.get("verified") else 0,
        follower_count,
        author_stats.get("followingCount") or author_stats.get("following_count"),
        author_stats.get("heartCount") or author_stats.get("heart"),
        author_stats.get("videoCount") or author_stats.get("video_count"),
        author.get("region") or "",
        author.get("avatarThumb") or author.get("avatar_thumb") or "",
        contact["email"],
        contact["instagram"],
        contact["youtube"],
        contact["twitter"],
        contact["website"],
        now, now,
    )
    with db() as conn:
        conn.execute(CREATOR_UPSERT_SQL, row)
    return sec_uid, follower_count


async def _teardown_api(api):
    if api is None:
        return
    try:
        await asyncio.shield(asyncio.wait_for(api.__aexit__(None, None, None), timeout=15))
    except Exception:
        pass


async def _spin_up_api(session_id, token):
    api = TikTokApi()
    await api.__aenter__()
    proxy_spec = _build_proxy_spec(session_id)
    kwargs = dict(
        ms_tokens=[token] if token else None,
        num_sessions=1, sleep_after=3, headless=True,
        browser=os.getenv("TIKTOK_BROWSER", "webkit"),
        timeout=90000,
        suppress_resource_load_types=["image", "media", "font", "stylesheet"],
    )
    if proxy_spec:
        kwargs["proxies"] = [proxy_spec]
    await api.create_sessions(**kwargs)
    return api


_REHYDRATION_RE = re.compile(
    r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
    re.DOTALL,
)


def _parse_profile_html(html: str):
    """Extract user info from __UNIVERSAL_DATA_FOR_REHYDRATION__ script tag.
    Returns a dict with user+stats keys, or None."""
    import json
    m = _REHYDRATION_RE.search(html)
    if not m:
        return None
    try:
        blob = json.loads(m.group(1))
    except Exception:
        return None
    scope = blob.get("__DEFAULT_SCOPE__", {})
    user_detail = scope.get("webapp.user-detail", {})
    user_info = user_detail.get("userInfo")
    if not user_info:
        return None
    return user_info  # has {"user": {...}, "stats": {...}, "statsV2": {...}}


def _store_from_profile_html(user_info: dict):
    """Store a creator parsed from profile HTML into the creators table."""
    user = user_info.get("user") or {}
    stats = user_info.get("stats") or user_info.get("statsV2") or {}
    sec_uid = user.get("secUid") or user.get("sec_uid")
    if not sec_uid:
        return None, None
    # statsV2 uses strings for counts — coerce
    def _int(v):
        try: return int(v) if v is not None else 0
        except (ValueError, TypeError): return 0
    follower_count = _int(stats.get("followerCount") or stats.get("follower_count"))
    contact = contacts.extract_contacts(user)
    now = time.time()
    row = (
        sec_uid,
        user.get("uniqueId") or user.get("unique_id"),
        user.get("nickname"),
        user.get("signature"),
        1 if user.get("verified") else 0,
        follower_count,
        _int(stats.get("followingCount") or stats.get("following_count")),
        _int(stats.get("heartCount") or stats.get("heart")),
        _int(stats.get("videoCount") or stats.get("video_count")),
        user.get("region") or "",
        user.get("avatarThumb") or user.get("avatar_thumb") or "",
        contact["email"],
        contact["instagram"],
        contact["youtube"],
        contact["twitter"],
        contact["website"],
        now, now,
    )
    with db() as conn:
        conn.execute(CREATOR_UPSERT_SQL, row)
    return sec_uid, follower_count


async def check_handle(api, handle, session_id):
    """
    Navigate Playwright to the profile HTML page directly. Parse embedded JSON
    from <script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"> — contains user + stats.
    Bypasses /api/user/detail/ (X-Gnarly blocked) and /api/post/item_list (requires
    sec_uid we don't have).
    """
    try:
        session = api.sessions[0]  # our _spin_up_api creates num_sessions=1
        page = session.page
        url = f"https://www.tiktok.com/@{handle}"
        await asyncio.wait_for(
            page.goto(url, wait_until="domcontentloaded"), timeout=REQUEST_TIMEOUT
        )
        html = await page.content()
    except asyncio.TimeoutError:
        mark_queue(handle, "failed", error="nav_timeout")
        return False, False, None
    except Exception as e:
        mark_queue(handle, "failed", error=f"nav:{type(e).__name__}")
        return False, False, None

    user_info = _parse_profile_html(html)
    if user_info is None:
        # Rehydration data missing entirely — could be bot wall, redirect, or unknown layout
        mark_queue(handle, "failed", error="no_rehydration_data")
        return False, False, None

    # Valid-profile test: userInfo.user.secUid must be present and non-empty
    user = user_info.get("user") or {}
    if not user.get("secUid"):
        mark_queue(handle, "done", error="not_found")
        return False, False, None

    sec_uid, follower_count = _store_from_profile_html(user_info)
    if sec_uid is None:
        mark_queue(handle, "failed", error="store_failed")
        return False, False, None

    in_range = follower_count is not None and FOLLOWER_MIN <= follower_count <= FOLLOWER_MAX
    mark_queue(handle, "done")
    return True, in_range, follower_count


async def worker(session_id, queue, state):
    failures = 0
    api = None
    handles_on_api = 0
    try:
        while True:
            try:
                handle, _mentions = queue.get_nowait()
            except asyncio.QueueEmpty:
                log.info(f"[w{session_id}] queue empty")
                return

            if api is None or handles_on_api >= HANDLES_PER_BROWSER:
                if api is not None:
                    await _teardown_api(api)
                    api = None
                try:
                    token = MS_TOKENS[state["token_idx"] % len(MS_TOKENS)] if MS_TOKENS else None
                    api = await _spin_up_api(session_id, token)
                    handles_on_api = 0
                except Exception as e:
                    log.error(f"[w{session_id}] session init failed: {e}")
                    await queue.put((handle, _mentions))
                    failures += 1
                    if failures >= 5:
                        return
                    await asyncio.sleep(min(30 * failures, 120))
                    continue

            mark_queue(handle, "running")
            stored, in_range, fc = await check_handle(api, handle, session_id)
            handles_on_api += 1

            state["checked"] += 1
            if stored:
                state["stored"] += 1
                if in_range:
                    state["in_range"] += 1
                    log.info(f"[w{session_id}] ✓ @{handle} ({fc:,} followers) IN RANGE")
                else:
                    log.debug(f"[w{session_id}] @{handle} ({fc:,}) out of range")
            else:
                failures += 1

            if failures >= 5:
                # session may be poisoned
                await _teardown_api(api)
                api = None
                failures = 0

            await asyncio.sleep(random.uniform(0.3, 1.0))
    finally:
        await _teardown_api(api)


async def heartbeat(state, stop_event):
    while not stop_event.is_set():
        try:
            with db() as conn:
                done = conn.execute("SELECT COUNT(*) FROM expand_queue WHERE status='done'").fetchone()[0]
                pending = conn.execute("SELECT COUNT(*) FROM expand_queue WHERE status='pending'").fetchone()[0]
            log.info(
                f"[♡] checked={state['checked']:,} stored={state['stored']:,} "
                f"in_range={state['in_range']:,} pending={pending:,} done={done:,}"
            )
        except Exception as e:
            log.error(f"heartbeat: {e}")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=HEARTBEAT_INTERVAL)
        except asyncio.TimeoutError:
            pass


async def main():
    init_db()
    if not MS_TOKENS:
        log.warning("MS_TOKEN not set — reliability drops")
    if PROXY_SERVER:
        log.info(f"✓ Residential proxy: {PROXY_SERVER}")
    else:
        log.warning("⚠ PROXY_SERVER not set — running from home IP")

    log.info("Mining @mentions from existing videos…")
    mine_mentions_into_queue()

    candidates = load_queue()
    if not candidates:
        log.info("No pending handles. Done.")
        return

    queue = asyncio.Queue()
    for c in candidates:
        queue.put_nowait(c)

    stop_event = asyncio.Event()
    state = {"checked": 0, "stored": 0, "in_range": 0, "token_idx": 0}

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    workers = [asyncio.create_task(worker(i, queue, state)) for i in range(NUM_SESSIONS)]
    hb = asyncio.create_task(heartbeat(state, stop_event))

    start = time.time()
    try:
        done_future = asyncio.gather(*workers, return_exceptions=True)
        stop_task = asyncio.create_task(stop_event.wait())
        await asyncio.wait({done_future, stop_task}, return_when=asyncio.FIRST_COMPLETED)
        if stop_event.is_set() and not done_future.done():
            for w in workers:
                w.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.gather(*workers, return_exceptions=True)
        if not stop_task.done():
            stop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stop_task
    finally:
        stop_event.set()
        hb.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await hb

    elapsed = time.time() - start
    log.info("=" * 60)
    log.info(f"EXPANSION COMPLETE: {elapsed/3600:.2f}h")
    log.info(f"  Handles checked:   {state['checked']:,}")
    log.info(f"  Stored:            {state['stored']:,}")
    log.info(f"  In range:          {state['in_range']:,}")
    log.info("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted. Re-run to resume.")
