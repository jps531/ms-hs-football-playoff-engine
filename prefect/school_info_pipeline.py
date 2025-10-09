from __future__ import annotations

import time
from typing import Dict, Any, Iterable, List
import requests

from prefect import flow, task, get_run_logger

from data_classes import School
from database_helpers import get_database_connection
from data_helpers import as_float_or_none
from web_helpers import UA, _extract_next_data


# -------------------------
# Helpers
# -------------------------

def find_school_info_for_schools(schools: List[School]) -> List[Dict[str, Any]]:
    """
    Return a list of dicts with school info data for the given schools.
    Each dict includes: school, class, region, primary_color, secondary_color.
    """
    logger = get_run_logger()
    records: List[Dict[str, Any]] = []

    for school in schools:

        url = school.maxpreps_url
        headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}

        logger.info("Searching MaxPreps for school %r via %s", school.school, url)

        r = requests.get(url, headers=headers, timeout=25)
        r.raise_for_status()
        data = _extract_next_data(r.text)

        school_info = data.get("props", {}).get("pageProps", {}).get("schoolContext", {}).get("schoolInfo", {})
        if not school_info:
            logger.warning("No info found for %r at %s", school.school, url)
            continue

        found_info = {
            "school": school.school,
            "class": school.class_,
            "region": school.region,
            "latitude": school_info.get("latitude") or 0.0,
            "longitude": school_info.get("longitude") or 0.0,
            "primary_color": school_info.get("color1") or "",
            "secondary_color": school_info.get("color2") or "",
            "maxpreps_logo": school_info.get("mascotUrl") or "",
        }

        records.append(found_info)

        logger.info("Found info for %r: %s", school.school, found_info)

        # Be polite to MaxPreps
        time.sleep(0.3)

    return records

def update_rows(school_records: Iterable[dict]) -> int:
    """
    Update school information for matching existing schools.
    Returns the number of rows actually updated (cursor.rowcount sum).
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
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            for row in school_records:
                lat = as_float_or_none(row["latitude"])
                lon = as_float_or_none(row["longitude"])

                logger.info("Updating %r (class %s, region %s) with primary color %r, secondary color %r, latitude %s, longitude %s, maxpreps_logo %r", row["school"], row["class"], row["region"], row["primary_color"], row["secondary_color"], lat, lon, row["maxpreps_logo"])

                cur.execute(q, (row["primary_color"], row["secondary_color"], lat, lon, row["maxpreps_logo"], row["school"], row["class"], row["region"]))
                updated += cur.rowcount

        conn.commit()

    logger.info("Updated %d school rows with school info data", updated)
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

@task(retries=2, retry_delay_seconds=10, name="Scrape School Info Data")
def scrape_task(existing_schools: List[School]) -> int:
    """
    Task to scrape school info data from MaxPreps.
    """
    logger = get_run_logger()
    school_records = find_school_info_for_schools(existing_schools)
    logger.info("Found school info records for %d schools", len(school_records))
    logger.info("Found school info records for the following schools: %s", school_records)
    updated_count = update_rows(school_records)
    logger.info("Updated %d schools", updated_count)
    return updated_count


@flow(name="School Info Data Flow")
def school_info_data_flow() -> int:
    """
    Flow to scrape and update school rows with school info data.
    """
    existing_schools = get_existing_schools()
    updated_count = scrape_task(existing_schools)
    return updated_count