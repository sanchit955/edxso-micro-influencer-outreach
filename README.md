# Automated Micro-Influencer Outreach System

EDXSO AI Engineer Intern — Assignment 1.

An end-to-end pipeline that discovers micro-influencers in a niche on
YouTube, enriches each candidate with real public data, filters them against
explicit criteria (with a recorded reason for every decision), generates a
personalised outreach email and Instagram DM for each shortlisted creator,
and "sends" the emails through a duplicate-safe sending layer that runs in
**simulation mode by default**.

**Chosen niche: Fitness** (implemented completely; the design is niche-
agnostic apart from the query set, theme lexicon and filter constants).

> **Data-integrity rule:** every row in the dataset comes from a real,
> fetched public page. No influencer, email address or metric in this
> project is fabricated or guessed. A field that cannot be obtained from the
> public page is recorded as `Not Found` / `Unavailable`, never invented.

---

## Technology stack

- **Python 3.12** — standard library for CSV/JSON/SQLite/argparse.
- **requests** — the only third-party dependency (HTTP fetching).
- **unittest** — test suite (no pytest dependency).
- **SQLite** (via `sqlite3`) — sending-layer state for duplicate protection.
- No API keys, no logins, no paid services are required to run the demo.

## APIs / tools used

- **YouTube public web pages** (no API key): search-results pages and
  channel pages embed a JSON blob (`ytInitialData`) with channel identity,
  descriptions, subscriber counts and recent-video data. This is parsed
  directly — the official YouTube Data API is *not* required for the demo,
  and the pages used are public and login-free.
- No other external API is used. Instagram/TikTok discovery is intentionally
  **not** scraped (see Limitations).

## Data sources

| Data | Source |
|---|---|
| Candidate channels | `youtube.com/results?search_query=...` public search pages |
| Name, description, channel ID | Channel page `channelMetadataRenderer` |
| Subscriber count | Channel page header (displayed count, e.g. "45.2K subscribers") |
| Recent video titles + view counts | Channel `/videos` tab (`lockupViewModel` entries) |
| Business email | The channel's own public description text only |
| Website/social links | URLs written in the public description |

Every record stores its **source URL** (see `data/dataset.csv`).

## Discovery methodology

1. A seed set of ~30 Fitness search queries (home workouts, yoga, pilates,
   HIIT, meal prep, mobility, calisthenics, senior fitness, …) is run
   against YouTube search.
2. Channels behind the results are collected from each result's channel
   endpoint and **deduplicated by channel ID**.
3. Queries continue until the candidate target (default 160) is reached or
   the query list is exhausted. Search results skew towards large channels,
   so a large candidate pool is collected on purpose — the filter, not the
   search ranking, decides who is a micro-influencer.

## Enrichment process

For every candidate, the channel's `/videos` page is fetched and parsed for:

- channel name and description,
- subscriber count (YouTube displays abbreviated counts — 45.2K is stored as
  45,200, the real publicly displayed figure),
- the 12 most recent public videos with their view counts,
- **content themes**: a Fitness keyword lexicon (strength, yoga, HIIT,
  weight loss, meal prep, mobility, dance fitness, low-impact/rehab, …)
  matched against video titles + description,
- **website/social links** literally present in the description,
- **business email**: extracted with a regex *only* when an email address
  literally appears in the public description text (placeholder addresses
  such as `name@example.com` are rejected). Otherwise the field is
  `Not Found`. Emails hidden behind YouTube's "view email address" captcha
  are **not** attempted — that is why many large channels show `Not Found`.

**Engagement rate** is computed, never assumed:

```
engagement % = (average views of recent public videos / subscribers) × 100
```

The rate is only computed from a meaningful sample — at least 3 recent
videos with usable view counts; a single viral video is not a rate. If view
counts or subscribers are unavailable, engagement is `Unavailable`.

## Filtering logic (Fitness — implemented in full)

A record **passes** only if *all* criteria hold; every record, pass or fail,
gets a human-readable reason in `data/dataset.csv`:

1. Subscriber count is publicly displayed (else the band cannot be verified).
2. **5,000 ≤ subscribers ≤ 100,000** (the micro-influencer band).
3. At least one Fitness content theme is detected (niche relevance).
4. Engagement rate is computable and **≥ 1.0%**.

## Personalization logic

For each passed influencer the system generates:

- an **email pitch of 60–90 words**, and
- an **Instagram DM of 15–30 words**,

assembled dynamically from sentence blocks chosen by that influencer's own
signals: their top content theme, their most-viewed recent video (referenced
by title), their subscriber count and average views, and a collaboration
angle that rotates across the shortlist — sponsorship, affiliate
partnership, UGC, brand ambassador, product placement, barter. Openings,
signal lines and calls-to-action have several variants selected
deterministically from the channel ID, so messages differ in structure, not
just in substituted names. Word-count bounds are enforced programmatically
on every message and asserted in the test suite.

### AI model / prompt design

Message generation in this submission is **rule-based dynamic generation —
no LLM is required and none is used in the demo run**. An optional LLM hook
(`personalization.generate_with_llm_if_available`) exists: if
`OPENAI_API_KEY` or `ANTHROPIC_API_KEY` is present in the environment, a
caller may route generation through that provider using this prompt design,
with the rule-based output as fallback:

- **System:** "You write concise, honest influencer outreach. Never invent
  facts about the creator; use only the data provided."
- **User:** "Write a 60–90 word email pitch and a 15–30 word Instagram DM
  for the fitness creator below. Reference their top theme and one specific
  recent video. Collaboration angle: {angle}. Data: name={name};
  subscribers={subs}; avg_views={avg}; themes={themes};
  recent_videos={titles}."

The brand name/sender in the copy (`FitGear`, Partnerships Team) are
configuration placeholders in `personalization.py`, to be replaced by the
operating brand — they are not influencer data.

## Sending mechanism

- Default mode is **simulated sending**: messages are recorded as
  `Sent (simulated)` in the outreach tracker; nothing leaves the machine.
- Eligible recipients: passed influencers with a real email found. Passed
  influencers without a public email are marked
  `Skipped - no public email found (DM queue only)`.
- **Duplicate protection:** a SQLite log keyed by channel ID records every
  send; re-running the pipeline sends **0** new messages to anyone already
  contacted (covered by a unit test).
- A `--live` SMTP mode exists (`SMTP_HOST/USER/PASS/FROM` env vars) but is
  off by default and was **not** used for this demo.
- **Instagram DMs are never auto-sent** — Instagram offers no sending API
  for this and automated DM tools violate platform terms. DMs are exported
  to `data/dm_queue.csv` as a manual-send queue.

## Outputs

| File | Contents |
|---|---|
| `data/dataset.csv` | Every enriched record: Name, Platform, Followers, Engagement, Niche, Email, Profile URL, Content Themes, Status, Filter Reason, Source URL |
| `data/messages.csv` / `data/messages.json` | Email pitch + DM per passed influencer |
| `data/outreach_tracker.csv` | Influencer, Email, Message Generated, Sent, Date, Status |
| `data/dm_queue.csv` | DMs queued for manual sending |
| `output/demo_run.md` | Summary of the real demo run (counts + a sample message) |

## Setup instructions

```bash
pip install -r requirements.txt
python -m outreach run            # full pipeline, simulated sending
python -m outreach run --candidates 60   # smaller/faster run
python -m unittest discover -s tests -v  # test suite
```

## Limitations (stated honestly)

- **Instagram and TikTok cannot be discovered this way**: their search and
  profile data sit behind login walls, so this system discovers on YouTube
  and treats Instagram only as a (manual) DM channel. Any tool claiming
  login-free Instagram scraping at scale is either using unofficial
  endpoints that break constantly or fabricating data.
- **Subscriber and view counts are YouTube's displayed (abbreviated)
  figures** — 45.2K, not an exact count. Band decisions use those public
  figures.
- **Many creators hide their email** behind YouTube's captcha-gated "view
  email" button, which this system does not attempt to bypass; those records
  honestly show `Not Found` and are reachable only via the DM queue.
- Engagement is a views-based proxy (views are not unique viewers), which is
  the standard public-data approximation.
- Search-result composition is controlled by YouTube; the candidate pool
  skews large, so pass rates are modest by design — the filter is strict.
- Pages are fetched politely and sequentially; a full run takes minutes,
  not seconds (see scaling notes for the production design).

## How this scales from 50 to 500+ influencers

1. **Discovery:** add query permutations (sub-niches × formats × languages)
   and channel-page "related channels" expansion; dedupe stays O(1) by
   channel ID. 500 candidates ≈ 60–80 queries.
2. **Fetching:** the fetch/parse step is stateless per channel — parallelise
   with a small worker pool (5–10 concurrent, with backoff and a shared
   rate limiter), or switch to the **YouTube Data API v3** (channels.list
   batches 50 channels per request; ~10 requests cover 500 channels inside
   the free daily quota) behind the same enrichment interface.
3. **Storage:** dataset/tracker CSVs become tables in the existing SQLite
   database (schema already keyed by channel ID), then Postgres when
   multiple operators run campaigns concurrently.
4. **Sending:** the sending layer already separates eligibility, message
   retrieval and send-state; a production deployment swaps the simulator for
   a queued SMTP/ESP sender with per-day caps, bounce handling and the same
   duplicate-protection log.
5. **Personalization:** the rule-based generator is O(1) per influencer; the
   optional LLM hook can be enabled per campaign with the same word-count
   and no-fabrication checks applied to its output.
