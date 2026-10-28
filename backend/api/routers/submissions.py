"""Public endpoints for user-submitted corrections and new assets.

The site's feedback form endpoints (``/feedback`` and ``/scores``) are open to
anonymous callers; with a valid Auth0 Bearer token the submission is linked to
that user's row (user_id). The asset and data endpoints (``/logos``,
``/helmets``, ``/colors``, ``/locations``, ``/helmet-assignments``) need a
signed-in account: they store images on Cloudinary or propose data changes,
nothing on the site calls them anonymously, and an account makes a flood both
attributable and capped (``_MAX_PER_ACCOUNT_PER_DAY`` across them).

Submissions enter a moderation queue and are not applied to the live database
until a moderator approves them via ``/api/v1/moderation/submissions/{id}/approve``.

The two endpoints the site's feedback form uses (``/feedback`` and ``/scores``)
are guarded against floods on top of their per-IP rate limits (nginx also
limits the request rate to ``/api/v1/submissions/``):

- a honeypot field the form hides from people: a filled one is answered as
  if accepted and dropped;
- Cloudflare Turnstile, when configured (see ``backend.api.turnstile``): a
  missing or failed token is refused with 403;
- a repeat of a still-pending submission within a day returns the original
  instead of queueing a copy;
- a circuit breaker: past ``_MAX_PENDING_PER_HOUR`` new pending form
  submissions in an hour, more are refused with 503 until the rate drops,
  so a distributed flood can't fill the queue.
"""

import json
from datetime import UTC, datetime
from functools import partial
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status

from backend.api.auth import CurrentUser, OptionalUser, optional_user_id
from backend.api.db import get_conn
from backend.api.limiter import client_ip, limiter
from backend.api.models.requests import (
    SubmitColorsRequest,
    SubmitFeedbackRequest,
    SubmitHelmetAssignmentRequest,
    SubmitLocationRequest,
    SubmitScoreRequest,
)
from backend.api.models.responses import HelmetAssignmentAlreadyConfirmed, SubmissionCreatedResponse
from backend.api.turnstile import verify_turnstile
from backend.helpers.image_helpers import (
    LogoType,
    check_upload,
    save_and_upload,
    upload_submission_helmet_image,
    upload_submission_logo,
)
from backend.helpers.query_helpers import require_game_exists, require_helmet_design_exists, require_school_exists
from backend.helpers.submission_helpers import (
    build_colors_payload,
    build_feedback_payload,
    build_helmet_assignment_payload,
    build_helmet_image_fields,
    build_helmet_initial_payload,
    build_location_payload,
    build_logo_image_fields,
    build_logo_initial_payload,
    build_score_payload,
    insert_submission,
    update_submission_payload,
)

router = APIRouter(prefix="/api/v1/submissions", tags=["submissions"])

# The signed-in asset and data endpoints.
_ACCOUNT_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Sign in required"},
    404: {"description": "Not found"},
    429: {"description": "Daily limit reached"},
}
_MAX_HELMET_IMAGES = 5
_VALID_IMAGE_LABELS = {"left", "right", "front", "logo", "other"}

# The feedback form's endpoints: a few a minute is plenty for a person
# correcting scores, and a day's cap stops slow drips.
_FORM_LIMIT = "5/minute;30/day"
_MAX_PENDING_PER_HOUR = 300

# Signed-in submissions of assets and data: plenty for someone filling in a
# school's helmets and colors, not enough to fill the Cloudinary account.
_ACCOUNT_TYPES = ("logo", "helmet", "colors", "location", "helmet_assignment")
_MAX_PER_ACCOUNT_PER_DAY = 25


async def _require_under_account_cap(conn, user_id: int) -> None:
    """Raise 429 once *user_id* has made ``_MAX_PER_ACCOUNT_PER_DAY`` asset/data submissions in a day."""
    row = await (
        await conn.execute(
            """
            SELECT COUNT(*) FROM submissions
            WHERE user_id = %s AND type = ANY(%s) AND submitted_at > NOW() - INTERVAL '1 day'
            """,
            (user_id, list(_ACCOUNT_TYPES)),
        )
    ).fetchone()
    if row is not None and row[0] >= _MAX_PER_ACCOUNT_PER_DAY:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"That's the limit of {_MAX_PER_ACCOUNT_PER_DAY} submissions a day. Please try again tomorrow.",
        )


async def _accept_form_submission(
    conn, stype: str, school: str | None, user_id: int | None, payload: dict
) -> tuple[int, datetime]:
    """Queue a feedback-form submission, unless it repeats a pending one or the queue is flooded.

    Returns ``(id, submitted_at)``: the original's for a repeat, a new row's otherwise.
    Raises 503 when more than ``_MAX_PENDING_PER_HOUR`` form submissions arrived in the last hour.
    """
    repeat = await (
        await conn.execute(
            """
            SELECT id, submitted_at FROM submissions
            WHERE type = %s AND status = 'pending' AND school IS NOT DISTINCT FROM %s
              AND payload = %s::jsonb AND submitted_at > NOW() - INTERVAL '1 day'
            ORDER BY submitted_at DESC LIMIT 1
            """,
            (stype, school, json.dumps(payload)),
        )
    ).fetchone()
    if repeat is not None:
        return repeat[0], repeat[1]
    recent = await (
        await conn.execute(
            """
            SELECT COUNT(*) FROM submissions
            WHERE type IN ('feedback', 'score') AND status = 'pending'
              AND submitted_at > NOW() - INTERVAL '1 hour'
            """
        )
    ).fetchone()
    if recent is not None and recent[0] >= _MAX_PENDING_PER_HOUR:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="We’re getting more reports than usual. Please try again in a little while.",
            headers={"Retry-After": "900"},
        )
    return await insert_submission(conn, stype, school, user_id, payload)


def _honeypot_response(stype: str, school: str | None) -> SubmissionCreatedResponse:
    """What an automated submission (honeypot filled) gets back: looks accepted, nothing is stored."""
    return SubmissionCreatedResponse(id=0, type=stype, school=school, submitted_at=datetime.now(UTC))


class _HelmetForm:
    """Helmet submission text fields, grouped via Depends to keep the route signature under the parameter limit."""

    def __init__(
        self,
        school: Annotated[str, Form(max_length=100)],
        year_first_worn: Annotated[int, Form()],
        description: Annotated[str, Form(max_length=2000)],
        year_last_worn: Annotated[int | None, Form()] = None,
        currently_worn: Annotated[bool, Form()] = False,
        color: Annotated[str | None, Form(max_length=100)] = None,
        finish: Annotated[str | None, Form(max_length=100)] = None,
        facemask_color: Annotated[str | None, Form(max_length=100)] = None,
        logo_description: Annotated[str | None, Form(max_length=500)] = None,
        stripe: Annotated[str | None, Form(max_length=200)] = None,
        additional_notes: Annotated[str | None, Form(max_length=2000)] = None,
        other_note: Annotated[str | None, Form(max_length=2000)] = None,
    ) -> None:
        """Bind form fields to instance attributes for FastAPI dependency injection."""
        self.school = school
        self.year_first_worn = year_first_worn
        self.description = description
        self.year_last_worn = year_last_worn
        self.currently_worn = currently_worn
        self.color = color
        self.finish = finish
        self.facemask_color = facemask_color
        self.logo_description = logo_description
        self.stripe = stripe
        self.additional_notes = additional_notes
        self.other_note = other_note


@router.post("/logos", status_code=status.HTTP_201_CREATED, responses=_ACCOUNT_RESPONSES)
@limiter.limit("3/minute")
async def submit_logo(
    request: Request,
    current_user: CurrentUser,
    school: Annotated[str, Form(max_length=100)],
    logo_type: Annotated[LogoType, Form()],
    file: Annotated[UploadFile, File()],
) -> SubmissionCreatedResponse:
    """Submit a school logo for moderator review.

    The image is a reference only — never auto-published. It's uploaded to
    the Cloudinary staging area (``logos/submissions/{logo_type}/{school}_{id}``,
    keyed by this submission's id) and persists there indefinitely as
    evidence; a moderator recreates it to a standard format as a new
    ``team_logos`` asset after accepting the submission.
    """
    user_id = current_user["db_id"]
    async with get_conn() as conn:
        await require_school_exists(conn, school)
        await _require_under_account_cap(conn, user_id)
    # Before anything is stored: a refused file leaves no submission behind.
    await check_upload(file)

    payload = build_logo_initial_payload(logo_type)
    # Insert first so we get the submission_id for Cloudinary path construction.
    async with get_conn() as conn:
        submission_id, submitted_at = await insert_submission(conn, "logo", school, user_id, payload)

    cloudinary_path = await save_and_upload(
        file,
        partial(upload_submission_logo, school_name=school, logo_type=logo_type, submission_id=submission_id),
    )
    payload.update(build_logo_image_fields(cloudinary_path))

    async with get_conn() as conn:
        await update_submission_payload(conn, submission_id, payload)

    return SubmissionCreatedResponse(id=submission_id, type="logo", school=school, submitted_at=submitted_at)


@router.post("/helmets", status_code=status.HTTP_201_CREATED, responses=_ACCOUNT_RESPONSES)
@limiter.limit("3/minute")
async def submit_helmet(
    request: Request,
    current_user: CurrentUser,
    form: Annotated[_HelmetForm, Depends()],
    images: Annotated[list[UploadFile], File()] = [],
    image_labels: Annotated[list[str], Form()] = [],
    logo_image: Annotated[UploadFile | None, File()] = None,
) -> SubmissionCreatedResponse:
    """Submit a helmet design for moderator review.

    Upload up to five reference images (``images``) and an optional logo image
    (``logo_image``).  Images are stored in ``helmets/submissions/`` on
    Cloudinary and used by the moderator to create a helmet mockup — they are
    never promoted to a production path automatically. ``image_labels``, when
    provided, must be the same length as ``images`` and caption each one for
    the moderation gallery (one of ``left``, ``right``, ``front``, ``logo``,
    ``other``).
    """
    if len(images) > _MAX_HELMET_IMAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"At most {_MAX_HELMET_IMAGES} images may be uploaded per submission",
        )
    if image_labels and len(image_labels) != len(images):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="image_labels must be the same length as images when provided",
        )
    for label in image_labels:
        if label not in _VALID_IMAGE_LABELS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Invalid image label '{label}'. Valid: {sorted(_VALID_IMAGE_LABELS)}",
            )

    user_id = current_user["db_id"]
    async with get_conn() as conn:
        await require_school_exists(conn, form.school)
        await _require_under_account_cap(conn, user_id)
    # Every file before anything is stored: one refused file leaves no half-made submission behind.
    for upload in [*images, *([logo_image] if logo_image is not None else [])]:
        await check_upload(upload)

    payload = build_helmet_initial_payload(
        year_first_worn=form.year_first_worn,
        description=form.description,
        year_last_worn=form.year_last_worn,
        currently_worn=form.currently_worn,
        color=form.color,
        finish=form.finish,
        facemask_color=form.facemask_color,
        logo_description=form.logo_description,
        stripe=form.stripe,
        additional_notes=form.additional_notes,
        other_note=form.other_note,
    )

    # Insert first so we get the submission_id for Cloudinary path construction.
    async with get_conn() as conn:
        submission_id, submitted_at = await insert_submission(conn, "helmet", form.school, user_id, payload)

    # Upload images and collect Cloudinary paths.
    image_paths: list[str] = []
    logo_image_path: str | None = None
    for i, img in enumerate(images):
        path = await save_and_upload(
            img, partial(upload_submission_helmet_image, school_name=form.school, submission_id=submission_id, index=i)
        )
        image_paths.append(path)

    if logo_image is not None:
        logo_image_path = await save_and_upload(
            logo_image,
            partial(
                upload_submission_helmet_image, school_name=form.school, submission_id=submission_id, index=len(images)
            ),
        )

    # Update payload with collected paths.
    payload.update(build_helmet_image_fields(image_paths, image_labels, logo_image_path))

    async with get_conn() as conn:
        await update_submission_payload(conn, submission_id, payload)

    return SubmissionCreatedResponse(id=submission_id, type="helmet", school=form.school, submitted_at=submitted_at)


@router.post("/colors", status_code=status.HTTP_201_CREATED, responses=_ACCOUNT_RESPONSES)
@limiter.limit("10/minute")
async def submit_colors(
    request: Request, body: SubmitColorsRequest, current_user: CurrentUser
) -> SubmissionCreatedResponse:
    """Submit a school color correction for moderator review."""
    user_id = current_user["db_id"]
    async with get_conn() as conn:
        await require_school_exists(conn, body.school)
        await _require_under_account_cap(conn, user_id)
        payload = build_colors_payload(body)
        submission_id, submitted_at = await insert_submission(conn, "colors", body.school, user_id, payload)

    return SubmissionCreatedResponse(id=submission_id, type="colors", school=body.school, submitted_at=submitted_at)


@router.post("/locations", status_code=status.HTTP_201_CREATED, responses=_ACCOUNT_RESPONSES)
@limiter.limit("10/minute")
async def submit_location(
    request: Request, body: SubmitLocationRequest, current_user: CurrentUser
) -> SubmissionCreatedResponse:
    """Submit corrected GPS coordinates for a school."""
    user_id = current_user["db_id"]
    async with get_conn() as conn:
        await require_school_exists(conn, body.school)
        await _require_under_account_cap(conn, user_id)
        payload = build_location_payload(body)
        submission_id, submitted_at = await insert_submission(conn, "location", body.school, user_id, payload)

    return SubmissionCreatedResponse(id=submission_id, type="location", school=body.school, submitted_at=submitted_at)


@router.post(
    "/scores",
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"description": "Spam check failed"},
        404: {"description": "School or game not found"},
        503: {"description": "Too many reports right now"},
    },
)
@limiter.limit(_FORM_LIMIT)
async def submit_score(
    request: Request, body: SubmitScoreRequest, current_user: OptionalUser = None
) -> SubmissionCreatedResponse:
    """Submit a corrected game score for moderator review.

    Both the school and the game (school + date) must already exist in the database.
    A repeat of a pending correction returns the original; see the module notes on flood guards.
    """
    if body.website:
        return _honeypot_response("score", body.school)
    await verify_turnstile(body.turnstile_token, client_ip(request))
    async with get_conn() as conn:
        await require_school_exists(conn, body.school)
        await require_game_exists(conn, body.school, body.date)

        user_id = optional_user_id(current_user)
        payload = build_score_payload(body)
        submission_id, submitted_at = await _accept_form_submission(conn, "score", body.school, user_id, payload)

    return SubmissionCreatedResponse(id=submission_id, type="score", school=body.school, submitted_at=submitted_at)


@router.post("/helmet-assignments", status_code=status.HTTP_201_CREATED, responses=_ACCOUNT_RESPONSES)
@limiter.limit("10/minute")
async def submit_helmet_assignment(
    request: Request,
    response: Response,
    body: SubmitHelmetAssignmentRequest,
    current_user: CurrentUser,
) -> SubmissionCreatedResponse | HelmetAssignmentAlreadyConfirmed:
    """Submit or confirm which helmet design a school wore in a specific game.

    404 if the school, the game (school + date), or the design doesn't exist, or if the
    design belongs to a different school. If the game's current ``helmet_design_id``
    already matches, no new submission is queued — the request is acknowledged with
    ``200`` and ``already_confirmed: true`` instead of creating a duplicate queue entry.
    """
    async with get_conn() as conn:
        await require_school_exists(conn, body.school)
        await require_game_exists(conn, body.school, body.date)
        await require_helmet_design_exists(conn, body.helmet_design_id)

        design_school = await (
            await conn.execute("SELECT school FROM helmet_designs WHERE id = %s", (body.helmet_design_id,))
        ).fetchone()
        assert design_school is not None
        if design_school[0] != body.school:
            raise HTTPException(
                status_code=404,
                detail=f"Helmet design {body.helmet_design_id} does not belong to '{body.school}'",
            )

        current = await (
            await conn.execute(
                "SELECT helmet_design_id FROM games WHERE school = %s AND date = %s", (body.school, body.date)
            )
        ).fetchone()
        assert current is not None
        if current[0] == body.helmet_design_id:
            response.status_code = status.HTTP_200_OK
            return HelmetAssignmentAlreadyConfirmed(
                school=body.school, date=body.date, helmet_design_id=body.helmet_design_id
            )

        user_id = current_user["db_id"]
        await _require_under_account_cap(conn, user_id)
        payload = build_helmet_assignment_payload(body)
        submission_id, submitted_at = await insert_submission(conn, "helmet_assignment", body.school, user_id, payload)

    return SubmissionCreatedResponse(
        id=submission_id, type="helmet_assignment", school=body.school, submitted_at=submitted_at
    )


@router.post(
    "/feedback",
    status_code=status.HTTP_201_CREATED,
    responses={403: {"description": "Spam check failed"}, 503: {"description": "Too many reports right now"}},
)
@limiter.limit(_FORM_LIMIT)
async def submit_feedback(
    request: Request, body: SubmitFeedbackRequest, current_user: OptionalUser = None
) -> SubmissionCreatedResponse:
    """Submit feedback for moderator review: a score report, wrong odds or scenarios, or anything else.

    A repeat of a pending report returns the original; see the module notes on flood guards.
    """
    if body.website:
        return _honeypot_response("feedback", None)
    await verify_turnstile(body.turnstile_token, client_ip(request))
    user_id = optional_user_id(current_user)
    payload = build_feedback_payload(body)
    async with get_conn() as conn:
        submission_id, submitted_at = await _accept_form_submission(conn, "feedback", None, user_id, payload)

    return SubmissionCreatedResponse(id=submission_id, type="feedback", school=None, submitted_at=submitted_at)
