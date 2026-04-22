"""Standings, seeding odds, and scenario endpoints."""

from collections import defaultdict
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from backend.api.db import get_conn
from backend.api.models.requests import SimulateRegionRequest
from backend.api.models.responses import (
    RecordModel,
    RemainingGameModel,
    ScenarioEntry,
    SeedingOddsModel,
    StandingsResponse,
    TeamStandingsEntry,
)
from backend.helpers.data_classes import AppliedGameResult, CompletedGame, RemainingGame, StandingsOdds
from backend.helpers.scenario_serializers import deserialize_complete_scenarios, deserialize_remaining_games
from backend.helpers.scenario_updater import apply_region_game_results
from backend.helpers.scenarios import determine_odds, determine_scenarios

router = APIRouter(prefix="/api/v1", tags=["standings"])

_DISPLAY_THRESHOLD = 6  # R ≤ 6 → show human-readable scenario list

SeasonQ = Annotated[int, Query()]
DateQ = Annotated[date | None, Query()]

_404 = {404: {"description": "Not found"}}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _today() -> date:
    """Return today's date (injectable seam for tests)."""
    return datetime.now().date()


def _remaining_models(remaining: list[RemainingGame]) -> list[RemainingGameModel]:
    """Convert RemainingGame dataclasses to API response models."""
    return [RemainingGameModel(team_a=r.a, team_b=r.b, location_a=r.location_a) for r in remaining]


def _scenario_list(complete_scenarios: list[dict] | None) -> list[ScenarioEntry] | None:
    """Convert complete scenario dicts to ScenarioEntry response models, or None if empty."""
    if not complete_scenarios:
        return None
    result = []
    for sc in complete_scenarios:
        seeding = sc.get("seeding", ())
        result.append(ScenarioEntry(outcomes={team: str(idx + 1) for idx, team in enumerate(seeding)}))
    return result


async def _load_standings_snapshot(
    conn, season: int, clazz: int, region: int, as_of: date
) -> list[tuple] | None:
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
    row = await (await conn.execute(
        """
        SELECT remaining_games, complete_scenarios, as_of_date
        FROM region_scenarios
        WHERE season = %s AND class = %s AND region = %s AND as_of_date <= %s
        ORDER BY as_of_date DESC LIMIT 1
        """,
        (season, str(clazz), region, as_of),
    )).fetchone()
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
        FROM games
        WHERE season = %s AND region_game = TRUE AND final = TRUE AND date <= %s
          AND school = ANY(%s)
        ORDER BY date
        """,
        (season, as_of, teams),
    )
    seen_pairs: set[frozenset] = set()
    completed: list[CompletedGame] = []
    async for school, opponent, pf, pa, game_date in game_rows:
        pair = frozenset([school, opponent])
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        if pf is None or pa is None:
            continue
        a, b = (school, opponent) if school < opponent else (opponent, school)
        winner = school if pf > pa else opponent
        loser = opponent if pf > pa else school
        completed.append(CompletedGame(a=a, b=b, winner=winner, loser=loser, margin=abs(pf - pa), game_date=game_date))

    all_pairs = {frozenset([t1, t2]) for i, t1 in enumerate(teams) for t2 in teams[i + 1 :]}
    done_pairs = {frozenset([c.a, c.b]) for c in completed}
    remaining = [
        RemainingGame(a=min(*pair), b=max(*pair))
        for pair in sorted(all_pairs - done_pairs, key=lambda p: tuple(sorted(p)))
    ]

    results = determine_scenarios(teams, completed, remaining)
    odds = determine_odds(
        teams,
        results.first_counts, results.second_counts, results.third_counts, results.fourth_counts,
        results.denom,
    )
    return teams, completed, remaining, odds, results.coinflip_teams


def _build_team_entries(
    standings_rows: list[tuple],
    odds_override: dict[str, StandingsOdds] | None,
    coinflip_override: set[str] | None,
) -> list[TeamStandingsEntry]:
    """Build per-team response entries from DB rows or on-demand odds."""
    entries = []
    for row in standings_rows:
        school = row[0]
        record = RecordModel(wins=row[1], losses=row[2], ties=row[3], region_wins=row[4], region_losses=row[5], region_ties=row[6])
        if odds_override and school in odds_override:
            o = odds_override[school]
            odds = SeedingOddsModel(p1=o.p1, p2=o.p2, p3=o.p3, p4=o.p4, p_playoffs=o.p_playoffs)
            clinched, eliminated = o.clinched, o.eliminated
            coin_flip = school in (coinflip_override or set())
        else:
            odds = SeedingOddsModel(p1=row[7], p2=row[8], p3=row[9], p4=row[10], p_playoffs=row[11])
            clinched, eliminated = row[12], row[13]
            coin_flip = row[14]
        entries.append(TeamStandingsEntry(school=school, record=record, odds=odds, clinched=clinched, eliminated=eliminated, coin_flip_needed=coin_flip))
    return entries


def _standings_from_odds(
    odds_map: dict[str, StandingsOdds],
    coinflip_teams: set[str],
    records: dict[str, tuple],
) -> list[TeamStandingsEntry]:
    """Build team entries from on-demand computation (no DB standings row available)."""
    entries = []
    for school in sorted(odds_map):
        rec = records.get(school, (0, 0, 0, 0, 0, 0))
        o = odds_map[school]
        entries.append(TeamStandingsEntry(
            school=school,
            record=RecordModel(wins=rec[0], losses=rec[1], ties=rec[2], region_wins=rec[3], region_losses=rec[4], region_ties=rec[5]),
            odds=SeedingOddsModel(p1=o.p1, p2=o.p2, p3=o.p3, p4=o.p4, p_playoffs=o.p_playoffs),
            clinched=o.clinched,
            eliminated=o.eliminated,
            coin_flip_needed=school in coinflip_teams,
        ))
    return entries


def _records_from_completed(teams: list[str], completed: list[CompletedGame]) -> dict[str, tuple]:
    """Build region W/L records from completed games (for on-demand path)."""
    wins: dict[str, int] = defaultdict(int)
    losses: dict[str, int] = defaultdict(int)
    for g in completed:
        wins[g.winner] += 1
        losses[g.loser] += 1
    return {t: (0, 0, 0, wins[t], losses[t], 0) for t in teams}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/standings/{clazz}/{region}")
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
            team_entries = _build_team_entries(standings_rows, None, None)
        elif standings_rows is not None:
            _, _, remaining, _, _ = await _recompute_from_games(conn, season, clazz, region, as_of)
            snapshot_date = standings_rows[0][15]
            complete_scenarios = None
            team_entries = _build_team_entries(standings_rows, None, None)
        else:
            teams, completed, remaining, odds_map, coinflip_teams = await _recompute_from_games(conn, season, clazz, region, as_of)
            records = _records_from_completed(teams, completed)
            team_entries = _standings_from_odds(odds_map, coinflip_teams, records)
            snapshot_date = as_of
            complete_scenarios = None

    scenarios_available = len(remaining) <= _DISPLAY_THRESHOLD
    return StandingsResponse(
        season=season,
        class_=clazz,
        region=region,
        as_of_date=snapshot_date,
        scenarios_available=scenarios_available,
        remaining_games=_remaining_models(remaining),
        teams=team_entries,
        scenarios=_scenario_list(complete_scenarios) if scenarios_available else None,
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


@router.post("/standings/{clazz}/{region}/simulate")
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
            FROM games
            WHERE season = %s AND region_game = TRUE AND final = TRUE AND date <= %s
              AND school = ANY(%s)
            ORDER BY date
            """,
            (season, as_of, teams),
        )
        seen_pairs: set[frozenset] = set()
        completed: list[CompletedGame] = []
        async for school, opponent, pf, pa, game_date in game_rows:
            pair = frozenset([school, opponent])
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            if pf is None or pa is None:
                continue
            a, b = (school, opponent) if school < opponent else (opponent, school)
            winner = school if pf > pa else opponent
            loser = opponent if pf > pa else school
            completed.append(CompletedGame(a=a, b=b, winner=winner, loser=loser, margin=abs(pf - pa), game_date=game_date))

        new_results = [
            AppliedGameResult(
                team_a=r.winner,
                team_b=r.loser,
                score_a=r.winner_score or 1,
                score_b=r.loser_score or 0,
            )
            for r in body.results
        ]
        _, odds_map = apply_region_game_results(teams, completed, remaining, new_results)

        applied_pairs = [{r.winner, r.loser} for r in body.results]
        updated_remaining = [rg for rg in remaining if {rg.a, rg.b} not in applied_pairs]

    records = _records_from_completed(teams, completed)
    team_entries = _standings_from_odds(odds_map, set(), records)

    scenarios_available = len(updated_remaining) <= _DISPLAY_THRESHOLD
    return StandingsResponse(
        season=season,
        class_=clazz,
        region=region,
        as_of_date=snapshot_date,
        scenarios_available=scenarios_available,
        remaining_games=_remaining_models(updated_remaining),
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
