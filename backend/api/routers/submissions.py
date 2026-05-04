"""Public endpoints for user-submitted corrections and new assets.

All endpoints are open to anonymous callers.  If the request includes a valid
Auth0 Bearer token the submission is linked to that user's row (user_id), which
enables future features like auto-approval for trusted contributors.  Submissions
without a token are accepted normally with user_id=NULL.

Submissions enter a moderation queue and are not applied to the live database
until a moderator approves them via ``/api/v1/moderation/submissions/{id}/approve``.
"""

import json
import os
import tempfile
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from backend.api.auth import OptionalUser
from backend.api.db import get_conn
from backend.api.models.requests import (
    SubmitColorsRequest,
    SubmitFeedbackRequest,
    SubmitLocationRequest,
    SubmitScoreRequest,
)
from backend.api.models.responses import SubmissionCreatedResponse
from backend.helpers.image_helpers import (
    LogoType,
    upload_submission_helmet_image,
    upload_submission_logo,
)

router = APIRouter(prefix="/api/v1/submissions", tags=["submissions"])

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}
_MAX_HELMET_IMAGES = 5
_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


def _validate_upload(file: UploadFile, contents: bytes) -> None:
    """Raise HTTP 422 if the upload is not an allowed image type or exceeds size limit."""
    if len(contents) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File exceeds maximum allowed size of {_MAX_FILE_BYTES // 1024 // 1024} MB",
        )
    if file.content_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: {sorted(_ALLOWED_MIME_TYPES)}",
        )


def _save_temp(file: UploadFile, contents: bytes) -> str:
    """Write upload contents to a named temp file (mode 0600) and return its path."""
    suffix = os.path.splitext(file.filename or "")[1] or ".png"
    tmp = tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=suffix)
    tmp.write(contents)
    tmp.close()
    return tmp.name


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


async def _require_school(conn, school: str) -> None:
    """Raise HTTP 404 if the school does not exist in the database."""
    row = await (await conn.execute("SELECT 1 FROM schools WHERE school = %s", (school,))).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"School '{school}' not found")


@router.post("/logos", status_code=status.HTTP_201_CREATED, responses=_404)
async def submit_logo(
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
        await _require_school(conn, school)

    contents = await file.read()
    _validate_upload(file, contents)
    tmp_path = _save_temp(file, contents)
    try:
        cloudinary_path = upload_submission_logo(tmp_path, school, logo_type)
    finally:
        os.unlink(tmp_path)

    user_id = current_user["db_id"] if current_user else None
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
async def submit_helmet(
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"At most {_MAX_HELMET_IMAGES} images may be uploaded per submission",
        )

    async with get_conn() as conn:
        await _require_school(conn, form.school)

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

    user_id = current_user["db_id"] if current_user else None
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
    tmp_paths: list[str] = []
    image_paths: list[str] = []
    logo_image_path: str | None = None
    try:
        for i, img in enumerate(images):
            contents = await img.read()
            _validate_upload(img, contents)
            tmp = _save_temp(img, contents)
            tmp_paths.append(tmp)
            path = upload_submission_helmet_image(tmp, form.school, submission_id, i)
            image_paths.append(path)

        if logo_image is not None:
            contents = await logo_image.read()
            _validate_upload(logo_image, contents)
            tmp = _save_temp(logo_image, contents)
            tmp_paths.append(tmp)
            logo_image_path = upload_submission_helmet_image(tmp, form.school, submission_id, len(images))
    finally:
        for p in tmp_paths:
            try:
                os.unlink(p)
            except OSError:
                pass

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
async def submit_colors(body: SubmitColorsRequest, current_user: OptionalUser = None) -> SubmissionCreatedResponse:
    """Submit a school color correction for moderator review."""
    user_id = current_user["db_id"] if current_user else None
    async with get_conn() as conn:
        await _require_school(conn, body.school)

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
async def submit_location(body: SubmitLocationRequest, current_user: OptionalUser = None) -> SubmissionCreatedResponse:
    """Submit corrected GPS coordinates for a school."""
    user_id = current_user["db_id"] if current_user else None
    async with get_conn() as conn:
        await _require_school(conn, body.school)

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
async def submit_score(body: SubmitScoreRequest, current_user: OptionalUser = None) -> SubmissionCreatedResponse:
    """Submit a corrected game score for moderator review.

    Both the school and the game (school + date) must already exist in the database.
    """
    async with get_conn() as conn:
        await _require_school(conn, body.school)

        game_row = await (
            await conn.execute(
                "SELECT 1 FROM games WHERE school = %s AND date = %s",
                (body.school, body.date),
            )
        ).fetchone()
        if game_row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Game for '{body.school}' on {body.date} not found",
            )

        user_id = current_user["db_id"] if current_user else None
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
async def submit_feedback(body: SubmitFeedbackRequest, current_user: OptionalUser = None) -> SubmissionCreatedResponse:
    """Submit general feedback for moderator review."""
    user_id = current_user["db_id"] if current_user else None
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
