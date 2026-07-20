"""Helpers for the submissions/moderation queue, shared across routers.

Includes row-mapping helpers and the pure "what to override" logic for
applying an approved submission — kept separate from the DB I/O in
``moderation.py`` so each submission type's payload-to-override mapping can
be unit tested without a database connection.
"""

from backend.api.models.responses import SubmissionSummary


def build_submission_summary(row: tuple) -> SubmissionSummary:
    """Map a (id, type, status, school, submitted_at, reviewed_at) row to SubmissionSummary."""
    return SubmissionSummary(
        id=row[0],
        type=row[1],
        status=row[2],
        school=row[3],
        submitted_at=row[4],
        reviewed_at=row[5],
    )


def build_color_overrides(payload: dict) -> list[tuple[str, str]]:
    """Return (field, value) school-override pairs for an approved 'colors' submission.

    Secondary colors are joined into comma-separated name/hex strings, matching
    how ``schools.secondary_color``/``secondary_color_hex`` store multiple colors.
    """
    overrides: list[tuple[str, str]] = []
    primary = payload.get("primary_color")
    if primary:
        overrides.append(("primary_color", primary["name"]))
        overrides.append(("primary_color_hex", primary["hex"]))
    secondary_list: list[dict] = payload.get("secondary_colors", [])
    if secondary_list:
        overrides.append(("secondary_color", ", ".join(c["name"] for c in secondary_list)))
        overrides.append(("secondary_color_hex", ", ".join(c["hex"] for c in secondary_list)))
    return overrides


def build_location_overrides(payload: dict) -> list[tuple[str, str]]:
    """Return (field, value) school-override pairs for an approved 'location' submission."""
    return [
        ("latitude", str(payload["latitude"])),
        ("longitude", str(payload["longitude"])),
    ]


def build_score_overrides(payload: dict) -> tuple[str, list[tuple[str, str]]]:
    """Return (game_date, [(field, value), ...]) game-override pairs for an approved 'score' submission."""
    game_date: str = payload["date"]
    overrides = [
        ("points_for", str(payload["points_for"])),
        ("points_against", str(payload["points_against"])),
    ]
    return game_date, overrides
