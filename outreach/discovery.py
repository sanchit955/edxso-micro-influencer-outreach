"""Stage 1 — Discovery.

Searches YouTube's public search-results pages with niche keywords and
collects the channels behind the results. YouTube search is used because it
is publicly readable without an API key or login; Instagram and TikTok
search/discovery pages are login-walled (see README limitations).

Candidates are deduplicated by channel ID. Search continues across queries
until the candidate target is reached or the query list is exhausted.
"""

import time
import urllib.parse

import requests

from .http_util import fetch_html, extract_initial_data, walk

# Chosen niche: FITNESS. Queries are the discovery seed set; each returns a
# fresh mix of channels, and more queries are added here when a run needs a
# larger pool.
NICHE = "Fitness"
SEARCH_QUERIES = [
    "home workout for beginners",
    "fat loss workout at home",
    "yoga for beginners morning routine",
    "pilates workout at home",
    "dumbbell workout full body",
    "hiit workout no equipment",
    "weight loss tips and workout",
    "healthy meal prep fitness",
    "stretching routine flexibility",
    "mobility exercises daily routine",
    "calisthenics for beginners",
    "postpartum workout recovery",
    "senior fitness gentle exercise",
    "dance workout cardio",
    "walking workout at home",
    "resistance band workout",
    "core workout abs routine",
    "glute workout at home",
    "arm workout with dumbbells",
    "low impact workout knee friendly",
    "back pain relief exercises",
    "posture correction exercises",
    "barre workout at home",
    "kettlebell workout beginners",
    "bodyweight workout routine",
    "chair exercises for seniors",
    "zumba dance fitness workout",
    "indoor cycling workout",
    "jump rope workout",
    "physical therapy exercises at home",
    "wall pilates for beginners",
    "standing abs workout no jumping",
    "apartment friendly quiet workout",
    "tai chi for beginners at home",
    "prenatal workout safe exercises",
    "fitness for women over 40",
    "fitness for women over 50",
    "somatic exercises for beginners",
    "menopause fitness workout",
    "exercises for osteoporosis safety",
    "diabetes friendly exercise routine",
    "small space home gym workout",
    "beginner treadmill walking workout",
    "face yoga exercises routine",
]


def _channels_from_search(html: str):
    """Extract (channel_id, name, handle_url) tuples from a search page."""
    data = extract_initial_data(html)
    if not data:
        return []
    out = []
    for vr in walk(data, "videoRenderer"):
        runs = vr.get("longBylineText", {}).get("runs", [])
        if not runs:
            continue
        ep = runs[0].get("navigationEndpoint", {}).get("browseEndpoint", {})
        channel_id = ep.get("browseId")
        handle = ep.get("canonicalBaseUrl")  # e.g. "/@somehandle"
        name = runs[0].get("text", "").strip()
        if channel_id and name:
            out.append((channel_id, name, handle))
    # Channel-style results (channelRenderer) appear for direct channel hits.
    for cr in walk(data, "channelRenderer"):
        channel_id = cr.get("channelId")
        title = cr.get("title", {}).get("simpleText", "").strip()
        nav = cr.get("navigationEndpoint", {}).get("browseEndpoint", {})
        handle = nav.get("canonicalBaseUrl")
        if channel_id and title:
            out.append((channel_id, title, handle))
    return out


def discover(target_candidates: int = 160, verbose: bool = True):
    """Collect up to `target_candidates` unique candidate channels.

    Returns a list of dicts: channel_id, name, handle, profile_url, source_url
    (the search page the channel was discovered on).
    """
    session = requests.Session()
    candidates = {}

    for query in SEARCH_QUERIES:
        if len(candidates) >= target_candidates:
            break
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
        html = fetch_html(url, session)
        found_before = len(candidates)
        for channel_id, name, handle in _channels_from_search(html):
            if channel_id in candidates:
                continue
            profile_url = (
                "https://www.youtube.com" + handle
                if handle
                else f"https://www.youtube.com/channel/{channel_id}"
            )
            candidates[channel_id] = {
                "channel_id": channel_id,
                "name": name,
                "handle": handle or "",
                "profile_url": profile_url,
                "source_url": url,
                "discovered_via_query": query,
            }
        if verbose:
            print(f"[discovery] '{query}': {len(candidates) - found_before} new "
                  f"(total {len(candidates)})")
        time.sleep(0.4)  # be polite to the source

    return list(candidates.values())
