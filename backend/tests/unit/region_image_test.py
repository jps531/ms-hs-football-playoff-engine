"""A region's overview as an image to share: its size, what it fits, and a finished region's playoff road."""

from PIL import Image

from backend.helpers.region_image import (
    SIZE,
    _games_list,
    _Page,
    region_playoffs,
    region_seeds,
    render_region_overview,
)
from backend.tests.unit.share_cards_test import TEAMS, _team

GOLD = (0xD9, 0xA5, 0x20)  # the trophy's ball


def _certain(name: str, seed: int) -> dict:
    """A finished region's team, certain of *seed*."""
    t = _team(name, 1.0 if seed <= 4 else 0.0)
    t["odds"] = {**t["odds"], **{f"p{k}": 1.0 if k == seed else 0.0 for k in (1, 2, 3, 4)}}
    return t


FINISHED = {"headline": "Raleigh won the region.", "teams": [_certain("Raleigh", 1), _certain("Magee", 2)]}


def _side(team: str | None, region: int, seed: int) -> dict:
    """A bracket side: locked to *team*, or open (fed by a region seed)."""
    occupants = [{"team": team, "p_reach": 1.0, "is_locked": True}] if team else []
    return {"feeders": [{"region": region, "seed": seed}], "occupants": occupants}


def _game(gid: str, rnd: str, a: dict, b: dict, matchups=()) -> dict:
    """A bracket game."""
    return {"id": gid, "round": rnd, "side_a": a, "side_b": b, "matchups": list(matchups)}


def _later(gid: str, rnd: str, team: str, opponent: str | None, host_a: float | None) -> dict:
    """A later-round game where *team* is locked in, against *opponent* (or one not yet set)."""
    a = {
        "feeders": [{"region": 6, "seed": 1}, {"region": 5, "seed": 4}],
        "occupants": [{"team": team, "is_locked": True}],
    }
    b_occ = [{"team": opponent, "is_locked": True}] if opponent else []
    b = {"feeders": [{"region": 7, "seed": 2}, {"region": 8, "seed": 3}], "occupants": b_occ}
    mu = [{"team_a": team, "team_b": opponent, "p_host_a": host_a}] if opponent else []
    return _game(gid, rnd, a, b, mu)


def test_the_overview_is_a_4_by_5_page_in_either_theme_and_odds_mode():
    payload = {"headline": "Raleigh leads.", "teams": TEAMS, "remaining_games": [{"team_a": "Magee", "team_b": "Mize"}]}
    for theme in ("dark", "light"):
        for mode in ("projected", "tossup"):
            (page,) = render_region_overview(3, 6, 2026, payload, [], "2026 season · x", mode, theme)
            assert page.size == SIZE == (2160, 2700)


def test_remaining_games_that_dont_fit_are_counted():
    """The games list fills one column, then two; what's left over is counted for the region page."""
    rows = [{"date": "Fri, Oct 9", "first": f"Team {i}", "joiner": "at", "second": f"Team {i + 1}"} for i in range(60)]
    page = _Page.new("dark", {})
    _, left_out = _games_list(page, 0, 900, rows)
    assert 0 < left_out < 60
    _, none_left = _games_list(page, 0, 2000, rows[:5])
    assert none_left == 0


def test_a_finished_regions_seeds():
    assert region_seeds(FINISHED) == {"Raleigh": 1, "Magee": 2}
    assert region_seeds({**FINISHED, "remaining_games": [{"team_a": "Raleigh", "team_b": "Magee"}]}) == {}


def test_a_playoff_road_lists_each_game_played_then_the_next():
    first = [
        _game(
            "N-0-0",
            "First Round",
            _side("Raleigh", 6, 1),
            _side("Pisgah", 5, 4),
            [
                {"team_a": "Raleigh", "team_b": "Pisgah", "p_host_a": 1.0},
            ],
        ),
        _game(
            "N-0-1",
            "First Round",
            _side("Union", 7, 2),
            _side("Magee", 6, 2),
            [
                {"team_a": "Union", "team_b": "Magee", "p_host_a": 1.0},
            ],
        ),
    ]
    # Before any game: each team's first-round game, with who hosts when it's certain.
    before = region_playoffs({"Raleigh": 1, "Magee": 2}, first, {})
    assert before == [
        {"seed": 1, "team": "Raleigh", "steps": [("First Round", "Next: vs Pisgah, at home")]},
        {"seed": 2, "team": "Magee", "steps": [("First Round", "Next: at Union")]},
    ]
    # An opponent not set yet is named by the seed that goes there.
    open_ = [_game("N-0-0", "First Round", _side("Raleigh", 6, 1), _side(None, 5, 4))]
    assert region_playoffs({"Raleigh": 1}, open_, {})[0]["steps"] == [("First Round", "Next: vs the Region 5 #4 seed")]
    # Played: wins with their scores, a loss ends the road, the next game while still in.
    games = [*first, _later("N-1-0", "Second Round", "Raleigh", None, None)]
    results = {
        "N-0-0": {"winner": "Raleigh", "loser": "Pisgah", "winner_score": 42, "loser_score": 0},
        "N-0-1": {"winner": "Union", "loser": "Magee", "winner_score": 33, "loser_score": 27},
    }
    after = region_playoffs({"Raleigh": 1, "Magee": 2}, games, results)
    assert after[0]["steps"] == [
        ("First Round", "Beat Pisgah 42–0"),
        ("Second Round", "Next: vs an opponent not yet set"),
    ]
    assert after[1]["steps"] == [("First Round", "Lost to Union 27–33")]
    # The championship won: the road ends with the title.
    final = _later("final", "Championship Game", "Raleigh", "Noxubee County", None)
    results["final"] = {"winner": "Raleigh", "loser": "Noxubee County", "winner_score": 12, "loser_score": 6}
    road = region_playoffs({"Raleigh": 1}, [*first, final], results)[0]["steps"]
    assert road[-2:] == [("Championship Game", "Beat Noxubee County 12–6"), ("", "Won the state championship")]


def test_a_finished_region_shows_its_playoff_road_and_its_champion_gets_the_trophy():
    def gold(img: Image.Image) -> int:
        return sum(1 for px in img.getdata() if px == GOLD)

    champion = [
        {
            "seed": 1,
            "team": "Raleigh",
            "steps": [("Championship Game", "Beat Noxubee County 12–6"), ("", "Won the state championship")],
        }
    ]
    beaten = [{"seed": 1, "team": "Raleigh", "steps": [("Semifinals", "Lost to Seminary 14–27")]}]
    with_cup = render_region_overview(3, 6, 2025, FINISHED, [], "2025 season · Final", "projected", playoffs=champion)[
        0
    ]
    without = render_region_overview(3, 6, 2025, FINISHED, [], "2025 season · Final", "projected", playoffs=beaten)[0]
    plain = render_region_overview(3, 6, 2025, FINISHED, [], "2025 season · Final", "projected")[0]
    assert gold(with_cup) > 1000 and gold(without) == 0
    assert without.tobytes() != plain.tobytes()  # the road is drawn
