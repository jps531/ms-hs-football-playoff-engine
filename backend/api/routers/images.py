"""Image upload endpoints for school logos and helmet designs."""

import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from psycopg import sql

from backend.api.auth import require_moderator
from backend.api.db import get_conn
from backend.api.models.responses import ImageUploadResponse
from backend.helpers.image_helpers import (
    HelmetImageType,
    LogoType,
    logo_url,
    save_temp,
    upload_helmet,
    upload_logo,
    validate_upload,
)

router = APIRouter(prefix="/api/v1/images", tags=["images"], dependencies=[Depends(require_moderator)])

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}

_HELMET_COL: dict[HelmetImageType, str] = {
    "left": "image_left",
    "right": "image_right",
    "photo": "photo",
}


@router.post("/logos/{school}/{logo_type}", responses=_404)
async def upload_school_logo(
    school: str,
    logo_type: LogoType,
    file: Annotated[UploadFile, File()],
) -> ImageUploadResponse:
    """Upload a logo for *school* and update the DB."""
    async with get_conn() as conn:
        row = await (await conn.execute("SELECT 1 FROM schools WHERE school = %s", (school,))).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"School '{school}' not found")

    contents = await file.read()
    validate_upload(file.content_type, len(contents))
    tmp_path = save_temp(file.filename, contents)
    try:
        path = upload_logo(tmp_path, school, logo_type)
    finally:
        os.unlink(tmp_path)

    col = sql.Identifier(f"logo_{logo_type}")
    async with get_conn() as conn:
        await conn.execute(
            sql.SQL("UPDATE schools SET {} = %s WHERE school = %s").format(col),
            (path, school),
        )

    return ImageUploadResponse(path=path, url=logo_url(path))


@router.post("/helmets/{helmet_design_id}/{image_type}", responses=_404)
async def upload_helmet_image(
    helmet_design_id: int,
    image_type: HelmetImageType,
    file: Annotated[UploadFile, File()],
) -> ImageUploadResponse:
    """Upload an image for *helmet_design_id* and update the DB."""
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                "SELECT school, year_first_worn FROM helmet_designs WHERE id = %s",
                (helmet_design_id,),
            )
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Helmet design {helmet_design_id} not found")
        school, year = row[0], row[1]

    contents = await file.read()
    validate_upload(file.content_type, len(contents))
    tmp_path = save_temp(file.filename, contents)
    try:
        path = upload_helmet(tmp_path, school, year, image_type, helmet_design_id)
    finally:
        os.unlink(tmp_path)

    col = sql.Identifier(_HELMET_COL[image_type])
    async with get_conn() as conn:
        await conn.execute(
            sql.SQL("UPDATE helmet_designs SET {} = %s WHERE id = %s").format(col),
            (path, helmet_design_id),
        )

    return ImageUploadResponse(path=path, url=logo_url(path))
