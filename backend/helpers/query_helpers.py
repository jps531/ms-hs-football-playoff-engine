"""Small SQL-fragment builders and DB-backed validation helpers shared across routers."""

from collections.abc import Sequence
from typing import LiteralString

from fastapi import HTTPException
from psycopg import sql


async def require_school_exists(conn, school: str) -> None:  # pragma: no cover
    """Raise HTTP 404 if *school* is not present in the ``schools`` table."""
    row = await (await conn.execute("SELECT 1 FROM schools WHERE school = %s", (school,))).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"School '{school}' not found")


async def require_game_exists(conn, school: str, game_date) -> None:  # pragma: no cover
    """Raise HTTP 404 if no game exists for *school* on *game_date*."""
    row = await (
        await conn.execute("SELECT 1 FROM games WHERE school = %s AND date = %s", (school, game_date))
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Game for '{school}' on {game_date} not found")


async def require_location_exists(conn, location_id: int) -> None:  # pragma: no cover
    """Raise HTTP 404 if no location exists with *location_id*."""
    row = await (await conn.execute("SELECT 1 FROM locations WHERE id = %s", (location_id,))).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Location {location_id} not found")


async def resolve_location_by_name_or_team(conn, location: str) -> tuple[int, str]:  # pragma: no cover
    """Resolve *location* to a single locations row, matching case-insensitively and exactly
    against either ``locations.name`` or ``locations.home_team``.

    Returns ``(id, name)``. Raises HTTP 404 if nothing matches, HTTP 409 if ambiguous.
    """
    rows = await (
        await conn.execute(
            "SELECT id, name FROM locations WHERE LOWER(name) = LOWER(%s) OR LOWER(home_team) = LOWER(%s)",
            (location, location),
        )
    ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"Location '{location}' not found (checked name and home_team)")
    if len(rows) > 1:
        names = ", ".join(sorted(r[1] for r in rows))
        raise HTTPException(
            status_code=409,
            detail=f"Location '{location}' is ambiguous — matches multiple locations: {names}",
        )
    return rows[0][0], rows[0][1]


async def upsert_school_season(  # pragma: no cover
    conn,
    school: str,
    season: int,
    class_: int,
    region: int,
    is_active: bool,
    copy_identity_from: str | None,
) -> None:
    """Create or overwrite a school_seasons row with explicit class, region, and is_active.

    Creates the parent schools row if it does not already exist. Overwrites
    class and region on conflict, so this is safe to re-run. Use for mid-cycle
    changes the Regions pipeline cannot handle: consolidations, closures, new
    schools.

    When *copy_identity_from* is supplied, copies mascot, colors, city, zip,
    latitude, and longitude from that school into *school*'s base columns
    immediately, before the MHSAA identity and NCES pipelines have run. Raises
    HTTP 404 if the source school does not exist.
    """
    await conn.execute(
        "INSERT INTO schools (school) VALUES (%s) ON CONFLICT (school) DO NOTHING",
        (school,),
    )
    await conn.execute(
        """
        INSERT INTO school_seasons (school, season, class, region, is_active)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (school, season) DO UPDATE SET
            class     = EXCLUDED.class,
            region    = EXCLUDED.region,
            is_active = EXCLUDED.is_active
        """,
        (school, season, class_, region, is_active),
    )
    if copy_identity_from:
        src = await (await conn.execute("SELECT 1 FROM schools WHERE school = %s", (copy_identity_from,))).fetchone()
        if src is None:
            raise HTTPException(status_code=404, detail=f"Source school '{copy_identity_from}' not found")
        await conn.execute(
            """
            UPDATE schools s SET
                mascot              = COALESCE(NULLIF(e.mascot, ''),              s.mascot),
                primary_color       = COALESCE(NULLIF(e.primary_color, ''),       s.primary_color),
                secondary_color     = COALESCE(NULLIF(e.secondary_color, ''),     s.secondary_color),
                primary_color_hex   = COALESCE(NULLIF(e.primary_color_hex, ''),   s.primary_color_hex),
                secondary_color_hex = COALESCE(NULLIF(e.secondary_color_hex, ''), s.secondary_color_hex),
                city                = COALESCE(s.city,      e.city),
                zip                 = COALESCE(s.zip,       e.zip),
                latitude            = COALESCE(s.latitude,  e.latitude),
                longitude           = COALESCE(s.longitude, e.longitude)
            FROM schools_effective e
            WHERE s.school = %s AND e.school = %s
            """,
            (school, copy_identity_from),
        )


async def require_helmet_design_exists(conn, design_id: int) -> None:  # pragma: no cover
    """Raise HTTP 404 if no helmet design exists with *design_id*."""
    row = await (await conn.execute("SELECT 1 FROM helmet_designs WHERE id = %s", (design_id,))).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Helmet design {design_id} not found")


def validate_submission_for_helmet_link(sub_row: tuple | None, submission_id: int) -> None:
    """Validate a fetched ``(type, helmet_design_id)`` submissions row before linking it to a new
    helmet design via ``POST /admin/helmets``'s ``from_submission_id``.

    Raises HTTP 404 if *sub_row* is ``None`` (no such submission), HTTP 422 if
    it isn't a helmet-type submission, HTTP 409 if it's already linked to a
    different design.
    """
    if sub_row is None:
        raise HTTPException(status_code=404, detail=f"Submission {submission_id} not found")
    if sub_row[0] != "helmet":
        raise HTTPException(status_code=422, detail=f"Submission {submission_id} is not a helmet submission")
    if sub_row[1] is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Submission {submission_id} is already linked to helmet design {sub_row[1]}",
        )


async def require_team_logo_exists(conn, team_logo_id: int) -> None:  # pragma: no cover
    """Raise HTTP 404 if no team_logos row exists with *team_logo_id*."""
    row = await (await conn.execute("SELECT 1 FROM team_logos WHERE id = %s", (team_logo_id,))).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Team logo {team_logo_id} not found")


def validate_submission_for_logo_asset(sub_row: tuple | None, submission_id: int) -> None:
    """Validate a fetched ``(type, status)`` submissions row before creating a new team_logos
    row from it via ``POST /admin/logos``'s ``from_submission_id``.

    Raises HTTP 404 if *sub_row* is ``None`` (no such submission), HTTP 422 if
    it isn't a logo-type submission, HTTP 422 if it isn't in the
    ``accepted_pending_asset`` state (not yet accepted, already turned into an
    asset, or rejected). Unlike the helmet link check, this has no 409 case —
    ``status`` alone already distinguishes "not yet accepted" from "already
    turned into an asset" (status would already be ``approved`` by then), since
    team_logos carries the FK to submissions (not the reverse, as with
    helmets), so there is no separate "already linked" state to detect here.
    """
    if sub_row is None:
        raise HTTPException(status_code=404, detail=f"Submission {submission_id} not found")
    if sub_row[0] != "logo":
        raise HTTPException(status_code=422, detail=f"Submission {submission_id} is not a logo submission")
    if sub_row[1] != "accepted_pending_asset":
        raise HTTPException(
            status_code=422,
            detail=f"Submission {submission_id} is not accepted-pending-asset (status={sub_row[1]!r})",
        )


async def set_school_logo_column(conn, school: str, logo_type: str, path: str) -> None:  # pragma: no cover
    """Write *path* into the ``schools.logo_{logo_type}`` column for *school*."""
    col = sql.Identifier(f"logo_{logo_type}")
    await conn.execute(
        sql.SQL("UPDATE schools SET {} = %s WHERE school = %s").format(col),
        (path, school),
    )


# helmet_designs image column per HelmetImageType ('left'/'right'/'photo') — not a simple
# f-string prefix like set_school_logo_column's, since 'photo' maps to itself.
HELMET_IMAGE_COLUMNS: dict[str, str] = {"left": "image_left", "right": "image_right", "photo": "photo"}


async def set_helmet_image_column(conn, helmet_design_id: int, image_type: str, path: str) -> None:  # pragma: no cover
    """Write *path* into the appropriate ``helmet_designs`` image column for *helmet_design_id*."""
    col = sql.Identifier(HELMET_IMAGE_COLUMNS[image_type])
    await conn.execute(
        sql.SQL("UPDATE helmet_designs SET {} = %s WHERE id = %s").format(col),
        (path, helmet_design_id),
    )


async def set_team_logo_image_column(conn, team_logo_id: int, path: str) -> None:  # pragma: no cover
    """Write *path* into ``team_logos.image_url`` for *team_logo_id*. Unlike helmets,
    there's a single image column — no image_type dimension needed."""
    await conn.execute(
        "UPDATE team_logos SET image_url = %s, updated_at = NOW() WHERE id = %s",
        (path, team_logo_id),
    )


def append_optional_filters(
    conditions: list[LiteralString], params: list, *pairs: tuple[LiteralString, object]
) -> None:
    """Append ``(sql_fragment, value)`` pairs to *conditions*/*params* in place, skipping any
    pair whose value is ``None``.

    Dedupes the repeated ``if x is not None: conditions.append(...); params.append(x)``
    idiom used to build a dynamic ``WHERE`` clause from optional query params.
    Mandatory conditions (e.g. a required ``season`` filter) should be added to
    *conditions*/*params* directly by the caller before calling this — only the
    optional tail belongs here.
    """
    for sql_fragment, value in pairs:
        if value is not None:
            conditions.append(sql_fragment)
            params.append(value)


def and_join_conditions(conditions: Sequence[LiteralString]) -> sql.Composed:
    """Join raw SQL condition strings with ``AND``, for a dynamic ``WHERE`` clause."""
    return sql.SQL(" AND ").join(sql.SQL(c) for c in conditions)


def build_set_clause(update_data: dict) -> sql.Composed:
    """Build a ``col1 = %s, col2 = %s, ...`` fragment from an update dict.

    Column order matches ``update_data``'s iteration order — pass
    ``list(update_data.values())`` (same order) as the corresponding query params.
    """
    return sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(k)) for k in update_data)


def require_nonempty_update(update_data: dict) -> None:
    """Raise HTTP 422 if *update_data* (from ``body.model_dump(exclude_unset/none=True)``) is empty."""
    if not update_data:
        raise HTTPException(status_code=422, detail="No fields provided to update")


def validate_override_field(field: str, valid_fields: frozenset[str]) -> None:
    """Raise HTTP 422 if *field* is not one of *valid_fields* (a DELETE .../overrides/{field} path param)."""
    if field not in valid_fields:
        raise HTTPException(status_code=422, detail=f"Invalid override field '{field}'. Valid: {sorted(valid_fields)}")
