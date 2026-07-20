"""Playoff hosting odds endpoints."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request

from backend.api.db import get_conn
from backend.api.limiter import limiter
from backend.api.models.requests import GameResultRequest, SimulateBracketRequest
from backend.api.models.responses import ClassHostingResponse, HostingResponse
from backend.helpers.api_helpers import (
    _load_and_build_playoff_bracket_state,
    _load_elo_ratings,
    _load_format_slots,
    build_hosting_entries,
    build_seeding_by_region,
    filter_to_team_or_404,
    has_displayable_scenarios,
    load_scenarios_snapshot,
    parse_completed_games,
    recompute_scenarios_from_games,
    resolve_hosting_scenario_inputs,
    results_to_applied,
    select_sentinel_region,
    standings_odds_from_row,
    today,
)
from backend.helpers.data_classes import FormatSlot, StandingsOdds
from backend.helpers.home_game_scenarios import enumerate_home_game_scenarios
from backend.helpers.scenario_renderer import team_home_scenarios_as_dict
from backend.helpers.scenario_updater import apply_region_game_results
from backend.helpers.scenario_viewer import build_scenario_atoms
from backend.helpers.win_probability import EloConfig, make_matchup_prob_fn

router = APIRouter(prefix="/api/v1", tags=["hosting"])

SeasonQ = Annotated[int, Query(ge=1980, le=2040)]
ClazzPath = Annotated[int, Path(ge=1, le=7)]
RegionPath = Annotated[int, Path(ge=1, le=8)]
IncludeScenariosQ = Annotated[bool, Query()]
_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


async def _compute_seed_atoms_if_pre_playoff(
    conn, season: int, clazz: int, region: int, as_of: date, teams: list[str] | None = None,
) -> dict | None:
    """Return a ``build_scenario_atoms`` dict for *region*, or ``None`` when it doesn't apply.

    Returns ``None`` when the region has no remaining games (fully decided —
    every team's seed is already clinched, so no ``seed_required`` placeholder
    can occur) or when the remaining-game count exceeds ``DISPLAY_THRESHOLD``
    (the same combinatorial-blowup guard standings scenario enumeration uses).
    """
    scenarios_data = await load_scenarios_snapshot(conn, season, clazz, region, as_of)
    if scenarios_data is not None:
        remaining, _, _, _ = scenarios_data
    else:
        _, _, remaining, _, _ = await recompute_scenarios_from_games(conn, season, clazz, region, as_of)

    if not has_displayable_scenarios(remaining):
        return None

    if teams is None:
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
    return build_scenario_atoms(teams, completed, remaining)


def _attach_hosting_scenarios(
    entries: list,
    region_odds: dict[str, StandingsOdds],
    slots: list[FormatSlot],
    season: int,
    region: int,
    seed_atoms: dict | None = None,
) -> list:
    """Return a new list of TeamHostingEntry with hosting scenario conditions attached.

    Calls ``enumerate_home_game_scenarios`` per team (pure/fast) and serialises
    the result via ``team_home_scenarios_as_dict``.  Probability annotations are
    derived from the entry's ``RoundHostingOdds`` fields so no extra DB round-trip
    is needed.  *seed_atoms* (from ``_compute_seed_atoms_if_pre_playoff``), when
    provided, expands pre-playoff ``seed_required`` placeholders into the real
    underlying game conditions.
    """
    updated = []
    for entry in entries:
        odds = region_odds.get(entry.school)
        if odds is None:
            updated.append(entry)
            continue

        (
            seed, achievable_seeds,
            p_reach, p_host_given_reach, p_host_overall,
            p_reach_w, p_host_given_reach_w, p_host_overall_w,
        ) = resolve_hosting_scenario_inputs(odds, entry)

        home_scenarios = enumerate_home_game_scenarios(
            region=region,
            seed=seed,
            slots=slots,
            season=season,
            achievable_seeds=achievable_seeds,
            p_reach_by_round=p_reach,
            p_host_given_reach_by_round=p_host_given_reach,
            p_host_overall_by_round=p_host_overall,
            p_reach_weighted_by_round=p_reach_w,
            p_host_given_reach_weighted_by_round=p_host_given_reach_w,
            p_host_overall_weighted_by_round=p_host_overall_w,
        )
        updated.append(
            entry.model_copy(
                update={"scenarios": team_home_scenarios_as_dict(entry.school, home_scenarios, seed_atoms=seed_atoms)}
            )
        )
    return updated


_HostingOddsRowParts = tuple[
    str,
    StandingsOdds,
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]


def _unpack_hosting_odds_row(r) -> _HostingOddsRowParts:
    """Unpack a school-first region_standings hosting-odds row into its component parts.

    Expects columns in the order: school, odds_1st..odds_playoffs, odds_playoffs
    (duplicated), clinched, eliminated, home_(r1,r2,qf,sf), home_(...)_weighted,
    adv_(r1,r2,qf,sf), adv_(...)_weighted — i.e. the shape shared by
    ``_load_region_odds`` and ``_load_all_regions_hosting_odds`` (the latter with
    a leading ``region`` column stripped off before calling this).
    """
    school = r[0]
    odds = standings_odds_from_row(school, r[1], r[2], r[3], r[4], r[5], r[7], r[8])
    home = (r[9], r[10], r[11], r[12])
    home_w = (r[13], r[14], r[15], r[16])
    adv = (r[17], r[18], r[19], r[20])
    adv_w = (r[21], r[22], r[23], r[24])
    return school, odds, home, home_w, adv, adv_w


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
                seed_atoms_by_region[region] = await _compute_seed_atoms_if_pre_playoff(conn, season, clazz, region, as_of)

    if not all_loaded:
        raise HTTPException(status_code=404, detail=f"No data for {clazz}A season {season}")

    region_responses = []
    for region in sorted(all_loaded):
        region_odds, home_p_host_given_reach, home_p_host_given_reach_w, stored_adv, stored_adv_w = all_loaded[region]
        entries = build_hosting_entries(
            region_odds, slots, region, season, clazz,
            home_p_host_given_reach=home_p_host_given_reach,
            home_p_host_given_reach_w=home_p_host_given_reach_w,
            stored_adv=stored_adv,
            stored_adv_w=stored_adv_w,
        )
        if include_scenarios:
            entries = _attach_hosting_scenarios(
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
        seed_atoms = await _compute_seed_atoms_if_pre_playoff(conn, season, clazz, region, as_of) if include_scenarios else None

    entries = build_hosting_entries(
        region_odds, slots, region, season, clazz,
        home_p_host_given_reach=home_p_host_given_reach,
        home_p_host_given_reach_w=home_p_host_given_reach_w,
        stored_adv=stored_adv,
        stored_adv_w=stored_adv_w,
    )
    if include_scenarios:
        entries = _attach_hosting_scenarios(entries, region_odds, slots, season, region, seed_atoms=seed_atoms)
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
        scenarios_data = await load_scenarios_snapshot(conn, season, clazz, sentinel_region, as_of)
        if scenarios_data is not None:
            sentinel_remaining, _, _, _ = scenarios_data
        else:
            _, _, sentinel_remaining, _, _ = await recompute_scenarios_from_games(conn, season, clazz, sentinel_region, as_of)

        elo_ratings = await _load_elo_ratings(conn, season, as_of)

        all_region_odds: dict[int, dict[str, StandingsOdds]] | None = None
        cross_region_wins: dict[tuple[int, int], int] | None = None
        odds_by_region: dict[int, dict[str, StandingsOdds]] = {}
        wins_by_team: dict[str, int] = {}
        matchup_fn_by_region: dict[int, object] = {}
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
            shared_matchup_fn = state.matchup_fn
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

            results_by_region: dict[int, list[GameResultRequest]] = {}
            for r in body.results:
                if r.winner.school is None or r.loser.school is None:
                    continue  # slot refs don't map to regular-season games
                reg = school_to_region.get(r.winner.school) or school_to_region.get(r.loser.school)
                if reg is not None:
                    results_by_region.setdefault(reg, []).append(
                        GameResultRequest(
                            winner=r.winner.school,
                            loser=r.loser.school,
                            winner_score=r.winner_score,
                            loser_score=r.loser_score,
                        )
                    )

            for reg, reg_teams in sorted(regions_in_class.items()):
                reg_scenarios = await load_scenarios_snapshot(conn, season, clazz, reg, as_of)
                if reg_scenarios is not None:
                    reg_remaining, _, _, _ = reg_scenarios
                else:
                    _, _, reg_remaining, _, _ = await recompute_scenarios_from_games(conn, season, clazz, reg, as_of)

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

                if include_scenarios and has_displayable_scenarios(reg_remaining):
                    seed_atoms_by_region[reg] = build_scenario_atoms(reg_teams, completed, reg_remaining)

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
            entries = _attach_hosting_scenarios(
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

        scenarios_data = await load_scenarios_snapshot(conn, season, clazz, region, as_of)
        if scenarios_data is not None:
            remaining, _, _, _ = scenarios_data
        else:
            _, _, remaining, _, _ = await recompute_scenarios_from_games(conn, season, clazz, region, as_of)

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
        school_results = [
            GameResultRequest(
                winner=r.winner.school,
                loser=r.loser.school,
                winner_score=r.winner_score,
                loser_score=r.loser_score,
            )
            for r in body.results
            if r.winner.school is not None and r.loser.school is not None
        ]
        new_results = results_to_applied(school_results)

        elo_ratings = await _load_elo_ratings(conn, season, as_of)

        all_region_odds: dict[int, dict[str, StandingsOdds]] | None = None
        cross_region_wins: dict[tuple[int, int], int] | None = None
        wins_by_team: dict[str, int] = {}
        eliminated_hosting_map: dict[str, tuple] = {}

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
    if include_scenarios:
        seed_atoms = build_scenario_atoms(teams, completed, remaining) if has_displayable_scenarios(remaining) else None
        entries = _attach_hosting_scenarios(entries, odds_map, slots, season, region, seed_atoms=seed_atoms)
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
