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


# ----------------------------------------------------------------- what has to happen

from backend.helpers.region_image import CAPPED_PAGES, SHOW_ALL_PAGES  # noqa: E402
from backend.helpers.team_image import _split, render_team_scenarios, team_outcomes  # noqa: E402
from backend.prefect.share_assets_pipeline import _outcomes_payload  # noqa: E402
from backend.tests.unit.static_pages_test import _cond, _odds, _seed  # noqa: E402

SIX = ["Raleigh", "Seminary", "Magee", "Mize", "Taylorsville", "Bay Springs"]


def _ways(n: int) -> list[list[dict]]:
    """*n* ways, each two results."""
    return [
        [
            {"type": "game_result", "school": SIX[k % 6], "opponent": SIX[(k + 1) % 6], "min_margin": 1 + k},
            {"type": "game_result", "school": SIX[(k + 2) % 6], "opponent": SIX[(k + 3) % 6]},
        ]
        for k in range(n)
    ]


def _with_paths(seeds: dict[int, int], left: int = 3) -> dict:
    """Raleigh with a path to each seed in *seeds* (seed: its number of ways); the others without paths."""
    raleigh = {
        **TEAMS[0],
        "school": "Raleigh",
        "odds": _odds(0.25, 0.25, 0.25, 0.25),
        "paths": [_seed(s, _ways(n)) for s, n in seeds.items()],
    }
    others = [{**TEAMS[0], "school": s, "odds": _odds(0, 0, 0, 0), "paths": []} for s in SIX[1:]]
    return {
        "teams": [raleigh, *others],
        "remaining_games": [{"team_a": "Raleigh", "team_b": "Mize"}] * left,
        "scenarios_available": True,
        "key_insights": [],
    }


def test_the_teams_cards_are_the_region_pages_in_its_order():
    cards, intro = team_outcomes(_with_paths({2: 1, 1: 1, 3: 1}), "Raleigh", "tossup")
    assert [c["title"] for c in cards] == [
        "Raleigh wins the region",
        "Raleigh finishes as the #2 seed",
        "Raleigh finishes as the #3 seed",
    ]
    assert intro == ""
    assert team_outcomes(_with_paths({1: 1}), "Seminary", "tossup") == ([], "")  # nothing left for it
    assert team_outcomes(_with_paths({1: 1}, left=0), "Raleigh", "tossup") == ([], "")


def test_no_image_when_nothing_is_left_to_decide_for_the_team():
    assert render_team_scenarios(3, 6, 2026, _with_paths({1: 1}), "Seminary", "x", "tossup") == []
    pages = render_team_scenarios(3, 6, 2026, _with_paths({1: 2, 2: 2}), "Raleigh", "x", "projected", "light")
    assert len(pages) == 1 and pages[0].size == SIZE


def test_before_full_scenarios_the_results_that_settle_a_spot():
    payload = {
        "teams": [{**TEAMS[0], "school": s, "odds": _odds(0.2, 0.2, 0.2, 0.2)} for s in SIX],
        "remaining_games": [{"team_a": "Raleigh", "team_b": "Mize"}] * 8,
        "scenarios_available": False,
        "key_insights": [
            {
                "insight_type": "clinch_seed",
                "team": "Raleigh",
                "seed": 1,
                "conditions": [{"winner": "Raleigh", "loser": "Mize"}],
                "rendered": "Raleigh clinches the region: Raleigh beats Mize",
            }
        ],
    }
    cards, intro = team_outcomes(payload, "Raleigh", "tossup")
    assert len(cards) == 1 and intro.startswith("Full scenarios appear once five or fewer region games remain; 8")
    assert len(render_team_scenarios(3, 6, 2026, payload, "Raleigh", "x", "tossup")) == 1


def test_a_card_too_tall_for_a_page_continues_in_the_next_box_with_every_way():
    page = _Page.new("dark", {})
    card = {"team": "Raleigh", "title": "Raleigh wins the region", "p": 0.5, "groups": _ways(60)}
    boxes = _split(page, card, 1600)
    assert len(boxes) > 1 and all(h <= 1600 for _, h in boxes)
    assert [w for b, _ in boxes for w in b["groups"]] == card["groups"]  # every way, in order, once
    assert [b.get("continued", False) for b, _ in boxes] == [False] + [True] * (len(boxes) - 1)
    assert [b["continues"] for b, _ in boxes] == [True] * (len(boxes) - 1) + [False]


def test_a_list_up_to_five_pages_is_shown_in_full_and_a_longer_one_stops_at_four():
    needed = {}
    for n in range(10, 400, 10):
        payload = _with_paths({1: n, 2: n})
        needed.setdefault(len(render_team_scenarios(3, 6, 2026, payload, "Raleigh", "x", "tossup", show_all=99)), n)
        if max(needed) > SHOW_ALL_PAGES:
            break
    assert SHOW_ALL_PAGES in needed and max(needed) > SHOW_ALL_PAGES
    full = _with_paths({1: needed[SHOW_ALL_PAGES], 2: needed[SHOW_ALL_PAGES]})
    assert len(render_team_scenarios(3, 6, 2026, full, "Raleigh", "x", "tossup")) == SHOW_ALL_PAGES
    long = _with_paths({1: needed[max(needed)], 2: needed[max(needed)]})
    assert len(render_team_scenarios(3, 6, 2026, long, "Raleigh", "x", "tossup")) == CAPPED_PAGES


def test_a_teams_job_carries_only_its_own_paths_and_insights():
    paths = _with_paths({1: 1})
    paths["teams"][1]["paths"] = [_seed(2, _cond("Seminary", "Mize"))]
    mine = _outcomes_payload(paths, "Raleigh")
    assert [bool(t.get("paths")) for t in mine["teams"]] == [True] + [False] * 5
    assert mine["scenarios_available"] is True and mine["key_insights"] == []
    assert team_outcomes(mine, "Raleigh", "tossup") == team_outcomes(paths, "Raleigh", "tossup")
    # A team without paths of its own, once full scenarios exist, has nothing to show (as on the page).
    none = {**paths, "teams": [{**t, "paths": []} if t["school"] == "Mize" else t for t in paths["teams"]]}
    assert team_outcomes(_outcomes_payload(none, "Mize"), "Mize", "tossup") == ([], "")


def test_the_pipeline_draws_each_teams_what_has_to_happen_and_indexes_it(tmp_path):
    from datetime import date

    from backend.helpers.image_jobs import TEAM_SCENARIOS, draw_images
    from backend.prefect.share_assets_pipeline import _region_image_jobs, region_indexes

    paths = _with_paths({1: 1, 2: 1})
    payload = {k: v for k, v in paths.items() if k != "key_insights"}
    payload["teams"] = [{k: v for k, v in t.items() if k != "paths"} for t in paths["teams"]]
    jobs = _region_image_jobs(3, 6, 2026, payload, [], [], date(2026, 10, 9), date(2026, 10, 10), {}, {}, paths)
    mine = [j for j in jobs if j.renderer == TEAM_SCENARIOS]
    assert {j.kwargs["school"] for j in mine} == set(SIX)  # one job each (a team with nothing to show draws no file)
    assert mine[0].path == "region/2026/3a-6-team-raleigh-scenarios-projected-dark.png"
    files: dict[str, list[str]] = {}
    draw_images(tmp_path, mine, files_out=files)
    index = region_indexes(2026, mine, files)["region/2026/3a-6.json"]
    variants = [f"{m}-{t}" for m in ("projected", "tossup") for t in ("dark", "light")]
    assert index["teams"]["Raleigh"]["scenarios"] == dict.fromkeys(variants, 1)
    assert index["teams"]["Seminary"]["scenarios"] == dict.fromkeys(variants, 0)
    # Without paths (no games left), no such jobs.
    assert not [
        j
        for j in _region_image_jobs(3, 6, 2026, payload, [], [], date(2026, 10, 9), date(2026, 10, 10), {}, {})
        if j.renderer == TEAM_SCENARIOS
    ]
