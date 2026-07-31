"""Public endpoints for user-submitted corrections and new assets.

All endpoints are open to anonymous callers.  If the request includes a valid
Auth0 Bearer token the submission is linked to that user's row (user_id), which
enables future features like auto-approval for trusted contributors.  Submissions
without a token are accepted normally with user_id=NULL.

Submissions enter a moderation queue and are not applied to the live database
until a moderator approves them via ``/api/v1/moderation/submissions/{id}/approve``.
"""

from functools import partial
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status

from backend.api.auth import OptionalUser, optional_user_id
from backend.api.db import get_conn
from backend.api.limiter import limiter
from backend.api.models.requests import (
    SubmitColorsRequest,
    SubmitFeedbackRequest,
    SubmitHelmetAssignmentRequest,
    SubmitLocationRequest,
    SubmitScoreRequest,
)
from backend.api.models.responses import HelmetAssignmentAlreadyConfirmed, SubmissionCreatedResponse
from backend.helpers.image_helpers import (
    LogoType,
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
    build_logo_payload,
    build_score_payload,
    insert_submission,
    update_submission_payload,
)

router = APIRouter(prefix="/api/v1/submissions", tags=["submissions"])

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}
_MAX_HELMET_IMAGES = 5
_VALID_IMAGE_LABELS = {"left", "right", "front", "logo", "other"}


class _HelmetForm:
    """Helmet submission text fields, grouped via Depends to keep the route signature under the parameter limit."""

    def __init__(
        self,
        school: Annotated[str, Form()],
        year_first_worn: Annotated[int, Form()],
        description: Annotated[str, Form()],
        year_last_worn: Annotated[int | None, Form()] = None,
        currently_worn: Annotated[bool, Form()] = False,
        color: Annotated[str | None, Form()] = None,
        finish: Annotated[str | None, Form()] = None,
        facemask_color: Annotated[str | None, Form()] = None,
        logo_description: Annotated[str | None, Form()] = None,
        stripe: Annotated[str | None, Form()] = None,
        additional_notes: Annotated[str | None, Form()] = None,
        other_note: Annotated[str | None, Form()] = None,
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


@router.post("/logos", status_code=status.HTTP_201_CREATED, responses=_404)
@limiter.limit("3/minute")
async def submit_logo(
    request: Request,
    school: Annotated[str, Form()],
    logo_type: Annotated[LogoType, Form()],
    file: Annotated[UploadFile, File()],
    current_user: OptionalUser = None,
) -> SubmissionCreatedResponse:
    """Submit a school logo for moderator review.

    The image is uploaded to the Cloudinary staging area
    (``logos/submissions/{logo_type}/{school}``) and will be moved to the
    production folder upon moderator approval.
    """
    async with get_conn() as conn:
        await require_school_exists(conn, school)

    cloudinary_path = await save_and_upload(
        file, partial(upload_submission_logo, school_name=school, logo_type=logo_type)
    )

    user_id = optional_user_id(current_user)
    payload = build_logo_payload(logo_type, cloudinary_path)
    async with get_conn() as conn:
        submission_id, submitted_at = await insert_submission(conn, "logo", school, user_id, payload)

    return SubmissionCreatedResponse(id=submission_id, type="logo", school=school, submitted_at=submitted_at)


@router.post("/helmets", status_code=status.HTTP_201_CREATED, responses=_404)
@limiter.limit("3/minute")
async def submit_helmet(
    request: Request,
    form: Annotated[_HelmetForm, Depends()],
    images: Annotated[list[UploadFile], File()] = [],
    image_labels: Annotated[list[str], Form()] = [],
    logo_image: Annotated[UploadFile | None, File()] = None,
    current_user: OptionalUser = None,
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

    async with get_conn() as conn:
        await require_school_exists(conn, form.school)

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

    user_id = optional_user_id(current_user)
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


@router.post("/colors", status_code=status.HTTP_201_CREATED, responses=_404)
@limiter.limit("10/minute")
async def submit_colors(
    request: Request, body: SubmitColorsRequest, current_user: OptionalUser = None
) -> SubmissionCreatedResponse:
    """Submit a school color correction for moderator review."""
    user_id = optional_user_id(current_user)
    async with get_conn() as conn:
        await require_school_exists(conn, body.school)
        payload = build_colors_payload(body)
        submission_id, submitted_at = await insert_submission(conn, "colors", body.school, user_id, payload)

    return SubmissionCreatedResponse(id=submission_id, type="colors", school=body.school, submitted_at=submitted_at)


@router.post("/locations", status_code=status.HTTP_201_CREATED, responses=_404)
@limiter.limit("10/minute")
async def submit_location(
    request: Request, body: SubmitLocationRequest, current_user: OptionalUser = None
) -> SubmissionCreatedResponse:
    """Submit corrected GPS coordinates for a school."""
    user_id = optional_user_id(current_user)
    async with get_conn() as conn:
        await require_school_exists(conn, body.school)
        payload = build_location_payload(body)
        submission_id, submitted_at = await insert_submission(conn, "location", body.school, user_id, payload)

    return SubmissionCreatedResponse(id=submission_id, type="location", school=body.school, submitted_at=submitted_at)


@router.post(
    "/scores", status_code=status.HTTP_201_CREATED, responses={404: {"description": "School or game not found"}}
)
@limiter.limit("10/minute")
async def submit_score(
    request: Request, body: SubmitScoreRequest, current_user: OptionalUser = None
) -> SubmissionCreatedResponse:
    """Submit a corrected game score for moderator review.

    Both the school and the game (school + date) must already exist in the database.
    """
    async with get_conn() as conn:
        await require_school_exists(conn, body.school)
        await require_game_exists(conn, body.school, body.date)

        user_id = optional_user_id(current_user)
        payload = build_score_payload(body)
        submission_id, submitted_at = await insert_submission(conn, "score", body.school, user_id, payload)

    return SubmissionCreatedResponse(id=submission_id, type="score", school=body.school, submitted_at=submitted_at)


@router.post("/helmet-assignments", status_code=status.HTTP_201_CREATED, responses=_404)
@limiter.limit("10/minute")
async def submit_helmet_assignment(
    request: Request,
    response: Response,
    body: SubmitHelmetAssignmentRequest,
    current_user: OptionalUser = None,
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

        user_id = optional_user_id(current_user)
        payload = build_helmet_assignment_payload(body)
        submission_id, submitted_at = await insert_submission(conn, "helmet_assignment", body.school, user_id, payload)

    return SubmissionCreatedResponse(
        id=submission_id, type="helmet_assignment", school=body.school, submitted_at=submitted_at
    )


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def submit_feedback(
    request: Request, body: SubmitFeedbackRequest, current_user: OptionalUser = None
) -> SubmissionCreatedResponse:
    """Submit general feedback for moderator review."""
    user_id = optional_user_id(current_user)
    payload = build_feedback_payload(body)
    async with get_conn() as conn:
        submission_id, submitted_at = await insert_submission(conn, "feedback", None, user_id, payload)

    return SubmissionCreatedResponse(id=submission_id, type="feedback", school=None, submitted_at=submitted_at)
