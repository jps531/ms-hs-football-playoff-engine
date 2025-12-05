from __future__ import annotations

import time, re
from typing import Iterable, List
from psycopg2.extras import execute_values
from prefect import flow, task, get_run_logger
from datetime import datetime

from prefect_files.data_classes import Game, School
from prefect_files.database_helpers import get_database_connection
from prefect_files.data_helpers import _normalize_ws, get_school_name_from_ahsfhs, parseTextSection, to_plain_text, update_school_name_for_ahsfhs_search, _month_to_num
from web_helpers import UA, fetch_article_text_from_ahsfhs


# -------------------------
# Constants
# -------------------------


# Matches lines like:
# "Fri., Aug. 29", "Thu., Oct. 3", "Sat, Sep 5", "Aug. 29" (weekday optional)
DATE_LINE_RE = re.compile(
    r"""^\s*
        (?:(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s*[.,]?\s+)?   # optional weekday
        ([A-Za-z]{3,9})\.?,?\s+                         # month
        (\d{1,2})\b                                     # day
    """,
    re.IGNORECASE | re.VERBOSE,
)


# -------------------------
# Prefect tasks & flow
# -------------------------


@task(task_run_name="Fetch AHSFHS Schedule Data for {school_name} for {season}")
def parse_ahsfhs_schedule(text: str, season: int, school_name: str, url: str) -> List[Game]:
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

    schedule_portion = parseTextSection(text, "Opponent Score", f"{season} Season Totals")

    # Regex for each game chunk
    game_re = re.compile(
        r"""
        (?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.,\s+
        (?P<mon>[A-Za-z]{3,9})\.?,?\s+
        (?P<day>\d{1,2})\s+
        (?P<loc>vs\.|@)\s+
        (?P<opp>[A-Za-z0-9&.'\- ]+?)      
        (?:\s*(?P<star1>\*))?             
        (?:\s+(?P<pfor>\d+)\s+(?P<pagn>\d+)\s+
            (?P<res>(?:[WL])|\#(?:Won|Lost))
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
        re.I | re.X
    )

    games: List[Game] = []
    for m in game_re.finditer(schedule_portion):
        mon = _month_to_num(m.group("mon"))
        day = int(m.group("day"))
        date = f"{mon:02d}/{day:02d}/{season}"

        opponent = get_school_name_from_ahsfhs(m.group("opp").strip())
        if opponent.lower() == "open":
            continue  # skip OPEN weeks

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
                game_status = "Final - Forfeit"
            else:
                # Regular W/L result
                result = tag
                game_status = "Final"
        else:
            # No result: determine if the game has happened yet or not
            if m.group("pfor") and m.group("pagn"):
                result = "W" if int(m.group("pfor")) > int(m.group("pagn")) else "L"
                game_status = "Final"
            else:
                result = None
                game_status = ""

            overtime = 0

        round_text = m.group("round")
        if round_text:
            round_text = " ".join(round_text.strip().split())  # normalize spacing

        region = bool(m.group("star1") or m.group("star2"))

        game = Game.from_db_tuple({
            "school": school_name,
            "date": datetime.strptime(date, "%m/%d/%Y").date(),
            "season": season,
            "location_id": None, # AHSFHS does not provided advanced location information,
            "points_for": int(m.group("pfor")) if m.group("pfor") else None,
            "points_against": int(m.group("pagn")) if m.group("pagn") else None,
            "round": round_text or None,
            "kickoff_time": None,  # AHSFHS does not provide kickoff times
            "opponent": opponent,
            "result": result,
            "game_status": game_status,
            "source": url,
            "location": "home" if m.group("loc").lower().rstrip(".") == "vs" else "away" if m.group("loc").lower().rstrip(".") == "@" else "neutral",
            "region_game": region,
            "final": True if m.group("res") else False,
            "overtime": overtime,
        })

        if game is not None:
            games.append(game)

    logger.info("Parsed schedule for %r: %s", school_name, games)

    return games


@task(task_run_name="Find AHSFHS Schedule for Schools from {season}")
def find_ahsfhs_schedule_for_schools(schools: List[School], season: int) -> List[Game]:
    """
    Return a list of dicts with ashsfhs schedule data for the given schools.
    """
    records: List[Game] = []

    for school in schools:

        url = f"https://www.ahsfhs.org/MISSISSIPPI/teams/gamesbyyear.asp?Team={update_school_name_for_ahsfhs_search(school.school)}&Year={season}"

        text = fetch_article_text_from_ahsfhs(url)

        schedule = parse_ahsfhs_schedule(text or "", season=season, school_name=school.school, url=url)
        
        records.extend(schedule)

        # Be polite to AHSFHS
        time.sleep(0.3)

    return records


@task(task_run_name="Insert/Update AHSFHS Game Records")
def insert_rows(game_records: Iterable[Game]) -> int:
    """
    Insert all found schedule data.
    Returns the number of rows actually inserted (cursor.rowcount sum).
    """
    if not game_records:
        return 0

    logger = get_run_logger()

    logger.info("Inserting/Updating %d game records into games table", len(list(game_records)))
    rows_data = [r.as_db_tuple() for r in game_records]
    logger.info("Raw game records: %s", game_records)
    logger.info("Prepared %d rows for insertion: %s", len(rows_data), rows_data)

    # --- do the updates ---
    sql = """
    WITH incoming_raw AS (
        SELECT *
        FROM (VALUES %s) AS v(
            school, date, season, location_id, points_for, points_against,
            "round", kickoff_time, opponent, result, game_status, source,
            location, region_game, final, overtime
        )
    ),
    incoming AS (
        SELECT
            school::text          AS school,
            date::date            AS date,
            season::integer       AS season,
            location_id::integer  AS location_id,
            points_for::integer   AS points_for,
            points_against::integer AS points_against,
            "round"::text         AS "round",
            kickoff_time::timestamptz AS kickoff_time,
            opponent::text        AS opponent,
            result::text          AS result,
            game_status::text     AS game_status,
            source::text          AS source,
            location::text        AS location,
            region_game::boolean  AS region_game,
            final::boolean        AS final,
            overtime::integer     AS overtime
        FROM incoming_raw
    ),
    deleted AS (
        DELETE FROM games g
        USING incoming i
        WHERE g.school = i.school
        AND g.date BETWEEN i.date - INTERVAL '3 days'
                        AND i.date + INTERVAL '3 days'
        RETURNING g.*
    )
    INSERT INTO games
        (school, date, season, location_id, points_for, points_against,
        "round", kickoff_time, opponent, result, game_status, source,
        location, region_game, final, overtime)
    SELECT
        i.school, i.date, i.season, i.location_id, i.points_for, i.points_against,
        i."round", i.kickoff_time, i.opponent, i.result, i.game_status, i.source,
        i.location, i.region_game, i.final, i.overtime
    FROM incoming i
    ON CONFLICT (school, date) DO UPDATE SET
        location        = COALESCE(NULLIF(EXCLUDED.location,''),        games.location),
        location_id     = COALESCE(EXCLUDED.location_id,                games.location_id),
        opponent        = COALESCE(NULLIF(EXCLUDED.opponent,''),        games.opponent),
        points_for      = COALESCE(EXCLUDED.points_for,                 games.points_for),
        points_against  = COALESCE(EXCLUDED.points_against,             games.points_against),
        result          = COALESCE(NULLIF(EXCLUDED.result,''),          games.result),
        final           = COALESCE(EXCLUDED.final,                      games.final),
        overtime        = COALESCE(EXCLUDED.overtime,                   games.overtime),
        game_status     = COALESCE(EXCLUDED.game_status,                games.game_status),
        source          = COALESCE(EXCLUDED.source,                     games.source),
        region_game     = COALESCE(EXCLUDED.region_game,                games.region_game),
        season          = COALESCE(EXCLUDED.season,                     games.season),
        "round"         = COALESCE(NULLIF(EXCLUDED."round",''),         games."round"),
        kickoff_time    = COALESCE(EXCLUDED.kickoff_time,               games.kickoff_time)
        -- you can keep / drop the big IS DISTINCT FROM WHERE clause if you want
    ;
    """

    template = "(" + ", ".join(["%s"] * 16) + ")"

    with get_database_connection() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, rows_data, template=template, page_size=500)
        conn.commit()

    return len(list(game_records))


@task(task_run_name="Get Existing Schools for AHSFHS Schedule Scrape")
def get_existing_schools(season: int) -> List[School]:
    """
    Gets the list of existing schools from the database.
    """
    q = """
        SELECT school, season, class, region, city, zip, latitude, longitude, mascot, maxpreps_id, maxpreps_url, maxpreps_logo, primary_color, secondary_color FROM schools
        WHERE season = %s
    """
    schools: List[School] = []
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(q, (season,))
            for row in cur.fetchall():
                schools.append(School.from_db_tuple(row))
    logger = get_run_logger()
    logger.info("Fetched %d existing schools from database", len(schools))
    return schools


@task(retries=2, retry_delay_seconds=10, task_run_name="Scrape AHSFHS Schedule Data for {season}")
def scrape_task(existing_schools: List[School], season: int) -> int:
    """
    Task to scrape schedule data from AHSFHS.
    """
    logger = get_run_logger()
    game_records = find_ahsfhs_schedule_for_schools(existing_schools, season)
    logger.info("Found AHSFHS Schedules for %d games", len(game_records))
    updated_count = insert_rows(game_records)
    logger.info("Inserted/Updated %d games", updated_count)
    return updated_count

@flow(name="AHSFHS Schedule Data Flow")
def ahsfhs_schedule_data_flow(season: int = 2025) -> int:
    """
    Flow to scrape and update school rows with AHSFHS schedule data.
    """
    existing_schools = get_existing_schools(season)
    updated_count = scrape_task(existing_schools, season)
    return updated_count