"""Navigation and metadata endpoints: seasons, structure, teams."""

from typing import Annotated, Any, LiteralString

from fastapi import APIRouter, HTTPException, Query
from psycopg import sql

from backend.api.db import get_conn
from backend.api.models.responses import (
    ClassStructure,
    HelmetDesignModel,
    RegionSummary,
    SeasonModel,
    SeasonStructureResponse,
    TeamModel,
    YearsWornRange,
)

router = APIRouter(prefix="/api/v1", tags=["meta"])
_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


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

    where_clause = sql.SQL(" AND ").join(sql.SQL(c) for c in conditions)
    query = sql.SQL("""
        SELECT s.school, s.display_name, ss.season, ss.class, ss.region,
               s.city, s.mascot, s.primary_color, s.secondary_color, s.maxpreps_logo,
               s.display_logo
        FROM schools_effective s
        JOIN school_seasons ss ON s.school = ss.school
        WHERE {}
        ORDER BY ss.class, ss.region, s.school
    """).format(where_clause)
    async with get_conn() as conn:
        rows = await conn.execute(query, params)
        return [
            TeamModel(
                school=r[0],
                display_name=r[1],
                season=r[2],
                class_=r[3],
                region=r[4],
                city=r[5] or "",
                mascot=r[6] or "",
                primary_color=r[7] or "",
                secondary_color=r[8] or "",
                maxpreps_logo=r[9] or "",
                display_logo=r[10] or "",
            )
            async for r in rows
        ]


@router.get("/teams/{team}", responses=_404)
async def get_team(team: str, season: Annotated[int, Query()]) -> TeamModel:
    """Return metadata for a single *team* in *season*."""
    async with get_conn() as conn:
        row = await conn.execute(
            """
            SELECT s.school, s.display_name, ss.season, ss.class, ss.region,
                   s.city, s.mascot, s.primary_color, s.secondary_color, s.maxpreps_logo,
                   s.display_logo
            FROM schools_effective s
            JOIN school_seasons ss ON s.school = ss.school
            WHERE s.school = %s AND ss.season = %s
            """,
            (team, season),
        )
        r = await row.fetchone()

    if r is None:
        raise HTTPException(status_code=404, detail=f"Team '{team}' not found for season {season}")

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
        maxpreps_logo=r[9] or "",
        display_logo=r[10] or "",
    )


def _row_to_helmet(r) -> HelmetDesignModel:
    years_worn = None
    if r[4] is not None:
        years_worn = [YearsWornRange(start=span["start"], end=span["end"]) for span in r[4]]
    return HelmetDesignModel(
        id=r[0],
        school=r[1],
        year_first_worn=r[2],
        year_last_worn=r[3],
        years_worn=years_worn,
        image_left=r[5],
        image_right=r[6],
        photo=r[7],
        color=r[8],
        finish=r[9],
        facemask_color=r[10],
        logo=r[11],
        stripe=r[12],
        tags=list(r[13] or []),
        notes=r[14],
    )


_HELMET_SELECT = """
    SELECT id, school, year_first_worn, year_last_worn, years_worn,
           image_left, image_right, photo, color, finish,
           facemask_color, logo, stripe, tags, notes
    FROM helmet_designs
"""


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

    where_clause = sql.SQL(" AND ").join(sql.SQL(c) for c in conditions)
    query = sql.SQL(_HELMET_SELECT + " WHERE {} ORDER BY year_first_worn").format(where_clause)

    async with get_conn() as conn:
        rows = await conn.execute(query, params)
        results = [_row_to_helmet(r) async for r in rows]

    if not results and year is None:
        async with get_conn() as conn:
            check = await conn.execute("SELECT 1 FROM schools WHERE school = %s", (team,))
            if await check.fetchone() is None:
                raise HTTPException(status_code=404, detail=f"Team '{team}' not found")

    return results


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
        where_clause = sql.SQL(" AND ").join(sql.SQL(c) for c in conditions)
        query = sql.SQL(_HELMET_SELECT + " WHERE {} ORDER BY school, year_first_worn").format(where_clause)
    else:
        query = sql.SQL(_HELMET_SELECT + " ORDER BY school, year_first_worn")

    async with get_conn() as conn:
        rows = await conn.execute(query, params)
        return [_row_to_helmet(r) async for r in rows]
