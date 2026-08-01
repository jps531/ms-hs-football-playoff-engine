"""Navigation and metadata endpoints: seasons, structure, teams."""

from typing import Annotated, Any, Literal, LiteralString

from fastapi import APIRouter, HTTPException, Query
from psycopg import sql

from backend.api.db import get_conn
from backend.api.models.responses import (
    ChampionshipVenueModel,
    ClassStructure,
    HelmetDesignModel,
    HelmetDetailModel,
    HelmetListItemModel,
    LocationDetailModel,
    RegionSummary,
    RoadmapResponse,
    SeasonDatesResponse,
    SeasonModel,
    SeasonStructureResponse,
    TeamLogoModel,
    TeamModel,
)
from backend.helpers.api_helpers import (
    HELMET_DESIGNS_SELECT,
    HELMET_STATS_SELECT,
    build_helmet_from_fields,
    build_helmet_from_row,
    build_helmet_game_worn,
    build_helmet_stats_fields,
    build_roadmap_games,
    build_season_dates,
    load_championship_venue,
    load_home_venues,
    venue_distance_miles,
)
from backend.helpers.image_helpers import LogoType, logo_url
from backend.helpers.logo_helpers import TEAM_LOGOS_SELECT, build_logo_from_row
from backend.helpers.query_helpers import and_join_conditions, require_school_exists

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
        color_variants=r[16],
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
               s.latitude, s.longitude, s.zip, s.secondary_color_hex,
               s.color_variants
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
                   s.latitude, s.longitude, s.zip, s.secondary_color_hex,
                   s.color_variants
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
            await require_school_exists(conn, team)

    return results


@router.get("/teams/{team}/helmets/resolved", responses=_404)
async def resolve_team_helmet(
    team: str,
    season: Annotated[int, Query(ge=1980, le=2040)],
) -> HelmetDesignModel | None:
    """Resolve the default helmet design to display for *team* in *season*.

    Fallback order: the school's primary design covering *season*, else the
    most recently introduced design covering *season*, else ``null``. "Covering
    *season*" respects non-contiguous wear (``years_worn``) via
    ``helmet_covers_season()`` when set, not just the year_first_worn/
    year_last_worn outer bound. Does not consider per-game assignments —
    those are explicit on each game row (``GET /games``'s ``helmet_a``/
    ``helmet_b``) and take precedence over this endpoint when present; callers
    should only fall back here when a game has no explicit assignment, or for
    contexts (team headers) with no single game.
    """
    async with get_conn() as conn:
        await require_school_exists(conn, team)

        query = sql.SQL(
            HELMET_DESIGNS_SELECT
            + " WHERE school = %s AND helmet_covers_season(years_worn, year_first_worn, year_last_worn, %s)"
            + " ORDER BY is_primary DESC, year_first_worn DESC LIMIT 1"
        )
        row = await (await conn.execute(query, (team, season))).fetchone()

    return build_helmet_from_fields(*row) if row is not None else None


@router.get("/teams/{team}/logos", responses=_404)
async def list_team_logos(
    team: str,
    logo_type: Annotated[LogoType | None, Query()] = None,
    year: Annotated[int | None, Query()] = None,
) -> list[TeamLogoModel]:
    """Return logo asset history for *team*, optionally filtered by logo_type and/or year.

    Mirrors GET /teams/{team}/helmets: ``year`` uses the same simplified
    outer-bound check the helmet endpoint uses (year_start <= year AND
    (year_end IS NULL OR year_end >= year)), not the full logo_covers_season
    — currently equivalent since logos have no non-contiguous-span case, but
    this is "the" documented semantics for that filter.
    """
    conditions: list[LiteralString] = ["school = %s"]
    params: list = [team]
    if logo_type is not None:
        conditions.append("logo_type = %s")
        params.append(logo_type)
    if year is not None:
        conditions.append("(year_start IS NULL OR year_start <= %s) AND (year_end IS NULL OR year_end >= %s)")
        params.extend([year, year])

    where_clause = and_join_conditions(conditions)
    query = sql.SQL(TEAM_LOGOS_SELECT + " WHERE {} ORDER BY logo_type, year_start").format(where_clause)

    async with get_conn() as conn:
        rows = await conn.execute(query, params)
        results = [build_logo_from_row(r) async for r in rows]

    if not results and year is None and logo_type is None:
        async with get_conn() as conn:
            await require_school_exists(conn, team)

    return results


@router.get("/teams/{team}/logos/resolved", responses=_404)
async def resolve_team_logo(
    team: str,
    season: Annotated[int, Query(ge=1980, le=2040)],
    logo_type: Annotated[LogoType, Query()] = "primary",
) -> TeamLogoModel | None:
    """Resolve the logo asset to display for *team*/*logo_type* in *season*.

    Fallback order: the row that is both is_primary and covers *season* via
    logo_covers_season(), else the row with the most recent year_start that
    covers *season*, else null. year_start is nullable (unlike helmets'
    NOT NULL year_first_worn), so the ORDER BY needs NULLS LAST — otherwise
    Postgres's default NULLS FIRST for DESC would put the unbounded-past
    ("current") row ahead of more specific historical matches, inverting the
    intended preference.
    """
    async with get_conn() as conn:
        await require_school_exists(conn, team)

        query = sql.SQL(
            TEAM_LOGOS_SELECT
            + " WHERE school = %s AND logo_type = %s AND logo_covers_season(year_start, year_end, %s)"
            + " ORDER BY is_primary DESC, year_start DESC NULLS LAST LIMIT 1"
        )
        row = await (await conn.execute(query, (team, logo_type, season))).fetchone()

    return build_logo_from_row(row) if row is not None else None


@router.get("/teams/{team}/roadmap", responses=_404)
async def get_team_roadmap(team: str, season: Annotated[int, Query(ge=1980, le=2040)]) -> RoadmapResponse:
    """Return *team*'s full-season roadmap for *season* (regular season plus playoffs) with the
    straight-line distance traveled for each game, plus cumulative and championship-venue mileage.

    Home games always show ``distance_miles: 0`` (no travel). Away games resolve to an explicit
    venue on record, else fall back to the opponent's home venue (same campus-coordinate fallback
    as ``load_home_venues``). Neutral games only get a distance when the game has an explicit venue
    on record — no team's campus is a reasonable stand-in for a true neutral site — except the
    championship game, whose venue is resolved from the season/class's known championship venue.
    ``championship_distance_miles`` is computed the same way, independent of whether *team* has
    actually reached (or is scheduled for) the championship game. Regular-season games have
    ``round: null``.
    """
    async with get_conn() as conn:
        clazz_row = await (
            await conn.execute("SELECT class FROM school_seasons WHERE school = %s AND season = %s", (team, season))
        ).fetchone()
        if clazz_row is None:
            raise HTTPException(status_code=404, detail=f"Team '{team}' not found for season {season}")
        clazz = clazz_row[0]

        venues = await load_home_venues(conn)
        team_venue = venues.get(team)

        game_rows = await conn.execute(
            """
            SELECT g.round, g.date, g.opponent, g.location,
                   COALESCE(l.name, cvl.name), COALESCE(l.city, cvl.city),
                   COALESCE(l.latitude, cvl.latitude), COALESCE(l.longitude, cvl.longitude)
            FROM games_effective g
            JOIN school_seasons ss ON ss.school = g.school AND ss.season = g.season
            LEFT JOIN locations l ON g.location_id = l.id
            LEFT JOIN championship_venues cv
              ON g.round = 'Championship Game' AND cv.season = g.season AND cv.class = ss.class
            LEFT JOIN locations cvl ON cvl.id = cv.location_id
            WHERE g.school = %s AND g.season = %s
            ORDER BY g.date
            """,
            (team, season),
        )

        games, total_miles = build_roadmap_games([r async for r in game_rows], team_venue, venues)

        championship_venue = await load_championship_venue(conn, season, clazz)

    return RoadmapResponse(
        school=team,
        season=season,
        games=games,
        total_miles=total_miles,
        championship_distance_miles=venue_distance_miles(team_venue, championship_venue),
    )


@router.get("/helmets")
async def list_helmets(
    team: Annotated[str | None, Query()] = None,
    color: Annotated[str | None, Query()] = None,
    finish: Annotated[str | None, Query()] = None,
    tag: Annotated[str | None, Query()] = None,
    sort: Annotated[Literal["created_at"] | None, Query()] = None,
) -> list[HelmetListItemModel]:
    """Return helmet designs across all teams with optional filters, badged with
    a win/loss ``stats`` object (games with an explicit assignment only —
    never inferred). ``sort=created_at`` orders newest-added first; otherwise
    ordered by school, then year introduced."""
    conditions: list[LiteralString] = []
    params: list = []
    if team is not None:
        conditions.append("hd.school = %s")
        params.append(team)
    if color is not None:
        conditions.append("hd.color ILIKE %s")
        params.append(color)
    if finish is not None:
        conditions.append("hd.finish ILIKE %s")
        params.append(finish)
    if tag is not None:
        conditions.append("%s = ANY(hd.tags)")
        params.append(tag)

    order_by = "hd.created_at DESC" if sort == "created_at" else "hd.school, hd.year_first_worn"
    if conditions:
        where_clause = and_join_conditions(conditions)
        query = sql.SQL(HELMET_STATS_SELECT + " WHERE {} ORDER BY " + order_by).format(where_clause)
    else:
        query = sql.SQL(HELMET_STATS_SELECT + " ORDER BY " + order_by)

    async with get_conn() as conn:
        rows = await conn.execute(query, params)
        return [HelmetListItemModel(**build_helmet_stats_fields(*r)) async for r in rows]


@router.get("/helmets/{design_id}", responses=_404)
async def get_helmet_detail(design_id: int) -> HelmetDetailModel:
    """Return a single helmet design with full stats and the games it was worn in.

    Stats count only games with an explicit ``helmet_design_id`` assignment —
    games where the design would merely be inferred as the team's primary are
    never counted. ``games_played`` is the school's total final games across
    the seasons this design spans (see ``helmet_covers_season``), so the UI
    can render e.g. "6–1 in 7 tracked games (of 11 played)"."""
    async with get_conn() as conn:
        row = await (await conn.execute(HELMET_STATS_SELECT + " WHERE hd.id = %s", (design_id,))).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Helmet design {design_id} not found")

        games_rows = await conn.execute(
            """
            SELECT school, date, opponent, points_for, points_against, result, round
            FROM games_effective
            WHERE helmet_design_id = %s
            ORDER BY date
            """,
            (design_id,),
        )
        games_worn = [build_helmet_game_worn(r) async for r in games_rows]

    return HelmetDetailModel(**build_helmet_stats_fields(*row), games_worn=games_worn)


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
