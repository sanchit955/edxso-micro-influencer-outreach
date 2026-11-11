"""Stage 4 — Personalization.

Generates a unique email pitch (60–90 words) and Instagram DM (15–30 words)
for every PASSED influencer. Generation is rule-based and dynamic: the text
is assembled from sentence blocks selected by the influencer's own signals —
their top content theme, their most-viewed recent video, their subscriber
count and average views, and a collaboration angle that rotates across the
shortlist (sponsorship, affiliate, UGC, ambassador, product placement,
barter). Openings and closings vary deterministically by channel ID, so no
two messages are the same fixed template.

An optional LLM hook exists (see generate_with_llm_if_available): if an
OPENAI_API_KEY / ANTHROPIC_API_KEY is present in the environment a caller may
route through it, but the pipeline never requires one and the default path
is the rule-based generator below. Word-count bounds are enforced
programmatically on every message.
"""

import hashlib
import os
import re

# Demo brand identity used in the pitch copy. This is configuration, not
# influencer data: an operator replaces it with the real brand before use.
BRAND = "FitGear"
SENDER_NAME = "Alex"
SENDER_ROLE = "Partnerships Team"

ANGLES = [
    ("sponsorship", "a paid sponsorship slot in one of your upcoming videos"),
    ("affiliate partnership", "an affiliate partnership with tracked links and a revenue share on every sale"),
    ("UGC collaboration", "a short UGC collaboration where you create content we repost to our audience"),
    ("brand ambassador role", "a longer-term brand ambassador role across a full training programme cycle"),
    ("product placement", "a natural product placement woven into your regular routines"),
    ("barter collaboration", "a product-for-content barter collaboration to start, with paid work to follow"),
]

_OPENINGS = [
    "Hi {first}, I have been watching {channel} and your {theme} content really stands out.",
    "Hello {first} — your {theme} uploads on {channel} are exactly what our audience looks for.",
    "Hi {first}, your channel {channel} keeps showing up whenever I research quality {theme} creators.",
    "Hello {first}, I came across {channel} this week and your {theme} videos hooked me straight away.",
]

_SIGNAL_LINES = [
    "Your recent video \"{video}\" shows the kind of practical, no-nonsense coaching our customers trust.",
    "I especially liked \"{video}\" — clear instruction, real results, and comments full of people actually trying the routine.",
    "\"{video}\" is a great example of how you turn {theme} into something beginners can follow at home.",
]

_AUDIENCE_LINES = [
    "With about {subs} subscribers and recent videos averaging roughly {avg} views, you reach exactly the committed home-fitness audience we want.",
    "Your {subs} subscribers are loyal — recent uploads averaging around {avg} views is strong, consistent attention for a channel your size.",
    "An audience of {subs} subscribers averaging roughly {avg} views per recent video is precisely the engaged niche we build campaigns around.",
]

_CTAS = [
    "Would you be open to a quick 15-minute call this week to discuss rates, deliverables and timelines?",
    "Can I send over a one-page brief with rates and deliverables for you to look at?",
    "If that sounds interesting, I can share examples of similar creator campaigns we have run.",
]

_FILLERS = [
    "We handle scripting support, product shipping and approvals end to end, so the extra work on your side stays minimal.",
    "Everything is agreed in writing upfront, including usage rights, posting dates and payment terms.",
    "We are onboarding a small group of fitness creators this month, and your channel is high on our list.",
    "Our previous creator partners in fitness have renewed with us for second and third campaigns.",
]

_SIGNOFF = "Thanks for your time,\n{signer}"


def _pick(options, seed_text, salt=""):
    h = int(hashlib.md5((seed_text + salt).encode()).hexdigest(), 16)
    return options[h % len(options)]


# Short DM-friendly label per collaboration angle.
DM_ANGLE_SHORT = {
    "sponsorship": "paid sponsorship",
    "affiliate partnership": "affiliate deal",
    "UGC collaboration": "UGC project",
    "brand ambassador role": "ambassador deal",
    "product placement": "product placement",
    "barter collaboration": "barter collab",
}

# Channel names starting with these words are brands/shows, not people —
# greet them by their full channel name instead of the first token.
_NON_NAME_TOKENS = {
    "the", "move", "pregnancy", "improved", "get", "fit", "feel", "train",
    "belly", "walk", "tone", "dance", "yoga", "pilates", "zumba", "hiit",
}


def _greeting_name(channel_name: str) -> str:
    name = re.sub(r"\s+", " ", (channel_name or "").strip())
    if not name:
        return "there"
    first = re.sub(r"[^A-Za-z]", "", name.split()[0])
    if first.lower() in _NON_NAME_TOKENS or len(name.split()) > 2:
        return name
    return first or name


def _article(phrase: str) -> str:
    return "an" if phrase[0].lower() in "aeiou" else "a"


def _short_title(title: str, max_words: int = 9) -> str:
    clean = re.sub(r"[\[\]()#|]", "", title or "").strip()
    words = clean.split()
    if len(words) > max_words:
        clean = " ".join(words[:max_words]) + "…"
    return clean or "your latest upload"


def _fmt(n) -> str:
    if n is None:
        return "an engaged"
    if n >= 1000:
        return f"{int(round(n)):,}"
    return str(int(n))


def _word_count(text: str) -> int:
    return len(text.split())


def _enforce_bounds(text, minimum, maximum, fillers, seed):
    """Trim long sentences / add fillers until the word count fits the range.

    Trimming runs first, then padding, and the pair repeats — padding after a
    trim is what prevents an over-trimmed message from ending up too short.
    """
    fillers = list(fillers)
    for _ in range(6):
        while _word_count(text) > maximum:
            sentences = re.split(r"(?<=[.!?]) ", text.replace("\n", " "))
            if len(sentences) <= 1:
                break
            removable = sentences[1:]
            longest = max(removable, key=_word_count)
            # Never trim so far that the text drops below the minimum.
            if _word_count(text) - _word_count(longest) < minimum and len(sentences) > 2:
                longest = min(removable, key=_word_count)
            sentences.remove(longest)
            text = " ".join(sentences)
        while _word_count(text) < minimum and fillers:
            addition = fillers.pop(0)
            insert_at = text.rfind("\n")  # keep a sign-off last if present
            if insert_at > 0:
                text = text[:insert_at] + " " + addition + text[insert_at:]
            else:
                text = text + " " + addition
        if minimum <= _word_count(text) <= maximum:
            break
    return text


def generate_messages(inf, angle_index: int):
    """Fill inf.email_subject, inf.email_pitch, inf.dm_text, inf.collab_angle."""
    seed = inf.channel_id or inf.name
    angle_key, angle_phrase = ANGLES[angle_index % len(ANGLES)]
    first = _greeting_name(inf.name)
    theme = inf.themes[0] if inf.themes else "fitness"
    best_video = max(inf.recent_videos, key=lambda v: v["views"] or 0) if inf.recent_videos else {}
    video = _short_title(best_video.get("title", ""))

    opening = _pick(_OPENINGS, seed, "open").format(first=first, channel=inf.name, theme=theme)
    signal = _pick(_SIGNAL_LINES, seed, "sig").format(video=video, theme=theme)
    audience = _pick(_AUDIENCE_LINES, seed, "aud").format(
        subs=_fmt(inf.subscribers), avg=_fmt(inf.avg_views))
    angle_line = (f"I am reaching out from the {SENDER_ROLE} at {BRAND} about {angle_phrase}.")
    cta = _pick(_CTAS, seed, "cta")
    signoff = _SIGNOFF.format(signer=f"{SENDER_NAME}, {SENDER_ROLE}, {BRAND}")

    body = " ".join([opening, signal, audience, angle_line, cta])
    # Body is held to 60-82 words so the complete pitch (body + 8-word
    # sign-off) always lands inside the required 60-90 word range.
    body = _enforce_bounds(body, 60, 82, _FILLERS, seed)
    inf.email_pitch = body + "\n\n" + signoff
    inf.email_subject = f"{inf.name} x {BRAND}: {angle_key} idea for your {theme} audience"
    inf.collab_angle = angle_key

    dm_angle = DM_ANGLE_SHORT[angle_key]
    dm_variants = [
        "Hi {first}! Loved your {theme} video \"{video}\". I work with {brand} — interested in {art} {angle} collab for your {subs} subscribers? Happy to share rates and details here.",
        "Hey {first}, your {theme} content is brilliant — \"{video}\" especially. I am with {brand}; would you be open to {art} {angle} collaboration? I can send rates and a brief right here.",
        "Hi {first}! I help {brand} find creators like you. Your {theme} audience ({subs} subscribers) fits our next campaign perfectly — fancy {art} {angle} collab? Details and rates on request.",
    ]
    dm = _pick(dm_variants, seed, "dm").format(
        first=first, theme=theme, video=_short_title(video, 6), brand=BRAND,
        angle=dm_angle, art=_article(dm_angle), subs=_fmt(inf.subscribers))
    dm = _enforce_bounds(dm, 15, 30,
                         ["No pressure at all either way.", "It is a paid opportunity, by the way."], seed)
    inf.dm_text = dm
    return inf


def personalize_all(passed_records):
    for i, rec in enumerate(passed_records):
        generate_messages(rec, angle_index=i)
    return passed_records


def generate_with_llm_if_available(inf):  # pragma: no cover - optional hook
    """Optional LLM path. Returns None unless an API key is configured, in
    which case a caller could POST the prompt below to the provider. The
    default pipeline does not call this: generation must work fully offline.
    Prompt design (also documented in README):

        System: You write concise, honest influencer outreach. Never invent
        facts about the creator; use only the data provided.
        User: Write a 60-90 word email pitch and a 15-30 word Instagram DM
        for the fitness creator below. Reference their top theme and one
        specific recent video. Collaboration angle: {angle}.
        Data: name={name}; subscribers={subs}; avg_views={avg};
        themes={themes}; recent_videos={titles}.
    """
    if not (os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")):
        return None
    return None  # hook intentionally not wired: rule-based path is the default
