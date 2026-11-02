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


# ----------------------------------------------------------------- the scenarios image

from itertools import permutations  # noqa: E402

from backend.helpers.region_image import CAPPED_PAGES, SHOW_ALL_PAGES, render_region_scenarios  # noqa: E402

SIX = ["Raleigh", "Seminary", "Magee", "Mize", "Taylorsville", "Bay Springs"]


def _scenarios(n: int, ways: int = 1, explain: bool = False, step_words: int = 30) -> list[dict]:
    """*n* distinct finishes (as the API gives them), each reached *ways* ways, maybe with an explanation."""
    out = []
    for i, order in enumerate(list(permutations(SIX))[:n]):
        groups = [
            [
                {
                    "type": "game_result",
                    "winner": order[0],
                    "loser": order[5],
                    "min_margin": 1 + k,
                    "max_margin": 2 + k,
                },
                {"type": "game_result", "winner": order[1], "loser": order[4], "min_margin": 1, "max_margin": None},
            ]
            for k in range(ways)
        ]
        why = [
            {
                "teams": [order[1], order[2]],
                "places": [2, 3],
                "steps": ["Head-to-head: " + "a long step " * step_words],
                "when": None,
            }
        ]
        out.append(
            {
                "scenario_num": i + 1,
                "sub_label": "",
                "title": "",
                "game_winners": [],
                "outcomes": {t: str(k + 1) for k, t in enumerate(order)},
                "conditions": None,
                "condition_groups": groups,
                "open_groups": None,
                "p": 1 / n,
                "p_weighted": 1 / n,
                "explanation": why if explain else None,
            }
        )
    return out


def _payload(scenarios=None, insights=None, left: int = 3) -> dict:
    """A region's payload with *left* games to play."""
    return {
        "headline": "",
        "teams": [_team(t, 0.5) for t in SIX],
        "remaining_games": [{"team_a": "Raleigh", "team_b": "Mize"}] * left,
        "scenarios": scenarios or [],
        "key_insights": insights or [],
    }


def _pages(payload: dict, **kw) -> int:
    """How many pages the scenarios image takes."""
    return len(render_region_scenarios(3, 6, 2026, payload, "x", "projected", **kw))


def test_no_scenarios_image_when_nothing_is_left_to_show():
    assert _pages(_payload(_scenarios(3), left=0)) == 0  # every region game played
    assert _pages(_payload(left=12)) == 0  # no full scenarios yet, and no result settles a spot


def test_every_page_is_4_by_5_and_a_short_list_fits_on_one():
    pages = render_region_scenarios(3, 6, 2026, _payload(_scenarios(2)), "x", "tossup", "light")
    assert len(pages) == 1 and pages[0].size == SIZE


def test_a_list_up_to_five_pages_is_shown_in_full_and_a_longer_one_stops_at_four():
    """Never leaves out a sliver: a list one page past four is shown whole; past five, four pages and the rest
    on the region page."""
    needed = {}
    for n in range(4, 80, 2):
        needed.setdefault(_pages(_payload(_scenarios(n)), show_all=99, capped=99), n)
        if max(needed) > SHOW_ALL_PAGES:
            break
    assert SHOW_ALL_PAGES in needed and max(needed) > SHOW_ALL_PAGES
    assert _pages(_payload(_scenarios(needed[SHOW_ALL_PAGES]))) == SHOW_ALL_PAGES
    assert _pages(_payload(_scenarios(needed[max(needed)]))) == CAPPED_PAGES


def test_explanations_go_in_only_where_they_add_no_page():
    """Against the same cards with every explanation left to the region page (one too long to ever fit):
    the explanations that go in add no page, and some do go in."""
    for n in (2, 8, 14):
        pointers = _pages(_payload(_scenarios(n, explain=True, step_words=5000)))
        assert _pages(_payload(_scenarios(n, explain=True))) == pointers
    one = render_region_scenarios(3, 6, 2026, _payload(_scenarios(1, explain=True)), "x", "projected")[0]
    pointer = render_region_scenarios(
        3, 6, 2026, _payload(_scenarios(1, explain=True, step_words=5000)), "x", "projected"
    )[0]
    assert one.tobytes() != pointer.tobytes()  # a short list has room: the explanation is drawn


def test_a_scenario_too_long_for_a_page_keeps_its_first_ways():
    """Its first ways, whole, and how many more there are; nothing cut mid-way."""
    assert _pages(_payload(_scenarios(1, ways=200))) == 1


def test_before_full_scenarios_the_results_that_settle_a_spot():
    insight = {
        "insight_type": "clinch_seed",
        "team": "Raleigh",
        "seed": 1,
        "conditions": [{"winner": "Raleigh", "loser": "Mize"}],
        "rendered": "Raleigh clinches the region: Raleigh beats Mize",
    }
    pages = render_region_scenarios(3, 6, 2026, _payload(insights=[insight], left=9), "x", "projected", "dark")
    assert len(pages) == 1 and pages[0].size == SIZE
