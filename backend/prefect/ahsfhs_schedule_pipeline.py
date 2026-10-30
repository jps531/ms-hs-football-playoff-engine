"""Prefect tasks and flow for scraping game schedule data from the AHSFHS website.

Fetches each school's season schedule, parses game dates/results/regions,
and writes records to the ``games`` table via INSERT ... ON CONFLICT UPDATE.
Afterwards, games a school's page no longer lists (e.g. the old date of a
rescheduled game) are removed, so the table mirrors AHSFHS.
"""

import json
import re
import time
from collections.abc import Iterable
from datetime import date, datetime

from prefect import flow, get_run_logger, task
from psycopg2.extras import execute_values

from backend.helpers.data_classes import Game, School
from backend.helpers.data_helpers import (
    _month_to_num,
    _normalize_ws,
    get_school_name_from_ahsfhs,
    parse_text_section,
    school_name_for_season,
    source_name_for_season,
    to_plain_text,
    update_school_name_for_ahsfhs_search,
)
from backend.helpers.database_helpers import get_database_connection
from backend.helpers.web_helpers import fetch_article_text_from_ahsfhs

# -------------------------
# Prefect tasks & flow
# -------------------------


def parse_ahsfhs_schedule(text: str, season: int, school_name: str, url: str, clazz: int) -> list[Game]:
    """
    Parse AHSFHS schedule text (with lots of line breaks) into a list of dicts:
    Each dict has the following keys:
      - school (str)
      - date (MM/DD/YYYY)
      - location ('vs'|'@')
      - location_id (NULL for this step)
      - opponent (str)
      - points_for (int|None)
      - points_against (int|None)
      - result ('W'|'L'|None)
      - region_game (bool)
      - season (int)
      - round (str|None)
      - final (bool)
      - overtime (int)
      - game_status (str)
      - kickoff_time (NULL for this step)
      - source (AHSFHS URL in this case)

    OPEN dates are ignored.
    """
    text = to_plain_text(_normalize_ws(text))
    logger = get_run_logger()
    logger.info("Searching AHSFHS for schedules %r via %s", school_name, url)

    schedule_portion = parse_text_section(text, "Opponent Score", f"{season} Season Totals")

    # Regex for each game chunk
    game_re = re.compile(
        r"""
        (?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.,\s+
        (?P<mon>[A-Z]{3,9})\.?,?\s+
        (?P<day>\d{1,2})\s+
        (?:(?P<loc>vs\.|@)\s+)?
        (?P<opp>[A-Z&.'\- ]+)
        (?:\s*(?P<star1>\*))?
        (?:\s+(?P<pfor>\d+)\s+(?P<pagn>\d+)\s+
            (?P<res>[WL]|\#(?:Won|Lost))
            (?:\s*\((?P<ot>\d*)OT\))?
        )?
        (?:\s+(?P<round>
            (?:1st|2nd|3rd)\s+Round\s+Playoffs |
            Semi-?finals\s+Playoffs |
            Championship\s+Game
        ))?
        (?:\s*(?P<star2>\*))?
        (?:\s+Playoffs\b)?
        (?=\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.|$)
        """,
        re.I | re.X,
    )

    games: list[Game] = []
    for m in game_re.finditer(schedule_portion):
        mon = _month_to_num(m.group("mon"))
        day = int(m.group("day"))
        date = f"{mon:02d}/{day:02d}/{season}"

        # AHSFHS can lag a school's new name (SCHOOL_RENAMES); store it under the site's name for the season.
        opponent = school_name_for_season(get_school_name_from_ahsfhs(m.group("opp").strip()), season)
        if opponent.lower().startswith("open"):
            continue  # skip OPEN weeks (handles "OPEN", "OPEN Playoffs", etc.)

        raw_res = m.group("res")
        result = None

        if raw_res:
            # Strip "#" and normalize to uppercase for comparison
            tag = raw_res.lstrip("#").upper()

            ot_group = m.group("ot")

            # Normalize overtime to integer
            if ot_group is None:
                overtime = 0
            elif ot_group == "":
                overtime = 1
            else:
                overtime = int(ot_group)

            # Forfeit cases
            if tag in {"WON", "LOST"}:
                # mark as Forfeit game
                result = "W" if tag.startswith("W") else "L"
                game_status = "final_forfeit"
            else:
                # Regular W/L result
                result = tag
                game_status = "final"
        else:
            # No result means the game hasn't been played: the pattern only matches a score
            # together with its W/L, so there is no score here either.
            result = None
            game_status = ""
            overtime = 0

        round_text = m.group("round")
        if round_text:
            round_text = " ".join(round_text.strip().split())  # normalize spacing

        # Sanitize Round Names
        if round_text:
            round_text = round_text.replace("1st Round Playoffs", "First Round")
            if clazz >= 5:
                round_text = round_text.replace("2nd Round Playoffs", "Quarterfinals")
            else:
                round_text = round_text.replace("2nd Round Playoffs", "Second Round")
            round_text = round_text.replace("3rd Round Playoffs", "Quarterfinals")
            round_text = round_text.replace("Semi-finals Playoffs", "Semifinals")

        region = bool(m.group("star1") or m.group("star2"))

        raw_loc = m.group("loc")
        if raw_loc is None:
            location = "neutral"
        elif raw_loc.lower().rstrip(".") == "vs":
            location = "home"
        else:
            location = "away"

        game = Game.from_db_tuple(
            {
                "school": school_name,
                "date": datetime.strptime(date, "%m/%d/%Y").date(),
                "season": season,
                "location_id": None,  # AHSFHS does not provided advanced location information,
                "points_for": int(m.group("pfor")) if m.group("pfor") else None,
                "points_against": int(m.group("pagn")) if m.group("pagn") else None,
                "round": round_text or None,
                "kickoff_time": None,  # AHSFHS does not provide kickoff times
                "opponent": opponent,
                "result": result,
                "game_status": game_status,
                "source": url,
                "location": location,
                "region_game": region,
                "final": True if m.group("res") else False,
                "overtime": overtime,
            }
        )

        if game is not None:
            games.append(game)

    logger.info("Parsed schedule for %r: %s", school_name, games)

    return games


@task(task_run_name="Find AHSFHS Schedule for Schools from {season}")
def find_ahsfhs_schedule_for_schools(schools: list[School], season: int) -> list[Game]:
    """
    Return a list of dicts with ashsfhs schedule data for the given schools.
    """
    records: list[Game] = []
    logger = get_run_logger()
    failed_schools: list[str] = []

    for school in schools:
        source = source_name_for_season(school.school, season)  # a renamed school's page is still under its old name
        url = f"https://www.ahsfhs.org/MISSISSIPPI/teams/gamesbyyear.asp?Team={update_school_name_for_ahsfhs_search(source)}&Year={season}"

        try:
            text = fetch_article_text_from_ahsfhs(url)
            schedule = parse_ahsfhs_schedule(
                text or "", season=season, school_name=school.school, url=url, clazz=school.class_
            )
        except Exception:
            logger.error("Failed to fetch/parse AHSFHS schedule for %r via %s; skipping", school.school, url, exc_info=True)
            failed_schools.append(school.school)
            continue

        records.extend(schedule)

        # Be polite to AHSFHS
        time.sleep(0.3)

    if failed_schools:
        logger.warning(
            "Skipped %d school(s) due to fetch/parse errors: %s", len(failed_schools), ", ".join(failed_schools)
        )

    return records


# This run's scraped rows, loaded into a temporary table so the steps below can
# each read them. The column order is Game.as_db_tuple()'s.
_INCOMING_TABLE_SQL = """
    CREATE TEMP TABLE incoming (
        school TEXT, date DATE, season INTEGER, location_id INTEGER, points_for INTEGER,
        points_against INTEGER, "round" TEXT, kickoff_time TIMESTAMPTZ, opponent TEXT,
        result TEXT, game_status TEXT, source TEXT, location TEXT, region_game BOOLEAN,
        final BOOLEAN, overtime INTEGER
    ) ON COMMIT DROP
"""

# A game AHSFHS now lists a few days from the date we have it on: the school's
# only row against the same opponent within three days, at a date this run
# doesn't list, and no row yet at the new date. Moving that row keeps
# everything attached to it (approved corrections, the helmet worn, the games
# people marked as attended) where replacing it would lose them.
_MOVED_GAMES_SQL = """
    SELECT g.school, g.date, i.date, g.opponent
    FROM incoming i
    JOIN games g ON g.school = i.school AND g.opponent = i.opponent
        AND g.date <> i.date AND g.date BETWEEN i.date - 3 AND i.date + 3
    WHERE NOT EXISTS (SELECT 1 FROM games x WHERE x.school = i.school AND x.date = i.date)
      AND NOT EXISTS (SELECT 1 FROM incoming j WHERE j.school = g.school AND j.date = g.date)
      AND (SELECT count(*) FROM games y WHERE y.school = i.school AND y.opponent = i.opponent
               AND y.date BETWEEN i.date - 3 AND i.date + 3) = 1
      AND (SELECT count(*) FROM incoming k WHERE k.school = i.school AND k.opponent = i.opponent
               AND k.date BETWEEN g.date - 3 AND g.date + 3) = 1
    ORDER BY g.school, g.date
"""

# Rows within three days of a scraped game, at a date this run doesn't list:
# what the source had there before (a different opponent, say). Unplayed rows
# without corrections are removed; the others are kept and reported, the same
# rule as remove_unlisted_games.
_STALE_NEARBY_SQL = """
    DELETE FROM games g
    WHERE EXISTS (SELECT 1 FROM incoming i WHERE i.school = g.school
                      AND g.date BETWEEN i.date - 3 AND i.date + 3)
      AND NOT EXISTS (SELECT 1 FROM incoming j WHERE j.school = g.school AND j.date = g.date)
      AND g.final IS NOT TRUE
      AND g.overrides = '{}'::jsonb
    RETURNING g.school, g.date, g.opponent
"""
_KEPT_NEARBY_SQL = """
    SELECT g.school, g.date, g.opponent, g.overrides <> '{}'::jsonb AS overridden
    FROM games g
    WHERE EXISTS (SELECT 1 FROM incoming i WHERE i.school = g.school
                      AND g.date BETWEEN i.date - 3 AND i.date + 3)
      AND NOT EXISTS (SELECT 1 FROM incoming j WHERE j.school = g.school AND j.date = g.date)
    ORDER BY g.school, g.date
"""

# Score fields whose AHSFHS value has changed since the last run on a row
# whose value was corrected by hand. Read before the upsert, which then stores
# the new value: the correction still wins (games_effective reads overrides
# first), but a moderator should look at whether it's still right.
_SCORE_FIELDS = ("points_for", "points_against", "result")
_CHANGED_UNDER_CORRECTION_SQL = " UNION ALL ".join(
    f"""
    SELECT g.school, g.date, g.opponent, '{field}', g.{field}::text, NULLIF(i.{field}::text, ''), g.overrides->>'{field}'
    FROM games g JOIN incoming i ON i.school = g.school AND i.date = g.date
    WHERE g.overrides ? '{field}' AND NULLIF(i.{field}::text, '') IS DISTINCT FROM g.{field}::text
      AND NULLIF(i.{field}::text, '') IS NOT NULL"""
    for field in _SCORE_FIELDS
)

# The score fields always take AHSFHS's value (the corrections live in
# overrides, which games_effective reads first), so the next run can tell when
# AHSFHS changes it. The other fields a correction can set keep the stored
# value while it's overridden, as before.
_UPSERT_SQL = """
    INSERT INTO games
        (school, date, season, location_id, points_for, points_against,
        "round", kickoff_time, opponent, result, game_status, source,
        location, region_game, final, overtime)
    SELECT school, date, season, location_id, points_for, points_against,
        "round", kickoff_time, opponent, result, game_status, source,
        location, region_game, final, overtime
    FROM incoming
    ON CONFLICT (school, date) DO UPDATE SET
        location        = CASE WHEN games.overrides ? 'location'       THEN games.location       ELSE COALESCE(NULLIF(EXCLUDED.location,''),    games.location)       END,
        location_id     = CASE WHEN games.overrides ? 'location_id'    THEN games.location_id    ELSE COALESCE(EXCLUDED.location_id,            games.location_id)    END,
        opponent        = COALESCE(NULLIF(EXCLUDED.opponent,''),        games.opponent),
        points_for      = COALESCE(EXCLUDED.points_for,                 games.points_for),
        points_against  = COALESCE(EXCLUDED.points_against,             games.points_against),
        result          = COALESCE(NULLIF(EXCLUDED.result,''),          games.result),
        final           = COALESCE(EXCLUDED.final,                      games.final),
        overtime        = COALESCE(EXCLUDED.overtime,                   games.overtime),
        game_status     = CASE WHEN games.overrides ? 'game_status' THEN games.game_status ELSE COALESCE(EXCLUDED.game_status,                games.game_status) END,
        source          = COALESCE(EXCLUDED.source,                     games.source),
        region_game     = CASE WHEN games.overrides ? 'region_game'    THEN games.region_game    ELSE COALESCE(EXCLUDED.region_game,            games.region_game)    END,
        season          = COALESCE(EXCLUDED.season,                     games.season),
        "round"         = CASE WHEN games.overrides ? 'round'          THEN games."round"        ELSE COALESCE(NULLIF(EXCLUDED."round",''),     games."round")        END,
        kickoff_time    = CASE WHEN games.overrides ? 'kickoff_time'   THEN games.kickoff_time   ELSE COALESCE(EXCLUDED.kickoff_time,           games.kickoff_time)   END
        -- overrides column is never written by the pipeline
"""


@task(task_run_name="Insert/Update AHSFHS Game Records")
def insert_rows(game_records: Iterable[Game]) -> int:
    """Write this run's scraped games, in one transaction.

    1. A game AHSFHS moved by up to three days is moved in place (see
       ``_MOVED_GAMES_SQL``), so its corrections, helmet and attendance stay.
    2. Other rows within three days of a scraped game, at a date it no longer
       lists, are removed unless they're finished or corrected (then reported).
    3. Each scraped game is inserted or updated. A score AHSFHS changed under
       an approved correction is reported; the correction still shows.

    Returns the number of scraped rows written.
    """
    game_records = list(game_records)
    if not game_records:
        return 0

    logger = get_run_logger()

    logger.info("Inserting/Updating %d game records into games table", len(game_records))
    rows_data = [r.as_db_tuple() for r in game_records]
    logger.info("Prepared %d rows for insertion: %s", len(rows_data), rows_data)

    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_INCOMING_TABLE_SQL)
            execute_values(cur, "INSERT INTO incoming VALUES %s", rows_data, page_size=500)
            cur.execute(_MOVED_GAMES_SQL)
            moved = cur.fetchall()
            for school, old_date, new_date, _opponent in moved:
                cur.execute("UPDATE games SET date = %s WHERE school = %s AND date = %s", (new_date, school, old_date))
            cur.execute(_STALE_NEARBY_SQL)
            removed = cur.fetchall()
            cur.execute(_KEPT_NEARBY_SQL)
            kept = cur.fetchall()
            cur.execute(_CHANGED_UNDER_CORRECTION_SQL)
            changed = cur.fetchall()
            cur.execute(_UPSERT_SQL)
        conn.commit()

    for school, old_date, new_date, opponent in moved:
        logger.info("Moved %s's game vs %s from %s to %s, as AHSFHS now lists it", school, opponent, old_date, new_date)
    for school, game_date, opponent in removed:
        logger.info("Removed %s's %s game vs %s: AHSFHS lists another game that week", school, game_date, opponent)
    for school, game_date, opponent, overridden in kept:
        logger.warning(
            "%s's %s game vs %s is no longer on its AHSFHS schedule (another game is listed that week); kept because %s",
            school,
            game_date,
            opponent,
            "it has manual overrides" if overridden else "it's a finished game",
        )
    for school, game_date, opponent, field, before, now, corrected in changed:
        verdict = "now agrees with" if now == corrected else "still differs from"
        logger.warning(
            "AHSFHS changed %s's %s game vs %s: %s %s -> %s, which %s the approved correction (%s). "
            "The correction still shows; clear it if AHSFHS is now right.",
            school,
            game_date,
            opponent,
            field,
            before,
            now,
            verdict,
            corrected,
        )

    return len(game_records)


# Each scraped school's listed dates, passed as one JSON object
# {school: ["YYYY-MM-DD", ...]}. A row is removed only when it's unplayed and
# has no manual overrides: a finished game with a score, or a row someone
# corrected by hand, is kept even if AHSFHS stops listing it, and reported.
_LISTED_CTE = """
    WITH listed AS (
        SELECT key AS school,
               ARRAY(SELECT jsonb_array_elements_text(value)::date) AS dates
        FROM jsonb_each(%s::jsonb)
    )
"""
_DELETE_UNLISTED_SQL = (
    _LISTED_CTE
    + """
    DELETE FROM games g
    USING listed l
    WHERE g.season = %s
      AND g.school = l.school
      AND NOT (g.date = ANY(l.dates))
      AND g.final IS NOT TRUE
      AND g.overrides = '{}'::jsonb
    RETURNING g.school, g.date, g.opponent
"""
)
_KEPT_UNLISTED_SQL = (
    _LISTED_CTE
    + """
    SELECT g.school, g.date, g.opponent, g.final, g.overrides <> '{}'::jsonb AS overridden
    FROM games g
    JOIN listed l ON l.school = g.school
    WHERE g.season = %s
      AND NOT (g.date = ANY(l.dates))
    ORDER BY g.school, g.date
"""
)


@task(task_run_name="Remove Unlisted AHSFHS Game Records for {season}")
def remove_unlisted_games(game_records: Iterable[Game], season: int) -> int:
    """Delete each scraped school's games that its AHSFHS page no longer lists.

    ``insert_rows`` only replaces a school's rows within three days of a
    scraped game, so when a game moves by more than that (rescheduled a week
    later, say), the row at its old date would otherwise stay and count as a
    game played that week. This removes, for every school whose page was
    scraped this run, that season's rows not on the page.

    Only schools with at least one scraped game are touched, so a page that
    failed to load or parse never wipes a schedule. Finished games and rows
    with manual overrides are never removed; they're logged as a warning.

    Args:
        game_records: This run's scraped games (every school's).
        season:       Season the games belong to.

    Returns:
        The number of rows deleted.
    """
    dates_by_school: dict[str, set[str]] = {}
    for g in game_records:
        dates_by_school.setdefault(g.school, set()).add(g.date.isoformat())
    if not dates_by_school:
        return 0

    logger = get_run_logger()
    listed = json.dumps({school: sorted(dates) for school, dates in dates_by_school.items()})

    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_DELETE_UNLISTED_SQL, (listed, season))
            deleted = cur.fetchall()
            cur.execute(_KEPT_UNLISTED_SQL, (listed, season))
            kept = cur.fetchall()
        conn.commit()

    for school, game_date, opponent in deleted:
        logger.info("Removed %s's %s game vs %s: no longer on its AHSFHS schedule", school, game_date, opponent)
    for school, game_date, opponent, _final, overridden in kept:
        reason = "it has manual overrides" if overridden else "it's a finished game"
        logger.warning(
            "%s's %s game vs %s is no longer on its AHSFHS schedule; kept because %s",
            school,
            game_date,
            opponent,
            reason,
        )
    return len(deleted)


@task(task_run_name="Get Existing Schools for AHSFHS Schedule Scrape")
def get_existing_schools(season: int) -> list[School]:
    """
    Gets the list of existing schools from the database.
    """
    q = """
        SELECT ss.school, ss.season, ss.class, ss.region,
               s.city, s.zip, s.latitude, s.longitude, s.mascot,
               s.primary_color, s.secondary_color
        FROM school_seasons ss
        JOIN schools_effective s USING (school)
        WHERE ss.season = %s
          AND ss.is_active = TRUE
    """
    schools: list[School] = []
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(q, (season,))
            for row in cur.fetchall():
                schools.append(School.from_db_tuple(row))
    logger = get_run_logger()
    logger.info("Fetched %d existing schools from database", len(schools))
    return schools


@flow(name="AHSFHS Schedule Data Flow")
def ahsfhs_schedule_data_flow(season: int | None = None) -> int:
    """
    Flow to scrape and update school rows with AHSFHS schedule data.
    """
    if season is None:
        season = date.today().year
    existing_schools = get_existing_schools(season)
    game_records = find_ahsfhs_schedule_for_schools(existing_schools, season)
    updated_count = insert_rows(game_records)
    remove_unlisted_games(game_records, season)
    return updated_count
