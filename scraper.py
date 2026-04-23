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
import vpn_rotate

load_dotenv()

# Support comma-separated list: MS_TOKEN=token1,token2,token3
_raw_tokens = os.getenv("MS_TOKEN", "")
MS_TOKENS = [t.strip() for t in _raw_tokens.split(",") if t.strip()]

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
HOME_IP_OVERRIDE = os.getenv("HOME_IP", "").strip()   # optional, skips auto-detection
PROACTIVE_ROTATION_EVERY = int(os.getenv("PROACTIVE_ROTATION_EVERY", "5"))
DB_PATH = Path(__file__).parent / "creators.db"
HASHTAG_FILE = Path(__file__).parent / "hashtags.txt"
LOG_PATH = Path(__file__).parent / "scraper.log"

NUM_SESSIONS = 3
VIDEOS_PER_HASHTAG = 1500
REQUEST_DELAY = (1.5, 3.0)
HASHTAG_COOLDOWN = (20, 40)
EMPTY_THRESHOLD = 3
MAX_VPN_ROTATIONS = 30
SESSION_TIMEOUT = 30 * 60
HEARTBEAT_INTERVAL = 300
MAX_CONSECUTIVE_FAILURES = 5
TOKEN_FAIL_THRESHOLD = 5   # consecutive zero-result hashtags → rotate token

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


def load_hashtag_queue():
    try:
        raw = HASHTAG_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        log.error(f"Missing {HASHTAG_FILE}")
        return []
    tags = [
        line.strip().lstrip("#").lower()
        for line in raw.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
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
    random.shuffle(pending)
    log.info(f"Hashtag queue loaded: {len(pending)} pending")
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


def extract_and_store(video_dict, hashtag):
    try:
        author = video_dict.get("author") or {}
        stats = video_dict.get("stats") or {}
        author_stats = video_dict.get("authorStats") or {}
        sec_uid = author.get("secUid") or author.get("sec_uid")
        if not sec_uid:
            return False

        contact = contacts.extract_contacts(author)

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
            time.time(),
            time.time(),
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
            time.time(),
        )

        with db() as conn:
            conn.execute(
                """
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
                """,
                creator_row,
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO videos(video_id, sec_uid, create_time, desc_text,
                    duration, play_count, digg_count, comment_count, share_count,
                    collect_count, hashtag_source, scraped_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                video_row,
            )
        return True
    except sqlite3.OperationalError as e:
        log.warning(f"DB busy on extract_and_store: {e}")
        return False
    except Exception as e:
        log.warning(f"extract_and_store failed ({type(e).__name__}): {e}")
        return False


async def scrape_hashtag(api, tag, session_id):
    log.info(f"[s{session_id}] START #{tag}")
    mark_hashtag(tag, "running")
    count = 0
    empty_streak = 0
    start = time.time()

    try:
        challenge = api.hashtag(name=tag)
        async for video in challenge.videos(count=VIDEOS_PER_HASHTAG):
            if time.time() - start > SESSION_TIMEOUT:
                log.warning(f"[s{session_id}] #{tag} TIMEOUT at {count}")
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
                    mark_hashtag(tag, "failed", count, error="empty_streak")
                    return count, True
                continue
            empty_streak = 0

            if extract_and_store(vd, tag):
                count += 1

            if count and count % 100 == 0:
                log.info(f"[s{session_id}] #{tag}: {count} videos stored")
                await asyncio.sleep(random.uniform(*REQUEST_DELAY))

    except EmptyResponseException as e:
        log.warning(f"[s{session_id}] #{tag} EmptyResponse: {e}")
        mark_hashtag(tag, "failed", count, error=f"empty:{e}")
        return count, True
    except InvalidResponseException as e:
        log.warning(f"[s{session_id}] #{tag} InvalidResponse: {e}")
        mark_hashtag(tag, "failed", count, error=f"invalid:{e}")
        return count, True
    except NotFoundException:
        log.info(f"[s{session_id}] #{tag} not found, skipping")
        mark_hashtag(tag, "done", count, error="not_found")
        return count, False
    except asyncio.CancelledError:
        log.info(f"[s{session_id}] #{tag} cancelled")
        mark_hashtag(tag, "pending", count)
        raise
    except Exception as e:
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
            return count, True   # flag so worker triggers rotation
        log.error(
            f"[s{session_id}] #{tag} UNEXPECTED {type(e).__name__}: {e}\n"
            f"{traceback.format_exc()}"
        )
        mark_hashtag(tag, "failed", count, error=f"unexpected:{type(e).__name__}")
        return count, False

    mark_hashtag(tag, "done", count)
    log.info(f"[s{session_id}] DONE #{tag} ({count} videos, {time.time()-start:.0f}s)")
    return count, False


async def worker(session_id, queue, rotation_event, state):
    """Single worker loop. Returns only when queue is empty."""
    failures = 0
    while True:
        if rotation_event.is_set():
            log.info(f"[s{session_id}] paused for VPN rotation")
            while rotation_event.is_set():
                await asyncio.sleep(2)

        try:
            tag = queue.get_nowait()
        except asyncio.QueueEmpty:
            log.info(f"[s{session_id}] queue empty, exiting")
            return

        if PROACTIVE_ROTATION_EVERY > 0:
            state["hashtags_started"] += 1
            if state["hashtags_started"] % PROACTIVE_ROTATION_EVERY == 0:
                if not rotation_event.is_set():
                    rotation_event.set()
                    state["rotations"] += 1
                    log.info(f"[s{session_id}] proactive rotation #{state['rotations']}")
                    try:
                        rotate_ok = await asyncio.to_thread(vpn_rotate.rotate)
                    except Exception as e:
                        log.error(f"proactive rotation failed: {e}")
                        rotate_ok = False
                    if not rotate_ok:
                        # Rotation couldn't confirm a non-home IP — wait longer and skip this hashtag
                        log.warning(f"[s{session_id}] rotation unconfirmed, waiting 60s before next attempt")
                        await asyncio.sleep(60)
                        await queue.put(tag)  # put hashtag back
                        rotation_event.clear()
                        continue
                    await asyncio.sleep(5)
                    rotation_event.clear()

        count, flagged = 0, False
        token = get_token(state)
        api = TikTokApi()
        try:
            async with asyncio.timeout(SESSION_TIMEOUT + 60):
                await api.__aenter__()
                try:
                    await api.create_sessions(
                        ms_tokens=[token] if token else None,
                        num_sessions=1,
                        sleep_after=3,
                        headless=True,
                        browser=os.getenv("TIKTOK_BROWSER", "chromium"),
                    )
                except Exception as e:
                    log.error(f"[s{session_id}] session init failed: {e}")
                    await queue.put(tag)
                    failures += 1
                    await asyncio.sleep(min(30 * failures, 180))
                    if failures >= MAX_CONSECUTIVE_FAILURES:
                        raise RuntimeError(f"session init failed {failures}x in a row")
                    continue
                count, flagged = await scrape_hashtag(api, tag, session_id)
        except asyncio.TimeoutError:
            log.error(f"[s{session_id}] HARD timeout on #{tag}")
            mark_hashtag(tag, "failed", error="hard_timeout")
            flagged = True
        except asyncio.CancelledError:
            mark_hashtag(tag, "pending")
            raise
        except RuntimeError:
            raise   # let supervisor handle
        except Exception as e:
            err_str = str(e).lower()
            session_dead = any(s in err_str for s in (
                "no valid sessions", "no sessions created", "sessions appear to be dead",
                "target page", "target closed", "browser has been closed",
                "page.evaluate", "context or browser",
            ))
            if session_dead:
                log.warning(f"[s{session_id}] #{tag} session died in worker ({type(e).__name__}) — will rotate")
                mark_hashtag(tag, "failed", error=f"session_died:{type(e).__name__}")
                flagged = True
            else:
                log.error(f"[s{session_id}] worker error on #{tag}: {e}")
                mark_hashtag(tag, "failed", error=f"worker:{type(e).__name__}")
                failures += 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    raise RuntimeError(f"too many consecutive failures ({failures})")
                continue
        finally:
            # Always cleanup — shielded so CancelledError doesn't abort cleanup
            try:
                await asyncio.shield(
                    asyncio.wait_for(api.__aexit__(None, None, None), timeout=15)
                )
            except Exception:
                pass

        if count > 0:
            failures = 0
            state["token_fails"] = 0
        else:
            failures += 1
            state["token_fails"] = state.get("token_fails", 0) + 1
            if state["token_fails"] >= TOKEN_FAIL_THRESHOLD and len(MS_TOKENS) > 1:
                log.warning(f"[s{session_id}] {TOKEN_FAIL_THRESHOLD} consecutive empty runs — rotating token")
                await asyncio.to_thread(rotate_token, state)

        if flagged:
            if not rotation_event.is_set():
                if state["rotations"] < MAX_VPN_ROTATIONS:
                    rotation_event.set()
                    state["rotations"] += 1
                    log.warning(f"[s{session_id}] REACTIVE rotation #{state['rotations']}")
                    try:
                        await asyncio.to_thread(vpn_rotate.rotate)
                    except Exception as e:
                        log.error(f"reactive rotation failed: {e}")
                    await asyncio.sleep(5)
                    rotation_event.clear()
                else:
                    log.warning(f"[s{session_id}] rotation cap reached — continuing without rotation")

        await asyncio.sleep(random.uniform(*HASHTAG_COOLDOWN))


async def supervised_worker(session_id, queue, rotation_event, state, stop_event):
    """Wraps worker() — restarts it if it crashes while queue still has items."""
    restart_count = 0
    while not stop_event.is_set():
        try:
            await worker(session_id, queue, rotation_event, state)
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


async def heartbeat(state, stop_event, rotation_event):
    last_videos = -1
    stall_ticks = 0
    STALL_LIMIT = 4  # 4 × 5min = 20min with no new videos → force rotation

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
                    (time.time(), creators, videos, done, state["rotations"]),
                )

            # Reload tokens from tokens.txt every heartbeat (token_refresher writes there)
            new_tokens = reload_tokens()
            if new_tokens:
                log.warning(f"⟳ Loaded {new_tokens} fresh token(s) from tokens.txt — total now {len(MS_TOKENS)}")

            log.info(
                f"[heartbeat] creators={creators:,} videos={videos:,} "
                f"done={done} pending={pending} rotations={state['rotations']} "
                f"with_email={with_email:,} tokens={len(MS_TOKENS)}"
            )

            # Stall watchdog — no new videos for STALL_LIMIT ticks → force VPN rotation
            if videos == last_videos and pending > 0:
                stall_ticks += 1
                if stall_ticks >= STALL_LIMIT:
                    log.warning(
                        f"[watchdog] No new videos in {STALL_LIMIT * HEARTBEAT_INTERVAL // 60}min "
                        f"— forcing VPN rotation"
                    )
                    notify(
                        "TikTok DB — stall detected",
                        f"No new videos in 20min. Forcing VPN rotation. Creators so far: {creators:,}",
                    )
                    if not rotation_event.is_set() and state["rotations"] < MAX_VPN_ROTATIONS:
                        rotation_event.set()
                        state["rotations"] += 1
                        try:
                            await asyncio.to_thread(vpn_rotate.rotate)
                        except Exception as e:
                            log.error(f"watchdog rotation failed: {e}")
                        await asyncio.sleep(5)
                        rotation_event.clear()
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

    # Load any auto-refreshed tokens from tokens.txt (written by token_refresher.py)
    file_added = reload_tokens()
    if file_added:
        log.info(f"Loaded {file_added} additional token(s) from tokens.txt")

    if not MS_TOKENS:
        log.warning("MS_TOKEN not set — reliability will drop. See README.")
    else:
        log.info(f"Loaded {len(MS_TOKENS)} token(s) total. Will auto-rotate on {TOKEN_FAIL_THRESHOLD} consecutive empty runs.")

    # Always clean up leftover WireGuard tunnels from previous runs first
    log.info("Cleaning up any leftover WireGuard tunnels…")
    await asyncio.to_thread(vpn_rotate.cleanup_all_tunnels)

    # Determine home IP: either explicit override in .env, or auto-detect
    if HOME_IP_OVERRIDE:
        vpn_rotate.set_home_ip(HOME_IP_OVERRIDE)
        log.info(f"✓ Home IP (from .env): {HOME_IP_OVERRIDE}")
    else:
        log.info("Detecting home IP (kills any active VPN for accuracy)…")
        # Kill any active openvpn processes so the detected IP is truly home, not VPN
        try:
            import subprocess
            subprocess.run(["taskkill", "/F", "/IM", "openvpn.exe"], capture_output=True, timeout=10)
            subprocess.run(["taskkill", "/F", "/IM", "openvpn-gui.exe"], capture_output=True, timeout=10)
            await asyncio.sleep(3)
        except Exception as e:
            log.debug(f"could not kill openvpn processes: {e}")
        home_ip = await asyncio.to_thread(vpn_rotate.detect_home_ip)
        if home_ip:
            log.info(f"✓ Home IP: {home_ip} — rotations will be rejected if they leak back to this")
            notify(
                "TikTok DB — scraper started",
                f"Home IP: {home_ip}. Scraping will begin after first VPN rotation.",
            )
        else:
            log.warning("⚠ Could not detect home IP. Set HOME_IP=<your_ip> in .env to fix leak detection.")

    pending = load_hashtag_queue()
    if not pending:
        log.info("No pending hashtags. Reset with:")
        log.info("  sqlite3 creators.db \"UPDATE hashtag_progress SET status='pending', error_count=0\"")
        return

    # Initial VPN rotation BEFORE workers start, so they don't try to scrape from home IP
    log.info("Establishing initial VPN tunnel before workers start…")
    initial_ok = await asyncio.to_thread(vpn_rotate.rotate)
    if initial_ok:
        log.info("✓ Initial VPN tunnel up — workers can start")
    else:
        log.warning("⚠ Initial VPN rotation failed. Workers will start anyway and may hit timeouts.")
        notify(
            "TikTok DB — initial VPN failed",
            "Could not establish initial VPN. Workers may scrape from home IP. Check log.",
        )

    queue = asyncio.Queue()
    for t in pending:
        queue.put_nowait(t)

    rotation_event = asyncio.Event()
    stop_event = asyncio.Event()
    state = {"hashtags_started": 0, "rotations": 0, "token_idx": 0, "token_fails": 0}

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, AttributeError):
            loop.add_signal_handler(sig, stop_event.set)

    workers = [
        asyncio.create_task(supervised_worker(i, queue, rotation_event, state, stop_event))
        for i in range(NUM_SESSIONS)
    ]
    hb = asyncio.create_task(heartbeat(state, stop_event, rotation_event))

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
        with contextlib.suppress(Exception):
            await hb
        with contextlib.suppress(Exception):
            vpn_rotate.disconnect_all()

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
    log.info(f"  VPN rotations:    {state['rotations']}")
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
