"""Moderator endpoints for reviewing and acting on user submissions.

All endpoints require a valid Auth0-issued ``Authorization: Bearer`` token
belonging to a user with the ``moderator`` or ``owner`` role.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.api.auth import ModeratorAuth
from backend.api.db import get_conn
from backend.api.models.requests import ModerationDecisionRequest
from backend.api.models.responses import SubmissionDetail, SubmissionSummary
from backend.helpers.image_helpers import LogoType, promote_submission_logo
from backend.helpers.query_helpers import set_school_logo_column
from backend.helpers.submission_helpers import (
    build_color_overrides,
    build_location_overrides,
    build_score_overrides,
    build_submission_summary,
)

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/moderation", tags=["moderation"])


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
    moderator: ModeratorAuth,
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
    return [build_submission_summary(r) for r in rows]


@router.get("/submissions/{submission_id}", responses={404: {"description": "Not found"}})
async def get_submission(moderator: ModeratorAuth, submission_id: int) -> SubmissionDetail:
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
    responses={
        404: {"description": "Not found"},
        409: {"description": "Already reviewed"},
        422: {"description": "Submission is missing a school"},
    },
)
async def approve_submission(
    moderator: ModeratorAuth,
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
    _log.info("moderation: user %s approved submission %s type=%s", moderator["db_id"], submission_id, row[1])
    return _row_to_detail(updated)


@router.post(
    "/submissions/{submission_id}/reject",
    responses={404: {"description": "Not found"}, 409: {"description": "Already reviewed"}},
)
async def reject_submission(
    moderator: ModeratorAuth,
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
    _log.info("moderation: user %s rejected submission %s type=%s", moderator["db_id"], submission_id, row[1])
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
