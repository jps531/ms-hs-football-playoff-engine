"""The daily moderation reminder: every submission still waiting, as a plain-text and HTML email.

Pure functions only. ``backend.prefect.submission_digest_pipeline`` loads the
rows and sends the message. Everything a visitor wrote is escaped in the HTML
version, and only counts go into the subject line.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

CATEGORY_LABELS = {"score": "Score report", "odds": "Odds or scenarios", "other": "Feedback"}
TYPE_LABELS = {
    "score": "Score correction",
    "date": "Date correction",
    "feedback": "Feedback",
    "colors": "Colors",
    "logo": "Logo",
    "helmet": "Helmet",
    "helmet_assignment": "Helmet worn",
    "location": "Location",
}
MESSAGE_PREVIEW = 280
MAX_LISTED = 50  # a long backlog lists this many; the page has the rest


@dataclass(frozen=True)
class DigestItem:
    """One submission still waiting, with the live game for a score correction (None when there's no game row).

    ``is_new`` marks one submitted since the last digest; ``submitted_at`` gives an older one its age.
    """

    id: int
    type: str
    status: str
    school: str | None
    payload: dict[str, Any]
    current_game: dict[str, Any] | None = None
    is_new: bool = True
    submitted_at: datetime | None = None


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
        category = CATEGORY_LABELS.get(item.payload.get("category", "other"), "Feedback")
        return "Feedback" if category == "Feedback" else f"Feedback · {category}"
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
    if item.type == "date":
        game = item.current_game
        opponent = f" vs {game['opponent']}" if game and game.get("opponent") else ""
        line = f"{item.school}{opponent}: reported on {_game_date(p.get('new_date'))}"
        line += f" (site shows {_game_date(game.get('date'))})" if game else " (the game is no longer on the site)"
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


def _waiting_for(item: DigestItem, now: datetime) -> str:
    """How long an older item has been waiting, e.g. 'waiting 3 days'."""
    if item.submitted_at is None:
        return "waiting"
    days = max(1, (now - item.submitted_at).days)
    return f"waiting {_plural(days, 'day')}"


def _breakdown(items: list[DigestItem]) -> str:
    """'3 score corrections, 1 feedback, 1 logo needing an asset'."""
    counts: dict[tuple[str, bool], int] = {}
    for item in items:
        key = (TYPE_LABELS.get(item.type, item.type).lower(), item.status == "accepted_pending_asset")
        counts[key] = counts.get(key, 0) + 1
    parts = []
    for (label, needs_asset), n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        noun = label if n == 1 or label == "feedback" else f"{label}s"
        parts.append(f"{n} {noun}{' needing an asset' if needs_asset else ''}")
    return ", ".join(parts)


def build_digest(
    items: list[DigestItem], site_url: str, now: datetime, hours: int = 24, limit: int = MAX_LISTED
) -> DigestEmail:
    """Render the reminder for every submission still waiting (*items*, newest first).

    Items submitted in the last *hours* are listed first as new; the rest follow as still
    waiting, with their age. At most *limit* are listed; the page has the rest.
    """
    site = site_url.rstrip("/")
    moderate = f"{site}/moderate"
    new = [i for i in items if i.is_new]
    older = [i for i in items if not i.is_new]
    subject = f"MSHSFB Moderation: {len(items)} waiting" + (f", {len(new)} new" if new else "")
    period = "yesterday" if hours == 24 else f"the last {hours} hours"
    head = f"{_plural(len(items), 'submission')} waiting for a decision ({_breakdown(items)})."
    head += f" {len(new)} new since {period}." if new else f" Nothing new since {period}."

    text_lines = [head, f"Review them at {moderate}", ""]
    html_sections = []
    remaining = limit
    for title, group in (("New", new), ("Still waiting", older)):
        shown = group[: max(remaining, 0)]
        remaining -= len(shown)
        if not group:
            continue
        text_lines += [f"{title} ({len(group)})", ""]
        html_items = []
        for item in shown:
            tags = []
            if item.status == "accepted_pending_asset":
                tags.append("needs asset")
            if not item.is_new:
                tags.append(_waiting_for(item, now))
            tag = f" [{', '.join(tags)}]" if tags else ""
            text_lines.append(f"#{item.id} {type_label(item)}{tag}")
            text_lines.append(f"  {summary(item)}")
            text_lines.extend(f"  {line}" for line in extras(item))
            text_lines.append("")
            extra_html = "".join(f'<br><span style="color:#666">{html.escape(line)}</span>' for line in extras(item))
            html_items.append(
                '<li style="margin:0 0 12px">'
                f"<strong>#{item.id} {html.escape(type_label(item))}</strong>"
                f'<span style="color:#666">{html.escape(tag)}</span><br>'
                f"{html.escape(summary(item))}{extra_html}</li>"
            )
        if len(shown) < len(group):
            more = f"…and {len(group) - len(shown)} more on the moderation page."
            text_lines += [more, ""]
            html_items.append(f'<li style="list-style:none;color:#666">{html.escape(more)}</li>')
        html_sections.append(
            f'<h3 style="font-size:15px;margin:20px 0 8px">{html.escape(title)} ({len(group)})</h3>'
            f'<ul style="padding-left:20px;margin:0">{"".join(html_items)}</ul>'
        )

    body_html = (
        '<div style="font:15px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;color:#1a1a1a;max-width:640px">'
        f"<p>{html.escape(head)}</p>"
        f'<p><a href="{html.escape(moderate)}" style="color:#2E6B4F;font-weight:600">Open the moderation page</a></p>'
        f"{''.join(html_sections)}"
        "</div>"
    )
    return DigestEmail(subject=subject, text="\n".join(text_lines).rstrip() + "\n", html=body_html)
