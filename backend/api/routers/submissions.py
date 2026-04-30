"""Public endpoints for user-submitted corrections and new assets.

All endpoints are unauthenticated.  Submissions enter a moderation queue
and are not applied to the live database until a moderator approves them
via ``/api/v1/moderation/submissions/{id}/approve``.
"""

import json
import os
import tempfile
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

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


def _save_temp(file: UploadFile, contents: bytes) -> str:
    """Write upload contents to a named temp file and return its path."""
    suffix = os.path.splitext(file.filename or "")[1] or ".png"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(contents)
    tmp.close()
    return tmp.name


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
) -> SubmissionCreatedResponse:
    """Submit a school logo for moderator review.

    The image is uploaded to the Cloudinary staging area
    (``logos/submissions/{logo_type}/{school}``) and will be moved to the
    production folder upon moderator approval.
    """
    async with get_conn() as conn:
        await _require_school(conn, school)

    contents = await file.read()
    tmp_path = _save_temp(file, contents)
    try:
        cloudinary_path = upload_submission_logo(tmp_path, school, logo_type)
    finally:
        os.unlink(tmp_path)

    payload = {"logo_type": logo_type, "cloudinary_path": cloudinary_path}
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                "INSERT INTO submissions (type, school, payload) VALUES ('logo', %s, %s) RETURNING id, submitted_at",
                (school, json.dumps(payload)),
            )
        ).fetchone()
    assert row is not None

    return SubmissionCreatedResponse(id=row[0], type="logo", school=school, submitted_at=row[1])


@router.post("/helmets", status_code=status.HTTP_201_CREATED, responses=_404)
async def submit_helmet(
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
    images: Annotated[list[UploadFile], File()] = [],
    logo_image: Annotated[UploadFile | None, File()] = None,
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
        await _require_school(conn, school)

    payload: dict[str, Any] = {
        "year_first_worn": year_first_worn,
        "description": description,
    }
    if year_last_worn is not None:
        payload["year_last_worn"] = year_last_worn
    if currently_worn:
        payload["currently_worn"] = currently_worn
    for key, val in [
        ("color", color),
        ("finish", finish),
        ("facemask_color", facemask_color),
        ("logo_description", logo_description),
        ("stripe", stripe),
        ("additional_notes", additional_notes),
    ]:
        if val is not None:
            payload[key] = val

    # Insert first so we get the submission_id for Cloudinary path construction.
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                "INSERT INTO submissions (type, school, payload) VALUES ('helmet', %s, %s) RETURNING id, submitted_at",
                (school, json.dumps(payload)),
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
            tmp = _save_temp(img, contents)
            tmp_paths.append(tmp)
            path = upload_submission_helmet_image(tmp, school, submission_id, i)
            image_paths.append(path)

        if logo_image is not None:
            contents = await logo_image.read()
            tmp = _save_temp(logo_image, contents)
            tmp_paths.append(tmp)
            logo_image_path = upload_submission_helmet_image(tmp, school, submission_id, len(images))
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

    return SubmissionCreatedResponse(id=submission_id, type="helmet", school=school, submitted_at=submitted_at)


@router.post("/colors", status_code=status.HTTP_201_CREATED, responses=_404)
async def submit_colors(body: SubmitColorsRequest) -> SubmissionCreatedResponse:
    """Submit a school color correction for moderator review."""
    async with get_conn() as conn:
        await _require_school(conn, body.school)

        payload: dict[str, Any] = {}
        if body.primary_color is not None:
            payload["primary_color"] = body.primary_color.model_dump()
        if body.secondary_colors:
            payload["secondary_colors"] = [c.model_dump() for c in body.secondary_colors]

        row = await (
            await conn.execute(
                "INSERT INTO submissions (type, school, payload) VALUES ('colors', %s, %s) RETURNING id, submitted_at",
                (body.school, json.dumps(payload)),
            )
        ).fetchone()
        assert row is not None

    return SubmissionCreatedResponse(id=row[0], type="colors", school=body.school, submitted_at=row[1])


@router.post("/locations", status_code=status.HTTP_201_CREATED, responses=_404)
async def submit_location(body: SubmitLocationRequest) -> SubmissionCreatedResponse:
    """Submit corrected GPS coordinates for a school."""
    async with get_conn() as conn:
        await _require_school(conn, body.school)

        payload = {"latitude": body.latitude, "longitude": body.longitude}
        row = await (
            await conn.execute(
                "INSERT INTO submissions (type, school, payload) VALUES ('location', %s, %s) RETURNING id, submitted_at",
                (body.school, json.dumps(payload)),
            )
        ).fetchone()
        assert row is not None

    return SubmissionCreatedResponse(id=row[0], type="location", school=body.school, submitted_at=row[1])


@router.post("/scores", status_code=status.HTTP_201_CREATED, responses={404: {"description": "School or game not found"}})
async def submit_score(body: SubmitScoreRequest) -> SubmissionCreatedResponse:
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

        payload = {
            "date": body.date.isoformat(),
            "points_for": body.points_for,
            "points_against": body.points_against,
        }
        row = await (
            await conn.execute(
                "INSERT INTO submissions (type, school, payload) VALUES ('score', %s, %s) RETURNING id, submitted_at",
                (body.school, json.dumps(payload)),
            )
        ).fetchone()
        assert row is not None

    return SubmissionCreatedResponse(id=row[0], type="score", school=body.school, submitted_at=row[1])


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def submit_feedback(body: SubmitFeedbackRequest) -> SubmissionCreatedResponse:
    """Submit general feedback for moderator review."""
    payload = {"subject": body.subject, "message": body.message}
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                "INSERT INTO submissions (type, school, payload) VALUES ('feedback', NULL, %s) RETURNING id, submitted_at",
                (json.dumps(payload),),
            )
        ).fetchone()
    assert row is not None

    return SubmissionCreatedResponse(id=row[0], type="feedback", school=None, submitted_at=row[1])
