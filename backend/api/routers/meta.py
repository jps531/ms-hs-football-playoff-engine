"""Navigation and metadata endpoints: seasons, structure, teams."""

from typing import Annotated, Any, LiteralString

from fastapi import APIRouter, HTTPException, Query
from psycopg import sql

from backend.api.db import get_conn
from backend.api.models.responses import (
    ChampionshipVenueModel,
    ClassStructure,
    HelmetDesignModel,
    LocationDetailModel,
    RegionSummary,
    SeasonDatesResponse,
    SeasonModel,
    SeasonStructureResponse,
    TeamModel,
)
from backend.helpers.api_helpers import (
    HELMET_DESIGNS_SELECT,
    build_helmet_from_fields,
    build_helmet_from_row,
    build_season_dates,
)
from backend.helpers.image_helpers import logo_url
from backend.helpers.query_helpers import and_join_conditions

router = APIRouter(prefix="/api/v1", tags=["meta"])
_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


def _row_to_team_model(r) -> TeamModel:
    """Map a schools_effective/school_seasons join row to a TeamModel."""
    return TeamModel(
        school=r[0],
        display_name=r[1],
        season=r[2],
        class_=r[3],
        region=r[4],
        city=r[5] or "",
        mascot=r[6] or "",
        primary_color=r[7] or "",
        secondary_color=r[8] or "",
        logo_primary=logo_url(r[9] or ""),
        logo_secondary=logo_url(r[10] or ""),
        logo_tertiary=logo_url(r[11] or ""),
        latitude=r[12],
        longitude=r[13],
        zip=r[14],
        secondary_color_hex=r[15],
    )


@router.get("/seasons")
async def list_seasons() -> list[SeasonModel]:
    """Return all seasons that have at least one school enrolled."""
    async with get_conn() as conn:
        rows = await conn.execute("SELECT DISTINCT season FROM school_seasons ORDER BY season DESC")
        return [SeasonModel(season=r[0]) async for r in rows]


@router.get("/seasons/{season}/structure", responses=_404)
async def get_season_structure(season: int) -> SeasonStructureResponse:
    """Return all classes and regions with team counts for *season*."""
    async with get_conn() as conn:
        rows = await conn.execute(
            """
            SELECT class, region, COUNT(*) AS team_count
            FROM school_seasons
            WHERE season = %s
            GROUP BY class, region
            ORDER BY class, region
            """,
            (season,),
        )
        by_class: dict[int, list[RegionSummary]] = {}
        async for class_, region, team_count in rows:
            by_class.setdefault(class_, []).append(RegionSummary(region=region, team_count=team_count))

    if not by_class:
        raise HTTPException(status_code=404, detail=f"Season {season} not found")

    classes = [ClassStructure(class_=c, regions=regions) for c, regions in sorted(by_class.items())]
    return SeasonStructureResponse(season=season, classes=classes)


@router.get("/seasons/{season}/dates", responses=_404)
async def get_season_dates(
    season: int,
    class_: Annotated[int | None, Query(alias="class", ge=1, le=7)] = None,
) -> SeasonDatesResponse:
    """Return the notable game dates for *season*, for a timeline scrubber.

    Pass ``class`` to scope ``round``/``week`` to one classification and
    resolve them unambiguously — 1A-4A and 5A-7A run offset playoff
    schedules, so a date can otherwise be a playoff date for one group of
    classes and still regular season for another (see ``SeasonDateEntry``).
    """
    query = (
        "SELECT g.date, g.round, ss.class, g.school, g.opponent "
        "FROM games_effective g "
        "JOIN school_seasons ss ON g.school = ss.school AND g.season = ss.season "
        "WHERE g.season = %s"
    )
    params: list = [season]
    if class_ is not None:
        query += " AND ss.class = %s"
        params.append(class_)

    async with get_conn() as conn:
        rows = await conn.execute(query, params)
        game_rows = [tuple(r) async for r in rows]

    if not game_rows:
        raise HTTPException(status_code=404, detail=f"Season {season} not found")

    return SeasonDatesResponse(season=season, dates=build_season_dates(game_rows, class_filter=class_))


@router.get("/teams")
async def list_teams(
    season: Annotated[int, Query()],
    class_: Annotated[int | None, Query(alias="class")] = None,
    region: Annotated[int | None, Query()] = None,
) -> list[TeamModel]:
    """Return teams for *season*, optionally filtered by class and region."""
    conditions: list[LiteralString] = ["ss.season = %s"]
    params: list = [season]
    if class_ is not None:
        conditions.append("ss.class = %s")
        params.append(class_)
    if region is not None:
        conditions.append("ss.region = %s")
        params.append(region)

    where_clause = and_join_conditions(conditions)
    query = sql.SQL("""
        SELECT s.school, s.display_name, ss.season, ss.class, ss.region,
               s.city, s.mascot, s.primary_color, s.secondary_color,
               s.logo_primary, s.logo_secondary, s.logo_tertiary,
               s.latitude, s.longitude, s.zip, s.secondary_color_hex
        FROM schools_effective s
        JOIN school_seasons ss ON s.school = ss.school
        WHERE {}
        ORDER BY ss.class, ss.region, s.school
    """).format(where_clause)
    async with get_conn() as conn:
        rows = await conn.execute(query, params)
        return [_row_to_team_model(r) async for r in rows]


@router.get("/teams/{team}", responses=_404)
async def get_team(team: str, season: Annotated[int, Query()]) -> TeamModel:
    """Return metadata for a single *team* in *season*."""
    async with get_conn() as conn:
        row = await conn.execute(
            """
            SELECT s.school, s.display_name, ss.season, ss.class, ss.region,
                   s.city, s.mascot, s.primary_color, s.secondary_color,
                   s.logo_primary, s.logo_secondary, s.logo_tertiary,
                   s.latitude, s.longitude, s.zip, s.secondary_color_hex
            FROM schools_effective s
            JOIN school_seasons ss ON s.school = ss.school
            WHERE s.school = %s AND ss.season = %s
            """,
            (team, season),
        )
        r = await row.fetchone()

    if r is None:
        raise HTTPException(status_code=404, detail=f"Team '{team}' not found for season {season}")

    return _row_to_team_model(r)


_HELMET_SELECT = HELMET_DESIGNS_SELECT


@router.get("/teams/{team}/helmets", responses=_404)
async def list_team_helmets(
    team: str,
    year: Annotated[int | None, Query()] = None,
) -> list[HelmetDesignModel]:
    """Return all helmet designs for *team*, optionally filtered to designs worn in *year*."""
    conditions: list[LiteralString] = ["school = %s"]
    params: list = [team]
    if year is not None:
        conditions.append("year_first_worn <= %s AND (year_last_worn IS NULL OR year_last_worn >= %s)")
        params.extend([year, year])

    where_clause = and_join_conditions(conditions)
    query = sql.SQL(_HELMET_SELECT + " WHERE {} ORDER BY year_first_worn").format(where_clause)

    async with get_conn() as conn:
        rows = await conn.execute(query, params)
        results = [build_helmet_from_row(r) async for r in rows]

    if not results and year is None:
        async with get_conn() as conn:
            check = await conn.execute("SELECT 1 FROM schools WHERE school = %s", (team,))
            if await check.fetchone() is None:
                raise HTTPException(status_code=404, detail=f"Team '{team}' not found")

    return results


@router.get("/teams/{team}/helmets/resolved", responses=_404)
async def resolve_team_helmet(
    team: str,
    season: Annotated[int, Query(ge=1980, le=2040)],
) -> HelmetDesignModel | None:
    """Resolve the default helmet design to display for *team* in *season*.

    Fallback order: the school's primary design covering *season*, else the
    most recently introduced design covering *season*, else ``null``. Does
    not consider per-game assignments — those are explicit on each game row
    (``GET /games``'s ``helmet_a``/``helmet_b``) and take precedence over this
    endpoint when present; callers should only fall back here when a game has
    no explicit assignment, or for contexts (team headers) with no single game.
    """
    async with get_conn() as conn:
        check = await conn.execute("SELECT 1 FROM schools WHERE school = %s", (team,))
        if await check.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Team '{team}' not found")

        query = sql.SQL(
            HELMET_DESIGNS_SELECT
            + " WHERE school = %s AND year_first_worn <= %s"
            + " AND (year_last_worn IS NULL OR year_last_worn >= %s)"
            + " ORDER BY is_primary DESC, year_first_worn DESC LIMIT 1"
        )
        row = await (await conn.execute(query, (team, season, season))).fetchone()

    return build_helmet_from_fields(*row) if row is not None else None


@router.get("/helmets")
async def list_helmets(
    team: Annotated[str | None, Query()] = None,
    color: Annotated[str | None, Query()] = None,
    finish: Annotated[str | None, Query()] = None,
    tag: Annotated[str | None, Query()] = None,
) -> list[HelmetDesignModel]:
    """Return helmet designs across all teams with optional filters."""
    conditions: list[LiteralString] = []
    params: list = []
    if team is not None:
        conditions.append("school = %s")
        params.append(team)
    if color is not None:
        conditions.append("color ILIKE %s")
        params.append(color)
    if finish is not None:
        conditions.append("finish ILIKE %s")
        params.append(finish)
    if tag is not None:
        conditions.append("%s = ANY(tags)")
        params.append(tag)

    if conditions:
        where_clause = and_join_conditions(conditions)
        query = sql.SQL(_HELMET_SELECT + " WHERE {} ORDER BY school, year_first_worn").format(where_clause)
    else:
        query = sql.SQL(_HELMET_SELECT + " ORDER BY school, year_first_worn")

    async with get_conn() as conn:
        rows = await conn.execute(query, params)
        return [build_helmet_from_row(r) async for r in rows]


@router.get("/championships")
async def list_championships(
    season: Annotated[int | None, Query()] = None,
    class_: Annotated[int | None, Query(alias="class", ge=1, le=7)] = None,
) -> list[ChampionshipVenueModel]:
    """Return championship venue history, optionally filtered by season and/or class.

    Each entry's ``has_games`` is true when that season/class's Championship Game has
    been imported into ``games`` (so the UI can link through to the game page);
    pre-import seasons return ``has_games: false`` and render as pure almanac entries.
    """
    conditions: list[LiteralString] = []
    params: list = []
    if season is not None:
        conditions.append("cv.season = %s")
        params.append(season)
    if class_ is not None:
        conditions.append("cv.class = %s")
        params.append(class_)

    query = """
        SELECT cv.season, cv.class, l.id, l.name, l.city, l.home_team, l.latitude, l.longitude,
               EXISTS (
                 SELECT 1 FROM games g
                 JOIN school_seasons ss ON ss.school = g.school AND ss.season = g.season
                 WHERE g.season = cv.season AND ss.class = cv.class AND g.round = 'Championship Game'
               ) AS has_games
        FROM championship_venues cv
        JOIN locations l ON l.id = cv.location_id
    """
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY cv.season DESC, cv.class"

    async with get_conn() as conn:
        rows = await conn.execute(query, params)
        return [
            ChampionshipVenueModel(
                season=r[0],
                class_=r[1],
                location=LocationDetailModel(id=r[2], name=r[3], city=r[4], home_team=r[5], latitude=r[6], longitude=r[7]),
                has_games=r[8],
            )
            async for r in rows
        ]
