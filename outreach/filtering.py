"""Stage 3 — Filtering / classification (Fitness niche, implemented in full).

A record PASSES only when all of these hold:
  1. Subscriber count is available on the public channel page.
  2. Subscribers are inside the micro-influencer band: 5,000–100,000.
  3. Fitness relevance: at least one fitness content theme is detected in the
     channel's recent video titles / description.
  4. Engagement rate (avg recent views / subscribers) is computable and at
     or above the minimum threshold of 1.0%.

Every record — pass or fail — gets a human-readable reason naming the exact
criterion and the actual value observed. Nothing is silently dropped.
"""

MIN_SUBSCRIBERS = 5_000
MAX_SUBSCRIBERS = 100_000
MIN_ENGAGEMENT_PCT = 1.0


def _fmt(n) -> str:
    return f"{n:,}" if isinstance(n, int) else str(n)


def classify(inf) -> None:
    """Set inf.status and inf.filter_reason in place."""
    if not inf.recent_videos and not inf.description and inf.subscribers is None:
        inf.status = "Failed"
        inf.filter_reason = ("Channel page could not be fetched/parsed, so no "
                             "public data could be verified for this record.")
        return

    if inf.subscribers is None:
        inf.status = "Failed"
        inf.filter_reason = ("Subscriber count is not displayed on the public "
                             "channel page, so the micro-influencer band cannot "
                             "be verified.")
        return

    if inf.subscribers < MIN_SUBSCRIBERS:
        inf.status = "Failed"
        inf.filter_reason = (f"Below the micro-influencer band: {_fmt(inf.subscribers)} "
                             f"subscribers is under the {MIN_SUBSCRIBERS:,} minimum.")
        return

    if inf.subscribers > MAX_SUBSCRIBERS:
        inf.status = "Failed"
        inf.filter_reason = (f"Above the micro-influencer band: {_fmt(inf.subscribers)} "
                             f"subscribers exceeds the {MAX_SUBSCRIBERS:,} maximum.")
        return

    if not inf.themes:
        inf.status = "Failed"
        inf.filter_reason = ("No fitness content themes detected in recent video "
                             "titles or channel description, so niche relevance "
                             "for Fitness is not established.")
        return

    if inf.engagement_rate is None:
        inf.status = "Failed"
        inf.filter_reason = ("Engagement rate unavailable: fewer than three recent "
                             "public videos with usable view counts, so no reliable "
                             "rate can be computed.")
        return

    if inf.engagement_rate < MIN_ENGAGEMENT_PCT:
        inf.status = "Failed"
        inf.filter_reason = (f"Engagement below threshold: {inf.engagement_rate:.2f}% "
                             f"(avg recent views / subscribers) is under the "
                             f"{MIN_ENGAGEMENT_PCT:.1f}% minimum.")
        return

    inf.status = "Passed"
    inf.filter_reason = (
        f"Passed: {_fmt(inf.subscribers)} subscribers inside the 5,000–100,000 "
        f"micro band; fitness themes detected ({'; '.join(inf.themes[:3])}); "
        f"engagement {inf.engagement_rate:.2f}% meets the {MIN_ENGAGEMENT_PCT:.1f}% minimum."
    )


def filter_all(records):
    for rec in records:
        classify(rec)
    return records
