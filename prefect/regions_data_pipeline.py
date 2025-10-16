from __future__ import annotations

import re
from typing import Iterable, List, Tuple
from psycopg2.extras import execute_values
from prefect import flow, task, get_run_logger

from data_classes import School
from data_helpers import clean_school_name, to_normal_case, SPACE_RE
from web_helpers import fetch_article_text
from database_helpers import get_database_connection


# -------------------------
# Config
# -------------------------

CLASS_HDR = re.compile(r"\bClass\s+([1-7])A\b", re.IGNORECASE)


# -------------------------
# Prefect tasks & flow
# -------------------------


@task(name="Find Class Sections")
def _find_class_sections(text: str) -> List[Tuple[int, int, int]]:
    """Find each 'Class {N}A' header and return (class_num, start, end)."""
    matches = list(CLASS_HDR.finditer(text))
    sections: List[Tuple[int, int, int]] = []
    for i, m in enumerate(matches):
        cls = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append((cls, start, end))
    return sections


@task(name="Parse Class Section: {cls}")
def _parse_section(text: str, cls: int) -> List[Tuple[str, int, int]]:
    """
    Parse a single Class section into (school, class, region) tuples.
    Each line looks like: 'SCHOOL NAME {class} {region}'.
    """
    rows: List[Tuple[str, int, int]] = []
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


@task(name="Parse Regions from Text")
def parse_regions_from_text(text: str) -> List[dict]:
    """Parse all class sections into dictionaries."""
    out: List[dict] = []
    for cls, start, end in _find_class_sections(text):
        section = text[start:end]
        for school, class_num, region in _parse_section(section, cls):
            out.append({
                "school": school,
                "class": class_num,
                "region": region,
            })
    return out


@task(name="Scrape Regions Data")
def scrape_regions(url: str) -> List[dict]:
    """End-to-end: fetch, parse, clean."""
    text = fetch_article_text(url)
    rows = parse_regions_from_text(text)
    return rows


@task(name="Insert Regions Data")
def insert_rows(rows: Iterable[School]) -> int:
    """
    Insert the given rows into the database.
    Returns the number of rows inserted.
    """
    if not rows:
        return 0
    sql = """
        INSERT INTO schools (school, season, class, region)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (school) DO UPDATE SET
        class  = COALESCE(EXCLUDED.class,  schools.class),
        region = COALESCE(EXCLUDED.region, schools.region);
    """
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, ((row.school, row.season, row.class_, row.region) for row in rows))
            conn.commit()
    return len(list(rows))


@task(retries=2, retry_delay_seconds=10, name="Scrape Regions Data")
def scrape_task(url: str, season: int) -> List[School]:
    """
    Task to scrape the regions data from the given URL.
    """
    logger = get_run_logger()
    logger.info("Fetching and parsing rendered text from %s", url)
    rows = [
        School(
            school=r["school"],
            class_=r["class"],
            region=r["region"],
            season=season
        )
        for r in scrape_regions(url)
    ]
    logger.info("Parsed %d schools", len(rows))
    return rows


@task(name="Insert Regions Data")
def insert_task(rows: List[School]) -> int:
    """
    Task to insert the given rows into the database.
    """
    logger = get_run_logger()
    inserted = insert_rows(rows)
    logger.info("Inserted %d new rows into schools", inserted)
    return inserted


@flow(name="Regions Data Flow")
def regions_data_flow(season: int = 2025) -> int:
    """
    Flow to scrape and insert regions data.
    """
    regions_source_url = ""
    if (season == 2025):
            regions_source_url = "https://www.misshsaa.com/2024/11/19/2025-27-football-regions/"
    elif (season == 2023):
        regions_source_url = "https://www.misshsaa.com/2022/11/03/2023-25-football-regions/"
    elif (season == 2021):
        regions_source_url = "https://www.misshsaa.com/2020/10/29/2021-23-football-regions/"
    elif (season == 2019):
        regions_source_url = "https://www.misshsaa.com/2018/10/31/2019-21-football-regions/"
    else:
        raise ValueError(f"No regions URL configured for season {season}") 
    rows = scrape_task(regions_source_url, season)
    inserted = insert_task(rows)
    return inserted