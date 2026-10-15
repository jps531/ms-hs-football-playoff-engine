"""Static page content (backend.helpers.static_pages) and the pipeline that writes it."""

import re
import xml.etree.ElementTree as ET
from datetime import date

from backend.helpers.static_pages import class_body, initials, insight_lines, region_body, site_body, sitemap_xml
from backend.prefect.share_assets_pipeline import build_share_assets
from backend.tests.unit.share_cards_test import DATES, TEAMS, _team

STAMP = "Through Week 8 · Oct 9 · Projected"
HELMETS = {"Raleigh": {"helmet_url": "https://res.cloudinary.com/x/raleigh.png"}}


def _region(**extra):
    """A Region 6-3A payload as the API returns it."""
    return {
        "as_of_date": "2026-10-09",
        "headline": "Raleigh clinches the region with a win over Seminary <Friday>.",
        "teams": TEAMS,
        "remaining_games": [
            {"team_a": "Raleigh", "team_b": "Seminary", "location_a": "home"},
            {"team_a": "Magee", "team_b": "Mize", "location_a": "away"},
            {"team_a": "Mize", "team_b": "Raleigh", "location_a": None},
        ],
        "key_insights": [
            {
                "insight_type": "eliminated_if",
                "team": "Mize",
                "rendered": "Mize is eliminated from the playoffs: Magee beats Mize",
            },
            {
                "insight_type": "clinch_seed",
                "team": "Raleigh",
                "seed": 1,
                "rendered": "Raleigh clinches 1st seed: Raleigh beats Seminary",
            },
            {
                "insight_type": "clinch_seed",
                "team": "Raleigh",
                "seed": 1,
                "rendered": "Raleigh clinches 1st seed: Raleigh beats Seminary",
            },
            {"insight_type": "already_clinched", "team": "Raleigh", "rendered": "Raleigh has clinched a playoff spot"},
        ],
        **extra,
    }


def _text(fragment: str) -> str:
    """The fragment's visible text, tags stripped and whitespace collapsed."""
    return " ".join(re.sub(r"<[^>]+>", " ", fragment).split())


class TestRegionBody:
    """What a region page reads like before the app loads, or without JavaScript."""

    def test_title_headline_snapshot_and_links(self):
        """The h1, the escaped headline and the snapshot line, with links to the class and its bracket."""
        body = region_body(3, 6, _region(), STAMP, "projected", HELMETS)
        assert '<h1 class="title">Region 6-3A</h1>' in body
        assert "Seminary &lt;Friday&gt;." in body
        assert f'<p class="provenance provenance--static">{STAMP}</p>' in body
        assert 'href="/standings/3a"' in body and 'href="/brackets/3a"' in body

    def test_standings_table_in_display_order_with_projected_odds(self):
        """Rows follow the app's order; odds are the mode's, as text; each team links to its view."""
        body = region_body(3, 6, _region(), STAMP, "projected", HELMETS)
        names = re.findall(r'<span class="team-name">([^<]+)</span>', body)
        assert names == ["Raleigh", "Seminary", "Magee", "Mize"]
        row = body[body.index("Raleigh</span>") : body.index("</tr>", body.index("Raleigh</span>"))]
        assert "3–1" in row and "6–2" in row and ">80%<" in row and ">100%<" in row
        assert 'href="/standings/3a/6?team=raleigh"' in body
        assert '<img class="mark mark--helmet" src="https://res.cloudinary.com/x/raleigh.png"' in body
        assert '<span class="mark mark--initials" aria-hidden="true">S</span>' in body
        assert "projected odds of finishing in each playoff position" in body

    def test_tossup_mode_uses_the_unweighted_odds(self):
        """Toss-up pages show the 50/50 numbers and say so."""
        teams = [_team("Raleigh", 1.0, 0.8, weighted=False)]
        body = region_body(3, 6, _region(teams=teams), STAMP, "tossup", {})
        assert ">80%<" in body and "toss-up odds" in body

    def test_remaining_games_put_the_away_team_first(self):
        """Without a schedule: 'A at B' when the standings know the site, 'A vs B' when not."""
        text = _text(region_body(3, 6, _region(), STAMP, "projected", {}))
        assert "Remaining games Seminary at Raleigh Magee at Mize Mize vs Raleigh" in text

    def test_remaining_games_take_dates_and_sites_from_the_schedule(self):
        """As the region view does: the schedule's date and home/away win; dated games first, oldest first."""
        games = [
            {
                "team_a": "Raleigh",
                "team_b": "Mize",
                "location_a": "away",
                "date": "2026-10-16",
                "is_region_game": True,
                "final": False,
            },
            {
                "team_a": "Seminary",
                "team_b": "Raleigh",
                "location_a": None,
                "date": "2026-10-23",
                "is_region_game": True,
                "final": False,
            },
            {
                "team_a": "Magee",
                "team_b": "Raleigh",
                "location_a": "home",
                "date": "2026-10-02",
                "is_region_game": True,
                "final": True,
                "score_a": 7,
                "score_b": 21,
            },
        ]
        text = _text(region_body(3, 6, _region(), STAMP, "projected", {}, games))
        assert ("Remaining games Fri, Oct 16: Raleigh at Mize Fri, Oct 23: Seminary at Raleigh Magee at Mize") in text

    def test_conditions_are_grouped_like_the_scenario_cards(self):
        """One line per outcome, worded as the cards are, ways joined by 'or'; clinches before eliminations."""
        insights = [
            *_region()["key_insights"],
            {
                "insight_type": "clinch_seed",
                "team": "Raleigh",
                "seed": 1,
                "rendered": "Raleigh clinches 1st seed: Seminary beats Magee; Mize beats Magee",
            },
            {
                "insight_type": "clinch_playoffs",
                "team": "Magee",
                "rendered": "Magee clinches a playoff spot: Magee beats Mize",
            },
        ]
        assert insight_lines(insights) == [
            "Raleigh clinches the region if Raleigh beats Seminary or if Seminary beats Magee and Mize beats Magee",
            "Magee clinches a playoff spot if Magee beats Mize",
            "Mize is eliminated if Magee beats Mize",
        ]
        assert "What has to happen" in region_body(3, 6, _region(), STAMP, "projected", {})

    def test_a_settled_region_has_no_empty_sections(self):
        """No remaining games or conditions: those sections are left out, not left empty."""
        body = region_body(3, 6, _region(remaining_games=[], key_insights=None, headline=None), STAMP, "projected", {})
        assert "Remaining games" not in body and "What has to happen" not in body
        assert 'class="headline"' not in body

    def test_status_badges_and_dimmed_eliminated_rows(self):
        """Clinched and eliminated teams carry the app's badges; eliminated rows are dimmed."""
        out = {**_team("Mize", 0.0), "eliminated": True}
        clinched = {**TEAMS[0], "clinched": True}
        body = region_body(3, 6, _region(teams=[clinched, out]), STAMP, "projected", {})
        assert '<span class="badge badge--clinched">' in body
        assert (
            '<tr class="is-eliminated">' in body and '<span class="badge badge--eliminated">Eliminated</span>' in body
        )


def test_initials_match_the_app():
    """Same rule as format.js: skip County/High/School/Academy, two letters at most."""
    assert initials("Jefferson Davis County") == "JD"
    assert initials("Oak Grove High School") == "OG"
    assert initials("St. Andrew's Academy") == "SA"
    assert initials("Academy") == "A"


def test_class_body_lists_every_region_in_order():
    """Region blocks in number order, each linking to its region page."""
    body = class_body(
        3, {"regions": [{"region": 7, "teams": TEAMS}, {"region": 6, "teams": TEAMS}]}, STAMP, "projected", {}
    )
    assert '<h1 class="title">Class 3A</h1>' in body
    assert body.index('id="region-6"') < body.index('id="region-7"')
    assert '<a href="/standings/3a/6">Region 6</a>' in body
    assert 'href="/standings/3a/7?team=raleigh"' in body


def test_site_body_links_every_class_region_and_bracket():
    """The front page lists each class's regions, and its bracket only when there is one."""
    body = site_body({3: [7, 6], 1: [1]}, [3])
    assert body.index("Class 1A") < body.index("Class 3A")
    assert '<a href="/standings/3a/6">Region 6-3A</a>' in body
    assert '<a href="/brackets/3a">3A Bracket</a>' in body and "/brackets/1a" not in body


def test_sitemap_is_valid_xml_with_lastmod():
    """A well-formed sitemap; pages with a snapshot date carry it."""
    xml = sitemap_xml("https://mshsfootball.com/", [("/", date(2026, 10, 14)), ("/methodology", None)])
    root = ET.fromstring(xml)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    assert [u.findtext("s:loc", namespaces=ns) for u in root] == [
        "https://mshsfootball.com/",
        "https://mshsfootball.com/methodology",
    ]
    assert root[0].findtext("s:lastmod", namespaces=ns) == "2026-10-14"
    assert root[1].find("s:lastmod", ns) is None


def test_pipeline_writes_page_content_front_page_and_sitemap(tmp_path):
    """Each region and class gets its static content from the same reads as its card; plus site.html and the sitemap."""
    api = {
        "/seasons": [{"season": 2026}],
        "/teams?season=2026": [{"school": "Raleigh", "helmet_url": "https://res.cloudinary.com/x/raleigh.png"}],
        "/standings/3?season=2026": {"as_of_date": "2026-10-09", "regions": [{"region": 6, "teams": TEAMS}]},
        "/seasons/2026/dates?class=3": {"dates": DATES},
        "/standings/3/6?season=2026": _region(),
        "/games?season=2026&class=3&region=6": [
            {
                "team_a": "Raleigh",
                "team_b": "Mize",
                "location_a": "away",
                "date": "2026-10-16",
                "is_region_game": True,
                "final": False,
            }
        ],
    }
    build_share_assets(api.get, tmp_path, "https://mshsfootball.com", date(2026, 10, 14))
    region = (tmp_path / "body" / "3-6.html").read_text()
    assert "Region 6-3A" in region and "2026 season · Through Week 8 · Oct 9 · Projected" in region
    assert "Fri, Oct 16: Raleigh at Mize" in region  # from the schedule
    assert "raleigh.png" in region
    assert "Class 3A" in (tmp_path / "body" / "3.html").read_text()
    assert "/standings/3a/6" in (tmp_path / "body" / "site.html").read_text()
    sitemap = (tmp_path / "sitemap.xml").read_text()
    for path in ("/</loc>", "/standings/3a</loc>", "/standings/3a/6</loc>", "/methodology</loc>"):
        assert path in sitemap
    assert "<lastmod>2026-10-09</lastmod>" in sitemap
    assert "/brackets/3a" not in sitemap  # no bracket odds yet, so no bracket page to list
