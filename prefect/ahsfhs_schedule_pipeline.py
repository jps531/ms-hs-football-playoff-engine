from __future__ import annotations

import time
import re
from typing import Dict, Any, Iterable, List, Optional

from prefect import flow, task, get_run_logger

from data_classes import School
from database_helpers import get_database_connection
from data_helpers import _month_to_num, _pad, get_school_name_from_ahsfhs, update_school_name_for_ahsfhs_search
from web_helpers import UA, fetch_article_text_from_ahsfhs


# -------------------------
# Helpers
# -------------------------

def parse_ahsfhs_schedule(text: str, season_year: Optional[int] = None) -> List[Dict]:
    """
    Extract AHSFHS schedule entries from a page's text.

    Returns a list of dicts with:
      - date (DD/MM/YYYY)
      - location ('vs' or '@')
      - opponent (str)
      - points_for (int|None)
      - points_against (int|None)
      - result ('W'|'L'|None)
      - region_game (bool)
    """
    # Find the correct season block
    season_pattern = (
        rf"(?P<year>\d{{4}})\s+Season\s*?\n"  # "2025 Season"
        r"(?P<body>.*?)(?:\n\d{4}\s+Season\s+Totals|\Z)"  # up to "2025 Season Totals" or end
    )
    flags = re.DOTALL

    if season_year is not None:
        # Look for the specific season first
        m = re.search(season_pattern, text, flags)
        # Scan all blocks to pick matching year
        blocks = list(re.finditer(season_pattern, text, flags))
        target = None
        for b in blocks:
            if int(b.group("year")) == season_year:
                target = b
                break
        if not target:
            # Fallback: just use the first matched block
            target = m
    else:
        target = re.search(season_pattern, text, flags)

    if not target:
        return []

    year = int(target.group("year")) if season_year is None else int(season_year)
    body = target.group("body")

    # Remove common header line if present
    body = re.sub(r"^\s*Date\s+Opponent\s+Score\s*\n", "", body, flags=re.IGNORECASE | re.MULTILINE)

    # Line pattern for entries like:
    # "Fri., Aug. 29 @ Northside 8 32 L"
    # "Fri., Oct. 10 @ Crystal Springs *"
    # "Fri., Oct. 3 OPEN"
    line_re = re.compile(
        r"""
        ^(?P<dow>Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.,\s+
        (?P<mon>[A-Za-z]{3,9})\.?\s+
        (?P<day>\d{1,2})\s+
        (?P<loc>vs\.|@)\s+
        (?P<opp>.*?)
        (?:                           # optional score/result section
            \s+(?P<pf>\d+)\s+(?P<pa>\d+)\s+(?P<res>[WL])
        )?
        \s*(?P<region>\*)?
        \s*$
        """,
        re.IGNORECASE | re.VERBOSE | re.MULTILINE,
    )

    results: List[Dict] = []

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Skip OPEN lines quickly
        if re.search(r"\bOPEN\b", line, re.IGNORECASE):
            continue

        m = line_re.match(line)
        if not m:
            # Not a schedule line; skip
            continue

        mon = m.group("mon")
        day = int(m.group("day"))
        loc = m.group("loc").lower().rstrip(".")  # "vs." -> "vs"
        opp = m.group("opp").strip()
        pf = m.group("pf")
        pa = m.group("pa")
        res = m.group("res")
        region_flag = m.group("region") is not None

        mon_num = _month_to_num(mon)
        if not mon_num:
            # Unknown month; skip defensively
            continue

        date_str = f"{_pad(mon_num)}/{_pad(day)}/{year}"

        results.append({
            "date": date_str,
            "location": "home" if loc == "vs" else "away",  # 'vs' or '@'
            "opponent": get_school_name_from_ahsfhs(opp),  # cleaned opponent name
            "points_for": int(pf) if pf is not None else None,
            "points_against": int(pa) if pa is not None else None,
            "result": res.upper() if res else None,
            "region_game": bool(region_flag),
        })

    return results

def find_ahsfhs_schedule_for_schools(schools: List[School], year: int) -> List[Dict[str, Any]]:
    """
    Return a list of dicts with ashsfhs schedule data for the given schools.
    """
    logger = get_run_logger()
    records: List[Dict[str, Any]] = []

    for school in schools:

        url = f"https://www.ahsfhs.org/MISSISSIPPI/teams/gamesbyyear.asp?Team={update_school_name_for_ahsfhs_search(school.school)}&Year={year}"
        headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}

        logger.info("Searching AHSFHS for schedules %r via %s", school.school, url)

        text = fetch_article_text_from_ahsfhs(url)

        logger.info("Fetched text for %r: %s", school.school, text)

        schedule = parse_ahsfhs_schedule(text, season_year=year)

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