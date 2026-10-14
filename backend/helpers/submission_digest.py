"""The daily moderation digest: what was submitted, as a plain-text and HTML email.

Pure functions only. ``backend.prefect.submission_digest_pipeline`` loads the
rows and sends the message. Everything a visitor wrote is escaped in the HTML
version, and only counts go into the subject line.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date
from typing import Any

CATEGORY_LABELS = {"score": "Score report", "odds": "Odds or scenarios", "other": "Feedback"}
TYPE_LABELS = {
    "score": "Score correction",
    "feedback": "Feedback",
    "colors": "Colors",
    "logo": "Logo",
    "helmet": "Helmet",
    "helmet_assignment": "Helmet worn",
    "location": "Location",
}
MESSAGE_PREVIEW = 280


@dataclass(frozen=True)
class DigestItem:
    """One new submission, with the live game for a score correction (None when there's no game row)."""

    id: int
    type: str
    status: str
    school: str | None
    payload: dict[str, Any]
    current_game: dict[str, Any] | None = None


@dataclass(frozen=True)
class DigestEmail:
    """A rendered digest."""

    subject: str
    text: str
    html: str


def _plural(n: int, word: str) -> str:
    """'1 submission', '3 submissions'."""
    return f"{n} {word}{'' if n == 1 else 's'}"


def _clip(text: str, limit: int = MESSAGE_PREVIEW) -> str:
    """Collapse whitespace and cut *text* to *limit* characters with an ellipsis."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _game_date(iso: str | None) -> str:
    """'Fri Oct 10' from an ISO date, or the raw value if it isn't one."""
    try:
        d = date.fromisoformat(iso or "")
    except ValueError:
        return iso or "unknown date"
    return f"{d:%a %b} {d.day}"


def _score(points_for: Any, points_against: Any) -> str:
    """'21–3', or 'no score' when either side is missing."""
    if points_for is None or points_against is None:
        return "no score"
    return f"{points_for}–{points_against}"


def type_label(item: DigestItem) -> str:
    """The submission's kind as a moderator reads it, e.g. 'Feedback · Odds or scenarios'."""
    if item.type == "feedback":
        return f"Feedback · {CATEGORY_LABELS.get(item.payload.get('category', 'other'), 'Feedback')}"
    return TYPE_LABELS.get(item.type, item.type.replace("_", " ").capitalize())


def about(item: DigestItem) -> str:
    """What a feedback report is about: its subject without the category the label already gives.

    The site's form writes subjects like "Odds or scenarios · Region 2-7A · Oxford"; this returns
    "Region 2-7A · Oxford", or "" when the subject is only the category.
    """
    subject = (item.payload.get("subject") or "").strip()
    for label in CATEGORY_LABELS.values():
        if subject == label:
            return ""
        subject = subject.removeprefix(f"{label} · ")
    return subject


def summary(item: DigestItem) -> str:
    """A one-line description of what was submitted."""
    p = item.payload
    if item.type == "score":
        game = item.current_game
        opponent = f" vs {game['opponent']}" if game and game.get("opponent") else ""
        line = f"{item.school}{opponent}, {_game_date(p.get('date'))}: reported {_score(p.get('points_for'), p.get('points_against'))}"
        line += (
            f" (site shows {_score(game.get('points_for'), game.get('points_against'))})"
            if game
            else " (no game on the site that day)"
        )
        return line + (f". Source: {_clip(p['note'], 160)}" if p.get("note") else "")
    if item.type == "feedback":
        return f"{about(item)}: {_clip(p.get('message') or '')}".removeprefix(": ")
    return f"{item.school or 'No school'}"


def extras(item: DigestItem) -> list[str]:
    """Context lines under the summary: the page it came from and a reply address."""
    lines = []
    if item.payload.get("page"):
        lines.append(f"Page: {item.payload['page']}")
    if item.payload.get("email"):
        lines.append(f"Reply to: {item.payload['email']}")
    return lines


def build_digest(
    items: list[DigestItem], pending_counts: dict[str, int], site_url: str, hours: int = 24
) -> DigestEmail:
    """Render the digest for *items* (newest first) and the queue's current pending counts."""
    site = site_url.rstrip("/")
    moderate = f"{site}/moderate"
    pending = sum(pending_counts.values())
    subject = f"Moderation: {_plural(len(items), 'new submission')}, {pending} pending"
    period = "day" if hours == 24 else f"{hours} hours"
    pending_parts = ", ".join(f"{n} {TYPE_LABELS.get(t, t).lower()}" for t, n in sorted(pending_counts.items()) if n)
    head = f"{_plural(len(items), 'new submission')} in the last {period}. {pending} pending in all"
    head += f" ({pending_parts})." if pending_parts else "."

    text_lines = [head, f"Review them at {moderate}", ""]
    html_items = []
    for item in items:
        status = "" if item.status == "pending" else f" [{item.status.replace('_', ' ')}]"
        text_lines.append(f"#{item.id} {type_label(item)}{status}")
        text_lines.append(f"  {summary(item)}")
        text_lines.extend(f"  {line}" for line in extras(item))
        text_lines.append("")
        extra_html = "".join(f'<br><span style="color:#666">{html.escape(line)}</span>' for line in extras(item))
        html_items.append(
            '<li style="margin:0 0 12px">'
            f"<strong>#{item.id} {html.escape(type_label(item))}{html.escape(status)}</strong><br>"
            f"{html.escape(summary(item))}{extra_html}</li>"
        )

    body_html = (
        '<div style="font:15px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;color:#1a1a1a;max-width:640px">'
        f"<p>{html.escape(head)}</p>"
        f'<p><a href="{html.escape(moderate)}" style="color:#2E6B4F;font-weight:600">Open the moderation page</a></p>'
        f'<ul style="padding-left:20px">{"".join(html_items)}</ul>'
        "</div>"
    )
    return DigestEmail(subject=subject, text="\n".join(text_lines).rstrip() + "\n", html=body_html)
