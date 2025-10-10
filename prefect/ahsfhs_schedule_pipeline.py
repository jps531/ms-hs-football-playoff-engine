from __future__ import annotations

import time
import re
from typing import Dict, Any, Iterable, List

from prefect import flow, task, get_run_logger

from data_classes import School
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


def parse_ahsfhs_schedule(text: str, season_year: int) -> List[Dict]:
    """
    Parse AHSFHS schedule text (with lots of line breaks) into a list of dicts:
      - date (MM/DD/YYYY)
      - location ('vs'|'@')
      - opponent (str)
      - points_for (int|None)
      - points_against (int|None)
      - result ('W'|'L'|None)
      - region_game (bool)

    OPEN dates are ignored.
    """
    logger = get_run_logger()
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
        (?:\s*(?P<star>\*))?                   # optional region star
        (?=\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.|$)  # lookahead to next game or end
        """,
        re.I | re.X
    )

    games = []
    for m in game_re.finditer(schedule_portion):
        mon = _month_to_num(m.group("mon"))
        day = int(m.group("day"))
        date = f"{mon:02d}/{day:02d}/{season_year}"

        opponent = m.group("opp").strip()
        if opponent.lower() == "open":
            continue  # skip OPEN weeks

        games.append({
            "date": date,
            "location": m.group("loc").lower().rstrip("."),
            "opponent": opponent,
            "points_for": int(m.group("pfor")) if m.group("pfor") else None,
            "points_against": int(m.group("pagn")) if m.group("pagn") else None,
            "result": m.group("res"),
            "region_game": bool(m.group("star")),
        })

    return games

def find_ahsfhs_schedule_for_schools(schools: List[School], year: int) -> List[Dict[str, Any]]:
    """
    Return a list of dicts with ashsfhs schedule data for the given schools.
    """
    logger = get_run_logger()
    records: List[Dict[str, Any]] = []

    for school in schools:

        url = f"https://www.ahsfhs.org/MISSISSIPPI/teams/gamesbyyear.asp?Team={update_school_name_for_ahsfhs_search(school.school)}&Year={year}"
        logger.info("Searching AHSFHS for schedules %r via %s", school.school, url)

        text = fetch_article_text_from_ahsfhs(url)

        schedule = parse_ahsfhs_schedule(text or "", season_year=year)

        logger.info("Parsed schedule for %r: %s", school.school, schedule)

        # r = requests.get(url, headers=headers, timeout=25)
        # r.raise_for_status()
        # data = _extract_next_data(r.text)

        #school_info = data.get("props", {}).get("pageProps", {}).get("schoolContext", {}).get("schoolInfo", {})
        # if not school_info:
        #     logger.warning("No info found for %r at %s", school.school, url)
        #     continue

        # found_info = {
        #     "school": school.school,
        #     "class": school.class_,
        #     "region": school.region,
        #     "latitude": school_info.get("latitude") or 0.0,
        #     "longitude": school_info.get("longitude") or 0.0,
        #     "primary_color": school_info.get("color1") or "",
        #     "secondary_color": school_info.get("color2") or "",
        #     "maxpreps_logo": school_info.get("mascotUrl") or "",
        # }

        # records.append(found_info)

        # logger.info("Found info for %r: %s", school.school, found_info)

        # Be polite to MaxPreps
        time.sleep(0.3)

    return records

def insert_rows(school_records: Iterable[dict]) -> int:
    """
    Insert all found schedule data.
    Returns the number of rows actually inserted (cursor.rowcount sum).
    """
    if not school_records:
        return 0

    logger = get_run_logger()

    # --- do the updates ---
    q = """
    UPDATE schools
    SET primary_color   = COALESCE(NULLIF(%s, ''), primary_color),
        secondary_color = COALESCE(NULLIF(%s, ''), secondary_color),
        latitude        = COALESCE(%s, latitude),
        longitude       = COALESCE(%s, longitude),
        maxpreps_logo   = COALESCE(NULLIF(%s, ''), maxpreps_logo)
    WHERE school = %s AND class = %s AND region = %s
    """

    updated = 0
    # with get_database_connection() as conn:
    #     with conn.cursor() as cur:
    #         for row in school_records:
    #             lat = as_float_or_none(row["latitude"])
    #             lon = as_float_or_none(row["longitude"])

    #             logger.info("Updating %r (class %s, region %s) with primary color %r, secondary color %r, latitude %s, longitude %s, maxpreps_logo %r", row["school"], row["class"], row["region"], row["primary_color"], row["secondary_color"], lat, lon, row["maxpreps_logo"])

    #             cur.execute(q, (row["primary_color"], row["secondary_color"], lat, lon, row["maxpreps_logo"], row["school"], row["class"], row["region"]))
    #             updated += cur.rowcount

    #     conn.commit()

    # logger.info("Updated %d school rows with school info data", updated)
    return updated


def get_existing_schools() -> List[School]:
    """
    Gets the list of existing schools from the database.
    """
    q = """
        SELECT school, class, region, city, zip, latitude, longitude, mascot, maxpreps_id, maxpreps_url, maxpreps_logo, primary_color, secondary_color FROM schools
    """
    schools: List[School] = []
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(q)
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
    school_records = find_ahsfhs_schedule_for_schools(existing_schools, year)
    logger.info("Found AHSFHS Schedules for %d schools", len(school_records))
    logger.info("Found AHSFHS Schedules for the following schools: %s", school_records)
    updated_count = insert_rows(school_records)
    logger.info("Updated %d schools", updated_count)
    return updated_count


@flow(name="AHSFHS Schedule Data Flow")
def ahsfhs_schedule_data_flow(year: int = 2025) -> int:
    """
    Flow to scrape and update school rows with AHSFHS schedule data.
    """
    existing_schools = get_existing_schools()
    updated_count = scrape_task(existing_schools, year)
    return updated_count