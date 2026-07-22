"""Public endpoints for user-submitted corrections and new assets.

All endpoints are open to anonymous callers.  If the request includes a valid
Auth0 Bearer token the submission is linked to that user's row (user_id), which
enables future features like auto-approval for trusted contributors.  Submissions
without a token are accepted normally with user_id=NULL.

Submissions enter a moderation queue and are not applied to the live database
until a moderator approves them via ``/api/v1/moderation/submissions/{id}/approve``.
"""

import json
from functools import partial
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from backend.api.auth import OptionalUser, optional_user_id
from backend.api.db import get_conn
from backend.api.limiter import limiter
from backend.api.models.requests import (
    SubmitColorsRequest,
    SubmitFeedbackRequest,
    SubmitLocationRequest,
    SubmitScoreRequest,
)
from backend.api.models.responses import SubmissionCreatedResponse
from backend.helpers.image_helpers import (
    LogoType,
    save_and_upload,
    upload_submission_helmet_image,
    upload_submission_logo,
)
from backend.helpers.query_helpers import require_game_exists, require_school_exists

router = APIRouter(prefix="/api/v1/submissions", tags=["submissions"])

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}
_MAX_HELMET_IMAGES = 5


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
    payload = {"logo_type": logo_type, "cloudinary_path": cloudinary_path}
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                "INSERT INTO submissions (type, school, user_id, payload) VALUES ('logo', %s, %s, %s) RETURNING id, submitted_at",
                (school, user_id, json.dumps(payload)),
            )
        ).fetchone()
    assert row is not None

    return SubmissionCreatedResponse(id=row[0], type="logo", school=school, submitted_at=row[1])


@router.post("/helmets", status_code=status.HTTP_201_CREATED, responses=_404)
@limiter.limit("3/minute")
async def submit_helmet(
    request: Request,
    form: Annotated[_HelmetForm, Depends()],
    images: Annotated[list[UploadFile], File()] = [],
    logo_image: Annotated[UploadFile | None, File()] = None,
    current_user: OptionalUser = None,
) -> SubmissionCreatedResponse:
    """Submit a helmet design for moderator review.

    Upload up to five reference images (``images``) and an optional logo image
    (``logo_image``).  Images are stored in ``helmets/submissions/`` on
    Cloudinary and used by the moderator to create a helmet mockup — they are
    never promoted to a production path automatically.
    """
    if len(images) > _MAX_HELMET_IMAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"At most {_MAX_HELMET_IMAGES} images may be uploaded per submission",
        )

    async with get_conn() as conn:
        await require_school_exists(conn, form.school)

    payload: dict[str, Any] = {
        "year_first_worn": form.year_first_worn,
        "description": form.description,
    }
    if form.year_last_worn is not None:
        payload["year_last_worn"] = form.year_last_worn
    if form.currently_worn:
        payload["currently_worn"] = form.currently_worn
    for key, val in [
        ("color", form.color),
        ("finish", form.finish),
        ("facemask_color", form.facemask_color),
        ("logo_description", form.logo_description),
        ("stripe", form.stripe),
        ("additional_notes", form.additional_notes),
    ]:
        if val is not None:
            payload[key] = val

    user_id = optional_user_id(current_user)
    # Insert first so we get the submission_id for Cloudinary path construction.
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                "INSERT INTO submissions (type, school, user_id, payload) VALUES ('helmet', %s, %s, %s) RETURNING id, submitted_at",
                (form.school, user_id, json.dumps(payload)),
            )
        ).fetchone()
    assert row is not None
    submission_id: int = row[0]
    submitted_at = row[1]

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
    payload["image_paths"] = image_paths
    if logo_image_path is not None:
        payload["logo_image_path"] = logo_image_path

    async with get_conn() as conn:
        await conn.execute(
            "UPDATE submissions SET payload = %s, updated_at = NOW() WHERE id = %s",
            (json.dumps(payload), submission_id),
        )

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

        payload: dict[str, Any] = {}
        if body.primary_color is not None:
            payload["primary_color"] = body.primary_color.model_dump()
        if body.secondary_colors:
            payload["secondary_colors"] = [c.model_dump() for c in body.secondary_colors]

        row = await (
            await conn.execute(
                "INSERT INTO submissions (type, school, user_id, payload) VALUES ('colors', %s, %s, %s) RETURNING id, submitted_at",
                (body.school, user_id, json.dumps(payload)),
            )
        ).fetchone()
        assert row is not None

    return SubmissionCreatedResponse(id=row[0], type="colors", school=body.school, submitted_at=row[1])


@router.post("/locations", status_code=status.HTTP_201_CREATED, responses=_404)
@limiter.limit("10/minute")
async def submit_location(
    request: Request, body: SubmitLocationRequest, current_user: OptionalUser = None
) -> SubmissionCreatedResponse:
    """Submit corrected GPS coordinates for a school."""
    user_id = optional_user_id(current_user)
    async with get_conn() as conn:
        await require_school_exists(conn, body.school)

        payload = {"latitude": body.latitude, "longitude": body.longitude}
        row = await (
            await conn.execute(
                "INSERT INTO submissions (type, school, user_id, payload) VALUES ('location', %s, %s, %s) RETURNING id, submitted_at",
                (body.school, user_id, json.dumps(payload)),
            )
        ).fetchone()
        assert row is not None

    return SubmissionCreatedResponse(id=row[0], type="location", school=body.school, submitted_at=row[1])


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
        payload = {
            "date": body.date.isoformat(),
            "points_for": body.points_for,
            "points_against": body.points_against,
        }
        row = await (
            await conn.execute(
                "INSERT INTO submissions (type, school, user_id, payload) VALUES ('score', %s, %s, %s) RETURNING id, submitted_at",
                (body.school, user_id, json.dumps(payload)),
            )
        ).fetchone()
        assert row is not None

    return SubmissionCreatedResponse(id=row[0], type="score", school=body.school, submitted_at=row[1])


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def submit_feedback(
    request: Request, body: SubmitFeedbackRequest, current_user: OptionalUser = None
) -> SubmissionCreatedResponse:
    """Submit general feedback for moderator review."""
    user_id = optional_user_id(current_user)
    payload = {"subject": body.subject, "message": body.message}
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                "INSERT INTO submissions (type, school, user_id, payload) VALUES ('feedback', NULL, %s, %s) RETURNING id, submitted_at",
                (user_id, json.dumps(payload)),
            )
        ).fetchone()
    assert row is not None

    return SubmissionCreatedResponse(id=row[0], type="feedback", school=None, submitted_at=row[1])
