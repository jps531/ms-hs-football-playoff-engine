"""Prefect tasks and flow for scraping region/class assignments from the MHSAA website.

Fetches the MHSAA football regions article for the given season, parses each
class section for school-to-region mappings, and writes results to the
``schools`` (``regions``) table via INSERT ... ON CONFLICT UPDATE.
"""

import re
from collections.abc import Iterable
from datetime import date

from prefect import flow, get_run_logger, task
from psycopg2.extras import execute_values

from backend.helpers.data_classes import School
from backend.helpers.data_helpers import SPACE_RE, clean_school_name
from backend.helpers.database_helpers import get_database_connection
from backend.helpers.web_helpers import fetch_article_text

# -------------------------
# Config
# -------------------------

CLASS_HDR = re.compile(r"\bClass\s+([1-7])A\b", re.IGNORECASE)

# MHSAA publishes one classification article per 2-year cycle. Keys are the
# odd year that starts each cycle; add a new entry when MHSAA publishes the
# next cycle's article.
_REGIONS_CYCLE_URLS: dict[int, str] = {
    2019: "https://www.misshsaa.com/2018/10/31/2019-21-football-regions/",
    2021: "https://www.misshsaa.com/2020/10/29/2021-23-football-regions/",
    2023: "https://www.misshsaa.com/2022/11/03/2023-25-football-regions/",
    2025: "https://www.misshsaa.com/2024/11/19/2025-27-football-regions/",
}


# -------------------------
# Prefect tasks & flow
# -------------------------


def _find_class_sections(text: str) -> list[tuple[int, int, int]]:
    """Find each 'Class {N}A' header and return (class_num, start, end)."""
    matches = list(CLASS_HDR.finditer(text))
    sections: list[tuple[int, int, int]] = []
    for i, m in enumerate(matches):
        cls = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append((cls, start, end))
    return sections


def _parse_section(text: str, cls: int) -> list[tuple[str, int, int]]:
    """
    Parse a single Class section into (school, class, region) tuples.
    Each line looks like: 'SCHOOL NAME {class} {region}'.
    """
    rows: list[tuple[str, int, int]] = []
    s = SPACE_RE.sub(" ", text.replace("\n", " ")).strip()
    pattern = re.compile(rf"(.+?)\s{cls}\s([1-8])(?=\s|$)")
    pos = 0
    while True:
        m = pattern.search(s, pos)
        if not m:
            break
        raw_name = m.group(1).strip()
        region = int(m.group(2))

        # Remove trailing junk
        for tail in ("School Name", "School", "Class", "Region"):
            if raw_name.endswith(tail):
                raw_name = raw_name[: -len(tail)].rstrip()

        school = clean_school_name(raw_name)
        if school:
            rows.append((school, cls, region))

        pos = m.end()
    return rows


def parse_regions_from_text(text: str) -> list[dict]:
    """Parse all class sections into dictionaries."""
    out: list[dict] = []
    for cls, start, end in _find_class_sections(text):
        section = text[start:end]
        for school, class_num, region in _parse_section(section, cls):
            out.append(
                {
                    "school": school,
                    "class": class_num,
                    "region": region,
                }
            )
    return out


@task(task_run_name="Fetch Regions Task")
def fetch_regions(url: str) -> list[dict]:
    """End-to-end: fetch, parse, clean."""
    text = fetch_article_text(url)
    rows = parse_regions_from_text(text)
    return rows


@task(task_run_name="Insert Regions Data")
def insert_rows(rows: Iterable[School]) -> int:
    """
    Insert the given rows into the database.
    Upserts into schools (static identity) then school_seasons (class/region).
    Returns the number of rows inserted.
    """
    rows_data = list(rows)
    if not rows_data:
        return 0

    schools_sql = """
        INSERT INTO schools (school)
        VALUES %s
        ON CONFLICT (school) DO NOTHING
    """
    seasons_sql = """
        INSERT INTO school_seasons (school, season, class, region)
        VALUES %s
        ON CONFLICT (school, season) DO UPDATE SET
            class  = COALESCE(EXCLUDED.class,  school_seasons.class),
            region = COALESCE(EXCLUDED.region, school_seasons.region)
            -- is_active is never overwritten by the pipeline; set manually via UPDATE
    """
    schools_data = [(r.school,) for r in rows_data]
    seasons_data = [(r.school, r.season, r.class_, r.region) for r in rows_data]

    with get_database_connection() as conn:
        with conn.cursor() as cur:
            execute_values(cur, schools_sql, schools_data, template="(%s)")
            execute_values(cur, seasons_sql, seasons_data, template="(%s,%s,%s,%s)")
        conn.commit()
    return len(rows_data)


@task(retries=2, retry_delay_seconds=10, task_run_name="Scrape Regions Data")
def scrape_task(url: str, season: int) -> list[School]:
    """
    Task to scrape the regions data from the given URL.
    """
    logger = get_run_logger()
    logger.info("Fetching and parsing rendered text from %s", url)
    text = fetch_article_text(url)
    rows = [
        School(school=r["school"], class_=r["class"], region=r["region"], season=season)
        for r in parse_regions_from_text(text)
    ]
    logger.info("Parsed %d schools", len(rows))
    return rows


@flow(name="Regions Data Flow")
def regions_data_flow(season: int | None = None) -> int:
    """
    Flow to scrape and insert regions data.
    """
    if season is None:
        season = date.today().year
    logger = get_run_logger()
    cycle_start = season if season % 2 == 1 else season - 1
    regions_source_url = _REGIONS_CYCLE_URLS.get(cycle_start)
    if regions_source_url is None:
        raise ValueError(
            f"No regions URL configured for the {cycle_start}–{cycle_start + 1} cycle "
            f"(season {season}). Add it to _REGIONS_CYCLE_URLS in regions_data_pipeline.py."
        )
    rows = scrape_task(regions_source_url, season)
    inserted = insert_rows(rows)
    logger.info("Inserted %d new rows into schools", inserted)
    return inserted
