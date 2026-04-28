"""Prefect tasks and flow for updating playoff bracket standings after each round.

After each playoff round, this pipeline reads actual game results, rebuilds
deterministic seeding odds (alive teams get 1.0 for their actual seed;
eliminated teams get 0.0), and re-runs the existing bracket/home-odds helpers
to write updated snapshots to ``region_standings``.

The flow is self-backfilling: running it on a past season produces one snapshot
per playoff round date, equivalent to running it live after each round.
"""

from prefect import flow, get_run_logger, task

from backend.helpers.bracket_helpers import survivors_from_games
from backend.helpers.data_classes import (
    Game,
    StandingsOdds,
)
from backend.helpers.database_helpers import get_database_connection
from backend.helpers.win_probability import EloConfig, compute_elo_ratings, make_matchup_prob_fn
from backend.prefect.region_scenarios_pipeline import (
    RegionSeedingData,
    fetch_all_season_games,
    fetch_all_season_schools,
    fetch_completed_pairs,
    fetch_region_teams,
    get_region_finish_scenarios,
)

# ---------------------------------------------------------------------------
# Task A — fetch actual playoff seedings from region_standings
# ---------------------------------------------------------------------------


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Actual Seedings for {clazz}A")
def fetch_actual_seedings(season: int, clazz: int) -> dict[str, tuple[int, int]]:
    """Return school → (region, actual_seed) for all clinched playoff teams.

    Queries the most recent pre-playoff region_standings snapshot where each
    team is clinched, and infers their actual seed from the odds column closest
    to 1.0.

    Args:
        season: Football season year.
        clazz:  MHSAA classification (1–7).

    Returns:
        Dict mapping school name to (region, seed) for all playoff-qualifying
        teams in this class.  Teams that did not qualify are excluded.
    """
    sql = """
        SELECT rs.school, rs.region,
            CASE
                WHEN rs.odds_1st  > 0.99 THEN 1
                WHEN rs.odds_2nd  > 0.99 THEN 2
                WHEN rs.odds_3rd  > 0.99 THEN 3
                WHEN rs.odds_4th  > 0.99 THEN 4
            END AS seed
        FROM region_standings rs
        WHERE rs.season  = %s
          AND rs.class   = %s
          AND rs.clinched = TRUE
          AND rs.as_of_date = (
              SELECT MAX(rs2.as_of_date)
              FROM region_standings rs2
              WHERE rs2.season  = %s
                AND rs2.class   = %s
                AND rs2.clinched = TRUE
          )
    """
    result: dict[str, tuple[int, int]] = {}
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (season, clazz, season, clazz))
            for school, region, seed in cur.fetchall():
                if seed is not None:
                    result[school] = (region, seed)
    return result


# ---------------------------------------------------------------------------
# Task B — fetch completed playoff games
# ---------------------------------------------------------------------------


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Playoff Games for {clazz}A")
def fetch_completed_playoff_games(season: int, clazz: int) -> list[Game]:
    """Return all completed school-perspective playoff Game rows for this class.

    Args:
        season: Football season year.
        clazz:  MHSAA classification (1–7).

    Returns:
        List of ``Game`` objects sorted by date, one row per school per game.
    """
    sql = """
        SELECT g.school, g.date, g.season, g.location_id, g.points_for,
               g.points_against, g.round, g.kickoff_time, g.opponent,
               g.result, g.game_status, g.source, g.location,
               g.region_game, g.final, g.overtime
        FROM games_effective g
        JOIN school_seasons ss ON ss.school = g.school AND ss.season = g.season
        WHERE g.season = %s
          AND g.final  = TRUE
          AND g.round  IS NOT NULL
          AND ss.class = %s
        ORDER BY g.date
    """
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (season, clazz))
            rows = cur.fetchall()
    return [Game.from_db_tuple(row) for row in rows]


# ---------------------------------------------------------------------------
# Task C — build RegionSeedingData with deterministic playoff odds
# ---------------------------------------------------------------------------


@task(task_run_name="Build Playoff Seeding Data {season} {region}-{clazz}A")
def build_playoff_region_data(
    clazz: int,
    region: int,
    season: int,
    school_to_seed: dict[str, tuple[int, int]],
    playoff_games: list[Game],
) -> RegionSeedingData:
    """Construct a RegionSeedingData bundle with deterministic seeding odds.

    Identifies still-alive teams via ``survivors_from_games``, then sets
    each team's seeding probability to exactly 1.0 for their actual seed
    (alive teams) or 0.0 across the board (eliminated / non-playoff teams).
    Completed region games are fetched so ``write_region_standings`` can
    display accurate W/L records.

    Args:
        clazz:          MHSAA classification (1–7).
        region:         Region number within the class.
        season:         Football season year.
        school_to_seed: All clinched teams for this class, school → (region, seed).
        playoff_games:  Completed playoff Game rows for this class up to some date.

    Returns:
        ``RegionSeedingData`` with deterministic odds and no remaining games.
    """
    teams = fetch_region_teams(clazz, region, season)
    completed_region = fetch_completed_pairs(teams, season)

    # Teams in this region with a known playoff seed.
    region_seed_map = {school: seed for school, (r, seed) in school_to_seed.items() if r == region}

    # Derive alive teams using bracket_helpers — handles multi-round history.
    region_school_to_seed = {s: (r, seed) for s, (r, seed) in school_to_seed.items() if r == region}
    known_survivors, _ = survivors_from_games(playoff_games, region_school_to_seed)
    # known_survivors is a set of (region, seed) tuples.
    alive_seeds = {seed for (r, seed) in known_survivors if r == region}

    odds: dict[str, StandingsOdds] = {}
    for school in teams:
        actual_seed = region_seed_map.get(school)
        is_alive = actual_seed is not None and actual_seed in alive_seeds

        if is_alive:
            odds[school] = StandingsOdds(
                school=school,
                p1=1.0 if actual_seed == 1 else 0.0,
                p2=1.0 if actual_seed == 2 else 0.0,
                p3=1.0 if actual_seed == 3 else 0.0,
                p4=1.0 if actual_seed == 4 else 0.0,
                p_playoffs=1.0,
                final_playoffs=1.0,
                clinched=True,
                eliminated=False,
            )
        else:
            odds[school] = StandingsOdds(
                school=school,
                p1=0.0,
                p2=0.0,
                p3=0.0,
                p4=0.0,
                p_playoffs=0.0,
                final_playoffs=0.0,
                clinched=False,
                eliminated=True,
            )

    return RegionSeedingData(
        odds=odds,
        odds_weighted=odds,
        coinflip_teams=set(),
        teams=teams,
        completed=completed_region,
        remaining=[],
    )


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------


@flow(name="Playoff Bracket Update")
def playoff_bracket_update(season: int | None = None) -> None:
    """Update region_standings with post-round bracket and home-game odds.

    Reads all completed playoff games for the season, groups them by round
    date, and writes one ``region_standings`` snapshot per playoff round per
    class/region.  Running on a past season produces a full historical record
    of bracket odds after each round — no separate backfill flow needed.

    Args:
        season: Football season year (defaults to the current calendar year).
    """
    from datetime import date as _date

    if season is None:
        season = _date.today().year
    logger = get_run_logger()

    all_games = fetch_all_season_games(season)
    all_schools = fetch_all_season_schools(season)
    elo_cfg = EloConfig()
    elo_ratings, _, _ = compute_elo_ratings(all_games, all_schools, elo_cfg)

    class_regions: dict[int, list[int]] = {c: list(range(1, 9)) if c <= 4 else list(range(1, 5)) for c in range(1, 8)}

    for clazz, regions in class_regions.items():
        school_to_seed = fetch_actual_seedings(season, clazz)
        if not school_to_seed:
            logger.info("No clinched seedings found for %dA season %d — skipping.", clazz, season)
            continue

        playoff_games = fetch_completed_playoff_games(season, clazz)
        if not playoff_games:
            logger.info("No completed playoff games for %dA season %d — skipping.", clazz, season)
            continue

        playoff_dates = sorted({g.date for g in playoff_games})
        logger.info("%dA season %d: %d playoff dates to process.", clazz, season, len(playoff_dates))

        for playoff_date in playoff_dates:
            games_to_date = [g for g in playoff_games if g.date <= playoff_date]

            seeding: dict[int, RegionSeedingData] = {}
            for region in regions:
                seeding[region] = build_playoff_region_data(
                    clazz,
                    region,
                    season,
                    school_to_seed,
                    games_to_date,
                )

            # Build Elo-based matchup probability function from deterministic odds.
            class_weighted_odds = {r: seeding[r].odds_weighted for r in regions}
            matchup_fn = make_matchup_prob_fn(elo_ratings, class_weighted_odds, elo_cfg)

            for region in regions:
                get_region_finish_scenarios(
                    clazz,
                    region,
                    season,
                    seeding[region],
                    matchup_fn,
                    as_of_date=playoff_date,
                )

        logger.info("%dA season %d: playoff bracket update complete.", clazz, season)
