"""Prefect tasks and flow for updating playoff bracket standings after each round.

After each playoff round, this pipeline reads actual game results, rebuilds
deterministic "alive" odds for the bracket math (alive teams get 1.0 for their
actual seed; eliminated teams get 0.0), and re-runs the existing
bracket/home-odds helpers to write updated snapshots to ``region_standings``.
The seeding odds it stores are each team's final regular-season seeding, not
the alive markers: a team knocked out in the quarterfinals is still the No. 2
seed that made the playoffs, and its bracket odds still show the rounds it
reached.

The flow is self-backfilling: running it on a past season produces one snapshot
per playoff round date, equivalent to running it live after each round.
"""

import bisect
from datetime import date

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
    fetch_num_rounds,
    fetch_region_teams,
    get_region_finish_scenarios,
)

# ---------------------------------------------------------------------------
# Task A — fetch actual playoff seedings from region_standings
# ---------------------------------------------------------------------------


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Actual Seedings for {clazz}A")
def fetch_actual_seedings(season: int, clazz: int, before: date | None = None) -> dict[str, tuple[int, int]]:
    """Return school → (region, actual_seed) for all clinched playoff teams.

    For each school, reads its newest ``region_standings`` row (before
    *before*, the class's first playoff date, when given) in which it is
    clinched with a locked seed, and takes that seed. Looking per school and
    before the playoffs keeps every playoff team's seed even when a later
    snapshot (or one written by an older version of this pipeline) stored a
    knocked-out team without it.

    Args:
        season: Football season year.
        clazz:  MHSAA classification (1–7).
        before: Only consider snapshots dated strictly before this date.

    Returns:
        Dict mapping school name to (region, seed) for all playoff-qualifying
        teams in this class.  Teams that did not qualify are excluded.
    """
    sql = """
        SELECT DISTINCT ON (rs.school) rs.school, rs.region,
            CASE
                WHEN rs.odds_1st  > 0.99 THEN 1
                WHEN rs.odds_2nd  > 0.99 THEN 2
                WHEN rs.odds_3rd  > 0.99 THEN 3
                WHEN rs.odds_4th  > 0.99 THEN 4
            END AS seed
        FROM region_standings rs
        JOIN school_seasons active
          ON active.school = rs.school AND active.season = rs.season AND active.is_active
        WHERE rs.season  = %s
          AND rs.class   = %s
          AND rs.clinched = TRUE
          AND (rs.odds_1st > 0.99 OR rs.odds_2nd > 0.99 OR rs.odds_3rd > 0.99 OR rs.odds_4th > 0.99)
          AND (%s::date IS NULL OR rs.as_of_date < %s::date)
        ORDER BY rs.school, rs.as_of_date DESC
    """
    result: dict[str, tuple[int, int]] = {}
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (season, clazz, before, before))
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


def playoff_round_odds(
    teams: list[str],
    region_seed_map: dict[str, int],
    alive_seeds: set[int],
) -> tuple[dict[str, StandingsOdds], dict[str, StandingsOdds]]:
    """Build one region's odds after a playoff round: (alive, standings).

    *alive* drives the bracket math: a team still in the bracket gets 1.0 for
    its seed and for the playoffs; a knocked-out or non-playoff team gets 0.0
    across the board, so it drops out of future rounds.

    *standings* is what ``region_standings`` stores and readers see: every
    playoff team keeps its final seeding (1.0 for its seed and the playoffs)
    for the rest of the season, win or lose; teams that missed the playoffs
    stay at 0.0. ``clinched`` marks a playoff team and ``eliminated`` a team
    no longer alive, in both.

    Args:
        teams:           Every school in the region.
        region_seed_map: Playoff teams in the region, school → seed.
        alive_seeds:     Seeds from this region still alive in the bracket.
    """
    alive: dict[str, StandingsOdds] = {}
    standings: dict[str, StandingsOdds] = {}

    def seeded(school: str, seed: int, eliminated: bool) -> StandingsOdds:
        """Odds of a playoff team holding *seed*."""
        return StandingsOdds(
            school=school,
            p1=1.0 if seed == 1 else 0.0,
            p2=1.0 if seed == 2 else 0.0,
            p3=1.0 if seed == 3 else 0.0,
            p4=1.0 if seed == 4 else 0.0,
            p_playoffs=1.0,
            final_playoffs=1.0,
            clinched=True,
            eliminated=eliminated,
        )

    def zeroed(school: str, made_playoffs: bool) -> StandingsOdds:
        """Odds of a team out of the bracket (or never in it)."""
        return StandingsOdds(
            school=school,
            p1=0.0,
            p2=0.0,
            p3=0.0,
            p4=0.0,
            p_playoffs=0.0,
            final_playoffs=0.0,
            clinched=made_playoffs,
            eliminated=True,
        )

    for school in teams:
        seed = region_seed_map.get(school)
        if seed is None:
            alive[school] = standings[school] = zeroed(school, made_playoffs=False)
        elif seed in alive_seeds:
            alive[school] = standings[school] = seeded(school, seed, eliminated=False)
        else:
            alive[school] = zeroed(school, made_playoffs=True)
            standings[school] = seeded(school, seed, eliminated=True)
    return alive, standings


@task(task_run_name="Build Playoff Seeding Data {season} {region}-{clazz}A")
def build_playoff_region_data(
    clazz: int,
    region: int,
    season: int,
    school_to_seed: dict[str, tuple[int, int]],
    playoff_games: list[Game],
) -> RegionSeedingData:
    """Construct a RegionSeedingData bundle with deterministic seeding odds.

    Identifies still-alive teams via ``survivors_from_games``, then builds
    the alive odds the bracket math runs on and the seeding odds to store
    (see ``playoff_round_odds``). Completed region games are fetched so
    ``write_region_standings`` can display accurate W/L records.

    Args:
        clazz:          MHSAA classification (1–7).
        region:         Region number within the class.
        season:         Football season year.
        school_to_seed: All clinched teams for this class, school → (region, seed).
        playoff_games:  Completed playoff Game rows for this class up to some date.

    Returns:
        ``RegionSeedingData`` with deterministic odds and no remaining games.
    """
    teams = fetch_region_teams.fn(clazz, region, season)
    completed_region = fetch_completed_pairs.fn(teams, season)

    # Teams in this region with a known playoff seed.
    region_seed_map = {school: seed for school, (r, seed) in school_to_seed.items() if r == region}

    # Derive alive teams using bracket_helpers — handles multi-round history.
    region_school_to_seed = {s: (r, seed) for s, (r, seed) in school_to_seed.items() if r == region}
    known_survivors, _ = survivors_from_games(playoff_games, region_school_to_seed)
    # known_survivors is a set of (region, seed) tuples.
    alive_seeds = {seed for (r, seed) in known_survivors if r == region}

    odds, standings = playoff_round_odds(teams, region_seed_map, alive_seeds)

    return RegionSeedingData(
        odds=odds,
        odds_weighted=odds,
        coinflip_teams=set(),
        teams=teams,
        completed=completed_region,
        remaining=[],
        standings_odds=standings,
        standings_odds_weighted=standings,
    )


# ---------------------------------------------------------------------------
# Task D — clear snapshots that would shadow the playoff ones
# ---------------------------------------------------------------------------

# Every per-class snapshot table, with how each stores ``class``.
_SNAPSHOT_TABLES = (
    ("region_standings", int),
    ("region_computation_state", int),
    ("region_scenarios", str),
)


@task(retries=2, retry_delay_seconds=10, task_run_name="Clear stale {season} {clazz}A playoff-season snapshots")
def clear_stale_playoff_snapshots(
    season: int, clazz: int, first_playoff_date: date, playoff_dates: list[date]
) -> dict[str, int]:
    """Delete a class's snapshots dated in its playoffs but not on one of its playoff dates.

    Readers take the newest snapshot on or before a date, so a regular-season
    style row dated after the class's last playoff game (say, one written for
    another class's later championship date by a run that didn't yet skip
    classes in the playoffs) hides the playoff update's final row. Once a
    class's playoffs start, only this flow writes its snapshots, on its own
    playoff dates, so any other date from the first playoff game on is stale.

    Args:
        season:             Football season year.
        clazz:              MHSAA classification (1–7).
        first_playoff_date: Date of the class's first completed playoff game.
        playoff_dates:      Every date this flow writes for the class.

    Returns:
        Rows deleted per table.
    """
    deleted: dict[str, int] = {}
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            for table, class_type in _SNAPSHOT_TABLES:
                cur.execute(
                    f"DELETE FROM {table} WHERE season = %s AND class = %s "  # noqa: S608 -- fixed table names
                    "AND as_of_date >= %s AND NOT (as_of_date = ANY(%s))",
                    (season, class_type(clazz), first_playoff_date, list(playoff_dates)),
                )
                deleted[table] = cur.rowcount
        conn.commit()
    return deleted


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
    elo_ratings, _, elo_snapshots = compute_elo_ratings(all_games, all_schools, elo_cfg)
    snapshot_dates = [snap[0] for snap in elo_snapshots]

    class_regions: dict[int, list[int]] = {c: list(range(1, 9)) if c <= 4 else list(range(1, 5)) for c in range(1, 8)}

    for clazz, regions in class_regions.items():
        playoff_games = fetch_completed_playoff_games(season, clazz)
        if not playoff_games:
            logger.info("No completed playoff games for %dA season %d — skipping.", clazz, season)
            continue

        # Seeds come from the regular season's final snapshots, never from a
        # playoff-date row this flow wrote on an earlier run.
        first_playoff_date = min(g.date for g in playoff_games)
        school_to_seed = fetch_actual_seedings(season, clazz, before=first_playoff_date)
        if not school_to_seed:
            logger.info("No clinched seedings found for %dA season %d — skipping.", clazz, season)
            continue

        num_rounds = fetch_num_rounds(clazz, season)
        playoff_dates = sorted({g.date for g in playoff_games})
        logger.info("%dA season %d: %d playoff dates to process.", clazz, season, len(playoff_dates))

        deleted = clear_stale_playoff_snapshots(season, clazz, first_playoff_date, playoff_dates)
        if any(deleted.values()):
            logger.info("%dA season %d: cleared stale playoff-season snapshots %s.", clazz, season, deleted)

        round_snapshots: dict[int, dict[int, dict[str, StandingsOdds]]] = {}
        for playoff_date in playoff_dates:
            games_to_date = [g for g in playoff_games if g.date <= playoff_date]
            # Derive rounds completed from survivor count rather than distinct dates,
            # because some rounds span multiple calendar dates (e.g. a first round
            # where a few games are played the Thursday before the main Friday).
            # Anchored to num_rounds so classes with fewer actual qualifiers than
            # the nominal bracket size (e.g. 1A/4A with 16 teams in a 5-round format)
            # produce correct odds — surviving is always a power of 2, total entry
            # count is not reliable when not all bracket slots are filled.
            playoff_schools = set(school_to_seed)
            eliminated = {g.school for g in games_to_date if g.result == "L" and g.school in playoff_schools}
            surviving = max(1, len(playoff_schools) - len(eliminated))
            rounds_completed = num_rounds - (surviving.bit_length() - 1)

            seeding: dict[int, RegionSeedingData] = {}
            for region in regions:
                seeding[region] = build_playoff_region_data(
                    clazz,
                    region,
                    season,
                    school_to_seed,
                    games_to_date,
                )

            # Use Elo snapshot from just before this playoff date so ratings
            # don't incorporate results of future rounds (lookahead bias fix).
            idx = bisect.bisect_right(snapshot_dates, playoff_date) - 1
            elo_at_date = elo_snapshots[idx][1] if idx >= 0 else elo_ratings

            # Build Elo-based matchup probability function from deterministic odds.
            class_weighted_odds = {r: seeding[r].odds_weighted for r in regions}
            matchup_fn = make_matchup_prob_fn(elo_at_date, class_weighted_odds, elo_cfg)

            all_region_odds = {r: seeding[r].odds for r in regions}

            for region in regions:
                get_region_finish_scenarios(
                    clazz,
                    region,
                    season,
                    seeding[region],
                    matchup_fn,
                    as_of_date=playoff_date,
                    rounds_completed=rounds_completed,
                    all_region_odds=all_region_odds,
                    round_snapshots=round_snapshots,
                )

            round_snapshots[rounds_completed] = all_region_odds

        logger.info("%dA season %d: playoff bracket update complete.", clazz, season)
