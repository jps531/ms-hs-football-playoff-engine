"""Standings, seeding odds, and scenario endpoints."""

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from backend.api.db import get_conn
from backend.api.models.requests import SimulateRegionRequest
from backend.api.models.responses import StandingsResponse
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
from backend.helpers.scenario_serializers import deserialize_complete_scenarios, deserialize_remaining_games
from backend.helpers.scenario_updater import apply_region_game_results
from backend.helpers.scenarios import determine_odds, determine_scenarios

router = APIRouter(prefix="/api/v1", tags=["standings"])

SeasonQ = Annotated[int, Query()]
DateQ = Annotated[date | None, Query()]

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


def _today() -> date:
    """Return today's date (injectable seam for tests)."""
    return datetime.now().date()


async def _load_standings_snapshot(conn, season: int, clazz: int, region: int, as_of: date) -> list[tuple] | None:
    """Load region_standings rows for the most recent snapshot on or before *as_of*."""
    rows = await conn.execute(
        """
        SELECT DISTINCT ON (school)
            school, wins, losses, ties, region_wins, region_losses, region_ties,
            odds_1st, odds_2nd, odds_3rd, odds_4th, odds_playoffs,
            clinched, eliminated, coin_flip_needed, as_of_date
        FROM region_standings
        WHERE season = %s AND class = %s AND region = %s AND as_of_date <= %s
        ORDER BY school, as_of_date DESC
        """,
        (season, clazz, region, as_of),
    )
    result = [r async for r in rows]
    return result if result else None


async def _load_scenarios_snapshot(
    conn, season: int, clazz: int, region: int, as_of: date
) -> tuple[list[RemainingGame], list[dict], date] | None:
    """Load remaining_games and complete_scenarios from region_scenarios."""
    row = await (
        await conn.execute(
            """
        SELECT remaining_games, complete_scenarios, as_of_date
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
    return remaining, complete, row[2]


async def _recompute_from_games(
    conn, season: int, clazz: int, region: int, as_of: date
) -> tuple[list[str], list[CompletedGame], list[RemainingGame], dict[str, StandingsOdds], set[str]]:
    """Build completed/remaining game lists from raw game data and recompute odds."""
    team_rows = await conn.execute(
        "SELECT school FROM school_seasons WHERE season = %s AND class = %s AND region = %s ORDER BY school",
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
    clazz: int,
    region: int,
    season: SeasonQ,
    date: DateQ = None,
) -> StandingsResponse:
    """Return seeding odds and (when R≤6) scenario list for *clazz*A Region *region*."""
    as_of = date or _today()
    async with get_conn() as conn:
        standings_rows = await _load_standings_snapshot(conn, season, clazz, region, as_of)
        scenarios_data = await _load_scenarios_snapshot(conn, season, clazz, region, as_of)

        if standings_rows is not None and scenarios_data is not None:
            remaining, complete_scenarios, snapshot_date = scenarios_data
            team_entries = build_team_entries(standings_rows, None, None)
        elif standings_rows is not None:
            _, _, remaining, _, _ = await _recompute_from_games(conn, season, clazz, region, as_of)
            snapshot_date = standings_rows[0][15]
            complete_scenarios = None
            team_entries = build_team_entries(standings_rows, None, None)
        else:
            teams, completed, remaining, odds_map, coinflip_teams = await _recompute_from_games(
                conn, season, clazz, region, as_of
            )
            records = records_from_completed(teams, completed)
            team_entries = standings_from_odds(odds_map, coinflip_teams, records)
            snapshot_date = as_of
            complete_scenarios = None

    scenarios_available = len(remaining) <= DISPLAY_THRESHOLD
    return StandingsResponse(
        season=season,
        class_=clazz,
        region=region,
        as_of_date=snapshot_date,
        scenarios_available=scenarios_available,
        remaining_games=remaining_to_models(remaining),
        teams=team_entries,
        scenarios=scenarios_to_entries(complete_scenarios) if scenarios_available else None,
    )


@router.get("/standings/{clazz}/{region}/teams/{team}", responses=_404)
async def get_team_standings(
    clazz: int,
    region: int,
    team: str,
    season: SeasonQ,
    date: DateQ = None,
) -> StandingsResponse:
    """Return standings filtered to a single *team* (same data, subset of teams list)."""
    response = await get_standings(clazz, region, season=season, date=date)
    response.teams = [t for t in response.teams if t.school == team]
    if not response.teams:
        raise HTTPException(status_code=404, detail=f"Team '{team}' not found in {clazz}A Region {region}")
    return response


@router.post("/standings/{clazz}/{region}/simulate", responses=_404)
async def simulate_standings(
    clazz: int,
    region: int,
    body: SimulateRegionRequest,
    season: SeasonQ,
    date: DateQ = None,
) -> StandingsResponse:
    """Apply hypothetical game results and return updated seeding odds."""
    as_of = date or _today()
    async with get_conn() as conn:
        scenarios_data = await _load_scenarios_snapshot(conn, season, clazz, region, as_of)
        if scenarios_data is not None:
            remaining, _, snapshot_date = scenarios_data
        else:
            _, _, remaining, _, _ = await _recompute_from_games(conn, season, clazz, region, as_of)
            snapshot_date = as_of

        team_rows = await conn.execute(
            "SELECT school FROM school_seasons WHERE season = %s AND class = %s AND region = %s ORDER BY school",
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
    return StandingsResponse(
        season=season,
        class_=clazz,
        region=region,
        as_of_date=snapshot_date,
        scenarios_available=scenarios_available,
        remaining_games=remaining_to_models(updated_remaining),
        teams=team_entries,
        scenarios=None,
    )


@router.post("/standings/{clazz}/{region}/teams/{team}/simulate", responses=_404)
async def simulate_team_standings(
    clazz: int,
    region: int,
    team: str,
    body: SimulateRegionRequest,
    season: SeasonQ,
    date: DateQ = None,
) -> StandingsResponse:
    """What-if standings filtered to a single *team*."""
    response = await simulate_standings(clazz, region, body, season=season, date=date)
    response.teams = [t for t in response.teams if t.school == team]
    if not response.teams:
        raise HTTPException(status_code=404, detail=f"Team '{team}' not found in {clazz}A Region {region}")
    return response
