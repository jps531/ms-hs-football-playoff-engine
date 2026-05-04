"""Elo ratings and RPI endpoints."""

from datetime import date
from typing import Annotated, Any, LiteralString

from fastapi import APIRouter, HTTPException, Query
from psycopg import sql

from backend.api.db import get_conn
from backend.api.models.responses import EloSnapshot, EloTrendResponse, TeamRatingModel

router = APIRouter(prefix="/api/v1", tags=["ratings"])

SeasonQ = Annotated[int, Query(ge=2020, le=2040)]
_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


@router.get("/ratings")
async def list_ratings(
    season: SeasonQ,
    class_: Annotated[int | None, Query(alias="class", ge=1, le=7)] = None,
    region: Annotated[int | None, Query(ge=1, le=8)] = None,
    team: Annotated[str | None, Query()] = None,
) -> list[TeamRatingModel]:
    """Return current Elo and RPI for teams matching the given filters."""
    conditions: list[LiteralString] = ["tr.season = %s"]
    params: list = [season]
    if class_ is not None:
        conditions.append("ss.class = %s")
        params.append(class_)
    if region is not None:
        conditions.append("ss.region = %s")
        params.append(region)
    if team is not None:
        conditions.append("tr.school = %s")
        params.append(team)

    where_clause = sql.SQL(" AND ").join(sql.SQL(c) for c in conditions)
    query = sql.SQL("""
        SELECT tr.school, tr.season, tr.elo, tr.rpi
        FROM team_ratings tr
        JOIN school_seasons ss ON tr.school = ss.school AND tr.season = ss.season
        WHERE {}
        ORDER BY tr.elo DESC
    """).format(where_clause)
    async with get_conn() as conn:
        rows = await conn.execute(query, params)
        return [TeamRatingModel(school=r[0], season=r[1], elo=r[2], rpi=r[3]) async for r in rows]


@router.get("/ratings/{team}/trend", responses=_404)
async def elo_trend(
    team: str,
    season: SeasonQ,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> EloTrendResponse:
    """Return the Elo time-series for *team* in *season*.

    Reads pre-computed per-pipeline-run snapshots from ``team_ratings`` (one row
    per school per run date).  Optional ``date_from``/``date_to`` filter the
    returned snapshots.  Returns an empty list if no pipeline has run yet.
    """
    async with get_conn() as conn:
        exists = await (
            await conn.execute(
                "SELECT 1 FROM school_seasons WHERE school = %s AND season = %s",
                (team, season),
            )
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail=f"Team '{team}' not found for season {season}")

        rows = await conn.execute(
            """
            SELECT as_of_date, elo, rpi
            FROM team_ratings
            WHERE school = %s AND season = %s
            ORDER BY as_of_date
            """,
            (team, season),
        )
        result_snapshots: list[EloSnapshot] = []
        async for snap_date, elo, rpi in rows:
            if date_from and snap_date < date_from:
                continue
            if date_to and snap_date > date_to:
                continue
            result_snapshots.append(EloSnapshot(date=snap_date, elo=elo, rpi=rpi))

    return EloTrendResponse(school=team, season=season, snapshots=result_snapshots)
