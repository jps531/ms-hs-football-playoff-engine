"""Standings, seeding odds, and scenario endpoints."""

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request

from backend.api.db import get_conn
from backend.api.limiter import limiter
from backend.api.models.requests import SimulateRegionRequest
from backend.api.models.responses import (
    ComputationStateModel,
    KeyInsightConditionModel,
    KeyInsightModel,
    StandingsResponse,
)
from backend.helpers.api_helpers import (
    DISPLAY_THRESHOLD,
    build_team_entries,
    compute_remaining_games,
    filter_remaining_after_simulation,
    parse_completed_games,
    records_from_completed,
    remaining_to_models,
    results_to_applied,
    scenarios_to_entries,
    standings_from_odds,
)
from backend.helpers.data_classes import CompletedGame, RemainingGame, StandingsOdds
from backend.helpers.insights import deserialize_insights
from backend.helpers.scenario_renderer import atoms_from_complete_scenarios, team_scenarios_as_dict
from backend.helpers.scenario_serializers import deserialize_complete_scenarios, deserialize_remaining_games
from backend.helpers.scenario_updater import apply_region_game_results
from backend.helpers.scenarios import determine_odds, determine_scenarios

router = APIRouter(prefix="/api/v1", tags=["standings"])

SeasonQ = Annotated[int, Query(ge=1980, le=2040)]
DateQ = Annotated[date | None, Query()]
ClazzPath = Annotated[int, Path(ge=1, le=7)]
RegionPath = Annotated[int, Path(ge=1, le=8)]
IncludeTeamScenariosQ = Annotated[bool, Query()]

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


def _today() -> date:
    """Return today's date (injectable seam for tests)."""
    return datetime.now().date()


def _odds_from_rows(standings_rows: list[tuple]) -> tuple[dict, dict]:
    """Build (odds, weighted_odds) StandingsOdds dicts from standings DB rows.

    Row columns 7-11 are unweighted p1-p_playoffs; 16-20 are weighted.
    """
    odds: dict[str, StandingsOdds] = {}
    weighted: dict[str, StandingsOdds] = {}
    for row in standings_rows:
        school = row[0]
        odds[school] = StandingsOdds(
            school=school, p1=row[7], p2=row[8], p3=row[9], p4=row[10], p_playoffs=row[11],
            final_playoffs=row[11], clinched=bool(row[12]), eliminated=bool(row[13]),
        )
        weighted[school] = StandingsOdds(
            school=school, p1=row[16], p2=row[17], p3=row[18], p4=row[19], p_playoffs=row[20],
            final_playoffs=row[20], clinched=bool(row[12]), eliminated=bool(row[13]),
        )
    return odds, weighted


def _filter_scenarios_by_simulation(
    complete_scenarios: list[dict],
    simulated_results: list,
) -> list[dict]:
    """Keep only scenarios where every simulated (winner, loser) pair appears in game_winners."""
    simulated_pairs = {(r.winner, r.loser) for r in simulated_results}
    if not simulated_pairs:
        return complete_scenarios
    return [
        sc for sc in complete_scenarios
        if all(pair in sc.get("game_winners", []) for pair in simulated_pairs)
    ]


async def _load_standings_snapshot(conn, season: int, clazz: int, region: int, as_of: date) -> list[tuple] | None:
    """Load region_standings rows for the most recent snapshot on or before *as_of*.

    Row positions (0-indexed):
      0-6:   school, wins, losses, ties, region_wins, region_losses, region_ties
      7-11:  odds_1st–odds_playoffs (unweighted seeding)
      12-14: clinched, eliminated, coin_flip_needed
      15:    as_of_date
      16-20: odds_1st_weighted–odds_playoffs_weighted
      21-25: odds_second_round–odds_champion (bracket advancement, unweighted)
      26-30: odds_second_round_weighted–odds_champion_weighted
      31-34: odds_first_round_home–odds_semifinals_home (unweighted)
      35-38: odds_first_round_home_weighted–odds_semifinals_home_weighted
    """
    rows = await conn.execute(
        """
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
            odds_quarterfinals_home_weighted, odds_semifinals_home_weighted
        FROM region_standings
        WHERE season = %s AND class = %s AND region = %s AND as_of_date <= %s
        ORDER BY school, as_of_date DESC
        """,
        (season, clazz, region, as_of),
    )
    result = [r async for r in rows]
    return result if result else None


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


async def _load_scenarios_snapshot(
    conn, season: int, clazz: int, region: int, as_of: date
) -> tuple[list[RemainingGame], list[dict], list[KeyInsightModel], date] | None:
    """Load remaining_games, complete_scenarios, and key_insights from region_scenarios."""
    row = await (
        await conn.execute(
            """
        SELECT remaining_games, complete_scenarios, key_insights, as_of_date
        FROM region_scenarios
        WHERE season = %s AND class = %s AND region = %s AND as_of_date <= %s
        ORDER BY as_of_date DESC LIMIT 1
        """,
            (season, str(clazz), region, as_of),
        )
    ).fetchone()
    if row is None:
        return None
    remaining = deserialize_remaining_games(row[0])
    complete = deserialize_complete_scenarios(row[1])
    raw_insights = deserialize_insights(row[2] or [])
    key_insights = [
        KeyInsightModel(
            insight_type=ins.insight_type,
            team=ins.team,
            seed=ins.seed,
            conditions=[KeyInsightConditionModel(winner=c.winner, loser=c.loser) for c in ins.conditions],
            rendered=ins.rendered,
            r_computed=ins.r_computed,
        )
        for ins in raw_insights
    ]
    return remaining, complete, key_insights, row[3]


async def _recompute_from_games(
    conn, season: int, clazz: int, region: int, as_of: date
) -> tuple[list[str], list[CompletedGame], list[RemainingGame], dict[str, StandingsOdds], set[str]]:
    """Build completed/remaining game lists from raw game data and recompute odds."""
    team_rows = await conn.execute(
        "SELECT school FROM school_seasons WHERE season = %s AND class = %s AND region = %s AND is_active = TRUE ORDER BY school",
        (season, clazz, region),
    )
    teams = [r[0] async for r in team_rows]
    if not teams:
        raise HTTPException(status_code=404, detail=f"No teams found for {clazz}A Region {region} season {season}")

    game_rows = await conn.execute(
        """
        SELECT school, opponent, points_for, points_against, date
        FROM games_effective
        WHERE season = %s AND region_game = TRUE AND final = TRUE AND date <= %s
          AND school = ANY(%s)
        ORDER BY date
        """,
        (season, as_of, teams),
    )
    completed = parse_completed_games([r async for r in game_rows])
    remaining = compute_remaining_games(teams, completed)

    results = determine_scenarios(teams, completed, remaining)
    odds = determine_odds(
        teams,
        results.first_counts,
        results.second_counts,
        results.third_counts,
        results.fourth_counts,
        results.denom,
    )
    return teams, completed, remaining, odds, results.coinflip_teams


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/standings/{clazz}/{region}", responses=_404)
async def get_standings(
    clazz: ClazzPath,
    region: RegionPath,
    season: SeasonQ,
    date: DateQ = None,
    include_team_scenarios: IncludeTeamScenariosQ = False,
) -> StandingsResponse:
    """Return seeding odds and (when R≤6) scenario list for *clazz*A Region *region*.

    Pass ``include_team_scenarios=true`` to also receive per-team per-seed
    condition strings grouped by team name (only available when R≤6).
    """
    as_of = date or _today()
    async with get_conn() as conn:
        standings_rows = await _load_standings_snapshot(conn, season, clazz, region, as_of)
        scenarios_data = await _load_scenarios_snapshot(conn, season, clazz, region, as_of)
        computation_state = await _load_computation_state(conn, season, clazz, region, as_of)

        if standings_rows is not None and scenarios_data is not None:
            remaining, complete_scenarios, key_insights, snapshot_date = scenarios_data
            team_entries = build_team_entries(standings_rows, None, None)
        elif standings_rows is not None:
            _, _, remaining, _, _ = await _recompute_from_games(conn, season, clazz, region, as_of)
            snapshot_date = standings_rows[0][15]
            complete_scenarios = None
            key_insights = None
            team_entries = build_team_entries(standings_rows, None, None)
        else:
            teams, completed, remaining, odds_map, coinflip_teams = await _recompute_from_games(
                conn, season, clazz, region, as_of
            )
            records = records_from_completed(teams, completed)
            team_entries = standings_from_odds(odds_map, coinflip_teams, records)
            snapshot_date = as_of
            complete_scenarios = None
            key_insights = None

    scenarios_available = len(remaining) <= DISPLAY_THRESHOLD

    ts: dict | None = None
    if include_team_scenarios and complete_scenarios and scenarios_available:
        odds, weighted = _odds_from_rows(standings_rows) if standings_rows else ({}, {})
        ts = team_scenarios_as_dict(
            atoms_from_complete_scenarios(complete_scenarios),
            odds=odds,
            weighted_odds=weighted,
        )

    return StandingsResponse(
        season=season,
        class_=clazz,
        region=region,
        as_of_date=snapshot_date,
        scenarios_available=scenarios_available,
        remaining_games=remaining_to_models(remaining),
        teams=team_entries,
        scenarios=scenarios_to_entries(complete_scenarios) if scenarios_available else None,
        team_scenarios=ts,
        key_insights=key_insights if key_insights else None,
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
    response = await get_standings(clazz, region, season=season, date=date, include_team_scenarios=include_team_scenarios)
    response.teams = [t for t in response.teams if t.school == team]
    if not response.teams:
        raise HTTPException(status_code=404, detail=f"Team '{team}' not found in {clazz}A Region {region}")
    return response


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

    Pass ``include_team_scenarios=true`` to also receive per-team per-seed
    condition strings for the remaining scenarios after simulation.
    """
    as_of = date or _today()
    async with get_conn() as conn:
        scenarios_data = await _load_scenarios_snapshot(conn, season, clazz, region, as_of)
        if scenarios_data is not None:
            remaining, complete_scenarios, _, snapshot_date = scenarios_data
        else:
            _, _, remaining, _, _ = await _recompute_from_games(conn, season, clazz, region, as_of)
            complete_scenarios = None
            snapshot_date = as_of

        team_rows = await conn.execute(
            "SELECT school FROM school_seasons WHERE season = %s AND class = %s AND region = %s AND is_active = TRUE ORDER BY school",
            (season, clazz, region),
        )
        teams = [r[0] async for r in team_rows]

        game_rows = await conn.execute(
            """
            SELECT school, opponent, points_for, points_against, date
            FROM games_effective
            WHERE season = %s AND region_game = TRUE AND final = TRUE AND date <= %s
              AND school = ANY(%s)
            ORDER BY date
            """,
            (season, as_of, teams),
        )
        completed = parse_completed_games([r async for r in game_rows])

        new_results = results_to_applied(body.results)
        _, odds_map = apply_region_game_results(teams, completed, remaining, new_results)
        updated_remaining = filter_remaining_after_simulation(remaining, body.results)

    records = records_from_completed(teams, completed)
    team_entries = standings_from_odds(odds_map, set(), records)

    scenarios_available = len(updated_remaining) <= DISPLAY_THRESHOLD

    filtered_scenarios: list[dict] | None = None
    ts: dict | None = None
    if complete_scenarios and scenarios_available:
        filtered_scenarios = _filter_scenarios_by_simulation(complete_scenarios, body.results)
        if include_team_scenarios and filtered_scenarios:
            sim_odds = {school: StandingsOdds(
                school=school, p1=o.p1, p2=o.p2, p3=o.p3, p4=o.p4,
                p_playoffs=o.p_playoffs, final_playoffs=o.p_playoffs,
                clinched=o.clinched, eliminated=o.eliminated,
            ) for school, o in odds_map.items()}
            ts = team_scenarios_as_dict(
                atoms_from_complete_scenarios(filtered_scenarios),
                odds=sim_odds,
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
        team_scenarios=ts,
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
    response = await simulate_standings(request, clazz, region, body, season=season, date=date, include_team_scenarios=include_team_scenarios)
    response.teams = [t for t in response.teams if t.school == team]
    if not response.teams:
        raise HTTPException(status_code=404, detail=f"Team '{team}' not found in {clazz}A Region {region}")
    return response
