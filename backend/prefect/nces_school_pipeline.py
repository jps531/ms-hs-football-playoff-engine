"""Prefect tasks and flow for populating school geographic data from NCES EDGE API.

Fetches latitude, longitude, city, and ZIP for every Mississippi public high
school from the National Center for Education Statistics EDGE geocode service
(public domain US government data, no ToS restrictions).  Fuzzy-matches NCES
school names against the canonical names already in the ``schools`` table and
writes the four geographic fields, skipping any field protected by an override.
"""

import time
from pathlib import Path

import requests
from prefect import flow, get_run_logger, task
from psycopg2.extras import execute_batch

from backend.helpers.data_classes import School
from backend.helpers.data_helpers import _norm, normalize_nces_school_name
from backend.helpers.database_helpers import get_database_connection
from backend.helpers.web_helpers import UA, _ratio

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NCES_URL = (
    "https://nces.ed.gov/opengis/rest/services/K12_School_Locations/EDGE_ADMINDATA_PUBLICSCH_2223/MapServer/0/query"
)
_NCES_PARAMS = {
    "where": "LSTATE = 'MS'",
    "outFields": "SCH_NAME,LCITY,LZIP,LATCOD,LONCOD",
    "f": "json",
    "resultRecordCount": 1000,
}
_MATCH_THRESHOLD = 0.75


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@task(task_run_name="Fetch NCES School Locations for Mississippi")
def fetch_nces_schools() -> list[dict]:
    """Paginate the NCES EDGE API and return all MS high school records."""
    logger = get_run_logger()
    headers = {"User-Agent": UA, "Accept": "application/json"}
    records: list[dict] = []
    offset = 0

    while True:
        params = {**_NCES_PARAMS, "resultOffset": offset}
        r = requests.get(_NCES_URL, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        payload = r.json()

        features = payload.get("features") or []
        for feat in features:
            attrs = feat.get("attributes") or {}
            records.append(
                {
                    "nces_name": attrs.get("SCH_NAME") or "",
                    "city": (attrs.get("LCITY") or "").title(),
                    "zip": attrs.get("LZIP") or "",
                    "latitude": attrs.get("LATCOD"),
                    "longitude": attrs.get("LONCOD"),
                }
            )

        if not payload.get("exceededTransferLimit"):
            break
        offset += len(features)
        time.sleep(0.2)

    logger.info("Fetched %d NCES school records", len(records))
    return records


@task(task_run_name="Match NCES Records to DB Schools")
def match_nces_to_db(nces_records: list[dict], db_schools: list[School]) -> list[dict]:
    """Fuzzy-match each NCES record to a canonical DB school name.

    Returns a list of dicts ready for the update query, one entry per
    successfully matched school.  Unmatched records are logged and skipped.
    """
    logger = get_run_logger()
    db_norms = {_norm(s.school): s.school for s in db_schools}

    matched: list[dict] = []
    unmatched: list[str] = []

    for rec in nces_records:
        normalized = _norm(normalize_nces_school_name(rec["nces_name"]))
        best_key = max(db_norms, key=lambda k, n=normalized: _ratio(n, k))
        best_score = _ratio(normalized, best_key)
        if best_score >= _MATCH_THRESHOLD:
            matched.append(
                {
                    "school": db_norms[best_key],
                    "city": rec["city"],
                    "zip": rec["zip"],
                    "latitude": rec["latitude"],
                    "longitude": rec["longitude"],
                }
            )
            logger.debug("NCES %r → %r (score %.2f)", rec["nces_name"], db_norms[best_key], best_score)
        else:
            unmatched.append(rec["nces_name"])

    if unmatched:
        logger.warning(
            "%d NCES records unmatched (threshold %.2f): %s",
            len(unmatched),
            _MATCH_THRESHOLD,
            unmatched,
        )
    logger.info("Matched %d / %d NCES records to DB schools", len(matched), len(nces_records))
    return matched


@task(task_run_name="Write NCES Geographic Data to DB")
def update_rows(school_records: list[dict]) -> int:
    """Update city, zip, latitude, longitude — skip any field with an override."""
    if not school_records:
        return 0

    logger = get_run_logger()
    sql = """
        UPDATE schools
        SET city      = CASE WHEN overrides ? 'city'      THEN city      ELSE COALESCE(NULLIF(%s, ''), city)      END,
            zip       = CASE WHEN overrides ? 'zip'       THEN zip       ELSE COALESCE(NULLIF(%s, ''), zip)       END,
            latitude  = CASE WHEN overrides ? 'latitude'  THEN latitude  ELSE COALESCE(%s, latitude)              END,
            longitude = CASE WHEN overrides ? 'longitude' THEN longitude ELSE COALESCE(%s, longitude)             END
        WHERE school = %s
    """
    rows_data = [(r["city"], r["zip"], r["latitude"], r["longitude"], r["school"]) for r in school_records]
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            execute_batch(cur, sql, rows_data, page_size=200)
        conn.commit()
    logger.info("Updated geographic data for %d schools", len(rows_data))
    return len(rows_data)


@task(task_run_name="Apply Private School Location Seeds")
def apply_seed_locations() -> int:
    """Execute sql/seeds/seed_private_school_locations.sql against the DB.

    Covers private schools and ambiguous-name schools that the NCES pipeline
    cannot match.  Safe to re-run — each UPDATE is a no-op if the value is
    already set.
    """
    seed_path = Path(__file__).parents[2] / "sql" / "seeds" / "seed_private_school_locations.sql"
    logger = get_run_logger()
    sql_text = seed_path.read_text()
    # Strip comment/blank lines then split on ";" to get individual statements.
    data_lines = [ln for ln in sql_text.splitlines() if ln.strip() and not ln.strip().startswith("--")]
    statements = [s.strip() for s in "\n".join(data_lines).split(";") if s.strip()]
    if not statements:
        logger.warning("No statements found in %s", seed_path)
        return 0
    total = 0
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)
                total += max(cur.rowcount, 0)
        conn.commit()
    logger.info("Private school seed applied: %d rows updated", total)
    return total


def get_existing_schools() -> list[School]:
    """Fetch the distinct list of all schools from the database."""
    q = "SELECT DISTINCT school, 0, 0, 0 FROM schools"
    schools: list[School] = []
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(q)
            for row in cur.fetchall():
                schools.append(School.from_db_tuple(row))
    return schools


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------


@flow(name="NCES School Geographic Data Flow")
def nces_school_data_flow() -> int:
    """Fetch NCES school locations and write city/zip/lat/lon to the DB."""
    db_schools = get_existing_schools()
    nces_records = fetch_nces_schools()
    matched = match_nces_to_db(nces_records, db_schools)
    updated = update_rows(matched)
    apply_seed_locations()
    return updated
