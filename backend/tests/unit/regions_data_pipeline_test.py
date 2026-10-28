"""Unit tests for backend.prefect.regions_data_pipeline's parser.

The MHSAA regions article is the source of every school's class and region for a season, so
the parser decides which region page each school appears on. The text below is laid out the way
``fetch_article_text`` returns the article: a "Class NA" heading per class, a header row, then one
"SCHOOL NAME {class} {region}" line per school.
"""

import logging

import pytest

import backend.prefect.regions_data_pipeline as pipeline
from backend.prefect.regions_data_pipeline import _find_class_sections, _parse_section, parse_regions_from_text

ARTICLE = """2025-27 Football Regions
Class 1A
School Name Class Region
Biggersville High School 1 1
Mount Olive Attendance Center 1 8
Class 4A
School Name Class Region
Leake Central High School 4 5
Jefferson Co High 4 7
Class 7A
School Name Class Region
Tupelo High School 7 1
Oak Grove High School 7 4
"""


def test_each_class_heading_starts_a_section_that_runs_to_the_next():
    """One section per "Class NA" heading, in page order, ending where the next begins."""
    sections = _find_class_sections(ARTICLE)
    assert [cls for cls, _, _ in sections] == [1, 4, 7]
    (_, s1, e1), (_, s4, _), (_, _, e7) = sections
    assert e1 < s4 and "Mount Olive" in ARTICLE[s1:e1] and "Jefferson" not in ARTICLE[s1:e1]
    assert e7 == len(ARTICLE)


def test_a_section_gives_each_school_its_class_and_region():
    """Names are cleaned the way the rest of the site spells them; the header row isn't a school."""
    _, start, end = _find_class_sections(ARTICLE)[0]
    assert [(s, c, r) for s, c, r in _parse_section(ARTICLE[start:end], 1)][0] == ("Biggersville", 1, 1)
    assert [(c, r) for _, c, r in _parse_section(ARTICLE[start:end], 1)] == [(1, 1), (1, 8)]


def test_the_whole_article_parses_to_every_school():
    """Every school, with its class from its section and its region from its line."""
    rows = [r for r in parse_regions_from_text(ARTICLE) if r["region"] != 8]
    assert rows == [
        {"school": "Biggersville", "class": 1, "region": 1},
        {"school": "Leake Central", "class": 4, "region": 5},
        {"school": "Jefferson County", "class": 4, "region": 7},  # "Jefferson Co High", spelled as the site does
        {"school": "Tupelo", "class": 7, "region": 1},
        {"school": "Oak Grove", "class": 7, "region": 4},
    ]


def test_a_line_whose_class_doesnt_match_its_section_isnt_read_as_a_school():
    """Only "{class} {region}" for the section's own class counts, so a stray number isn't a region."""
    assert _parse_section("School Name Class Region Tupelo High School 6 1", 7) == []


def test_text_with_no_class_headings_gives_nothing():
    """A page that isn't the regions article (an error page, a redesign) yields no schools, not junk."""
    assert parse_regions_from_text("Page not found") == []


def test_scraping_files_renamed_schools_under_the_sites_name_and_applies_overrides(monkeypatch):
    """scrape_task: AHSFHS-lagged names go under the season's name, and the season's overrides win."""
    monkeypatch.setattr(pipeline, "get_run_logger", lambda: logging.getLogger("test"))
    monkeypatch.setattr(pipeline, "fetch_article_text", lambda url: ARTICLE)
    rows = {r.school: (r.class_, r.region) for r in pipeline.scrape_task.fn("http://x", 2026)}
    # Leake Central plays as Leake from 2026 (SCHOOL_RENAMES).
    assert rows["Leake"] == (4, 5) and "Leake Central" not in rows
    rows_2025 = {r.school: (r.class_, r.region) for r in pipeline.scrape_task.fn("http://x", 2025)}
    # 2025's overrides restore what the page said before MHSAA edited it.
    assert rows_2025["Leake County"] == (1, 5) and rows_2025["Leake Central"] == (4, 5)


@pytest.mark.parametrize("season", [2025, 2026])
def test_every_season_has_its_cycles_article(season):
    """The article for a season is its two-year cycle's (odd year first)."""
    start = season if season % 2 else season - 1
    assert start in pipeline._REGIONS_CYCLE_URLS
