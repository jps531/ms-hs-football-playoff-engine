"""Share cards: text helpers match the site, cards render, and the pipeline writes every file."""

from datetime import date

from PIL import Image, ImageDraw

from backend.helpers.share_cards import (
    HEIGHT,
    WIDTH,
    _inter,
    description,
    display_order,
    format_pct,
    meta_tags,
    odds_bucket,
    odds_mode,
    provenance,
    render_class_card,
    render_region_card,
    render_site_card,
    standing_positions,
    wrap,
)
from backend.prefect.share_assets_pipeline import build_share_assets


def _team(name, p_playoffs, p1=0.0, weighted=True, region_wins=3, region_losses=1):
    w = (lambda v: v) if weighted else (lambda v: 0.0)
    return {
        "school": name,
        "record": {
            "wins": 6,
            "losses": 2,
            "ties": 0,
            "region_wins": region_wins,
            "region_losses": region_losses,
            "region_ties": 0,
        },
        "odds": {
            "p1": p1,
            "p2": 0.0,
            "p3": 0.0,
            "p4": 0.0,
            "p_playoffs": p_playoffs,
            "p1_weighted": w(p1),
            "p2_weighted": 0.0,
            "p3_weighted": 0.0,
            "p4_weighted": 0.0,
            "p_playoffs_weighted": w(p_playoffs),
        },
    }


TEAMS = [_team("Raleigh", 1.0, 0.8), _team("Seminary", 0.94, 0.15), _team("Magee", 0.42), _team("Mize", 0.004)]
DATES = [
    {"date": "2026-10-01", "kind": "games", "week": 7, "description": "Week 7"},
    {"date": "2026-10-03", "kind": "games", "week": 7, "description": "Week 7"},
    {"date": "2026-10-09", "kind": "games", "week": 8, "description": "Week 8"},
    {"date": "2026-10-16", "kind": "games", "week": 9, "description": "Week 9"},
]


def test_percent_and_ramp_match_the_site():
    """Same text and color buckets as format.js: rounding half up, <1% / >99% edges, 79% stays out of the 80s."""
    assert [format_pct(p) for p in (0, 0.004, 0.005, 0.125, 0.995, 0.999, 1)] == [
        "0%",
        "<1%",
        "1%",
        "13%",
        ">99%",
        ">99%",
        "100%",
    ]
    assert [odds_bucket(p) for p in (0, 0.004, 0.2, 0.79, 0.8, 1)] == [1, 1, 2, 4, 5, 5]


def test_provenance_says_what_the_page_says():
    """Newest week the snapshot reaches; "Latest update" when it predates that week's last games."""
    assert provenance(date(2026, 10, 9), DATES, "projected", date(2026, 10, 14)) == "Through Week 8 · Oct 9 · Projected"
    assert (
        provenance(date(2026, 10, 2), DATES, "tossup", date(2026, 10, 14))
        == "Through Week 7 · Latest update Oct 2 · Toss-up"
    )
    # Games on or after today don't count yet.
    assert (
        provenance(date(2026, 10, 16), DATES, "projected", date(2026, 10, 16)) == "Through Week 8 · Oct 9 · Projected"
    )
    assert provenance(date(2026, 8, 20), [], "tossup", date(2026, 8, 21)) == "Updated Aug 20 · Toss-up"


def test_odds_mode_is_projected_only_when_weighted_odds_exist():
    assert odds_mode(TEAMS) == "projected"
    assert odds_mode([_team("A", 0.5, weighted=False)]) == "tossup"


def test_description_keeps_the_headline_and_cuts_long_ones_at_a_word():
    short = "Raleigh clinches the region with a win over Seminary."
    assert description(short) == short
    long = "Raleigh clinches the region with a win over Seminary, " * 5
    cut = description(long)
    assert len(cut) <= 155 and cut.endswith("…") and not cut.endswith(" …")
    assert long.startswith(cut[:-1])


def test_meta_tags_escape_and_carry_every_preview_tag():
    tags = meta_tags(
        'Region 6-3A "race" & more', "D'Iberville <wins>", "https://x/og.png?v=1&a=2", "https://x/standings/3a/6"
    )
    assert "<title>Region 6-3A &quot;race&quot; &amp; more</title>" in tags
    assert 'content="D&#x27;Iberville &lt;wins&gt;"' in tags
    for tag in (
        'property="og:title"',
        'property="og:description"',
        'property="og:image"',
        'name="twitter:card"',
        'rel="canonical"',
    ):
        assert tag in tags
    assert "og.png?v=1&amp;a=2" in tags


def test_headline_wraps_to_at_most_three_lines():
    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font = _inter(34, 600)
    lines = wrap(draw, "word " * 200, font, 1072, 3)
    assert len(lines) == 3 and lines[-1].endswith("…")
    assert all(draw.textlength(line, font=font) <= 1072 for line in lines)
    assert wrap(draw, "Short and sweet.", font, 1072, 3) == ["Short and sweet."]


def test_cards_render_at_link_preview_size():
    region = render_region_card(
        3, 6, {"headline": "Raleigh has it won.", "teams": TEAMS}, "Through Week 8 · Oct 9 · Projected", "projected"
    )
    eight = {"regions": [{"region": r, "teams": TEAMS} for r in range(1, 9)]}
    four = {"regions": [{"region": r, "teams": TEAMS} for r in range(1, 5)]}
    for img in (
        region,
        render_class_card(3, eight, "x", "projected"),
        render_class_card(7, four, "x", "tossup"),
        render_site_card(),
    ):
        assert img.size == (WIDTH, HEIGHT)
    # No headline, no teams: still a card, not a crash.
    assert render_region_card(3, 6, {"headline": None, "teams": []}, "x", "tossup").size == (WIDTH, HEIGHT)


def test_pipeline_writes_a_card_and_meta_file_for_every_region_and_class(tmp_path):
    """Built from the API's own responses; regions and classes without data are skipped."""
    api = {
        "/seasons": [{"season": 2026}, {"season": 2025}],
        "/standings/3?season=2026": {
            "as_of_date": "2026-10-09",
            "regions": [{"region": 6, "teams": TEAMS}, {"region": 7, "teams": TEAMS}],
        },
        "/seasons/2026/dates?class=3": {"dates": DATES},
        "/standings/3/6?season=2026": {
            "as_of_date": "2026-10-09",
            "headline": "Raleigh has the region won.",
            "teams": TEAMS,
        },
        "/standings/3/7?season=2026": {"as_of_date": "2026-10-09", "headline": None, "teams": TEAMS},
    }
    written = build_share_assets(api.get, tmp_path, "https://mshsfootball.com/", date(2026, 10, 14))
    assert written == {"regions": 2, "classes": 1}
    for name in ("site.png", "3.png", "3-6.png", "3-7.png"):
        assert Image.open(tmp_path / "og" / name).size == (WIDTH, HEIGHT)
    meta = (tmp_path / "meta" / "3-6.html").read_text()
    assert "<title>Region 6-3A playoff race — Mississippi High School Football</title>" in meta
    assert 'content="Raleigh has the region won."' in meta
    assert "https://mshsfootball.com/static/og/3-6.png?v=20261009" in meta
    assert 'href="https://mshsfootball.com/standings/3a/6"' in meta
    # A region without a headline still gets a specific description, not the site's.
    assert "Region 7-3A standings" in (tmp_path / "meta" / "3-7.html").read_text()
    assert "/standings/3a" in (tmp_path / "meta" / "3.html").read_text()
    assert not list(tmp_path.rglob(".*"))  # no temp files left behind


def test_card_order_and_tied_positions_match_the_standings_table():
    """Region record first, then odds; ties share a position (Region 6-3A on Oct 9, 2026)."""
    api_order = [
        _team("Magee", 1.0, 0.33, region_wins=2, region_losses=0),
        _team("Seminary", 0.997, 0.28, region_wins=1, region_losses=0),
        _team("Raleigh", 0.998, 0.39, region_wins=1, region_losses=0),
        _team("McLaurin", 0.39, 0.0, region_wins=0, region_losses=2),
        _team("Jefferson Davis County", 0.61, 0.0, region_wins=0, region_losses=2),
    ]
    ordered = display_order(api_order)
    assert [t["school"] for t in ordered] == ["Magee", "Raleigh", "Seminary", "Jefferson Davis County", "McLaurin"]
    assert standing_positions(ordered) == [1, 1, 1, 4, 4]
    # A team that hasn't played sits with the .500 teams.
    fresh = [_team("A", 0.5, region_wins=1, region_losses=1), _team("B", 0.5, region_wins=0, region_losses=0)]
    assert standing_positions(display_order(fresh)) == [1, 1]
