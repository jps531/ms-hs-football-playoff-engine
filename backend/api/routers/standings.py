"""Standings, seeding odds, and scenario endpoints."""

from collections import defaultdict
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request

from backend.api.db import get_conn
from backend.api.limiter import limiter
from backend.api.models.requests import SimulateRegionRequest
from backend.api.models.responses import (
    ClassRegionStandings,
    ClassStandingsResponse,
    ClassSummary,
    ComputationStateModel,
    RegionSummaryCard,
    StandingsResponse,
    StandingsSummaryResponse,
    TeamStandingsEntry,
)
from backend.helpers.api_helpers import (
    _load_all_region_odds,
    _load_elo_ratings,
    _load_format_slots,
    _odds_from_rows,
    build_region_summary_card,
    build_standings_bracket_home_odds,
    build_team_entries,
    build_team_paths,
    current_standings_order,
    filter_remaining_after_simulation,
    filter_scenarios_by_simulation,
    filter_to_team_or_404,
    group_rows_and_completed_by_region,
    load_active_region_teams,
    load_completed_region_games,
    load_remaining_game_dates,
    load_scenarios_snapshot,
    recompute_scenarios_from_games,
    records_from_completed,
    remaining_to_models,
    resolve_standings_snapshot,
    results_to_applied,
    scenarios_to_entries,
    standings_from_odds,
    today,
    within_display_threshold,
)
from backend.helpers.scenario_renderer import atoms_from_complete_scenarios
from backend.helpers.scenario_updater import apply_region_game_results, merge_applied_results
from backend.helpers.win_probability import EloConfig, make_matchup_prob_fn

router = APIRouter(prefix="/api/v1", tags=["standings"])

SeasonQ = Annotated[int, Query(ge=1980, le=2040)]
DateQ = Annotated[date | None, Query()]
ClazzPath = Annotated[int, Path(ge=1, le=7)]
RegionPath = Annotated[int, Path(ge=1, le=8)]
IncludeTeamScenariosQ = Annotated[bool, Query()]

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


def _reorder_team_entries(team_entries: list[TeamStandingsEntry], order: list[str]) -> list[TeamStandingsEntry]:
    """Re-emit *team_entries* in *order*, dropping any school not present in *order*."""
    by_school = {e.school: e for e in team_entries}
    return [by_school[s] for s in order if s in by_school]


_SUMMARY_SELECT = """
    SELECT * FROM (
        SELECT DISTINCT ON (school)
            school, class, region,
            wins, losses, ties, region_wins, region_losses, region_ties,
            as_of_date,
            odds_1st, odds_2nd, odds_3rd, odds_4th, odds_playoffs,
            clinched, eliminated
        FROM region_standings
        WHERE season = %s AND as_of_date <= %s
        ORDER BY school, as_of_date DESC
    ) latest
    ORDER BY class, region, school
"""

_CLASS_SELECT = """
    SELECT * FROM (
        SELECT DISTINCT ON (school)
            school, wins, losses, ties, region_wins, region_losses, region_ties,
            odds_1st, odds_2nd, odds_3rd, odds_4th, odds_playoffs,
            clinched, eliminated, coin_flip_needed, as_of_date,
            odds_1st_weighted, odds_2nd_weighted, odds_3rd_weighted, odds_4th_weighted, odds_playoffs_weighted,
            odds_second_round, odds_quarterfinals, odds_semifinals, odds_finals, odds_champion,
            odds_second_round_weighted, odds_quarterfinals_weighted, odds_semifinals_weighted,
            odds_finals_weighted, odds_champion_weighted,
            odds_first_round_home, odds_second_round_home, odds_quarterfinals_home, odds_semifinals_home,
            odds_first_round_home_weighted, odds_second_round_home_weighted,
            odds_quarterfinals_home_weighted, odds_semifinals_home_weighted,
            region
        FROM region_standings
        WHERE season = %s AND class = %s AND as_of_date <= %s
        ORDER BY school, as_of_date DESC
    ) latest
    ORDER BY region, school
"""


async def _load_computation_state(
    conn, season: int, clazz: int, region: int, as_of: date
) -> ComputationStateModel | None:
    """Load the most recent computation state for a region on or before *as_of*."""
    row = await (
        await conn.execute(
            """
            SELECT DISTINCT ON (season, class, region)
                margin_sensitive, margin_compute_status, computed_at, margin_computed_at
            FROM region_computation_state
            WHERE season = %s AND class = %s AND region = %s AND as_of_date <= %s
            ORDER BY season, class, region, as_of_date DESC
            """,
            (season, clazz, region, as_of),
        )
    ).fetchone()
    if row is None:
        return None
    return ComputationStateModel(
        margin_sensitive=row[0],
        margin_compute_status=row[1],
        computed_at=row[2],
        margin_computed_at=row[3],
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/standings/summary", responses=_404)
async def get_standings_summary(season: SeasonQ, date: DateQ = None) -> StandingsSummaryResponse:
    """Statewide summary: one card per region across every class for *season*.

    Reads the latest region_standings snapshot on or before *date* (defaults
    to today) for every school in the season, then groups by (class, region)
    to build each card. No scenario data is read — clinched/eliminated/leader/
    volatility all derive from the stored seeding-odds snapshot plus completed
    region games only.
    """
    as_of_date = date or today()
    async with get_conn() as conn:
        rows = [r async for r in await conn.execute(_SUMMARY_SELECT, (season, as_of_date))]
        if not rows:
            raise HTTPException(status_code=404, detail=f"Season {season} not found")
        all_schools = [r[0] for r in rows]
        completed_games = await load_completed_region_games(conn, season, as_of_date, all_schools)

    by_class_region, completed_by_region = group_rows_and_completed_by_region(
        rows, completed_games, key_fn=lambda r: (r[1], r[2])
    )

    latest_seen = max(row[9] for row in rows)
    by_class: dict[int, list[RegionSummaryCard]] = defaultdict(list)
    for (clazz, region), region_rows in sorted(by_class_region.items()):
        card = build_region_summary_card(region, region_rows, completed_by_region[(clazz, region)])
        by_class[clazz].append(card)

    classes = [ClassSummary(class_=c, regions=regions) for c, regions in sorted(by_class.items())]
    return StandingsSummaryResponse(season=season, as_of_date=latest_seen, classes=classes)


@router.get("/standings/{clazz}", responses=_404)
async def get_class_standings(clazz: ClazzPath, season: SeasonQ, date: DateQ = None) -> ClassStandingsResponse:
    """Full standings tables (teams[] only, no scenarios) for every region in *clazz*A.

    Reads the latest region_standings snapshot on or before *date* (defaults
    to today) for every school in the class — same per-team detail as
    ``GET /standings/{clazz}/{region}`` (odds, bracket_odds, home_game_odds,
    clinched, eliminated, coin_flip_needed), minus scenarios and
    computation_state.
    """
    as_of_date = date or today()
    async with get_conn() as conn:
        rows = [r async for r in await conn.execute(_CLASS_SELECT, (season, clazz, as_of_date))]
        if not rows:
            raise HTTPException(status_code=404, detail=f"{clazz}A not found for season {season}")
        all_schools = [r[0] for r in rows]
        completed_games = await load_completed_region_games(conn, season, as_of_date, all_schools)

    by_region, completed_by_region = group_rows_and_completed_by_region(rows, completed_games, key_fn=lambda r: r[39])

    latest_seen = max(row[15] for row in rows)
    regions = []
    for region, region_rows in sorted(by_region.items()):
        team_entries = build_team_entries(region_rows, None, None)
        teams = [r[0] for r in region_rows]
        odds_by_school, _ = _odds_from_rows(region_rows)
        order = current_standings_order(teams, completed_by_region[region], odds_by_school)
        regions.append(ClassRegionStandings(region=region, teams=_reorder_team_entries(team_entries, order)))

    return ClassStandingsResponse(season=season, class_=clazz, as_of_date=latest_seen, regions=regions)


@router.get("/standings/{clazz}/{region}", responses=_404)
async def get_standings(
    clazz: ClazzPath,
    region: RegionPath,
    season: SeasonQ,
    date: DateQ = None,
    include_team_scenarios: IncludeTeamScenariosQ = False,
) -> StandingsResponse:
    """Return seeding odds and (when R≤6) scenario list for *clazz*A Region *region*.

    Pass ``include_team_scenarios=true`` to also receive a per-team ``paths``
    breakdown — minimized OR-of-AND conditions per achievable outcome (seed /
    playoffs / eliminated) — only available when R≤6.
    """
    as_of = date or today()
    async with get_conn() as conn:
        snapshot = await resolve_standings_snapshot(conn, season, clazz, region, as_of, include_team_scenarios)
        computation_state = await _load_computation_state(conn, season, clazz, region, as_of)
        game_dates = (
            await load_remaining_game_dates(conn, season, snapshot.remaining) if snapshot.scenario_atoms else {}
        )

    team_entries = _reorder_team_entries(
        snapshot.team_entries, current_standings_order(snapshot.teams, snapshot.completed, snapshot.odds_for_order)
    )

    scenarios_available = within_display_threshold(snapshot.remaining)

    if include_team_scenarios and snapshot.scenario_atoms and scenarios_available:
        for entry in team_entries:
            entry.paths = build_team_paths(
                entry.school,
                snapshot.scenario_atoms.get(entry.school, {}),
                game_dates,
                snapshot.odds_for_order.get(entry.school),
            )

    return StandingsResponse(
        season=season,
        class_=clazz,
        region=region,
        as_of_date=snapshot.snapshot_date,
        scenarios_available=scenarios_available,
        remaining_games=remaining_to_models(snapshot.remaining),
        teams=team_entries,
        scenarios=scenarios_to_entries(snapshot.complete_scenarios) if scenarios_available else None,
        key_insights=snapshot.key_insights if snapshot.key_insights else None,
        computation_state=computation_state,
    )


@router.get("/standings/{clazz}/{region}/teams/{team}", responses=_404)
async def get_team_standings(
    clazz: ClazzPath,
    region: RegionPath,
    team: str,
    season: SeasonQ,
    date: DateQ = None,
    include_team_scenarios: IncludeTeamScenariosQ = False,
) -> StandingsResponse:
    """Return standings filtered to a single *team* (same data, subset of teams list)."""
    response = await get_standings(
        clazz, region, season=season, date=date, include_team_scenarios=include_team_scenarios
    )
    return filter_to_team_or_404(response, team, clazz, region)


@router.post("/standings/{clazz}/{region}/simulate", responses=_404)
@limiter.limit("10/minute")
async def simulate_standings(
    request: Request,
    clazz: ClazzPath,
    region: RegionPath,
    body: SimulateRegionRequest,
    season: SeasonQ,
    date: DateQ = None,
    include_team_scenarios: IncludeTeamScenariosQ = False,
) -> StandingsResponse:
    """Apply hypothetical game results and return updated seeding odds.

    Pass ``include_team_scenarios=true`` to also receive a per-team ``paths``
    breakdown for the remaining scenarios after simulation.
    """
    as_of = date or today()
    async with get_conn() as conn:
        scenarios_data = await load_scenarios_snapshot(conn, season, clazz, region, as_of)
        if scenarios_data is not None:
            remaining, complete_scenarios, _, snapshot_date = scenarios_data
        else:
            _, _, remaining, _, _ = await recompute_scenarios_from_games(conn, season, clazz, region, as_of)
            complete_scenarios = None
            snapshot_date = as_of

        teams = await load_active_region_teams(conn, season, clazz, region)
        completed = await load_completed_region_games(conn, season, as_of, teams)

        new_results = results_to_applied(body.results)
        _, odds_map = apply_region_game_results(teams, completed, remaining, new_results)
        updated_remaining = filter_remaining_after_simulation(remaining, body.results)

        slots = await _load_format_slots(conn, season, clazz)
        elo_ratings = await _load_elo_ratings(conn, season, as_of)
        by_region = await _load_all_region_odds(conn, season, clazz, as_of)
        game_dates = await load_remaining_game_dates(conn, season, remaining) if include_team_scenarios else {}

    records = records_from_completed(teams, completed)
    by_region[region] = odds_map
    matchup_fn = make_matchup_prob_fn(elo_ratings, by_region, EloConfig()) if elo_ratings else None
    bracket_home_odds_by_school = build_standings_bracket_home_odds(
        region, odds_map, by_region, slots, season, clazz, win_prob_fn_weighted=matchup_fn
    )
    team_entries = standings_from_odds(
        odds_map, set(), records, bracket_home_odds_by_school=bracket_home_odds_by_school
    )

    all_completed, _ = merge_applied_results(completed, remaining, new_results)
    team_entries = _reorder_team_entries(team_entries, current_standings_order(teams, all_completed, odds_map))

    scenarios_available = within_display_threshold(updated_remaining)

    filtered_scenarios: list[dict] | None = None
    if complete_scenarios and scenarios_available:
        filtered_scenarios = filter_scenarios_by_simulation(complete_scenarios, body.results)
        if include_team_scenarios and filtered_scenarios:
            sim_atoms = atoms_from_complete_scenarios(filtered_scenarios)
            for entry in team_entries:
                if entry.school in sim_atoms:
                    entry.paths = build_team_paths(
                        entry.school, sim_atoms[entry.school], game_dates, odds_map.get(entry.school)
                    )

    return StandingsResponse(
        season=season,
        class_=clazz,
        region=region,
        as_of_date=snapshot_date,
        scenarios_available=scenarios_available,
        remaining_games=remaining_to_models(updated_remaining),
        teams=team_entries,
        scenarios=scenarios_to_entries(filtered_scenarios),
    )


@router.post("/standings/{clazz}/{region}/teams/{team}/simulate", responses=_404)
@limiter.limit("10/minute")
async def simulate_team_standings(
    request: Request,
    clazz: ClazzPath,
    region: RegionPath,
    team: str,
    body: SimulateRegionRequest,
    season: SeasonQ,
    date: DateQ = None,
    include_team_scenarios: IncludeTeamScenariosQ = False,
) -> StandingsResponse:
    """What-if standings filtered to a single *team*."""
    response = await simulate_standings(
        request, clazz, region, body, season=season, date=date, include_team_scenarios=include_team_scenarios
    )
    return filter_to_team_or_404(response, team, clazz, region)
