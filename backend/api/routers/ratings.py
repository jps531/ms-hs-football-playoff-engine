"""Elo ratings and RPI endpoints."""

from datetime import date
from typing import Annotated, Any, LiteralString

from fastapi import APIRouter, HTTPException, Query
from psycopg import sql

from backend.api.db import get_conn
from backend.api.models.responses import EloSnapshot, EloTrendResponse, MoversResponse, TeamRatingModel
from backend.helpers.api_helpers import build_movers_response
from backend.helpers.query_helpers import and_join_conditions, append_optional_filters

router = APIRouter(prefix="/api/v1", tags=["ratings"])

SeasonQ = Annotated[int, Query(ge=1980, le=2040)]
_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


@router.get("/ratings")
async def list_ratings(
    season: SeasonQ,
    class_: Annotated[int | None, Query(alias="class", ge=1, le=7)] = None,
    region: Annotated[int | None, Query(ge=1, le=8)] = None,
    team: Annotated[str | None, Query()] = None,
    date: Annotated[date | None, Query()] = None,
) -> list[TeamRatingModel]:
    """Return Elo and RPI for teams matching the given filters.

    Without ``date``, returns all stored snapshots for the season (one row per
    school per pipeline run), sorted by Elo descending.  With ``date``, returns
    one row per school — the most recent snapshot on or before that date —
    also sorted by Elo descending.
    """
    conditions: list[LiteralString] = ["tr.season = %s"]
    params: list = [season]
    append_optional_filters(
        conditions, params, ("ss.class = %s", class_), ("ss.region = %s", region), ("tr.school = %s", team)
    )

    where_clause = and_join_conditions(conditions)

    if date is not None:
        params.append(date)
        query = sql.SQL("""
            SELECT * FROM (
                SELECT DISTINCT ON (tr.school)
                    tr.school, tr.season, tr.elo, tr.rpi, tr.as_of_date, tr.games_played, tr.computed_at
                FROM team_ratings tr
                JOIN school_seasons ss ON tr.school = ss.school AND tr.season = ss.season
                WHERE {} AND tr.as_of_date <= %s
                ORDER BY tr.school, tr.as_of_date DESC
            ) latest
            ORDER BY elo DESC
        """).format(where_clause)
    else:
        query = sql.SQL("""
            SELECT tr.school, tr.season, tr.elo, tr.rpi, tr.as_of_date, tr.games_played, tr.computed_at
            FROM team_ratings tr
            JOIN school_seasons ss ON tr.school = ss.school AND tr.season = ss.season
            WHERE {}
            ORDER BY tr.elo DESC
        """).format(where_clause)

    async with get_conn() as conn:
        rows = await conn.execute(query, params)
        return [
            TeamRatingModel(
                school=r[0], season=r[1], elo=r[2], rpi=r[3],
                as_of_date=r[4], games_played=r[5], computed_at=r[6],
            )
            async for r in rows
        ]


async def _resolve_mover_snapshot_dates(
    conn, season: int, date_from: date | None, date_to: date | None
) -> tuple[date, date] | None:
    """Resolve the (before, after) snapshot dates for GET /ratings/movers.

    Both given: used as-is. Only ``date_to``: pairs it with the snapshot
    immediately before it. Only ``date_from``: pairs it with the latest
    snapshot overall. Neither: the two most recent snapshot dates for the
    season. Returns None when fewer than two snapshots are available for
    whichever of these is requested.
    """
    if date_from is not None and date_to is not None:
        return date_from, date_to
    if date_from is not None:
        latest = await (
            await conn.execute("SELECT MAX(as_of_date) FROM team_ratings WHERE season = %s", (season,))
        ).fetchone()
        if latest is None or latest[0] is None:
            return None
        return date_from, latest[0]

    query = "SELECT DISTINCT as_of_date FROM team_ratings WHERE season = %s"
    params: list = [season]
    if date_to is not None:
        query += " AND as_of_date <= %s"
        params.append(date_to)
    query += " ORDER BY as_of_date DESC LIMIT 2"
    rows = await conn.execute(query, params)
    dates = [r[0] async for r in rows]
    return (dates[1], dates[0]) if len(dates) == 2 else None


@router.get("/ratings/movers")
async def ratings_movers(
    season: SeasonQ,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> MoversResponse:
    """Return the biggest Elo risers/fallers between two rating snapshots.

    Without ``date_from``/``date_to``, defaults to the two most recent
    snapshot dates for the season. Teams present in only one snapshot are
    excluded.
    """
    async with get_conn() as conn:
        target_dates = await _resolve_mover_snapshot_dates(conn, season, date_from, date_to)
        if target_dates is None:
            return MoversResponse(risers=[], fallers=[])
        before_target, after_target = target_dates

        rows = await conn.execute(
            """
            WITH before_snap AS (
                SELECT DISTINCT ON (tr.school) tr.school, tr.elo AS elo_before
                FROM team_ratings tr
                WHERE tr.season = %s AND tr.as_of_date <= %s
                ORDER BY tr.school, tr.as_of_date DESC
            ),
            after_snap AS (
                SELECT DISTINCT ON (tr.school) tr.school, tr.elo AS elo_after
                FROM team_ratings tr
                WHERE tr.season = %s AND tr.as_of_date <= %s
                ORDER BY tr.school, tr.as_of_date DESC
            )
            SELECT b.school, ss.class, ss.region, b.elo_before, a.elo_after
            FROM before_snap b
            JOIN after_snap a ON a.school = b.school
            JOIN school_seasons ss ON ss.school = b.school AND ss.season = %s
            """,
            (season, before_target, season, after_target, season),
        )
        mover_rows = [r async for r in rows]
    return build_movers_response(mover_rows, limit)


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
