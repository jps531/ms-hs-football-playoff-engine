"""Daily moderation digest: email what was submitted in the last day.

Runs each morning (see ``flows.py``). It reads the submissions table directly
and, when anything new came in, emails the digest built by
``backend.helpers.submission_digest`` to ``DIGEST_TO``. A quiet day sends
nothing.

Mail goes out over SMTP, configured by environment variables:

    SMTP_HOST, SMTP_PORT (default 587)   the server
    SMTP_USERNAME, SMTP_PASSWORD         login, when the server needs one
    SMTP_SECURITY                        starttls (default), ssl, or none;
                                         port 465 implies ssl
    SMTP_FROM                            the From address (default SMTP_USERNAME)
    DIGEST_TO                            recipients, comma-separated
    SITE_URL                             for the link to /moderate

Without SMTP_HOST or DIGEST_TO the flow logs the digest and sends nothing.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

from prefect import flow, get_run_logger, task

from backend.helpers.database_helpers import get_database_connection
from backend.helpers.submission_digest import DigestEmail, DigestItem, build_digest

SITE_URL = os.environ.get("SITE_URL", "https://mshsfootball.com")

# New submissions, with the live game a score correction would change (see the moderation queue).
_NEW_SUBMISSIONS_SQL = """
    SELECT s.id, s.type::text, s.status::text, s.school, s.payload,
           g.school IS NOT NULL, g.opponent, g.points_for, g.points_against
    FROM submissions s
    LEFT JOIN games_effective g
      ON s.type = 'score'
     AND g.school = s.school
     AND g.date = CASE WHEN s.type = 'score' THEN (s.payload->>'date')::date END
    WHERE s.submitted_at >= NOW() - make_interval(hours => %s)
    ORDER BY s.submitted_at DESC
"""

_PENDING_COUNTS_SQL = "SELECT type::text, COUNT(*) FROM submissions WHERE status = 'pending' GROUP BY type"


def row_to_item(row: tuple) -> DigestItem:
    """Map a _NEW_SUBMISSIONS_SQL row to a DigestItem."""
    game = {"opponent": row[6], "points_for": row[7], "points_against": row[8]} if row[5] else None
    return DigestItem(id=row[0], type=row[1], status=row[2], school=row[3], payload=row[4] or {}, current_game=game)


@task(task_run_name="Load new submissions")
def load_new_submissions(hours: int) -> tuple[list[DigestItem], dict[str, int]]:
    """Return the submissions from the last *hours* (newest first) and the pending count per type."""
    with get_database_connection() as conn, conn.cursor() as cur:
        cur.execute(_NEW_SUBMISSIONS_SQL, (hours,))
        items = [row_to_item(r) for r in cur.fetchall()]
        cur.execute(_PENDING_COUNTS_SQL)
        counts = {t: n for t, n in cur.fetchall()}
    return items, counts


def smtp_settings() -> dict | None:
    """The SMTP settings from the environment, or None when mail isn't configured."""
    host = os.environ.get("SMTP_HOST", "").strip()
    recipients = [a.strip() for a in os.environ.get("DIGEST_TO", "").split(",") if a.strip()]
    if not host or not recipients:
        return None
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME", "").strip()
    security = os.environ.get("SMTP_SECURITY", "").strip().lower() or ("ssl" if port == 465 else "starttls")
    return {
        "host": host,
        "port": port,
        "username": username,
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "security": security,
        "sender": os.environ.get("SMTP_FROM", "").strip() or username,
        "recipients": recipients,
    }


def build_message(digest: DigestEmail, sender: str, recipients: list[str]) -> EmailMessage:
    """A multipart (text + HTML) message for *digest*."""
    message = EmailMessage()
    message["Subject"] = digest.subject
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(digest.text)
    message.add_alternative(digest.html, subtype="html")
    return message


def send_message(message: EmailMessage, settings: dict) -> None:
    """Send *message* over SMTP with *settings* (see ``smtp_settings``)."""
    context = ssl.create_default_context()
    if settings["security"] == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(settings["host"], settings["port"], context=context, timeout=30)
    else:
        server = smtplib.SMTP(settings["host"], settings["port"], timeout=30)
    with server:
        if settings["security"] == "starttls":
            server.starttls(context=context)
        if settings["username"]:
            server.login(settings["username"], settings["password"])
        server.send_message(message)


@task(task_run_name="Send the digest")
def send_digest(digest: DigestEmail) -> bool:
    """Email *digest*; returns False (and logs it) when SMTP isn't configured."""
    logger = get_run_logger()
    settings = smtp_settings()
    if settings is None:
        logger.warning("SMTP_HOST or DIGEST_TO not set; not sending.\n%s\n\n%s", digest.subject, digest.text)
        return False
    send_message(build_message(digest, settings["sender"], settings["recipients"]), settings)
    logger.info("Sent %r to %d recipient(s)", digest.subject, len(settings["recipients"]))
    return True


@flow(name="Submission Digest Flow")
def submission_digest_flow(hours: int = 24) -> int:
    """Email a digest of the last *hours* of submissions; returns how many were in it (0 sends nothing)."""
    logger = get_run_logger()
    items, counts = load_new_submissions(hours)
    if not items:
        logger.info("No new submissions in the last %d hours; nothing to send.", hours)
        return 0
    send_digest(build_digest(items, counts, SITE_URL, hours))
    return len(items)
