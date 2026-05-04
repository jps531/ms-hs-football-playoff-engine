"""Prefect tasks and flow for populating school identity data from misshsaa.com.

Scrapes the Mississippi High School Activities Association school directory
(https://www.misshsaa.com/mhsaa-school-directory/) for mascot (nickname),
primary color, and secondary color.  The directory page is a Knack app that
is JavaScript-rendered, so Playwright is used for headless rendering.

misshsaa.com robots.txt only disallows /wp-admin/; all other pages are open.
"""

import time as _time
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from prefect import flow, get_run_logger, task
from psycopg2.extras import execute_batch

from backend.helpers.data_classes import School
from backend.helpers.data_helpers import (
    _color_to_hex,
    _colors_csv_to_hex,
    _norm,
    _normalize_mascot,
    _parse_colors,
    normalize_nces_school_name,
)
from backend.helpers.database_helpers import get_database_connection
from backend.helpers.web_helpers import UA, _ratio

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DIRECTORY_URL = "https://www.misshsaa.com/mhsaa-school-directory/"
_MATCH_THRESHOLD = 0.75
_PLAYWRIGHT_TIMEOUT_MS = 30_000
# Knack school-type values that correspond to MHSAA football programs.
_HS_TYPES = {"High School", "Attendance Center"}

# Post-normalisation name remaps for directory entries whose institutional
# name doesn't cleanly reduce to the DB short name via normalize_nces_school_name.
# Key: _norm(normalize_nces_school_name(directory_name)); value: _norm(db_name).
_MHSAA_NAME_REMAPS = {
    "lafayette county": "lafayette",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _render_directory_page() -> str:
    """Paginate through all pages of the Knack school directory and return combined HTML.

    The directory defaults to 100 items per page (5 pages total).  Switching
    the per-page selector via Playwright does not reliably trigger a Knack
    reload, so instead we click the "next" arrow on each page, collect the
    item HTML, and return all items wrapped in a single ``<div>``.  The parser
    can then treat the combined result as if it were one page.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(user_agent=UA)
        page.goto(_DIRECTORY_URL, wait_until="networkidle", timeout=_PLAYWRIGHT_TIMEOUT_MS)
        page.wait_for_selector(".kn-list-item-container", timeout=_PLAYWRIGHT_TIMEOUT_MS)

        all_items: list[str] = []

        while True:
            chunk: str = page.eval_on_selector_all(
                ".kn-list-item-container",
                "els => els.map(el => el.outerHTML).join('')",
            )
            all_items.append(chunk)

            # Playwright's locator engine pierces shadow DOM; document.querySelector
            # does not. Use locator API for both the existence check and the click.
            next_btn = page.locator(".kn-change-page.kn-next")
            if not next_btn.count():
                break
            # Check disabled state separately — the CSS :not(.disabled) compound
            # selector is unreliable on shadow-DOM elements in headless containers.
            if "disabled" in (next_btn.first.get_attribute("class") or ""):
                break

            # Capture the first item's text so we can detect when the page turns.
            # networkidle alone is unreliable in the containerised environment:
            # it can return before Knack finishes swapping the list DOM.
            before = page.locator(".kn-list-item-container").first.inner_text()
            next_btn.first.dispatch_event("click")
            deadline = _time.monotonic() + _PLAYWRIGHT_TIMEOUT_MS / 1000
            while _time.monotonic() < deadline:
                page.wait_for_timeout(300)
                try:
                    if page.locator(".kn-list-item-container").first.inner_text() != before:
                        break
                except Exception:
                    continue

        browser.close()

    return "<div>" + "".join(all_items) + "</div>"


def _parse_directory_html(html: str) -> list[dict]:
    """Parse rendered Knack directory HTML into a list of school dicts.

    Each dict has keys: ``name``, ``mascot``, ``primary_color``, ``secondary_color``.

    Knack field IDs confirmed against live page (2025):
      field_1  — school name (in ``.kn-label-none`` container)
      field_32 — school type ("High School", "Middle School", etc.)
      field_37 — mascot
      field_38 — school colors

    Only "High School" and "Attendance Center" entries are returned; middle
    schools, junior high schools, and district offices are skipped.
    """
    soup = BeautifulSoup(html, "html.parser")
    records = []

    for item in soup.select(".kn-list-item-container"):
        type_el = item.select_one(".field_32 .kn-detail-body")
        if not type_el or type_el.get_text(strip=True) not in _HS_TYPES:
            continue

        name_el = item.select_one(".kn-label-none.field_1")
        mascot_el = item.select_one(".field_37 .kn-detail-body")
        colors_el = item.select_one(".field_38 .kn-detail-body")

        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        mascot = _normalize_mascot(mascot_el.get_text(strip=True) if mascot_el else "")
        colors_text = colors_el.get_text(strip=True) if colors_el else ""

        primary, secondary = _parse_colors(colors_text)

        if name:
            records.append(
                {
                    "name": name,
                    "mascot": mascot,
                    "primary_color": primary,
                    "secondary_color": secondary,
                    "primary_color_hex": _color_to_hex(primary),
                    "secondary_color_hex": _colors_csv_to_hex(secondary),
                }
            )

    return records


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@task(task_run_name="Scrape MHSAA School Directory")
def scrape_directory() -> list[dict]:
    """Render the MHSAA school directory and return parsed school records."""
    logger = get_run_logger()
    logger.info("Rendering MHSAA school directory via Playwright")
    html = _render_directory_page()
    records = _parse_directory_html(html)
    logger.info("Parsed %d school records from directory", len(records))
    if not records:
        logger.warning(
            "No records parsed from MHSAA directory — page structure may have changed. "
            "Inspect %s and update _parse_directory_html().",
            _DIRECTORY_URL,
        )
    return records


@task(task_run_name="Match MHSAA Directory Records to DB Schools")
def match_directory_to_db(directory_records: list[dict], db_schools: list[School]) -> list[dict]:
    """Fuzzy-match each directory record to a canonical DB school name."""
    logger = get_run_logger()
    db_norms = {_norm(s.school): s.school for s in db_schools}

    matched: list[dict] = []
    unmatched: list[str] = []

    for rec in directory_records:
        # Directory names are full institutional names ("Aberdeen High School");
        # DB names are short ("Aberdeen"). Strip suffixes before fuzzy matching.
        normalized = _norm(normalize_nces_school_name(rec["name"]))
        normalized = _MHSAA_NAME_REMAPS.get(normalized, normalized)
        best_key = max(db_norms, key=lambda k, n=normalized: _ratio(n, k))
        best_score = _ratio(normalized, best_key)
        if best_score >= _MATCH_THRESHOLD:
            matched.append(
                {
                    "school": db_norms[best_key],
                    "mascot": rec["mascot"],
                    "primary_color": rec["primary_color"],
                    "secondary_color": rec["secondary_color"],
                    "primary_color_hex": rec["primary_color_hex"],
                    "secondary_color_hex": rec["secondary_color_hex"],
                }
            )
            logger.debug("Directory %r → %r (score %.2f)", rec["name"], db_norms[best_key], best_score)
        else:
            unmatched.append(rec["name"])

    if unmatched:
        logger.warning(
            "%d directory records unmatched (threshold %.2f): %s",
            len(unmatched),
            _MATCH_THRESHOLD,
            unmatched,
        )
    logger.info(
        "Matched %d / %d directory records to DB schools",
        len(matched),
        len(directory_records),
    )
    return matched


@task(task_run_name="Write MHSAA Identity Data to DB")
def update_rows(school_records: list[dict]) -> int:
    """Update mascot, primary_color, secondary_color — skip any field with an override."""
    if not school_records:
        return 0

    logger = get_run_logger()
    sql = """
        UPDATE schools
        SET mascot              = CASE WHEN overrides ? 'mascot'              THEN mascot              ELSE COALESCE(NULLIF(%s, ''), mascot)              END,
            primary_color       = CASE WHEN overrides ? 'primary_color'       THEN primary_color       ELSE COALESCE(NULLIF(%s, ''), primary_color)       END,
            secondary_color     = CASE WHEN overrides ? 'secondary_color'     THEN secondary_color     ELSE COALESCE(NULLIF(%s, ''), secondary_color)     END,
            primary_color_hex   = CASE WHEN overrides ? 'primary_color_hex'   THEN primary_color_hex   ELSE COALESCE(NULLIF(%s, ''), primary_color_hex)   END,
            secondary_color_hex = CASE WHEN overrides ? 'secondary_color_hex' THEN secondary_color_hex ELSE COALESCE(NULLIF(%s, ''), secondary_color_hex) END
        WHERE school = %s
    """
    rows_data = [
        (
            r["mascot"],
            r["primary_color"],
            r["secondary_color"],
            r["primary_color_hex"],
            r["secondary_color_hex"],
            r["school"],
        )
        for r in school_records
    ]
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            execute_batch(cur, sql, rows_data, page_size=200)
        conn.commit()
    logger.info("Updated identity data for %d schools", len(rows_data))
    return len(rows_data)


@task(task_run_name="Apply MHSAA Identity Seeds")
def apply_seed_identity() -> int:
    """Execute sql/seeds/seed_mhsaa_identity.sql to fill in schools absent from the directory.

    Covers schools not present in — or not matchable from — the MHSAA school
    directory (e.g. West Bolivar, Hazlehurst).  Safe to re-run; each statement
    is a no-op when the value is already set.
    """
    seed_path = Path(__file__).parents[2] / "sql" / "seeds" / "seed_mhsaa_identity.sql"
    logger = get_run_logger()
    sql_text = seed_path.read_text()
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
    logger.info("MHSAA identity seed applied: %d rows updated", total)
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


@flow(name="MHSAA School Identity Data Flow")
def misshsaa_school_data_flow() -> int:
    """Scrape MHSAA school directory and write mascot/colors to the DB."""
    db_schools = get_existing_schools()
    directory_records = scrape_directory()
    matched = match_directory_to_db(directory_records, db_schools)
    updated = update_rows(matched)
    apply_seed_identity()
    return updated
