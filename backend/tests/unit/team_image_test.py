"""A team's season as an image to share: its games, its playoff rounds, and its road through the bracket."""

from PIL import Image, ImageDraw

from backend.helpers.region_image import SIZE, _Page
from backend.helpers.share_cards import _inter
from backend.helpers.team_image import _ladder, playoff_rounds, render_team_season, score_size, team_games
from backend.tests.unit.region_image_test import GOLD
from backend.tests.unit.share_cards_test import TEAMS


def _g(a, b, score=None, loc="home", region=True, when="2026-10-09", rnd=None):
    """A ``/games`` row: *a* vs *b*, with *a*'s location and, when played, the score (a's first)."""
    row = {"team_a": a, "team_b": b, "location_a": loc, "is_region_game": region, "date": when, "round": rnd}
    if score:
        row |= {"final": True, "score_a": score[0], "score_b": score[1]}
    return row


def test_a_teams_games_played_then_to_play():
    games = [
        _g("Magee", "Raleigh", (6, 35), loc="away", when="2026-10-17"),
        _g("Mize", "Magee", (36, 41), loc="home", region=False, when="2026-09-12"),
        _g("Magee", "Seminary", (27, 27), when="2026-10-24"),
        _g("Seminary", "Magee", when="2026-10-31"),
        _g("Raleigh", "Seminary", (1, 0)),  # not Magee's
        _g("Magee", "Quitman", (23, 16), when="2026-11-14", rnd="First Round"),  # left to the playoff road
    ]
    played, to_play = team_games("Magee", games)
    assert [(g["date"], g["opponent"], g["joiner"], g["result"], g["region"]) for g in played] == [
        ("2026-09-12", "Mize", "at", "W", False),
        ("2026-10-17", "Raleigh", "at", "L", True),
        ("2026-10-24", "Seminary", "vs", "T", True),
    ]
    assert (played[0]["score_for"], played[0]["score_against"]) == (41, 36)  # the team's score first
    assert [(g["opponent"], g["joiner"]) for g in to_play] == [("Seminary", "at")]


def test_playoff_rounds_skip_the_second_round_in_5a_to_7a():
    team = {
        **TEAMS[0],
        "bracket_odds": dict.fromkeys(("second_round", "quarterfinals", "semifinals", "finals", "champion"), 0.5),
    }
    assert [r["round"] for r in playoff_rounds(team, "tossup", 3)] == [
        "First Round", "Second Round", "Quarterfinals", "Semifinals", "Championship Game", "Champions",
    ]  # fmt: skip
    assert "Second Round" not in [r["round"] for r in playoff_rounds(team, "tossup", 6)]
    assert playoff_rounds(TEAMS[0], "tossup", 3) == []  # no bracket odds


def test_the_season_is_a_4_by_5_page_in_either_theme():
    payload = {"teams": TEAMS, "remaining_games": []}
    games = [_g(TEAMS[0]["school"], TEAMS[1]["school"], (21, 14))]
    for theme in ("dark", "light"):
        (page,) = render_team_season(3, 6, 2026, payload, TEAMS[0]["school"], games, "x", "projected", theme)
        assert page.size == SIZE


def test_every_score_fits_its_box():
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    for score in ("12–6", "34–28", "100–98"):
        size = score_size(d, "W", score, 253)  # a box's inside when a class has all six rounds
        assert d.textlength("W", font=_inter(size + 4, 700)) + 14 + d.textlength(score, font=_inter(size, 700)) <= 253
    assert score_size(d, "W", "12–6", 253) == 56  # a short score keeps the full size


def _rounds():
    return [
        {"round": r, "reach": 1.0, "neutral": r == "Championship Game", "host_if_reach": None, "host_overall": None}
        for r in ("First Round", "Second Round", "Quarterfinals", "Semifinals", "Championship Game", "Champions")
    ]


def _won(rnd, opp):
    return {"round": rnd, "kind": "won", "opponent": opp, "score_for": 28, "score_against": 14, "where": None}


def test_the_road_stops_at_a_loss_and_a_champion_gets_the_trophy():
    def draw(road):
        page = _Page.new("dark", {})
        _ladder(page, 0, _rounds(), road)
        return page.img

    lost = [_won("First Round", "Pisgah"), {**_won("Second Round", "Union"), "kind": "lost"}]
    img = draw(lost)
    # Nothing past the second round's box: the right of the row is the page's background.
    right = img.crop((SIZE[0] // 2, 100, SIZE[0], 400))
    assert len(set(right.getdata())) == 1
    final = [_won(r, "X") for r in ("First Round", "Second Round", "Quarterfinals", "Semifinals", "Championship Game")]
    assert sum(1 for px in draw(final).getdata() if px == GOLD) > 1000
