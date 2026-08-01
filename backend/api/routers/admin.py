"""Admin endpoints for season setup and data maintenance."""

import logging
from datetime import date as date_type
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import sql
from psycopg.errors import UniqueViolation

from backend.api.auth import require_moderator
from backend.api.db import get_conn
from backend.api.models.requests import (
    AssignChampionshipVenueRequest,
    BulkRecomputeColorsRequest,
    CreateHelmetDesignRequest,
    CreateLocationRequest,
    CreateTeamLogoRequest,
    GameOverrideField,
    LocationOverrideField,
    PatchHelmetDesignRequest,
    PatchLocationRequest,
    PatchSchoolSeasonRequest,
    PatchTeamLogoRequest,
    PlayoffFormatRequest,
    SchoolOverrideField,
    SetGameHelmetRequest,
    SetGameOverrideRequest,
    SetLocationOverrideRequest,
    SetSchoolOverrideRequest,
    UpsertSchoolSeasonRequest,
)
from backend.api.models.responses import (
    AssignChampionshipVenueResult,
    BulkColorRecomputeResult,
    ChampionshipGameRow,
    ChampionshipVenueAssignment,
    ColorVariantsRecomputeResult,
    HelmetDesignModel,
    LocationDetailModel,
    LocationModel,
    OverrideAuditRow,
    PlayoffFormatSeedResult,
    TeamLogoModel,
)
from backend.helpers.api_helpers import (
    HELMET_DESIGNS_SELECT,
    build_helmet_from_row,
    current_season,
    default_classes_for_season,
)
from backend.helpers.color_variants import recompute_color_variants
from backend.helpers.logo_helpers import TEAM_LOGOS_SELECT, build_logo_from_row, sync_logo_cache
from backend.helpers.query_helpers import (
    build_set_clause,
    require_game_exists,
    require_helmet_design_exists,
    require_location_exists,
    require_nonempty_update,
    require_school_exists,
    require_team_logo_exists,
    resolve_location_by_name_or_team,
    validate_override_field,
    validate_submission_for_helmet_link,
    validate_submission_for_logo_asset,
)
from backend.helpers.query_helpers import upsert_school_season as upsert_school_season_row

_log = logging.getLogger(__name__)

# Valid field sets for DELETE path param validation
_SCHOOL_OVERRIDE_FIELDS = frozenset(SchoolOverrideField.__args__)  # type: ignore[attr-defined]
_GAME_OVERRIDE_FIELDS = frozenset(GameOverrideField.__args__)  # type: ignore[attr-defined]
_LOCATION_OVERRIDE_FIELDS = frozenset(LocationOverrideField.__args__)  # type: ignore[attr-defined]

# School override fields that feed color_variants — writing one of these must trigger a recompute.
_COLOR_HEX_OVERRIDE_FIELDS = frozenset({"primary_color_hex", "secondary_color_hex"})

_HELMET_SELECT = HELMET_DESIGNS_SELECT + " WHERE id = %s"
_TEAM_LOGO_SELECT = TEAM_LOGOS_SELECT + " WHERE id = %s"


router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_moderator)])

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}
_409: dict[int | str, dict[str, Any]] = {409: {"description": "Conflict"}}


# ---------------------------------------------------------------------------
# Locations (read-only helper for the championship venue picker)
# ---------------------------------------------------------------------------


@router.get("/locations")
async def list_locations() -> list[LocationModel]:
    """Return all venues in the locations table, ordered by name."""
    async with get_conn() as conn:
        rows = await conn.execute("SELECT id, name, city, home_team FROM locations ORDER BY name")
        return [LocationModel(id=r[0], name=r[1], city=r[2], home_team=r[3]) async for r in rows]


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

    _log.info("admin: seeding playoff format season=%s classes=%s", season, [c.class_ for c in body.classes])
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


@router.post("/championship-venue", responses={404: {"description": "Not found"}, 409: {"description": "Conflict"}})
async def assign_championship_venue(
    body: AssignChampionshipVenueRequest,
    dry_run: Annotated[bool, Query()] = False,
) -> AssignChampionshipVenueResult:
    """Assign a venue to a season's championship game(s), independent of whether
    that season's Championship Game rows exist in ``games`` yet.

    ``location`` is resolved case-insensitively against ``locations.name`` or
    ``locations.home_team`` (exact match); if it matches zero locations this
    returns 404, if it matches more than one it returns 409 listing the
    conflicting names.

    If ``class`` is omitted, the venue is assigned to every class in the
    season: classes are read from ``school_seasons`` if that season has been
    set up, otherwise from the historical MHSAA class count for that year.

    On a match, this upserts ``championship_venues`` for the resolved
    class(es) — the source of truth, usable even before that season's games
    have been scraped — and also mirrors ``location_id``/``location='neutral'``
    onto any Championship Game rows that already exist in ``games``. Safe to
    re-run to correct a mistake or reflect a venue change.

    Pass ``?dry_run=true`` to preview affected rows without writing.
    """
    async with get_conn() as conn:
        location_id, location_name = await resolve_location_by_name_or_team(conn, body.location)

        if body.class_ is not None:
            classes = [body.class_]
        else:
            class_rows = await conn.execute(
                "SELECT DISTINCT class FROM school_seasons WHERE season = %s ORDER BY class",
                (body.season,),
            )
            classes = [r[0] async for r in class_rows]
            if not classes:
                classes = default_classes_for_season(body.season)

        find_sql = """
            SELECT g.school, g.date, g.opponent, ss.class
            FROM games g
            JOIN school_seasons ss ON ss.school = g.school AND ss.season = g.season
            WHERE g.season = %s
              AND g.round = 'Championship Game'
              AND ss.class = ANY(%s)
            ORDER BY ss.class, g.date, g.school
        """
        game_rows = await conn.execute(find_sql, (body.season, classes))
        games = [ChampionshipGameRow(school=r[0], date=r[1], opponent=r[2], class_=r[3]) async for r in game_rows]

        if not dry_run:
            _log.info(
                "admin: assigning championship venue location_id=%s location=%s season=%s classes=%s games=%s",
                location_id,
                body.location,
                body.season,
                classes,
                len(games),
            )
            for clazz in classes:
                await conn.execute(
                    """
                    INSERT INTO championship_venues (season, class, location_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (season, class) DO UPDATE SET location_id = EXCLUDED.location_id
                    """,
                    (body.season, clazz, location_id),
                )
            for game in games:
                await conn.execute(
                    "UPDATE games SET location_id = %s, location = 'neutral' WHERE school = %s AND date = %s",
                    (location_id, game.school, game.date),
                )

    return AssignChampionshipVenueResult(
        season=body.season,
        location_id=location_id,
        location_name=location_name,
        classes=classes,
        games_updated=len(games),
        games=games,
        dry_run=dry_run,
    )


@router.get("/championship-venue")
async def list_championship_venues(
    season: Annotated[int | None, Query()] = None,
) -> list[ChampionshipVenueAssignment]:
    """Return all currently assigned championship venues, optionally filtered by season."""
    async with get_conn() as conn:
        sql_str = """
            SELECT cv.season, cv.class, cv.location_id, l.name
            FROM championship_venues cv
            JOIN locations l ON l.id = cv.location_id
        """
        params: list = []
        if season is not None:
            sql_str += " WHERE cv.season = %s"
            params.append(season)
        sql_str += " ORDER BY cv.season DESC, cv.class"
        rows = await conn.execute(sql_str, params)
        return [
            ChampionshipVenueAssignment(season=r[0], class_=r[1], location_id=r[2], location_name=r[3])
            async for r in rows
        ]


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
        await require_school_exists(conn, school)
        await conn.execute("SELECT set_school_override(%s, %s, %s)", (school, body.field, body.value))
        if body.field in _COLOR_HEX_OVERRIDE_FIELDS:
            await recompute_color_variants(conn, school)
    _log.info("admin: set school override school=%s field=%s", school, body.field)
    return OverrideAuditRow(source=f"school:{school}", key=body.field, value=body.value)


@router.delete("/schools/{school}/overrides/{field}", status_code=204, responses=_404)
async def clear_school_override(school: str, field: str) -> None:
    """Remove a manual override from a school field, restoring the pipeline-written value."""
    validate_override_field(field, _SCHOOL_OVERRIDE_FIELDS)
    async with get_conn() as conn:
        await require_school_exists(conn, school)
        await conn.execute("SELECT clear_school_override(%s, %s)", (school, field))
        if field in _COLOR_HEX_OVERRIDE_FIELDS:
            await recompute_color_variants(conn, school)
    _log.info("admin: cleared school override school=%s field=%s", school, field)


@router.post("/schools/{school}/recompute-colors", responses=_404)
async def recompute_school_colors(school: str) -> ColorVariantsRecomputeResult:
    """Manually recompute color_variants for one school (e.g. after a data repair)."""
    async with get_conn() as conn:
        await require_school_exists(conn, school)
        variants = await recompute_color_variants(conn, school)
    _log.info("admin: recomputed color_variants school=%s", school)
    return ColorVariantsRecomputeResult(school=school, color_variants=variants)


@router.post("/schools/recompute-colors")
async def bulk_recompute_school_colors(body: BulkRecomputeColorsRequest) -> BulkColorRecomputeResult:
    """Recompute color_variants for a batch of schools, or every school if none are given.

    Intended for use after an algorithm_version bump — re-clamps every school's
    colors under the new algorithm in one pass.
    """
    async with get_conn() as conn:
        if body.schools is not None:
            target_schools = body.schools
        else:
            rows = await conn.execute("SELECT school FROM schools ORDER BY school")
            target_schools = [r[0] async for r in rows]

        clamp_failed_schools: list[str] = []
        for school in target_schools:
            variants = await recompute_color_variants(conn, school)
            if variants and _any_clamp_failed(variants):
                clamp_failed_schools.append(school)

    _log.info("admin: bulk recomputed color_variants for %d schools", len(target_schools))
    return BulkColorRecomputeResult(recomputed=len(target_schools), clamp_failed_schools=clamp_failed_schools)


def _any_clamp_failed(variants: dict) -> bool:
    """Return True if any surface in a color_variants blob has clamp_failed set."""
    blobs = ([variants["primary"]] if variants.get("primary") else []) + variants.get("secondary", [])
    return any(blob[mode]["clamp_failed"] for blob in blobs for mode in ("light", "dark"))


# ---------------------------------------------------------------------------
# Game overrides
# ---------------------------------------------------------------------------


@router.put("/games/{school}/{date}/overrides", responses=_404)
async def set_game_override(school: str, date: date_type, body: SetGameOverrideRequest) -> OverrideAuditRow:
    """Set a manual override on a game field (e.g. fix a miscategorized region game or wrong score)."""
    async with get_conn() as conn:
        await require_game_exists(conn, school, date)
        await conn.execute("SELECT set_game_override(%s, %s, %s, %s)", (school, date, body.field, body.value))
    _log.info("admin: set game override school=%s date=%s field=%s", school, date, body.field)
    return OverrideAuditRow(source=f"game:{school}:{date}", key=body.field, value=body.value)


@router.delete("/games/{school}/{date}/overrides/{field}", status_code=204, responses=_404)
async def clear_game_override(school: str, date: date_type, field: str) -> None:
    """Remove a manual override from a game field, restoring the pipeline-written value."""
    validate_override_field(field, _GAME_OVERRIDE_FIELDS)
    async with get_conn() as conn:
        await require_game_exists(conn, school, date)
        await conn.execute("SELECT clear_game_override(%s, %s, %s)", (school, date, field))
    _log.info("admin: cleared game override school=%s date=%s field=%s", school, date, field)


# ---------------------------------------------------------------------------
# Game helmet assignment
# ---------------------------------------------------------------------------


@router.put("/games/{school}/{date}/helmet", responses=_404)
async def set_game_helmet(school: str, date: date_type, body: SetGameHelmetRequest) -> dict:
    """Assign (or clear) the helmet design worn by *school* in a specific game."""
    async with get_conn() as conn:
        await require_game_exists(conn, school, date)
        if body.helmet_design_id is not None:
            await require_helmet_design_exists(conn, body.helmet_design_id)
        await conn.execute(
            "UPDATE games SET helmet_design_id = %s WHERE school = %s AND date = %s",
            (body.helmet_design_id, school, date),
        )
    _log.info("admin: set game helmet school=%s date=%s helmet_design_id=%s", school, date, body.helmet_design_id)
    return {"school": school, "date": str(date), "helmet_design_id": body.helmet_design_id}


# ---------------------------------------------------------------------------
# School season flags
# ---------------------------------------------------------------------------


@router.patch("/school-seasons/{school}/{season}", responses=_404)
async def patch_school_season(school: str, season: int, body: PatchSchoolSeasonRequest) -> dict:
    """Toggle is_active for a school in a given season (pipeline never writes this column)."""
    async with get_conn() as conn:
        row = await (
            await conn.execute("SELECT 1 FROM school_seasons WHERE school = %s AND season = %s", (school, season))
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"School '{school}' season {season} not found")
        await conn.execute(
            "UPDATE school_seasons SET is_active = %s WHERE school = %s AND season = %s",
            (body.is_active, school, season),
        )
    _log.info("admin: set school_season is_active=%s school=%s season=%s", body.is_active, school, season)
    return {"school": school, "season": season, "is_active": body.is_active}


@router.put("/school-seasons/{school}/{season}", dependencies=[Depends(require_moderator)], responses=_404)
async def upsert_school_season(school: str, season: int, body: UpsertSchoolSeasonRequest) -> dict:
    """Create or overwrite a school_seasons row with explicit class, region, and is_active.

    Creates the parent schools row if it does not already exist. Overwrites class
    and region on conflict, so this is safe to re-run. Use for mid-cycle changes
    the Regions pipeline cannot handle: consolidations, closures, new schools.

    When ``copy_identity_from`` is supplied, copies mascot, colors, city, zip,
    latitude, and longitude from that school into the new school's base columns
    immediately, before the MHSAA identity and NCES pipelines have run. 404s if
    the source school does not exist.
    """
    async with get_conn() as conn:
        await upsert_school_season_row(
            conn, school, season, body.class_, body.region, body.is_active, body.copy_identity_from
        )
    if body.copy_identity_from:
        _log.info("admin: copied identity from '%s' to '%s'", body.copy_identity_from, school)
    _log.info(
        "admin: upsert school_season school=%s season=%s class=%s region=%s is_active=%s",
        school, season, body.class_, body.region, body.is_active,
    )
    return {
        "school": school,
        "season": season,
        "class": body.class_,
        "region": body.region,
        "is_active": body.is_active,
        "identity_copied_from": body.copy_identity_from,
    }


# ---------------------------------------------------------------------------
# Locations CRUD + overrides
# ---------------------------------------------------------------------------


@router.post("/locations", status_code=201, responses=_409)
async def create_location(body: CreateLocationRequest) -> LocationDetailModel:
    """Add a new venue to the locations table."""
    async with get_conn() as conn:
        try:
            row = await (
                await conn.execute(
                    """
                INSERT INTO locations (name, city, home_team, latitude, longitude)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, name, city, home_team, latitude, longitude
                """,
                    (body.name, body.city, body.home_team, body.latitude, body.longitude),
                )
            ).fetchone()
        except UniqueViolation:
            raise HTTPException(status_code=409, detail=f"Location '{body.name}' in '{body.city}' already exists")
    assert row is not None
    _log.info("admin: created location id=%s name=%s city=%s", row[0], body.name, body.city)
    return LocationDetailModel(id=row[0], name=row[1], city=row[2], home_team=row[3], latitude=row[4], longitude=row[5])


@router.patch("/locations/{location_id}", responses=_404)
async def patch_location(location_id: int, body: PatchLocationRequest) -> LocationDetailModel:
    """Update fields on an existing venue."""
    update_data = body.model_dump(exclude_unset=True)
    require_nonempty_update(update_data)
    async with get_conn() as conn:
        await require_location_exists(conn, location_id)
        set_clause = build_set_clause(update_data)
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
        await require_location_exists(conn, location_id)
        await conn.execute("SELECT set_location_override(%s, %s, %s)", (location_id, body.field, body.value))
    return OverrideAuditRow(source=f"location:{location_id}", key=body.field, value=body.value)


@router.delete("/locations/{location_id}/overrides/{field}", status_code=204, responses=_404)
async def clear_location_override(location_id: int, field: str) -> None:
    """Remove a manual override from a location field."""
    validate_override_field(field, _LOCATION_OVERRIDE_FIELDS)
    async with get_conn() as conn:
        await require_location_exists(conn, location_id)
        await conn.execute("SELECT clear_location_override(%s, %s)", (location_id, field))


# ---------------------------------------------------------------------------
# Helmet design CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/helmets",
    status_code=201,
    responses={
        404: {"description": "Not found"},
        409: {"description": "Submission already linked to a helmet design"},
        422: {"description": "Submission is not a helmet submission"},
    },
)
async def create_helmet_design(body: CreateHelmetDesignRequest) -> HelmetDesignModel:
    """Create a new helmet design record. Upload images separately via POST /api/v1/images/helmets/{id}/{type}.

    Pass ``from_submission_id`` to link this design back to the helmet submission it was
    created from (sets ``submissions.helmet_design_id`` in the same transaction) — 404 if the
    submission doesn't exist, 422 if it isn't a helmet-type submission, 409 if it's already
    linked to a different design.
    """
    async with get_conn() as conn:
        await require_school_exists(conn, body.school)

        if body.from_submission_id is not None:
            sub_row = await (
                await conn.execute(
                    "SELECT type, helmet_design_id FROM submissions WHERE id = %s", (body.from_submission_id,)
                )
            ).fetchone()
            validate_submission_for_helmet_link(sub_row, body.from_submission_id)

        years_worn_json = (
            [{"start": r.start, "end": r.end} for r in body.years_worn] if body.years_worn is not None else None
        )
        if body.is_primary:
            await conn.execute(
                "UPDATE helmet_designs SET is_primary = FALSE WHERE school = %s AND is_primary", (body.school,)
            )
        id_row = await (
            await conn.execute(
                """
            INSERT INTO helmet_designs
                (school, year_first_worn, year_last_worn, years_worn,
                 color, finish, facemask_color, logo, stripe, tags, notes, is_primary)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
                (
                    body.school,
                    body.year_first_worn,
                    body.year_last_worn,
                    years_worn_json,
                    body.color,
                    body.finish,
                    body.facemask_color,
                    body.logo,
                    body.stripe,
                    body.tags,
                    body.notes,
                    body.is_primary,
                ),
            )
        ).fetchone()
        assert id_row is not None
        if body.from_submission_id is not None:
            await conn.execute(
                "UPDATE submissions SET helmet_design_id = %s, updated_at = NOW() WHERE id = %s",
                (id_row[0], body.from_submission_id),
            )
        detail_row = await (await conn.execute(_HELMET_SELECT, (id_row[0],))).fetchone()
    assert detail_row is not None
    _log.info("admin: created helmet_design id=%s school=%s year=%s", id_row[0], body.school, body.year_first_worn)
    return build_helmet_from_row(detail_row)


@router.patch("/helmets/{design_id}", responses=_404)
async def patch_helmet_design(design_id: int, body: PatchHelmetDesignRequest) -> HelmetDesignModel:
    """Update metadata fields on a helmet design. Image columns are managed via /images/helmets/."""
    update_data = body.model_dump(exclude_unset=True)
    require_nonempty_update(update_data)

    # model_dump() recursively converts nested models to dicts, so years_worn is already list[dict]
    async with get_conn() as conn:
        await require_helmet_design_exists(conn, design_id)

        if update_data.get("is_primary"):
            await conn.execute(
                """
                UPDATE helmet_designs SET is_primary = FALSE
                WHERE is_primary AND id != %s
                  AND school = (SELECT school FROM helmet_designs WHERE id = %s)
                """,
                (design_id, design_id),
            )

        set_clause = build_set_clause(update_data)
        update_query = sql.SQL("UPDATE helmet_designs SET {} WHERE id = %s").format(set_clause)
        await conn.execute(update_query, list(update_data.values()) + [design_id])
        detail_row = await (await conn.execute(_HELMET_SELECT, (design_id,))).fetchone()
    assert detail_row is not None
    return build_helmet_from_row(detail_row)


@router.delete("/helmets/{design_id}", status_code=204, responses=_404)
async def delete_helmet_design(design_id: int) -> None:
    """Delete a helmet design. Any games referencing it will have helmet_design_id set to NULL."""
    async with get_conn() as conn:
        await require_helmet_design_exists(conn, design_id)
        await conn.execute("DELETE FROM helmet_designs WHERE id = %s", (design_id,))
    _log.info("admin: deleted helmet_design id=%s", design_id)


# ---------------------------------------------------------------------------
# Team logo asset CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/logos",
    status_code=201,
    responses={
        404: {"description": "Not found"},
        422: {"description": "Submission is not an accepted-pending-asset logo submission"},
    },
)
async def create_team_logo(body: CreateTeamLogoRequest) -> TeamLogoModel:
    """Create a new team_logos record. Upload the asset separately via
    POST /api/v1/images/team-logos/{id}.

    Pass ``from_submission_id`` to close the loop back to the reference
    submission it was cut from — 404 if the submission doesn't exist, 422 if
    it isn't a logo submission or isn't in the accepted_pending_asset state.
    Unlike helmets (where the submission carries the FK to the design),
    team_logos carries the FK to the submission, so closing the loop here
    also flips the submission's status to approved in the same transaction.
    """
    async with get_conn() as conn:
        await require_school_exists(conn, body.school)

        if body.from_submission_id is not None:
            sub_row = await (
                await conn.execute("SELECT type, status FROM submissions WHERE id = %s", (body.from_submission_id,))
            ).fetchone()
            validate_submission_for_logo_asset(sub_row, body.from_submission_id)

        if body.is_primary:
            await conn.execute(
                "UPDATE team_logos SET is_primary = FALSE WHERE school = %s AND logo_type = %s AND is_primary",
                (body.school, body.logo_type),
            )
        id_row = await (
            await conn.execute(
                """
                INSERT INTO team_logos
                    (school, logo_type, year_start, year_end, is_primary, has_keyline, notes, source_submission_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    body.school,
                    body.logo_type,
                    body.year_start,
                    body.year_end,
                    body.is_primary,
                    body.has_keyline,
                    body.notes,
                    body.from_submission_id,
                ),
            )
        ).fetchone()
        assert id_row is not None

        if body.from_submission_id is not None:
            await conn.execute(
                "UPDATE submissions SET status = 'approved', reviewed_at = NOW(), updated_at = NOW() WHERE id = %s",
                (body.from_submission_id,),
            )

        await sync_logo_cache(conn, body.school, body.logo_type, current_season())
        detail_row = await (await conn.execute(_TEAM_LOGO_SELECT, (id_row[0],))).fetchone()
    assert detail_row is not None
    _log.info("admin: created team_logo id=%s school=%s logo_type=%s", id_row[0], body.school, body.logo_type)
    return build_logo_from_row(detail_row)


@router.patch("/logos/{logo_id}", responses=_404)
async def patch_team_logo(logo_id: int, body: PatchTeamLogoRequest) -> TeamLogoModel:
    """Update years, primary flag, keyline flag, or notes on a team_logos row.
    Image column is managed via /images/team-logos/."""
    update_data = body.model_dump(exclude_unset=True)
    require_nonempty_update(update_data)

    async with get_conn() as conn:
        await require_team_logo_exists(conn, logo_id)

        if update_data.get("is_primary"):
            await conn.execute(
                """
                UPDATE team_logos SET is_primary = FALSE
                WHERE is_primary AND id != %s
                  AND school = (SELECT school FROM team_logos WHERE id = %s)
                  AND logo_type = (SELECT logo_type FROM team_logos WHERE id = %s)
                """,
                (logo_id, logo_id, logo_id),
            )

        set_clause = build_set_clause(update_data)
        update_query = sql.SQL("UPDATE team_logos SET {}, updated_at = NOW() WHERE id = %s").format(set_clause)
        await conn.execute(update_query, list(update_data.values()) + [logo_id])
        detail_row = await (await conn.execute(_TEAM_LOGO_SELECT, (logo_id,))).fetchone()
        assert detail_row is not None
        model = build_logo_from_row(detail_row)
        await sync_logo_cache(conn, model.school, model.logo_type, current_season())
    return model


@router.delete("/logos/{logo_id}", status_code=204, responses=_404)
async def delete_team_logo(logo_id: int) -> None:
    """Delete a team_logos row."""
    async with get_conn() as conn:
        detail_row = await (await conn.execute(_TEAM_LOGO_SELECT, (logo_id,))).fetchone()
        if detail_row is None:
            raise HTTPException(status_code=404, detail=f"Team logo {logo_id} not found")
        model = build_logo_from_row(detail_row)
        await conn.execute("DELETE FROM team_logos WHERE id = %s", (logo_id,))
        await sync_logo_cache(conn, model.school, model.logo_type, current_season())
    _log.info("admin: deleted team_logo id=%s", logo_id)


@router.get("/logos/needs-recut")
async def list_logos_needing_recut() -> list[TeamLogoModel]:
    """Published logo assets with has_keyline = FALSE — the re-cut backlog."""
    async with get_conn() as conn:
        rows = await conn.execute(
            TEAM_LOGOS_SELECT + " WHERE has_keyline = FALSE AND image_url IS NOT NULL ORDER BY school, logo_type"
        )
        return [build_logo_from_row(r) async for r in rows]
