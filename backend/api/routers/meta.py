"""Navigation and metadata endpoints: seasons, structure, teams."""

from typing import Annotated, Any, LiteralString

from fastapi import APIRouter, HTTPException, Query
from psycopg import sql

from backend.api.db import get_conn
from backend.api.models.responses import (
    ClassStructure,
    RegionSummary,
    SeasonModel,
    SeasonStructureResponse,
    TeamModel,
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
        SELECT s.school, ss.season, ss.class, ss.region,
               s.city, s.mascot, s.primary_color, s.secondary_color, s.maxpreps_logo
        FROM schools s
        JOIN school_seasons ss ON s.school = ss.school
        WHERE {}
        ORDER BY ss.class, ss.region, s.school
    """).format(where_clause)
    async with get_conn() as conn:
        rows = await conn.execute(query, params)
        return [
            TeamModel(
                school=r[0],
                season=r[1],
                class_=r[2],
                region=r[3],
                city=r[4] or "",
                mascot=r[5] or "",
                primary_color=r[6] or "",
                secondary_color=r[7] or "",
                maxpreps_logo=r[8] or "",
            )
            async for r in rows
        ]


@router.get("/teams/{team}", responses=_404)
async def get_team(team: str, season: Annotated[int, Query()]) -> TeamModel:
    """Return metadata for a single *team* in *season*."""
    async with get_conn() as conn:
        row = await conn.execute(
            """
            SELECT s.school, ss.season, ss.class, ss.region,
                   s.city, s.mascot, s.primary_color, s.secondary_color, s.maxpreps_logo
            FROM schools s
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
        season=r[1],
        class_=r[2],
        region=r[3],
        city=r[4] or "",
        mascot=r[5] or "",
        primary_color=r[6] or "",
        secondary_color=r[7] or "",
        maxpreps_logo=r[8] or "",
    )
