"""Game schedule and win probability endpoints."""

from datetime import date, datetime
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
    VenueModel,
)
from backend.helpers.win_probability import EloConfig, compute_in_game_win_prob, compute_ot_win_prob

router = APIRouter(prefix="/api/v1", tags=["games"])

SeasonQ = Annotated[int, Query()]
_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


def _today() -> date:
    """Return today's date (injectable seam for tests)."""
    return datetime.now().date()


@router.get("/games")
async def list_games(
    season: SeasonQ,
    class_: Annotated[int | None, Query(alias="class")] = None,
    region: Annotated[int | None, Query()] = None,
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

    where_clause = sql.SQL(" AND ").join(sql.SQL(c) for c in conditions)
    query = sql.SQL("""
        SELECT g.school, g.opponent, g.date, g.points_for, g.points_against,
               g.location, g.region_game, g.game_status, g.season,
               l.name, l.city, l.latitude, l.longitude
        FROM games_effective g
        JOIN school_seasons ss ON g.school = ss.school AND g.season = ss.season
        LEFT JOIN locations l ON g.location_id = l.id
        WHERE {}
        ORDER BY g.date, g.school
    """).format(where_clause)
    async with get_conn() as conn:
        rows = await conn.execute(query, params)
        seen_pairs: set[frozenset] = set()
        games: list[GameModel] = []
        async for (
            school,
            opponent,
            game_date,
            pf,
            pa,
            location,
            region_game,
            status,
            gseason,
            v_name,
            v_city,
            v_lat,
            v_lon,
        ) in rows:
            # De-duplicate symmetric game pairs when not team-filtered
            if team is None:
                pair = frozenset([school, opponent])
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                if school > opponent:
                    school, opponent = opponent, school
                    pf, pa = pa, pf
                    location = {"home": "away", "away": "home"}.get(location, location)
            venue = VenueModel(name=v_name, city=v_city, latitude=v_lat, longitude=v_lon) if v_name else None
            games.append(
                GameModel(
                    season=gseason,
                    date=game_date,
                    team_a=school,
                    team_b=opponent,
                    score_a=pf,
                    score_b=pa,
                    location_a=location,
                    is_region_game=region_game,
                    status=status,
                    venue=venue,
                )
            )
    return games


@router.get("/games/probability", responses=_404)
async def pregame_win_probability(
    team_a: Annotated[str, Query()],
    team_b: Annotated[str, Query()],
    season: SeasonQ,
    location: Annotated[str | None, Query()] = None,
) -> PreGameWinProbResponse:
    """Return pre-game win probability using Elo ratings stored for *season*.

    ``location`` should be ``"home"``, ``"away"``, or ``"neutral"`` from *team_a*'s perspective.
    Omit for a neutral-site game.
    """
    async with get_conn() as conn:
        row_a = await (
            await conn.execute(
                "SELECT elo FROM team_ratings WHERE school = %s AND season = %s",
                (team_a, season),
            )
        ).fetchone()
        row_b = await (
            await conn.execute(
                "SELECT elo FROM team_ratings WHERE school = %s AND season = %s",
                (team_b, season),
            )
        ).fetchone()

    if row_a is None:
        raise HTTPException(status_code=404, detail=f"No Elo rating for '{team_a}' in season {season}")
    if row_b is None:
        raise HTTPException(status_code=404, detail=f"No Elo rating for '{team_b}' in season {season}")

    cfg = EloConfig()
    elo_a = row_a[0]
    elo_b = row_b[0]
    if location == "home":
        hfa = cfg.hfa_points
    elif location == "away":
        hfa = -cfg.hfa_points
    else:
        hfa = 0.0
    p = 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a - hfa) / cfg.scale))

    return PreGameWinProbResponse(
        team_a=team_a,
        team_b=team_b,
        elo_a=elo_a,
        elo_b=elo_b,
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
