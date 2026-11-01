"""Things a daily update did that someone should look at, gathered into one email.

The steps that log a warning worth acting on (a school's AHSFHS page that couldn't be read, a
score AHSFHS changed under an approved correction, a corrected or finished game no longer on
AHSFHS, share images that failed) also ``note`` it here, and after the commit the update notes
every past game still without a final score (``missing_scores``). Once the daily update has committed,
it ``take``s the notes and, if there are any, emails them grouped by kind
(``daily_update_pipeline``). A clean day sends nothing.

Notes are kept in the process: the daily update's steps run in it, on its threads.
"""

from __future__ import annotations

import threading

# The kinds, in the order the email lists them, each with its heading and what to do about it.
MISSING_SCORES = "missing_scores"
SKIPPED_SCHOOLS = "skipped_schools"
CHANGED_UNDER_CORRECTION = "changed_under_correction"
KEPT_OFF_SCHEDULE = "kept_off_schedule"
SHARE_IMAGES = "share_images"

KINDS = {
    MISSING_SCORES: (
        "Past games without a final score",
        "AHSFHS has no final score for these yet. A region game without one still counts as unplayed in "
        "the standings, odds and scenarios. Report or approve its score once you know it, or remove a "
        "game that didn't happen.",
    ),
    SKIPPED_SCHOOLS: (
        "AHSFHS pages that couldn't be read",
        "These schools' new scores aren't in today's numbers. If it keeps happening, check the pages.",
    ),
    CHANGED_UNDER_CORRECTION: (
        "Scores AHSFHS changed under an approved correction",
        "The correction still shows. If AHSFHS is now right, clear the correction.",
    ),
    KEPT_OFF_SCHEDULE: (
        "Games no longer on AHSFHS, kept",
        "Each is finished or has a correction, so it wasn't removed. Remove it if the game didn't happen.",
    ),
    SHARE_IMAGES: (
        "Share images",
        "Link previews still show the previous numbers. Run the share-assets deployment to redraw them.",
    ),
}

_notes: list[tuple[str, str]] = []
_guard = threading.Lock()


def note(kind: str, text: str) -> None:
    """Record one thing of *kind* (one of ``KINDS``) to put in the daily update's email."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
    with _guard:
        _notes.append((kind, text))


def clear() -> None:
    """Forget every note (the start of a daily update)."""
    with _guard:
        _notes.clear()


def take() -> dict[str, list[str]]:
    """The notes so far by kind, in ``KINDS`` order, and forget them."""
    with _guard:
        notes, _notes[:] = list(_notes), []
    by_kind: dict[str, list[str]] = {}
    for kind in KINDS:
        texts = [t for k, t in notes if k == kind]
        if texts:
            by_kind[kind] = texts
    return by_kind


def render(by_kind: dict[str, list[str]], season: int) -> tuple[str, str]:
    """The email for *by_kind* (from ``take``): (subject, text)."""
    count = sum(len(texts) for texts in by_kind.values())
    subject = f"Daily update done, {count} thing{'s' if count != 1 else ''} to look at"
    parts = [f"The {season} daily update finished and the site shows its numbers. A few things need a look:"]
    for kind, texts in by_kind.items():
        heading, advice = KINDS[kind]
        parts.append(f"{heading} ({len(texts)})\n{advice}\n" + "\n".join(f"- {t}" for t in texts))
    return subject, "\n\n".join(parts) + "\n"
