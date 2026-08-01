"""Image upload endpoints for school logos, team logo assets, and helmet designs."""

from functools import partial
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from backend.api.auth import require_moderator
from backend.api.db import get_conn
from backend.api.models.responses import ImageUploadResponse
from backend.helpers.api_helpers import current_season
from backend.helpers.image_helpers import (
    HelmetImageType,
    LogoType,
    logo_url,
    save_and_upload,
    upload_helmet,
    upload_team_logo,
)
from backend.helpers.logo_helpers import sync_logo_cache
from backend.helpers.query_helpers import require_school_exists, set_helmet_image_column, set_team_logo_image_column

router = APIRouter(prefix="/api/v1/images", tags=["images"], dependencies=[Depends(require_moderator)])

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


async def _resolve_or_create_team_logo_id(conn, school: str, logo_type: str) -> int:
    """Resolve the team_logos row this school/logo_type's "the" logo should be, creating one
    if none exists yet. Prefers a row that is both is_primary and covers the current season;
    falls back to the most recently created row for (school, logo_type); creates a fresh
    unbounded/is_primary row if there's no history at all yet.
    """
    row = await (
        await conn.execute(
            """
            SELECT id FROM team_logos
            WHERE school = %s AND logo_type = %s
            ORDER BY (is_primary AND logo_covers_season(year_start, year_end, %s)) DESC, created_at DESC
            LIMIT 1
            """,
            (school, logo_type, current_season()),
        )
    ).fetchone()
    if row is not None:
        return row[0]

    id_row = await (
        await conn.execute(
            """
            INSERT INTO team_logos (school, logo_type, year_start, year_end, is_primary, has_keyline)
            VALUES (%s, %s, NULL, NULL, TRUE, FALSE)
            RETURNING id
            """,
            (school, logo_type),
        )
    ).fetchone()
    assert id_row is not None
    return id_row[0]


@router.post("/logos/{school}/{logo_type}", responses=_404)
async def upload_school_logo(
    school: str,
    logo_type: LogoType,
    file: Annotated[UploadFile, File()],
) -> ImageUploadResponse:
    """Upload a logo for *school*'s current (or most recently created) team_logos row of
    *logo_type*, creating one if none exists yet, and sync the schools.logo_{type} cache.

    Kept as a convenience endpoint for moderators fixing/setting a school's logo without
    navigating the full team_logos CRUD — it always resolves through team_logos rather than
    writing schools.logo_{type} directly, so team_logos stays the single source of truth.
    """
    async with get_conn() as conn:
        await require_school_exists(conn, school)
        team_logo_id = await _resolve_or_create_team_logo_id(conn, school, logo_type)

    path = await save_and_upload(
        file, partial(upload_team_logo, school_name=school, logo_type=logo_type, team_logo_id=team_logo_id)
    )

    async with get_conn() as conn:
        await set_team_logo_image_column(conn, team_logo_id, path)
        await sync_logo_cache(conn, school, logo_type, current_season())

    return ImageUploadResponse(path=path, url=logo_url(path))


@router.post("/team-logos/{team_logo_id}", responses=_404)
async def upload_team_logo_image(
    team_logo_id: int,
    file: Annotated[UploadFile, File()],
) -> ImageUploadResponse:
    """Upload the published asset image for a specific team_logos row *team_logo_id*."""
    async with get_conn() as conn:
        row = await (
            await conn.execute("SELECT school, logo_type FROM team_logos WHERE id = %s", (team_logo_id,))
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Team logo {team_logo_id} not found")
        school, logo_type = row

    path = await save_and_upload(
        file, partial(upload_team_logo, school_name=school, logo_type=logo_type, team_logo_id=team_logo_id)
    )

    async with get_conn() as conn:
        await set_team_logo_image_column(conn, team_logo_id, path)
        await sync_logo_cache(conn, school, logo_type, current_season())

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

    path = await save_and_upload(
        file, partial(upload_helmet, school_name=school, year=year, image_type=image_type, helmet_id=helmet_design_id)
    )

    async with get_conn() as conn:
        await set_helmet_image_column(conn, helmet_design_id, image_type, path)

    return ImageUploadResponse(path=path, url=logo_url(path))
