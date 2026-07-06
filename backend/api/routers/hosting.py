"""Playoff hosting odds endpoints."""

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request

from backend.api.db import get_conn
from backend.api.limiter import limiter
from backend.api.models.requests import SimulateRegionRequest
from backend.api.models.responses import ClassHostingResponse, HostingResponse
from backend.helpers.api_helpers import (
    build_hosting_entries,
    build_seeding_by_region,
    parse_completed_games,
    results_to_applied,
)
from backend.helpers.bracket_home_odds import (
    half_slots_for_region,
    opponent_slots,
    qf_home_team,
    r2_home_team,
    sf_home_team,
    slot_index_for,
    was_home_r1,
)
from backend.helpers.data_classes import FormatSlot, StandingsOdds
from backend.helpers.scenario_updater import apply_region_game_results
from backend.helpers.win_probability import EloConfig, make_matchup_prob_fn

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


async def _load_all_regions_hosting_odds(
    conn, season: int, clazz: int, as_of: date
) -> dict[int, tuple[
    dict[str, StandingsOdds],
    dict[str, tuple[float, float, float, float]],
    dict[str, tuple[float, float, float, float]],
    dict[str, tuple[float, float, float, float]],
    dict[str, tuple[float, float, float, float]],
]]:
    """Return hosting odds for every region in *clazz*, keyed by region number."""
    rows = await conn.execute(
        """
        SELECT DISTINCT ON (school)
            region, school, odds_1st, odds_2nd, odds_3rd, odds_4th, odds_playoffs,
            odds_playoffs, clinched, eliminated,
            odds_first_round_home, odds_second_round_home,
            odds_quarterfinals_home, odds_semifinals_home,
            odds_first_round_home_weighted, odds_second_round_home_weighted,
            odds_quarterfinals_home_weighted, odds_semifinals_home_weighted,
            odds_playoffs, odds_second_round, odds_quarterfinals, odds_semifinals,
            odds_playoffs_weighted, odds_second_round_weighted,
            odds_quarterfinals_weighted, odds_semifinals_weighted
        FROM region_standings
        WHERE season = %s AND class = %s AND as_of_date <= %s
        ORDER BY school, as_of_date DESC
        """,
        (season, clazz, as_of),
    )
    by_region: dict[int, tuple] = {}
    async for r in rows:
        reg = r[0]
        if reg not in by_region:
            by_region[reg] = ({}, {}, {}, {}, {})
        result, home_cond, home_cond_w, adv, adv_w = by_region[reg]
        school = r[1]
        result[school] = StandingsOdds(
            school=school,
            p1=r[2], p2=r[3], p3=r[4], p4=r[5],
            p_playoffs=r[6], final_playoffs=r[7],
            clinched=r[8], eliminated=r[9],
        )
        home_cond[school] = (r[10], r[11], r[12], r[13])
        home_cond_w[school] = (r[14], r[15], r[16], r[17])
        adv[school] = (r[18], r[19], r[20], r[21])
        adv_w[school] = (r[22], r[23], r[24], r[25])
    return by_region


def _find_bracket_survivor(
    opp_slots: list[FormatSlot],
    min_wins: int,
    seed_to_school: dict[tuple[int, int], str],
    wins_by_team: dict[str, int],
) -> tuple[int, int] | None:
    """Return (region, seed) of the team from opp_slots with the most confirmed wins >= min_wins."""
    best: tuple[int, int] | None = None
    best_w = -1
    for slot in opp_slots:
        for r, s in ((slot.home_region, slot.home_seed), (slot.away_region, slot.away_seed)):
            school = seed_to_school.get((r, s))
            if school:
                w = wins_by_team.get(school, 0)
                if w >= min_wins and w > best_w:
                    best = (r, s)
                    best_w = w
    return best


def _eliminated_team_hosting(
    region: int,
    seed: int,
    rounds_played: int,
    slots: list[FormatSlot],
    seed_to_school: dict[tuple[int, int], str],
    wins_by_team: dict[str, int],
    season: int,
    clazz: int,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Deterministic (r1, r2, qf, sf) hosting tuple for an eliminated team.

    Values: 1.0 = hosted, 0.0 = away, None = round not played.
    rounds_played = confirmed_wins + 1.
    """
    is_1a_4a = clazz <= 4
    half = half_slots_for_region(region, slots)
    idx = slot_index_for(region, seed, half)
    if idx is None:
        return (None, None, None, None)

    r1_home_us = was_home_r1(region, seed, half[idx])
    r1 = 1.0 if r1_home_us else 0.0
    if rounds_played < 2:
        return (r1, None, None, None)

    r2: float | None = None
    r2_home_us = False
    if is_1a_4a:
        r2_opp = _find_bracket_survivor(opponent_slots(idx, 1, half), 1, seed_to_school, wins_by_team)
        if r2_opp is None:
            return (r1, None, None, None)
        r2_result = r2_home_team(region, seed, r2_opp[0], r2_opp[1], season)
        r2_home_us = r2_result == (region, seed)
        r2 = 1.0 if r2_home_us else 0.0
        if rounds_played < 3:
            return (r1, r2, None, None)

    # QF: offset differs between 1A-4A (offset 2) and 5A-7A (offset 1)
    qf_offset = 2 if is_1a_4a else 1
    min_wins_qf = 2 if is_1a_4a else 1
    qf_opp = _find_bracket_survivor(opponent_slots(idx, qf_offset, half), min_wins_qf, seed_to_school, wins_by_team)
    if qf_opp is None:
        return (r1, r2, None, None)
    qf_r, qf_s = qf_opp
    qf_half = half_slots_for_region(qf_r, slots)
    qf_idx = slot_index_for(qf_r, qf_s, qf_half)
    r1_home_opp = was_home_r1(qf_r, qf_s, qf_half[qf_idx]) if qf_idx is not None else False
    r2_home_opp = False
    if is_1a_4a and qf_idx is not None:
        r2_opp_of_opp = _find_bracket_survivor(opponent_slots(qf_idx, 1, qf_half), 1, seed_to_school, wins_by_team)
        if r2_opp_of_opp:
            r2_home_opp = r2_home_team(qf_r, qf_s, r2_opp_of_opp[0], r2_opp_of_opp[1], season) == (qf_r, qf_s)
    qf_home = qf_home_team(region, seed, r1_home_us, r2_home_us, qf_r, qf_s, r1_home_opp, r2_home_opp, season)
    qf = 1.0 if qf_home == (region, seed) else 0.0
    rounds_for_sf = 4 if is_1a_4a else 3
    if rounds_played < rounds_for_sf:
        return (r1, r2, qf, None)

    # SF: offset differs between 1A-4A (offset 3) and 5A-7A (offset 2)
    sf_offset = 3 if is_1a_4a else 2
    min_wins_sf = 3 if is_1a_4a else 2
    sf_opp = _find_bracket_survivor(opponent_slots(idx, sf_offset, half), min_wins_sf, seed_to_school, wins_by_team)
    if sf_opp is None:
        return (r1, r2, qf, None)
    sf_home = sf_home_team(region, seed, sf_opp[0], sf_opp[1], season)
    sf = 1.0 if sf_home == (region, seed) else 0.0
    return (r1, r2, qf, sf)


@router.get("/hosting/{clazz}", responses=_404)
async def get_class_hosting(
    clazz: ClazzPath,
    season: SeasonQ,
    date: Annotated[date | None, Query()] = None,
) -> ClassHostingResponse:
    """Return playoff hosting odds per round for all regions in *clazz*."""
    as_of = date or datetime.now().date()
    async with get_conn() as conn:
        slots = await _load_format_slots(conn, season, clazz)
        if not slots:
            raise HTTPException(status_code=404, detail=f"No playoff format found for {clazz}A season {season}")
        all_loaded = await _load_all_regions_hosting_odds(conn, season, clazz, as_of)

    if not all_loaded:
        raise HTTPException(status_code=404, detail=f"No data for {clazz}A season {season}")

    region_responses = []
    for region in sorted(all_loaded):
        region_odds, home_cond, home_cond_w, stored_adv, stored_adv_w = all_loaded[region]
        entries = build_hosting_entries(
            region_odds, slots, region, season, clazz,
            home_cond=home_cond,
            home_cond_w=home_cond_w,
            stored_adv=stored_adv,
            stored_adv_w=stored_adv_w,
        )
        region_responses.append(
            HostingResponse(season=season, class_=clazz, region=region, as_of_date=as_of, teams=entries)
        )
    return ClassHostingResponse(season=season, class_=clazz, as_of_date=as_of, regions=region_responses)


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


@router.post("/hosting/{clazz}/simulate", responses=_404)
@limiter.limit("10/minute")
async def simulate_class_hosting(
    request: Request,
    clazz: ClazzPath,
    body: SimulateRegionRequest,
    season: SeasonQ,
    date: Annotated[date | None, Query()] = None,
) -> ClassHostingResponse:
    """Apply hypothetical game results and return updated hosting odds for all regions in *clazz*."""
    from backend.api.routers.standings import _load_scenarios_snapshot, _recompute_from_games

    as_of = date or datetime.now().date()
    async with get_conn() as conn:
        slots = await _load_format_slots(conn, season, clazz)
        if not slots:
            raise HTTPException(status_code=404, detail=f"No playoff format found for {clazz}A season {season}")

        all_school_rows = await conn.execute(
            "SELECT school, region FROM school_seasons WHERE season=%s AND class=%s AND is_active=TRUE ORDER BY region, school",
            (season, clazz),
        )
        school_to_region: dict[str, int] = {}
        regions_in_class: dict[int, list[str]] = {}
        async for school, reg in all_school_rows:
            school_to_region[school] = reg
            regions_in_class.setdefault(reg, []).append(school)

        if not regions_in_class:
            raise HTTPException(status_code=404, detail=f"No teams found for {clazz}A season {season}")

        sentinel_region = next(iter(sorted(regions_in_class)))
        scenarios_data = await _load_scenarios_snapshot(conn, season, clazz, sentinel_region, as_of)
        if scenarios_data is not None:
            sentinel_remaining, _, _, _ = scenarios_data
        else:
            _, _, sentinel_remaining, _, _ = await _recompute_from_games(conn, season, clazz, sentinel_region, as_of)

        elo_rows = await conn.execute(
            """
            SELECT DISTINCT ON (school) school, elo
            FROM team_ratings
            WHERE season = %s AND as_of_date <= %s
            ORDER BY school, as_of_date DESC
            """,
            (season, as_of),
        )
        elo_ratings: dict[str, float] = {r[0]: r[1] async for r in elo_rows}

        all_region_odds: dict[int, dict[str, StandingsOdds]] | None = None
        cross_region_wins: dict[tuple[int, int], int] | None = None
        odds_by_region: dict[int, dict[str, StandingsOdds]] = {}
        wins_by_team: dict[str, int] = {}
        matchup_fn_by_region: dict[int, object] = {}
        eliminated_hosting_map: dict[str, tuple] = {}

        if not sentinel_remaining:
            # Playoff mode: apply submitted results across the full bracket.
            seed_rows = await conn.execute(
                """
                SELECT rs.school, rs.region,
                       CASE WHEN rs.odds_1st > 0.99 THEN 1
                            WHEN rs.odds_2nd > 0.99 THEN 2
                            WHEN rs.odds_3rd > 0.99 THEN 3
                            WHEN rs.odds_4th > 0.99 THEN 4
                       END AS seed
                FROM region_standings rs
                WHERE rs.season = %s AND rs.class = %s AND rs.clinched = TRUE
                  AND rs.as_of_date = (
                      SELECT MAX(rs2.as_of_date) FROM region_standings rs2
                      WHERE rs2.season = %s AND rs2.class = %s AND rs2.clinched = TRUE
                  )
                """,
                (season, clazz, season, clazz),
            )
            school_to_seed: dict[str, tuple[int, int]] = {}
            async for school, reg, seed in seed_rows:
                if seed is not None:
                    school_to_seed[school] = (reg, seed)

            losers_known: set[tuple[int, int]] = set()
            for r in body.results:
                if r.winner in school_to_seed:
                    wins_by_team[r.winner] = wins_by_team.get(r.winner, 0) + 1
                if r.loser in school_to_seed:
                    losers_known.add(school_to_seed[r.loser])

            all_region_odds = {}
            for school, (reg, seed) in school_to_seed.items():
                is_loser = (reg, seed) in losers_known
                if is_loser:
                    so = StandingsOdds(
                        school=school,
                        p1=0.0, p2=0.0, p3=0.0, p4=0.0,
                        p_playoffs=0.0, final_playoffs=0.0,
                        clinched=True, eliminated=True,
                    )
                else:
                    so = StandingsOdds(
                        school=school,
                        p1=1.0 if seed == 1 else 0.0,
                        p2=1.0 if seed == 2 else 0.0,
                        p3=1.0 if seed == 3 else 0.0,
                        p4=1.0 if seed == 4 else 0.0,
                        p_playoffs=1.0, final_playoffs=1.0,
                        clinched=True, eliminated=False,
                    )
                all_region_odds.setdefault(reg, {})[school] = so

            cross_region_wins = {
                school_to_seed[school]: wins
                for school, wins in wins_by_team.items()
                if school in school_to_seed
            }
            seed_to_school_map = {v: k for k, v in school_to_seed.items()}
            eliminated_hosting_map: dict[str, tuple] = {
                school: _eliminated_team_hosting(
                    reg, seed, wins_by_team.get(school, 0) + 1,
                    slots, seed_to_school_map, wins_by_team, season, clazz,
                )
                for school, (reg, seed) in school_to_seed.items()
                if (reg, seed) in losers_known
            }
            odds_by_region = dict(all_region_odds)
            shared_matchup_fn = make_matchup_prob_fn(elo_ratings, all_region_odds, EloConfig()) if elo_ratings else None
            matchup_fn_by_region = {reg: shared_matchup_fn for reg in odds_by_region}
        else:
            # Regular-season mode: per-region simulation.
            db_seeding_rows = await conn.execute(
                """
                SELECT DISTINCT ON (school) school, region, odds_1st, odds_2nd, odds_3rd, odds_4th
                FROM region_standings
                WHERE season = %s AND class = %s AND as_of_date <= %s
                ORDER BY school, as_of_date DESC
                """,
                (season, clazz, as_of),
            )
            all_db_seeding: list[tuple] = [(r[0], r[1], r[2], r[3], r[4], r[5]) async for r in db_seeding_rows]

            results_by_region: dict[int, list] = {}
            for r in body.results:
                reg = school_to_region.get(r.winner) or school_to_region.get(r.loser)
                if reg is not None:
                    results_by_region.setdefault(reg, []).append(r)

            for reg, reg_teams in sorted(regions_in_class.items()):
                reg_scenarios = await _load_scenarios_snapshot(conn, season, clazz, reg, as_of)
                if reg_scenarios is not None:
                    reg_remaining, _, _, _ = reg_scenarios
                else:
                    _, _, reg_remaining, _, _ = await _recompute_from_games(conn, season, clazz, reg, as_of)

                game_rows = await conn.execute(
                    """
                    SELECT school, opponent, points_for, points_against, date
                    FROM games_effective
                    WHERE season=%s AND region_game=TRUE AND final=TRUE AND date<=%s AND school=ANY(%s)
                    ORDER BY date
                    """,
                    (season, as_of, reg_teams),
                )
                completed = parse_completed_games([r async for r in game_rows])
                reg_new_results = results_to_applied(results_by_region.get(reg, []))
                _, odds_map = apply_region_game_results(reg_teams, completed, reg_remaining, reg_new_results)
                odds_by_region[reg] = odds_map

                other_seeding = [(s, r2, p1, p2, p3, p4) for s, r2, p1, p2, p3, p4 in all_db_seeding if r2 != reg]
                seeding_by_region = build_seeding_by_region(reg, odds_map, other_seeding)
                matchup_fn_by_region[reg] = make_matchup_prob_fn(elo_ratings, seeding_by_region, EloConfig()) if elo_ratings else None

    region_responses = []
    for reg in sorted(odds_by_region):
        entries = build_hosting_entries(
            odds_by_region[reg], slots, reg, season, clazz,
            wins_confirmed=wins_by_team,
            win_prob_fn_weighted=matchup_fn_by_region.get(reg),
            region_odds_weighted=odds_by_region[reg],
            all_region_odds=all_region_odds,
            cross_region_wins=cross_region_wins,
            eliminated_hosting=eliminated_hosting_map if eliminated_hosting_map else None,
        )
        region_responses.append(
            HostingResponse(season=season, class_=clazz, region=reg, as_of_date=as_of, teams=entries)
        )
    return ClassHostingResponse(season=season, class_=clazz, as_of_date=as_of, regions=region_responses)


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

        elo_rows = await conn.execute(
            """
            SELECT DISTINCT ON (school) school, elo
            FROM team_ratings
            WHERE season = %s AND as_of_date <= %s
            ORDER BY school, as_of_date DESC
            """,
            (season, as_of),
        )
        elo_ratings: dict[str, float] = {r[0]: r[1] async for r in elo_rows}

        all_region_odds: dict[int, dict[str, StandingsOdds]] | None = None
        cross_region_wins: dict[tuple[int, int], int] | None = None
        eliminated_hosting_map: dict[str, tuple] = {}

        if not remaining:
            # Playoff mode: apply submitted results to the bracket survivor set.
            seed_rows = await conn.execute(
                """
                SELECT rs.school, rs.region,
                       CASE WHEN rs.odds_1st > 0.99 THEN 1
                            WHEN rs.odds_2nd > 0.99 THEN 2
                            WHEN rs.odds_3rd > 0.99 THEN 3
                            WHEN rs.odds_4th > 0.99 THEN 4
                       END AS seed
                FROM region_standings rs
                WHERE rs.season = %s AND rs.class = %s AND rs.clinched = TRUE
                  AND rs.as_of_date = (
                      SELECT MAX(rs2.as_of_date) FROM region_standings rs2
                      WHERE rs2.season = %s AND rs2.class = %s AND rs2.clinched = TRUE
                  )
                """,
                (season, clazz, season, clazz),
            )
            school_to_seed: dict[str, tuple[int, int]] = {}
            async for school, reg, seed in seed_rows:
                if seed is not None:
                    school_to_seed[school] = (reg, seed)

            wins_by_team: dict[str, int] = {}
            losers_known: set[tuple[int, int]] = set()
            for r in body.results:
                if r.winner in school_to_seed:
                    wins_by_team[r.winner] = wins_by_team.get(r.winner, 0) + 1
                if r.loser in school_to_seed:
                    losers_known.add(school_to_seed[r.loser])

            odds_map: dict[str, StandingsOdds] = {}
            for school, (reg, seed) in school_to_seed.items():
                if reg != region:
                    continue
                is_loser = (reg, seed) in losers_known
                if is_loser:
                    odds_map[school] = StandingsOdds(
                        school=school,
                        p1=0.0, p2=0.0, p3=0.0, p4=0.0,
                        p_playoffs=0.0, final_playoffs=0.0,
                        clinched=True, eliminated=True,
                    )
                else:
                    odds_map[school] = StandingsOdds(
                        school=school,
                        p1=1.0 if seed == 1 else 0.0,
                        p2=1.0 if seed == 2 else 0.0,
                        p3=1.0 if seed == 3 else 0.0,
                        p4=1.0 if seed == 4 else 0.0,
                        p_playoffs=1.0,
                        final_playoffs=1.0,
                        clinched=True,
                        eliminated=False,
                    )

            all_region_odds: dict[int, dict[str, StandingsOdds]] = {}
            for school, (reg, seed) in school_to_seed.items():
                is_loser = (reg, seed) in losers_known
                if is_loser:
                    so = StandingsOdds(
                        school=school,
                        p1=0.0, p2=0.0, p3=0.0, p4=0.0,
                        p_playoffs=0.0, final_playoffs=0.0,
                        clinched=True, eliminated=True,
                    )
                else:
                    so = StandingsOdds(
                        school=school,
                        p1=1.0 if seed == 1 else 0.0,
                        p2=1.0 if seed == 2 else 0.0,
                        p3=1.0 if seed == 3 else 0.0,
                        p4=1.0 if seed == 4 else 0.0,
                        p_playoffs=1.0, final_playoffs=1.0,
                        clinched=True, eliminated=False,
                    )
                all_region_odds.setdefault(reg, {})[school] = so

            cross_region_wins: dict[tuple[int, int], int] = {
                school_to_seed[school]: wins
                for school, wins in wins_by_team.items()
                if school in school_to_seed
            }
            seed_to_school_map = {v: k for k, v in school_to_seed.items()}
            eliminated_hosting_map = {
                school: _eliminated_team_hosting(
                    reg, seed, wins_by_team.get(school, 0) + 1,
                    slots, seed_to_school_map, wins_by_team, season, clazz,
                )
                for school, (reg, seed) in school_to_seed.items()
                if (reg, seed) in losers_known
            }
            matchup_fn_w = make_matchup_prob_fn(elo_ratings, all_region_odds, EloConfig()) if elo_ratings else None
        else:
            # Regular-season mode: simulate remaining region games.
            _, odds_map = apply_region_game_results(teams, completed, remaining, new_results)
            wins_by_team = {}

            other_rows = await conn.execute(
                """
                SELECT DISTINCT ON (school) school, region, odds_1st, odds_2nd, odds_3rd, odds_4th
                FROM region_standings
                WHERE season = %s AND class = %s AND region != %s AND as_of_date <= %s
                ORDER BY school, as_of_date DESC
                """,
                (season, clazz, region, as_of),
            )
            other_region_rows = [(r[0], r[1], r[2], r[3], r[4], r[5]) async for r in other_rows]
            seeding_by_region = build_seeding_by_region(region, odds_map, other_region_rows)
            matchup_fn_w = make_matchup_prob_fn(elo_ratings, seeding_by_region, EloConfig()) if elo_ratings else None

    entries = build_hosting_entries(
        odds_map, slots, region, season, clazz,
        wins_confirmed=wins_by_team,
        win_prob_fn_weighted=matchup_fn_w,
        region_odds_weighted=odds_map,
        all_region_odds=all_region_odds,
        cross_region_wins=cross_region_wins,
        eliminated_hosting=eliminated_hosting_map if eliminated_hosting_map else None,
    )
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
