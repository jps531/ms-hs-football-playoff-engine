"""Moderator endpoints for reviewing and acting on user submissions.

All endpoints require a valid Auth0-issued ``Authorization: Bearer`` token
belonging to a user with the ``moderator`` or ``owner`` role.
"""

import logging

from fastapi import APIRouter, HTTPException

from backend.api.auth import ModeratorAuth
from backend.api.db import get_conn
from backend.api.models.requests import ModerationDecisionRequest
from backend.api.models.responses import SubmissionDetail, SubmissionSummary
from backend.helpers.submission_helpers import apply_submission, build_submission_summary

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/moderation", tags=["moderation"])


def _row_to_detail(row: tuple) -> SubmissionDetail:
    """Map a DB row (id, type, status, school, submitted_at, reviewed_at, payload, moderator_notes,
    helmet_design_id) to SubmissionDetail."""
    return SubmissionDetail(
        id=row[0],
        type=row[1],
        status=row[2],
        school=row[3],
        submitted_at=row[4],
        reviewed_at=row[5],
        payload=row[6],
        moderator_notes=row[7],
        helmet_design_id=row[8],
    )


@router.get("/submissions")
async def list_submissions(
    moderator: ModeratorAuth,
    type: str | None = None,
    status_filter: str | None = None,
    unlinked: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[SubmissionSummary]:
    """List submissions, optionally filtered by type, status, and/or helmet_design_id linkage.

    ``unlinked=true`` restricts to submissions with no linked helmet design (``helmet_design_id
    IS NULL``); ``unlinked=false`` restricts to linked ones. Combined with
    ``type=helmet&status_filter=approved``, this is the moderation UI's "needs mockup" tab.
    """
    async with get_conn() as conn:
        rows = await (
            await conn.execute(
                """
                SELECT id, type, status, school, submitted_at, reviewed_at, helmet_design_id
                FROM submissions
                WHERE (type::text = %s OR %s IS NULL)
                  AND (status::text = %s OR %s IS NULL)
                  AND (%s IS NULL OR (helmet_design_id IS NULL) = %s)
                ORDER BY submitted_at DESC
                LIMIT %s OFFSET %s
                """,
                (type, type, status_filter, status_filter, unlinked, unlinked, limit, offset),
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
                SELECT id, type, status, school, submitted_at, reviewed_at, payload, moderator_notes, helmet_design_id
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
                SELECT id, type, status, school, submitted_at, reviewed_at, payload, moderator_notes, helmet_design_id
                FROM submissions WHERE id = %s
                """,
                (submission_id,),
            )
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Submission {submission_id} not found")
        if row[2] != "pending":
            raise HTTPException(status_code=409, detail=f"Submission {submission_id} has already been {row[2]}")

        await apply_submission(conn, row)

        updated = await (
            await conn.execute(
                """
                UPDATE submissions
                   SET status = 'approved', reviewed_at = NOW(), moderator_notes = %s, updated_at = NOW()
                 WHERE id = %s
                RETURNING id, type, status, school, submitted_at, reviewed_at, payload, moderator_notes, helmet_design_id
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
                RETURNING id, type, status, school, submitted_at, reviewed_at, payload, moderator_notes, helmet_design_id
                """,
                (body.notes, submission_id),
            )
        ).fetchone()
    assert updated is not None
    _log.info("moderation: user %s rejected submission %s type=%s", moderator["db_id"], submission_id, row[1])
    return _row_to_detail(updated)
