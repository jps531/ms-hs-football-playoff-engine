"""Admin endpoints for season setup and data maintenance."""

from datetime import date as date_type
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from psycopg import sql
from psycopg.errors import UniqueViolation

from backend.api.db import get_conn
from backend.api.models.requests import (
    AssignChampionshipVenueRequest,
    CreateHelmetDesignRequest,
    CreateLocationRequest,
    GameOverrideField,
    LocationOverrideField,
    PatchHelmetDesignRequest,
    PatchLocationRequest,
    PatchSchoolSeasonRequest,
    PlayoffFormatRequest,
    SchoolOverrideField,
    SetGameHelmetRequest,
    SetGameOverrideRequest,
    SetLocationOverrideRequest,
    SetSchoolOverrideRequest,
)
from backend.api.models.responses import (
    AssignChampionshipVenueResult,
    ChampionshipGameRow,
    HelmetDesignModel,
    LocationDetailModel,
    LocationModel,
    OverrideAuditRow,
    PlayoffFormatSeedResult,
    YearsWornRange,
)

# Valid field sets for DELETE path param validation
_SCHOOL_OVERRIDE_FIELDS = frozenset(SchoolOverrideField.__args__)  # type: ignore[attr-defined]
_GAME_OVERRIDE_FIELDS = frozenset(GameOverrideField.__args__)  # type: ignore[attr-defined]
_LOCATION_OVERRIDE_FIELDS = frozenset(LocationOverrideField.__args__)  # type: ignore[attr-defined]

_HELMET_SELECT = """
    SELECT id, school, year_first_worn, year_last_worn, years_worn,
           image_left, image_right, photo, color, finish,
           facemask_color, logo, stripe, tags, notes
    FROM helmet_designs
    WHERE id = %s
"""


def _row_to_helmet(r) -> HelmetDesignModel:
    """Map a raw DB row tuple from _HELMET_SELECT to a HelmetDesignModel."""
    years_worn = None
    if r[4] is not None:
        years_worn = [YearsWornRange(start=s["start"], end=s["end"]) for s in r[4]]
    return HelmetDesignModel(
        id=r[0], school=r[1], year_first_worn=r[2], year_last_worn=r[3],
        years_worn=years_worn, image_left=r[5], image_right=r[6], photo=r[7],
        color=r[8], finish=r[9], facemask_color=r[10], logo=r[11], stripe=r[12],
        tags=list(r[13] or []), notes=r[14],
    )

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


# ---------------------------------------------------------------------------
# Locations (read-only helper for the championship venue picker)
# ---------------------------------------------------------------------------


@router.get("/locations")
async def list_locations() -> list[LocationModel]:
    """Return all venues in the locations table, ordered by name."""
    async with get_conn() as conn:
        rows = await conn.execute(
            "SELECT id, name, city, home_team FROM locations ORDER BY name"
        )
        return [
            LocationModel(id=r[0], name=r[1], city=r[2], home_team=r[3])
            async for r in rows
        ]


# ---------------------------------------------------------------------------
# Playoff format seeding
# ---------------------------------------------------------------------------


@router.post("/playoff-format")
async def seed_playoff_format(
    body: PlayoffFormatRequest,
    dry_run: Annotated[bool, Query()] = False,
) -> PlayoffFormatSeedResult:
    """Seed playoff_formats and playoff_format_slots for a new season.

    Idempotent — rows already present are skipped (ON CONFLICT DO NOTHING).
    Pass ``?dry_run=true`` to preview the counts without writing.
    """
    season = body.season
    total_slots = sum(len(c.slots) for c in body.classes)

    if dry_run:
        return PlayoffFormatSeedResult(
            season=season,
            classes_inserted=len(body.classes),
            slots_inserted=total_slots,
            dry_run=True,
        )

    format_sql = """
        INSERT INTO playoff_formats (season, class, num_regions, seeds_per_region, num_rounds, notes)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (season, class) DO NOTHING
    """
    slot_sql = """
        INSERT INTO playoff_format_slots
            (format_id, slot, home_region, home_seed, away_region, away_seed, north_south)
        SELECT f.id, $1, $2, $3, $4, $5, $6
        FROM playoff_formats f
        WHERE f.season = $7 AND f.class = $8
        ON CONFLICT DO NOTHING
    """

    async with get_conn() as conn:
        for cls in body.classes:
            notes = cls.notes or f"{cls.class_}A — {cls.num_regions * cls.seeds_per_region}-team bracket"
            await conn.execute(
                format_sql,
                (season, cls.class_, cls.num_regions, cls.seeds_per_region, cls.num_rounds, notes),
            )
            for slot in cls.slots:
                await conn.execute(
                    slot_sql,
                    (
                        slot.slot,
                        slot.home_region,
                        slot.home_seed,
                        slot.away_region,
                        slot.away_seed,
                        slot.north_south,
                        season,
                        cls.class_,
                    ),
                )

    return PlayoffFormatSeedResult(
        season=season,
        classes_inserted=len(body.classes),
        slots_inserted=total_slots,
        dry_run=False,
    )


# ---------------------------------------------------------------------------
# Championship venue assignment
# ---------------------------------------------------------------------------


@router.post("/championship-venue", responses=_404)
async def assign_championship_venue(
    body: AssignChampionshipVenueRequest,
    dry_run: Annotated[bool, Query()] = False,
) -> AssignChampionshipVenueResult:
    """Assign a venue to all Championship Game rows for a season.

    Championship games arrive from the scraper with ``location_id = NULL``.
    This endpoint sets ``location_id`` and ``location = 'neutral'``.

    Pass ``?dry_run=true`` to preview affected rows without writing.
    """
    async with get_conn() as conn:
        loc_row = await (
            await conn.execute(
                "SELECT id, name FROM locations WHERE id = $1",
                (body.location_id,),
            )
        ).fetchone()
        if loc_row is None:
            raise HTTPException(status_code=404, detail=f"Location id {body.location_id} not found")
        location_name = loc_row[1]

        find_sql = """
            SELECT g.school, g.date, g.opponent, ss.class
            FROM games g
            JOIN school_seasons ss ON ss.school = g.school AND ss.season = g.season
            WHERE g.season = $1
              AND g.round = 'Championship Game'
              AND g.location_id IS NULL
        """
        find_params: list = [body.season]
        if body.class_ is not None:
            find_sql += " AND ss.class = $2"
            find_params.append(body.class_)
        find_sql += " ORDER BY ss.class, g.date, g.school"

        game_rows = await conn.execute(find_sql, find_params)
        games = [
            ChampionshipGameRow(school=r[0], date=r[1], opponent=r[2], class_=r[3])
            async for r in game_rows
        ]

        if not games:
            raise HTTPException(
                status_code=404,
                detail=f"No unassigned Championship Game rows found for season {body.season}"
                + (f" class {body.class_}A" if body.class_ else ""),
            )

        if not dry_run:
            for game in games:
                await conn.execute(
                    "UPDATE games SET location_id = $1, location = 'neutral' WHERE school = $2 AND date = $3",
                    (body.location_id, game.school, game.date),
                )

    return AssignChampionshipVenueResult(
        season=body.season,
        location_id=body.location_id,
        location_name=location_name,
        games_updated=len(games),
        games=games,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# Override audit
# ---------------------------------------------------------------------------


@router.get("/overrides")
async def list_all_overrides() -> list[OverrideAuditRow]:
    """Return all active manual overrides across schools, locations, and games."""
    async with get_conn() as conn:
        rows = await conn.execute("SELECT source, key, value FROM list_overrides()")
        return [OverrideAuditRow(source=r[0], key=r[1], value=r[2]) async for r in rows]


# ---------------------------------------------------------------------------
# School overrides
# ---------------------------------------------------------------------------


@router.put("/schools/{school}/overrides", responses=_404)
async def set_school_override(school: str, body: SetSchoolOverrideRequest) -> OverrideAuditRow:
    """Set a manual override on a school field. Wins over pipeline-written values via schools_effective."""
    async with get_conn() as conn:
        row = await (await conn.execute("SELECT 1 FROM schools WHERE school = %s", (school,))).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"School '{school}' not found")
        await conn.execute("SELECT set_school_override(%s, %s, %s)", (school, body.field, body.value))
    return OverrideAuditRow(source=f"school:{school}", key=body.field, value=body.value)


@router.delete("/schools/{school}/overrides/{field}", status_code=204, responses=_404)
async def clear_school_override(school: str, field: str) -> None:
    """Remove a manual override from a school field, restoring the pipeline-written value."""
    if field not in _SCHOOL_OVERRIDE_FIELDS:
        raise HTTPException(status_code=422, detail=f"Invalid override field '{field}'. Valid: {sorted(_SCHOOL_OVERRIDE_FIELDS)}")
    async with get_conn() as conn:
        row = await (await conn.execute("SELECT 1 FROM schools WHERE school = %s", (school,))).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"School '{school}' not found")
        await conn.execute("SELECT clear_school_override(%s, %s)", (school, field))


# ---------------------------------------------------------------------------
# Game overrides
# ---------------------------------------------------------------------------


@router.put("/games/{school}/{date}/overrides", responses=_404)
async def set_game_override(school: str, date: date_type, body: SetGameOverrideRequest) -> OverrideAuditRow:
    """Set a manual override on a game field (e.g. fix a miscategorized region game or wrong score)."""
    async with get_conn() as conn:
        row = await (await conn.execute(
            "SELECT 1 FROM games WHERE school = %s AND date = %s", (school, date)
        )).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Game for '{school}' on {date} not found")
        await conn.execute("SELECT set_game_override(%s, %s, %s, %s)", (school, date, body.field, body.value))
    return OverrideAuditRow(source=f"game:{school}:{date}", key=body.field, value=body.value)


@router.delete("/games/{school}/{date}/overrides/{field}", status_code=204, responses=_404)
async def clear_game_override(school: str, date: date_type, field: str) -> None:
    """Remove a manual override from a game field, restoring the pipeline-written value."""
    if field not in _GAME_OVERRIDE_FIELDS:
        raise HTTPException(status_code=422, detail=f"Invalid override field '{field}'. Valid: {sorted(_GAME_OVERRIDE_FIELDS)}")
    async with get_conn() as conn:
        row = await (await conn.execute(
            "SELECT 1 FROM games WHERE school = %s AND date = %s", (school, date)
        )).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Game for '{school}' on {date} not found")
        await conn.execute("SELECT clear_game_override(%s, %s, %s)", (school, date, field))


# ---------------------------------------------------------------------------
# Game helmet assignment
# ---------------------------------------------------------------------------


@router.put("/games/{school}/{date}/helmet", responses=_404)
async def set_game_helmet(school: str, date: date_type, body: SetGameHelmetRequest) -> dict:
    """Assign (or clear) the helmet design worn by *school* in a specific game."""
    async with get_conn() as conn:
        row = await (await conn.execute(
            "SELECT 1 FROM games WHERE school = %s AND date = %s", (school, date)
        )).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Game for '{school}' on {date} not found")
        if body.helmet_design_id is not None:
            hrow = await (await conn.execute(
                "SELECT 1 FROM helmet_designs WHERE id = %s", (body.helmet_design_id,)
            )).fetchone()
            if hrow is None:
                raise HTTPException(status_code=404, detail=f"Helmet design {body.helmet_design_id} not found")
        await conn.execute(
            "UPDATE games SET helmet_design_id = %s WHERE school = %s AND date = %s",
            (body.helmet_design_id, school, date),
        )
    return {"school": school, "date": str(date), "helmet_design_id": body.helmet_design_id}


# ---------------------------------------------------------------------------
# School season flags
# ---------------------------------------------------------------------------


@router.patch("/school-seasons/{school}/{season}", responses=_404)
async def patch_school_season(school: str, season: int, body: PatchSchoolSeasonRequest) -> dict:
    """Toggle is_active for a school in a given season (pipeline never writes this column)."""
    async with get_conn() as conn:
        row = await (await conn.execute(
            "SELECT 1 FROM school_seasons WHERE school = %s AND season = %s", (school, season)
        )).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"School '{school}' season {season} not found")
        await conn.execute(
            "UPDATE school_seasons SET is_active = %s WHERE school = %s AND season = %s",
            (body.is_active, school, season),
        )
    return {"school": school, "season": season, "is_active": body.is_active}


# ---------------------------------------------------------------------------
# Locations CRUD + overrides
# ---------------------------------------------------------------------------


_409: dict[int | str, dict[str, Any]] = {409: {"description": "Conflict"}}


@router.post("/locations", status_code=201, responses=_409)
async def create_location(body: CreateLocationRequest) -> LocationDetailModel:
    """Add a new venue to the locations table."""
    async with get_conn() as conn:
        try:
            row = await (await conn.execute(
                """
                INSERT INTO locations (name, city, home_team, latitude, longitude)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, name, city, home_team, latitude, longitude
                """,
                (body.name, body.city, body.home_team, body.latitude, body.longitude),
            )).fetchone()
        except UniqueViolation:
            raise HTTPException(status_code=409, detail=f"Location '{body.name}' in '{body.city}' already exists")
    assert row is not None
    return LocationDetailModel(id=row[0], name=row[1], city=row[2], home_team=row[3], latitude=row[4], longitude=row[5])


@router.patch("/locations/{location_id}", responses=_404)
async def patch_location(location_id: int, body: PatchLocationRequest) -> LocationDetailModel:
    """Update fields on an existing venue."""
    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=422, detail="No fields provided to update")
    async with get_conn() as conn:
        row = await (await conn.execute("SELECT 1 FROM locations WHERE id = %s", (location_id,))).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Location {location_id} not found")
        set_clause = sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(k)) for k in update_data
        )
        query = sql.SQL(
            "UPDATE locations SET {} WHERE id = %s RETURNING id, name, city, home_team, latitude, longitude"
        ).format(set_clause)
        row = await (await conn.execute(query, list(update_data.values()) + [location_id])).fetchone()
    assert row is not None
    return LocationDetailModel(id=row[0], name=row[1], city=row[2], home_team=row[3], latitude=row[4], longitude=row[5])


@router.put("/locations/{location_id}/overrides", responses=_404)
async def set_location_override(location_id: int, body: SetLocationOverrideRequest) -> OverrideAuditRow:
    """Set a manual override on a location field."""
    async with get_conn() as conn:
        row = await (await conn.execute("SELECT 1 FROM locations WHERE id = %s", (location_id,))).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Location {location_id} not found")
        await conn.execute("SELECT set_location_override(%s, %s, %s)", (location_id, body.field, body.value))
    return OverrideAuditRow(source=f"location:{location_id}", key=body.field, value=body.value)


@router.delete("/locations/{location_id}/overrides/{field}", status_code=204, responses=_404)
async def clear_location_override(location_id: int, field: str) -> None:
    """Remove a manual override from a location field."""
    if field not in _LOCATION_OVERRIDE_FIELDS:
        raise HTTPException(status_code=422, detail=f"Invalid override field '{field}'. Valid: {sorted(_LOCATION_OVERRIDE_FIELDS)}")
    async with get_conn() as conn:
        row = await (await conn.execute("SELECT 1 FROM locations WHERE id = %s", (location_id,))).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Location {location_id} not found")
        await conn.execute("SELECT clear_location_override(%s, %s)", (location_id, field))


# ---------------------------------------------------------------------------
# Helmet design CRUD
# ---------------------------------------------------------------------------


@router.post("/helmets", status_code=201, responses=_404)
async def create_helmet_design(body: CreateHelmetDesignRequest) -> HelmetDesignModel:
    """Create a new helmet design record. Upload images separately via POST /api/v1/images/helmets/{id}/{type}."""
    async with get_conn() as conn:
        school_row = await (await conn.execute(
            "SELECT 1 FROM schools WHERE school = %s", (body.school,)
        )).fetchone()
        if school_row is None:
            raise HTTPException(status_code=404, detail=f"School '{body.school}' not found")

        years_worn_json = (
            [{"start": r.start, "end": r.end} for r in body.years_worn]
            if body.years_worn is not None else None
        )
        id_row = await (await conn.execute(
            """
            INSERT INTO helmet_designs
                (school, year_first_worn, year_last_worn, years_worn,
                 color, finish, facemask_color, logo, stripe, tags, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                body.school, body.year_first_worn, body.year_last_worn, years_worn_json,
                body.color, body.finish, body.facemask_color, body.logo, body.stripe,
                body.tags, body.notes,
            ),
        )).fetchone()
        assert id_row is not None
        detail_row = await (await conn.execute(_HELMET_SELECT, (id_row[0],))).fetchone()
    assert detail_row is not None
    return _row_to_helmet(detail_row)


@router.patch("/helmets/{design_id}", responses=_404)
async def patch_helmet_design(design_id: int, body: PatchHelmetDesignRequest) -> HelmetDesignModel:
    """Update metadata fields on a helmet design. Image columns are managed via /images/helmets/."""
    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=422, detail="No fields provided to update")

    # model_dump() recursively converts nested models to dicts, so years_worn is already list[dict]
    async with get_conn() as conn:
        row = await (await conn.execute("SELECT 1 FROM helmet_designs WHERE id = %s", (design_id,))).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Helmet design {design_id} not found")

        set_clause = sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(k)) for k in update_data
        )
        update_query = sql.SQL("UPDATE helmet_designs SET {} WHERE id = %s").format(set_clause)
        await conn.execute(update_query, list(update_data.values()) + [design_id])
        detail_row = await (await conn.execute(_HELMET_SELECT, (design_id,))).fetchone()
    assert detail_row is not None
    return _row_to_helmet(detail_row)


@router.delete("/helmets/{design_id}", status_code=204, responses=_404)
async def delete_helmet_design(design_id: int) -> None:
    """Delete a helmet design. Any games referencing it will have helmet_design_id set to NULL."""
    async with get_conn() as conn:
        row = await (await conn.execute("SELECT 1 FROM helmet_designs WHERE id = %s", (design_id,))).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Helmet design {design_id} not found")
        await conn.execute("DELETE FROM helmet_designs WHERE id = %s", (design_id,))
