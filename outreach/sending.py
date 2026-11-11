"""Stage 5 — Sending layer.

Default mode is SIMULATION: no real email ever leaves the system unless the
operator explicitly passes --live AND provides SMTP credentials via
environment variables (SMTP_HOST, SMTP_USER, SMTP_PASS, SMTP_FROM). The demo
run uses simulation only.

State lives in a small SQLite database so re-running the pipeline never
sends twice to the same influencer: an influencer (by channel ID) with a
recorded send is skipped on later runs. The human-readable outreach tracker
(CSV) mirrors the database with the required fields:
Influencer | Email | Message Generated | Sent | Date | Status.

Instagram DMs cannot be sent programmatically (platform restrictions), so
they are exported to a manual-send queue instead — see dm_queue handling in
the pipeline module.
"""

import csv
import os
import smtplib
import sqlite3
from datetime import date
from email.message import EmailMessage

TRACKER_FIELDS = ["Influencer", "Email", "Message Generated", "Sent", "Date", "Status"]


def _connect(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS outreach_log (
               channel_id TEXT PRIMARY KEY,
               influencer TEXT,
               email TEXT,
               sent INTEGER,
               date TEXT,
               status TEXT
           )"""
    )
    return conn


def already_sent(conn: sqlite3.Connection, channel_id: str) -> bool:
    row = conn.execute(
        "SELECT sent FROM outreach_log WHERE channel_id = ?", (channel_id,)
    ).fetchone()
    return bool(row and row[0])


def _smtp_send(inf) -> None:
    """Live SMTP send — only reachable with --live and env credentials."""
    msg = EmailMessage()
    msg["From"] = os.environ["SMTP_FROM"]
    msg["To"] = inf.email
    msg["Subject"] = inf.email_subject
    msg.set_content(inf.email_pitch)
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587"))) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)


def send_all(records, db_path: str, live: bool = False):
    """'Send' email pitches to passed records that have a real email address.

    Returns (new_sends, skipped_duplicates, tracker_rows).
    """
    conn = _connect(db_path)
    today = date.today().isoformat()
    new_sends = 0
    skipped = 0

    for inf in records:
        if inf.status != "Passed":
            continue
        message_generated = "Yes" if inf.email_pitch else "No"
        if inf.email == "Not Found":
            status = "Skipped - no public email found (DM queue only)"
            sent = 0
            row_date = ""
        elif already_sent(conn, inf.channel_id):
            skipped += 1
            continue  # keep the original tracker row; never duplicate
        else:
            if live:
                _smtp_send(inf)
                status = "Sent (live SMTP)"
            else:
                status = "Sent (simulated)"
            sent = 1
            row_date = today
            new_sends += 1
        conn.execute(
            "INSERT OR REPLACE INTO outreach_log VALUES (?,?,?,?,?,?)",
            (inf.channel_id, inf.name, inf.email, sent, row_date, status),
        )
    conn.commit()

    rows = [
        {"Influencer": r[0], "Email": r[1], "Message Generated": "Yes",
         "Sent": "Yes" if r[2] else "No", "Date": r[3], "Status": r[4]}
        for r in conn.execute(
            "SELECT influencer, email, sent, date, status FROM outreach_log ORDER BY influencer")
    ]
    conn.close()
    return new_sends, skipped, rows


def write_tracker(rows, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRACKER_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
