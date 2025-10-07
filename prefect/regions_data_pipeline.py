from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable, List

import pandas as pd
from prefect import flow, task, get_run_logger

from data_helpers import fetch_article_text, to_normal_case, get_conn, SPACE_RE


# -------------------------
# Config
# -------------------------

# --- DATABASE CONFIG ---
DB_HOST = os.getenv("POSTGRES_HOST", "db")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "mshsfootball")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

# --- REGIONS SCRAPE CONFIG ---
DEFAULT_REGIONS_SOURCE_URL = "https://www.misshsaa.com/2024/11/19/2025-27-football-regions/"
REGIONS_SOURCE_URL = os.getenv("REGIONS_SOURCE_URL", DEFAULT_REGIONS_SOURCE_URL)


# --- REGIONS CLEANING CONFIG ---
CLEAN_PHRASES = [
    r"\bHigh School\b",
    r"\bHigh\b",
    r"\bSchool\b",
    r"\bPublic\b",
    r"\bMemorial\b",
    r"\bHi Sch\b",
    r"\bSch\b",
    r"\bMiddle\b",
    r"\bSenior\b",
    r"\bJr Sr\b",
    r"\bJr\s*[/\\-]?\s*Sr\b",
    r"\(5-12\)",
    r"\(9-12\)",
    r"\bAttendance Center\b",
    r"\bName\b",
    r"\bClass\b",
    r"\bRegion\b",
]
CLEAN_RE = re.compile("|".join(CLEAN_PHRASES), flags=re.IGNORECASE)
CLASS_HDR = re.compile(r"\bClass\s+([1-7])A\b", re.IGNORECASE)


# -------------------------
# Data Classes
# -------------------------

# --- Data class for a row in the regions table ---
@dataclass
class RegionRow:
    school: str
    class_: int
    region: int

    def as_db_tuple(self):
        return (self.school, self.class_, self.region)


# -------------------------
# Helpers
# -------------------------

def clean_school_name(raw: str) -> str:
    """
    Clean the given raw school name by removing unwanted phrases and normalizing case.
    """
    tmp = CLEAN_RE.sub("", raw)
    tmp = SPACE_RE.sub(" ", tmp).strip(" ,.-\u2013\u2014\t\r\n")
    return to_normal_case(tmp)


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

def scrape_regions(url: str) -> List[dict]:
    """End-to-end: fetch, parse, clean."""
    text = fetch_article_text(url)
    rows = parse_regions_from_text(text)
    return rows

def insert_rows(rows: Iterable[RegionRow]) -> int:
    """
    Insert the given rows into the database.
    Returns the number of rows inserted.
    """
    if not rows:
        return 0
    q = """
        INSERT INTO schools (school, class, region)
        VALUES (%s, %s, %s)
        ON CONFLICT (school, class, region) DO NOTHING
    """
    count = 0
    with get_conn(DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD) as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(q, row.as_db_tuple())
                # rowcount is 1 for inserted, 0 for no-op on conflict
                count += cur.rowcount
    return count


# -------------------------
# Prefect tasks & flow
# -------------------------

@task(retries=2, retry_delay_seconds=10, name="Scrape Regions Data")
def scrape_task(url: str) -> List[RegionRow]:
    """
    Task to scrape the regions data from the given URL.
    """
    logger = get_run_logger()
    logger.info("Fetching and parsing rendered text from %s", url)
    rows = [
        RegionRow(
            school=r["school"],
            class_=r["class"],
            region=r["region"]
        )
        for r in scrape_regions(url)
    ]
    logger.info("Parsed %d schools", len(rows))
    return rows


@task(name="Insert Regions Data")
def insert_task(rows: List[RegionRow]) -> int:
    """
    Task to insert the given rows into the database.
    """
    logger = get_run_logger()
    inserted = insert_rows(rows)
    logger.info("Inserted %d new rows into schools", inserted)
    return inserted


@flow(name="Regions Data Flow")
def regions_data_flow() -> int:
    """
    Flow to scrape and insert regions data.
    """
    rows = scrape_task(REGIONS_SOURCE_URL)
    inserted = insert_task(rows)
    return inserted