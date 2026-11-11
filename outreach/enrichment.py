"""Stage 2 — Enrichment.

Fetches each candidate's public channel page (the /videos tab) and parses:
channel name, description, subscriber count, recent video titles + view
counts. From those it derives content themes (fitness keyword lexicon),
website/social links written in the description, and a business email —
ONLY when an email address literally appears in the public description
text. Anything not present stays "Not Found" / None ("Unavailable").

Engagement rate = (average views of recent public videos / subscribers) x 100.
"""

import re
import time

import requests

from .http_util import fetch_html, extract_initial_data, walk, parse_count
from .models import Influencer

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL_RE = re.compile(r"(https?://[^\s)]+|www\.[^\s)]+)")
_INSTAGRAM_RE = re.compile(r"instagram\.com/([A-Za-z0-9._]+)", re.I)

# Fitness theme lexicon: theme label -> keywords matched (lowercase substring)
# against recent video titles + the channel description.
THEME_LEXICON = {
    "strength training": ["strength", "dumbbell", "kettlebell", "barbell", "muscle", "resistance band"],
    "weight loss": ["weight loss", "fat loss", "lose weight", "calorie", "fat burn"],
    "yoga": ["yoga"],
    "pilates": ["pilates"],
    "HIIT & cardio": ["hiit", "cardio", "jump rope", "cycling", "spinning"],
    "home workouts": ["home workout", "at home", "no equipment", "bodyweight"],
    "mobility & stretching": ["mobility", "stretch", "flexibility", "posture"],
    "nutrition & meal prep": ["meal prep", "nutrition", "protein", "healthy eating", "diet"],
    "dance fitness": ["dance workout", "zumba", "dance fitness"],
    "low-impact & rehab": ["low impact", "knee", "back pain", "physical therapy", "rehab", "senior", "chair exercise", "postpartum"],
    "walking fitness": ["walking workout", "walk at home", "steps workout"],
    "core training": ["core workout", "abs workout", "ab workout"],
    "calisthenics": ["calisthenics"],
    "running": ["running", "marathon", "5k training"],
}


def extract_email(description: str) -> str:
    """Return the first real email literally present in the text, else 'Not Found'.

    Placeholder addresses (example.com etc.) and file-like matches are rejected
    so a non-address is never reported as a contact.
    """
    if not description:
        return "Not Found"
    for m in EMAIL_RE.finditer(description):
        addr = m.group(0).strip(".,;:)")
        low = addr.lower()
        if any(bad in low for bad in ("example.", "@domain.", ".png", ".jpg", "yourname", "youremail")):
            continue
        return addr
    return "Not Found"


def extract_social_links(description: str):
    links = []
    for m in _URL_RE.finditer(description or ""):
        url = m.group(1).rstrip(".,")
        if "youtube.com" not in url and url not in links:
            links.append(url)
    return links[:5]


def detect_themes(titles, description: str):
    haystack = (" ".join(titles) + " " + (description or "")).lower()
    themes = [label for label, kws in THEME_LEXICON.items()
              if any(kw in haystack for kw in kws)]
    return themes


def _parse_channel_page(html: str):
    """Parse one channel /videos page into raw fields (None when absent)."""
    data = extract_initial_data(html)
    if not data:
        return None
    meta = {}
    for md in walk(data, "channelMetadataRenderer"):
        meta = md
        break

    # Subscriber count lives in the page header as e.g. "45.2K subscribers".
    subscribers = None
    header_blob = str(data.get("header", {}))
    m = re.search(r"([\d.,]+\s*[KMB]?)\s*subscribers", header_blob)
    if m:
        subscribers = parse_count(m.group(1))

    # Recent videos: lockupViewModel entries on the videos tab.
    videos = []
    for lk in walk(data, "lockupViewModel"):
        if lk.get("contentType") not in (None, "LOCKUP_CONTENT_TYPE_VIDEO"):
            continue
        mdv = lk.get("metadata", {}).get("lockupMetadataViewModel", {})
        title = mdv.get("title", {}).get("content", "").strip()
        views = None
        rows = (mdv.get("metadata", {}).get("contentMetadataViewModel", {})
                .get("metadataRows", []))
        for row in rows:
            for part in row.get("metadataParts", []):
                txt = part.get("text", {}).get("content", "")
                label = part.get("accessibilityLabel", "")
                if "view" in label:
                    views = parse_count(label) or parse_count(txt)
        if title:
            videos.append({"title": title, "views": views})
        if len(videos) >= 12:
            break

    return {
        "name": meta.get("title"),
        "description": meta.get("description", "") or "",
        "channel_id": meta.get("externalId"),
        "subscribers": subscribers,
        "videos": videos,
    }


def enrich_candidate(candidate: dict, session: requests.Session) -> Influencer:
    inf = Influencer(
        channel_id=candidate["channel_id"],
        name=candidate.get("name") or "Not Found",
        profile_url=candidate["profile_url"],
        source_url=candidate["profile_url"] + "/videos",
    )
    html = fetch_html(inf.source_url, session)
    parsed = _parse_channel_page(html) if html else None
    if not parsed:
        # Retry once on the channel home page before giving up on this record.
        html = fetch_html(candidate["profile_url"], session)
        parsed = _parse_channel_page(html) if html else None
    if not parsed:
        inf.filter_reason = ""  # filtering stage records the fetch failure
        return inf

    if parsed["name"]:
        inf.name = parsed["name"]
    inf.description = parsed["description"]
    inf.subscribers = parsed["subscribers"]
    inf.recent_videos = parsed["videos"]
    view_counts = [v["views"] for v in parsed["videos"] if v["views"] is not None]
    if view_counts:
        inf.avg_views = sum(view_counts) / len(view_counts)
    # Engagement is only computed from a meaningful sample: at least 3 recent
    # videos with usable view counts. A single viral video is not a rate.
    if len(view_counts) >= 3 and inf.avg_views is not None and inf.subscribers:
        inf.engagement_rate = round(inf.avg_views / inf.subscribers * 100, 2)
    inf.email = extract_email(inf.description)
    inf.social_links = extract_social_links(inf.description)
    titles = [v["title"] for v in parsed["videos"]]
    inf.themes = detect_themes(titles, inf.description)
    return inf


def enrich_all(candidates, verbose: bool = True):
    session = requests.Session()
    records = []
    for i, cand in enumerate(candidates, 1):
        rec = enrich_candidate(cand, session)
        records.append(rec)
        if verbose:
            print(f"[enrichment] {i}/{len(candidates)} {rec.name}: "
                  f"subs={rec.followers_display()} email={rec.email} "
                  f"themes={len(rec.themes)} videos={len(rec.recent_videos)}")
        time.sleep(0.35)
    return records
