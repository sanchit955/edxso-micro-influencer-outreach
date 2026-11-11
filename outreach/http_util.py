"""HTTP + YouTube page-parsing helpers shared by discovery and enrichment.

YouTube public pages embed a JSON blob (`var ytInitialData = {...}`) that
contains everything used here: channel identity on search pages, and channel
metadata, subscriber count and recent videos on channel pages. No API key
and no login are required for these public pages.
"""

import json
import re
import time

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_INITIAL_DATA_RE = re.compile(r"var ytInitialData = (\{.*?\});</script>", re.S)


def fetch_html(url: str, session: requests.Session, retries: int = 2) -> str:
    """GET a public page, returning its HTML text ('' on failure)."""
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                return resp.text
            if resp.status_code in (404, 410):
                return ""
        except requests.RequestException:
            pass
        time.sleep(1.0 * (attempt + 1))
    return ""


def extract_initial_data(html: str):
    """Pull the ytInitialData JSON object out of a YouTube page, or None."""
    m = _INITIAL_DATA_RE.search(html or "")
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def walk(obj, key):
    """Yield every dict value stored under `key` anywhere in nested JSON."""
    if isinstance(obj, dict):
        if key in obj and isinstance(obj[key], dict):
            yield obj[key]
        for v in obj.values():
            yield from walk(v, key)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v, key)


_SUFFIX_MULT = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
_WORD_MULT = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}


def parse_count(text):
    """Parse a YouTube count string ('45.2K', '3.36M', '1,234', '10 thousand
    views') into an int. Returns None when nothing numeric is present.

    YouTube displays abbreviated counts, so the result is the displayed
    precision (e.g. 45.2K -> 45200), which is the real public figure.
    """
    if not text:
        return None
    t = str(text).replace(",", "").strip()
    m = re.search(r"([\d]+(?:\.[\d]+)?)\s*([KMB])\b", t, re.I)
    if m:
        return int(float(m.group(1)) * _SUFFIX_MULT[m.group(2).upper()])
    m = re.search(r"([\d]+(?:\.[\d]+)?)\s*(thousand|million|billion)", t, re.I)
    if m:
        return int(float(m.group(1)) * _WORD_MULT[m.group(2).lower()])
    m = re.search(r"\b([\d]{3,})\b", t)
    if m:
        return int(m.group(1))
    m = re.search(r"\b([\d]+)\b", t)
    if m:
        return int(m.group(1))
    return None
