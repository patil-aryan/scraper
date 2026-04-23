"""
FastAPI backend for TikTok Creator DB browser.

Development:  uvicorn api:app --reload --port 8000   (Vite proxies /api here)
Production:   npm run build in ui/, then uvicorn api:app --port 8000
              Open http://localhost:8000
"""
import math
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

DB_PATH = Path(__file__).parent / "creators.db"
UI_DIST = Path(__file__).parent / "ui" / "dist"

app = FastAPI(title="TikTok Creator DB")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

NICHE_MAP = {
    # Entertainment / discovery
    "fyp": "entertainment", "foryou": "entertainment", "foryoupage": "entertainment",
    "viral": "entertainment", "trending": "entertainment", "tiktok": "entertainment",
    "tiktokviral": "entertainment",

    # Comedy
    "comedy": "comedy", "funny": "comedy", "memes": "comedy", "pranks": "comedy",
    "skit": "comedy", "relatable": "comedy", "fails": "comedy", "humor": "comedy",
    "jokes": "comedy", "standup": "comedy", "roast": "comedy", "storytime": "comedy",
    "confessions": "comedy", "pov": "comedy",

    # Dance / Music
    "dance": "dance/music", "choreography": "dance/music", "dancer": "dance/music",
    "singing": "dance/music", "singer": "dance/music", "music": "dance/music",
    "musician": "dance/music", "rap": "dance/music", "cover": "dance/music",
    "producer": "dance/music", "hiphop": "dance/music", "rnb": "dance/music",
    "beatmaker": "dance/music", "indieartist": "dance/music",
    "newmusic": "dance/music", "songwriter": "dance/music",

    # Beauty
    "makeup": "beauty", "skincare": "beauty", "beauty": "beauty", "haircare": "beauty",
    "nails": "beauty", "mensgrooming": "beauty", "perfume": "beauty",
    "fragrance": "beauty", "lashes": "beauty", "glowup": "beauty",
    "grwm": "beauty", "hairtok": "beauty", "skintok": "beauty",
    "acne": "beauty", "antiaging": "beauty", "naturalhair": "beauty",

    # Fashion
    "fashion": "fashion", "ootd": "fashion", "outfit": "fashion",
    "streetwear": "fashion", "thrift": "fashion", "thriftflip": "fashion",
    "menstyle": "fashion", "womensfashion": "fashion", "aesthetic": "fashion",
    "stylist": "fashion", "accessories": "fashion", "vintage": "fashion",
    "slowfashion": "fashion", "capsulewardrobe": "fashion",
    "cottagecore": "fashion", "darkacademia": "fashion", "y2k": "fashion",

    # Fitness
    "fitness": "fitness", "gym": "fitness", "workout": "fitness",
    "bodybuilding": "fitness", "yoga": "fitness", "pilates": "fitness",
    "running": "fitness", "crossfit": "fitness", "calisthenics": "fitness",
    "weightloss": "fitness", "homeworkout": "fitness",
    "marathontraining": "fitness", "cycling": "fitness", "swimming": "fitness",

    # Food
    "food": "food", "recipe": "food", "cooking": "food", "baking": "food",
    "foodie": "food", "mealprep": "food", "chef": "food", "restaurant": "food",
    "coffee": "food", "dessert": "food", "vegantok": "food",
    "glutenfree": "food", "sourdough": "food", "fermentation": "food",
    "foodreview": "food",

    # Travel
    "travel": "travel", "wanderlust": "travel", "backpacking": "travel",
    "roadtrip": "travel", "hiking": "travel", "camping": "travel",
    "vanlife": "travel", "solotravel": "travel", "budgettravel": "travel",
    "luxurytravel": "travel", "adventure": "travel",
    "solofemaletravel": "travel", "digitalnomad": "travel",
    "travelhacks": "travel", "airbnb": "travel",

    # Tech
    "tech": "tech", "gadgets": "tech", "iphone": "tech", "android": "tech",
    "apple": "tech", "smarthome": "tech", "ai": "tech", "coding": "tech",
    "programming": "tech", "cybersecurity": "tech",
    "softwaredeveloper": "tech", "linux": "tech", "chatgpt": "tech",
    "machinelearning": "tech", "3dprinting": "tech",

    # Gaming
    "gaming": "gaming", "gamer": "gaming", "fortnite": "gaming",
    "minecraft": "gaming", "valorant": "gaming", "callofduty": "gaming",
    "roblox": "gaming", "pokemon": "gaming", "streamer": "gaming",
    "esports": "gaming", "twitch": "gaming", "gamedev": "gaming",
    "retrogaming": "gaming", "pcgaming": "gaming", "consolegaming": "gaming",

    # Finance
    "finance": "finance", "investing": "finance", "stocks": "finance",
    "crypto": "finance", "personalfinance": "finance", "realestate": "finance",
    "nft": "finance", "frugal": "finance", "debtfree": "finance",

    # Business
    "entrepreneur": "business", "sidehustle": "business", "passiveincome": "business",
    "smallbusiness": "business", "marketing": "business", "copywriting": "business",
    "dropshipping": "business", "ecommerce": "business",

    # Productivity / Education
    "productivity": "productivity", "career": "productivity",
    "jobsearch": "productivity", "lifehack": "productivity",
    "studytok": "education", "student": "education", "college": "education",
    "tutorial": "education", "learnontiktok": "education", "teacher": "education",
    "science": "education", "history": "education", "psychology": "education",
    "philosophy": "education", "languagelearning": "education", "chess": "education",

    # Art
    "art": "art", "drawing": "art", "painting": "art", "photography": "art",
    "digitalart": "art", "illustration": "art", "sketch": "art",
    "tattoo": "art", "ceramics": "art", "interiordesign": "art",
    "architecture": "art", "graphicdesign": "art",

    # DIY / Crafts
    "diy": "diy", "crafts": "diy", "woodworking": "diy",

    # Books
    "booktok": "books", "reading": "books", "writing": "books",
    "poetry": "books", "author": "books", "bookclub": "books",
    "fantasy": "books", "thriller": "books", "selfhelp": "books",
    "nonfiction": "books",

    # Pets
    "pets": "pets", "dog": "pets", "cat": "pets",
    "reptile": "pets", "exoticpets": "pets", "dogtraining": "pets",
    "cattok": "pets", "wildlife": "pets", "horse": "pets", "aquarium": "pets",

    # Lifestyle / Wellness
    "motivation": "lifestyle", "mentalhealth": "lifestyle", "selfcare": "lifestyle",
    "asmr": "lifestyle", "satisfying": "lifestyle", "oddlysatisfying": "lifestyle",
    "nature": "lifestyle", "meditation": "lifestyle", "journaling": "lifestyle",
    "minimalism": "lifestyle", "zerowaste": "lifestyle", "sustainability": "lifestyle",
    "homestead": "lifestyle", "plantmom": "lifestyle", "gardening": "lifestyle",
    "cleaning": "lifestyle", "organization": "lifestyle", "cottagelife": "lifestyle",
    "mindfullness": "lifestyle",

    # Demographic / family
    "mom": "family", "dad": "family", "parenting": "family",
    "pregnancy": "family", "newborn": "family", "adulting": "family",
    "over40": "family", "senior": "family",

    # Identity / community
    "lgbt": "community", "womenempowerment": "community",
    "blacktiktok": "community", "latinotiktok": "community", "asiantiktok": "community",

    # Country-specific (treat as "regional" niche)
    "uktiktok": "regional", "australiantiktok": "regional",
    "canadatiktok": "regional", "indiatiktok": "regional",
    "nigeriatiktok": "regional", "philippinestiktok": "regional",
    "braziltiktok": "regional", "mexicotiktok": "regional",
    "southafricatiktok": "regional", "singaporetiktok": "regional",
}


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA query_only=ON")
    return conn


def db_exists():
    return DB_PATH.exists()


def has_table(conn, name):
    r = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return r[0] > 0


# ── /api/stats ─────────────────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats():
    if not db_exists():
        return {"error": "creators.db not found — run scraper.py first"}
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM creators").fetchone()[0]
        with_email = conn.execute(
            "SELECT COUNT(*) FROM creators WHERE email != '' AND email IS NOT NULL"
        ).fetchone()[0]
        with_ig = conn.execute(
            "SELECT COUNT(*) FROM creators WHERE instagram != '' AND instagram IS NOT NULL"
        ).fetchone()[0]
        with_yt = conn.execute(
            "SELECT COUNT(*) FROM creators WHERE youtube != '' AND youtube IS NOT NULL"
        ).fetchone()[0]
        total_videos = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        hashtags_done = conn.execute(
            "SELECT COUNT(*) FROM hashtag_progress WHERE status='done'"
        ).fetchone()[0]
        hashtags_total = conn.execute("SELECT COUNT(*) FROM hashtag_progress").fetchone()[0]
        enriched = 0
        if has_table(conn, "enriched_stats"):
            enriched = conn.execute(
                "SELECT COUNT(*) FROM enriched_stats WHERE status='ok'"
            ).fetchone()[0]
        return {
            "total_creators": total,
            "total_videos": total_videos,
            "with_email": with_email,
            "with_instagram": with_ig,
            "with_youtube": with_yt,
            "hashtags_done": hashtags_done,
            "hashtags_total": hashtags_total,
            "enriched": enriched,
        }
    finally:
        conn.close()


# ── /api/niches ────────────────────────────────────────────────────────────

@app.get("/api/niches")
def get_niches():
    if not db_exists():
        return []
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT hashtag_source, COUNT(DISTINCT sec_uid) as n FROM videos "
            "WHERE hashtag_source IS NOT NULL GROUP BY hashtag_source"
        ).fetchall()
        niche_counts: dict[str, int] = {}
        for r in rows:
            niche = NICHE_MAP.get(r["hashtag_source"].lower(), "other")
            niche_counts[niche] = niche_counts.get(niche, 0) + r["n"]
        return sorted(
            [{"niche": k, "count": v} for k, v in niche_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )
    finally:
        conn.close()


# ── /api/view_distribution ─────────────────────────────────────────────────

@app.get("/api/view_distribution")
def get_view_distribution():
    if not db_exists():
        return []
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT play_count FROM videos WHERE play_count IS NOT NULL AND play_count > 0"
        ).fetchall()
        buckets = [
            ("0–1k",    0,          1_000),
            ("1k–10k",  1_000,      10_000),
            ("10k–50k", 10_000,     50_000),
            ("50k–100k",50_000,     100_000),
            ("100k–500k",100_000,   500_000),
            ("500k–1M", 500_000,    1_000_000),
            ("1M+",     1_000_000,  float("inf")),
        ]
        counts = {label: 0 for label, _, _ in buckets}
        for (v,) in rows:
            for label, lo, hi in buckets:
                if lo <= v < hi:
                    counts[label] += 1
                    break
        return [{"range": label, "count": counts[label]} for label, _, _ in buckets]
    finally:
        conn.close()


# ── /api/creators ──────────────────────────────────────────────────────────

@app.get("/api/creators")
def get_creators(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort: str = Query("follower_count"),
    order: str = Query("desc"),
    niche: Optional[str] = None,
    median_min: Optional[int] = None,
    median_max: Optional[int] = None,
    follower_min: Optional[int] = None,
    follower_max: Optional[int] = None,
    min_er: Optional[float] = None,
    min_videos: Optional[int] = None,
    has_email: Optional[bool] = None,
    has_instagram: Optional[bool] = None,
    region: Optional[str] = None,
    search: Optional[str] = None,
    use_enriched: bool = Query(True),
):
    if not db_exists():
        return {"items": [], "total": 0, "page": 1, "pages": 0}

    conn = get_db()
    try:
        enriched_available = use_enriched and has_table(conn, "enriched_stats")

        # Per-creator stats aggregation
        video_agg = """
            SELECT
                sec_uid,
                COUNT(*) AS videos_sampled,
                AVG(play_count) AS avg_views,
                MIN(play_count) AS min_views,
                MAX(play_count) AS max_views,
                AVG(digg_count) AS avg_likes,
                CASE WHEN SUM(play_count) > 0
                     THEN (SUM(digg_count)+SUM(comment_count)+SUM(share_count))*1.0/SUM(play_count)
                     ELSE 0 END AS engagement_rate,
                GROUP_CONCAT(DISTINCT hashtag_source) AS hashtags_seen
            FROM videos
            WHERE play_count IS NOT NULL AND play_count >= 0
            GROUP BY sec_uid
        """

        if enriched_available:
            inner = f"""
                SELECT
                    c.sec_uid, c.unique_id, c.nickname, c.signature,
                    c.verified, c.follower_count, c.following_count,
                    c.heart_count, c.video_count, c.region, c.avatar_url,
                    c.email, c.instagram, c.youtube, c.twitter, c.website,
                    COALESCE(e.median_views, va.avg_views) AS median_views,
                    COALESCE(e.mean_views,   va.avg_views) AS mean_views,
                    COALESCE(e.min_views,    va.min_views) AS min_views,
                    COALESCE(e.max_views,    va.max_views) AS max_views,
                    COALESCE(e.engagement_rate, va.engagement_rate) AS engagement_rate,
                    COALESCE(e.videos_sampled,  va.videos_sampled)  AS videos_sampled,
                    COALESCE(e.posts_per_week, 0) AS posts_per_week,
                    va.hashtags_seen,
                    CASE WHEN e.sec_uid IS NOT NULL THEN 1 ELSE 0 END AS is_enriched
                FROM creators c
                LEFT JOIN enriched_stats e ON e.sec_uid = c.sec_uid AND e.status = 'ok'
                LEFT JOIN ({video_agg}) va ON va.sec_uid = c.sec_uid
            """
        else:
            inner = f"""
                SELECT
                    c.sec_uid, c.unique_id, c.nickname, c.signature,
                    c.verified, c.follower_count, c.following_count,
                    c.heart_count, c.video_count, c.region, c.avatar_url,
                    c.email, c.instagram, c.youtube, c.twitter, c.website,
                    va.avg_views AS median_views,
                    va.avg_views AS mean_views,
                    va.min_views, va.max_views,
                    va.engagement_rate, va.videos_sampled,
                    0 AS posts_per_week,
                    va.hashtags_seen,
                    0 AS is_enriched
                FROM creators c
                LEFT JOIN ({video_agg}) va ON va.sec_uid = c.sec_uid
            """

        conditions = ["s.median_views IS NOT NULL"]
        params: list = []

        if median_min is not None:
            conditions.append("s.median_views >= ?"); params.append(median_min)
        if median_max is not None:
            conditions.append("s.median_views <= ?"); params.append(median_max)
        if follower_min is not None:
            conditions.append("s.follower_count >= ?"); params.append(follower_min)
        if follower_max is not None:
            conditions.append("s.follower_count <= ?"); params.append(follower_max)
        if min_er is not None:
            conditions.append("s.engagement_rate >= ?"); params.append(min_er)
        if min_videos is not None:
            conditions.append("s.videos_sampled >= ?"); params.append(min_videos)
        if has_email:
            conditions.append("s.email != '' AND s.email IS NOT NULL")
        if has_instagram:
            conditions.append("s.instagram != '' AND s.instagram IS NOT NULL")
        if region:
            conditions.append("s.region = ?"); params.append(region)
        if search:
            # Search across handle, nickname, bio, email, and social handles
            like = f"%{search}%"
            conditions.append(
                "(s.unique_id LIKE ? OR s.nickname LIKE ? OR s.signature LIKE ? "
                "OR s.email LIKE ? OR s.instagram LIKE ? OR s.youtube LIKE ? "
                "OR s.twitter LIKE ? OR s.website LIKE ?)"
            )
            params.extend([like] * 8)
        if niche and niche != "all":
            tags = [k for k, v in NICHE_MAP.items() if v == niche]
            if tags:
                ph = ",".join("?" * len(tags))
                conditions.append(
                    f"s.sec_uid IN (SELECT DISTINCT sec_uid FROM videos "
                    f"WHERE hashtag_source IN ({ph}))"
                )
                params.extend(tags)

        where = " AND ".join(conditions)

        valid_sorts = {
            "follower_count": "s.follower_count",
            "median_views": "s.median_views",
            "mean_views": "s.mean_views",
            "engagement_rate": "s.engagement_rate",
            "videos_sampled": "s.videos_sampled",
            "handle": "s.unique_id",
            "posts_per_week": "s.posts_per_week",
        }
        sort_col = valid_sorts.get(sort, "s.follower_count")
        order_dir = "DESC" if order.lower() == "desc" else "ASC"

        total = conn.execute(
            f"SELECT COUNT(*) FROM ({inner}) s WHERE {where}", params
        ).fetchone()[0]

        offset = (page - 1) * per_page
        rows = conn.execute(
            f"SELECT * FROM ({inner}) s WHERE {where} "
            f"ORDER BY {sort_col} {order_dir} NULLS LAST "
            f"LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()

        items = []
        for r in rows:
            d = dict(r)
            d["profile_url"] = f"https://tiktok.com/@{d.get('unique_id', '')}"
            for f in ("median_views", "mean_views", "min_views", "max_views"):
                d[f] = int(d[f] or 0)
            d["engagement_rate"] = round(float(d["engagement_rate"] or 0), 4)
            d["follower_count"] = d["follower_count"] or 0
            items.append(d)

        return {
            "items": items,
            "total": total,
            "page": page,
            "pages": math.ceil(total / per_page) if per_page else 1,
        }
    finally:
        conn.close()


# ── /api/creator/:sec_uid ──────────────────────────────────────────────────

@app.get("/api/creator/{sec_uid}")
def get_creator(sec_uid: str):
    if not db_exists():
        return JSONResponse({"error": "DB not found"}, status_code=404)
    conn = get_db()
    try:
        creator = conn.execute(
            "SELECT * FROM creators WHERE sec_uid = ?", (sec_uid,)
        ).fetchone()
        if not creator:
            return JSONResponse({"error": "Not found"}, status_code=404)

        videos = conn.execute(
            """SELECT video_id, create_time, play_count, digg_count,
                      comment_count, share_count, collect_count, hashtag_source
               FROM videos WHERE sec_uid = ?
               ORDER BY create_time DESC LIMIT 50""",
            (sec_uid,),
        ).fetchall()

        enriched = None
        if has_table(conn, "enriched_stats"):
            row = conn.execute(
                "SELECT * FROM enriched_stats WHERE sec_uid = ?", (sec_uid,)
            ).fetchone()
            if row:
                enriched = dict(row)

        return {
            "creator": dict(creator),
            "videos": [dict(v) for v in videos],
            "enriched": enriched,
        }
    finally:
        conn.close()


# ── /api/creators/export ───────────────────────────────────────────────────

@app.get("/api/creators/export")
def export_creators(
    format: str = Query("csv", regex="^(csv|json)$"),
    sort: str = Query("follower_count"),
    order: str = Query("desc"),
    niche: Optional[str] = None,
    median_min: Optional[int] = None,
    median_max: Optional[int] = None,
    follower_min: Optional[int] = None,
    follower_max: Optional[int] = None,
    min_er: Optional[float] = None,
    min_videos: Optional[int] = None,
    has_email: Optional[bool] = None,
    has_instagram: Optional[bool] = None,
    region: Optional[str] = None,
    search: Optional[str] = None,
    use_enriched: bool = Query(True),
    limit: int = Query(50000, ge=1, le=200000),
):
    """Export filtered creators as CSV or JSON. Uses the same filters as /api/creators."""
    import csv, io, json
    from fastapi.responses import StreamingResponse, Response
    from datetime import datetime

    # Reuse the same query logic as get_creators by calling it with a high page size
    result = get_creators(
        page=1, per_page=limit, sort=sort, order=order,
        niche=niche, median_min=median_min, median_max=median_max,
        follower_min=follower_min, follower_max=follower_max,
        min_er=min_er, min_videos=min_videos,
        has_email=has_email, has_instagram=has_instagram,
        region=region, search=search, use_enriched=use_enriched,
    )
    items = result.get("items", []) if isinstance(result, dict) else []

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"creators-{timestamp}.{format}"

    if format == "json":
        body = json.dumps(
            {"exported_at": timestamp, "total": len(items), "items": items},
            indent=2, default=str,
        )
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # CSV
    fields = [
        "unique_id", "nickname", "verified", "region",
        "follower_count", "following_count", "heart_count", "video_count",
        "median_views", "mean_views", "min_views", "max_views",
        "engagement_rate", "videos_sampled", "posts_per_week", "is_enriched",
        "email", "instagram", "youtube", "twitter", "website",
        "profile_url", "hashtags_seen", "signature", "sec_uid",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        # Flatten signature (bio) for CSV
        row = dict(item)
        if row.get("signature"):
            row["signature"] = row["signature"].replace("\n", " ").replace("\r", " ")
        writer.writerow(row)

    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── /api/regions ───────────────────────────────────────────────────────────

@app.get("/api/regions")
def get_regions():
    if not db_exists():
        return []
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT region, COUNT(*) as n FROM creators "
            "WHERE region IS NOT NULL AND region != '' "
            "GROUP BY region ORDER BY n DESC"
        ).fetchall()
        return [{"region": r["region"], "count": r["n"]} for r in rows]
    finally:
        conn.close()


# ── Serve built React app ──────────────────────────────────────────────────

if UI_DIST.exists():
    assets_dir = UI_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        # Let /api/* routes above handle API calls
        static = UI_DIST / full_path
        if static.exists() and static.is_file():
            return FileResponse(str(static))
        return FileResponse(str(UI_DIST / "index.html"))
else:
    @app.get("/")
    def no_ui():
        return {"message": "Run 'npm run build' inside the ui/ folder first, or use Vite dev server."}
