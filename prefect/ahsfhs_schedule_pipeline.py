from __future__ import annotations

import time
import re
from typing import Iterable, List
from psycopg2.extras import execute_values

from prefect import flow, task, get_run_logger

from data_classes import Game, School
from database_helpers import get_database_connection
from data_helpers import _normalize_ws, parseTextSection, to_plain_text, update_school_name_for_ahsfhs_search, _month_to_num
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
# Helpers
# -------------------------


def parse_ahsfhs_schedule(text: str, season_year: int, school_name: str, url: str) -> List[Game]:
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
      - game_status (str)
      - kickoff_time (NULL for this step)
      - source (AHSFHS URL in this case)

    OPEN dates are ignored.
    """
    text = to_plain_text(_normalize_ws(text))

    schedule_portion = parseTextSection(text, "Opponent Score", f"{season_year} Season Totals")

    # Regex for each game chunk
    game_re = re.compile(
        r"""
        (?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.,\s+
        (?P<mon>[A-Za-z]{3,9})\.?,?\s+
        (?P<day>\d{1,2})\s+
        (?P<loc>vs\.|@)\s+
        (?P<opp>[A-Za-z&.\'\- ]+?)             # opponent name
        (?:\s+(?P<pfor>\d+)\s+(?P<pagn>\d+)\s+(?P<res>[WL]))?  # optional score/result
        (?:\s+(?P<round>                                # optional playoff round
            (?:1st|2nd|3rd)\s+Round\s+Playoffs |
            Semi-finals\s+Playoffs |
            Championship\s+Game
        ))?
        (?:\s*(?P<star>\*))?                   # optional region star
        (?=\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.|$)  # lookahead to next game or end
        """,
        re.I | re.X
    )

    games: List[Game] = []
    for m in game_re.finditer(schedule_portion):
        mon = _month_to_num(m.group("mon"))
        day = int(m.group("day"))
        date = f"{mon:02d}/{day:02d}/{season_year}"

        opponent = m.group("opp").strip()
        if opponent.lower() == "open":
            continue  # skip OPEN weeks

        round_text = m.group("round")
        if round_text:
            round_text = " ".join(round_text.strip().split())  # normalize spacing

        games.append(Game.from_db_tuple({
            "school": school_name,
            "date": date,
            "location": "home" if m.group("loc").lower().rstrip(".") == "vs" else "away" if m.group("loc").lower().rstrip(".") == "@" else "neutral",
            "location_id": None, # AHSFHS does not provided advanced location information
            "opponent": opponent,
            "points_for": int(m.group("pfor")) if m.group("pfor") else None,
            "points_against": int(m.group("pagn")) if m.group("pagn") else None,
            "result": m.group("res") if m.group("res") else "W" if int(m.group("pfor")) > int(m.group("pagn")) else "L" if m.group("pagn") and m.group("pfor") else None,
            "region_game": bool(m.group("star")),
            "season": season_year,
            "round": round_text or None,
            "final": True if m.group("res") else False,
            "game_status": "Final" if m.group("res") else "", # AHSFHS games are either final or have not happened yet
            "kickoff_time": None,  # AHSFHS does not provide kickoff times
            "source": url,
            

        }))

    return games

def find_ahsfhs_schedule_for_schools(schools: List[School], year: int) -> List[Game]:
    """
    Return a list of dicts with ashsfhs schedule data for the given schools.
    """
    logger = get_run_logger()
    records: List[Game] = []

    for school in schools:

        url = f"https://www.ahsfhs.org/MISSISSIPPI/teams/gamesbyyear.asp?Team={update_school_name_for_ahsfhs_search(school.school)}&Year={year}"
        logger.info("Searching AHSFHS for schedules %r via %s", school.school, url)

        text = fetch_article_text_from_ahsfhs(url)

        schedule = parse_ahsfhs_schedule(text or "", season_year=year, school_name=school.school, url=url)
        
        records.extend(schedule)

        logger.info("Parsed schedule for %r: %s", school.school, schedule)

        # Be polite to AHSFHS
        time.sleep(0.3)

    return records

def insert_rows(game_records: Iterable[Game]) -> int:
    """
    Insert all found schedule data.
    Returns the number of rows actually inserted (cursor.rowcount sum).
    """
    if not game_records:
        return 0

    logger = get_run_logger()

    # --- do the updates ---
    sql = """
    INSERT INTO games
    (school, date, location, location_id, opponent, points_for, points_against, result, final, game_status, source, region_game, season, "round", kickoff_time)
    VALUES %s
    ON CONFLICT (school, date) DO UPDATE SET
    location        = COALESCE(NULLIF(EXCLUDED.location,''),        games.location),
    location_id     = COALESCE(EXCLUDED.location_id,                games.location_id),
    opponent        = COALESCE(NULLIF(EXCLUDED.opponent,''),        games.opponent),
    points_for      = COALESCE(EXCLUDED.points_for,                 games.points_for),
    points_against  = COALESCE(EXCLUDED.points_against,             games.points_against),
    result          = COALESCE(NULLIF(EXCLUDED.result,''),          games.result),
    final           = COALESCE(EXCLUDED.final,                      games.final),
    game_status     = COALESCE(EXCLUDED.game_status,                games.game_status),
    source          = COALESCE(EXCLUDED.source,                     games.source),
    region_game     = COALESCE(EXCLUDED.region_game,                games.region_game),
    season          = COALESCE(EXCLUDED.season,                     games.season),
    "round"         = COALESCE(NULLIF(EXCLUDED."round",''),         games."round"),
    kickoff_time    = COALESCE(EXCLUDED.kickoff_time,               games.kickoff_time)
    WHERE
        games.location        IS DISTINCT FROM COALESCE(NULLIF(EXCLUDED.location,''), games.location)
    OR games.location_id     IS DISTINCT FROM COALESCE(EXCLUDED.location_id, games.location_id)
    OR games.opponent        IS DISTINCT FROM COALESCE(NULLIF(EXCLUDED.opponent,''), games.opponent)
    OR games.points_for      IS DISTINCT FROM COALESCE(EXCLUDED.points_for, games.points_for)
    OR games.points_against  IS DISTINCT FROM COALESCE(EXCLUDED.points_against, games.points_against)
    OR games.result          IS DISTINCT FROM COALESCE(NULLIF(EXCLUDED.result,''), games.result)
    OR games.final           IS DISTINCT FROM COALESCE(EXCLUDED.final, games.final)
    OR games.game_status     IS DISTINCT FROM COALESCE(EXCLUDED.game_status, games.game_status)
    OR games.source          IS DISTINCT FROM COALESCE(EXCLUDED.source, games.source)
    OR games.region_game     IS DISTINCT FROM COALESCE(EXCLUDED.region_game, games.region_game)
    OR games.season          IS DISTINCT FROM COALESCE(EXCLUDED.season, games.season)
    OR games."round"         IS DISTINCT FROM COALESCE(NULLIF(EXCLUDED."round",''), games."round")
    OR games.kickoff_time    IS DISTINCT FROM COALESCE(EXCLUDED.kickoff_time, games.kickoff_time);
    """

    logger.info("Inserting/Updating %d game records into games table", len(list(game_records)))

    with get_database_connection() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, (game_records.as_db_tuple() for game_records in game_records))

    return len(list(game_records))


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


# -------------------------
# Prefect tasks & flow
# -------------------------

@task(retries=2, retry_delay_seconds=10, name="Scrape AHSFHS Schedule Data")
def scrape_task(existing_schools: List[School], year: int) -> int:
    """
    Task to scrape schedule data from AHSFHS.
    """
    logger = get_run_logger()
    game_records = find_ahsfhs_schedule_for_schools(existing_schools, year)
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