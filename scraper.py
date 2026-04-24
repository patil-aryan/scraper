"""
TikTok creator scraper — Windows native edition.
Run from Cursor terminal. Claude Code watches the log and can fix errors live.
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
    print("TikTokApi not installed. From project root: pip install -r requirements.txt")
    sys.exit(1)

import contacts

load_dotenv()

# Support comma-separated list: MS_TOKEN=token1,token2,token3
_raw_tokens = os.getenv("MS_TOKEN", "")
MS_TOKENS = [t.strip() for t in _raw_tokens.split(",") if t.strip()]

# Residential proxy (IPRoyal). Set in .env:
#   PROXY_SERVER=http://geo.iproyal.com:12321
#   PROXY_USER=username_country-us_session-abc_lifetime-30m
#   PROXY_PASS=yourpassword
PROXY_SERVER = os.getenv("PROXY_SERVER", "").strip()
PROXY_USER = os.getenv("PROXY_USER", "").strip()
PROXY_PASS = os.getenv("PROXY_PASS", "").strip()


def _build_proxy_spec(session_id: int) -> dict | None:
    """
    Return a Playwright-style proxy dict, or None if not configured.
    Injects a per-session sticky key so each worker holds its own IP.
    IPRoyal accepts options on either username or password side — we rewrite
    whichever contains `session-`.
    """
    if not PROXY_SERVER:
        return None
    import re as _re
    user = PROXY_USER
    password = PROXY_PASS
    sticky_key = f"session-w{session_id}{int(time.time())%100000}"
    if "session-" in password:
        password = _re.sub(r"session-[a-zA-Z0-9]+", sticky_key, password)
    elif "session-" in user:
        user = _re.sub(r"session-[a-zA-Z0-9]+", sticky_key, user)
    return {"server": PROXY_SERVER, "username": user, "password": password}


TOKENS_FILE = Path(__file__).parent / "tokens.txt"


def _load_tokens_from_file() -> list[str]:
    """Read tokens.txt (written by token_refresher.py). Returns list of tokens."""
    if not TOKENS_FILE.exists():
        return []
    try:
        return [
            line.strip()
            for line in TOKENS_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    except Exception:
        return []


def reload_tokens() -> int:
    """Merge any new tokens from tokens.txt into MS_TOKENS. Returns count added."""
    file_tokens = _load_tokens_from_file()
    if not file_tokens:
        return 0
    added = 0
    for t in file_tokens:
        if t not in MS_TOKENS:
            MS_TOKENS.append(t)
            added += 1
    return added
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "").strip()   # optional phone alerts
DB_PATH = Path(__file__).parent / "creators.db"
HASHTAG_FILE = Path(__file__).parent / "hashtags.txt"
LOG_PATH = Path(__file__).parent / "scraper.log"

# Tuning for M4 Pro 24GB + residential proxies
NUM_SESSIONS = int(os.getenv("NUM_SESSIONS", "6"))
VIDEOS_PER_HASHTAG = int(os.getenv("VIDEOS_PER_HASHTAG", "500"))
HASHTAGS_PER_BROWSER = int(os.getenv("HASHTAGS_PER_BROWSER", "10"))  # persist API across N hashtags
REQUEST_DELAY = (0.3, 0.8)
HASHTAG_COOLDOWN = (3, 8)
EMPTY_THRESHOLD = 3
SESSION_TIMEOUT = 30 * 60
HEARTBEAT_INTERVAL = 300
MAX_CONSECUTIVE_FAILURES = 5
TOKEN_FAIL_THRESHOLD = 5   # consecutive zero-result hashtags → rotate token
DB_BATCH_SIZE = 50         # flush accumulated rows every N videos

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("scraper")


def notify(title: str, message: str):
    """Push notification to phone via ntfy.sh (free, no account needed).
    Set NTFY_TOPIC in .env to enable. Subscribe to the same topic in the ntfy app."""
    if not NTFY_TOPIC:
        return
    try:
        import urllib.request
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode(),
            headers={"Title": title, "Priority": "high"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log.debug(f"ntfy notification failed: {e}")


def get_token(state: dict) -> str | None:
    """Return current active token, cycling through the list."""
    if not MS_TOKENS:
        return None
    return MS_TOKENS[state.get("token_idx", 0) % len(MS_TOKENS)]


def rotate_token(state: dict):
    """Advance to next token. Returns the new token."""
    old_idx = state.get("token_idx", 0)
    state["token_idx"] = old_idx + 1
    new_token = get_token(state)
    log.warning(
        f"Token rotated: slot {old_idx % len(MS_TOKENS)} → "
        f"{state['token_idx'] % len(MS_TOKENS)} of {len(MS_TOKENS)}"
    )
    notify(
        "TikTok DB — token rotated",
        f"Switched to token {state['token_idx'] % len(MS_TOKENS) + 1}/{len(MS_TOKENS)}. "
        f"Scraper still running.",
    )
    state["token_fails"] = 0
    return new_token


SCHEMA = """
CREATE TABLE IF NOT EXISTS creators (
    sec_uid       TEXT PRIMARY KEY,
    unique_id     TEXT,
    nickname      TEXT,
    signature     TEXT,
    verified      INTEGER,
    follower_count    INTEGER,
    following_count   INTEGER,
    heart_count       INTEGER,
    video_count       INTEGER,
    region        TEXT,
    avatar_url    TEXT,
    email         TEXT,
    instagram     TEXT,
    youtube       TEXT,
    twitter       TEXT,
    website       TEXT,
    first_seen    REAL,
    last_seen     REAL
);
CREATE TABLE IF NOT EXISTS videos (
    video_id      TEXT PRIMARY KEY,
    sec_uid       TEXT,
    create_time   INTEGER,
    desc_text     TEXT,
    duration      INTEGER,
    play_count    INTEGER,
    digg_count    INTEGER,
    comment_count INTEGER,
    share_count   INTEGER,
    collect_count INTEGER,
    hashtag_source TEXT,
    scraped_at    REAL
);
CREATE INDEX IF NOT EXISTS idx_videos_sec_uid    ON videos(sec_uid);
CREATE INDEX IF NOT EXISTS idx_videos_play       ON videos(play_count);
CREATE INDEX IF NOT EXISTS idx_creators_follower ON creators(follower_count);
CREATE INDEX IF NOT EXISTS idx_creators_email    ON creators(email);
CREATE TABLE IF NOT EXISTS hashtag_progress (
    hashtag         TEXT PRIMARY KEY,
    status          TEXT,
    videos_pulled   INTEGER DEFAULT 0,
    last_update     REAL,
    error_count     INTEGER DEFAULT 0,
    last_error      TEXT
);
CREATE TABLE IF NOT EXISTS run_stats (
    ts              REAL,
    creators_total  INTEGER,
    videos_total    INTEGER,
    hashtags_done   INTEGER,
    rotations       INTEGER
);
"""


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA cache_size=-200000")   # 200MB page cache
    conn.execute("PRAGMA mmap_size=8000000000") # 8GB mmap (M4 Pro has 24GB)
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
        conn.executescript(SCHEMA)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(creators)")}
        for col in ("email", "instagram", "youtube", "twitter", "website"):
            if col not in cols:
                conn.execute(f"ALTER TABLE creators ADD COLUMN {col} TEXT")
    log.info(f"Database ready at {DB_PATH}")


# Per-hashtag video limit overrides, populated from `tag:N` lines in hashtags.txt
HASHTAG_LIMITS: dict[str, int] = {}


def load_hashtag_queue():
    try:
        raw = HASHTAG_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        log.error(f"Missing {HASHTAG_FILE}")
        return []
    tags = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        s = s.lstrip("#").lower()
        # Parse optional `:N` suffix: "thriftflip:2000" → tag="thriftflip", limit=2000
        if ":" in s:
            name, _, lim = s.partition(":")
            name = name.strip()
            try:
                HASHTAG_LIMITS[name] = int(lim.strip())
            except ValueError:
                pass
            tags.append(name)
        else:
            tags.append(s)
    if HASHTAG_LIMITS:
        log.info(f"Per-hashtag video limits: {len(HASHTAG_LIMITS)} tags have overrides")
    with db() as conn:
        for t in tags:
            conn.execute(
                "INSERT OR IGNORE INTO hashtag_progress(hashtag, status) VALUES (?, 'pending')",
                (t,),
            )
        conn.execute(
            "UPDATE hashtag_progress SET status='pending' WHERE status='running'"
        )
        pending = [
            r[0]
            for r in conn.execute(
                "SELECT hashtag FROM hashtag_progress "
                "WHERE status IN ('pending','failed') "
                "AND COALESCE(error_count, 0) < 3"
            )
        ]
    # Prioritize: tags with :N overrides (higher limits) run first, then random
    # within each priority tier
    priority = [t for t in pending if t in HASHTAG_LIMITS]
    others   = [t for t in pending if t not in HASHTAG_LIMITS]
    random.shuffle(priority)
    random.shuffle(others)
    pending = priority + others
    log.info(f"Hashtag queue loaded: {len(pending)} pending ({len(priority)} priority :N tags first)")
    return pending


def mark_hashtag(tag, status, videos_pulled=None, error=None):
    try:
        with db() as conn:
            if status == "failed" and error:
                conn.execute(
                    """UPDATE hashtag_progress
                       SET status=?, videos_pulled=COALESCE(?, videos_pulled),
                           last_update=?, error_count=COALESCE(error_count,0)+1,
                           last_error=?
                       WHERE hashtag=?""",
                    (status, videos_pulled, time.time(), str(error)[:500], tag),
                )
            else:
                conn.execute(
                    """UPDATE hashtag_progress
                       SET status=?, videos_pulled=COALESCE(?, videos_pulled),
                           last_update=?
                       WHERE hashtag=?""",
                    (status, videos_pulled, time.time(), tag),
                )
    except Exception as e:
        log.error(f"mark_hashtag({tag}, {status}) failed: {e}")


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
    email=CASE WHEN excluded.email<>'' THEN excluded.email ELSE creators.email END,
    instagram=CASE WHEN excluded.instagram<>'' THEN excluded.instagram ELSE creators.instagram END,
    youtube=CASE WHEN excluded.youtube<>'' THEN excluded.youtube ELSE creators.youtube END,
    twitter=CASE WHEN excluded.twitter<>'' THEN excluded.twitter ELSE creators.twitter END,
    website=CASE WHEN excluded.website<>'' THEN excluded.website ELSE creators.website END,
    last_seen=excluded.last_seen
"""

VIDEO_INSERT_SQL = """
INSERT OR IGNORE INTO videos(video_id, sec_uid, create_time, desc_text,
    duration, play_count, digg_count, comment_count, share_count,
    collect_count, hashtag_source, scraped_at)
VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
"""


def prepare_rows(video_dict, hashtag, contact_cache):
    """
    Parse a video dict → (creator_row, video_row) or None if unusable.
    Uses contact_cache dict keyed by sec_uid to avoid re-regexing the same bio.
    """
    try:
        author = video_dict.get("author") or {}
        stats = video_dict.get("stats") or {}
        author_stats = video_dict.get("authorStats") or {}
        sec_uid = author.get("secUid") or author.get("sec_uid")
        if not sec_uid:
            return None

        contact = contact_cache.get(sec_uid)
        if contact is None:
            contact = contacts.extract_contacts(author)
            contact_cache[sec_uid] = contact

        now = time.time()
        creator_row = (
            sec_uid,
            author.get("uniqueId") or author.get("unique_id"),
            author.get("nickname"),
            author.get("signature"),
            1 if author.get("verified") else 0,
            author_stats.get("followerCount") or author_stats.get("follower_count"),
            author_stats.get("followingCount") or author_stats.get("following_count"),
            author_stats.get("heartCount") or author_stats.get("heart"),
            author_stats.get("videoCount") or author_stats.get("video_count"),
            author.get("region"),
            author.get("avatarThumb") or author.get("avatar_thumb") or "",
            contact["email"],
            contact["instagram"],
            contact["youtube"],
            contact["twitter"],
            contact["website"],
            now,
            now,
        )

        video_row = (
            video_dict.get("id"),
            sec_uid,
            video_dict.get("createTime") or video_dict.get("create_time"),
            (video_dict.get("desc") or "")[:2000],
            (video_dict.get("video") or {}).get("duration"),
            stats.get("playCount") or stats.get("play_count"),
            stats.get("diggCount") or stats.get("digg_count"),
            stats.get("commentCount") or stats.get("comment_count"),
            stats.get("shareCount") or stats.get("share_count"),
            stats.get("collectCount") or stats.get("collect_count"),
            hashtag,
            now,
        )
        return creator_row, video_row
    except Exception as e:
        log.warning(f"prepare_rows failed ({type(e).__name__}): {e}")
        return None


def flush_batch(creator_rows, video_rows):
    """Write a batch of rows in a single transaction. Safe if lists are empty."""
    if not creator_rows and not video_rows:
        return
    try:
        with db() as conn:
            if creator_rows:
                conn.executemany(CREATOR_UPSERT_SQL, creator_rows)
            if video_rows:
                conn.executemany(VIDEO_INSERT_SQL, video_rows)
    except sqlite3.OperationalError as e:
        log.warning(f"DB busy on flush_batch ({len(video_rows)} videos): {e}")
    except Exception as e:
        log.warning(f"flush_batch failed ({type(e).__name__}): {e}")


async def scrape_hashtag(api, tag, session_id, contact_cache):
    limit = HASHTAG_LIMITS.get(tag, VIDEOS_PER_HASHTAG)
    log.info(f"[s{session_id}] START #{tag} (videos={limit})")
    mark_hashtag(tag, "running")
    count = 0
    empty_streak = 0
    start = time.time()
    creator_batch: list[tuple] = []
    video_batch: list[tuple] = []

    def flush_if_full(force=False):
        nonlocal creator_batch, video_batch
        if force or len(video_batch) >= DB_BATCH_SIZE:
            flush_batch(creator_batch, video_batch)
            creator_batch = []
            video_batch = []

    try:
        challenge = api.hashtag(name=tag)
        async for video in challenge.videos(count=limit):
            if time.time() - start > SESSION_TIMEOUT:
                log.warning(f"[s{session_id}] #{tag} TIMEOUT at {count}")
                flush_if_full(force=True)
                mark_hashtag(tag, "failed", count, error="session_timeout")
                return count, True

            try:
                vd = video.as_dict
            except Exception as e:
                log.debug(f"[s{session_id}] bad video: {e}")
                continue

            if not vd or not vd.get("author"):
                empty_streak += 1
                if empty_streak >= EMPTY_THRESHOLD:
                    log.warning(f"[s{session_id}] #{tag} empty streak — flagged")
                    flush_if_full(force=True)
                    mark_hashtag(tag, "failed", count, error="empty_streak")
                    return count, True
                continue
            empty_streak = 0

            rows = prepare_rows(vd, tag, contact_cache)
            if rows is not None:
                creator_batch.append(rows[0])
                video_batch.append(rows[1])
                count += 1
                flush_if_full()

            if count and count % 100 == 0:
                log.info(f"[s{session_id}] #{tag}: {count} videos stored")
                await asyncio.sleep(random.uniform(*REQUEST_DELAY))

    except EmptyResponseException as e:
        flush_if_full(force=True)
        log.warning(f"[s{session_id}] #{tag} EmptyResponse: {e}")
        mark_hashtag(tag, "failed", count, error=f"empty:{e}")
        return count, True
    except InvalidResponseException as e:
        flush_if_full(force=True)
        log.warning(f"[s{session_id}] #{tag} InvalidResponse: {e}")
        mark_hashtag(tag, "failed", count, error=f"invalid:{e}")
        return count, True
    except NotFoundException:
        flush_if_full(force=True)
        log.info(f"[s{session_id}] #{tag} not found, skipping")
        mark_hashtag(tag, "done", count, error="not_found")
        return count, False
    except asyncio.CancelledError:
        flush_if_full(force=True)
        log.info(f"[s{session_id}] #{tag} cancelled")
        mark_hashtag(tag, "pending", count)
        raise
    except Exception as e:
        flush_if_full(force=True)
        err_str = str(e).lower()
        session_dead = any(s in err_str for s in (
            "no valid sessions", "no sessions created", "sessions appear to be dead",
            "target page", "target closed", "browser has been closed",
            "page.evaluate", "context or browser",
        ))
        if session_dead:
            log.warning(
                f"[s{session_id}] #{tag} session died ({type(e).__name__}) — "
                f"got {count} videos, will flag for rotation"
            )
            mark_hashtag(tag, "failed", count, error=f"session_died:{type(e).__name__}")
            return count, True   # flag so worker recreates API
        log.error(
            f"[s{session_id}] #{tag} UNEXPECTED {type(e).__name__}: {e}\n"
            f"{traceback.format_exc()}"
        )
        mark_hashtag(tag, "failed", count, error=f"unexpected:{type(e).__name__}")
        return count, False

    flush_if_full(force=True)
    mark_hashtag(tag, "done", count)
    log.info(f"[s{session_id}] DONE #{tag} ({count} videos, {time.time()-start:.0f}s)")
    return count, False


async def _teardown_api(api):
    """Best-effort async teardown, shielded from cancellation."""
    if api is None:
        return
    try:
        await asyncio.shield(
            asyncio.wait_for(api.__aexit__(None, None, None), timeout=15)
        )
    except Exception:
        pass


async def _spin_up_api(session_id, token):
    """Create a fresh TikTokApi with proxy + token. Returns api or raises."""
    api = TikTokApi()
    await api.__aenter__()
    proxy_spec = _build_proxy_spec(session_id)
    kwargs = dict(
        ms_tokens=[token] if token else None,
        num_sessions=1,
        sleep_after=3,
        headless=True,
        browser=os.getenv("TIKTOK_BROWSER", "chromium"),
        # 90s page load timeout — residential proxy + tiktok.com needs more than default 30s
        timeout=90000,
        # Block heavy resources: saves ~70% bandwidth and speeds up page load 3-5x
        suppress_resource_load_types=["image", "media", "font", "stylesheet"],
    )
    if proxy_spec:
        kwargs["proxies"] = [proxy_spec]
    await api.create_sessions(**kwargs)
    return api


async def worker(session_id, queue, state):
    """
    Single worker loop with a persistent TikTokApi reused across hashtags.
    The browser is only torn down on session-death, hard timeout, or every
    HASHTAGS_PER_BROWSER hashtags (to avoid unbounded drift).
    Returns only when queue is empty.
    """
    failures = 0
    api = None
    hashtags_on_api = 0
    contact_cache: dict = {}  # sec_uid → contact dict, reset when API recycles

    try:
        while True:
            try:
                tag = queue.get_nowait()
            except asyncio.QueueEmpty:
                log.info(f"[s{session_id}] queue empty, exiting")
                return

            # (Re)create API if needed — either first iteration or forced recycle
            if api is None or hashtags_on_api >= HASHTAGS_PER_BROWSER:
                if api is not None:
                    log.info(f"[s{session_id}] recycling browser after {hashtags_on_api} hashtags")
                    await _teardown_api(api)
                    api = None
                    contact_cache.clear()
                token = get_token(state)
                try:
                    api = await _spin_up_api(session_id, token)
                    hashtags_on_api = 0
                except Exception as e:
                    log.error(f"[s{session_id}] session init failed: {e}")
                    await queue.put(tag)
                    failures += 1
                    await asyncio.sleep(min(30 * failures, 180))
                    if failures >= MAX_CONSECUTIVE_FAILURES:
                        raise RuntimeError(f"session init failed {failures}x in a row")
                    continue

            count, flagged = 0, False
            try:
                async with asyncio.timeout(SESSION_TIMEOUT + 60):
                    count, flagged = await scrape_hashtag(api, tag, session_id, contact_cache)
                hashtags_on_api += 1
            except asyncio.TimeoutError:
                log.error(f"[s{session_id}] HARD timeout on #{tag}")
                mark_hashtag(tag, "failed", error="hard_timeout")
                flagged = True
            except asyncio.CancelledError:
                mark_hashtag(tag, "pending")
                raise
            except Exception as e:
                err_str = str(e).lower()
                session_dead = any(s in err_str for s in (
                    "no valid sessions", "no sessions created", "sessions appear to be dead",
                    "target page", "target closed", "browser has been closed",
                    "page.evaluate", "context or browser",
                ))
                if session_dead:
                    log.warning(f"[s{session_id}] #{tag} session died in worker ({type(e).__name__})")
                    mark_hashtag(tag, "failed", error=f"session_died:{type(e).__name__}")
                    flagged = True
                else:
                    log.error(f"[s{session_id}] worker error on #{tag}: {e}")
                    mark_hashtag(tag, "failed", error=f"worker:{type(e).__name__}")
                    failures += 1
                    if failures >= MAX_CONSECUTIVE_FAILURES:
                        raise RuntimeError(f"too many consecutive failures ({failures})")
                    continue

            if count > 0:
                failures = 0
                state["token_fails"] = 0
            else:
                failures += 1
                state["token_fails"] = state.get("token_fails", 0) + 1
                if state["token_fails"] >= TOKEN_FAIL_THRESHOLD and len(MS_TOKENS) > 1:
                    log.warning(f"[s{session_id}] {TOKEN_FAIL_THRESHOLD} consecutive empty runs — rotating token")
                    await asyncio.to_thread(rotate_token, state)
                    # force browser recycle so the new token attaches cleanly
                    await _teardown_api(api)
                    api = None
                    contact_cache.clear()

            # Priority (:N) tag that failed? Requeue up to PRIORITY_RETRY_MAX times
            PRIORITY_RETRY_MAX = 10
            if flagged and tag in HASHTAG_LIMITS:
                retry_key = f"retries_{tag}"
                retries = state.get(retry_key, 0)
                if retries < PRIORITY_RETRY_MAX:
                    state[retry_key] = retries + 1
                    log.warning(
                        f"[s{session_id}] priority #{tag} failed — requeuing "
                        f"(retry {retries + 1}/{PRIORITY_RETRY_MAX})"
                    )
                    await queue.put(tag)
                    # Reset progress row so it shows pending, not failed
                    with db() as conn:
                        conn.execute(
                            "UPDATE hashtag_progress SET status='pending', error_count=0 "
                            "WHERE hashtag=?", (tag,),
                        )
                else:
                    log.warning(
                        f"[s{session_id}] priority #{tag} gave up after {PRIORITY_RETRY_MAX} retries"
                    )

            if flagged and api is not None:
                # Session probably poisoned — tear down so next iter rebuilds
                log.info(f"[s{session_id}] tearing down browser after flag")
                await _teardown_api(api)
                api = None
                contact_cache.clear()

            await asyncio.sleep(random.uniform(*HASHTAG_COOLDOWN))
    finally:
        await _teardown_api(api)


async def supervised_worker(session_id, queue, state, stop_event):
    """Wraps worker() — restarts it if it crashes while queue still has items."""
    restart_count = 0
    while not stop_event.is_set():
        try:
            await worker(session_id, queue, state)
            return  # clean exit — queue was empty
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if stop_event.is_set():
                return
            if queue.empty():
                log.info(f"[s{session_id}] queue empty after crash, supervisor done")
                return
            restart_count += 1
            wait = min(60 * restart_count, 300)  # 1m, 2m, 3m… max 5m
            log.warning(
                f"[s{session_id}] worker crashed: {e} — "
                f"restart #{restart_count} in {wait}s"
            )
            notify(
                "TikTok DB — worker restarted",
                f"Worker {session_id} crashed (restart #{restart_count}): {e}. Still running.",
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=wait)
            except asyncio.TimeoutError:
                pass


async def heartbeat(state, stop_event):
    last_videos = -1
    stall_ticks = 0
    STALL_LIMIT = 6  # 6 × 5min = 30min with no new videos → alert (no VPN to rotate)

    while not stop_event.is_set():
        try:
            with db() as conn:
                creators = conn.execute("SELECT COUNT(*) FROM creators").fetchone()[0]
                videos   = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
                done     = conn.execute(
                    "SELECT COUNT(*) FROM hashtag_progress WHERE status='done'"
                ).fetchone()[0]
                pending  = conn.execute(
                    "SELECT COUNT(*) FROM hashtag_progress WHERE status='pending'"
                ).fetchone()[0]
                with_email = conn.execute(
                    "SELECT COUNT(*) FROM creators WHERE email != '' AND email IS NOT NULL"
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO run_stats(ts, creators_total, videos_total, hashtags_done, rotations) "
                    "VALUES(?,?,?,?,?)",
                    (time.time(), creators, videos, done, 0),
                )

            new_tokens = reload_tokens()
            if new_tokens:
                log.warning(f"⟳ Loaded {new_tokens} fresh token(s) from tokens.txt — total now {len(MS_TOKENS)}")

            log.info(
                f"[heartbeat] creators={creators:,} videos={videos:,} "
                f"done={done} pending={pending} with_email={with_email:,} "
                f"tokens={len(MS_TOKENS)}"
            )

            if videos == last_videos and pending > 0:
                stall_ticks += 1
                if stall_ticks >= STALL_LIMIT:
                    log.warning(
                        f"[watchdog] No new videos in {STALL_LIMIT * HEARTBEAT_INTERVAL // 60}min — "
                        f"check proxy/token health"
                    )
                    notify(
                        "TikTok DB — stall detected",
                        f"No new videos in {STALL_LIMIT * HEARTBEAT_INTERVAL // 60}min. "
                        f"Proxy or token may be dead. Creators so far: {creators:,}",
                    )
                    stall_ticks = 0
            else:
                stall_ticks = 0
            last_videos = videos

        except Exception as e:
            log.error(f"heartbeat failed: {e}")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=HEARTBEAT_INTERVAL)
        except asyncio.TimeoutError:
            pass


async def main():
    init_db()

    file_added = reload_tokens()
    if file_added:
        log.info(f"Loaded {file_added} additional token(s) from tokens.txt")

    if not MS_TOKENS:
        log.warning("MS_TOKEN not set — reliability will drop. See README.")
    else:
        log.info(f"Loaded {len(MS_TOKENS)} token(s). Auto-rotate on {TOKEN_FAIL_THRESHOLD} consecutive empty runs.")

    if PROXY_SERVER:
        log.info(f"✓ Residential proxy: {PROXY_SERVER} (per-worker sticky sessions)")
    else:
        log.warning("⚠ PROXY_SERVER not set — scraping from home IP. TikTok will throttle fast. See .env.example.")

    pending = load_hashtag_queue()
    if not pending:
        log.info("No pending hashtags. Reset with:")
        log.info("  sqlite3 creators.db \"UPDATE hashtag_progress SET status='pending', error_count=0\"")
        return

    queue = asyncio.Queue()
    for t in pending:
        queue.put_nowait(t)

    stop_event = asyncio.Event()
    state = {"token_idx": 0, "token_fails": 0}

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, AttributeError):
            loop.add_signal_handler(sig, stop_event.set)

    workers = [
        asyncio.create_task(supervised_worker(i, queue, state, stop_event))
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
            log.info("Stop signal received — cancelling workers")
            for w in workers:
                w.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.gather(*workers, return_exceptions=True)
        # Make sure stop_task doesn't leak
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
            creators = conn.execute("SELECT COUNT(*) FROM creators").fetchone()[0]
            videos = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
            with_email = conn.execute(
                "SELECT COUNT(*) FROM creators WHERE email != '' AND email IS NOT NULL"
            ).fetchone()[0]
            with_ig = conn.execute(
                "SELECT COUNT(*) FROM creators WHERE instagram != '' AND instagram IS NOT NULL"
            ).fetchone()[0]
    except Exception:
        creators = videos = with_email = with_ig = 0

    log.info("=" * 60)
    log.info(f"RUN COMPLETE: {elapsed/3600:.2f}h")
    log.info(f"  Unique creators:  {creators:,}")
    log.info(f"  With email:       {with_email:,}")
    log.info(f"  With Instagram:   {with_ig:,}")
    log.info(f"  Videos scraped:   {videos:,}")
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
