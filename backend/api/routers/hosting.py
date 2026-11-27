"""Playoff hosting odds endpoints."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from backend.api.auth import require_owner
from backend.api.db import get_conn
from backend.api.limiter import limiter
from backend.api.models.requests import BracketGameResultRequest, GameResultRequest, SimulateBracketRequest
from backend.api.models.responses import ClassHostingResponse, HostingResponse
from backend.helpers.api_helpers import (
    ACTIVE_SCHOOL_FILTER,
    _compute_seed_atoms_if_pre_playoff,
    _load_elo_ratings,
    _load_format_slots,
    _seed_odds,
    _unpack_hosting_odds_row,
    as_standings_odds,
    attach_hosting_scenarios,
    build_hosting_entries,
    build_seeding_by_region,
    class_team_odds,
    filter_to_team_or_404,
    has_displayable_scenarios,
    hosting_entries_from_class,
    load_active_region_teams,
    load_class_bracket_inputs,
    load_completed_region_games,
    load_other_region_seeding,
    resolve_remaining_games,
    results_to_applied,
    select_sentinel_region,
    today,
    what_if_results,
)
from backend.helpers.bracket_matchups import forced_wins
from backend.helpers.data_classes import StandingsOdds, StoredHostingOdds
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
        WHERE season = %s AND class = %s AND region = %s AND as_of_date <= %s"""
        + ACTIVE_SCHOOL_FILTER
        + """
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
        WHERE season = %s AND class = %s AND as_of_date <= %s"""
        + ACTIVE_SCHOOL_FILTER
        + """
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
            region_odds, clazz,
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
            raise HTTPException(status_code=404, detail=f"No data for Region {region}-{clazz}A, season {season}")
        region_odds, home_p_host_given_reach, home_p_host_given_reach_w, stored_adv, stored_adv_w = loaded
        slots = await _load_format_slots(conn, season, clazz)
        if not slots:
            raise HTTPException(status_code=404, detail=f"No playoff format found for {clazz}A season {season}")
        seed_atoms = None
        if include_scenarios:
            seed_atoms, _ = await _compute_seed_atoms_if_pre_playoff(conn, season, clazz, region, as_of)

    entries = build_hosting_entries(
        region_odds, clazz,
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


@router.post("/hosting/{clazz}/simulate", dependencies=[Depends(require_owner)], responses=_404)
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
            "SELECT school, region FROM school_seasons WHERE season=%s AND class=%s AND region IS NOT NULL"
            " AND is_active=TRUE ORDER BY region, school",
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

        odds_by_region: dict[int, dict[str, StandingsOdds]] = {}
        seed_atoms_by_region: dict[int, dict | None] = {}

        if not sentinel_remaining:
            # Playoff mode: the stored seeds and results, with the what-ifs added.
            c = await load_class_bracket_inputs(conn, season, clazz, as_of)
            what_ifs = what_if_results(body.results, c.odds_t)
            tossup, projected = class_team_odds(
                slots, season, c.odds_t, c.odds_w, c.matchup_fn, c.results, forced_wins(slots, what_ifs)
            )
            # The playoff teams, at their seeds.
            odds_by_region = {
                r: {t: o for t, o in teams.items() if o.p_playoffs > 0}
                for r, teams in as_standings_odds(c.odds_t).items()
            }
            if not any(odds_by_region.values()):
                raise HTTPException(status_code=404, detail=f"No clinched seeds for {clazz}A season {season}")
        else:
            # Regular-season mode: every region's games simulated.
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

                if include_scenarios:
                    scenario_completed, scenario_remaining = merge_applied_results(completed, reg_remaining, reg_new_results)
                    if has_displayable_scenarios(scenario_remaining):
                        seed_atoms_by_region[reg] = build_scenario_atoms(reg_teams, scenario_completed, scenario_remaining)

            # Every region's simulated seeding, worked out for the whole class.
            fn = make_matchup_prob_fn(elo_ratings, odds_by_region, EloConfig()) if elo_ratings else None
            tossup, projected = class_team_odds(slots, season, _seed_odds(odds_by_region), None, fn)

    region_responses = []
    for reg in sorted(odds_by_region):
        reg_odds = odds_by_region[reg]
        entries = hosting_entries_from_class(reg_odds, tossup, projected, clazz)
        if include_scenarios:
            entries = attach_hosting_scenarios(
                entries, reg_odds, slots, season, reg, seed_atoms=seed_atoms_by_region.get(reg)
            )
        region_responses.append(
            HostingResponse(season=season, class_=clazz, region=reg, as_of_date=as_of, teams=entries)
        )
    return ClassHostingResponse(season=season, class_=clazz, as_of_date=as_of, regions=region_responses)


@router.post("/hosting/{clazz}/{region}/simulate", dependencies=[Depends(require_owner)], responses=_404)
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
        scenario_completed, scenario_remaining = completed, remaining

        if not remaining:
            # Playoff mode: the stored seeds and results, with the what-ifs added.
            c = await load_class_bracket_inputs(conn, season, clazz, as_of)
            what_ifs = what_if_results(body.results, c.odds_t)
            tossup, projected = class_team_odds(
                slots, season, c.odds_t, c.odds_w, c.matchup_fn, c.results, forced_wins(slots, what_ifs)
            )
            odds_map = {t: o for t, o in as_standings_odds(c.odds_t).get(region, {}).items() if o.p_playoffs > 0}
            if not odds_map:
                raise HTTPException(status_code=404, detail=f"No clinched seeds for {clazz}A region {region} season {season}")
        else:
            # Regular-season mode: simulate remaining region games, the other regions as stored.
            scenario_completed, scenario_remaining = merge_applied_results(completed, remaining, new_results)
            _, odds_map = apply_region_game_results(teams, completed, remaining, new_results)

            other_region_rows = await load_other_region_seeding(conn, season, clazz, as_of, region)
            seeding_by_region = build_seeding_by_region(region, odds_map, other_region_rows)
            fn = make_matchup_prob_fn(elo_ratings, seeding_by_region, EloConfig()) if elo_ratings else None
            tossup, projected = class_team_odds(slots, season, _seed_odds(seeding_by_region), None, fn)

    entries = hosting_entries_from_class(odds_map, tossup, projected, clazz)
    if include_scenarios:
        seed_atoms = (
            build_scenario_atoms(teams, scenario_completed, scenario_remaining)
            if has_displayable_scenarios(scenario_remaining)
            else None
        )
        entries = attach_hosting_scenarios(entries, odds_map, slots, season, region, seed_atoms=seed_atoms)
    return HostingResponse(season=season, class_=clazz, region=region, as_of_date=as_of, teams=entries)


@router.post("/hosting/{clazz}/{region}/teams/{team}/simulate", dependencies=[Depends(require_owner)], responses=_404)
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
