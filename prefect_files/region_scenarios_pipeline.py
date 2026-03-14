from __future__ import annotations

from collections import defaultdict

from prefect import flow, get_run_logger, task
from psycopg2.extras import Json, execute_values

from prefect_files.data_classes import CompletedGame, RawCompletedGame, RemainingGame, Standings, StandingsOdds
from prefect_files.data_helpers import get_completed_games
from prefect_files.database_helpers import get_database_connection
from prefect_files.scenarios import determine_odds, determine_scenarios

# -------------------------
# Prefect Tasks
# -------------------------


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Region Teams for {region}-{clazz}A")
def fetch_region_teams(clazz: int, region: int, season: int) -> list[str]:
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT school FROM schools WHERE class=%s AND region=%s AND season=%s ORDER BY school",
                (clazz, region, season),
            )
            return [r[0] for r in cur.fetchall()]


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Completed Region Games for {teams}")
def fetch_completed_pairs(teams: list[str], season: int) -> list[CompletedGame]:
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
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT school, class, region, season, wins, losses, ties, region_wins, region_losses, region_ties "
                "FROM get_standings_for_region(%s, %s)",
                (clazz, region),
            )
            return [Standings(*r) for r in cur.fetchall()]


@task(task_run_name="Write {season} Region Standings for {region}-{clazz}A")
def write_region_standings(
    standings: list[Standings],
    odds: dict[str, StandingsOdds],
    scenarios: defaultdict,
    clazz: int,
    region: int,
    season: int,
):
    def seed_scenarios_for(scenarios, school):
        m = scenarios.setdefault(school, {})
        if m and not all(isinstance(k, int) for k in m.keys()):
            scenarios[school] = {int(k): v for k, v in m.items()}
            m = scenarios[school]
        for k in (1, 2, 3, 4):
            m.setdefault(k, [])
        return m

    _empty_odds = StandingsOdds("", 0, 0, 0, 0, 0, 0, False, False)

    data_by_school = []
    for team in standings:
        seed_scenarios = seed_scenarios_for(scenarios, team.school)
        o = odds.get(team.school, _empty_odds)
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
                Json(seed_scenarios[1]),
                Json(seed_scenarios[2]),
                Json(seed_scenarios[3]),
                Json(seed_scenarios[4]),
                o.p_playoffs,
                o.clinched,
                o.eliminated,
                0.0,  # odds_second_round
                0.0,  # odds_third_round
                0.0,  # odds_semifinals
                0.0,  # odds_finals
                0.0,  # odds_champion
                0.0,  # odds_playoffs_weighted
                0.0,  # odds_second_round_weighted
                0.0,  # odds_third_round_weighted
                0.0,  # odds_semifinals_weighted
                0.0,  # odds_finals_weighted
                0.0,  # odds_champion_weighted
                0.0,  # odds_first_round_home
                0.0,  # odds_second_round_home
                0.0,  # odds_third_round_home
                0.0,  # odds_semifinals_home
                0.0,  # odds_first_round_home_weighted
                0.0,  # odds_second_round_home_weighted
                0.0,  # odds_third_round_home_weighted
                0.0,  # odds_semifinals_home_weighted
                False,  # coin_flip_needed
            )
        )

    sql = """
        INSERT INTO region_standings (
            school, season, class, region,
            wins, losses, ties, region_wins, region_losses, region_ties,
            odds_1st, odds_2nd, odds_3rd, odds_4th,
            odds_1st_weighted, odds_2nd_weighted, odds_3rd_weighted, odds_4th_weighted,
            scenarios_1st, scenarios_2nd, scenarios_3rd, scenarios_4th,
            odds_playoffs, clinched, eliminated,
            odds_second_round, odds_third_round, odds_semifinals, odds_finals, odds_champion,
            odds_playoffs_weighted, odds_second_round_weighted, odds_third_round_weighted,
            odds_semifinals_weighted, odds_finals_weighted, odds_champion_weighted,
            odds_first_round_home, odds_second_round_home, odds_third_round_home, odds_semifinals_home,
            odds_first_round_home_weighted, odds_second_round_home_weighted,
            odds_third_round_home_weighted, odds_semifinals_home_weighted,
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
            scenarios_1st = EXCLUDED.scenarios_1st,
            scenarios_2nd = EXCLUDED.scenarios_2nd,
            scenarios_3rd = EXCLUDED.scenarios_3rd,
            scenarios_4th = EXCLUDED.scenarios_4th,
            odds_playoffs = EXCLUDED.odds_playoffs,
            clinched      = EXCLUDED.clinched,
            eliminated    = EXCLUDED.eliminated,
            odds_second_round = EXCLUDED.odds_second_round,
            odds_third_round  = EXCLUDED.odds_third_round,
            odds_semifinals   = EXCLUDED.odds_semifinals,
            odds_finals       = EXCLUDED.odds_finals,
            odds_champion     = EXCLUDED.odds_champion,
            odds_playoffs_weighted = EXCLUDED.odds_playoffs_weighted,
            odds_second_round_weighted = EXCLUDED.odds_second_round_weighted,
            odds_third_round_weighted  = EXCLUDED.odds_third_round_weighted,
            odds_semifinals_weighted   = EXCLUDED.odds_semifinals_weighted,
            odds_finals_weighted       = EXCLUDED.odds_finals_weighted,
            odds_champion_weighted     = EXCLUDED.odds_champion_weighted,
            odds_first_round_home = EXCLUDED.odds_first_round_home,
            odds_second_round_home = EXCLUDED.odds_second_round_home,
            odds_third_round_home = EXCLUDED.odds_third_round_home,
            odds_semifinals_home = EXCLUDED.odds_semifinals_home,
            odds_first_round_home_weighted = EXCLUDED.odds_first_round_home_weighted,
            odds_second_round_home_weighted = EXCLUDED.odds_second_round_home_weighted,
            odds_third_round_home_weighted = EXCLUDED.odds_third_round_home_weighted,
            odds_semifinals_home_weighted = EXCLUDED.odds_semifinals_home_weighted,
            coin_flip_needed = EXCLUDED.coin_flip_needed
        ;
    """

    template = "(" + ", ".join(["%s"] * 45) + ")"
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, data_by_school, template=template, page_size=500)
        conn.commit()

    return len(data_by_school)


# -------------------------
# Main task + flow
# -------------------------


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

    first_counts, second_counts, third_counts, fourth_counts, denom, minimized_scenarios = determine_scenarios(
        teams, completed, remaining, debug=debug
    )

    odds = determine_odds(teams, first_counts, second_counts, third_counts, fourth_counts, denom)

    region_standings = fetch_region_standings(clazz, region, season)

    logger.info("Writing region standings for season %d, class %d, region %d", season, clazz, region)
    logger.info("Region standings: %s", region_standings)
    logger.info("Odds: %s", odds)
    logger.info("Minimized scenarios: %s", minimized_scenarios)

    write_region_standings(region_standings, odds, minimized_scenarios, clazz, region, season)

    return minimized_scenarios


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
