"""Static page content (backend.helpers.static_pages) and the pipeline that writes it."""

import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from backend.helpers.static_pages import (
    CARD_H,
    ODDS_COLUMNS,
    PITCH,
    bracket_body,
    bracket_preview_html,
    bracket_trail,
    breadcrumb_ld,
    breadcrumb_nav,
    class_body,
    initials,
    insight_lines,
    json_ld,
    landing_body,
    layout_results,
    locked_seeds,
    pick_featured,
    region_body,
    region_trail,
    side_label,
    sitemap_xml,
    tree_centers,
    tree_columns,
)
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
        assert 'href="/standings/3a"' in body  # the class crumb; the bracket is a click away in the header nav

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
        assert '<tr class="is-eliminated">' in body
        assert '<span class="badge badge--eliminated"><svg' in body and "</svg>Eliminated</span>" in body


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


def _card(region, alive, volatility=0.5):
    """A /standings/summary region card."""
    return {"region": region, "teams_alive": alive, "volatility": volatility, "num_clinched": 1, "num_eliminated": 1}


SUMMARY = {
    "as_of_date": "2026-10-14",
    "classes": [
        {"class_": 3, "regions": [_card(1, 4, 0.9), _card(2, 5, 0.1)]},
        {"class_": 6, "regions": [_card(1, 5, 0.1), _card(2, 2, 0.99)]},
    ],
}
FEATURED = {
    "clazz": 3,
    "card": _card(6, 3),
    "standings": _region(headline="D'Iberville and Raleigh chase two spots <Friday>."),
    "stamp": "2026 season · " + STAMP,
    "mode": "projected",
    "bracket_html": "",
    "class_standings": {"regions": [{"region": 7, "teams": TEAMS}, {"region": 6, "teams": TEAMS}]},
}


def _side(feeders, occupants):
    """A matchups side: its feeder positions and who might fill it (team, p, locked)."""
    return {
        "feeders": [{"region": r, "seed": k} for r, k in feeders],
        "occupants": [{"team": t, "p_reach": p, "p_reach_weighted": p, "is_locked": lock} for t, p, lock in occupants],
    }


def _game(gid, rnd, a, b, matchups=()):
    """A /bracket/matchups game."""
    return {
        "id": gid,
        "round": rnd,
        "half": gid.split("-")[0],
        "side_a": a,
        "side_b": b,
        "matchups": [
            {"team_a": x, "team_b": y, "p_matchup": p, "p_matchup_weighted": p, "p_host_a": h, "p_host_a_weighted": h}
            for x, y, p, h in matchups
        ],
    }


BRACKET = [
    _game(
        "N-0-0",
        "First Round",
        _side([(1, 1)], [("Raleigh", 1.0, True)]),
        _side([(2, 4)], [("Mize", 0.6, False), ("Magee", 0.4, False)]),
        [("Raleigh", "Mize", 0.6, 1.0), ("Raleigh", "Magee", 0.4, 1.0)],
    ),
    _game(
        "N-0-1",
        "First Round",
        _side([(2, 2)], [("Seminary", 0.7, False)]),
        _side([(1, 3)], [("Taylorsville", 0.5, False)]),
    ),
    _game(
        "N-0-2",
        "First Round",
        _side([(3, 1)], [("Bay Springs", 0.8, False)]),
        _side([(4, 4)], [("Stringer", 0.3, False)]),
    ),
    _game(
        "N-0-3", "First Round", _side([(4, 2)], [("Lumberton", 0.6, False)]), _side([(3, 3)], [("Collins", 0.4, False)])
    ),
    _game(
        "N-1-0",
        "Second Round",
        _side(
            [(1, 1), (2, 4)],
            [("Raleigh", 0.7, False), ("Mize", 0.2, False), ("Magee", 0.1, False), ("Seminary", 0.05, False)],
        ),
        _side([(2, 2), (1, 3)], [("Seminary", 0.5, False), ("Taylorsville", 0.5, False)]),
        [("Raleigh", "Seminary", 0.35, 0.5), ("Raleigh", "Taylorsville", 0.35, 1.0), ("Mize", "Seminary", 0.1, 0.0)],
    ),
    _game(
        "N-1-1",
        "Second Round",
        _side([(3, 1), (4, 4)], [("Bay Springs", 0.6, False)]),
        _side([(4, 2), (3, 3)], [("Lumberton", 0.5, False)]),
    ),
    _game(
        "N-2-0",
        "Quarterfinals",
        _side([(1, 1), (2, 4), (2, 2), (1, 3)], [("Raleigh", 0.4, False)]),
        _side([(3, 1), (4, 4), (4, 2), (3, 3)], [("Bay Springs", 0.3, False)]),
    ),
    _game("final", "Championship Game", _side([], []), _side([], [])),
]
BRACKET_CTX = {"mode": "projected", "results": {}, "seeds": {"Raleigh": (1, 1)}, "teams": {}}


class TestBracketPreview:
    """The bracket page in miniature: the same cards and sheet the page draws."""

    def test_side_labels_match_bracket_js(self):
        """One or two positions by name; more by region; whole regions as 'Any Seed'."""
        assert side_label([{"region": 3, "seed": 1}]) == "Region 3 #1 Seed"
        assert (
            side_label([{"region": 1, "seed": 1}, {"region": 2, "seed": 4}]) == "Region 1 #1 Seed or Region 2 #4 Seed"
        )
        whole = [{"region": r, "seed": k} for r in (1, 2, 3) for k in (1, 2, 3, 4)]
        assert side_label(whole) == "Regions 1–3 (Any Seed)"
        mixed = [{"region": 1, "seed": 1}, {"region": 1, "seed": 3}, {"region": 2, "seed": 2}]
        assert side_label(mixed) == "Region 1 (#1 Seed, #3 Seed), Region 2 (#2 Seed)"

    def test_three_rounds_with_lines_and_one_open_game(self):
        """Seven cards in three columns, connector lines, the second-round game selected with its sheet open."""
        html = bracket_preview_html(3, BRACKET, BRACKET_CTX)
        assert html.count('class="bracket-preview__slot"') == 7
        assert [t for t in re.findall(r'class="tcol__title"[^>]*>([^<]+)<', html)] == [
            "First Round",
            "Second Round",
            "Quarterfinals",
        ]
        assert html.count("M") >= 6 and '<svg class="tree__lines"' in html
        assert html.count(" is-path") == 1 and "Second Round · North" in html

    def test_cards_read_like_the_tree(self):
        """Locked teams carry their seed and a lock; first-round slots their position; later ones '+N more'; the home side goes last."""
        html = bracket_preview_html(3, BRACKET, BRACKET_CTX)
        first = html.split('class="bracket-preview__slot"')[1]
        assert "Region 1 #1 Seed" in html and 'class="lock"' in html
        assert "Region 2 #4 Seed" in html and "+3 more" in html
        # Raleigh hosts its first-round game whoever comes, so it's the bottom row, with "at".
        assert first.index("Mize") < first.index("Raleigh")

    def test_sheet_lists_sides_and_matchups(self):
        """Top occupants per side with a 'Show all', then the likeliest matchups with who hosts."""
        html = bracket_preview_html(3, BRACKET, BRACKET_CTX)
        sheet = html[html.index('<div class="game-sheet bracket-preview__sheet">') :]
        assert "Show all 4" in sheet and "Most likely matchups" in sheet
        assert "50% chance Raleigh hosts" in sheet
        assert sheet.count('<li><span class="mu__teams">') == 2

    def test_results_show_scores(self):
        """A played game shows the score, winner first in weight, not odds."""
        layout = {
            "halves": {
                "N": [
                    [
                        {
                            "result": {
                                "winner": {"school": "Raleigh"},
                                "loser": {"school": "Mize"},
                                "winner_score": 35,
                                "loser_score": 7,
                            }
                        }
                    ]
                ]
            }
        }
        results = layout_results(layout)
        assert results == {"N-0-0": {"winner": "Raleigh", "loser": "Mize", "winner_score": 35, "loser_score": 7}}
        html = bracket_preview_html(3, BRACKET, {**BRACKET_CTX, "results": results})
        assert "tgame--played" in html and ">35<" in html and "trow--result is-winner" in html

    def test_too_small_a_bracket_draws_nothing(self):
        """Fewer than two rounds in a half: no preview (the landing just links)."""
        assert bracket_preview_html(3, BRACKET[:4], BRACKET_CTX) == ""

    def test_locked_seeds_from_class_standings(self):
        """A team certain of a seed gets that seed's label."""
        standings = {"regions": [{"region": 6, "teams": [_team("Raleigh", 1.0, 1.0), _team("Mize", 0.4, 0.2)]}]}
        assert locked_seeds(standings) == {"Raleigh": (6, 1)}


COLORS = {"Seminary": {"color_variants": {"primary": {"raw": "#123456"}, "secondary": [{"raw": "#ffcc00"}]}}}


def test_featured_race_is_the_most_open_one():
    """Most undecided, then most volatile, then the higher class; a settled season still gets an example."""
    assert pick_featured(SUMMARY) == {"clazz": 6, "card": _card(1, 5, 0.1)}
    closer = {"classes": [{"class_": 3, "regions": [_card(2, 5, 0.3)]}, *SUMMARY["classes"][1:]]}
    assert pick_featured(closer)["clazz"] == 3
    assert pick_featured({"classes": [{"class_": 1, "regions": [_card(1, 0)]}]})["clazz"] == 1
    assert pick_featured({"classes": []}) is None


class TestLandingBody:
    """The front page: who we are on the left, a tour of the site on the right."""

    def test_intro_and_every_tour_section(self):
        """Welcome, helmet, what we do and how it works; then class, region (with its three scenario kinds) and bracket."""
        body = landing_body(FEATURED, HELMETS)
        assert '<h1 class="landing-title">Mississippi High School Football</h1>' in body
        assert 'src="/static/helmet.webp"' in body
        for heading in (
            "What we do",
            "How it works",
            "Class standings",
            "Region breakdown",
            "Standings",
            "Region title scenarios",
            "Team seeding scenarios",
            "Unique region scenarios",
            "Bracket page",
        ):
            assert f">{heading}</h" in body, heading
        assert body.index("Class standings") < body.index("Region breakdown") < body.index("Bracket page")
        assert 'href="/methodology"' in body

    def test_class_preview_is_the_class_page_in_miniature(self):
        """One link to the class page, with the featured region and the next one inside, as the class page draws them."""
        body = landing_body(FEATURED, {**HELMETS, **COLORS})
        card = body[body.index('<a class="landing-preview landing-preview--class"') :]
        card = card[: card.index("</a>") + 4]
        assert 'href="/standings/3a" aria-label="Open the Class 3A page"' in card
        assert card.count("<a ") == 1 and 'aria-hidden="true"' in card
        assert (
            '<p class="region-block__title">Region 6</p>' in card
            and '<p class="region-block__title">Region 7</p>' in card
        )
        assert "raleigh.png" in card and 'fill="#123456"' in card
        assert '<p class="title">Class 3A</p>' in card

    def test_each_card_is_introduced(self):
        """A sentence before each example says what it is; 'most unsettled' only while the race is open."""
        body = landing_body({**FEATURED, "bracket_html": "<div>tree</div>"}, {})
        assert "Here’s Class 3A as it stands right now, starting with Region 6:" in body
        assert "Here’s Region 6-3A, the most unsettled race in the state right now:" in body
        assert "And here’s the Class 3A bracket, with one game opened up the way it looks after you tap it:" in body
        settled = landing_body({**FEATURED, "card": _card(6, 0)}, {})
        assert "Here’s Region 6-3A:" in settled and "most unsettled" not in settled
        assert "Class 3A bracket, with one game" not in settled  # no bracket preview, so no sentence for it

    def test_region_preview_is_one_link_with_no_links_inside(self):
        """The region page in miniature: a single link to it, hidden from screen readers inside."""
        body = landing_body(FEATURED, HELMETS)
        start = body.index('<a class="landing-preview" ')
        preview = body[start : body.index("</a>", body.index("landing-preview__label", start))]
        assert 'href="/standings/3a/6" aria-label="Open the Region 6-3A page"' in preview
        assert preview.count("<a ") == 1 and 'aria-hidden="true"' in preview
        assert "D&#39;Iberville and Raleigh chase two spots &lt;Friday&gt;." in preview
        assert ">1st</span>" in preview and ">Overall</th>" in preview

    def test_bracket_preview_is_the_bracket_page_in_miniature(self):
        """One link to the bracket, with the tree and an open sheet inside; just a link without data."""
        body = landing_body({**FEATURED, "bracket_html": bracket_preview_html(3, BRACKET, BRACKET_CTX)}, {})
        preview = body[body.index('<a class="landing-preview landing-preview--bracket"') :]
        preview = preview[: preview.index("</a>") + 4]
        assert 'href="/brackets/3a" aria-label="Open the Class 3A bracket"' in preview
        assert preview.count("<a ") == 1 and "Who might play here" in preview
        assert "See the 3A bracket" in landing_body({**FEATURED, "bracket_html": ""}, {})

    def test_no_data_still_renders(self):
        """Before any standings exist: the intro and tour, without examples."""
        body = landing_body(None, {})
        assert "Class standings" in body and "landing-example" not in body and "landing-preview" not in body


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
        "/standings/summary?season=2026": {
            "as_of_date": "2026-10-09",
            "classes": [{"class_": 3, "regions": [_card(6, 3)]}],
        },
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
    site = (tmp_path / "body" / "site.html").read_text()
    assert "Open the Region 6-3A page" in site and "2026 season · Through Week 8" in site  # the region's own payload
    sitemap = (tmp_path / "sitemap.xml").read_text()
    for path in ("/</loc>", "/standings/3a</loc>", "/standings/3a/6</loc>", "/methodology</loc>"):
        assert path in sitemap
    assert "<lastmod>2026-10-09</lastmod>" in sitemap
    assert "/brackets/3a" not in sitemap  # no bracket odds yet, so no bracket page to list
    assert not (tmp_path / "body" / "bracket-3.html").exists()
    head = (tmp_path / "meta" / "site.html").read_text()
    assert '<link rel="canonical" href="https://mshsfootball.com/">' in head and '"@type":"WebSite"' in head
    class_head = (tmp_path / "meta" / "3.html").read_text()
    assert '"@type":"BreadcrumbList"' in class_head and "https://mshsfootball.com/standings/3a" in class_head


def test_odds_headers_match_the_app():
    """The pre-rendered pages' odds headers and their full names are the app's, so the page doesn't change on load."""
    app_js = (Path(__file__).resolve().parents[3] / "nginx" / "html" / "static" / "js" / "app.js").read_text()
    for key, label, full in ODDS_COLUMNS:
        assert f'{{ key: "{key}", label: "{label}",' in app_js
        assert f'full: "{full}"' in app_js


# ------------------------------------------------------------ breadcrumbs and structured data


def test_breadcrumbs_link_every_level_but_this_one():
    """Home › Class 3A › Region 6-3A, the last unlinked and marked current; the same markup as components.js."""
    nav = breadcrumb_nav(region_trail(3, 6))
    assert nav == (
        '<nav class="crumbs" aria-label="Breadcrumb"><ol><li><a href="/">Home</a></li>'
        '<li><a href="/standings/3a">Class 3A</a></li><li aria-current="page">Region 6-3A</li></ol></nav>'
    )
    components = (
        Path(__file__).resolve().parents[3] / "nginx" / "html" / "static" / "js" / "components.js"
    ).read_text()
    for fragment in ('<li aria-current="page">', '<nav class="crumbs" aria-label="Breadcrumb"><ol>'):
        assert fragment in components


def test_breadcrumb_structured_data_uses_full_addresses():
    """BreadcrumbList items count from 1 and name absolute URLs."""
    data = breadcrumb_ld("https://mshsfootball.com", bracket_trail(3))
    assert [(i["position"], i["name"], i["item"]) for i in data["itemListElement"]] == [
        (1, "Home", "https://mshsfootball.com/"),
        (2, "Class 3A", "https://mshsfootball.com/standings/3a"),
        (3, "3A Bracket", "https://mshsfootball.com/brackets/3a"),
    ]


def test_structured_data_cannot_close_its_script_element():
    """A value containing </script> can't end the block early."""
    block = json_ld({"name": "</script><script>alert(1)</script>"})
    assert block.count("</script>") == 1 and "\\u003c/script>" in block


def test_region_and_class_pages_carry_breadcrumbs():
    """The static pages start with the same breadcrumbs as the app's."""
    assert breadcrumb_nav(region_trail(3, 6)) in region_body(3, 6, _region(), "stamp", "projected", {})


# ------------------------------------------------------------ the bracket page


def _games(ids: list[str]) -> list[dict]:
    """Bare games with the given ids (round named from the id's round number)."""
    names = {"0": "First Round", "1": "Quarterfinals", "2": "Semifinals"}
    return [{"id": i, "round": "Championship Game" if i == "final" else names[i.split("-")[1]]} for i in ids]


def test_tree_columns_match_bracket_js():
    """Both halves stacked per round, then the final fed by every semifinal (bracket.test.mjs's case)."""
    ids = [f"{h}-0-{i}" for h in "NS" for i in range(4)] + [f"{h}-1-{i}" for h in "NS" for i in range(2)]
    cols = tree_columns(_games([*ids, "N-2-0", "S-2-0", "final"]))
    assert [c["name"] for c in cols] == ["First Round", "Quarterfinals", "Semifinals", "Championship Game"]
    assert [(g["game"]["id"], g["feeders"]) for g in cols[1]["games"]] == [
        ("N-1-0", [0, 1]),
        ("N-1-1", [2, 3]),
        ("S-1-0", [4, 5]),
        ("S-1-1", [6, 7]),
    ]
    assert [g["feeders"] for g in cols[2]["games"]] == [[0, 1], [2, 3]]
    assert cols[3]["games"][0]["feeders"] == [0, 1]


def test_tree_centers_match_bracket_js_at_focus_zero():
    """The first column stacks; each later game sits between its feeders (bracket.js treeLayout(cols, 0))."""
    cols = tree_columns(_games(["N-0-0", "N-0-1", "N-0-2", "N-0-3", "N-1-0", "N-1-1", "N-2-0"]))
    centers, height = tree_centers(cols)
    first = [CARD_H / 2 + PITCH * i for i in range(4)]
    assert centers[0] == first
    assert centers[1] == [(first[0] + first[1]) / 2, (first[2] + first[3]) / 2]
    assert centers[2] == [(centers[1][0] + centers[1][1]) / 2]
    assert height == first[-1] + CARD_H / 2


def test_bracket_page_has_every_game_positioned_with_breadcrumbs():
    """Title, breadcrumbs, the snapshot line, and every game in its slot, readable without JavaScript."""
    html = bracket_body(3, BRACKET, BRACKET_CTX, "2026 season · Through Week 8")
    assert breadcrumb_nav(bracket_trail(3)) in html and '<h1 class="title">Class 3A Bracket</h1>' in html
    assert html.count('class="tslot"') == len(BRACKET)
    assert "translateY(0px)" in html and f"translateY({PITCH:g}px)" in html
    assert "Raleigh" in html and "Bay Springs" in html and "Championship Game" in html
    assert '<span class="visually-hidden">First Round, One spot set: </span>' in html
    assert bracket_body(3, [], BRACKET_CTX, "x") == ""


def test_front_page_has_every_classs_standings_and_bracket_under_the_helmet():
    """Two rows of seven buttons, each saying what it opens; the same markup as landing.js's classGrid."""
    from backend.helpers.static_pages import class_grid

    grid = class_grid()
    assert grid.count('class="landing-classes__item"') == 14
    assert (
        '<a class="landing-classes__item" href="/standings/3a">3A<span class="visually-hidden"> standings</span></a>'
        in grid
    )
    assert (
        '<a class="landing-classes__item" href="/brackets/7a">7A<span class="visually-hidden"> brackets</span></a>'
        in grid
    )
    body = landing_body(None, {})
    assert body.index("landing-helmet") < body.index("landing-classes") < body.index("What we do")
    js = (Path(__file__).resolve().parents[3] / "nginx" / "html" / "static" / "js" / "landing.js").read_text()
    assert 'class="landing-classes__item" href="${path(c)}">${c}A<span class="visually-hidden">' in js
