"""A school that goes by a new name while the sources still use the old one (SCHOOL_RENAMES in data_helpers):
Leake Central is "Leake" from 2026 on, everywhere the pipelines file data, and keeps its old name before then."""

import logging
import re
from pathlib import Path

import pytest

import backend.prefect.ahsfhs_schedule_pipeline as schedule
from backend.helpers.data_helpers import (
    SCHOOL_CONSOLIDATIONS,
    SCHOOL_NAME_CHANGES,
    SCHOOL_RENAMES,
    SCHOOL_STOPPED_PLAYING,
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
    from backend.helpers.data_helpers import name_in

    slugs = dict(re.findall(r'"([a-z0-9-]+)": "([^"]+)"', re.search(r"FORMER_SLUGS = \{([^}]*)\}", routes).group(1)))
    # Each old name to the name it has now (McEvans to Shaw), and none for a name taken back (Shaw).
    now = {old: name_in(old, first - 1, 9999) for old, _, first in [*SCHOOL_RENAMES, *SCHOOL_NAME_CHANGES]}
    now |= {old: new for old, new, _ in SCHOOL_SUCCESSORS}
    assert slugs == {slugify(old): new for old, new in now.items() if new != old}


def test_every_consolidation_matches_the_renames_successors_and_closures():
    """A consolidation's first school is the new one's rename or predecessor; every other one stopped
    playing the season before, its note naming the new school; and every closure into another school is a
    consolidation listed here."""
    carried = {(old, new, first) for old, new, first in [*SCHOOL_RENAMES, *SCHOOL_SUCCESSORS]}
    stopped = {school: (last, why) for school, last, why in SCHOOL_STOPPED_PLAYING}
    for new, first, merged in SCHOOL_CONSOLIDATIONS:
        assert (merged[0], new, first) in carried, new
        for school in merged[1:]:
            last, why = stopped[school]
            assert last == first - 1 and f"Consolidated into {new}" in why, school
    merged_away = {school for _, _, merged in SCHOOL_CONSOLIDATIONS for school in merged[1:]}
    assert {s for s, (_, why) in stopped.items() if why.startswith("Consolidated into")} == merged_away


def test_the_maps_timeline_knows_every_consolidation():
    """regions.js SCHOOL_CONSOLIDATIONS lets the timeline follow a school back through the ones merged
    into it; it must be data_helpers' list."""
    regions = (ROOT / "nginx" / "html" / "static" / "js" / "regions.js").read_text()
    block = re.search(r"SCHOOL_CONSOLIDATIONS = \[(.*?)\];\n", regions, re.S).group(1)
    found = [
        (new, int(first), re.findall(r'"([^"]+)"', members))
        for new, first, members in re.findall(r'\["([^"]+)", (\d{4}), \[([^\]]*)\]\]', block)
    ]
    assert found == [(new, first, list(merged)) for new, first, merged in SCHOOL_CONSOLIDATIONS]


def test_the_maps_compare_knows_every_rename():
    """regions.js SCHOOL_RENAMES finds a renamed school across seasons on the Compare view; it must be
    data_helpers' list."""
    regions = (ROOT / "nginx" / "html" / "static" / "js" / "regions.js").read_text()
    block = re.search(r"SCHOOL_RENAMES = \[(.*?)\];", regions, re.S).group(1)
    found = [(old, new, int(first)) for old, new, first in re.findall(r'\["([^"]+)", "([^"]+)", (\d{4})\]', block)]
    assert found == [tuple(r) for r in SCHOOL_RENAMES]
    block = re.search(r"SCHOOL_NAME_CHANGES = \[(.*?)\];", regions, re.S).group(1)
    found = [(old, new, int(first)) for old, new, first in re.findall(r'\["([^"]+)", "([^"]+)", (\d{4})\]', block)]
    assert found == [tuple(r) for r in SCHOOL_NAME_CHANGES]


def test_a_successor_starts_from_its_old_schools_rating_but_keeps_its_own_name_in_the_sources():
    """North Tippah (Falkner and Walnut, on Walnut's campus) starts 2027 from Walnut's rating; unlike a
    rename, AHSFHS is asked for North Tippah, and Walnut's name stays Walnut."""
    carried = with_predecessor_ratings({"Walnut": 1100.0, "Falkner": 950.0}, 2027)
    assert carried["North Tippah"] == 1100.0
    assert "North Tippah" not in with_predecessor_ratings({"Walnut": 1100.0}, 2026)
    assert source_name_for_season("North Tippah", 2027) == "North Tippah"
    assert school_name_for_season("Walnut", 2027) == "Walnut"


def test_a_schools_names_in_another_season():
    """names_in follows a school across a rename and a consolidation, either way (regions.js namesIn)."""
    from backend.helpers.data_helpers import name_in, names_in

    assert name_in("Leake Central", 2025, 2026) == "Leake"
    assert name_in("Leake", 2026, 2025) == "Leake Central"
    assert name_in("Leake", 2027, 2026) == "Leake"
    assert names_in("Leake", 2026, 2025) == ["Leake Central", "Leake County"]
    assert names_in("North Tippah", 2027, 2026) == ["Walnut", "Falkner"]
    assert names_in("Falkner", 2026, 2027) == ["North Tippah"]
    assert names_in("Walnut", 2026, 2028) == ["North Tippah"]
    assert names_in("Walnut", 2026, 2025) == ["Walnut"]
    assert names_in("Greenwood", 2027, 1990) == ["Greenwood"]


def test_a_school_renamed_more_than_once_and_the_sources_kept_up():
    """Shaw was McEvans 2020-22 and Shaw again from 2023; Ruleville Central is Thomas E. Edwards from
    2019. The sources use the new names, so they're never asked for the old ones."""
    from backend.helpers.data_helpers import name_in

    assert [school_name_for_season("Shaw", s) for s in (2019, 2020, 2022, 2023, 2026)] == [
        "Shaw", "McEvans", "McEvans", "Shaw", "Shaw"
    ]  # fmt: skip
    assert school_name_for_season("McEvans", 2024) == "Shaw"
    assert school_name_for_season("Ruleville Central", 2019) == "Thomas E. Edwards"
    assert source_name_for_season("Thomas E. Edwards", 2026) == "Thomas E. Edwards"
    assert source_name_for_season("Shaw", 2026) == "Shaw"
    assert name_in("Shaw", 2017, 2021) == "McEvans" and name_in("Shaw", 2017, 2024) == "Shaw"
    assert name_in("Shaw", 2024, 2021) == "McEvans" and name_in("Shaw", 2024, 2017) == "Shaw"
    assert name_in("McEvans", 2021, 2017) == "Shaw"
    assert name_in("Thomas E. Edwards", 2025, 2016) == "Ruleville Central"
    assert with_predecessor_ratings({"Shaw": 1000.0}, 2020)["McEvans"] == 1000.0
    assert with_predecessor_ratings({"McEvans": 990.0}, 2023)["Shaw"] == 990.0
