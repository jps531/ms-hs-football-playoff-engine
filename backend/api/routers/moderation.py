"""Moderator endpoints for reviewing and acting on user submissions.

All endpoints require the ``X-Moderator-Key`` header to match the
``MODERATOR_API_KEY`` environment variable.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from psycopg import sql

from backend.api.auth import ModeratorAuth
from backend.api.db import get_conn
from backend.api.models.requests import ModerationDecisionRequest
from backend.api.models.responses import SubmissionDetail, SubmissionSummary
from backend.helpers.image_helpers import LogoType, promote_submission_logo

router = APIRouter(prefix="/api/v1/moderation", tags=["moderation"])


def _row_to_summary(row: tuple) -> SubmissionSummary:
    """Map a DB row (id, type, status, school, submitted_at, reviewed_at) to SubmissionSummary."""
    return SubmissionSummary(
        id=row[0],
        type=row[1],
        status=row[2],
        school=row[3],
        submitted_at=row[4],
        reviewed_at=row[5],
    )


def _row_to_detail(row: tuple) -> SubmissionDetail:
    """Map a DB row (id, type, status, school, submitted_at, reviewed_at, payload, moderator_notes) to SubmissionDetail."""
    return SubmissionDetail(
        id=row[0],
        type=row[1],
        status=row[2],
        school=row[3],
        submitted_at=row[4],
        reviewed_at=row[5],
        payload=row[6],
        moderator_notes=row[7],
    )


@router.get("/submissions")
async def list_submissions(
    _: ModeratorAuth,
    type: str | None = None,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[SubmissionSummary]:
    """List submissions, optionally filtered by type and/or status."""
    async with get_conn() as conn:
        rows = await (
            await conn.execute(
                """
                SELECT id, type, status, school, submitted_at, reviewed_at
                FROM submissions
                WHERE (type::text = %s OR %s IS NULL)
                  AND (status::text = %s OR %s IS NULL)
                ORDER BY submitted_at DESC
                LIMIT %s OFFSET %s
                """,
                (type, type, status_filter, status_filter, limit, offset),
            )
        ).fetchall()
    return [_row_to_summary(r) for r in rows]


@router.get("/submissions/{submission_id}", responses={404: {"description": "Not found"}})
async def get_submission(_: ModeratorAuth, submission_id: int) -> SubmissionDetail:
    """Get a single submission with its full payload."""
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                """
                SELECT id, type, status, school, submitted_at, reviewed_at, payload, moderator_notes
                FROM submissions WHERE id = %s
                """,
                (submission_id,),
            )
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Submission {submission_id} not found")
    return _row_to_detail(row)


@router.post(
    "/submissions/{submission_id}/approve",
    responses={404: {"description": "Not found"}, 409: {"description": "Already reviewed"}},
)
async def approve_submission(
    _: ModeratorAuth,
    submission_id: int,
    body: ModerationDecisionRequest = ModerationDecisionRequest(),
) -> SubmissionDetail:
    """Approve a pending submission and auto-apply it to the live database.

    Helmet submissions are marked approved but not auto-applied; the moderator
    creates the helmet design record manually using the submitted information.
    """
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                """
                SELECT id, type, status, school, submitted_at, reviewed_at, payload, moderator_notes
                FROM submissions WHERE id = %s
                """,
                (submission_id,),
            )
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Submission {submission_id} not found")
        if row[2] != "pending":
            raise HTTPException(status_code=409, detail=f"Submission {submission_id} has already been {row[2]}")

        await _apply_submission(conn, row)

        updated = await (
            await conn.execute(
                """
                UPDATE submissions
                   SET status = 'approved', reviewed_at = NOW(), moderator_notes = %s, updated_at = NOW()
                 WHERE id = %s
                RETURNING id, type, status, school, submitted_at, reviewed_at, payload, moderator_notes
                """,
                (body.notes, submission_id),
            )
        ).fetchone()
    assert updated is not None

    return _row_to_detail(updated)


@router.post(
    "/submissions/{submission_id}/reject",
    responses={404: {"description": "Not found"}, 409: {"description": "Already reviewed"}},
)
async def reject_submission(
    _: ModeratorAuth,
    submission_id: int,
    body: ModerationDecisionRequest = ModerationDecisionRequest(),
) -> SubmissionDetail:
    """Reject a pending submission. No changes are applied to the database."""
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                "SELECT id, type, status FROM submissions WHERE id = %s",
                (submission_id,),
            )
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Submission {submission_id} not found")
        if row[2] != "pending":
            raise HTTPException(status_code=409, detail=f"Submission {submission_id} has already been {row[2]}")

        updated = await (
            await conn.execute(
                """
                UPDATE submissions
                   SET status = 'rejected', reviewed_at = NOW(), moderator_notes = %s, updated_at = NOW()
                 WHERE id = %s
                RETURNING id, type, status, school, submitted_at, reviewed_at, payload, moderator_notes
                """,
                (body.notes, submission_id),
            )
        ).fetchone()
    assert updated is not None

    return _row_to_detail(updated)


async def _apply_submission(conn: Any, row: tuple) -> None:
    """Apply an approved submission to the live database.

    Called inside the same connection as the status UPDATE so both succeed or
    fail together.  Cloudinary operations that precede the DB write are
    idempotent (overwrite=True), so partial failures can be safely retried by
    re-approving the submission.
    """
    stype: str = row[1]
    school: str | None = row[3]
    payload: dict = row[6]

    if stype == "logo":
        logo_type: LogoType = payload["logo_type"]
        staging_path: str = payload["cloudinary_path"]
        production_path = promote_submission_logo(staging_path, logo_type)
        col = sql.Identifier(f"logo_{logo_type}")
        await conn.execute(
            sql.SQL("UPDATE schools SET {} = %s WHERE school = %s").format(col),
            (production_path, school),
        )

    elif stype == "helmet":
        pass  # Moderator creates the helmet_design record manually.

    elif stype == "colors":
        primary = payload.get("primary_color")
        secondary_list: list[dict] = payload.get("secondary_colors", [])
        if primary:
            await conn.execute("SELECT set_school_override(%s, %s, %s)", (school, "primary_color", primary["name"]))
            await conn.execute("SELECT set_school_override(%s, %s, %s)", (school, "primary_color_hex", primary["hex"]))
        if secondary_list:
            names_csv = ", ".join(c["name"] for c in secondary_list)
            hex_csv = ", ".join(c["hex"] for c in secondary_list)
            await conn.execute("SELECT set_school_override(%s, %s, %s)", (school, "secondary_color", names_csv))
            await conn.execute("SELECT set_school_override(%s, %s, %s)", (school, "secondary_color_hex", hex_csv))

    elif stype == "location":
        await conn.execute("SELECT set_school_override(%s, %s, %s)", (school, "latitude", str(payload["latitude"])))
        await conn.execute("SELECT set_school_override(%s, %s, %s)", (school, "longitude", str(payload["longitude"])))

    elif stype == "score":
        game_date: str = payload["date"]
        await conn.execute("SELECT set_game_override(%s, %s, %s, %s)", (school, game_date, "points_for", str(payload["points_for"])))
        await conn.execute("SELECT set_game_override(%s, %s, %s, %s)", (school, game_date, "points_against", str(payload["points_against"])))

    elif stype == "feedback":
        pass  # No DB action on approval.
