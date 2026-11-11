"""Pipeline orchestration: runs all five stages and writes every output.

Outputs (paths relative to the project root):
  data/dataset.csv          every enriched record + filter status and reason
  data/messages.json/.csv   generated email pitch + DM per passed influencer
  data/dm_queue.csv         DMs queued for manual sending (platform rules)
  data/outreach_tracker.csv Influencer | Email | Message Generated | Sent | Date | Status
  data/outreach_state.sqlite  sending-layer state (duplicate protection)
  output/demo_run.md        human-readable summary of the run
"""

import csv
import json
import os
from datetime import datetime

from . import discovery, enrichment, filtering, personalization, sending

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
OUTPUT_DIR = os.path.join(ROOT, "output")


def _write_csv(path, fieldnames, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_pipeline(target_candidates: int = 160, live: bool = False, verbose: bool = True):
    started = datetime.now()

    candidates = discovery.discover(target_candidates=target_candidates, verbose=verbose)
    records = enrichment.enrich_all(candidates, verbose=verbose)
    records = filtering.filter_all(records)

    passed = [r for r in records if r.status == "Passed"]
    failed = [r for r in records if r.status == "Failed"]
    personalization.personalize_all(passed)

    # --- dataset.csv: every record, with status + reason -------------------
    dataset_fields = ["Name", "Platform", "Followers", "Engagement", "Niche",
                      "Email", "Profile URL", "Content Themes", "Status",
                      "Filter Reason", "Source URL"]
    _write_csv(os.path.join(DATA_DIR, "dataset.csv"), dataset_fields,
               [r.to_dataset_row() for r in records])

    # --- messages for passed influencers ------------------------------------
    message_rows = [{
        "Name": r.name,
        "Platform": r.platform,
        "Email": r.email,
        "Profile URL": r.profile_url,
        "Collaboration Angle": r.collab_angle,
        "Email Subject": r.email_subject,
        "Email Pitch": r.email_pitch,
        "Instagram DM": r.dm_text,
    } for r in passed]
    _write_csv(os.path.join(DATA_DIR, "messages.csv"),
               list(message_rows[0].keys()) if message_rows else
               ["Name", "Platform", "Email", "Profile URL", "Collaboration Angle",
                "Email Subject", "Email Pitch", "Instagram DM"],
               message_rows)
    with open(os.path.join(DATA_DIR, "messages.json"), "w", encoding="utf-8") as f:
        json.dump(message_rows, f, indent=2, ensure_ascii=False)

    # --- DM manual queue (Instagram cannot be automated) ---------------------
    _write_csv(os.path.join(DATA_DIR, "dm_queue.csv"),
               ["Influencer", "Platform", "Profile URL", "DM Text", "Status"],
               [{"Influencer": r.name, "Platform": "Instagram",
                 "Profile URL": r.profile_url, "DM Text": r.dm_text,
                 "Status": "Queued for manual send (Instagram has no sending API)"}
                for r in passed])

    # --- sending layer (simulated unless --live) ------------------------------
    db_path = os.path.join(DATA_DIR, "outreach_state.sqlite")
    new_sends, skipped_dupes, tracker_rows = sending.send_all(
        records, db_path, live=live)
    sending.write_tracker(tracker_rows, os.path.join(DATA_DIR, "outreach_tracker.csv"))

    emails_found = sum(1 for r in records if r.email != "Not Found")
    passed_with_email = sum(1 for r in passed if r.email != "Not Found")

    summary = {
        "discovered_candidates": len(candidates),
        "records_enriched": len(records),
        "passed": len(passed),
        "failed": len(failed),
        "emails_found": emails_found,
        "passed_with_email": passed_with_email,
        "messages_generated": len(passed),
        "new_simulated_sends": new_sends,
        "duplicate_sends_skipped": skipped_dupes,
        "live_mode": live,
    }

    # --- demo run summary ------------------------------------------------------
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    sample = passed[0] if passed else None
    lines = [
        "# Demo Run — Automated Micro-Influencer Outreach System",
        "",
        f"Run at: {started.strftime('%Y-%m-%d %H:%M IST')} · Niche: Fitness · "
        f"Sending mode: {'LIVE SMTP' if live else 'SIMULATED (default)'}",
        "",
        "## Pipeline numbers (real run, real public data)",
        "",
        f"- Candidate channels discovered from YouTube search: **{len(candidates)}**",
        f"- Channel pages fetched and enriched: **{len(records)}**",
        f"- Passed the Fitness filter (5,000–100,000 subs, niche themes, ≥1.0% engagement): **{len(passed)}**",
        f"- Failed the filter (each with a recorded reason in data/dataset.csv): **{len(failed)}**",
        f"- Records with a real business email found in the public description: **{emails_found}**",
        f"- Passed influencers with an email: **{passed_with_email}**",
        f"- Outreach messages generated (email pitch + DM per passed influencer): **{len(passed)}**",
        f"- New simulated sends this run: **{new_sends}** (duplicates skipped: {skipped_dupes})",
        "",
        "Engagement rate formula used everywhere: "
        "average views of the channel's recent public videos ÷ subscribers × 100.",
        "",
    ]
    if sample:
        lines += [
            "## Sample generated message (first passed influencer)",
            "",
            f"**{sample.name}** — {sample.followers_display()} subscribers, "
            f"engagement {sample.engagement_display()}, angle: {sample.collab_angle}",
            "",
            f"Subject: {sample.email_subject}",
            "",
            sample.email_pitch,
            "",
            f"Instagram DM: {sample.dm_text}",
            "",
        ]
    lines += [
        "## Failure breakdown",
        "",
    ]
    from collections import Counter
    reasons = Counter()
    for r in failed:
        key = r.filter_reason.split(":")[0].split("(")[0].strip()
        reasons[key] += 1
    for reason, count in reasons.most_common():
        lines.append(f"- {reason}: {count}")
    lines.append("")
    with open(os.path.join(OUTPUT_DIR, "demo_run.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    if verbose:
        print("\n=== Run summary ===")
        for k, v in summary.items():
            print(f"  {k}: {v}")
    return summary
