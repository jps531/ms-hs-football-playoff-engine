"""Game schedule and win probability endpoints."""

from datetime import date, datetime
from typing import Annotated, Any, LiteralString

from fastapi import APIRouter, HTTPException, Query
from psycopg import sql

from backend.api.db import get_conn
from backend.api.models.requests import LiveWinProbRequest, OTWinProbRequest
from backend.api.models.responses import (
    GameModel,
    HelmetDesignModel,
    LiveWinProbResponse,
    OTWinProbResponse,
    PreGameWinProbResponse,
    VenueModel,
)
from backend.helpers.win_probability import EloConfig, compute_in_game_win_prob, compute_ot_win_prob

router = APIRouter(prefix="/api/v1", tags=["games"])

SeasonQ = Annotated[int, Query()]
_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}

_HELMET_COLS = (
    "id", "school", "year_first_worn", "year_last_worn", "years_worn",
    "image_left", "image_right", "photo", "color", "finish",
    "facemask_color", "logo", "stripe", "tags", "notes",
)


def _today() -> date:
    """Return today's date (injectable seam for tests)."""
    return datetime.now().date()


def _build_helmet(*fields) -> HelmetDesignModel | None:
    """Build a HelmetDesignModel from a flat sequence of helmet_designs columns.

    Expects fields in the same order as ``_HELMET_COLS``. Returns None when
    the first field (id) is None, which indicates no helmet has been designated
    for this team in this game.
    """
    hid = fields[0]
    if hid is None:
        return None
    return HelmetDesignModel(**dict(zip(_HELMET_COLS, fields)))


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
               l.name, l.city, l.latitude, l.longitude,
               hd_a.id, hd_a.school, hd_a.year_first_worn, hd_a.year_last_worn, hd_a.years_worn,
               hd_a.image_left, hd_a.image_right, hd_a.photo, hd_a.color, hd_a.finish,
               hd_a.facemask_color, hd_a.logo, hd_a.stripe, hd_a.tags, hd_a.notes,
               hd_b.id, hd_b.school, hd_b.year_first_worn, hd_b.year_last_worn, hd_b.years_worn,
               hd_b.image_left, hd_b.image_right, hd_b.photo, hd_b.color, hd_b.finish,
               hd_b.facemask_color, hd_b.logo, hd_b.stripe, hd_b.tags, hd_b.notes
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
        rows = await conn.execute(query, params)
        seen_pairs: set[frozenset] = set()
        games: list[GameModel] = []
        async for (
            school, opponent, game_date, pf, pa, location, region_game, status, gseason,
            v_name, v_city, v_lat, v_lon,
            *ha_fields_then_hb,
        ) in rows:
            ha_fields = tuple(ha_fields_then_hb[:15])
            hb_fields = tuple(ha_fields_then_hb[15:])
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
                    ha_fields, hb_fields = hb_fields, ha_fields
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
                    helmet_a=_build_helmet(*ha_fields),
                    helmet_b=_build_helmet(*hb_fields),
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
