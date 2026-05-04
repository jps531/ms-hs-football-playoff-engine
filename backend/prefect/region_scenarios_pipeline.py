"""Prefect tasks and flow for computing region standings scenarios.

Reads completed and remaining games from the DB, calls ``determine_scenarios()``
and ``determine_odds()`` from ``scenarios.py``, and writes results to the
``region_standings`` table.
"""

import bisect
from dataclasses import dataclass as _dataclass
from datetime import date
from typing import TypeVar

from prefect import flow, get_run_logger, task
from prefect.utilities.annotations import quote as _prefect_quote
from psycopg2.extras import Json, execute_values

from backend.helpers.bracket_home_odds import (
    compute_bracket_advancement_odds,
    compute_quarterfinal_home_odds,
    compute_second_round_home_odds,
    compute_semifinal_home_odds,
)
from backend.helpers.data_classes import (
    BracketOdds,
    CompletedGame,
    FormatSlot,
    Game,
    MatchupProbFn,
    RawCompletedGame,
    RemainingGame,
    School,
    Standings,
    StandingsOdds,
    WinProbFn,
    equal_matchup_prob,
)
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.database_helpers import get_database_connection
from backend.helpers.scenario_serializers import (
    serialize_complete_scenarios,
    serialize_remaining_games,
    serialize_scenario_atoms,
)
from backend.helpers.scenario_viewer import (
    build_scenario_atoms,
    enumerate_division_scenarios,
    enumerate_outcomes,
)
from backend.helpers.scenarios import (
    compute_bracket_odds,
    compute_first_round_home_odds,
    determine_odds,
    determine_scenarios,
)
from backend.helpers.win_probability import (
    EloConfig,
    compute_elo_ratings,
    compute_rpi,
    make_matchup_prob_fn,
    make_win_prob_fn_from_ratings,
)

_T = TypeVar("_T")


def quote(value: _T) -> _T:
    """Wrap value with Prefect's quote to skip task-parameter introspection."""
    return _prefect_quote(value)  # type: ignore[return-value]


# -------------------------
# Local helpers
# -------------------------


@_dataclass
class HomeOdds:
    """Conditional home-game odds for all applicable playoff rounds.

    Each field holds a dict mapping school name to the conditional probability
    P(hosts round | reaches round).  ``second_round`` is empty for 5A–7A
    classes (which have no second round).
    """

    first_round: dict[str, float]
    second_round: dict[str, float]
    quarterfinals: dict[str, float]
    semifinals: dict[str, float]


@_dataclass
class RegionSeedingData:
    """Intermediate result from Phase 1 of the pipeline.

    Produced by ``get_region_seeding_odds`` and consumed by
    ``get_region_finish_scenarios``.  Carries everything computed from
    ``determine_scenarios`` so the expensive enumeration is not repeated.
    """

    odds: dict[str, StandingsOdds]
    odds_weighted: dict[str, StandingsOdds]
    coinflip_teams: set[str]
    teams: list[str]
    completed: list[CompletedGame]
    remaining: list[RemainingGame]


# -------------------------
# Prefect Tasks
# -------------------------


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Region Teams for {region}-{clazz}A")
def fetch_region_teams(clazz: int, region: int, season: int) -> list[str]:
    """Fetch alphabetically sorted school names for a given class/region/season."""
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT school FROM school_seasons WHERE class=%s AND region=%s AND season=%s AND is_active=TRUE ORDER BY school",
                (clazz, region, season),
            )
            return [r[0] for r in cur.fetchall()]


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} All Season Games for Win Probability")
def fetch_all_season_games(season: int, cutoff_date: date | None = None) -> list[Game]:
    """Fetch all final, scored games for the season (used to build Elo/RPI ratings).

    Args:
        cutoff_date: When provided, only games on or before this date are returned.
                     Used by the historical backfill flow to reconstruct past state.
    """
    base_query = (
        "SELECT school, date, season, location_id, points_for, points_against, "
        "       round, kickoff_time, opponent, result, game_status, source, "
        "       location, region_game, final, overtime "
        "FROM games_effective "
        "WHERE season=%s AND final=TRUE AND points_for IS NOT NULL AND points_against IS NOT NULL"
    )
    if cutoff_date is not None:
        base_query += " AND date <= %s"
        params: tuple = (season, cutoff_date)
    else:
        params = (season,)
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(base_query, params)
            return [
                Game(
                    school=row[0],
                    date=row[1],
                    season=row[2],
                    location_id=row[3],
                    points_for=row[4],
                    points_against=row[5],
                    round=row[6],
                    kickoff_time=row[7],
                    opponent=row[8],
                    result=row[9],
                    game_status=row[10],
                    source=row[11],
                    location=row[12],
                    region_game=row[13],
                    final=row[14],
                    overtime=row[15],
                )
                for row in cur.fetchall()
            ]


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} All Season Schools for Win Probability")
def fetch_all_season_schools(season: int) -> list[School]:
    """Fetch all schools for the season (used for Elo classification priors)."""
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ss.school, ss.season, ss.class, ss.region, "
                "       s.city, s.zip, s.latitude, s.longitude, "
                "       s.mascot, s.primary_color, s.secondary_color "
                "FROM school_seasons ss "
                "JOIN schools_effective s USING (school) "
                "WHERE ss.season=%s",
                (season,),
            )
            return [
                School(
                    school=row[0],
                    season=row[1],
                    class_=row[2],
                    region=row[3],
                    city=row[4],
                    zip=row[5],
                    latitude=row[6],
                    longitude=row[7],
                    mascot=row[8],
                    primary_color=row[9],
                    secondary_color=row[10],
                )
                for row in cur.fetchall()
            ]


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {prior_season} Prior Season Elo Ratings")
def fetch_prior_season_elo(prior_season: int) -> dict[str, float]:
    """Fetch final Elo ratings from the prior season for cross-season carryover.

    Returns an empty dict when no ratings exist for ``prior_season`` (e.g. the
    first season in the database), in which case ``compute_elo_ratings`` falls
    back to class priors for all teams.
    """
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT school, elo FROM team_ratings WHERE season = %s",
                (prior_season,),
            )
            return {row[0]: row[1] for row in cur.fetchall()}


@task(retries=2, retry_delay_seconds=10, task_run_name="Write {season} Team Ratings")
def write_team_ratings(
    elo_ratings: dict[str, float],
    rpi: dict[str, float | None],
    games_count: dict[str, int],
    season: int,
    as_of_date: date,
) -> int:
    """Append Elo and RPI ratings to the ``team_ratings`` table for *as_of_date*.

    One row per school per pipeline-run date is retained so the trend API can
    query historical snapshots.  Same-day reruns overwrite via ON CONFLICT.

    Returns:
        Number of rows written.
    """
    data = [
        (school, season, as_of_date, elo, rpi.get(school), games_count.get(school, 0))
        for school, elo in elo_ratings.items()
    ]
    if not data:
        return 0

    sql = """
        INSERT INTO team_ratings (school, season, as_of_date, elo, rpi, games_played, computed_at)
        VALUES %s
        ON CONFLICT (school, season, as_of_date) DO UPDATE SET
            elo          = EXCLUDED.elo,
            rpi          = EXCLUDED.rpi,
            games_played = EXCLUDED.games_played,
            computed_at  = EXCLUDED.computed_at
    """
    template = "(%s, %s, %s, %s, %s, %s, NOW())"
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, data, template=template, page_size=500)
        conn.commit()

    return len(data)


@task(retries=2, retry_delay_seconds=10, task_run_name="Write {season} Elo Game-Date Snapshots")
def write_elo_game_date_snapshots(
    elo_snapshots: list[tuple[date, dict[str, float], dict[str, int]]],
    season: int,
    skip_date: date,
    known_schools: set[str] | None = None,
) -> int:
    """Persist per-game-date Elo snapshots to team_ratings for timeline queries.

    Each entry in elo_snapshots corresponds to one unique game-date in the season.
    rpi is NULL for historical snapshots — RPI is only meaningful when all games
    are known, so the full-season value is written separately by write_team_ratings.

    Args:
        elo_snapshots:  Per-game-date snapshots from compute_elo_ratings().
        season:         Football season year.
        skip_date:      A date to skip (typically today's pipeline run date, which
                        is already written with full RPI by write_team_ratings).
        known_schools:  When provided, only schools in this set are written.
                        Use to exclude out-of-state opponents that lack a row in
                        the schools table.
    """
    data = [
        (school, season, snap_date, elo, None, snap_games.get(school, 0))
        for snap_date, snap_ratings, snap_games in elo_snapshots
        if snap_date != skip_date
        for school, elo in snap_ratings.items()
        if known_schools is None or school in known_schools
    ]
    if not data:
        return 0

    sql = """
        INSERT INTO team_ratings (school, season, as_of_date, elo, rpi, games_played, computed_at)
        VALUES %s
        ON CONFLICT (school, season, as_of_date) DO UPDATE SET
            elo          = EXCLUDED.elo,
            games_played = EXCLUDED.games_played,
            computed_at  = EXCLUDED.computed_at
    """
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, data, template="(%s,%s,%s,%s,%s,%s,NOW())", page_size=500)
        conn.commit()

    return len(data)


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Completed Region Games for {teams}")
def fetch_completed_pairs(teams: list[str], season: int, cutoff_date: date | None = None) -> list[CompletedGame]:
    """Fetch and normalize all finalized region games among the given teams.

    Args:
        cutoff_date: When provided, only games on or before this date are returned.
                     Used by the historical backfill flow to reconstruct past state.
    """
    base_query = (
        "SELECT school, opponent, date, result, points_for, points_against "
        "FROM games_effective "
        "WHERE season=%s AND final=TRUE AND region_game=TRUE"
    )
    if cutoff_date is not None:
        base_query += " AND date <= %s"
        params: tuple = (season, cutoff_date, teams, teams)
    else:
        params = (season, teams, teams)
    base_query += " AND school = ANY(%s) AND opponent = ANY(%s)"
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(base_query, params)
            rows = cur.fetchall()

    raw_results: list[RawCompletedGame] = [
        {
            "school": s,
            "opponent": o,
            "date": d,
            "result": r,
            "points_for": pf,
            "points_against": pa,
        }
        for (s, o, d, r, pf, pa) in rows
    ]

    logger = get_run_logger()
    logger.info(f"Fetched rows for completed region games: {raw_results}")

    completed = get_completed_games(raw_results)
    logger.info(f"Completed Games: {completed}")
    return completed


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Remaining Region Games for {teams}")
def fetch_remaining_pairs(teams: list[str], season: int, cutoff_date: date | None = None) -> list[RemainingGame]:
    """Fetch all unfinished region game pairs (deduplicated, canonical order) with location.

    Returns one RemainingGame per unplayed contest.  ``location_a`` is the
    location from the lex-first team's perspective ('home'/'away'/'neutral').

    Args:
        cutoff_date: When provided, treats games with date > cutoff_date as
                     remaining (historical reconstruction mode). Without it,
                     fetches games currently marked final=FALSE.
    """
    if cutoff_date is not None:
        date_filter = "date > %s AND region_game=TRUE"
        params: tuple = (season, cutoff_date, teams, teams)
    else:
        date_filter = "final=FALSE AND region_game=TRUE"
        params = (season, teams, teams)

    base_query = (
        "WITH cand AS ("
        "  SELECT"
        "    LEAST(school, opponent) AS a,"
        "    GREATEST(school, opponent) AS b,"
        "    CASE"
        "      WHEN school < opponent THEN location"
        "      WHEN school > opponent THEN"
        "        CASE location"
        "          WHEN 'home' THEN 'away'"
        "          WHEN 'away' THEN 'home'"
        "          ELSE 'neutral'"
        "        END"
        "      ELSE 'neutral'"
        "    END AS location_a"
        "  FROM games_effective"
        "  WHERE season=%s AND " + date_filter + "    AND school = ANY(%s) AND opponent = ANY(%s)"
        ") SELECT DISTINCT ON (a, b) a, b, location_a FROM cand"
    )
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(base_query, params)
            return [RemainingGame(a, b, loc) for a, b, loc in cur.fetchall()]


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Region Standings for {region}-{clazz}A")
def fetch_region_standings(clazz: int, region: int, season: int, cutoff_date: date | None = None) -> list[Standings]:
    """Fetch overall and region W/L/T records via the ``get_standings_for_region`` stored proc.

    Args:
        cutoff_date: When provided, only games on or before this date are counted.
                     Used by the historical backfill flow to reconstruct past records.
    """
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT school, class, region, season, wins, losses, ties, region_wins, region_losses, region_ties "
                "FROM get_standings_for_region(%s, %s, %s, %s)",
                (clazz, region, season, cutoff_date),
            )
            return [Standings(*r) for r in cur.fetchall()]


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Num Rounds for {clazz}A")
def fetch_num_rounds(clazz: int, season: int) -> int:
    """Fetch the total number of playoff rounds for this class/season from ``playoff_formats``.

    Args:
        clazz: MHSAA classification (1–7).
        season: Football season year.

    Returns:
        Total playoff rounds (4 for 5A–7A, 5 for 1A–4A).

    Raises:
        ValueError: If no format row is found for the given class and season.
    """
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT num_rounds FROM playoff_formats WHERE season = %s AND class = %s",
                (season, clazz),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"No playoff_formats entry for season={season}, class={clazz}")
            return row[0]


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} First-Round Home Seeds for {region}-{clazz}A")
def fetch_first_round_home_seeds(clazz: int, region: int, season: int) -> frozenset[int]:
    """Fetch the seed numbers for which a team in this region hosts their round-1 game.

    Queries ``playoff_format_slots`` for slots where ``home_region`` matches
    this region in the given season/class format.

    Args:
        clazz: MHSAA classification (1–7).
        region: Region number within the class.
        season: Football season year.

    Returns:
        A frozenset of seed numbers (subset of {1, 2, 3, 4}) that are
        designated as the home team in round 1 for this region.
    """
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pfs.home_seed "
                "FROM playoff_format_slots pfs "
                "JOIN playoff_formats pf ON pf.id = pfs.format_id "
                "WHERE pf.season = %s AND pf.class = %s AND pfs.home_region = %s",
                (season, clazz, region),
            )
            return frozenset(row[0] for row in cur.fetchall())


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Format Slots for {clazz}A")
def fetch_all_format_slots(clazz: int, season: int) -> list[FormatSlot]:
    """Fetch all first-round playoff format slots for this class/season.

    Args:
        clazz: MHSAA classification (1–7).
        season: Football season year.

    Returns:
        List of FormatSlot instances sorted by slot number.
    """
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pfs.slot, pfs.home_region, pfs.home_seed, "
                "       pfs.away_region, pfs.away_seed, pfs.north_south "
                "FROM playoff_format_slots pfs "
                "JOIN playoff_formats pf ON pf.id = pfs.format_id "
                "WHERE pf.season = %s AND pf.class = %s "
                "ORDER BY pfs.slot",
                (season, clazz),
            )
            return [FormatSlot(*row) for row in cur.fetchall()]


@task(task_run_name="Write {season} Region Standings for {region}-{clazz}A")
def write_region_standings(
    standings: list[Standings],
    odds: dict[str, StandingsOdds],
    clazz: int,
    region: int,
    season: int,
    as_of_date: date,
    coinflip_teams: set[str] | None = None,
    bracket_odds: dict[str, BracketOdds] | None = None,
    bracket_odds_weighted: dict[str, BracketOdds] | None = None,
    home_odds: HomeOdds | None = None,
    home_odds_weighted: HomeOdds | None = None,
    odds_weighted: dict[str, StandingsOdds] | None = None,
):
    """Upsert standings and odds into the ``region_standings`` table.

    Constructs one row per school and performs an INSERT ... ON CONFLICT UPDATE
    so that re-running the flow is idempotent.

    Home-odds parameters are **conditional** probabilities: P(hosts round |
    reaches round).  The marginal P(hosts round) can be recovered at query
    time by multiplying the stored ``odds_*_home`` value by the matching
    ``odds_*`` advancement probability.

    Args:
        standings: List of Standings instances from ``fetch_region_standings``.
        odds: Dict mapping school name to StandingsOdds (from ``determine_odds``).
        clazz: MHSAA classification (1-7).
        region: Region number within the class.
        season: Football season year.
        coinflip_teams: Set of team names that required a coin flip in at least
            one outcome scenario.  Defaults to empty set if not provided.
        bracket_odds: Dict mapping school name to ``BracketOdds`` (50/50
            advancement probabilities).  Defaults to all zeros if not provided.
        bracket_odds_weighted: Weighted advancement probabilities (same
            structure as ``bracket_odds``).  Defaults to all zeros.
        home_odds: Conditional home-game odds (50/50) for all applicable
            rounds.  Defaults to all zeros if not provided.
        home_odds_weighted: Weighted conditional home-game odds.  Defaults to
            all zeros if not provided.

    Returns:
        The number of rows written to the database.
    """
    coinflip_teams = coinflip_teams or set()
    bracket_odds = bracket_odds or {}
    bracket_odds_weighted = bracket_odds_weighted or {}
    odds_weighted = odds_weighted or {}
    _empty_bracket = BracketOdds("", 0.0, 0.0, 0.0, 0.0, 0.0)
    _empty_home = HomeOdds(first_round={}, second_round={}, quarterfinals={}, semifinals={})
    ho = home_odds or _empty_home
    how = home_odds_weighted or _empty_home

    _empty_odds = StandingsOdds("", 0, 0, 0, 0, 0, 0, False, False)

    data_by_school = []
    for team in standings:
        o = odds.get(team.school, _empty_odds)
        ow = odds_weighted.get(team.school, _empty_odds)
        b = bracket_odds.get(team.school, _empty_bracket)
        bw = bracket_odds_weighted.get(team.school, _empty_bracket)
        data_by_school.append(
            (
                team.school,
                season,
                as_of_date,
                clazz,
                region,
                team.wins,
                team.losses,
                team.ties,
                team.region_wins,
                team.region_losses,
                team.region_ties,
                o.p1,
                o.p2,
                o.p3,
                o.p4,
                ow.p1,  # odds_1st_weighted
                ow.p2,  # odds_2nd_weighted
                ow.p3,  # odds_3rd_weighted
                ow.p4,  # odds_4th_weighted
                o.p_playoffs,
                o.clinched,
                o.eliminated,
                b.second_round,
                b.quarterfinals,
                b.semifinals,
                b.finals,
                b.champion,
                ow.p_playoffs,  # odds_playoffs_weighted
                bw.second_round,  # odds_second_round_weighted
                bw.quarterfinals,  # odds_quarterfinals_weighted
                bw.semifinals,  # odds_semifinals_weighted
                bw.finals,  # odds_finals_weighted
                bw.champion,  # odds_champion_weighted
                ho.first_round.get(team.school, 0.0),  # odds_first_round_home
                ho.second_round.get(team.school, 0.0),  # odds_second_round_home
                ho.quarterfinals.get(team.school, 0.0),  # odds_quarterfinals_home
                ho.semifinals.get(team.school, 0.0),  # odds_semifinals_home
                how.first_round.get(team.school, 0.0),  # odds_first_round_home_weighted
                how.second_round.get(team.school, 0.0),  # odds_second_round_home_weighted
                how.quarterfinals.get(team.school, 0.0),  # odds_quarterfinals_home_weighted
                how.semifinals.get(team.school, 0.0),  # odds_semifinals_home_weighted
                team.school in coinflip_teams,  # coin_flip_needed
            )
        )

    sql = """
        INSERT INTO region_standings (
            school, season, as_of_date, class, region,
            wins, losses, ties, region_wins, region_losses, region_ties,
            odds_1st, odds_2nd, odds_3rd, odds_4th,
            odds_1st_weighted, odds_2nd_weighted, odds_3rd_weighted, odds_4th_weighted,
            odds_playoffs, clinched, eliminated,
            odds_second_round, odds_quarterfinals, odds_semifinals, odds_finals, odds_champion,
            odds_playoffs_weighted, odds_second_round_weighted, odds_quarterfinals_weighted,
            odds_semifinals_weighted, odds_finals_weighted, odds_champion_weighted,
            odds_first_round_home, odds_second_round_home, odds_quarterfinals_home, odds_semifinals_home,
            odds_first_round_home_weighted, odds_second_round_home_weighted,
            odds_quarterfinals_home_weighted, odds_semifinals_home_weighted,
            coin_flip_needed
        )
        VALUES %s
        ON CONFLICT (school, season, as_of_date) DO UPDATE SET
            class  = COALESCE(EXCLUDED.class,  region_standings.class),
            region = COALESCE(EXCLUDED.region, region_standings.region),
            wins   = EXCLUDED.wins,
            losses = EXCLUDED.losses,
            ties   = EXCLUDED.ties,
            region_wins   = EXCLUDED.region_wins,
            region_losses = EXCLUDED.region_losses,
            region_ties   = EXCLUDED.region_ties,
            odds_1st      = EXCLUDED.odds_1st,
            odds_2nd      = EXCLUDED.odds_2nd,
            odds_3rd      = EXCLUDED.odds_3rd,
            odds_4th      = EXCLUDED.odds_4th,
            odds_1st_weighted = EXCLUDED.odds_1st_weighted,
            odds_2nd_weighted = EXCLUDED.odds_2nd_weighted,
            odds_3rd_weighted = EXCLUDED.odds_3rd_weighted,
            odds_4th_weighted = EXCLUDED.odds_4th_weighted,
            odds_playoffs = EXCLUDED.odds_playoffs,
            clinched      = EXCLUDED.clinched,
            eliminated    = EXCLUDED.eliminated,
            odds_second_round = EXCLUDED.odds_second_round,
            odds_quarterfinals  = EXCLUDED.odds_quarterfinals,
            odds_semifinals   = EXCLUDED.odds_semifinals,
            odds_finals       = EXCLUDED.odds_finals,
            odds_champion     = EXCLUDED.odds_champion,
            odds_playoffs_weighted = EXCLUDED.odds_playoffs_weighted,
            odds_second_round_weighted = EXCLUDED.odds_second_round_weighted,
            odds_quarterfinals_weighted  = EXCLUDED.odds_quarterfinals_weighted,
            odds_semifinals_weighted   = EXCLUDED.odds_semifinals_weighted,
            odds_finals_weighted       = EXCLUDED.odds_finals_weighted,
            odds_champion_weighted     = EXCLUDED.odds_champion_weighted,
            odds_first_round_home = EXCLUDED.odds_first_round_home,
            odds_second_round_home = EXCLUDED.odds_second_round_home,
            odds_quarterfinals_home = EXCLUDED.odds_quarterfinals_home,
            odds_semifinals_home = EXCLUDED.odds_semifinals_home,
            odds_first_round_home_weighted = EXCLUDED.odds_first_round_home_weighted,
            odds_second_round_home_weighted = EXCLUDED.odds_second_round_home_weighted,
            odds_quarterfinals_home_weighted = EXCLUDED.odds_quarterfinals_home_weighted,
            odds_semifinals_home_weighted = EXCLUDED.odds_semifinals_home_weighted,
            coin_flip_needed = EXCLUDED.coin_flip_needed
        ;
    """

    template = "(" + ", ".join(["%s"] * 42) + ")"
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, data_by_school, template=template, page_size=500)
        conn.commit()

    return len(data_by_school)


# -------------------------
# Main task + flow
# -------------------------


@task(retries=2, retry_delay_seconds=10, task_run_name="Write {season} Region Scenarios for {region}-{clazz}A")
def write_region_scenarios(
    clazz: int,
    region: int,
    season: int,
    as_of_date: date,
    remaining: list[RemainingGame],
    scenario_atoms: dict,
    complete_scenarios: list[dict],
    r_remaining: int,
    margin_sensitive: bool,
    margin_compute_status: str,
    margin_computed_at_now: bool = False,
) -> None:
    """Serialize and upsert pre-computed scenario data into ``region_scenarios``
    and update ``region_computation_state`` accordingly.

    Args:
        clazz: MHSAA classification (1-7).
        region: Region number within the class.
        season: Football season year.
        remaining: Unplayed region game pairs.
        scenario_atoms: Per-team per-seed condition atoms.
        complete_scenarios: Full seeding scenario list.
        r_remaining: Number of remaining games (stored in state table).
        margin_sensitive: Whether this write reflects full margin-sensitive data.
        margin_compute_status: Lifecycle state for ``region_computation_state``.
        margin_computed_at_now: When True, sets ``margin_computed_at = NOW()``.
    """
    logger = get_run_logger()
    logger.info(
        "Writing region scenarios for season %d, class %d, region %d (%d complete scenarios, margin_sensitive=%s)",
        season,
        clazz,
        region,
        len(complete_scenarios),
        margin_sensitive,
    )

    remaining_json = Json(serialize_remaining_games(remaining))
    atoms_json = Json(serialize_scenario_atoms(scenario_atoms))
    scenarios_json = Json(serialize_complete_scenarios(complete_scenarios))

    scenarios_sql = """
        INSERT INTO region_scenarios
            (season, class, region, as_of_date, computed_at, remaining_games, scenario_atoms, complete_scenarios)
        VALUES (%s, %s, %s, %s, NOW(), %s, %s, %s)
        ON CONFLICT (season, class, region, as_of_date) DO UPDATE SET
            computed_at        = EXCLUDED.computed_at,
            remaining_games    = EXCLUDED.remaining_games,
            scenario_atoms     = EXCLUDED.scenario_atoms,
            complete_scenarios = EXCLUDED.complete_scenarios
    """

    state_sql = """
        INSERT INTO region_computation_state
            (season, class, region, as_of_date, r_remaining, margin_sensitive, margin_compute_status,
             computed_at, margin_computed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
        ON CONFLICT (season, class, region, as_of_date) DO UPDATE SET
            r_remaining           = EXCLUDED.r_remaining,
            margin_sensitive      = EXCLUDED.margin_sensitive,
            margin_compute_status = EXCLUDED.margin_compute_status,
            computed_at           = EXCLUDED.computed_at,
            margin_computed_at    = COALESCE(EXCLUDED.margin_computed_at,
                                             region_computation_state.margin_computed_at)
    """
    margin_computed_at = "NOW()" if margin_computed_at_now else None

    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                scenarios_sql, (season, str(clazz), region, as_of_date, remaining_json, atoms_json, scenarios_json)
            )
            cur.execute(
                state_sql,
                (
                    season,
                    clazz,
                    region,
                    as_of_date,
                    r_remaining,
                    margin_sensitive,
                    margin_compute_status,
                    margin_computed_at,
                ),
            )
        conn.commit()


@task(task_run_name="Upgrade {season} Region Scenarios (margin-sensitive) for {region}-{clazz}A")
def upgrade_region_scenarios(
    clazz: int,
    region: int,
    season: int,
    as_of_date: date,
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    pa_win: int = 14,
    base_margin_default: int = 7,
) -> None:
    """Run full margin-sensitive computation and upgrade stored scenario data.

    Called as a background task for R=5–6 regions after the initial win/loss-only
    write.  Updates ``region_scenarios`` with margin-sensitive atoms and flips
    ``region_computation_state`` to ``complete``.
    """
    logger = get_run_logger()
    logger.info(
        "Upgrading region %d-%dA season %d to margin-sensitive scenarios",
        region,
        clazz,
        season,
    )

    precomputed = enumerate_outcomes(
        teams, completed, remaining, pa_win=pa_win, base_margin_default=base_margin_default
    )
    scenario_atoms = build_scenario_atoms(
        teams, completed, remaining, pa_win=pa_win, base_margin_default=base_margin_default, precomputed=precomputed
    )
    complete_scenarios = enumerate_division_scenarios(
        teams,
        completed,
        remaining,
        scenario_atoms=scenario_atoms,
        pa_win=pa_win,
        base_margin_default=base_margin_default,
        precomputed=precomputed,
    )

    write_region_scenarios(
        clazz,
        region,
        season,
        as_of_date=as_of_date,
        remaining=remaining,
        scenario_atoms=scenario_atoms,
        complete_scenarios=complete_scenarios,
        r_remaining=len(remaining),
        margin_sensitive=True,
        margin_compute_status="complete",
        margin_computed_at_now=True,
    )
    logger.info("Upgrade complete for region %d-%dA season %d", region, clazz, season)


# R thresholds for margin computation mode
_R_ALWAYS_MARGIN = 4  # R ≤ this: always full margin, synchronous
_R_BACKGROUND_MAX = 6  # R ≤ this (and > _R_ALWAYS_MARGIN): win/loss first, upgrade in background
_R_MAX_COMPUTE = 15  # R > this: Monte Carlo odds, skip scenario enumeration entirely
# R > _R_BACKGROUND_MAX and R ≤ _R_MAX_COMPUTE: win/loss enumeration, no margin


@task(retries=2, retry_delay_seconds=10, task_run_name="Seeding Odds {season} {region}-{clazz}A")
def get_region_seeding_odds(
    clazz: int,
    region: int,
    season: int,
    elo_ratings: dict[str, float] | None = None,
    elo_snapshots: list[tuple[date, dict[str, float], dict[str, int]]] | None = None,
    elo_config: EloConfig | None = None,
    cutoff_date: date | None = None,
) -> RegionSeedingData:
    """Phase 1: fetch games, enumerate outcomes, and return seeding odds.

    Fetches all game data for the region, runs ``determine_scenarios``, and
    converts raw counts to ``StandingsOdds`` probabilities.  Results are
    returned as a ``RegionSeedingData`` bundle for consumption by
    ``get_region_finish_scenarios`` in Phase 2.

    Args:
        clazz:         MHSAA classification (1–7).
        region:        Region number within the class.
        season:        Football season year.
        elo_ratings:   Pre-computed final Elo ratings for all teams.  When
                       provided, win probabilities are Elo-based; otherwise
                       falls back to equal 50/50.
        elo_snapshots: Date-ordered rating snapshots paired with
                       ``elo_ratings``; ignored when ``elo_ratings`` is None.
        elo_config:    Elo configuration.  Defaults to ``EloConfig()``.
        cutoff_date:   When provided, only games on or before this date are
                       treated as completed; later games are treated as remaining.
                       Used by the historical backfill flow.

    Returns:
        A ``RegionSeedingData`` containing unweighted and weighted seeding
        odds, coinflip teams, and the fetched game lists.
    """
    teams = fetch_region_teams(clazz, region, season)
    if not teams:
        raise SystemExit("No teams found.")
    completed = fetch_completed_pairs(teams, season, cutoff_date=cutoff_date)
    remaining = fetch_remaining_pairs(teams, season, cutoff_date=cutoff_date)

    win_prob_fn: WinProbFn | None = None
    if elo_ratings is not None:
        win_prob_fn = make_win_prob_fn_from_ratings(elo_ratings, elo_snapshots or [], elo_config)

    R = len(remaining)
    use_sampling = R > _R_MAX_COMPUTE
    r = determine_scenarios(
        teams,
        completed,
        remaining,
        win_prob_fn=win_prob_fn,
        ignore_margins=use_sampling or (R > _R_ALWAYS_MARGIN),
        n_samples=50_000 if use_sampling else None,
    )

    odds = determine_odds(teams, r.first_counts, r.second_counts, r.third_counts, r.fourth_counts, r.denom)
    odds_weighted = determine_odds(
        teams,
        r.first_counts_weighted,
        r.second_counts_weighted,
        r.third_counts_weighted,
        r.fourth_counts_weighted,
        r.denom_weighted,
    )
    return RegionSeedingData(
        odds=odds,
        odds_weighted=odds_weighted,
        coinflip_teams=r.coinflip_teams,
        teams=teams,
        completed=completed,
        remaining=remaining,
    )


@task(retries=2, retry_delay_seconds=10, task_run_name="Get {season} Region Finish Scenarios for {region}-{clazz}A")
def get_region_finish_scenarios(
    clazz: int,
    region: int,
    season: int,
    seeding_data: RegionSeedingData,
    matchup_prob_fn: MatchupProbFn | None = None,
    as_of_date: date | None = None,
):
    """Phase 2: compute bracket/home odds and write results to DB.

    Consumes pre-computed seeding odds from ``get_region_seeding_odds`` and an
    optional Elo-based ``MatchupProbFn`` built at flow level from all-region
    seeding odds.  Computes bracket advancement and home-game probabilities,
    writes ``region_standings``, and then writes scenario atoms.

    Args:
        clazz:           MHSAA classification (1–7).
        region:          Region number within the class.
        season:          Football season year.
        seeding_data:    Pre-computed seeding odds from Phase 1.
        matchup_prob_fn: Elo-based matchup probability function built from all
                         regions in the class.  Falls back to equal 50/50 when
                         ``None``.
        as_of_date:      Date to write snapshots for.  Defaults to today.
                         When provided explicitly (backfill mode), skips the
                         background margin-sensitivity upgrade.
    """
    logger = get_run_logger()

    odds = seeding_data.odds
    odds_weighted = seeding_data.odds_weighted
    teams = seeding_data.teams
    completed = seeding_data.completed
    remaining = seeding_data.remaining

    mp_fn = matchup_prob_fn or equal_matchup_prob

    num_rounds = fetch_num_rounds(clazz, season)
    bracket = compute_bracket_odds(num_rounds, odds)

    home_seeds = fetch_first_round_home_seeds(clazz, region, season)
    first_round_home_marginal = compute_first_round_home_odds(home_seeds, odds)
    first_round_home_marginal_w = compute_first_round_home_odds(home_seeds, odds_weighted)

    slots = fetch_all_format_slots(clazz, season)
    second_round_home_marginal = compute_second_round_home_odds(region, odds, slots, season) if clazz <= 4 else {}
    quarterfinals_home_marginal = compute_quarterfinal_home_odds(region, odds, slots, season)
    semifinals_home_marginal = compute_semifinal_home_odds(region, odds, slots, season)

    bracket_weighted = compute_bracket_advancement_odds(region, odds_weighted, slots, mp_fn)
    second_round_home_marginal_w = (
        compute_second_round_home_odds(region, odds_weighted, slots, season, mp_fn) if clazz <= 4 else {}
    )
    quarterfinals_home_marginal_w = compute_quarterfinal_home_odds(region, odds_weighted, slots, season, mp_fn)
    semifinals_home_marginal_w = compute_semifinal_home_odds(region, odds_weighted, slots, season, mp_fn)

    # Convert marginal home odds to conditional: P(hosts | reaches).
    _empty_bracket = BracketOdds("", 0.0, 0.0, 0.0, 0.0, 0.0)

    def _safe_cond(marginal: float, advancement: float) -> float:
        """Return marginal / advancement, or 0.0 when advancement is zero."""
        return marginal / advancement if advancement > 0 else 0.0

    first_round_home_cond = {
        school: _safe_cond(m, odds[school].p_playoffs if school in odds else 0.0)
        for school, m in first_round_home_marginal.items()
    }
    second_round_home_cond = (
        {
            school: _safe_cond(m, bracket.get(school, _empty_bracket).second_round)
            for school, m in second_round_home_marginal.items()
        }
        if clazz <= 4
        else {}
    )
    quarterfinals_home_cond = {
        school: _safe_cond(m, bracket.get(school, _empty_bracket).quarterfinals)
        for school, m in quarterfinals_home_marginal.items()
    }
    semifinals_home_cond = {
        school: _safe_cond(m, bracket.get(school, _empty_bracket).semifinals)
        for school, m in semifinals_home_marginal.items()
    }

    first_round_home_cond_w = {
        school: _safe_cond(m, odds_weighted[school].p_playoffs if school in odds_weighted else 0.0)
        for school, m in first_round_home_marginal_w.items()
    }
    second_round_home_cond_w = (
        {
            school: _safe_cond(m, bracket_weighted.get(school, _empty_bracket).second_round)
            for school, m in second_round_home_marginal_w.items()
        }
        if clazz <= 4
        else {}
    )
    quarterfinals_home_cond_w = {
        school: _safe_cond(m, bracket_weighted.get(school, _empty_bracket).quarterfinals)
        for school, m in quarterfinals_home_marginal_w.items()
    }
    semifinals_home_cond_w = {
        school: _safe_cond(m, bracket_weighted.get(school, _empty_bracket).semifinals)
        for school, m in semifinals_home_marginal_w.items()
    }

    region_standings = fetch_region_standings(clazz, region, season, cutoff_date=as_of_date)
    run_date = as_of_date if as_of_date is not None else date.today()
    is_backfill = as_of_date is not None

    logger.info("Writing region standings for season %d, class %d, region %d", season, clazz, region)
    logger.info("Region standings: %s", region_standings)
    logger.info("Odds: %s", odds)
    write_region_standings(
        region_standings,
        odds,
        clazz,
        region,
        season,
        as_of_date=run_date,
        coinflip_teams=seeding_data.coinflip_teams,
        bracket_odds=bracket,
        bracket_odds_weighted=bracket_weighted,
        home_odds=HomeOdds(
            first_round=first_round_home_cond,
            second_round=second_round_home_cond,
            quarterfinals=quarterfinals_home_cond,
            semifinals=semifinals_home_cond,
        ),
        home_odds_weighted=HomeOdds(
            first_round=first_round_home_cond_w,
            second_round=second_round_home_cond_w,
            quarterfinals=quarterfinals_home_cond_w,
            semifinals=semifinals_home_cond_w,
        ),
        odds_weighted=odds_weighted,
    )

    R = len(remaining)

    if R <= _R_ALWAYS_MARGIN:
        # Full margin-sensitive computation synchronously.
        precomputed = enumerate_outcomes(teams, completed, remaining)
        scenario_atoms = build_scenario_atoms(teams, completed, remaining, precomputed=precomputed)
        complete_scenarios = enumerate_division_scenarios(
            teams, completed, remaining, scenario_atoms=scenario_atoms, precomputed=precomputed
        )
        write_region_scenarios(
            clazz,
            region,
            season,
            as_of_date=run_date,
            remaining=quote(remaining),
            scenario_atoms=quote(scenario_atoms),
            complete_scenarios=quote(complete_scenarios),
            r_remaining=R,
            margin_sensitive=True,
            margin_compute_status="not_needed",
        )
    elif R <= _R_BACKGROUND_MAX:
        # Win/loss-only first for fast initial display; schedule margin upgrade.
        precomputed_wl = enumerate_outcomes(teams, completed, remaining, ignore_margins=True)
        scenario_atoms = build_scenario_atoms(teams, completed, remaining, precomputed=precomputed_wl)
        complete_scenarios = enumerate_division_scenarios(
            teams, completed, remaining, scenario_atoms=scenario_atoms, precomputed=precomputed_wl
        )
        write_region_scenarios(
            clazz,
            region,
            season,
            as_of_date=run_date,
            remaining=quote(remaining),
            scenario_atoms=quote(scenario_atoms),
            complete_scenarios=quote(complete_scenarios),
            r_remaining=R,
            margin_sensitive=False,
            margin_compute_status="pending",
        )
        # Submit background upgrade — runs full margin enumeration asynchronously.
        # Skipped in backfill mode (historical data is already final).
        if not is_backfill:
            upgrade_region_scenarios.submit(
                clazz,
                region,
                season,
                as_of_date=run_date,
                teams=teams,
                completed=completed,
                remaining=remaining,
            )
    elif R > _R_MAX_COMPUTE:
        # Too many remaining games to enumerate scenarios: write empty atoms/scenarios.
        # Monte Carlo odds are written by get_region_seeding_odds; scenario text is
        # not meaningful or displayable at this R.
        write_region_scenarios(
            clazz,
            region,
            season,
            as_of_date=run_date,
            remaining=quote(remaining),
            scenario_atoms=quote({}),
            complete_scenarios=quote([]),
            r_remaining=R,
            margin_sensitive=False,
            margin_compute_status="skipped",
        )
        return {}
    else:
        # R > _R_BACKGROUND_MAX and R ≤ _R_MAX_COMPUTE: win/loss-only permanently.
        precomputed_wl = enumerate_outcomes(teams, completed, remaining, ignore_margins=True)
        scenario_atoms = build_scenario_atoms(teams, completed, remaining, precomputed=precomputed_wl)
        complete_scenarios = enumerate_division_scenarios(
            teams, completed, remaining, scenario_atoms=scenario_atoms, precomputed=precomputed_wl
        )
        write_region_scenarios(
            clazz,
            region,
            season,
            as_of_date=run_date,
            remaining=quote(remaining),
            scenario_atoms=quote(scenario_atoms),
            complete_scenarios=quote(complete_scenarios),
            r_remaining=R,
            margin_sensitive=False,
            margin_compute_status="skipped",
        )

    return scenario_atoms


@flow(name="Region Scenarios Data Flow")
def region_scenarios_data_flow(
    season: int | None = None,
    clazz: int | None = None,
    region: int | None = None,
) -> dict[str, object]:
    """Region Scenarios Data Flow"""
    if season is None:
        season = date.today().year
    logger = get_run_logger()
    logger.info(
        "Running region scenarios data flow for season %d, class %d, region %d",
        season,
        clazz,
        region,
    )

    # Compute Elo ratings once at flow level from all season games.
    # Ratings and RPI are written to team_ratings before region tasks run,
    # guaranteeing that region_standings and team_ratings reflect the same computation.
    all_games = fetch_all_season_games(season)
    all_schools = fetch_all_season_schools(season)
    elo_cfg = EloConfig()
    prior_elo = fetch_prior_season_elo(season - 1)
    elo_ratings, games_count, elo_snapshots = compute_elo_ratings(
        all_games, all_schools, elo_cfg, prior_ratings=prior_elo or None
    )
    rpi = compute_rpi(all_games)
    # Restrict to MS schools only — out-of-state opponents get Elo ratings during
    # computation (for win probability accuracy) but have no row in schools/school_seasons.
    ms_schools = {s.school for s in all_schools}
    ms_elo_ratings = {k: v for k, v in elo_ratings.items() if k in ms_schools}
    ms_games_count = {k: v for k, v in games_count.items() if k in ms_schools}
    flow_run_date = date.today()
    write_team_ratings(quote(ms_elo_ratings), quote(rpi), quote(ms_games_count), season, as_of_date=flow_run_date)
    n_snap = write_elo_game_date_snapshots(
        quote(elo_snapshots), season, skip_date=flow_run_date, known_schools=quote(ms_schools)
    )
    logger.info("Wrote team ratings for %d teams; %d historical game-date snapshot rows", len(elo_ratings), n_snap)

    # Cache quoted versions to avoid re-quoting on every loop iteration.
    q_elo_ratings = quote(elo_ratings)
    q_elo_snapshots = quote(elo_snapshots)

    # -----------------------------------------------------------------------
    # Phase 1: enumerate seeding odds for every region.
    # All regions must finish before we can build the per-class matchup fn.
    # -----------------------------------------------------------------------
    seeding: dict[tuple[int, int], RegionSeedingData] = {}
    if clazz is None or region is None:
        for c in [1, 2, 3, 4]:
            for r in [1, 2, 3, 4, 5, 6, 7, 8]:
                seeding[(c, r)] = get_region_seeding_odds(c, r, season, q_elo_ratings, q_elo_snapshots, elo_cfg)
        for c in [5, 6, 7]:
            for r in [1, 2, 3, 4]:
                seeding[(c, r)] = get_region_seeding_odds(c, r, season, q_elo_ratings, q_elo_snapshots, elo_cfg)
    else:
        seeding[(clazz, region)] = get_region_seeding_odds(
            clazz, region, season, q_elo_ratings, q_elo_snapshots, elo_cfg
        )

    # -----------------------------------------------------------------------
    # Build one MatchupProbFn per class using all-region weighted seeding odds.
    # expected_elo[region, seed] = Σ_t  P(t achieves seed)  ×  elo[t]
    # -----------------------------------------------------------------------
    def _regions_for(c: int) -> list[int]:
        """Return valid region numbers for class c (1–8 for 1A–4A; 1–4 for 5A–7A)."""
        return list(range(1, 9)) if c <= 4 else list(range(1, 5))

    matchup_fns: dict[int, MatchupProbFn] = {}
    for c in {clazz} if clazz is not None else {1, 2, 3, 4, 5, 6, 7}:
        class_weighted_odds = {r: seeding[(c, r)].odds_weighted for r in _regions_for(c) if (c, r) in seeding}
        matchup_fns[c] = make_matchup_prob_fn(elo_ratings, class_weighted_odds, elo_cfg)

    # -----------------------------------------------------------------------
    # Phase 2: compute bracket/home odds and write all results to DB.
    # -----------------------------------------------------------------------
    scenario_dicts: dict = {}
    if clazz is None or region is None:
        for c in [1, 2, 3, 4]:
            scenario_dicts[c] = {}
            for r in [1, 2, 3, 4, 5, 6, 7, 8]:
                scenario_dicts[c][r] = get_region_finish_scenarios(c, r, season, quote(seeding[(c, r)]), matchup_fns[c])
        for c in [5, 6, 7]:
            scenario_dicts[c] = {}
            for r in [1, 2, 3, 4]:
                scenario_dicts[c][r] = get_region_finish_scenarios(c, r, season, quote(seeding[(c, r)]), matchup_fns[c])
    else:
        scenario_dicts.setdefault(clazz, {})[region] = get_region_finish_scenarios(
            clazz, region, season, quote(seeding[(clazz, region)]), matchup_fns[clazz]
        )
    return scenario_dicts


@flow(name="Backfill Historical Snapshots")
def backfill_historical_snapshots(season: int | None = None) -> None:
    """Populate dated snapshots for every computed table across all game-dates in a season.

    Run this once after importing a full historical season's games.  It writes
    team_ratings, region_standings, region_scenarios, and region_computation_state
    rows for each unique game-date so the frontend timeline can serve any past
    date without on-the-fly recomputation.

    Note: region_standings W/L records reflect whatever is in the DB when this
    flow runs (the stored proc has no date filter).  Seeding odds are historically
    accurate because fetch_completed_pairs and fetch_remaining_pairs are
    cutoff-date filtered.
    """
    if season is None:
        season = date.today().year
    logger = get_run_logger()

    all_games = fetch_all_season_games(season)
    all_schools = fetch_all_season_schools(season)
    elo_cfg = EloConfig()
    prior_elo = fetch_prior_season_elo(season - 1)
    elo_ratings, games_count, elo_snapshots = compute_elo_ratings(
        all_games, all_schools, elo_cfg, prior_ratings=prior_elo or None
    )
    rpi = compute_rpi(all_games)
    ms_schools = {s.school for s in all_schools}
    ms_elo_ratings = {k: v for k, v in elo_ratings.items() if k in ms_schools}
    ms_games_count = {k: v for k, v in games_count.items() if k in ms_schools}

    today = date.today()
    write_team_ratings(quote(ms_elo_ratings), quote(rpi), quote(ms_games_count), season, as_of_date=today)
    n_snap = write_elo_game_date_snapshots(
        quote(elo_snapshots), season, skip_date=today, known_schools=quote(ms_schools)
    )
    logger.info("Wrote %d Elo game-date snapshot rows for season %d", n_snap, season)

    if not elo_snapshots:
        logger.info("No game-date snapshots — nothing to backfill.")
        return

    snap_dates = [snap[0] for snap in elo_snapshots]

    logger.info("Backfilling region standings for %d game dates", len(snap_dates))

    def _ratings_at_cutoff(cutoff: date) -> dict[str, float]:
        """Return Elo ratings as of cutoff by finding the last snapshot on or before it."""
        idx = bisect.bisect_right(snap_dates, cutoff) - 1
        return elo_snapshots[idx][1] if idx >= 0 else elo_ratings

    class_regions: dict[int, list[int]] = {c: list(range(1, 9)) if c <= 4 else list(range(1, 5)) for c in range(1, 8)}

    for cutoff_date in snap_dates:
        logger.info("Backfilling region standings/scenarios for %s", cutoff_date)
        ratings_at = _ratings_at_cutoff(cutoff_date)
        q_ratings_at = quote(ratings_at)

        # Phase 1: seeding odds per region.  Pass ratings_at and empty snapshots
        # so win probability for remaining games uses cutoff-date ratings only.
        seeding: dict[tuple[int, int], RegionSeedingData] = {}
        for c, regions in class_regions.items():
            for r in regions:
                seeding[(c, r)] = get_region_seeding_odds(
                    c,
                    r,
                    season,
                    elo_ratings=q_ratings_at,
                    elo_snapshots=quote([]),
                    elo_config=elo_cfg,
                    cutoff_date=cutoff_date,
                )

        # Build per-class matchup probability functions from cutoff-date ratings.
        matchup_fns: dict[int, MatchupProbFn] = {}
        for c, regions in class_regions.items():
            class_weighted_odds = {r: seeding[(c, r)].odds_weighted for r in regions}
            matchup_fns[c] = make_matchup_prob_fn(ratings_at, class_weighted_odds, elo_cfg)

        # Phase 2: bracket/home odds and write all results with as_of_date=cutoff_date.
        for c, regions in class_regions.items():
            for r in regions:
                get_region_finish_scenarios(
                    c, r, season, quote(seeding[(c, r)]), matchup_fns[c], as_of_date=cutoff_date
                )

    logger.info("Backfill complete for season %d: %d dates processed", season, len(snap_dates))
