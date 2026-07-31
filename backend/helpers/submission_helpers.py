"""Helpers for the submissions/moderation queue, shared across routers.

Includes row-mapping helpers and the pure "what to override" logic for
applying an approved submission — kept separate from the DB I/O in
``moderation.py`` so each submission type's payload-to-override mapping can
be unit tested without a database connection. Also includes the mirror-image
"request -> payload dict" builders used by ``submissions.py`` when a
submission is first created, plus the shared insert/update DB calls every
submission type uses.
"""

import json
from typing import Any

from fastapi import HTTPException

from backend.api.models.responses import SubmissionSummary
from backend.helpers.image_helpers import LogoType, promote_submission_logo
from backend.helpers.query_helpers import require_helmet_design_exists, set_school_logo_column


def build_submission_summary(row: tuple) -> SubmissionSummary:
    """Map a (id, type, status, school, submitted_at, reviewed_at, helmet_design_id) row to SubmissionSummary."""
    return SubmissionSummary(
        id=row[0],
        type=row[1],
        status=row[2],
        school=row[3],
        submitted_at=row[4],
        reviewed_at=row[5],
        helmet_design_id=row[6],
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


def build_helmet_assignment_override(payload: dict) -> tuple[str, int]:
    """Return (game_date, helmet_design_id) for an approved 'helmet_assignment' submission."""
    return payload["date"], payload["helmet_design_id"]


async def apply_submission(conn: Any, row: tuple) -> None:
    """Apply an approved submission to the live database.

    Called inside the same connection as the status UPDATE so both succeed or
    fail together. Cloudinary operations that precede the DB write are
    idempotent (overwrite=True), so partial failures can be safely retried by
    re-approving the submission.
    """
    stype: str = row[1]
    school: str | None = row[3]
    payload: dict = row[6]

    if school is None:
        raise HTTPException(status_code=422, detail="Submission is missing a school")

    if stype == "logo":
        logo_type: LogoType = payload["logo_type"]
        staging_path: str = payload["cloudinary_path"]
        production_path = promote_submission_logo(staging_path, logo_type)
        await set_school_logo_column(conn, school, logo_type, production_path)

    elif stype == "helmet":
        pass  # Moderator creates the helmet_design record manually.

    elif stype == "colors":
        for field, value in build_color_overrides(payload):
            await conn.execute("SELECT set_school_override(%s, %s, %s)", (school, field, value))

    elif stype == "location":
        for field, value in build_location_overrides(payload):
            await conn.execute("SELECT set_school_override(%s, %s, %s)", (school, field, value))

    elif stype == "score":
        game_date, overrides = build_score_overrides(payload)
        for field, value in overrides:
            await conn.execute("SELECT set_game_override(%s, %s, %s, %s)", (school, game_date, field, value))

    elif stype == "feedback":
        pass  # No DB action on approval.

    elif stype == "helmet_assignment":
        game_date, helmet_design_id = build_helmet_assignment_override(payload)
        await require_helmet_design_exists(conn, helmet_design_id)
        await conn.execute(
            "UPDATE games SET helmet_design_id = %s WHERE school = %s AND date = %s",
            (helmet_design_id, school, game_date),
        )


def assemble_optional_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Return ``{key: val}`` for each ``(key, val)`` pair where *val* is not ``None``.

    Dedupes the "only include a payload key if the caller actually supplied a
    value" idiom repeated across the submission-payload builders below.
    """
    return {key: val for key, val in pairs if val is not None}


def build_colors_payload(body: Any) -> dict[str, Any]:
    """Build a 'colors' submission payload from a ``SubmitColorsRequest`` body."""
    payload: dict[str, Any] = {}
    if body.primary_color is not None:
        payload["primary_color"] = body.primary_color.model_dump()
    if body.secondary_colors:
        payload["secondary_colors"] = [c.model_dump() for c in body.secondary_colors]
    return payload


def build_location_payload(body: Any) -> dict[str, Any]:
    """Build a 'location' submission payload from a ``SubmitLocationRequest`` body."""
    return {"latitude": body.latitude, "longitude": body.longitude}


def build_score_payload(body: Any) -> dict[str, Any]:
    """Build a 'score' submission payload from a ``SubmitScoreRequest`` body."""
    return {"date": body.date.isoformat(), "points_for": body.points_for, "points_against": body.points_against}


def build_helmet_assignment_payload(body: Any) -> dict[str, Any]:
    """Build a 'helmet_assignment' submission payload from a ``SubmitHelmetAssignmentRequest`` body."""
    return {"date": body.date.isoformat(), "helmet_design_id": body.helmet_design_id}


def build_feedback_payload(body: Any) -> dict[str, Any]:
    """Build a 'feedback' submission payload from a ``SubmitFeedbackRequest`` body."""
    return {"subject": body.subject, "message": body.message}


def build_logo_payload(logo_type: str, cloudinary_path: str) -> dict[str, Any]:
    """Build a 'logo' submission payload from the uploaded logo type and staging path."""
    return {"logo_type": logo_type, "cloudinary_path": cloudinary_path}


def build_helmet_initial_payload(
    year_first_worn: int,
    description: str,
    year_last_worn: int | None = None,
    currently_worn: bool = False,
    color: str | None = None,
    finish: str | None = None,
    facemask_color: str | None = None,
    logo_description: str | None = None,
    stripe: str | None = None,
    additional_notes: str | None = None,
    other_note: str | None = None,
) -> dict[str, Any]:
    """Build a 'helmet' submission's initial payload from form fields, before image upload."""
    payload: dict[str, Any] = {"year_first_worn": year_first_worn, "description": description}
    if year_last_worn is not None:
        payload["year_last_worn"] = year_last_worn
    if currently_worn:
        payload["currently_worn"] = currently_worn
    payload.update(
        assemble_optional_fields(
            [
                ("color", color),
                ("finish", finish),
                ("facemask_color", facemask_color),
                ("logo_description", logo_description),
                ("stripe", stripe),
                ("additional_notes", additional_notes),
                ("other_note", other_note),
            ]
        )
    )
    return payload


def build_helmet_image_fields(
    image_paths: list[str], image_labels: list[str], logo_image_path: str | None
) -> dict[str, Any]:
    """Build the payload fields to merge into a 'helmet' submission after its images are uploaded."""
    fields: dict[str, Any] = {"image_paths": image_paths}
    if image_labels:
        fields["image_labels"] = image_labels
    if logo_image_path is not None:
        fields["logo_image_path"] = logo_image_path
    return fields


async def insert_submission(  # pragma: no cover
    conn, stype: str, school: str | None, user_id: int | None, payload: dict
) -> tuple[int, Any]:
    """Insert a new pending submission row. Returns ``(id, submitted_at)``."""
    row = await (
        await conn.execute(
            "INSERT INTO submissions (type, school, user_id, payload) VALUES (%s, %s, %s, %s) "
            "RETURNING id, submitted_at",
            (stype, school, user_id, json.dumps(payload)),
        )
    ).fetchone()
    assert row is not None
    return row[0], row[1]


async def update_submission_payload(conn, submission_id: int, payload: dict) -> None:  # pragma: no cover
    """Overwrite a submission's payload (used by the helmet flow's second phase, after image upload)."""
    await conn.execute(
        "UPDATE submissions SET payload = %s, updated_at = NOW() WHERE id = %s",
        (json.dumps(payload), submission_id),
    )
