"""Draft a cycle's region file (``backend/data/regions/``) from MHSAA's football regions article.

    uv run python -m backend.tools.draft_regions --season 2027 > backend/data/regions/2027-29.csv

It's a first draft for a person to check, not the source of truth: MHSAA's page has changed format
from one cycle to the next (a table in the article for 2025-27, a table on a page embedded in it for
2027-29), and it can't know a school's new name, a consolidation or a closure. What it can't place it
says on stderr, with the same checks the loader runs (``region_files.problems``): a name the site
doesn't know, a school from last season with no place, a region too small. Fix those in the file or
in ``data_helpers`` (SCHOOL_RENAMES, SCHOOL_SUCCESSORS, SCHOOL_CLOSURES), then load the season with
``regions-data-pipeline``.

Any HTML table of schools reads: rows of school, class and region under "Class 7A", or of school and
"Region 1" under a heading naming the class ("Football — 1A (boys)"). The article's own tables and
those of any page it embeds (an iframe) are read.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from html.parser import HTMLParser

from backend.helpers.data_helpers import clean_school_name, school_name_for_season
from backend.helpers.region_files import FIELDS, assignments_for_season, cycle_path, cycle_start, problems

# Each cycle's article, by the first season of the cycle.
ARTICLES: dict[int, str] = {
    2025: "https://www.misshsaa.com/2024/11/19/2025-27-football-regions/",
    2027: "https://www.misshsaa.com/2026/11/04/2027-29-football-regions/",
}

# MHSAA's spellings (after clean_school_name) that differ from the site's name for the same school.
MHSAA_NAMES: dict[str, str] = {
    "O'Bannon": "O’Bannon",
    "St. Andrews": "St. Andrew’s",
    "Thomas E. Edwards, Sr": "Thomas E. Edwards",
    "Thomas E. Edwards": "Thomas E. Edwards",
    "Jdc": "Jefferson Davis County",
    "Jefferson Davis County High": "Jefferson Davis County",
}

_CLASS = re.compile(r"\b([1-7])A\b")
_REGION = re.compile(r"Region\s+([1-8])$")


class _Tables(HTMLParser):
    """Rows of school tables, in document order: (class, school as written, region)."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[tuple[int, str, int]] = []
        self.clazz: int | None = None
        self._cells: list[str] | None = None
        self._cell: str | None = None
        self._heading: str | None = None

    def handle_starttag(self, tag, attrs):
        """Start a heading, a row or a cell."""
        if tag in ("h1", "h2", "h3", "h4", "caption"):
            self._heading = ""
        elif tag == "tr":
            self._cells = []
        elif tag in ("td", "th") and self._cells is not None:
            self._cell = ""

    def handle_endtag(self, tag):
        """Finish a heading (it may name the class), a cell, or a row (it may be a school)."""
        if tag in ("h1", "h2", "h3", "h4", "caption") and self._heading is not None:
            self._class_from(self._heading)
            self._heading = None
        elif tag in ("td", "th") and self._cell is not None and self._cells is not None:
            self._cells.append(" ".join(self._cell.split()))
            self._cell = None
        elif tag == "tr" and self._cells is not None:
            self._row([c for c in self._cells])
            self._cells = None

    def handle_data(self, data):
        """Text inside the open cell or heading."""
        if self._cell is not None:
            self._cell += data
        if self._heading is not None:
            self._heading += data

    def _class_from(self, text: str) -> None:
        """Take the class from a heading like "Class 7A" or "Football — 1A (boys)"."""
        m = _CLASS.search(text)
        if m and ("Class" in text or "Football" in text or len(text) < 40):
            self.clazz = int(m.group(1))

    def _row(self, cells: list[str]) -> None:
        """Keep a row that's a school: school, class, region; or school and "Region N" under a class heading."""
        filled = [c for c in cells if c]
        if len(filled) == 3 and filled[1].isdigit() and filled[2].isdigit():
            self.rows.append((int(filled[1]), filled[0], int(filled[2])))
        elif len(filled) == 2 and (m := _REGION.match(filled[1])) and self.clazz:
            self.rows.append((self.clazz, filled[0], int(m.group(1))))
        elif len(filled) == 1 and filled[0].startswith("Class"):
            self._class_from(filled[0])


def parse_tables(html: str) -> list[tuple[int, str, int]]:
    """Every school row in *html*'s tables: (class, school as MHSAA writes it, region)."""
    parser = _Tables()
    parser.feed(html)
    return parser.rows


def site_name(raw: str, season: int) -> str:
    """The site's name for a school as MHSAA writes it, in *season*."""
    name = clean_school_name(raw)
    return school_name_for_season(MHSAA_NAMES.get(name, name), season)


def draft(documents: list[str], season: int) -> dict[str, tuple[int, int]]:
    """Each school's (class, region) from the tables in *documents* (HTML), under the site's names."""
    out = {}
    for html in documents:
        for clazz, raw, region in parse_tables(html):
            out[site_name(raw, season)] = (clazz, region)
    return out


def to_csv(assigned: dict[str, tuple[int, int]]) -> str:
    """A cycle file's text: one school a line, by class, region and name, every season of the cycle."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(FIELDS)
    for school, (clazz, region) in sorted(assigned.items(), key=lambda kv: (kv[1][0], kv[1][1], kv[0].lower())):
        w.writerow([school, clazz, region, ""])
    return buf.getvalue()


def fetch(url: str) -> list[str]:  # pragma: no cover - a real browser on the real page
    """The article's HTML and that of each page embedded in it, as a browser renders them."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        article = page.locator("article .entry-content, .entry-content, article").first
        documents = [article.inner_html()]
        for src in article.locator("iframe").evaluate_all("els => els.map((e) => e.src)"):
            if src.startswith("https://") and "maxpreps" not in src:
                embedded = browser.new_page()
                embedded.goto(src, wait_until="networkidle")
                documents.append(embedded.content())
        browser.close()
    return documents


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - the command line
    """Print the draft file for ``--season``'s cycle; say what needs a person on stderr."""
    args = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    args.add_argument("--season", type=int, required=True, help="the cycle's first season (2027 for 2027-29)")
    args.add_argument("--url", help="the article (default: ARTICLES for the cycle)")
    opts = args.parse_args(argv)
    season = cycle_start(opts.season)
    url = opts.url or ARTICLES.get(season)
    if not url:
        print(f"No article for {season}: pass --url, or add it to ARTICLES.", file=sys.stderr)
        return 2
    assigned = draft(fetch(url), season)
    sys.stdout.write(to_csv(assigned))
    prior_path = cycle_path(season - 1)
    prior = set(assignments_for_season(season - 1, prior_path)) if prior_path.exists() else None
    known = set(prior or ())  # the schools of last cycle's file; the loader checks against the database
    issues = problems(assigned, season, known, prior)
    print(f"{len(assigned)} schools from {url}", file=sys.stderr)
    for issue in issues:
        print(f"CHECK: {issue}", file=sys.stderr)
    return 1 if issues else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
