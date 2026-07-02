"""Playoff hosting odds endpoints."""

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request

from backend.api.db import get_conn
from backend.api.limiter import limiter
from backend.api.models.requests import SimulateRegionRequest
from backend.api.models.responses import HostingResponse
from backend.helpers.api_helpers import (
    build_hosting_entries,
    parse_completed_games,
    results_to_applied,
)
from backend.helpers.data_classes import FormatSlot, StandingsOdds
from backend.helpers.scenario_updater import apply_region_game_results

router = APIRouter(prefix="/api/v1", tags=["hosting"])

SeasonQ = Annotated[int, Query(ge=1980, le=2040)]
ClazzPath = Annotated[int, Path(ge=1, le=7)]
RegionPath = Annotated[int, Path(ge=1, le=8)]
_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


async def _load_format_slots(conn, season: int, clazz: int) -> list[FormatSlot]:
    """Return all playoff format slots for *clazz* in *season*."""
    rows = await conn.execute(
        """
        SELECT pfs.slot, pfs.home_region, pfs.home_seed,
               pfs.away_region, pfs.away_seed, pfs.north_south
        FROM playoff_format_slots pfs
        JOIN playoff_formats pf ON pfs.format_id = pf.id
        WHERE pf.season = %s AND pf.class = %s
        ORDER BY pfs.slot
        """,
        (season, clazz),
    )
    return [
        FormatSlot(slot=r[0], home_region=r[1], home_seed=r[2], away_region=r[3], away_seed=r[4], north_south=r[5])
        async for r in rows
    ]


async def _load_region_odds(
    conn, season: int, clazz: int, region: int, as_of: date
) -> tuple[
    dict[str, StandingsOdds],
    dict[str, tuple[float, float, float, float]],   # home_cond (r1, r2, qf, sf)
    dict[str, tuple[float, float, float, float]],   # home_cond_w (r1, r2, qf, sf)
    dict[str, tuple[float, float, float, float]],   # adv (r1=p_playoffs, r2, qf, sf)
    dict[str, tuple[float, float, float, float]],   # adv_w
] | None:
    """Load per-team seeding odds, home conditionals, and bracket advancement from the most recent snapshot."""
    rows = await conn.execute(
        """
        SELECT DISTINCT ON (school)
            school, odds_1st, odds_2nd, odds_3rd, odds_4th, odds_playoffs,
            odds_playoffs, clinched, eliminated,
            odds_first_round_home, odds_second_round_home,
            odds_quarterfinals_home, odds_semifinals_home,
            odds_first_round_home_weighted, odds_second_round_home_weighted,
            odds_quarterfinals_home_weighted, odds_semifinals_home_weighted,
            odds_playoffs, odds_second_round, odds_quarterfinals, odds_semifinals,
            odds_playoffs_weighted, odds_second_round_weighted,
            odds_quarterfinals_weighted, odds_semifinals_weighted
        FROM region_standings
        WHERE season = %s AND class = %s AND region = %s AND as_of_date <= %s
        ORDER BY school, as_of_date DESC
        """,
        (season, clazz, region, as_of),
    )
    result: dict[str, StandingsOdds] = {}
    home_cond: dict[str, tuple[float, float, float, float]] = {}
    home_cond_w: dict[str, tuple[float, float, float, float]] = {}
    adv: dict[str, tuple[float, float, float, float]] = {}
    adv_w: dict[str, tuple[float, float, float, float]] = {}
    async for r in rows:
        result[r[0]] = StandingsOdds(
            school=r[0],
            p1=r[1],
            p2=r[2],
            p3=r[3],
            p4=r[4],
            p_playoffs=r[5],
            final_playoffs=r[6],
            clinched=r[7],
            eliminated=r[8],
        )
        home_cond[r[0]] = (r[9], r[10], r[11], r[12])    # r1, r2, qf, sf conditionals
        home_cond_w[r[0]] = (r[13], r[14], r[15], r[16]) # weighted
        adv[r[0]] = (r[17], r[18], r[19], r[20])          # p_playoffs, r2, qf, sf advancement
        adv_w[r[0]] = (r[21], r[22], r[23], r[24])        # weighted advancement
    return (result, home_cond, home_cond_w, adv, adv_w) if result else None


@router.get("/hosting/{clazz}/{region}", responses=_404)
async def get_hosting(
    clazz: ClazzPath,
    region: RegionPath,
    season: SeasonQ,
    date: Annotated[date | None, Query()] = None,
) -> HostingResponse:
    """Return playoff hosting odds per round for all teams in *clazz*A Region *region*."""
    as_of = date or datetime.now().date()
    async with get_conn() as conn:
        loaded = await _load_region_odds(conn, season, clazz, region, as_of)
        if loaded is None:
            raise HTTPException(status_code=404, detail=f"No data for {clazz}A Region {region} season {season}")
        region_odds, home_cond, home_cond_w, stored_adv, stored_adv_w = loaded
        slots = await _load_format_slots(conn, season, clazz)
        if not slots:
            raise HTTPException(status_code=404, detail=f"No playoff format found for {clazz}A season {season}")

    entries = build_hosting_entries(
        region_odds, slots, region, season, clazz,
        home_cond=home_cond,
        home_cond_w=home_cond_w,
        stored_adv=stored_adv,
        stored_adv_w=stored_adv_w,
    )
    return HostingResponse(season=season, class_=clazz, region=region, as_of_date=as_of, teams=entries)


@router.get("/hosting/{clazz}/{region}/teams/{team}", responses=_404)
async def get_team_hosting(
    clazz: ClazzPath,
    region: RegionPath,
    team: str,
    season: SeasonQ,
    date: Annotated[date | None, Query()] = None,
) -> HostingResponse:
    """Return hosting odds for a single *team*."""
    response = await get_hosting(clazz, region, season=season, date=date)
    response.teams = [t for t in response.teams if t.school == team]
    if not response.teams:
        raise HTTPException(status_code=404, detail=f"Team '{team}' not found in {clazz}A Region {region}")
    return response


@router.post("/hosting/{clazz}/{region}/simulate", responses=_404)
@limiter.limit("10/minute")
async def simulate_hosting(
    request: Request,
    clazz: ClazzPath,
    region: RegionPath,
    body: SimulateRegionRequest,
    season: SeasonQ,
    date: Annotated[date | None, Query()] = None,
) -> HostingResponse:
    """Apply hypothetical game results and return updated hosting odds."""
    from backend.api.routers.standings import _load_scenarios_snapshot, _recompute_from_games

    as_of = date or datetime.now().date()
    async with get_conn() as conn:
        slots = await _load_format_slots(conn, season, clazz)
        if not slots:
            raise HTTPException(status_code=404, detail=f"No playoff format found for {clazz}A season {season}")

        scenarios_data = await _load_scenarios_snapshot(conn, season, clazz, region, as_of)
        if scenarios_data is not None:
            remaining, _, _, _ = scenarios_data
        else:
            _, _, remaining, _, _ = await _recompute_from_games(conn, season, clazz, region, as_of)

        team_rows = await conn.execute(
            "SELECT school FROM school_seasons WHERE season=%s AND class=%s AND region=%s AND is_active=TRUE ORDER BY school",
            (season, clazz, region),
        )
        teams = [r[0] async for r in team_rows]

        game_rows = await conn.execute(
            """
            SELECT school, opponent, points_for, points_against, date
            FROM games_effective
            WHERE season=%s AND region_game=TRUE AND final=TRUE AND date<=%s AND school=ANY(%s)
            ORDER BY date
            """,
            (season, as_of, teams),
        )
        completed = parse_completed_games([r async for r in game_rows])
        new_results = results_to_applied(body.results)
        _, odds_map = apply_region_game_results(teams, completed, remaining, new_results)

    entries = build_hosting_entries(odds_map, slots, region, season, clazz)
    return HostingResponse(season=season, class_=clazz, region=region, as_of_date=as_of, teams=entries)


@router.post("/hosting/{clazz}/{region}/teams/{team}/simulate", responses=_404)
@limiter.limit("10/minute")
async def simulate_team_hosting(
    request: Request,
    clazz: ClazzPath,
    region: RegionPath,
    team: str,
    body: SimulateRegionRequest,
    season: SeasonQ,
    date: Annotated[date | None, Query()] = None,
) -> HostingResponse:
    """What-if hosting odds for a single *team*."""
    response = await simulate_hosting(request, clazz, region, body, season=season, date=date)
    response.teams = [t for t in response.teams if t.school == team]
    if not response.teams:
        raise HTTPException(status_code=404, detail=f"Team '{team}' not found in {clazz}A Region {region}")
    return response
