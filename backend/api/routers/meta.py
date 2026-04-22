"""Navigation and metadata endpoints: seasons, structure, teams."""

from fastapi import APIRouter, HTTPException, Query

from backend.api.db import get_conn
from backend.api.models.responses import (
    ClassStructure,
    RegionSummary,
    SeasonModel,
    SeasonStructureResponse,
    TeamModel,
)

router = APIRouter(prefix="/api/v1", tags=["meta"])


@router.get("/seasons", response_model=list[SeasonModel])
async def list_seasons() -> list[SeasonModel]:
    """Return all seasons that have at least one school enrolled."""
    async with get_conn() as conn:
        rows = await conn.execute(
            "SELECT DISTINCT season FROM school_seasons ORDER BY season DESC"
        )
        return [SeasonModel(season=r[0]) async for r in rows]


@router.get("/seasons/{season}/structure", response_model=SeasonStructureResponse)
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


@router.get("/teams", response_model=list[TeamModel])
async def list_teams(
    season: int = Query(...),
    class_: int | None = Query(None, alias="class"),
    region: int | None = Query(None),
) -> list[TeamModel]:
    """Return teams for *season*, optionally filtered by class and region."""
    conditions = ["ss.season = %s"]
    params: list = [season]
    if class_ is not None:
        conditions.append("ss.class = %s")
        params.append(class_)
    if region is not None:
        conditions.append("ss.region = %s")
        params.append(region)

    where = " AND ".join(conditions)
    query = f"""
        SELECT s.school, ss.season, ss.class, ss.region,
               s.city, s.mascot, s.primary_color, s.secondary_color, s.maxpreps_logo
        FROM schools s
        JOIN school_seasons ss ON s.school = ss.school
        WHERE {where}
        ORDER BY ss.class, ss.region, s.school
    """
    async with get_conn() as conn:
        rows = await conn.execute(query, params)
        return [
            TeamModel(
                school=r[0], season=r[1], class_=r[2], region=r[3],
                city=r[4] or "", mascot=r[5] or "", primary_color=r[6] or "",
                secondary_color=r[7] or "", maxpreps_logo=r[8] or "",
            )
            async for r in rows
        ]


@router.get("/teams/{team}", response_model=TeamModel)
async def get_team(team: str, season: int = Query(...)) -> TeamModel:
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
        school=r[0], season=r[1], class_=r[2], region=r[3],
        city=r[4] or "", mascot=r[5] or "", primary_color=r[6] or "",
        secondary_color=r[7] or "", maxpreps_logo=r[8] or "",
    )
