"""Moderator endpoints for reviewing and acting on user submissions.

All endpoints require a valid Auth0-issued ``Authorization: Bearer`` token
belonging to a user with the ``moderator`` or ``owner`` role.
"""

import logging

from fastapi import APIRouter, HTTPException

from backend.api.auth import ModeratorAuth
from backend.api.db import get_conn
from backend.api.models.requests import ModerationDecisionRequest
from backend.api.models.responses import (
    ColorSubmissionPreview,
    ColorVariantsPreview,
    SubmissionDetail,
    SubmissionSummary,
)
from backend.helpers.color_contrast import compute_color_variants
from backend.helpers.color_variants import split_secondary_hexes
from backend.helpers.submission_helpers import apply_submission, build_submission_summary, resolve_approval_status

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
    ``type=helmet&status_filter=approved``, this is the moderation UI's "needs mockup" tab for
    helmets specifically — ``unlinked`` is helmet_design_id-specific and meaningless combined
    with other types (``helmet_design_id`` is always NULL for non-helmet submissions, so
    ``unlinked=true`` would trivially match every row). The type-agnostic "needs asset" queue
    for every type that uses the accept/asset-creation flow (currently just ``logo``) is simply
    ``status_filter=accepted_pending_asset``, optionally combined with ``type=``.
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


@router.get(
    "/submissions/{submission_id}/color-preview",
    responses={404: {"description": "Not found"}, 422: {"description": "Not a colors submission"}},
)
async def get_color_submission_preview(moderator: ModeratorAuth, submission_id: int) -> ColorSubmissionPreview:
    """Preview a pending 'colors' submission's WCAG variants against the school's current colors.

    Read-only — never writes color_variants. Uses the same compute_color_variants()
    call that approval's recompute_color_variants() will use, so what's previewed
    here is guaranteed to match what gets persisted if the submission is approved.
    """
    async with get_conn() as conn:
        row = await (
            await conn.execute("SELECT type, school, payload FROM submissions WHERE id = %s", (submission_id,))
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Submission {submission_id} not found")
        stype, school, payload = row
        if stype != "colors":
            raise HTTPException(status_code=422, detail=f"Submission {submission_id} is not a 'colors' submission")
        if school is None:
            raise HTTPException(status_code=422, detail=f"Submission {submission_id} is missing a school")

        current_row = await (
            await conn.execute(
                "SELECT primary_color_hex, secondary_color_hex FROM schools_effective WHERE school = %s",
                (school,),
            )
        ).fetchone()

    current_primary_hex, current_secondary_hex = current_row if current_row else (None, None)
    current = compute_color_variants(current_primary_hex, split_secondary_hexes(current_secondary_hex))

    proposed_primary = payload.get("primary_color")
    proposed_secondary = payload.get("secondary_colors", [])
    proposed = compute_color_variants(
        proposed_primary["hex"] if proposed_primary else None,
        [c["hex"] for c in proposed_secondary],
    )

    return ColorSubmissionPreview(
        submission_id=submission_id,
        school=school,
        current=ColorVariantsPreview(primary=current.primary, secondary=current.secondary),
        proposed=ColorVariantsPreview(primary=proposed.primary, secondary=proposed.secondary),
    )


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

    Helmet and logo submissions are marked approved/accepted but not
    auto-applied; the moderator creates the real record manually using the
    submitted information. The status this transitions to is per-type: see
    ``resolve_approval_status`` — logo submissions move to
    ``accepted_pending_asset`` rather than ``approved``, since approving a
    reference doesn't publish an asset.
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

        new_status = resolve_approval_status(row[1])
        updated = await (
            await conn.execute(
                """
                UPDATE submissions
                   SET status = %s, reviewed_at = NOW(), moderator_notes = %s, updated_at = NOW()
                 WHERE id = %s
                RETURNING id, type, status, school, submitted_at, reviewed_at, payload, moderator_notes, helmet_design_id
                """,
                (new_status, body.notes, submission_id),
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
    """Reject a submission that is pending or accepted-pending-asset. No changes are applied
    to the database. A moderator can still reject a logo reference before an asset is made."""
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                "SELECT id, type, status FROM submissions WHERE id = %s",
                (submission_id,),
            )
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Submission {submission_id} not found")
        if row[2] not in ("pending", "accepted_pending_asset"):
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
