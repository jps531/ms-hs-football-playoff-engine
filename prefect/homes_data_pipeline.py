from __future__ import annotations

import os
import re
from typing import Iterable, List, Tuple
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

from prefect import flow, task, get_run_logger

import requests
from bs4 import BeautifulSoup

from data_classes import School
from data_helpers import fetch_article_text, to_normal_case, SPACE_RE
from database_helpers import get_database_connection


# -------------------------
# Config
# -------------------------

# --- DATABASE CONFIG ---
DB_HOST = os.getenv("POSTGRES_HOST", "db")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "mshsfootball")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

# --- HOMES SCRAPE CONFIG ---
DEFAULT_HOMES_SOURCE_URL = "https://www.maxpreps.com/ms/football/schools/"
HOMES_SOURCE_URL = os.getenv("HOMES_SOURCE_URL", DEFAULT_HOMES_SOURCE_URL)


# --- HOMES CLEANING CONFIG ---
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

# --- WEB REQUEST CONFIG ---
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Safari/537.36")

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


def _is_school_link(href: str, state: str) -> bool:
    """
    Accept paths like /ms/jackson/callaway-chargers/football (4 parts after leading slash)
    Reject /ms/, /ms/schools/, /ms/rankings/, etc.
    """
    try:
        p = urlparse(href)
        parts = [seg for seg in p.path.split("/") if seg]
        return len(parts) == 4 and parts[0].lower() == state.lower()
    except Exception:
        return False
    

def fetch_state_school_links(state_code: str = "ms"):
    """
    Returns a list of dicts: {"name": str, "city": str | None, "href": str}
    scraped from https://www.maxpreps.com/{state_code}/football/schools/
    """

    logger = get_run_logger()
    logger.info("Fetching school links for state code: %s", state_code)

    base = "https://www.maxpreps.com"
    url  = f"{base}/{state_code}/football/schools/"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        page = browser.new_page(user_agent=UA)
        page.set_default_navigation_timeout(60000)
        page.goto(url, wait_until="domcontentloaded")
        # Wait until client-side renders the list
        page.wait_for_selector(f"a[href^='/{state_code}/']", timeout=15000)

        anchors = page.query_selector_all(f"a[href^='/{state_code}/']")
        out, seen = [], set()
        for a in anchors:
            href = a.get_attribute("href") or ""
            if not href or not _is_school_link(href, state_code):
                continue

            text = (a.inner_text() or "").strip()
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if not lines:
                continue

            if len(lines) > 1 and re.match(r"^[A-Z]$", lines[0]):
                lines = lines[1:]

            name = lines[0]

            if len(name) <= 2 or "," in name:
                continue

            city = None
            for ln in lines[1:]:
                m = re.match(r"^(.+),\s*[A-Z]{2}$", ln)
                if m:
                    city = m.group(1).strip()
                    break

            abs_href = urljoin(base, href)
            key = (name, abs_href)
            if key in seen:
                continue
            seen.add(key)

            out.append({"name": name, "city": city, "href": abs_href})

        browser.close()
        logger.info("Found %d unique school links", len(out))
        logger.info("Found the following unique school links: %s", out)
        return out


def update_rows(existing_schools: Iterable[School], school_links: Iterable[dict]) -> int:
    """
    Update schools.city and schools.homepage for matching existing schools.
    Returns the number of rows actually updated (cursor.rowcount sum).
    """
    if not school_links or not existing_schools:
        return 0

    logger = get_run_logger()

    # --- build a fast lookup from scraped list, keyed by normalized name ---
    def _norm(s: str) -> str:
        if not s:
            return ""
        # Reuse your cleaning rules, then lower/collapse spaces for stable matching
        s = CLEAN_RE.sub("", s)
        s = SPACE_RE.sub(" ", s).strip(" ,.-\u2013\u2014\t\r\n")
        return s.lower()

    scraped_index = {}
    for item in school_links:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        key = _norm(name)
        # Prefer first-seen; if you want last-wins, just assign unconditionally
        scraped_index.setdefault(key, {
            "city": (item.get("city") or "").strip() or None,
            "href": (item.get("href") or "").strip() or None,
        })

    # --- do the updates ---
    q = """
        UPDATE schools
           SET city     = COALESCE(NULLIF(%s, ''), city),
               homepage = COALESCE(NULLIF(%s, ''), homepage)
         WHERE school = %s AND class = %s AND region = %s
    """

    updated = 0
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            for row in existing_schools:
                key = _norm(row.school)
                match = scraped_index.get(key)
                if not match:
                    continue

                city = match["city"] or ""
                homepage = match["href"] or ""

                cur.execute(q, (city, homepage, row.school, row.class_, row.region))
                updated += cur.rowcount

        conn.commit()

    logger.info("Updated %d school rows with city/homepage", updated)
    return updated


def get_existing_schools() -> List[School]:
    """
    Gets the list of existing schools from the database.
    """
    q = """
        SELECT school, class, region FROM schools
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

@task(retries=2, retry_delay_seconds=10, name="Scrape Homes Data")
def scrape_task(url: str, existing_schools: List[School]) -> List[School]:
    """
    Task to scrape the homes data from the given URL.
    """
    logger = get_run_logger()
    logger.info("Fetching and parsing rendered text from %s", url)
    school_links = fetch_state_school_links()
    updated_count = update_rows(existing_schools, school_links)
    logger.info("Updated %d schools", updated_count)
    return updated_count


@flow(name="Homes Data Flow")
def homes_data_flow() -> int:
    """
    Flow to scrape and update school rows with homes data.
    """
    existing_schools = get_existing_schools()
    rows = scrape_task(HOMES_SOURCE_URL, existing_schools)
    return rows