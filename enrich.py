"""
Second-pass enrichment. After scraper.py has built a creator DB via hashtags,
this script directly pulls each creator's recent videos from the user video
endpoint to get solid, representative stats.

For each candidate creator:
  - Pull up to MAX_VIDEOS_PER_CREATOR recent videos from their profile
  - Recompute median/mean/min/max views, likes, engagement
  - Store in an `enriched_stats` table
  - CSV export uses these enriched stats instead of hashtag-derived ones

Workflow:
  1. Run scraper.py overnight (builds creators table from hashtags)
  2. Run analyze.py to get rough filtered candidates
  3. Run enrich.py to get reliable per-creator stats
  4. Re-run analyze.py with ENRICHED=True — uses accurate stats

Rate limiting: enrichment is ~1 request per creator (vs ~50 per hashtag in
scraper.py), so it's much faster per creator. Still uses VPN rotation and
session pooling for safety.
"""
import asyncio
import contextlib
import logging
import os
import random
import signal
import sqlite3
import sys
import time
import traceback
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
    print("TikTokApi not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

load_dotenv()

MS_TOKEN = os.getenv("MS_TOKEN", "").strip()
DB_PATH = Path(__file__).parent / "creators.db"
LOG_PATH = Path(__file__).parent / "enrich.log"

# Residential proxy (IPRoyal). See scraper.py for .env format.
PROXY_SERVER = os.getenv("PROXY_SERVER", "").strip()
PROXY_USER = os.getenv("PROXY_USER", "").strip()
PROXY_PASS = os.getenv("PROXY_PASS", "").strip()


def _build_proxy_spec(session_id: int) -> dict | None:
    if not PROXY_SERVER:
        return None
    import re as _re
    user = PROXY_USER
    password = PROXY_PASS
    sticky_key = f"session-e{session_id}{int(time.time())%100000}"
    if "session-" in password:
        password = _re.sub(r"session-[a-zA-Z0-9]+", sticky_key, password)
    elif "session-" in user:
        user = _re.sub(r"session-[a-zA-Z0-9]+", sticky_key, user)
    return {"server": PROXY_SERVER, "username": user, "password": password}


# --- Tuning for M4 Pro 24GB + residential proxies ---
NUM_SESSIONS = int(os.getenv("ENRICH_NUM_SESSIONS", "6"))
MAX_VIDEOS_PER_CREATOR = 50           # TikTok paginates; 50 gives reliable medians
CREATORS_PER_BROWSER = int(os.getenv("CREATORS_PER_BROWSER", "25"))  # persist API across N creators
REQUEST_DELAY = (0.3, 0.8)
CREATOR_COOLDOWN = (0.5, 2.0)         # between creators on same session
EMPTY_THRESHOLD = 3
CREATOR_TIMEOUT = 90                  # max seconds per creator
HEARTBEAT_INTERVAL = 300
MAX_CONSECUTIVE_FAILURES = 5

# Pre-filter candidates before enrichment (user's target: 10k-2M followers)
PREFILTER_FOLLOWER_MIN = int(os.getenv("FOLLOWER_MIN", "10000"))
PREFILTER_FOLLOWER_MAX = int(os.getenv("FOLLOWER_MAX", "2000000"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("enrich")


ENRICH_SCHEMA = """
CREATE TABLE IF NOT EXISTS enriched_stats (
    sec_uid           TEXT PRIMARY KEY,
    videos_sampled    INTEGER,
    median_views      INTEGER,
    mean_views        REAL,
    min_views         INTEGER,
    max_views         INTEGER,
    median_likes      INTEGER,
    median_comments   INTEGER,
    median_shares     INTEGER,
    total_views       INTEGER,
    total_engagement  INTEGER,
    engagement_rate   REAL,
    oldest_create_time INTEGER,
    newest_create_time INTEGER,
    posting_days      INTEGER,   -- days between oldest and newest
    posts_per_week    REAL,
    enriched_at       REAL,
    status            TEXT       -- ok | private | not_found | error
);

CREATE TABLE IF NOT EXISTS enrich_progress (
    sec_uid      TEXT PRIMARY KEY,
    status       TEXT,            -- pending | running | done | failed
    attempts     INTEGER DEFAULT 0,
    last_error   TEXT,
    last_update  REAL
);

CREATE INDEX IF NOT EXISTS idx_enrich_status ON enrich_progress(status);
"""


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA cache_size=-200000")
    conn.execute("PRAGMA mmap_size=8000000000")
    conn.execute("PRAGMA temp_store=MEMORY")
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
        conn.executescript(ENRICH_SCHEMA)
    log.info(f"Enrichment schema ready in {DB_PATH}")


def load_candidates():
    """
    Build the enrichment queue: creators within a sensible follower range
    that haven't been enriched yet (or previously failed).
    """
    with db() as conn:
        # Seed enrich_progress for any creators not yet queued
        conn.execute(
            """
            INSERT OR IGNORE INTO enrich_progress(sec_uid, status)
            SELECT sec_uid, 'pending' FROM creators
            WHERE follower_count BETWEEN ? AND ?
            """,
            (PREFILTER_FOLLOWER_MIN, PREFILTER_FOLLOWER_MAX),
        )
        # Reset anything stuck in 'running' from a prior crash
        conn.execute(
            "UPDATE enrich_progress SET status='pending' WHERE status='running'"
        )
        rows = conn.execute(
            """
            SELECT ep.sec_uid, c.unique_id
              FROM enrich_progress ep
              JOIN creators c ON c.sec_uid = ep.sec_uid
             WHERE ep.status IN ('pending', 'failed')
               AND COALESCE(ep.attempts, 0) < 3
            """
        ).fetchall()
    candidates = [(r[0], r[1]) for r in rows if r[1]]
    random.shuffle(candidates)
    log.info(f"Enrichment queue: {len(candidates):,} creators pending")
    return candidates


def mark_candidate(sec_uid, status, error=None):
    try:
        with db() as conn:
            conn.execute(
                """UPDATE enrich_progress
                   SET status=?, last_update=?,
                       attempts=COALESCE(attempts,0)+?,
                       last_error=?
                   WHERE sec_uid=?""",
                (
                    status,
                    time.time(),
                    1 if status in ("done", "failed") else 0,
                    str(error)[:500] if error else None,
                    sec_uid,
                ),
            )
    except Exception as e:
        log.error(f"mark_candidate({sec_uid}, {status}) failed: {e}")


def store_enriched(sec_uid, videos, status="ok"):
    """Compute stats from a list of video dicts and store."""
    if not videos and status == "ok":
        status = "no_videos"

    plays, likes, comments, shares, create_times = [], [], [], [], []
    for v in videos:
        stats = v.get("stats") or {}
        plays.append(stats.get("playCount") or stats.get("play_count") or 0)
        likes.append(stats.get("diggCount") or stats.get("digg_count") or 0)
        comments.append(stats.get("commentCount") or stats.get("comment_count") or 0)
        shares.append(stats.get("shareCount") or stats.get("share_count") or 0)
        ct = v.get("createTime") or v.get("create_time")
        if ct:
            create_times.append(int(ct))

    if plays:
        sorted_plays = sorted(plays)
        n = len(sorted_plays)
        median_views = (
            sorted_plays[n // 2]
            if n % 2
            else (sorted_plays[n // 2 - 1] + sorted_plays[n // 2]) // 2
        )
        sorted_likes = sorted(likes)
        median_likes = (
            sorted_likes[n // 2]
            if n % 2
            else (sorted_likes[n // 2 - 1] + sorted_likes[n // 2]) // 2
        )
        sorted_comments = sorted(comments)
        median_comments = (
            sorted_comments[n // 2]
            if n % 2
            else (sorted_comments[n // 2 - 1] + sorted_comments[n // 2]) // 2
        )
        sorted_shares = sorted(shares)
        median_shares = (
            sorted_shares[n // 2]
            if n % 2
            else (sorted_shares[n // 2 - 1] + sorted_shares[n // 2]) // 2
        )
        total_views = sum(plays)
        total_eng = sum(likes) + sum(comments) + sum(shares)
        er = total_eng / total_views if total_views else 0
    else:
        median_views = median_likes = median_comments = median_shares = 0
        total_views = total_eng = 0
        er = 0

    oldest = min(create_times) if create_times else None
    newest = max(create_times) if create_times else None
    if oldest and newest and newest > oldest:
        posting_days = (newest - oldest) // 86400
        posts_per_week = (len(plays) / max(posting_days, 1)) * 7
    else:
        posting_days = 0
        posts_per_week = 0

    try:
        with db() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO enriched_stats(
                    sec_uid, videos_sampled, median_views, mean_views,
                    min_views, max_views, median_likes, median_comments,
                    median_shares, total_views, total_engagement,
                    engagement_rate, oldest_create_time, newest_create_time,
                    posting_days, posts_per_week, enriched_at, status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sec_uid, len(plays), int(median_views),
                    sum(plays) / len(plays) if plays else 0,
                    min(plays) if plays else 0,
                    max(plays) if plays else 0,
                    int(median_likes), int(median_comments), int(median_shares),
                    total_views, total_eng, round(er, 4),
                    oldest, newest, posting_days, round(posts_per_week, 2),
                    time.time(), status,
                ),
            )
    except Exception as e:
        log.error(f"store_enriched failed for {sec_uid}: {e}")


async def enrich_creator(api, sec_uid, unique_id, session_id):
    """Pull recent videos for one creator. Returns (video_count, flagged)."""
    start = time.time()
    videos = []
    empty_streak = 0

    try:
        user = api.user(username=unique_id, sec_uid=sec_uid)
        async for video in user.videos(count=MAX_VIDEOS_PER_CREATOR):
            if time.time() - start > CREATOR_TIMEOUT:
                log.warning(f"[s{session_id}] @{unique_id} TIMEOUT at {len(videos)}")
                break
            try:
                vd = video.as_dict
            except Exception:
                empty_streak += 1
                if empty_streak >= EMPTY_THRESHOLD:
                    break
                continue
            if not vd:
                empty_streak += 1
                if empty_streak >= EMPTY_THRESHOLD:
                    return videos, True
                continue
            empty_streak = 0
            videos.append(vd)

    except EmptyResponseException as e:
        log.warning(f"[s{session_id}] @{unique_id} empty: {e}")
        mark_candidate(sec_uid, "failed", error=f"empty:{e}")
        return videos, True
    except InvalidResponseException as e:
        log.warning(f"[s{session_id}] @{unique_id} invalid: {e}")
        mark_candidate(sec_uid, "failed", error=f"invalid:{e}")
        return videos, True
    except NotFoundException:
        log.debug(f"[s{session_id}] @{unique_id} not found")
        store_enriched(sec_uid, [], status="not_found")
        mark_candidate(sec_uid, "done", error="not_found")
        return videos, False
    except asyncio.CancelledError:
        mark_candidate(sec_uid, "pending")
        raise
    except Exception as e:
        log.error(f"[s{session_id}] @{unique_id} unexpected {type(e).__name__}: {e}")
        mark_candidate(sec_uid, "failed", error=f"unexpected:{type(e).__name__}")
        return videos, False

    store_enriched(sec_uid, videos, status="ok" if videos else "private_or_empty")
    mark_candidate(sec_uid, "done")
    return videos, False


async def _teardown_api(api):
    if api is None:
        return
    try:
        await asyncio.shield(
            asyncio.wait_for(api.__aexit__(None, None, None), timeout=15)
        )
    except Exception:
        pass


async def _spin_up_api(session_id):
    api = TikTokApi()
    await api.__aenter__()
    proxy_spec = _build_proxy_spec(session_id)
    kwargs = dict(
        ms_tokens=[MS_TOKEN] if MS_TOKEN else None,
        num_sessions=1,
        sleep_after=3,
        headless=True,
        browser=os.getenv("TIKTOK_BROWSER", "chromium"),
        timeout=90000,
        suppress_resource_load_types=["image", "media", "font", "stylesheet"],
    )
    if proxy_spec:
        kwargs["proxies"] = [proxy_spec]
    await api.create_sessions(**kwargs)
    return api


async def worker(session_id, queue, state):
    """Persistent-API enrichment worker. Browser reused across CREATORS_PER_BROWSER creators."""
    failures = 0
    api = None
    creators_on_api = 0

    try:
        while True:
            try:
                sec_uid, unique_id = queue.get_nowait()
            except asyncio.QueueEmpty:
                log.info(f"[s{session_id}] queue empty, exiting")
                return

            if api is None or creators_on_api >= CREATORS_PER_BROWSER:
                if api is not None:
                    log.info(f"[s{session_id}] recycling browser after {creators_on_api} creators")
                    await _teardown_api(api)
                    api = None
                try:
                    api = await _spin_up_api(session_id)
                    creators_on_api = 0
                except Exception as e:
                    log.error(f"[s{session_id}] session init failed: {e}")
                    await queue.put((sec_uid, unique_id))
                    failures += 1
                    await asyncio.sleep(min(30 * failures, 180))
                    if failures >= MAX_CONSECUTIVE_FAILURES:
                        return
                    continue

            video_count, flagged = 0, False
            try:
                async with asyncio.timeout(CREATOR_TIMEOUT + 30):
                    videos, flagged = await enrich_creator(api, sec_uid, unique_id, session_id)
                    video_count = len(videos)
                    state["done"] += 1
                    creators_on_api += 1
                    if state["done"] % 50 == 0:
                        log.info(f"[s{session_id}] @{unique_id}: {video_count} vids (progress: {state['done']:,})")
            except asyncio.TimeoutError:
                log.error(f"[s{session_id}] HARD timeout on @{unique_id}")
                mark_candidate(sec_uid, "failed", error="hard_timeout")
                flagged = True
            except Exception as e:
                log.error(f"[s{session_id}] worker error on @{unique_id}: {e}")
                mark_candidate(sec_uid, "failed", error=f"worker:{type(e).__name__}")
                failures += 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    return
                continue

            if video_count > 0:
                failures = 0
            else:
                failures += 1

            if flagged and api is not None:
                log.info(f"[s{session_id}] tearing down browser after flag")
                await _teardown_api(api)
                api = None

            if failures >= MAX_CONSECUTIVE_FAILURES:
                return

            await asyncio.sleep(random.uniform(*CREATOR_COOLDOWN))
    finally:
        await _teardown_api(api)


async def heartbeat(state, stop_event):
    while not stop_event.is_set():
        try:
            with db() as conn:
                done = conn.execute(
                    "SELECT COUNT(*) FROM enrich_progress WHERE status='done'"
                ).fetchone()[0]
                pending = conn.execute(
                    "SELECT COUNT(*) FROM enrich_progress WHERE status='pending'"
                ).fetchone()[0]
                enriched = conn.execute(
                    "SELECT COUNT(*) FROM enriched_stats WHERE status='ok'"
                ).fetchone()[0]
            log.info(
                f"[♡] enriched={enriched:,} done={done:,} pending={pending:,}"
            )
        except Exception as e:
            log.error(f"heartbeat: {e}")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=HEARTBEAT_INTERVAL)
        except asyncio.TimeoutError:
            pass


async def main():
    init_db()

    if not MS_TOKEN or MS_TOKEN == "paste_your_ms_token_here":
        log.warning("MS_TOKEN not set — reliability drops")

    if PROXY_SERVER:
        log.info(f"✓ Residential proxy: {PROXY_SERVER}")
    else:
        log.warning("⚠ PROXY_SERVER not set — enrichment from home IP. TikTok will throttle fast.")

    log.info(f"Follower prefilter: {PREFILTER_FOLLOWER_MIN:,}–{PREFILTER_FOLLOWER_MAX:,}")

    candidates = load_candidates()
    if not candidates:
        log.info("No candidates to enrich. Done!")
        return

    queue = asyncio.Queue()
    for c in candidates:
        queue.put_nowait(c)

    stop_event = asyncio.Event()
    state = {"done": 0}

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    workers = [
        asyncio.create_task(worker(i, queue, state))
        for i in range(NUM_SESSIONS)
    ]
    hb = asyncio.create_task(heartbeat(state, stop_event))

    start = time.time()
    try:
        # gather() already returns a Future — don't wrap in create_task (Py 3.14+ rejects it)
        done_future = asyncio.gather(*workers, return_exceptions=True)
        stop_task = asyncio.create_task(stop_event.wait())
        await asyncio.wait(
            {done_future, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if stop_event.is_set() and not done_future.done():
            log.info("Stop signal — cancelling workers")
            for w in workers:
                w.cancel()
            with contextlib.suppress(Exception):
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
    try:
        with db() as conn:
            enriched = conn.execute(
                "SELECT COUNT(*) FROM enriched_stats WHERE status='ok'"
            ).fetchone()[0]
            avg_videos = conn.execute(
                "SELECT AVG(videos_sampled) FROM enriched_stats WHERE status='ok'"
            ).fetchone()[0] or 0
    except Exception:
        enriched = 0
        avg_videos = 0

    log.info("=" * 60)
    log.info(f"ENRICHMENT COMPLETE: {elapsed/3600:.2f}h")
    log.info(f"  Creators enriched: {enriched:,}")
    log.info(f"  Avg videos/creator: {avg_videos:.1f}")
    log.info("=" * 60)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted. State saved — re-run to resume.")
    except Exception as e:
        log.critical(f"FATAL: {e}\n{traceback.format_exc()}")
        sys.exit(1)
