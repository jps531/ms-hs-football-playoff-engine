"""A school that goes by a new name while the sources still use the old one (SCHOOL_RENAMES in data_helpers):
Leake Central is "Leake" from 2026 on, everywhere the pipelines file data, and keeps its old name before then."""

import logging
import re
from pathlib import Path

import pytest

import backend.prefect.ahsfhs_schedule_pipeline as schedule
from backend.helpers.data_helpers import (
    SCHOOL_RENAMES,
    SCHOOL_SUCCESSORS,
    school_name_for_season,
    source_name_for_season,
    update_school_name_for_ahsfhs_search,
    with_predecessor_ratings,
)
from backend.helpers.region_files import assignments_for_season
from backend.helpers.share_cards import slugify

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _stub_run_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pipeline tasks log through Prefect's run logger, which needs a live run; a plain logger stands in."""
    monkeypatch.setattr(schedule, "get_run_logger", lambda: logging.getLogger("test"))


def test_the_new_name_starts_in_its_first_season_and_history_keeps_the_old():
    """Leake Central is Leake from 2026 on and keeps its old name before; other schools are untouched."""
    assert school_name_for_season("Leake Central", 2026) == "Leake"
    assert school_name_for_season("Leake Central", 2027) == "Leake"
    assert school_name_for_season("Leake Central", 2025) == "Leake Central"
    assert school_name_for_season("Leake County", 2026) == "Leake County"
    assert school_name_for_season("Raleigh", 2026) == "Raleigh"


def test_the_sources_are_still_asked_for_the_old_name():
    """AHSFHS still files the team under Leake Central, so that's the page fetched for 2026's Leake."""
    assert source_name_for_season("Leake", 2026) == "Leake Central"
    assert update_school_name_for_ahsfhs_search(source_name_for_season("Leake", 2026)) == "Leake%20Central"
    assert source_name_for_season("Leake Central", 2025) == "Leake Central"
    assert source_name_for_season("Raleigh", 2026) == "Raleigh"


def test_other_schools_games_against_it_are_filed_under_the_new_name():
    """An opponent's schedule that still says Leake Central files the 2026 game under Leake."""
    def opponent(season: int) -> str:
        """The opponent's name on a parsed Neshoba Central game against Leake Central in *season*."""
        text = f"Opponent Score Fri., Oct. 2 vs. Leake Central 21 14 W {season} Season Totals"
        [game] = schedule.parse_ahsfhs_schedule(
            text, season=season, school_name="Neshoba Central", url="http://x", clazz=5
        )
        return game.opponent

    assert opponent(2026) == "Leake"
    assert opponent(2025) == "Leake Central"


def test_the_region_file_has_it_under_the_new_name():
    """The 2025-27 file has Leake Central (5-4A) for 2025 and Leake (2-5A) for 2026."""
    assert assignments_for_season(2025)["Leake Central"] == (4, 5)
    assert assignments_for_season(2026)["Leake"] == (5, 2)


def test_elo_carries_over_from_the_old_name_in_the_first_season_only():
    """Leake starts 2026 with Leake Central's rating; later seasons carry Leake's own, and the input isn't changed."""
    prior = {"Leake Central": 1210.0, "Leake County": 980.0, "Raleigh": 1150.0}
    carried = with_predecessor_ratings(prior, 2026)
    assert carried["Leake"] == 1210.0 and carried["Raleigh"] == 1150.0
    assert "Leake" not in with_predecessor_ratings(prior, 2025)  # before the change
    # From 2027 on, Leake has its own 2026 rating to carry.
    assert with_predecessor_ratings({"Leake": 1260.0, "Leake Central": 1210.0}, 2027)["Leake"] == 1260.0
    assert prior == {"Leake Central": 1210.0, "Leake County": 980.0, "Raleigh": 1150.0}  # not modified


def test_old_team_links_are_mapped_for_every_rename():
    """routes.js FORMER_SLUGS sends an old ?team= slug to the new name; it must cover every rename."""
    routes = (ROOT / "nginx" / "html" / "static" / "js" / "routes.js").read_text()
    slugs = dict(re.findall(r'"([a-z0-9-]+)": "([^"]+)"', re.search(r"FORMER_SLUGS = \{([^}]*)\}", routes).group(1)))
    assert slugs == {slugify(old): new for old, new, _ in [*SCHOOL_RENAMES, *SCHOOL_SUCCESSORS]}


def test_a_successor_starts_from_its_old_schools_rating_but_keeps_its_own_name_in_the_sources():
    """North Tippah (Falkner and Walnut, on Walnut's campus) starts 2027 from Walnut's rating; unlike a
    rename, AHSFHS is asked for North Tippah, and Walnut's name stays Walnut."""
    carried = with_predecessor_ratings({"Walnut": 1100.0, "Falkner": 950.0}, 2027)
    assert carried["North Tippah"] == 1100.0
    assert "North Tippah" not in with_predecessor_ratings({"Walnut": 1100.0}, 2026)
    assert source_name_for_season("North Tippah", 2027) == "North Tippah"
    assert school_name_for_season("Walnut", 2027) == "Walnut"
