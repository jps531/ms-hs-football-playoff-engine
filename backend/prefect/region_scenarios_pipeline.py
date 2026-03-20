"""Prefect tasks and flow for computing region standings scenarios.

Reads completed and remaining games from the DB, calls ``determine_scenarios()``
and ``determine_odds()`` from ``scenarios.py``, and writes results to the
``region_standings`` table.
"""

from prefect import flow, get_run_logger, task
from psycopg2.extras import Json, execute_values

from backend.helpers.bracket_home_odds import (
    compute_quarterfinal_home_odds,
    compute_second_round_home_odds,
    compute_semifinal_home_odds,
)
from backend.helpers.data_classes import (
    BracketOdds,
    CompletedGame,
    FormatSlot,
    RawCompletedGame,
    RemainingGame,
    Standings,
    StandingsOdds,
)
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.database_helpers import get_database_connection
from backend.helpers.scenario_serializers import (
    serialize_complete_scenarios,
    serialize_remaining_games,
    serialize_scenario_atoms,
)
from backend.helpers.scenario_viewer import build_scenario_atoms, enumerate_division_scenarios
from backend.helpers.scenarios import (
    compute_bracket_odds,
    compute_first_round_home_odds,
    determine_odds,
    determine_scenarios,
)

# -------------------------
# Prefect Tasks
# -------------------------


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Region Teams for {region}-{clazz}A")
def fetch_region_teams(clazz: int, region: int, season: int) -> list[str]:
    """Fetch alphabetically sorted school names for a given class/region/season."""
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT school FROM school_seasons WHERE class=%s AND region=%s AND season=%s ORDER BY school",
                (clazz, region, season),
            )
            return [r[0] for r in cur.fetchall()]


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Completed Region Games for {teams}")
def fetch_completed_pairs(teams: list[str], season: int) -> list[CompletedGame]:
    """Fetch and normalize all finalized region games among the given teams."""
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT school, opponent, date, result, points_for, points_against "
                "FROM games "
                "WHERE season=%s AND final=TRUE AND region_game=TRUE "
                "  AND school = ANY(%s) AND opponent = ANY(%s)",
                (season, teams, teams),
            )
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
def fetch_remaining_pairs(teams: list[str], season: int) -> list[RemainingGame]:
    """Fetch all unfinished region game pairs (deduplicated, in canonical order) for the given teams."""
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "WITH cand AS ("
                "  SELECT LEAST(school,opponent) a, GREATEST(school,opponent) b FROM games "
                "  WHERE season=%s AND final=FALSE AND region_game=TRUE "
                "    AND school = ANY(%s) AND opponent = ANY(%s)"
                ") SELECT DISTINCT a,b FROM cand",
                (season, teams, teams),
            )
            return [RemainingGame(a, b) for a, b in cur.fetchall()]


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Region Standings for {region}-{clazz}A")
def fetch_region_standings(clazz: int, region: int, season: int) -> list[Standings]:
    """Fetch current overall and region W/L/T records via the ``get_standings_for_region`` stored proc."""
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT school, class, region, season, wins, losses, ties, region_wins, region_losses, region_ties "
                "FROM get_standings_for_region(%s, %s)",
                (clazz, region),
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
    coinflip_teams: set[str] | None = None,
    first_round_home_odds: dict[str, float] | None = None,
    bracket_odds: dict[str, BracketOdds] | None = None,
    second_round_home_odds: dict[str, float] | None = None,
    quarterfinals_home_odds: dict[str, float] | None = None,
    semifinals_home_odds: dict[str, float] | None = None,
):
    """Upsert standings and odds into the ``region_standings`` table.

    Constructs one row per school and performs an INSERT ... ON CONFLICT UPDATE
    so that re-running the flow is idempotent.  Weighted odds columns are
    written as 0.0 placeholders pending future implementation.

    Args:
        standings: List of Standings instances from ``fetch_region_standings``.
        odds: Dict mapping school name to StandingsOdds (from ``determine_odds``).
        clazz: MHSAA classification (1-7).
        region: Region number within the class.
        season: Football season year.
        coinflip_teams: Set of team names that required a coin flip in at least
            one outcome scenario.  Defaults to empty set if not provided.
        first_round_home_odds: Dict mapping school name to probability of
            hosting their round-1 game.  Defaults to all zeros if not provided.
        bracket_odds: Dict mapping school name to ``BracketOdds`` (from
            ``compute_bracket_odds``).  Defaults to all zeros if not provided.
        second_round_home_odds: Dict mapping school name to marginal P(hosting
            round 2).  1A-4A only; pass empty dict or omit for 5A-7A.
        quarterfinals_home_odds: Dict mapping school name to marginal P(hosting
            the quarterfinal).  Defaults to all zeros if not provided.
        semifinals_home_odds: Dict mapping school name to marginal P(hosting
            the semifinal).  Defaults to all zeros if not provided.

    Returns:
        The number of rows written to the database.
    """
    coinflip_teams = coinflip_teams or set()
    first_round_home_odds = first_round_home_odds or {}
    bracket_odds = bracket_odds or {}
    second_round_home_odds = second_round_home_odds or {}
    quarterfinals_home_odds = quarterfinals_home_odds or {}
    semifinals_home_odds = semifinals_home_odds or {}
    _empty_bracket = BracketOdds("", 0.0, 0.0, 0.0, 0.0, 0.0)

    _empty_odds = StandingsOdds("", 0, 0, 0, 0, 0, 0, False, False)

    data_by_school = []
    for team in standings:
        o = odds.get(team.school, _empty_odds)
        b = bracket_odds.get(team.school, _empty_bracket)
        data_by_school.append(
            (
                team.school,
                season,
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
                0.0,  # odds_1st_weighted (not yet calculated)
                0.0,  # odds_2nd_weighted
                0.0,  # odds_3rd_weighted
                0.0,  # odds_4th_weighted
                o.p_playoffs,
                o.clinched,
                o.eliminated,
                b.second_round,
                b.quarterfinals,
                b.semifinals,
                b.finals,
                b.champion,
                0.0,  # odds_playoffs_weighted
                0.0,  # odds_second_round_weighted
                0.0,  # odds_quarterfinals_weighted
                0.0,  # odds_semifinals_weighted
                0.0,  # odds_finals_weighted
                0.0,  # odds_champion_weighted
                first_round_home_odds.get(team.school, 0.0),  # odds_first_round_home
                second_round_home_odds.get(team.school, 0.0),  # odds_second_round_home
                quarterfinals_home_odds.get(team.school, 0.0),  # odds_quarterfinals_home
                semifinals_home_odds.get(team.school, 0.0),  # odds_semifinals_home
                0.0,  # odds_first_round_home_weighted
                0.0,  # odds_second_round_home_weighted
                0.0,  # odds_quarterfinals_home_weighted
                0.0,  # odds_semifinals_home_weighted
                team.school in coinflip_teams,  # coin_flip_needed
            )
        )

    sql = """
        INSERT INTO region_standings (
            school, season, class, region,
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
        ON CONFLICT (school, season) DO UPDATE SET
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

    template = "(" + ", ".join(["%s"] * 41) + ")"
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
    remaining: list[RemainingGame],
    scenario_atoms: dict,
    complete_scenarios: list[dict],
) -> None:
    """Serialize and upsert pre-computed scenario data into ``region_scenarios``.

    Called once per pipeline run after ``determine_scenarios()`` and
    ``enumerate_division_scenarios()`` complete.  The frontend reads this table
    to render both display formats without re-running the tiebreaker engine.
    """
    logger = get_run_logger()
    logger.info(
        "Writing region scenarios for season %d, class %d, region %d (%d complete scenarios)",
        season,
        clazz,
        region,
        len(complete_scenarios),
    )

    remaining_json = Json(serialize_remaining_games(remaining))
    atoms_json = Json(serialize_scenario_atoms(scenario_atoms))
    scenarios_json = Json(serialize_complete_scenarios(complete_scenarios))

    sql = """
        INSERT INTO region_scenarios
            (season, class, region, computed_at, remaining_games, scenario_atoms, complete_scenarios)
        VALUES (%s, %s, %s, NOW(), %s, %s, %s)
        ON CONFLICT (season, class, region) DO UPDATE SET
            computed_at        = EXCLUDED.computed_at,
            remaining_games    = EXCLUDED.remaining_games,
            scenario_atoms     = EXCLUDED.scenario_atoms,
            complete_scenarios = EXCLUDED.complete_scenarios
    """
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (season, str(clazz), region, remaining_json, atoms_json, scenarios_json))
        conn.commit()


@task(retries=2, retry_delay_seconds=10, task_run_name="Get {season} Region Finish Scenarios for {region}-{clazz}A")
def get_region_finish_scenarios(clazz: int, region: int, season: int, debug=False):
    """
    Enumerate all remaining outcomes for a (class, region, season), apply the tiebreakers,
    and aggregate seeding odds + human-readable scenario explanations.
    """
    logger = get_run_logger()

    teams = fetch_region_teams(clazz, region, season)
    if not teams:
        raise SystemExit("No teams found.")
    completed = fetch_completed_pairs(teams, season)
    remaining = fetch_remaining_pairs(teams, season)

    r = determine_scenarios(teams, completed, remaining, debug=debug)

    odds = determine_odds(teams, r.first_counts, r.second_counts, r.third_counts, r.fourth_counts, r.denom)

    num_rounds = fetch_num_rounds(clazz, season)
    bracket = compute_bracket_odds(num_rounds, odds)

    home_seeds = fetch_first_round_home_seeds(clazz, region, season)
    first_round_home = compute_first_round_home_odds(home_seeds, odds)

    slots = fetch_all_format_slots(clazz, season)
    second_round_home = compute_second_round_home_odds(region, odds, slots) if clazz <= 4 else {}
    quarterfinals_home = compute_quarterfinal_home_odds(region, odds, slots, season)
    semifinals_home = compute_semifinal_home_odds(region, odds, slots, season)

    region_standings = fetch_region_standings(clazz, region, season)

    logger.info("Writing region standings for season %d, class %d, region %d", season, clazz, region)
    logger.info("Region standings: %s", region_standings)
    logger.info("Odds: %s", odds)
    write_region_standings(
        region_standings,
        odds,
        clazz,
        region,
        season,
        r.coinflip_teams,
        first_round_home,
        bracket,
        second_round_home,
        quarterfinals_home,
        semifinals_home,
    )

    scenario_atoms = build_scenario_atoms(teams, completed, remaining)
    complete_scenarios = enumerate_division_scenarios(teams, completed, remaining, scenario_atoms=scenario_atoms)
    write_region_scenarios(clazz, region, season, remaining, scenario_atoms, complete_scenarios)

    return scenario_atoms


@flow(name="Region Scenarios Data Flow")
def region_scenarios_data_flow(
    season: int = 2025,
    clazz: int | None = None,
    region: int | None = None,
) -> dict[str, object]:
    """Region Scenarios Data Flow"""
    logger = get_run_logger()
    logger.info(
        "Running region scenarios data flow for season %d, class %d, region %d",
        season,
        clazz,
        region,
    )
    scenario_dicts: dict = {}
    if clazz is None or region is None:
        for c in [1, 2, 3, 4]:
            scenario_dicts[c] = {}
            for r in [1, 2, 3, 4, 5, 6, 7, 8]:
                scenario_dicts[c][r] = get_region_finish_scenarios(c, r, season)
        for c in [5, 6, 7]:
            scenario_dicts[c] = {}
            for r in [1, 2, 3, 4]:
                scenario_dicts[c][r] = get_region_finish_scenarios(c, r, season)
    else:
        scenario_dicts.setdefault(clazz, {})[region] = get_region_finish_scenarios(clazz, region, season)
    return scenario_dicts
