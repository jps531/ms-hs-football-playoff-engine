"""Daily moderation reminder: email what is still waiting for a decision.

Runs each morning (see ``flows.py``). While anything is waiting for a decision
(pending, or a logo accepted but still needing its asset) it emails
``DIGEST_TO`` a reminder built by ``backend.helpers.submission_digest``: what
came in over the last day first, then everything older that's still open.
When nothing is waiting it sends nothing.

Mail goes out over SMTP, configured by environment variables:

    SMTP_HOST, SMTP_PORT (default 587)   the server
    SMTP_USERNAME, SMTP_PASSWORD         login, when the server needs one
    SMTP_SECURITY                        starttls (default), ssl, or none;
                                         port 465 implies ssl; none (the
                                         password and digest in the clear) is
                                         refused unless ENVIRONMENT=local
    SMTP_FROM                            the From address (default SMTP_USERNAME)
    DIGEST_TO                            recipients, comma-separated
    SITE_URL                             for the link to /moderate

Without SMTP_HOST or DIGEST_TO the flow logs the digest and sends nothing.

Each run also forgets the contact email on feedback that was decided more
than ``EMAIL_RETENTION_DAYS`` ago: it was only ever there for a reply.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage

from prefect import flow, get_run_logger, task

from backend.helpers.database_helpers import get_database_connection
from backend.helpers.submission_digest import DigestEmail, DigestItem, build_digest

SITE_URL = os.environ.get("SITE_URL", "https://mshsfootball.com")

# Statuses that still need a moderator: undecided, or a logo accepted but awaiting its asset.
UNRESOLVED = ("pending", "accepted_pending_asset")

# Every submission still waiting, newest first, flagged new if it came in during the last
# %s hours, with the live game a score or date report would change (see the moderation queue).
_WAITING_SQL = """
    SELECT s.id, s.type::text, s.status::text, s.school, s.payload,
           g.school IS NOT NULL, g.opponent, g.points_for, g.points_against,
           s.submitted_at >= NOW() - make_interval(hours => %s), s.submitted_at, g.date, NOW()
    FROM submissions s
    LEFT JOIN games_effective g
      ON s.type IN ('score', 'date')
     AND g.school = s.school
     AND CASE WHEN s.type NOT IN ('score', 'date') THEN FALSE
              WHEN s.payload ? 'game_id' THEN g.game_id = (s.payload->>'game_id')::bigint
              ELSE g.date = (s.payload->>'date')::date END
    WHERE s.status::text IN %s
    ORDER BY s.submitted_at DESC
"""


def row_to_item(row: tuple) -> DigestItem:
    """Map a _WAITING_SQL row (without its trailing NOW()) to a DigestItem."""
    game = (
        {"opponent": row[6], "points_for": row[7], "points_against": row[8], "date": row[11].isoformat()}
        if row[5]
        else None
    )
    return DigestItem(
        id=row[0],
        type=row[1],
        status=row[2],
        school=row[3],
        payload=row[4] or {},
        current_game=game,
        is_new=bool(row[9]),
        submitted_at=row[10],
    )


@task(task_run_name="Load waiting submissions")
def load_waiting_submissions(hours: int) -> tuple[list[DigestItem], datetime]:
    """Return every submission still waiting (newest first), and the database's current time."""
    with get_database_connection() as conn, conn.cursor() as cur:
        cur.execute(_WAITING_SQL, (hours, UNRESOLVED))
        rows = cur.fetchall()
        if not rows:
            cur.execute("SELECT NOW()")
            return [], cur.fetchone()[0]
    return [row_to_item(r) for r in rows], rows[0][12]


def smtp_settings() -> dict | None:
    """The SMTP settings from the environment, or None when mail isn't configured."""
    host = os.environ.get("SMTP_HOST", "").strip()
    recipients = [a.strip() for a in os.environ.get("DIGEST_TO", "").split(",") if a.strip()]
    if not host or not recipients:
        return None
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME", "").strip()
    security = os.environ.get("SMTP_SECURITY", "").strip().lower() or ("ssl" if port == 465 else "starttls")
    if security not in ("starttls", "ssl", "none"):
        raise ValueError(f"SMTP_SECURITY must be starttls, ssl, or none, not {security!r}")
    if security == "none" and os.environ.get("ENVIRONMENT", "local") != "local":
        raise ValueError("SMTP_SECURITY=none sends the SMTP password and the digest unencrypted; use starttls or ssl")
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


EMAIL_RETENTION_DAYS = 90


@task(task_run_name="Forget old contact emails")
def forget_old_contact_emails(days: int = EMAIL_RETENTION_DAYS) -> int:
    """Remove ``payload.email`` from submissions approved or rejected more than *days* ago; returns how many."""
    with get_database_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE submissions SET payload = payload - 'email', updated_at = NOW()
            WHERE payload ? 'email' AND status IN ('approved', 'rejected')
              AND COALESCE(reviewed_at, submitted_at) < NOW() - make_interval(days => %s)
            """,
            (days,),
        )
        forgotten = cur.rowcount
    get_run_logger().info("Forgot the contact email on %d submission(s) decided over %d days ago", forgotten, days)
    return forgotten


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
    """Email a reminder of every submission still waiting, marking what came in over the last *hours*.

    Returns how many were waiting; 0 means nothing was sent.
    """
    logger = get_run_logger()
    forget_old_contact_emails()
    items, now = load_waiting_submissions(hours)
    if not items:
        logger.info("Nothing is waiting for a decision; nothing to send.")
        return 0
    send_digest(build_digest(items, SITE_URL, now, hours))
    return len(items)
