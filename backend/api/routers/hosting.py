"""Playoff hosting odds endpoints."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request

from backend.api.db import get_conn
from backend.api.limiter import limiter
from backend.api.models.requests import BracketGameResultRequest, GameResultRequest, SimulateBracketRequest
from backend.api.models.responses import ClassHostingResponse, HostingResponse
from backend.helpers.api_helpers import (
    _compute_seed_atoms_if_pre_playoff,
    _load_and_build_playoff_bracket_state,
    _load_elo_ratings,
    _load_format_slots,
    _unpack_hosting_odds_row,
    attach_hosting_scenarios,
    build_hosting_entries,
    build_seeding_by_region,
    filter_to_team_or_404,
    has_displayable_scenarios,
    load_active_region_teams,
    load_completed_region_games,
    load_other_region_seeding,
    resolve_remaining_games,
    results_to_applied,
    select_sentinel_region,
    today,
)
from backend.helpers.data_classes import MatchupProbFn, StandingsOdds, StoredHostingOdds
from backend.helpers.scenario_updater import apply_region_game_results, merge_applied_results
from backend.helpers.scenario_viewer import build_scenario_atoms
from backend.helpers.win_probability import EloConfig, make_matchup_prob_fn

router = APIRouter(prefix="/api/v1", tags=["hosting"])

SeasonQ = Annotated[int, Query(ge=1980, le=2040)]
ClazzPath = Annotated[int, Path(ge=1, le=7)]
RegionPath = Annotated[int, Path(ge=1, le=8)]
IncludeScenariosQ = Annotated[bool, Query()]
_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


def _to_school_only_results(results: list[BracketGameResultRequest]) -> list[GameResultRequest]:
    """Convert ParticipantRef-based bracket results to GameResultRequest, dropping slot-ref-only entries.

    Regular-season simulation only understands school-name matchups; results
    identified purely by (region, seed) slot refs, or by round (no specific
    loser), don't map to a specific regular-season game and are skipped.
    """
    return [
        GameResultRequest(
            winner=r.winner.school,
            loser=r.loser.school,
            winner_score=r.winner_score,
            loser_score=r.loser_score,
        )
        for r in results
        if r.winner.school is not None and r.loser is not None and r.loser.school is not None
    ]


async def _load_region_odds(
    conn, season: int, clazz: int, region: int, as_of: date
) -> tuple[
    dict[str, StandingsOdds],
    dict[str, tuple[float, float, float, float]],   # home_p_host_given_reach (r1, r2, qf, sf)
    dict[str, tuple[float, float, float, float]],   # home_p_host_given_reach_w (r1, r2, qf, sf)
    dict[str, tuple[float, float, float, float]],   # adv (r1=p_playoffs, r2, qf, sf)
    dict[str, tuple[float, float, float, float]],   # adv_w
] | None:
    """Load per-team seeding odds, home p_host_given_reach values, and bracket advancement from the most recent snapshot."""
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
    home_p_host_given_reach: dict[str, tuple[float, float, float, float]] = {}
    home_p_host_given_reach_w: dict[str, tuple[float, float, float, float]] = {}
    adv: dict[str, tuple[float, float, float, float]] = {}
    adv_w: dict[str, tuple[float, float, float, float]] = {}
    async for r in rows:
        school, odds, home, home_w, a, a_w = _unpack_hosting_odds_row(r)
        result[school] = odds
        home_p_host_given_reach[school] = home
        home_p_host_given_reach_w[school] = home_w
        adv[school] = a
        adv_w[school] = a_w
    return (result, home_p_host_given_reach, home_p_host_given_reach_w, adv, adv_w) if result else None


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
        result, home_p_host_given_reach, home_p_host_given_reach_w, adv, adv_w = by_region[reg]
        school, odds, home, home_w, a, a_w = _unpack_hosting_odds_row(r[1:])
        result[school] = odds
        home_p_host_given_reach[school] = home
        home_p_host_given_reach_w[school] = home_w
        adv[school] = a
        adv_w[school] = a_w
    return by_region


@router.get("/hosting/{clazz}", responses=_404)
async def get_class_hosting(
    clazz: ClazzPath,
    season: SeasonQ,
    date: Annotated[date | None, Query()] = None,
    include_scenarios: IncludeScenariosQ = False,
) -> ClassHostingResponse:
    """Return playoff hosting odds per round for all regions in *clazz*.

    Pass ``include_scenarios=true`` to include hosting condition text per team.
    """
    as_of = date or today()
    async with get_conn() as conn:
        slots = await _load_format_slots(conn, season, clazz)
        if not slots:
            raise HTTPException(status_code=404, detail=f"No playoff format found for {clazz}A season {season}")
        all_loaded = await _load_all_regions_hosting_odds(conn, season, clazz, as_of)

        seed_atoms_by_region: dict[int, dict | None] = {}
        if include_scenarios:
            for region in all_loaded:
                seed_atoms_by_region[region], _ = await _compute_seed_atoms_if_pre_playoff(
                    conn, season, clazz, region, as_of
                )

    if not all_loaded:
        raise HTTPException(status_code=404, detail=f"No data for {clazz}A season {season}")

    region_responses = []
    for region in sorted(all_loaded):
        region_odds, home_p_host_given_reach, home_p_host_given_reach_w, stored_adv, stored_adv_w = all_loaded[region]
        entries = build_hosting_entries(
            region_odds, slots, region, season, clazz,
            stored=StoredHostingOdds(
                given_reach=home_p_host_given_reach,
                given_reach_weighted=home_p_host_given_reach_w,
                advancement=stored_adv,
                advancement_weighted=stored_adv_w,
            ),
        )
        if include_scenarios:
            entries = attach_hosting_scenarios(
                entries, region_odds, slots, season, region, seed_atoms=seed_atoms_by_region.get(region)
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
    include_scenarios: IncludeScenariosQ = False,
) -> HostingResponse:
    """Return playoff hosting odds per round for all teams in *clazz*A Region *region*.

    Pass ``include_scenarios=true`` to include hosting condition text per team.
    """
    as_of = date or today()
    async with get_conn() as conn:
        loaded = await _load_region_odds(conn, season, clazz, region, as_of)
        if loaded is None:
            raise HTTPException(status_code=404, detail=f"No data for {clazz}A Region {region} season {season}")
        region_odds, home_p_host_given_reach, home_p_host_given_reach_w, stored_adv, stored_adv_w = loaded
        slots = await _load_format_slots(conn, season, clazz)
        if not slots:
            raise HTTPException(status_code=404, detail=f"No playoff format found for {clazz}A season {season}")
        seed_atoms = None
        if include_scenarios:
            seed_atoms, _ = await _compute_seed_atoms_if_pre_playoff(conn, season, clazz, region, as_of)

    entries = build_hosting_entries(
        region_odds, slots, region, season, clazz,
        stored=StoredHostingOdds(
            given_reach=home_p_host_given_reach,
            given_reach_weighted=home_p_host_given_reach_w,
            advancement=stored_adv,
            advancement_weighted=stored_adv_w,
        ),
    )
    if include_scenarios:
        entries = attach_hosting_scenarios(entries, region_odds, slots, season, region, seed_atoms=seed_atoms)
    return HostingResponse(season=season, class_=clazz, region=region, as_of_date=as_of, teams=entries)


@router.get("/hosting/{clazz}/{region}/teams/{team}", responses=_404)
async def get_team_hosting(
    clazz: ClazzPath,
    region: RegionPath,
    team: str,
    season: SeasonQ,
    date: Annotated[date | None, Query()] = None,
    include_scenarios: IncludeScenariosQ = False,
) -> HostingResponse:
    """Return hosting odds for a single *team*."""
    response = await get_hosting(clazz, region, season=season, date=date, include_scenarios=include_scenarios)
    return filter_to_team_or_404(response, team, clazz, region)


@router.post("/hosting/{clazz}/simulate", responses=_404)
@limiter.limit("10/minute")
async def simulate_class_hosting(
    request: Request,
    clazz: ClazzPath,
    body: SimulateBracketRequest,
    season: SeasonQ,
    date: Annotated[date | None, Query()] = None,
    include_scenarios: IncludeScenariosQ = False,
) -> ClassHostingResponse:
    """Apply hypothetical game results and return updated hosting odds for all regions in *clazz*.

    Pass ``include_scenarios=true`` to include hosting condition text per team.
    """
    as_of = date or today()
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

        sentinel_region = select_sentinel_region(regions_in_class)
        sentinel_remaining = await resolve_remaining_games(conn, season, clazz, sentinel_region, as_of)

        elo_ratings = await _load_elo_ratings(conn, season, as_of)

        all_region_odds: dict[int, dict[str, StandingsOdds]] | None = None
        cross_region_wins: dict[tuple[int, int], int] | None = None
        odds_by_region: dict[int, dict[str, StandingsOdds]] = {}
        wins_by_team: dict[str, int] = {}
        matchup_fn_by_region: dict[int, MatchupProbFn | None] = {}
        eliminated_hosting_map: dict[str, tuple] = {}
        seed_atoms_by_region: dict[int, dict | None] = {}

        if not sentinel_remaining:
            # Playoff mode: delegate to shared bracket-state builder.
            state = await _load_and_build_playoff_bracket_state(
                conn, season, clazz, as_of, body.results, elo_ratings, slots
            )
            if state is None:
                raise HTTPException(status_code=404, detail=f"No clinched seeds for {clazz}A season {season}")
            all_region_odds = state.all_region_odds
            cross_region_wins = state.cross_region_wins
            wins_by_team = state.wins_by_team
            eliminated_hosting_map = state.eliminated_hosting_map
            odds_by_region = dict(state.all_region_odds)
            matchup_fn_by_region = dict.fromkeys(odds_by_region, state.matchup_fn)
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

            results_by_region: dict[int, list[GameResultRequest]] = {}
            for gr in _to_school_only_results(body.results):
                reg = school_to_region.get(gr.winner) or school_to_region.get(gr.loser)
                if reg is not None:
                    results_by_region.setdefault(reg, []).append(gr)

            for reg, reg_teams in sorted(regions_in_class.items()):
                reg_remaining = await resolve_remaining_games(conn, season, clazz, reg, as_of)

                completed = await load_completed_region_games(conn, season, as_of, reg_teams)
                reg_new_results = results_to_applied(results_by_region.get(reg, []))
                _, odds_map = apply_region_game_results(reg_teams, completed, reg_remaining, reg_new_results)
                odds_by_region[reg] = odds_map

                other_seeding = [(s, r2, p1, p2, p3, p4) for s, r2, p1, p2, p3, p4 in all_db_seeding if r2 != reg]
                seeding_by_region = build_seeding_by_region(reg, odds_map, other_seeding)
                matchup_fn_by_region[reg] = make_matchup_prob_fn(elo_ratings, seeding_by_region, EloConfig()) if elo_ratings else None

                if include_scenarios:
                    scenario_completed, scenario_remaining = merge_applied_results(completed, reg_remaining, reg_new_results)
                    if has_displayable_scenarios(scenario_remaining):
                        seed_atoms_by_region[reg] = build_scenario_atoms(reg_teams, scenario_completed, scenario_remaining)

    region_responses = []
    for reg in sorted(odds_by_region):
        reg_odds = odds_by_region[reg]
        entries = build_hosting_entries(
            reg_odds, slots, reg, season, clazz,
            wins_confirmed=wins_by_team,
            win_prob_fn_weighted=matchup_fn_by_region.get(reg),
            region_odds_weighted=reg_odds,
            all_region_odds=all_region_odds,
            cross_region_wins=cross_region_wins,
            eliminated_hosting=eliminated_hosting_map if eliminated_hosting_map else None,
        )
        if include_scenarios:
            entries = attach_hosting_scenarios(
                entries, reg_odds, slots, season, reg, seed_atoms=seed_atoms_by_region.get(reg)
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
    body: SimulateBracketRequest,
    season: SeasonQ,
    date: Annotated[date | None, Query()] = None,
    include_scenarios: IncludeScenariosQ = False,
) -> HostingResponse:
    """Apply hypothetical game results and return updated hosting odds."""
    as_of = date or today()
    async with get_conn() as conn:
        slots = await _load_format_slots(conn, season, clazz)
        if not slots:
            raise HTTPException(status_code=404, detail=f"No playoff format found for {clazz}A season {season}")

        remaining = await resolve_remaining_games(conn, season, clazz, region, as_of)

        teams = await load_active_region_teams(conn, season, clazz, region)
        completed = await load_completed_region_games(conn, season, as_of, teams)
        new_results = results_to_applied(_to_school_only_results(body.results))

        elo_ratings = await _load_elo_ratings(conn, season, as_of)

        all_region_odds: dict[int, dict[str, StandingsOdds]] | None = None
        cross_region_wins: dict[tuple[int, int], int] | None = None
        wins_by_team: dict[str, int] = {}
        eliminated_hosting_map: dict[str, tuple] = {}
        scenario_completed, scenario_remaining = completed, remaining

        if not remaining:
            # Playoff mode: delegate to shared bracket-state builder.
            state = await _load_and_build_playoff_bracket_state(
                conn, season, clazz, as_of, body.results, elo_ratings, slots
            )
            if state is None:
                raise HTTPException(status_code=404, detail=f"No clinched seeds for {clazz}A region {region} season {season}")
            all_region_odds = state.all_region_odds
            cross_region_wins = state.cross_region_wins
            wins_by_team = state.wins_by_team
            eliminated_hosting_map = state.eliminated_hosting_map
            odds_map = state.all_region_odds.get(region, {})
            matchup_fn_w = state.matchup_fn
        else:
            # Regular-season mode: simulate remaining region games.
            scenario_completed, scenario_remaining = merge_applied_results(completed, remaining, new_results)
            _, odds_map = apply_region_game_results(teams, completed, remaining, new_results)
            wins_by_team = {}

            other_region_rows = await load_other_region_seeding(conn, season, clazz, as_of, region)
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
    if include_scenarios:
        seed_atoms = (
            build_scenario_atoms(teams, scenario_completed, scenario_remaining)
            if has_displayable_scenarios(scenario_remaining)
            else None
        )
        entries = attach_hosting_scenarios(entries, odds_map, slots, season, region, seed_atoms=seed_atoms)
    return HostingResponse(season=season, class_=clazz, region=region, as_of_date=as_of, teams=entries)


@router.post("/hosting/{clazz}/{region}/teams/{team}/simulate", responses=_404)
@limiter.limit("10/minute")
async def simulate_team_hosting(
    request: Request,
    clazz: ClazzPath,
    region: RegionPath,
    team: str,
    body: SimulateBracketRequest,
    season: SeasonQ,
    date: Annotated[date | None, Query()] = None,
    include_scenarios: IncludeScenariosQ = False,
) -> HostingResponse:
    """What-if hosting odds for a single *team*."""
    response = await simulate_hosting(request, clazz, region, body, season=season, date=date, include_scenarios=include_scenarios)
    return filter_to_team_or_404(response, team, clazz, region)
