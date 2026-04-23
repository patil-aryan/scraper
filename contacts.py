"""
Contact + social handle extraction from TikTok profile data.

TikTok author objects can include:
  - signature         : free-text bio
  - bioLink.link      : single clickable URL below bio
  - ins_id            : linked Instagram handle (when creator connected IG)
  - youtube_channel_id: linked YouTube channel
  - twitter_id        : linked Twitter/X handle

We try structured fields first, then regex the bio for what's missing.
Returns a dict of strings (empty string when not found).
"""
import re
from urllib.parse import urlparse

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Label-style: "IG: @name", "Insta - name", "📷 name"
# Uses word boundary + optional @
IG_LABEL_RE = re.compile(
    r"(?:^|[\s\n|•·⋅\-,])(?:ig|insta|instagram|📷)\s*[:\-]?\s*@?([a-zA-Z0-9_.]{3,30})",
    re.I | re.M,
)
IG_URL_RE = re.compile(r"instagram\.com/([a-zA-Z0-9_.]{2,30})", re.I)

YT_LABEL_RE = re.compile(
    r"(?:^|[\s\n|•·⋅\-,])(?:yt|youtube)\s*[:\-]?\s*@?([a-zA-Z0-9_\-]{3,50})",
    re.I | re.M,
)
YT_URL_RE = re.compile(
    r"youtube\.com/(?:@|c/|channel/|user/)?([a-zA-Z0-9_\-]{2,50})", re.I
)

TW_LABEL_RE = re.compile(
    r"(?:^|[\s\n|•·⋅\-,])(?:twitter|x)\s*[:\-]?\s*@?([a-zA-Z0-9_]{3,15})",
    re.I | re.M,
)
TW_URL_RE = re.compile(r"(?:twitter\.com|x\.com)/([a-zA-Z0-9_]{2,15})", re.I)

# Generic URL finder for fallback 'website' column
URL_RE = re.compile(r"https?://[^\s)>\]]+", re.I)

# Bio tokens we don't want being mistaken for handles
STOPWORDS = {
    "com", "net", "org", "www", "http", "https", "the", "and", "for",
    "email", "business", "contact", "dm", "me", "my", "only", "follow",
    "gmail", "yahoo", "outlook", "hotmail", "icloud", "proton",
    "ample", "example",
}


def _first_match(regexes, text):
    if not text:
        return ""
    for r in regexes:
        m = r.search(text)
        if m:
            handle = m.group(1).strip().strip("._-")
            if handle.lower() not in STOPWORDS and len(handle) >= 2:
                return handle
    return ""


def _extract_email(bio):
    if not bio:
        return ""
    m = EMAIL_RE.search(bio)
    return m.group(0).lower() if m else ""


def _extract_website(bio_link, bio):
    """Website = bioLink.link first, else first non-social URL in bio."""
    if bio_link:
        return bio_link.strip()
    if not bio:
        return ""
    for m in URL_RE.finditer(bio):
        url = m.group(0).rstrip(".,;:")
        host = urlparse(url).hostname or ""
        if any(
            s in host for s in ("instagram.com", "youtube.com", "youtu.be",
                                "twitter.com", "x.com", "tiktok.com")
        ):
            continue
        return url
    return ""


def extract_contacts(author):
    """
    Pull every contact signal from a TikTok author dict.
    Safe against missing keys / weird shapes.
    """
    if not isinstance(author, dict):
        author = {}

    bio = author.get("signature") or ""
    bio_link_raw = author.get("bioLink") or author.get("bio_link") or {}
    if isinstance(bio_link_raw, dict):
        bio_link = bio_link_raw.get("link") or ""
    else:
        bio_link = str(bio_link_raw or "")

    ins_id = (author.get("ins_id") or "").strip()
    yt_id = (author.get("youtube_channel_id") or "").strip()
    tw_id = (author.get("twitter_id") or "").strip()

    # Email first — grab it before we mutate the bio
    email = _extract_email(bio)

    # For handle extraction: strip emails and URLs from bio so we don't
    # mistake "example.com" or "@gmail.com" for a social handle.
    bio_clean = bio
    if bio_clean:
        bio_clean = EMAIL_RE.sub(" ", bio_clean)
        bio_clean = URL_RE.sub(lambda m: " " + m.group(0) + " ", bio_clean)

    # URL-style matches work on the raw bio; label-style matches work on cleaned bio
    if not ins_id:
        ins_id = _first_match([IG_URL_RE], bio) or _first_match([IG_LABEL_RE], bio_clean)
    if not yt_id:
        yt_id = _first_match([YT_URL_RE], bio) or _first_match([YT_LABEL_RE], bio_clean)
    if not tw_id:
        tw_id = _first_match([TW_URL_RE], bio) or _first_match([TW_LABEL_RE], bio_clean)

    return {
        "email": email,
        "instagram": ins_id.lstrip("@"),
        "youtube": yt_id.lstrip("@"),
        "twitter": tw_id.lstrip("@"),
        "website": _extract_website(bio_link, bio),
    }


if __name__ == "__main__":
    # quick sanity tests
    samples = [
        {"signature": "🎨 art & vibes\n📧 hello@example.com\nIG: @myhandle"},
        {"signature": "booking: biz@agency.co | YT: creatorname"},
        {"signature": "just here for fun 🌸", "ins_id": "linked_ig"},
        {"signature": "check out youtube.com/@reallongyoutubechannel"},
        {"signature": "x.com/testuser for updates", "bioLink": {"link": "https://mysite.com"}},
    ]
    for s in samples:
        print(extract_contacts(s))
