"""Prefect tasks and flow for computing region standings scenarios.

Reads completed and remaining games from the DB, calls ``determine_scenarios()``
and ``determine_odds()`` from ``scenarios.py``, and writes results to the
``region_standings`` table.
"""

from dataclasses import dataclass as _dataclass

from prefect import flow, get_run_logger, task
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
    bracket_odds: dict[str, BracketOdds] | None = None,
    bracket_odds_weighted: dict[str, BracketOdds] | None = None,
    home_odds: HomeOdds | None = None,
    home_odds_weighted: HomeOdds | None = None,
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
    _empty_bracket = BracketOdds("", 0.0, 0.0, 0.0, 0.0, 0.0)
    _empty_home = HomeOdds(
        first_round={}, second_round={}, quarterfinals={}, semifinals={}
    )
    ho = home_odds or _empty_home
    how = home_odds_weighted or _empty_home

    _empty_odds = StandingsOdds("", 0, 0, 0, 0, 0, 0, False, False)

    data_by_school = []
    for team in standings:
        o = odds.get(team.school, _empty_odds)
        b = bracket_odds.get(team.school, _empty_bracket)
        bw = bracket_odds_weighted.get(team.school, _empty_bracket)
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
                0.0,  # odds_1st_weighted (seeding weights not yet implemented)
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
                bw.second_round,   # odds_playoffs_weighted (= p_playoffs × win odds)
                bw.second_round,   # odds_second_round_weighted
                bw.quarterfinals,  # odds_quarterfinals_weighted
                bw.semifinals,     # odds_semifinals_weighted
                bw.finals,         # odds_finals_weighted
                bw.champion,       # odds_champion_weighted
                ho.first_round.get(team.school, 0.0),    # odds_first_round_home
                ho.second_round.get(team.school, 0.0),   # odds_second_round_home
                ho.quarterfinals.get(team.school, 0.0),  # odds_quarterfinals_home
                ho.semifinals.get(team.school, 0.0),     # odds_semifinals_home
                how.first_round.get(team.school, 0.0),    # odds_first_round_home_weighted
                how.second_round.get(team.school, 0.0),   # odds_second_round_home_weighted
                how.quarterfinals.get(team.school, 0.0),  # odds_quarterfinals_home_weighted
                how.semifinals.get(team.school, 0.0),     # odds_semifinals_home_weighted
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
        season, clazz, region, len(complete_scenarios), margin_sensitive,
    )

    remaining_json = Json(serialize_remaining_games(remaining))
    atoms_json = Json(serialize_scenario_atoms(scenario_atoms))
    scenarios_json = Json(serialize_complete_scenarios(complete_scenarios))

    scenarios_sql = """
        INSERT INTO region_scenarios
            (season, class, region, computed_at, remaining_games, scenario_atoms, complete_scenarios)
        VALUES (%s, %s, %s, NOW(), %s, %s, %s)
        ON CONFLICT (season, class, region) DO UPDATE SET
            computed_at        = EXCLUDED.computed_at,
            remaining_games    = EXCLUDED.remaining_games,
            scenario_atoms     = EXCLUDED.scenario_atoms,
            complete_scenarios = EXCLUDED.complete_scenarios
    """

    state_sql = """
        INSERT INTO region_computation_state
            (season, class, region, r_remaining, margin_sensitive, margin_compute_status,
             computed_at, margin_computed_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
        ON CONFLICT (season, class, region) DO UPDATE SET
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
            cur.execute(scenarios_sql, (season, str(clazz), region, remaining_json, atoms_json, scenarios_json))
            cur.execute(state_sql, (season, clazz, region, r_remaining, margin_sensitive,
                                    margin_compute_status, margin_computed_at))
        conn.commit()


@task(task_run_name="Upgrade {season} Region Scenarios (margin-sensitive) for {region}-{clazz}A")
def upgrade_region_scenarios(
    clazz: int,
    region: int,
    season: int,
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
        region, clazz, season,
    )

    precomputed = enumerate_outcomes(teams, completed, remaining, pa_win=pa_win,
                                     base_margin_default=base_margin_default)
    scenario_atoms = build_scenario_atoms(teams, completed, remaining,
                                          pa_win=pa_win, base_margin_default=base_margin_default,
                                          precomputed=precomputed)
    complete_scenarios = enumerate_division_scenarios(teams, completed, remaining,
                                                      scenario_atoms=scenario_atoms,
                                                      pa_win=pa_win,
                                                      base_margin_default=base_margin_default,
                                                      precomputed=precomputed)

    write_region_scenarios(
        clazz, region, season, remaining, scenario_atoms, complete_scenarios,
        r_remaining=len(remaining),
        margin_sensitive=True,
        margin_compute_status="complete",
        margin_computed_at_now=True,
    )
    logger.info("Upgrade complete for region %d-%dA season %d", region, clazz, season)


# R thresholds for margin computation mode
_R_ALWAYS_MARGIN = 4   # R ≤ this: always full margin, synchronous
_R_BACKGROUND_MAX = 6  # R ≤ this (and > _R_ALWAYS_MARGIN): win/loss first, upgrade in background
                        # R > this: win/loss only, permanently


@task(retries=2, retry_delay_seconds=10, task_run_name="Get {season} Region Finish Scenarios for {region}-{clazz}A")
def get_region_finish_scenarios(clazz: int, region: int, season: int):
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

    r = determine_scenarios(teams, completed, remaining)

    odds = determine_odds(teams, r.first_counts, r.second_counts, r.third_counts, r.fourth_counts, r.denom)

    num_rounds = fetch_num_rounds(clazz, season)
    bracket = compute_bracket_odds(num_rounds, odds)

    home_seeds = fetch_first_round_home_seeds(clazz, region, season)
    first_round_home_marginal = compute_first_round_home_odds(home_seeds, odds)

    slots = fetch_all_format_slots(clazz, season)
    second_round_home_marginal = (
        compute_second_round_home_odds(region, odds, slots, season) if clazz <= 4 else {}
    )
    quarterfinals_home_marginal = compute_quarterfinal_home_odds(region, odds, slots, season)
    semifinals_home_marginal = compute_semifinal_home_odds(region, odds, slots, season)

    # Weighted bracket advancement odds (win_prob_fn not yet wired from DB;
    # defaults to equal_matchup_prob, giving the same values as `bracket`).
    bracket_weighted = compute_bracket_advancement_odds(region, odds, slots)

    # Convert marginal home odds to conditional: P(hosts | reaches).
    # If a team cannot reach a round (advancement == 0) store 0.0.
    _empty_bracket = BracketOdds("", 0.0, 0.0, 0.0, 0.0, 0.0)

    def _safe_cond(marginal: float, advancement: float) -> float:
        """Return marginal / advancement, or 0.0 when advancement is zero."""
        return marginal / advancement if advancement > 0 else 0.0

    first_round_home_cond = {
        school: _safe_cond(m, odds[school].p_playoffs if school in odds else 0.0)
        for school, m in first_round_home_marginal.items()
    }
    second_round_home_cond = {
        school: _safe_cond(m, bracket.get(school, _empty_bracket).second_round)
        for school, m in second_round_home_marginal.items()
    } if clazz <= 4 else {}
    quarterfinals_home_cond = {
        school: _safe_cond(m, bracket.get(school, _empty_bracket).quarterfinals)
        for school, m in quarterfinals_home_marginal.items()
    }
    semifinals_home_cond = {
        school: _safe_cond(m, bracket.get(school, _empty_bracket).semifinals)
        for school, m in semifinals_home_marginal.items()
    }

    # Weighted conditional home odds (same win_prob_fn caveat as bracket_weighted).
    second_round_home_marginal_w = (
        compute_second_round_home_odds(region, odds, slots, season) if clazz <= 4 else {}
    )
    quarterfinals_home_marginal_w = compute_quarterfinal_home_odds(region, odds, slots, season)
    semifinals_home_marginal_w = compute_semifinal_home_odds(region, odds, slots, season)

    first_round_home_cond_w = first_round_home_cond  # same until win_prob_fn is wired
    second_round_home_cond_w = {
        school: _safe_cond(m, bracket_weighted.get(school, _empty_bracket).second_round)
        for school, m in second_round_home_marginal_w.items()
    } if clazz <= 4 else {}
    quarterfinals_home_cond_w = {
        school: _safe_cond(m, bracket_weighted.get(school, _empty_bracket).quarterfinals)
        for school, m in quarterfinals_home_marginal_w.items()
    }
    semifinals_home_cond_w = {
        school: _safe_cond(m, bracket_weighted.get(school, _empty_bracket).semifinals)
        for school, m in semifinals_home_marginal_w.items()
    }

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
        bracket,
        bracket_weighted,
        HomeOdds(
            first_round=first_round_home_cond,
            second_round=second_round_home_cond,
            quarterfinals=quarterfinals_home_cond,
            semifinals=semifinals_home_cond,
        ),
        HomeOdds(
            first_round=first_round_home_cond_w,
            second_round=second_round_home_cond_w,
            quarterfinals=quarterfinals_home_cond_w,
            semifinals=semifinals_home_cond_w,
        ),
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
            clazz, region, season, remaining, scenario_atoms, complete_scenarios,
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
            clazz, region, season, remaining, scenario_atoms, complete_scenarios,
            r_remaining=R,
            margin_sensitive=False,
            margin_compute_status="pending",
        )
        # Submit background upgrade — runs full margin enumeration asynchronously.
        upgrade_region_scenarios.submit(
            clazz, region, season, teams, completed, remaining,
        )
    else:
        # R ≥ 7: win/loss-only permanently.
        precomputed_wl = enumerate_outcomes(teams, completed, remaining, ignore_margins=True)
        scenario_atoms = build_scenario_atoms(teams, completed, remaining, precomputed=precomputed_wl)
        complete_scenarios = enumerate_division_scenarios(
            teams, completed, remaining, scenario_atoms=scenario_atoms, precomputed=precomputed_wl
        )
        write_region_scenarios(
            clazz, region, season, remaining, scenario_atoms, complete_scenarios,
            r_remaining=R,
            margin_sensitive=False,
            margin_compute_status="skipped",
        )

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
