from __future__ import annotations

import re, time, requests
from typing import Dict, Any, Iterable, List, Mapping, Optional, Union
from urllib.parse import quote_plus
from psycopg2.extras import execute_batch
from prefect import flow, task, get_run_logger

from prefect_files.data_classes import School
from data_helpers import _get_field, _norm, update_school_name_for_maxpreps_search
from database_helpers import get_database_connection
from web_helpers import UA, _extract_next_data, _iter_dicts, _ratio


# -------------------------
# Helpers
# -------------------------


@task(task_run_name="Find MaxPreps School Record for {school_name}")
def find_maxpreps_school_record(school_name: str, state_abbrev: str = "MS") -> Optional[Dict]:
    """
    Return the best matching school record from MaxPreps search for the given name.
    The record includes: name, city, zip, mascot, canonicalUrl, schoolId, state.

    Example:
      {'name': 'DeSoto Central', 'city': 'Southaven', 'zip': '38672-6795',
       'mascot': 'Jaguars',
       'canonicalUrl': 'https://www.maxpreps.com/ms/southaven/desoto-central-jaguars/',
       'schoolId': '1f1e94a4-fd1e-493e-9f72-060604041001', 'state': 'MS'}
    """
    logger = get_run_logger()
    q_norm = _norm(school_name)
    url = f"https://www.maxpreps.com/search/?q={quote_plus(update_school_name_for_maxpreps_search(school_name))}"
    headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}

    logger.info("Searching MaxPreps for school %r via %s", school_name, url)

    r = requests.get(url, headers=headers, timeout=25)
    r.raise_for_status()
    data = _extract_next_data(r.text)

    # Prefer the structured list provided by the page
    page_props = (data or {}).get("props", {}).get("pageProps", {})
    results: List[Dict] = page_props.get("initialSchoolResults", []) or []

    # Filter to requested state (case-insensitive)
    state_up = (state_abbrev or "").upper()
    candidates = [row for row in results if (row.get("state", "").upper() == state_up)]

    if not candidates:
        logger.info("No initialSchoolResults for state=%s; falling back to generic scrape", state_abbrev)
        # Fallback: walk the JSON for canonical school hrefs if needed
        # (kept small: returns None if nothing is found)
        href_candidates: List[Dict] = []
        for node in _iter_dicts(data):
            href = node.get("href") or node.get("url")
            title = node.get("title") or node.get("name") or node.get("text")
            subtitle = node.get("subtitle") or node.get("description") or ""
            if not href or not isinstance(href, str): 
                continue
            # pattern like "/ms/<city>/<slug>/" (canonical school page)
            if not re.match(r"^/[a-z]{2}/[^/]+/[^/]+/?$", href, re.I):
                continue
            if not title or not isinstance(title, str):
                continue
            # Try to keep state consistent if present in subtitle
            if state_up and not re.search(rf",\s*{re.escape(state_up)}\b", subtitle, re.I):
                continue
            href_candidates.append({"title": title.strip(), "href": href})

        if not href_candidates:
            return None

        # Score by fuzzy similarity to the *title* we saw
        best = max(href_candidates, key=lambda c: _ratio(_norm(c["title"]), q_norm))
        return {
            "name": best["title"],
            "city": None,
            "zip": None,
            "mascot": None,
            "maxpreps_url": "https://www.maxpreps.com" + best["href"],
            "maxpreps_id": None,
        }

    # Choose the best candidate by fuzzy name match
    def score(row: Dict) -> float:
        return _ratio(_norm(row.get("name", "")), q_norm)

    best_row = max(candidates, key=score)

    # Normalize output shape
    record = {
        "name": best_row.get("name"),
        "city": best_row.get("city"),
        "zip": best_row.get("zip"),
        "mascot": "Gators" if best_row.get("name") == "Lake Cormorant" else best_row.get("mascot"),
        "maxpreps_url": best_row.get("canonicalUrl"),
        "maxpreps_id": best_row.get("schoolId"),
    }
    logger.info("Resolved %r → %s (%s, %s, %s)", school_name, record["maxpreps_url"], record["city"], record["zip"], record["mascot"])
    return record


@task(task_run_name="Find MaxPreps Records for Schools")
def find_records_for_schools(rows: Iterable[Union["School", Mapping[str, Any]]]) -> List[dict]:
    """
    rows: iterable of School dataclass instances or dicts with keys:
          school, season, class_/class, region
    Returns: [{'school', 'season', 'class', 'region', 'city'}...]
    """
    out: List[dict] = []
    logger = get_run_logger()
    rows_list = list(rows)
    logger.info("Finding MaxPreps URLs for %d schools", len(rows_list))

    for r in rows_list:
        school_name = _get_field(r, "school")
        season = _get_field(r, "season")
        cls = _get_field(r, "class_", "class")
        region = _get_field(r, "region")

        if not school_name:
            logger.warning("Row missing 'school' field; skipping: %r", r)
            continue

        record = find_maxpreps_school_record(school_name, "MS")

        if not record:
            logger.warning("No MaxPreps match for %r; skipping", school_name)
            continue

        out.append({"school": school_name, "season": season, "class": cls, "region": region, "city": record.get("city") or "", "zip": record.get("zip") or "", "mascot": record.get("mascot") or "", "maxpreps_id": record.get("maxpreps_id") or "", "maxpreps_url": record.get("maxpreps_url") or "", "primary_color": "", "secondary_color": ""})
        logger.info("Found record for %s (%s): %s", school_name, season, record)

        time.sleep(0.3)  # polite rate limit

    return out

@task(task_run_name="Insert Updated MaxPreps Info Data")
def update_rows(school_records: Iterable[dict]) -> int:
    """
    Update MaxPreps information for matching existing schools.
    Returns the number of rows actually updated (cursor.rowcount sum).
    """
    if not school_records:
        return 0

    logger = get_run_logger()

    # --- do the updates ---
    sql = """
        UPDATE schools
        SET city         = COALESCE(NULLIF(%s, ''), city),
            zip          = COALESCE(NULLIF(%s, ''), zip),
            mascot       = COALESCE(NULLIF(%s, ''), mascot),
            maxpreps_id  = COALESCE(NULLIF(%s, ''), maxpreps_id),
            maxpreps_url = COALESCE(NULLIF(%s, ''), maxpreps_url)
        WHERE school = %s AND season = %s AND class = %s AND region = %s
    """

    # If school_records might be a generator, materialize it ONCE
    records = list(school_records)
    logger.info("Updating %d school records in schools table", len(records))

    rows_data = [
        (
            r["city"],
            r["zip"],
            r["mascot"],
            r["maxpreps_id"],
            r["maxpreps_url"],
            r["school"],   # <-- order matches the WHERE clause
            r["season"],
            r["class"],
            r["region"],
        )
        for r in records
    ]

    with get_database_connection() as conn:
        with conn.cursor() as cur:
            execute_batch(cur, sql, rows_data, page_size=200)
        conn.commit()
    return len(records)


def get_existing_schools() -> List[School]:
    """
    Gets the list of existing schools from the database.
    """
    q = """
        SELECT DISTINCT school, season, class, region FROM schools
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

@task(retries=2, retry_delay_seconds=10, task_run_name="Scrape MaxPreps Data")
def scrape_task(existing_schools: List[School]) -> int:
    """
    Task to scrape the MaxPreps data from the given URL.
    """
    logger = get_run_logger()
    school_records = find_records_for_schools(existing_schools)
    logger.info("Found MaxPreps records for %d schools", len(school_records))
    logger.info("Found MaxPreps records for the following schools: %s", school_records)
    updated_count = update_rows(school_records)
    logger.info("Updated %d schools", updated_count)
    return updated_count

@flow(name="MaxPreps Data Flow")
def maxpreps_data_flow() -> int:
    """
    Flow to scrape and update school rows with MaxPreps data.
    """
    existing_schools = get_existing_schools()
    rows = scrape_task(existing_schools)
    return rows