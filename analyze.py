"""
Creator-centric export with contact info.

One row per creator. Columns:
  handle, profile_url, nickname, niche, secondary_niches, region, verified,
  followers, following, total_likes, videos_on_account, videos_scraped,
  median_views, mean_views, min_views, max_views,
  median_likes, median_comments, median_shares,
  engagement_rate, views_per_follower,
  email, instagram, youtube, twitter, website,     # <-- contact columns
  oldest_video, newest_video, hashtags_seen_in,
  sec_uid, avatar_url, bio

Filters: MEDIAN_MIN..MEDIAN_MAX views, FOLLOWER_MIN..FOLLOWER_MAX,
MIN_VIDEOS per creator, MIN_ER engagement floor.

Output: creators_filtered.csv ranked by quality score.
"""
import csv
import sqlite3
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "creators.db"
OUT_CSV = Path(__file__).parent / "creators_filtered.csv"

# ---- tuning ----
MEDIAN_MIN = 10_000
MEDIAN_MAX = 100_000
MIN_VIDEOS = 3
FOLLOWER_MIN = 1_000
FOLLOWER_MAX = 500_000
MIN_ER = 0.02
# Set to True to only export creators with an email (tighter outreach list)
EMAIL_ONLY = False
# Use enriched_stats table (from enrich.py) instead of hashtag-derived stats.
# Enriched stats are much more accurate because they sample 30+ videos per
# creator directly from their profile. Falls back to hashtag stats if no
# enrichment data exists for a creator.
USE_ENRICHED = True
# ----------------

NICHE_MAP = {
    "fyp": "entertainment", "foryou": "entertainment", "foryoupage": "entertainment",
    "viral": "entertainment", "trending": "entertainment", "tiktok": "entertainment",
    "tiktokviral": "entertainment",
    "comedy": "comedy", "funny": "comedy", "memes": "comedy", "pranks": "comedy",
    "skit": "comedy", "relatable": "comedy", "fails": "comedy", "humor": "comedy",
    "jokes": "comedy", "standup": "comedy",
    "dance": "dance_music", "choreography": "dance_music", "dancer": "dance_music",
    "singing": "dance_music", "singer": "dance_music", "music": "dance_music",
    "musician": "dance_music", "rap": "dance_music", "cover": "dance_music",
    "producer": "dance_music",
    "makeup": "beauty", "skincare": "beauty", "beauty": "beauty", "haircare": "beauty",
    "nails": "beauty", "mensgrooming": "beauty", "perfume": "beauty",
    "fragrance": "beauty", "lashes": "beauty", "glowup": "beauty",
    "fashion": "fashion", "ootd": "fashion", "outfit": "fashion",
    "streetwear": "fashion", "thrift": "fashion", "menstyle": "fashion",
    "womensfashion": "fashion", "aesthetic": "fashion", "stylist": "fashion",
    "accessories": "fashion",
    "fitness": "fitness", "gym": "fitness", "workout": "fitness",
    "bodybuilding": "fitness", "yoga": "fitness", "pilates": "fitness",
    "running": "fitness", "crossfit": "fitness", "calisthenics": "fitness",
    "weightloss": "fitness",
    "food": "food", "recipe": "food", "cooking": "food", "baking": "food",
    "foodie": "food", "mealprep": "food", "chef": "food", "restaurant": "food",
    "coffee": "food", "dessert": "food",
    "travel": "travel", "wanderlust": "travel", "backpacking": "travel",
    "roadtrip": "travel", "hiking": "travel", "camping": "travel",
    "vanlife": "travel", "solotravel": "travel", "budgettravel": "travel",
    "luxurytravel": "travel", "adventure": "travel",
    "tech": "tech", "gadgets": "tech", "iphone": "tech", "android": "tech",
    "apple": "tech", "smarthome": "tech", "ai": "tech", "coding": "tech",
    "programming": "tech", "cybersecurity": "tech",
    "gaming": "gaming", "gamer": "gaming", "fortnite": "gaming",
    "minecraft": "gaming", "valorant": "gaming", "callofduty": "gaming",
    "roblox": "gaming", "pokemon": "gaming", "streamer": "gaming",
    "esports": "gaming",
    "finance": "finance", "investing": "finance", "stocks": "finance",
    "crypto": "finance", "personalfinance": "finance", "realestate": "finance",
    "entrepreneur": "business", "sidehustle": "business",
    "passiveincome": "business", "smallbusiness": "business",
    "marketing": "business", "copywriting": "business",
    "productivity": "productivity", "studytok": "education", "student": "education",
    "college": "education", "career": "productivity", "jobsearch": "productivity",
    "tutorial": "education", "howto": "education",
    "art": "art", "drawing": "art", "painting": "art", "photography": "art",
    "booktok": "books", "reading": "books", "writing": "books",
    "diy": "diy", "lifehack": "diy",
    "pets": "pets", "dog": "pets", "cat": "pets", "nature": "lifestyle",
    "motivation": "lifestyle", "mentalhealth": "lifestyle", "selfcare": "lifestyle",
    "asmr": "lifestyle", "satisfying": "lifestyle",
}


def infer_niche(hashtag_counts):
    niche_votes = Counter()
    for tag, n in hashtag_counts.items():
        niche_votes[NICHE_MAP.get(tag.lower(), "other")] += n
    if not niche_votes:
        return "unknown", ""
    ranked = niche_votes.most_common()
    primary = ranked[0][0]
    threshold = ranked[0][1] * 0.2
    secondary = [n for n, c in ranked[1:] if c >= threshold]
    return primary, "|".join(secondary)


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Ensure contact columns exist (forward-compat with older DBs)
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(creators)")}
    for col in ("email", "instagram", "youtube", "twitter", "website"):
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE creators ADD COLUMN {col} TEXT")
            conn.commit()

    rows = conn.execute(
        """
        SELECT c.sec_uid, c.unique_id, c.nickname, c.signature, c.verified,
               c.follower_count, c.following_count, c.heart_count, c.video_count,
               c.region, c.avatar_url,
               c.email, c.instagram, c.youtube, c.twitter, c.website,
               v.play_count, v.digg_count, v.comment_count, v.share_count,
               v.create_time, v.hashtag_source
          FROM creators c
          JOIN videos v ON v.sec_uid = c.sec_uid
         WHERE v.play_count IS NOT NULL
        """
    ).fetchall()

    # Load enriched stats if available and requested
    enriched = {}
    if USE_ENRICHED:
        try:
            enrich_rows = conn.execute(
                """SELECT sec_uid, videos_sampled, median_views, mean_views,
                          min_views, max_views, median_likes, median_comments,
                          median_shares, engagement_rate, posts_per_week
                     FROM enriched_stats WHERE status='ok'"""
            ).fetchall()
            for r in enrich_rows:
                enriched[r["sec_uid"]] = dict(r)
            if enriched:
                print(f"Loaded enriched stats for {len(enriched):,} creators")
        except sqlite3.OperationalError:
            print("No enriched_stats table yet. Run enrich.py to get accurate stats.")

    grouped = {}
    for r in rows:
        g = grouped.setdefault(
            r["sec_uid"], {"meta": r, "videos": [], "hashtags": Counter()}
        )
        g["videos"].append(r)
        if r["hashtag_source"]:
            g["hashtags"][r["hashtag_source"]] += 1

    kept = []
    for sec_uid, data in grouped.items():
        meta = data["meta"]
        vids = data["videos"]

        # Prefer enriched stats if available
        if sec_uid in enriched:
            e = enriched[sec_uid]
            videos_sampled = e["videos_sampled"]
            median_views = e["median_views"]
            mean_views = e["mean_views"]
            min_views = e["min_views"]
            max_views = e["max_views"]
            median_likes = e["median_likes"]
            median_comments = e["median_comments"]
            median_shares = e["median_shares"]
            er = e["engagement_rate"]
            posts_per_week = e["posts_per_week"]
            stats_source = "enriched"
        else:
            if len(vids) < MIN_VIDEOS:
                continue
            plays = [v["play_count"] or 0 for v in vids]
            likes = [v["digg_count"] or 0 for v in vids]
            comments = [v["comment_count"] or 0 for v in vids]
            shares = [v["share_count"] or 0 for v in vids]
            median_views = statistics.median(plays)
            mean_views = statistics.mean(plays)
            min_views = min(plays)
            max_views = max(plays)
            median_likes = statistics.median(likes)
            median_comments = statistics.median(comments)
            median_shares = statistics.median(shares)
            total_views = sum(plays) or 1
            er = (sum(likes) + sum(comments) + sum(shares)) / total_views
            videos_sampled = len(vids)
            posts_per_week = 0  # unknown without enrichment
            stats_source = "hashtag"

        create_times = [v["create_time"] for v in vids if v["create_time"]]

        followers = meta["follower_count"] or 0
        if not (MEDIAN_MIN <= median_views <= MEDIAN_MAX):
            continue
        if not (FOLLOWER_MIN <= followers <= FOLLOWER_MAX):
            continue
        if er < MIN_ER:
            continue

        email = (meta["email"] or "").strip()
        if EMAIL_ONLY and not email:
            continue

        primary_niche, secondary_niches = infer_niche(data["hashtags"])

        if create_times:
            oldest = datetime.fromtimestamp(min(create_times)).date().isoformat()
            newest = datetime.fromtimestamp(max(create_times)).date().isoformat()
        else:
            oldest = newest = ""

        kept.append({
            "handle": meta["unique_id"],
            "profile_url": f"https://tiktok.com/@{meta['unique_id']}",
            "nickname": meta["nickname"],
            "niche": primary_niche,
            "secondary_niches": secondary_niches,
            "region": meta["region"],
            "verified": bool(meta["verified"]),
            "followers": followers,
            "following": meta["following_count"],
            "total_likes": meta["heart_count"],
            "videos_on_account": meta["video_count"],
            "videos_sampled": videos_sampled,
            "stats_source": stats_source,
            "median_views": int(median_views),
            "mean_views": int(mean_views),
            "min_views": int(min_views),
            "max_views": int(max_views),
            "median_likes": int(median_likes),
            "median_comments": int(median_comments),
            "median_shares": int(median_shares),
            "engagement_rate": round(er, 4),
            "views_per_follower": round(median_views / followers, 3) if followers else 0,
            "posts_per_week": round(posts_per_week, 2),
            "email": email,
            "instagram": (meta["instagram"] or "").strip(),
            "youtube": (meta["youtube"] or "").strip(),
            "twitter": (meta["twitter"] or "").strip(),
            "website": (meta["website"] or "").strip(),
            "oldest_video": oldest,
            "newest_video": newest,
            "hashtags_seen_in": "|".join(
                f"{t}:{n}" for t, n in data["hashtags"].most_common(5)
            ),
            "sec_uid": sec_uid,
            "avatar_url": meta["avatar_url"],
            "bio": (meta["signature"] or "").replace("\n", " ").replace("\r", " ")[:500],
        })

    kept.sort(
        key=lambda x: x["engagement_rate"] * (x["median_views"] ** 0.5),
        reverse=True,
    )

    if not kept:
        print("No creators matched filters. Widen MEDIAN_MAX or drop MIN_ER.")
        return

    fields = list(kept[0].keys())
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(kept)

    total_creators = conn.execute("SELECT COUNT(*) FROM creators").fetchone()[0]
    total_videos = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    with_email = sum(1 for c in kept if c["email"])
    with_ig = sum(1 for c in kept if c["instagram"])
    with_yt = sum(1 for c in kept if c["youtube"])
    with_site = sum(1 for c in kept if c["website"])

    print(f"\nDB totals:        {total_creators:,} creators, {total_videos:,} videos")
    print(f"After filtering:  {len(kept):,} creators match")
    print(f"  with email:     {with_email:,}  ({100*with_email/len(kept):.1f}%)")
    print(f"  with Instagram: {with_ig:,}  ({100*with_ig/len(kept):.1f}%)")
    print(f"  with YouTube:   {with_yt:,}")
    print(f"  with website:   {with_site:,}")
    print(f"\nFilters:          median {MEDIAN_MIN:,}-{MEDIAN_MAX:,} views, "
          f"followers {FOLLOWER_MIN:,}-{FOLLOWER_MAX:,}, ER>={MIN_ER*100:.1f}%")
    print(f"Export:           {OUT_CSV}")

    niche_counts = Counter(c["niche"] for c in kept)
    print(f"\nBy niche:")
    for niche, cnt in niche_counts.most_common():
        print(f"  {niche:<18} {cnt:>6,}")

    print(f"\nTop 10 by quality score:")
    for c in kept[:10]:
        email_flag = "📧" if c["email"] else "  "
        print(
            f"  {email_flag} @{c['handle']:<22} "
            f"[{c['niche']:<14}] "
            f"followers={c['followers']:>7,}  "
            f"median_views={c['median_views']:>6,}  "
            f"ER={c['engagement_rate']*100:>4.1f}%"
        )


if __name__ == "__main__":
    main()
