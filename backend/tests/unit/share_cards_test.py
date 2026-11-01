"""Share cards: text helpers match the site, cards render, and the pipeline writes every file."""

from datetime import date

from PIL import Image, ImageDraw

from backend.helpers.share_cards import (
    HEIGHT,
    WIDTH,
    _inter,
    bracket_description,
    bracket_favorites,
    description,
    display_order,
    format_pct,
    meta_tags,
    odds_bucket,
    odds_mode,
    position_labels,
    provenance,
    render_bracket_card,
    render_class_card,
    render_region_card,
    render_site_card,
    render_team_bracket_card,
    render_team_card,
    slugify,
    standing_positions,
    team_bracket_description,
    team_description,
    team_road,
    team_status,
    wrap,
)
from backend.prefect.share_assets_pipeline import build_share_assets


def _team(name, p_playoffs, p1=0.0, weighted=True, region_wins=3, region_losses=1):
    """A team's standings entry with these odds (its Projected twins zero when not *weighted*)."""
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
    """Cards say Projected only when the teams have Elo-weighted odds; otherwise Toss-up."""
    assert odds_mode(TEAMS) == "projected"
    assert odds_mode([_team("A", 0.5, weighted=False)]) == "tossup"


def test_description_keeps_the_headline_and_cuts_long_ones_at_a_word():
    """A short headline is the description as is; a long one is cut at a word, within 155 characters, with an ellipsis."""
    short = "Raleigh clinches the region with a win over Seminary."
    assert description(short) == short
    long = "Raleigh clinches the region with a win over Seminary, " * 5
    cut = description(long)
    assert len(cut) <= 155 and cut.endswith("…") and not cut.endswith(" …")
    assert long.startswith(cut[:-1])


def test_meta_tags_escape_and_carry_every_preview_tag():
    """The title, description and URLs are escaped, and every tag link previews read is there."""
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
    """A long headline wraps to three lines that fit the card, the last ending in an ellipsis; a short one stays one line."""
    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font = _inter(34, 600)
    lines = wrap(draw, "word " * 200, font, 1072, 3)
    assert len(lines) == 3 and lines[-1].endswith("…")
    assert all(draw.textlength(line, font=font) <= 1072 for line in lines)
    assert wrap(draw, "Short and sweet.", font, 1072, 3) == ["Short and sweet."]


def test_cards_render_at_link_preview_size():
    """Region, class and site cards render at the link-preview size, even with no headline or teams."""
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
    assert written == {"regions": 2, "classes": 1, "teams": 8, "brackets": 0, "bracket_teams": 0, "past_brackets": 0}
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
    assert position_labels(standing_positions(ordered)) == ["T-1", "T-1", "T-1", "T-4", "T-4"]
    assert position_labels([1, 2, 2, 4]) == ["1", "T-2", "T-2", "4"]  # a shared position reads as a tie, not a seed
    # A team that hasn't played sits with the .500 teams.
    fresh = [_team("A", 0.5, region_wins=1, region_losses=1), _team("B", 0.5, region_wins=0, region_losses=0)]
    assert standing_positions(display_order(fresh)) == [1, 1]


def _with_bracket(team, **reach):
    """A team entry with round-by-round reach odds (same in both modes)."""
    rounds = {"second_round": 0.0, "quarterfinals": 0.0, "semifinals": 0.0, "finals": 0.0, "champion": 0.0, **reach}
    return {**team, "bracket_odds": {**rounds, **{f"{k}_weighted": v for k, v in rounds.items()}}}


def test_slugs_match_the_site():
    """Same cases as routes.test.mjs, so a card's file matches the ?team= the app writes."""
    assert slugify("St. Martin") == "st-martin"
    assert slugify("D'Iberville") == "diberville"
    assert slugify("St. Andrew’s") == "st-andrews"
    assert slugify("H. W. Byers") == "h-w-byers"
    assert slugify("Jefferson Davis County") == "jefferson-davis-county"


def test_team_status_matches_the_page_badges():
    """A team card's status is the page's badge: clinched (with its seed when locked), eliminated, or none; then the playoff run."""
    locked = _team("Raleigh", 1.0, 1.0)
    assert team_status(locked, 3) == ("clinched", "Clinched #1")
    assert team_status({**_team("Magee", 0.4), "eliminated": True}, 3) == ("eliminated", "Eliminated")
    assert team_status({**_team("Seminary", 1.0, 0.5), "clinched": True}, 3) == ("clinched", "Clinched")
    assert team_status(_team("Mize", 0.5), 3) is None
    # Once the bracket is underway, the run takes over.
    assert team_status(_with_bracket(locked, second_round=1.0, quarterfinals=0.0), 3) == (
        "eliminated",
        "Lost in Second Round",
    )
    assert team_status(_with_bracket(locked, second_round=1.0, quarterfinals=1.0, semifinals=0.5), 3) == (
        "clinched",
        "Advanced to Quarterfinals",
    )
    champ = _with_bracket(locked, second_round=1, quarterfinals=1, semifinals=1, finals=1, champion=1)
    assert team_status(champ, 3) == ("champion", "State Champion")


def test_team_description_states_its_numbers():
    """A team's description gives its record, the odds mode, and the odds that apply (no "0% to win the region"; none once it's out)."""
    racing = _with_bracket(_team("Raleigh", 0.997, 0.39), second_round=0.6, champion=0.04)
    assert team_description(racing, 3, 6, "projected") == (
        "Raleigh (6–2, 3–1 in Region 6-3A), Projected odds: 39% to win the region, >99% to make the playoffs, 4% to win the state championship."
    )
    locked = _with_bracket(_team("Raleigh", 1.0, 1.0), second_round=0.8, champion=0.06)
    assert (
        team_description(locked, 3, 6, "projected")
        == "Raleigh (6–2, 3–1 in Region 6-3A), Projected odds: locked in as the #1 seed, 6% to win the state championship."
    )
    # Can't win the region: it doesn't lead with "0% to win the region".
    chasing = _team("Magee", 0.28, 0.0)
    assert (
        team_description(chasing, 3, 6, "projected")
        == "Magee (6–2, 3–1 in Region 6-3A), Projected odds: 28% to make the playoffs."
    )
    # The mode comes up front, so trimming a long line to the preview limit can't drop it.
    assert team_description(chasing, 3, 6, "tossup").startswith("Magee (6–2, 3–1 in Region 6-3A), Toss-up odds: ")
    out = {**_team("Mize", 0.0), "eliminated": True}  # facts only: no odds mode named
    assert team_description(out, 3, 6, "projected") == "Mize (6–2, 3–1 in Region 6-3A): out of the playoff race."


def test_team_card_renders_with_and_without_a_playoff_path():
    """A team card renders at preview size for both bracket shapes and with a long school name."""
    team = _with_bracket(_team("Jefferson Davis County Attendance Center", 0.6, 0.1), second_round=0.3, champion=0.01)
    for clazz in (3, 6):  # 5A-7A have no second round
        assert render_team_card(clazz, 6, team, "Through Week 8 · Oct 9 · Projected", "projected").size == (
            WIDTH,
            HEIGHT,
        )
    assert render_team_card(3, 6, _team("Mize", 0.5), "x", "tossup").size == (WIDTH, HEIGHT)


def test_team_files_for_teams_no_longer_in_a_region_are_removed(tmp_path):
    """Writing a region's team files removes one for a team no longer there and writes each current team's card and tags."""
    api = {
        "/seasons": [{"season": 2026}],
        "/standings/3?season=2026": {"as_of_date": "2026-10-09", "regions": [{"region": 6, "teams": TEAMS}]},
        "/seasons/2026/dates?class=3": {"dates": DATES},
        "/standings/3/6?season=2026": {"as_of_date": "2026-10-09", "headline": "Raleigh leads.", "teams": TEAMS},
    }
    (tmp_path / "meta" / "3-6").mkdir(parents=True)
    (tmp_path / "meta" / "3-6" / "moved-away.html").write_text("old")
    assert build_share_assets(api.get, tmp_path, "https://mshsfootball.com", date(2026, 10, 14))["teams"] == 4
    assert sorted(p.name for p in (tmp_path / "meta" / "3-6").iterdir()) == [
        "magee.html",
        "mize.html",
        "raleigh.html",
        "seminary.html",
    ]
    meta = (tmp_path / "meta" / "3-6" / "raleigh.html").read_text()
    assert "<title>Raleigh in the Region 6-3A playoff race — Mississippi High School Football</title>" in meta
    assert "https://mshsfootball.com/static/og/3-6/raleigh.png?v=20261009" in meta
    assert 'href="https://mshsfootball.com/standings/3a/6?team=raleigh"' in meta
    assert Image.open(tmp_path / "og" / "3-6" / "raleigh.png").size == (WIDTH, HEIGHT)


def _occ(team, p, locked=False):
    """A bracket side's occupant: *team*, its chance of being there, and whether it's locked in."""
    return {"team": team, "p_reach": p, "p_reach_weighted": None, "is_locked": locked}


def _mu(a, b, p, host_a):
    """A bracket matchup: *a* vs *b*, its chance, and *a*'s chance of hosting."""
    return {
        "team_a": a,
        "team_b": b,
        "p_matchup": p,
        "p_matchup_weighted": None,
        "p_host_a": host_a,
        "p_host_a_weighted": None,
    }


GAMES = [
    # First round: Raleigh is the 1 seed or the 2 seed, in two different games.
    {
        "id": "S-0-0",
        "round": "First Round",
        "side_a": {"occupants": [_occ("Raleigh", 0.6), _occ("Magee", 0.4)]},
        "side_b": {"occupants": [_occ("Tylertown", 1.0, True)]},
        "matchups": [_mu("Raleigh", "Tylertown", 0.6, 1.0), _mu("Magee", "Tylertown", 0.4, 1.0)],
    },
    {
        "id": "S-0-1",
        "round": "First Round",
        "side_a": {"occupants": [_occ("Union", 1.0, True)]},
        "side_b": {"occupants": [_occ("Raleigh", 0.4), _occ("Magee", 0.6)]},
        "matchups": [_mu("Union", "Raleigh", 0.4, 1.0), _mu("Union", "Magee", 0.6, 1.0)],
    },
    {
        "id": "S-1-0",
        "round": "Second Round",
        "side_a": {"occupants": [_occ("Raleigh", 0.5), _occ("Tylertown", 0.5)]},
        "side_b": {"occupants": [_occ("Union", 0.7), _occ("Magee", 0.3)]},
        "matchups": [
            _mu("Raleigh", "Union", 0.35, 0.6),
            _mu("Raleigh", "Magee", 0.15, 0.6),
            _mu("Tylertown", "Union", 0.35, 0.5),
        ],
    },
    {
        "id": "final",
        "round": "Championship Game",
        "side_a": {"occupants": [_occ("Raleigh", 0.1)]},
        "side_b": {"occupants": [_occ("Pisgah", 0.2)]},
        "matchups": [],
    },
]


def test_team_road_adds_both_sides_and_finds_the_likeliest_opponent():
    """Raleigh can be in either first-round game; the road sums them and names the likeliest opponent overall."""
    road = team_road(GAMES, "Raleigh", "tossup")
    assert [s["round"] for s in road] == ["First Round", "Second Round", "Championship Game"]
    first, second, final = road
    assert first["reach"] == 1.0
    assert (first["opponent"], first["hosts"]) == ("Tylertown", "team")  # 0.6 vs Tylertown beats 0.4 at Union
    assert abs(first["p_if_there"] - 0.6) < 1e-9
    assert (second["opponent"], second["hosts"]) == ("Union", "split")
    assert abs(second["p_if_there"] - 0.7) < 1e-9 and abs(second["p_team_hosts"] - 0.6) < 1e-9
    assert final["opponent"] is None  # every pairing under the listing floor
    union = team_road(GAMES, "Union", "tossup")[0]
    assert (union["opponent"], union["hosts"]) == ("Magee", "team")
    assert team_road(GAMES, "Nobody", "tossup") == []


def test_team_bracket_description_names_the_road():
    """A team's bracket description names its likeliest opponent in each round and its title chance."""
    road = team_road(GAMES, "Raleigh", "tossup")
    assert team_bracket_description("Raleigh", road, 0.04, "tossup") == (
        "Raleigh’s likeliest opponents (Toss-up): First Round vs Tylertown, Second Round vs Union; 4% to win the state championship."
    )


def _bracket_team(name, semis, final, champ, playoffs=1.0):
    """A team with these semifinal, final and championship odds (both modes)."""
    t = _team(name, playoffs)
    odds = {"second_round": 0.8, "quarterfinals": 0.5, "semifinals": semis, "finals": final, "champion": champ}
    return {**t, "bracket_odds": {**odds, **{f"{k}_weighted": v for k, v in odds.items()}}}


def test_bracket_favorites_and_description():
    """The bracket's favorites are the likeliest champions (ties broken by the final, then the semifinal); the description follows the season to its champion."""
    teams = [
        _bracket_team("Magee", 0.3, 0.15, 0.05),
        _bracket_team("Raleigh", 0.4, 0.2, 0.12),
        _bracket_team("Out", 0.0, 0.0, 0.0, playoffs=0.0),
        _bracket_team("Seminary", 0.3, 0.16, 0.05),
    ]
    favorites = bracket_favorites(teams, "projected")
    assert [t["school"] for t in favorites] == ["Raleigh", "Seminary", "Magee"]  # ties broken by the final, then semis
    assert bracket_description(3, favorites, "projected") == (
        "Projected odds: Raleigh leads the Class 3A bracket at 12% to win the state championship, ahead of Seminary (5%) and Magee (5%)."
    )
    champ = [_bracket_team("Raleigh", 1.0, 1.0, 1.0)]
    assert bracket_description(3, champ, "projected") == "Raleigh won the Class 3A state championship."
    assert bracket_description(3, [], "projected") == "Who might play whom in the Class 3A playoffs, and where."


def test_bracket_cards_render():
    """The class bracket card and a team's bracket card render at preview size."""
    teams = [_bracket_team(n, 0.3, 0.15, 0.05) for n in ("Raleigh", "Magee", "Seminary Attendance Center Long Name")]
    regions = {t["school"]: 6 for t in teams}
    assert render_bracket_card(3, teams, regions, "x", "projected").size == (WIDTH, HEIGHT)
    road = team_road(GAMES, "Raleigh", "tossup")
    assert render_team_bracket_card(3, 6, teams[0], road, "x", "tossup").size == (WIDTH, HEIGHT)


def test_pipeline_writes_bracket_cards_for_teams_with_a_road(tmp_path):
    """The pipeline writes a bracket card and tags for each team with a road, removes stale ones, and writes the bracket page."""
    teams = [_bracket_team("Raleigh", 0.4, 0.2, 0.12), _bracket_team("Union", 0.3, 0.1, 0.05)]
    api = {
        "/seasons": [{"season": 2026}],
        "/standings/3?season=2026": {"as_of_date": "2026-10-09", "regions": [{"region": 6, "teams": teams}]},
        "/seasons/2026/dates?class=3": {"dates": DATES},
        "/standings/3/6?season=2026": {"as_of_date": "2026-10-09", "headline": "Raleigh leads.", "teams": teams},
        "/bracket/matchups?season=2026&class=3": {"games": GAMES},
        "/championships?season=2026&class=3": [
            {"season": 2026, "class_": 3, "location": {"name": "Davis Wade Stadium", "city": "Starkville, MS"}}
        ],
    }
    (tmp_path / "og" / "bracket-3").mkdir(parents=True)
    (tmp_path / "og" / "bracket-3" / "gone.png").write_bytes(b"old")
    (tmp_path / "bracket" / "2026").mkdir(parents=True)
    (tmp_path / "bracket" / "2026" / "3a-all-odds.png").write_bytes(b"named before themes")
    (tmp_path / "og" / "bracket-3.png").write_bytes(b"named before it carried the season")
    written = build_share_assets(api.get, tmp_path, "https://mshsfootball.com", date(2026, 10, 14))
    assert (written["brackets"], written["bracket_teams"]) == (1, 2)
    assert sorted(p.name for p in (tmp_path / "og" / "bracket-3").iterdir()) == ["raleigh.png", "union.png"]
    meta = (tmp_path / "meta" / "bracket-3" / "raleigh.html").read_text()
    assert "Raleigh’s path in the Class 3A bracket" in meta
    assert 'href="https://mshsfootball.com/brackets/3a?team=raleigh"' in meta
    assert "https://mshsfootball.com/static/og/bracket-3/raleigh.png?v=20261009" in meta
    page = (tmp_path / "body" / "bracket-3.html").read_text()  # the bracket page itself, readable without JavaScript
    assert '<h1 class="title">Class 3A Bracket</h1>' in page and 'class="tslot"' in page
    assert '<p class="tfinal__venue">Davis Wade Stadium • Starkville</p>' in page  # where the final is played
    assert '"@type":"BreadcrumbList"' in (tmp_path / "meta" / "bracket-3.html").read_text()
    assert "Raleigh leads the Class 3A bracket" in (tmp_path / "meta" / "bracket-3.html").read_text()
    # The link preview: a picture of the whole bracket, named for its season, under both names: the
    # page's (/brackets/3a) and the season's (/brackets/3a?season=2026), which keeps its own address.
    assert not (tmp_path / "og" / "bracket-3.png").exists()
    assert Image.open(tmp_path / "og" / "bracket-2026-3.png").size == (WIDTH, HEIGHT)
    card = "https://mshsfootball.com/static/og/bracket-2026-3.png?v=20261009"
    assert card in (tmp_path / "meta" / "bracket-3.html").read_text()
    season_meta = (tmp_path / "meta" / "bracket-2026-3.html").read_text()
    assert card in season_meta and "<title>2026 Class 3A playoff bracket — " in season_meta
    assert '<meta property="og:url" content="https://mshsfootball.com/brackets/3a?season=2026">' in season_meta
    # The bracket's images to share: every view blank; no Projected ones without Projected odds. The
    # sitemap lists the whole-bracket image with the bracket page.
    images = sorted(p.name for p in (tmp_path / "bracket" / "2026").iterdir())
    assert images == [f"3a-{v}-blank-{t}.png" for v in ("all", "north", "south") for t in ("dark", "light")]
    sitemap = (tmp_path / "sitemap.xml").read_text()
    assert (
        "<loc>https://mshsfootball.com/brackets/3a</loc><lastmod>2026-10-09</lastmod><image:image>"
        "<image:loc>https://mshsfootball.com/static/bracket/2026/3a-all-blank-light.png</image:loc></image:image>"
    ) in sitemap


def test_past_seasons_get_their_final_bracket_images_once(tmp_path):
    """A past season's bracket is drawn as of its last week of games, blank (results), and not again next run."""
    teams = [_bracket_team("Raleigh", 0.4, 0.2, 0.12), _bracket_team("Union", 0.3, 0.1, 0.05)]
    calls: list[str] = []
    api = {
        "/seasons": [{"season": 2026}, {"season": 2025}],
        "/standings/3?season=2026": {"as_of_date": "2026-10-09", "regions": [{"region": 6, "teams": teams}]},
        "/seasons/2026/dates?class=3": {"dates": DATES},
        "/standings/3/6?season=2026": {"as_of_date": "2026-10-09", "headline": None, "teams": teams},
        "/seasons/2025/dates?class=3": {
            "dates": [{"date": "2025-12-05", "kind": "games", "week": 15, "description": "Championship Game"}]
        },
        # Its last game day was Friday, Dec 5: the bracket as of that week's Sunday, Dec 7.
        "/bracket/matchups?season=2025&class=3&date=2025-12-07": {"as_of_date": "2025-12-07", "games": GAMES},
    }

    def fetch(path):
        calls.append(path)
        return api.get(path)

    assert build_share_assets(fetch, tmp_path, "https://mshsfootball.com", date(2026, 10, 14))["past_brackets"] == 1
    assert sorted(p.name for p in (tmp_path / "bracket" / "2025").iterdir()) == [
        f"3a-{v}-blank-{t}.png" for v in ("all", "north", "south") for t in ("dark", "light")
    ]
    # Its link preview, for /brackets/3a?season=2025.
    assert Image.open(tmp_path / "og" / "bracket-2025-3.png").size == (WIDTH, HEIGHT)
    meta = (tmp_path / "meta" / "bracket-2025-3.html").read_text()
    assert "<title>2025 Class 3A playoff bracket — " in meta
    assert "https://mshsfootball.com/static/og/bracket-2025-3.png?v=20251207" in meta
    assert '<meta property="og:url" content="https://mshsfootball.com/brackets/3a?season=2025">' in meta
    assert '<meta name="description" content="The 2025 Class 3A playoff bracket.">' in meta  # no final result here
    calls.clear()
    assert build_share_assets(fetch, tmp_path, "https://mshsfootball.com", date(2026, 10, 14))["past_brackets"] == 0
    assert not [c for c in calls if "season=2025" in c]  # already drawn: not fetched again


def test_titles_fall_back_to_inter_bold_without_the_nippo_file(tmp_path, monkeypatch, caplog):
    """Nippo isn't in the repository (its license), so without the file the cards still draw, in Inter Bold."""
    import backend.helpers.share_cards as sc

    monkeypatch.setattr(sc, "NIPPO", tmp_path / "Nippo-Bold.otf")
    sc._nippo.cache_clear()
    try:
        font = sc._nippo(30)
        assert font.getname()[0] == "Inter" and "Nippo-Bold.otf not found" in caplog.text
        assert render_site_card().size == (WIDTH, HEIGHT)
    finally:
        sc._nippo.cache_clear()


def test_team_road_names_a_host_only_when_hosting_is_certain():
    """A 99.99% chance of hosting is a split with its chance, not "at home"; only a certainty is "team"."""
    near = [{**GAMES[0], "matchups": [_mu("Raleigh", "Tylertown", 0.6, 0.9999), _mu("Magee", "Tylertown", 0.4, 1.0)]}]
    first = team_road(near, "Raleigh", "tossup")[0]
    assert first["hosts"] == "split" and abs(first["p_team_hosts"] - 0.9999) < 1e-12
    away = [{**GAMES[0], "matchups": [_mu("Raleigh", "Tylertown", 0.6, 0.0001), _mu("Magee", "Tylertown", 0.4, 1.0)]}]
    assert team_road(away, "Raleigh", "tossup")[0]["hosts"] == "split"
    assert team_road(GAMES, "Raleigh", "tossup")[0]["hosts"] == "team"  # p_host_a exactly 1


def test_a_past_seasons_bracket_says_who_won_it():
    from backend.helpers.share_cards import bracket_title, past_bracket_description

    assert past_bracket_description(3, 2025, {"final": {"winner": "Raleigh"}}) == (
        "Raleigh won the 2025 Class 3A state championship."
    )
    assert past_bracket_description(3, 2025, {}) == "The 2025 Class 3A playoff bracket."
    assert bracket_title(3, 2025) == "2025 Class 3A playoff bracket — Mississippi High School Football"
    assert bracket_title(3) == "Class 3A playoff bracket — Mississippi High School Football"
