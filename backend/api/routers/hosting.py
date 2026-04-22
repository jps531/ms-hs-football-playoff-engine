"""Playoff hosting odds endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from backend.api.db import get_conn
from backend.api.models.requests import SimulateRegionRequest
from backend.api.models.responses import (
    HostingResponse,
    RoundHostingOdds,
    TeamHostingEntry,
)
from backend.helpers.bracket_home_odds import (
    compute_bracket_advancement_odds,
    compute_quarterfinal_home_odds,
    compute_second_round_home_odds,
    compute_semifinal_home_odds,
    marginal_home_odds,
)
from backend.helpers.data_classes import FormatSlot, StandingsOdds

router = APIRouter(prefix="/api/v1", tags=["hosting"])

SeasonQ = Annotated[int, Query()]
_404 = {404: {"description": "Not found"}}


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


async def _load_region_odds(conn, season: int, clazz: int, region: int, as_of: date) -> dict[str, StandingsOdds] | None:
    """Return StandingsOdds per team from the most recent snapshot on or before *as_of*."""
    rows = await conn.execute(
        """
        SELECT DISTINCT ON (school)
            school, odds_1st, odds_2nd, odds_3rd, odds_4th, odds_playoffs,
            odds_playoffs, clinched, eliminated
        FROM region_standings
        WHERE season = %s AND class = %s AND region = %s AND as_of_date <= %s
        ORDER BY school, as_of_date DESC
        """,
        (season, clazz, region, as_of),
    )
    result: dict[str, StandingsOdds] = {}
    async for r in rows:
        result[r[0]] = StandingsOdds(
            school=r[0], p1=r[1], p2=r[2], p3=r[3], p4=r[4],
            p_playoffs=r[5], final_playoffs=r[6],
            clinched=r[7], eliminated=r[8],
        )
    return result if result else None


def _build_hosting_entries(
    region_odds: dict[str, StandingsOdds],
    slots: list[FormatSlot],
    region: int,
    season: int,
    clazz: int,
) -> list[TeamHostingEntry]:
    """Compute per-round hosting odds for all teams in the region."""
    is_1a_4a = clazz <= 4
    adv_odds = compute_bracket_advancement_odds(region, region_odds, slots)
    qf_home = compute_quarterfinal_home_odds(region, region_odds, slots, season)
    sf_home = compute_semifinal_home_odds(region, region_odds, slots, season)

    entries = []
    for school, o in region_odds.items():
        adv = adv_odds.get(school)
        p_qf_cond = qf_home.get(school, 0.0)
        p_sf_cond = sf_home.get(school, 0.0)

        if is_1a_4a:
            r2_home_dict = compute_second_round_home_odds(region, region_odds, slots, season)
            p_r2_cond = r2_home_dict.get(school, 0.0)
            p_r1_adv = adv.second_round if adv else 0.0
            p_r2_adv = adv.quarterfinals if adv else 0.0
            p_qf_adv = adv.semifinals if adv else 0.0
            r1_odds = RoundHostingOdds(
                conditional=1.0,
                marginal=marginal_home_odds(1.0, o.p_playoffs),
            )
            r2_odds = RoundHostingOdds(
                conditional=p_r2_cond / p_r1_adv if p_r1_adv > 0 else None,
                marginal=marginal_home_odds(p_r2_cond, p_r1_adv) if p_r1_adv > 0 else 0.0,
            )
            qf_odds = RoundHostingOdds(
                conditional=p_qf_cond / p_r2_adv if p_r2_adv > 0 else None,
                marginal=marginal_home_odds(p_qf_cond, p_r2_adv) if p_r2_adv > 0 else 0.0,
            )
            sf_odds = RoundHostingOdds(
                conditional=p_sf_cond / p_qf_adv if p_qf_adv > 0 else None,
                marginal=marginal_home_odds(p_sf_cond, p_qf_adv) if p_qf_adv > 0 else 0.0,
            )
        else:
            # 5A–7A: no second round; first round IS the quarterfinal
            p_qf_adv = adv.quarterfinals if adv else 0.0
            p_sf_adv = adv.semifinals if adv else 0.0
            r1_odds = RoundHostingOdds(
                conditional=1.0,
                marginal=marginal_home_odds(1.0, o.p_playoffs),
            )
            r2_odds = RoundHostingOdds(conditional=None, marginal=None)
            qf_odds = RoundHostingOdds(
                conditional=p_qf_cond / p_qf_adv if p_qf_adv > 0 else None,
                marginal=marginal_home_odds(p_qf_cond, p_qf_adv) if p_qf_adv > 0 else 0.0,
            )
            sf_odds = RoundHostingOdds(
                conditional=p_sf_cond / p_sf_adv if p_sf_adv > 0 else None,
                marginal=marginal_home_odds(p_sf_cond, p_sf_adv) if p_sf_adv > 0 else 0.0,
            )

        entries.append(TeamHostingEntry(
            school=school,
            first_round=r1_odds,
            second_round=r2_odds,
            quarterfinals=qf_odds,
            semifinals=sf_odds,
        ))
    return entries


@router.get("/hosting/{clazz}/{region}", responses=_404)
async def get_hosting(
    clazz: int,
    region: int,
    season: SeasonQ,
    date: Annotated[date | None, Query()] = None,
) -> HostingResponse:
    """Return playoff hosting odds per round for all teams in *clazz*A Region *region*."""
    from datetime import datetime
    as_of = date or datetime.now().date()
    async with get_conn() as conn:
        region_odds = await _load_region_odds(conn, season, clazz, region, as_of)
        if region_odds is None:
            raise HTTPException(status_code=404, detail=f"No data for {clazz}A Region {region} season {season}")
        slots = await _load_format_slots(conn, season, clazz)
        if not slots:
            raise HTTPException(status_code=404, detail=f"No playoff format found for {clazz}A season {season}")

    entries = _build_hosting_entries(region_odds, slots, region, season, clazz)
    return HostingResponse(season=season, class_=clazz, region=region, as_of_date=as_of, teams=entries)


@router.get("/hosting/{clazz}/{region}/teams/{team}", responses=_404)
async def get_team_hosting(
    clazz: int,
    region: int,
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
async def simulate_hosting(
    clazz: int,
    region: int,
    body: SimulateRegionRequest,
    season: SeasonQ,
    date: Annotated[date | None, Query()] = None,
) -> HostingResponse:
    """Apply hypothetical game results and return updated hosting odds."""
    from datetime import datetime

    from backend.api.routers.standings import _load_scenarios_snapshot, _recompute_from_games
    from backend.helpers.data_classes import AppliedGameResult
    from backend.helpers.scenario_updater import apply_region_game_results

    as_of = date or datetime.now().date()
    async with get_conn() as conn:
        slots = await _load_format_slots(conn, season, clazz)
        if not slots:
            raise HTTPException(status_code=404, detail=f"No playoff format found for {clazz}A season {season}")

        scenarios_data = await _load_scenarios_snapshot(conn, season, clazz, region, as_of)
        if scenarios_data is not None:
            remaining, _, _ = scenarios_data
        else:
            _, _, remaining, _, _ = await _recompute_from_games(conn, season, clazz, region, as_of)

        team_rows = await conn.execute(
            "SELECT school FROM school_seasons WHERE season=%s AND class=%s AND region=%s ORDER BY school",
            (season, clazz, region),
        )
        teams = [r[0] async for r in team_rows]

        game_rows = await conn.execute(
            """
            SELECT school, opponent, points_for, points_against, date
            FROM games
            WHERE season=%s AND region_game=TRUE AND final=TRUE AND date<=%s AND school=ANY(%s)
            ORDER BY date
            """,
            (season, as_of, teams),
        )
        from backend.helpers.data_classes import CompletedGame
        seen: set[frozenset] = set()
        completed = []
        async for school, opponent, pf, pa, gd in game_rows:
            pair = frozenset([school, opponent])
            if pair in seen or pf is None or pa is None:
                continue
            seen.add(pair)
            a, b = (school, opponent) if school < opponent else (opponent, school)
            winner = school if pf > pa else opponent
            loser = opponent if pf > pa else school
            completed.append(CompletedGame(a=a, b=b, winner=winner, loser=loser, margin=abs(pf - pa), game_date=gd))

        new_results = [
            AppliedGameResult(team_a=r.winner, team_b=r.loser, score_a=r.winner_score or 1, score_b=r.loser_score or 0)
            for r in body.results
        ]
        _, odds_map = apply_region_game_results(teams, completed, remaining, new_results)

    entries = _build_hosting_entries(odds_map, slots, region, season, clazz)
    return HostingResponse(season=season, class_=clazz, region=region, as_of_date=as_of, teams=entries)


@router.post("/hosting/{clazz}/{region}/teams/{team}/simulate", responses=_404)
async def simulate_team_hosting(
    clazz: int,
    region: int,
    team: str,
    body: SimulateRegionRequest,
    season: SeasonQ,
    date: Annotated[date | None, Query()] = None,
) -> HostingResponse:
    """What-if hosting odds for a single *team*."""
    response = await simulate_hosting(clazz, region, body, season=season, date=date)
    response.teams = [t for t in response.teams if t.school == team]
    if not response.teams:
        raise HTTPException(status_code=404, detail=f"Team '{team}' not found in {clazz}A Region {region}")
    return response
