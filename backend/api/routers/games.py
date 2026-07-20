"""Game schedule and win probability endpoints."""

from datetime import date
from typing import Annotated, Any, LiteralString

from fastapi import APIRouter, HTTPException, Query
from psycopg import sql

from backend.api.db import get_conn
from backend.api.models.requests import LiveWinProbRequest, OTWinProbRequest
from backend.api.models.responses import (
    GameModel,
    LiveWinProbResponse,
    OTWinProbResponse,
    PreGameWinProbResponse,
)
from backend.helpers.api_helpers import build_game_models
from backend.helpers.query_helpers import and_join_conditions
from backend.helpers.win_probability import (
    EloConfig,
    compute_in_game_win_prob,
    compute_ot_win_prob,
    compute_pregame_win_prob,
)

router = APIRouter(prefix="/api/v1", tags=["games"])

SeasonQ = Annotated[int, Query(ge=1980, le=2040)]
_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


@router.get("/games")
async def list_games(
    season: SeasonQ,
    class_: Annotated[int | None, Query(alias="class", ge=1, le=7)] = None,
    region: Annotated[int | None, Query(ge=1, le=8)] = None,
    team: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> list[GameModel]:
    """Return games filtered by season, class, region, team, and/or date range.

    Each game appears once (from team_a's perspective). When a ``team`` filter
    is supplied, games are listed from that team's perspective.
    """
    # Build the base query joining back to school_seasons for class/region filters
    conditions: list[LiteralString] = ["g.season = %s"]
    params: list = [season]
    if class_ is not None:
        conditions.append("ss.class = %s")
        params.append(class_)
    if region is not None:
        conditions.append("ss.region = %s")
        params.append(region)
    if team is not None:
        conditions.append("g.school = %s")
        params.append(team)
    if date_from is not None:
        conditions.append("g.date >= %s")
        params.append(date_from)
    if date_to is not None:
        conditions.append("g.date <= %s")
        params.append(date_to)

    where_clause = and_join_conditions(conditions)
    query = sql.SQL("""
        SELECT g.school, g.opponent, g.date, g.points_for, g.points_against,
               g.location, g.region_game, g.game_status, g.season,
               l.name, l.city, l.latitude, l.longitude,
               hd_a.id, hd_a.school, hd_a.year_first_worn, hd_a.year_last_worn, hd_a.years_worn,
               hd_a.image_left, hd_a.image_right, hd_a.photo, hd_a.color, hd_a.finish,
               hd_a.facemask_color, hd_a.logo, hd_a.stripe, hd_a.tags, hd_a.notes,
               hd_b.id, hd_b.school, hd_b.year_first_worn, hd_b.year_last_worn, hd_b.years_worn,
               hd_b.image_left, hd_b.image_right, hd_b.photo, hd_b.color, hd_b.finish,
               hd_b.facemask_color, hd_b.logo, hd_b.stripe, hd_b.tags, hd_b.notes,
               g.round, g.kickoff_time, g.overtime, g.final,
               g.game_quarter, g.game_clock, g.source
        FROM games_effective g
        JOIN school_seasons ss ON g.school = ss.school AND g.season = ss.season
        LEFT JOIN locations l ON g.location_id = l.id
        LEFT JOIN helmet_designs hd_a ON hd_a.id = g.helmet_design_id
        LEFT JOIN games_effective g_opp
          ON g_opp.school = g.opponent AND g_opp.date = g.date AND g_opp.season = g.season
        LEFT JOIN helmet_designs hd_b ON hd_b.id = g_opp.helmet_design_id
        WHERE {}
        ORDER BY g.date, g.school
    """).format(where_clause)
    async with get_conn() as conn:
        rows = [r async for r in await conn.execute(query, params)]
    return build_game_models(rows, team_filter=team)


@router.get("/games/probability", responses=_404)
async def pregame_win_probability(
    team_a: Annotated[str, Query()],
    team_b: Annotated[str, Query()],
    season: SeasonQ,
    location: Annotated[str | None, Query()] = None,
    as_of: Annotated[date | None, Query(description="Use Elo ratings as of this date. Defaults to the latest available.")] = None,
) -> PreGameWinProbResponse:
    """Return pre-game win probability using Elo ratings stored for *season*.

    ``location`` should be ``"home"``, ``"away"``, or ``"neutral"`` from *team_a*'s perspective.
    Omit for a neutral-site game.

    ``as_of`` pins both teams' ratings to the most recent snapshot on or before
    that date, so you can compare the same matchup at different points in the
    season.  Omit to use the latest stored rating.
    """
    _sql = """
        SELECT elo, as_of_date FROM team_ratings
        WHERE school = %s AND season = %s {date_filter}
        ORDER BY as_of_date DESC LIMIT 1
    """
    if as_of is not None:
        query = _sql.format(date_filter="AND as_of_date <= %s")
        params_a = (team_a, season, as_of)
        params_b = (team_b, season, as_of)
    else:
        query = _sql.format(date_filter="")
        params_a = (team_a, season)
        params_b = (team_b, season)

    async with get_conn() as conn:
        row_a = await (await conn.execute(query, params_a)).fetchone()
        row_b = await (await conn.execute(query, params_b)).fetchone()

    if row_a is None:
        detail = f"No Elo rating for '{team_a}' in season {season}"
        if as_of:
            detail += f" on or before {as_of}"
        raise HTTPException(status_code=404, detail=detail)
    if row_b is None:
        detail = f"No Elo rating for '{team_b}' in season {season}"
        if as_of:
            detail += f" on or before {as_of}"
        raise HTTPException(status_code=404, detail=detail)

    cfg = EloConfig()
    elo_a, elo_date_a = row_a
    elo_b, elo_date_b = row_b
    if location == "home":
        hfa = cfg.hfa_points
    elif location == "away":
        hfa = -cfg.hfa_points
    else:
        hfa = 0.0
    p = compute_pregame_win_prob(elo_a, elo_b, location, cfg)

    return PreGameWinProbResponse(
        team_a=team_a,
        team_b=team_b,
        elo_a=elo_a,
        elo_b=elo_b,
        elo_date_a=elo_date_a,
        elo_date_b=elo_date_b,
        location_a=location,
        hfa_adjustment=hfa,
        p_team_a=p,
    )


@router.post("/games/probability/live")
async def live_win_probability(body: LiveWinProbRequest) -> LiveWinProbResponse:
    """Return in-game win probability (regulation) given current game state."""
    p = compute_in_game_win_prob(body.pregame_prob, body.current_margin, body.seconds_remaining)
    return LiveWinProbResponse(p_team_a=p)


@router.post("/games/probability/overtime")
async def ot_win_probability(body: OTWinProbRequest) -> OTWinProbResponse:
    """Return OT win probability after team A's possession, before team B responds."""
    p = compute_ot_win_prob(body.pregame_prob, body.ot_scored_margin)
    return OTWinProbResponse(p_team_a=p)
