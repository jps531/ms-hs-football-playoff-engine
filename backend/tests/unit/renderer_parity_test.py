"""The pre-rendered pages and the app agree.

``static_pages.py`` (and ``share_cards.py``'s text helpers) mirror the site's JavaScript function by
function, so a page reads the same before and after the app draws it (docs/architecture/FRONTEND.md).
Each side has its own tests; this file runs both on the same input and checks the answers match, so a
change to one side that the other doesn't get fails here. The JavaScript runs under Node, through
``nginx/tests/parity/run.mjs``.

Data is compared exactly (the JavaScript's camelCase keys read as snake_case); HTML by the words a
reader gets (tags dropped, entities decoded, whitespace collapsed), since the two sides lay out their
markup differently.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import backend.helpers.bracket_home_odds as odds
import backend.helpers.share_cards as cards
import backend.helpers.static_pages as sp
from backend.tests.unit.static_pages_test import (
    _REGION_6,
    _TIE,
    BRACKET,
    INSIGHTS,
    STRINGER,
    TEAMS,
    UNCONDITIONAL,
    _cond,
    _odds,
    _playoffs,
    _seed,
)

ROOT = Path(__file__).resolve().parents[3]

# Two positions meeting in a playoff game: same region, cross-region with different seeds, and
# equal seeds from lower/higher-numbered regions (the odd/even-year tiebreak).
HOST_PAIRS = [((1, 1), (1, 3)), ((1, 4), (1, 2)), ((1, 2), (2, 3)), ((3, 4), (2, 1)), ((1, 2), (4, 2)), ((5, 1), (2, 1))]
RUNNER = ROOT / "nginx" / "tests" / "parity" / "run.mjs"


def _call(module: str, fn: str, *args) -> dict:
    """A JavaScript call for the runner: ``module.js``'s export *fn* on *args*."""
    return {"module": module, "fn": fn, "args": list(args)}


def _of(call: dict, index: int | None = None) -> dict:
    """An argument that is another call's result (or its *index*-th item)."""
    return {"$call": call, **({} if index is None else {"index": index})}


def _snake(value):
    """The JavaScript's result with camelCase keys as snake_case, to compare with Python's."""
    if isinstance(value, dict):
        return {re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", k).lower(): _snake(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_snake(v) for v in value]
    return value


def _words(fragment: str) -> str:
    """What a reader gets from an HTML fragment: its text, entities decoded, whitespace collapsed."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


# ------------------------------------------------------------------ inputs

# The 2-7A shape (static_pages_test's outcome-card case): every kind of outcome card.
OUTCOME_TEAMS = [
    {"school": "Oxford", "clinched": True, "odds": _odds(1, 0, 0, 0),
     "paths": [_seed(1, UNCONDITIONAL), _playoffs(UNCONDITIONAL)]},
    {"school": "Starkville", "clinched": True, "odds": _odds(0, 0, 0.5, 0.5),
     "paths": [_seed(3, _cond("Clinton", "MC")), _seed(4, _cond("MC", "Clinton")), _playoffs(UNCONDITIONAL)]},
    {"school": "MC", "odds": _odds(0, 0, 0.5, 0.146, [0, 0, 0.6, 0.2]),
     "paths": [_seed(3, _cond("MC", "Clinton")), _seed(4, _cond("Clinton", "MC")), _playoffs(_cond("MC", "Clinton"))]},
    {"school": "Clinton", "odds": _odds(0, 0, 0, 0.354),
     "paths": [_seed(4, _cond("Clinton", "MC")), _playoffs(_cond("Clinton", "MC"))]},
    {"school": "Murrah", "eliminated": True, "odds": _odds(0, 0, 0, 0),
     "paths": [{"outcome": {"type": "eliminated"}, "conditions": UNCONDITIONAL}]},
]  # fmt: skip


# Complete scenarios: margins and a coin flip (Stringer), OR groups with a tiebreaker decision and a
# tie left open, one that straddles the playoff line, shared conditions said once, and a comparison of
# two games' margins.
def _win(w, l, lo=1, hi=None):
    """A stored game-result condition: *w* beats *l* by *lo* to *hi* (no upper bound when None)."""
    return {"type": "game_result", "winner": w, "loser": l, "min_margin": lo, "max_margin": hi}


_DECISION = {"type": "tiebreak_decision", "description": "Point differential in games among A, B and C: A best"}
_COMPARISON = {"type": "margin_condition", "add": [["C", "D"]], "sub": [["A", "B"]], "op": ">=", "threshold": 3,
               "description": "C wins by at least 3 more points than A (a margin over 12 counts as 12)"}  # fmt: skip
SCENARIOS = [
    STRINGER,
    {"scenario_num": 1, "sub_label": "a", "title": "", "game_winners": [{"winner": "A", "loser": "B"}],
     "condition_groups": [[_win("A", "B", 1, 8)], [_win("A", "B"), _DECISION]],
     "outcomes": {"A": "1", "B": "2", "C": "3", "D": "4", "E": "5"},
     "open_groups": [{"step": 5, "teams": ["B", "C", "D"], "description": "..."}]},
    {"scenario_num": 2, "sub_label": "", "title": "A beats B", "game_winners": [{"winner": "A", "loser": "B"}],
     "outcomes": {"A": "1", "B": "2", "C": "3", "D": "4", "E": "5"},
     "open_groups": [{"step": 3, "teams": ["D", "E"], "description": "..."}]},
    {"scenario_num": 3, "sub_label": "a", "title": "", "game_winners": [],
     "condition_groups": [[_win("A", "B"), _win("C", "D", 1, 8)], [_win("A", "B"), _win("C", "D", 10)]],
     "outcomes": {"A": "1", "B": "2", "C": "3", "D": "4"}, "p": 0.25, "p_weighted": 0.3},
    {"scenario_num": 4, "sub_label": "b", "title": "", "game_winners": [],
     "conditions": [_win("A", "B", 1, 4), _win("C", "D"), _COMPARISON],
     "outcomes": {"C": "1", "A": "2", "B": "3", "D": "4"}},
]  # fmt: skip

EXPLANATION = [
    {
        "teams": ["B", "C"],
        "places": [2, 3],
        "when": [[{"winner": "A", "loser": "B"}]],
        "steps": ["Head-to-head: B beat C.", "B finishes 2nd."],
    },
    {
        "teams": ["A", "B", "C"],
        "places": [1, 2, 3],
        "when": [
            [{"winner": "C", "loser": "D", "min_margin": 1, "max_margin": None},
             {"winner": "A", "loser": "B", "min_margin": 12, "max_margin": None}],
            [{"winner": "A", "loser": "B", "min_margin": 1, "max_margin": 12},
             {"winner": "D", "loser": "C", "min_margin": 5, "max_margin": 6}],
        ],
        "steps": ["Point differential in their games against each other, capped at 12 a game: A 0, B 0, C 0."],
    },
]  # fmt: skip

CONDITION = {"type": "game_result", "school": "Mize", "opponent": "Raleigh", "required_result": "win", "min_margin": 8}
SCENARIO_CARD = {"title": "Mize clinches the region", "team": "Mize", "p": 0.25, "groups": [[CONDITION]]}

BADGE_TEAMS = [
    {**TEAMS[0], "clinched": True, "odds": _odds(1, 0, 0, 0)},
    {**TEAMS[0], "clinched": True, "odds": _odds(0, 0.5, 0.5, 0)},
    {**TEAMS[0], "eliminated": True, "odds": _odds(0, 0, 0, 0)},
    {**TEAMS[0], "coin_flip_needed": True},
]

NAMES = ["St. Andrew's Academy", "D'Iberville", "Jefferson Davis County High School", "Leake"]
POSITIONS = [{"region": 3, "seed": 1}, {"region": 3, "seed": 4}]
FEEDERS = [
    [{"region": 3, "seed": 1}],
    [{"region": 1, "seed": 1}, {"region": 2, "seed": 4}],
    [{"region": r, "seed": k} for r in (1, 2, 3) for k in (1, 2, 3, 4)],
    [{"region": 1, "seed": 1}, {"region": 1, "seed": 3}, {"region": 2, "seed": 2}],
]


def _result(winner, loser, w, l):
    """A played game in the bracket layout: its winner, loser and score."""
    return {"result": {"winner": {"school": winner}, "loser": {"school": loser}, "winner_score": w, "loser_score": l}}


LAYOUT = {
    "halves": {
        "N": [[_result("Raleigh", "Mize", 35, 7), {"result": None}], [_result("Raleigh", "Bay Springs", 21, 14)]]
    },
    "championship": _result("Raleigh", "Magee", 28, 27),
}
PCTS = [0, 0.001, 0.004, 0.5, 0.794, 0.996, 0.9999, 1]
DATES = ["2026-10-09", "2026-11-27", None]
MARGINS = [(1, None), (8, None), (1, 7), (3, 3), (None, 5)]


def _tree(games: list[dict]) -> dict:
    """The JavaScript's columns for *games*, both halves (what the pre-rendered page draws)."""
    return _call("bracket", "treeColumns", _of(_call("bracket", "bracketStructure", games)), ["N", "S"])


# --------------------------------------------------------------- the pairs

# (name, Python's answer, the JavaScript call, how to compare: "data" or "words")
CASES = [
    ("completeScenarioCards", sp.complete_scenario_cards(SCENARIOS), _call("scenarios", "completeScenarioCards", SCENARIOS), "data"),
    ("outcomeCards tossup", sp.outcome_cards(OUTCOME_TEAMS, "tossup"), _call("scenarios", "outcomeCards", OUTCOME_TEAMS, "tossup"), "data"),
    ("outcomeCards projected", sp.outcome_cards(OUTCOME_TEAMS, "projected"), _call("scenarios", "outcomeCards", OUTCOME_TEAMS, "projected"), "data"),
    ("insightCards", sp.insight_cards(INSIGHTS), _call("scenarios", "insightCards", INSIGHTS), "data"),
    ("whyBlocks", sp.why_blocks(EXPLANATION), _call("scenarios", "whyBlocks", EXPLANATION), "data"),
    ("tieHeading", dict(zip(("title", "teams"), sp.tie_heading(_TIE), strict=True)), _call("standings", "tieHeading", _TIE), "data"),
    ("regionComplete", sp.region_complete(TEAMS), _call("standings", "regionComplete", TEAMS), "data"),
    ("displayOrder", [t["school"] for t in cards.display_order(TEAMS)], _call("standings", "displayOrder", TEAMS), "schools"),
    ("positionLabels", cards.position_labels(cards.standing_positions(cards.display_order(TEAMS))),
     _call("standings", "positionLabels", _of(_call("standings", "standingPositions", _of(_call("standings", "displayOrder", TEAMS))))), "data"),
    *[(f"positionName {p}", sp.position_name(p["region"], p["seed"]), _call("bracket", "positionName", p), "data") for p in POSITIONS],
    *[(f"sideLabel {i}", sp.side_label(f), _call("bracket", "sideLabel", f), "data") for i, f in enumerate(FEEDERS)],
    ("occupants", sp.occupants(BRACKET[0]["side_b"], "projected"), _call("bracket", "occupants", BRACKET[0]["side_b"], "projected"), "data"),
    ("matchups", sp.game_matchups(BRACKET[0], "projected"), _call("bracket", "matchups", BRACKET[0], "projected"), "data"),
    ("layoutResults", sp.layout_results(LAYOUT), _call("bracket", "layoutResults", LAYOUT), "data"),
    ("treeColumns", [[(g["game"]["id"], g["feeders"]) for g in c["games"]] for c in sp.tree_columns(BRACKET)], _tree(BRACKET), "columns"),
    ("roundPicks", sp.round_picks(sp.tree_columns(_REGION_6)[0], "projected", {}),
     _call("bracket", "roundPicks", _of(_tree(_REGION_6), 0), "projected", {}), "data"),
    *[(f"formatPct {p}", cards.format_pct(p), _call("format", "formatPct", p), "data") for p in PCTS],
    *[(f"oddsBucket {p}", cards.odds_bucket(p), _call("format", "oddsBucket", p), "data") for p in PCTS],
    *[(f"initials {n}", sp.initials(n), _call("format", "initials", n), "data") for n in NAMES],
    *[(f"slugify {n}", cards.slugify(n), _call("routes", "slugify", n), "data") for n in NAMES],
    *[(f"gameDate {d}", sp.game_date(d), _call("format", "gameDate", d), "data") for d in DATES],
    *[(f"marginText {m}", sp.margin_text(*m), _call("format", "marginText", *m), "data") for m in MARGINS],
    ("joinNames", [sp.join_names(n) for n in (["A"], ["A", "B"], ["A", "B", "C"])],
     [_call("format", "joinNames", n) for n in (["A"], ["A", "B"], ["A", "B", "C"])], "each"),
    ("recordText", [cards.record_text(3, 1, 0), cards.record_text(2, 2, 1)],
     [_call("format", "recordText", 3, 1, 0), _call("format", "recordText", 2, 2, 1)], "each"),
    ("conditionChip", sp.condition_chip(CONDITION, {}), _call("components", "conditionChip", CONDITION, {}), "words"),
    ("conditionGroups", sp.condition_groups([[CONDITION], [CONDITION]], {}), _call("components", "conditionGroups", [[CONDITION], [CONDITION]], {}), "words"),
    ("scenarioCard", sp.scenario_card(SCENARIO_CARD, {}),
     _call("components", "scenarioCard", {**SCENARIO_CARD, "team": None, "teams": {}}), "words"),
    *[(f"outcomeScenarioCard {i}", sp.outcome_scenario_card({**c, "why": []}, {}, c.get("p")),
       _call("components", "outcomeScenarioCard", {**c, "why": []}, {}, {"p": c.get("p")}), "words")
      for i, c in enumerate(sp.complete_scenario_cards(SCENARIOS))],
    # The pre-rendered card folds its explanation into a <details> under "Explanation"; the app opens it in a sheet.
    ("whyTies", sp.why_this_order(sp.why_blocks(EXPLANATION)).replace("Explanation", "", 1),
     _call("components", "whyTies", _of(_call("scenarios", "whyBlocks", EXPLANATION))), "words"),
    *[(f"statusBadges {i}", sp._badge(t, 3, True), _call("components", "statusBadges", t, {"regionComplete": True, "clazz": 3}), "words")
      for i, t in enumerate(BADGE_TEAMS)],
    *[(f"tableMode {m}", sp.table_mode(m), _call("components", "tableMode", m), "html") for m in ("projected", "tossup")],
    ("genericHelmet", sp.generic_helmet("#112233", "#445566"), _call("components", "genericHelmet", {"shell": "#112233", "stripe": "#445566"}), "html"),
    ("trophyIcon", sp.trophy_icon(), _call("components", "trophyIcon"), "html"),
    *[(f"championBanner {i}", sp.champion_banner(2025, 3, r, {}),
       _call("components", "championBanner", 2025, 3,
             {"winner": r["winner"], "loser": r.get("loser"), "winnerScore": r.get("winner_score"), "loserScore": r.get("loser_score")}, {}),
       "words")
      for i, r in enumerate(({"winner": "Raleigh", "loser": "Noxubee County", "winner_score": 12, "loser_score": 6},
                             {"winner": "Raleigh", "loser": "Noxubee County"}))],
    ("classGrid", sp.class_grid(), _call("landing", "classGrid"), "html"),
    *[(f"hosting {p}", sp._hosting(p), _call("bracket", "hosting", p), "host") for p in (None, 0, 0.001, 0.4, 0.9999, 1 - 1e-12, 1)],
    # bracket.js's hosting rules against bracket_home_odds.py's, every way they can differ.
    *[(f"{fn} {x} {y} {season}", "x" if rule(*x, *y, season) == x else "y",
       _call("bracket", fn, {"region": x[0], "seed": x[1]}, {"region": y[0], "seed": y[1]}, season), "data")
      for fn, rule in (("secondRoundHost", odds.r2_home_team), ("semifinalHost", odds.sf_home_team))
      for x, y in HOST_PAIRS for season in (2025, 2026)],
    *[(f"quarterfinalHost {x} {hx} {y} {hy} {season}",
       "x" if odds.qf_home_team(x[0], x[1], hx >= 1, hx >= 2, y[0], y[1], hy >= 1, hy >= 2, season) == x else "y",
       _call("bracket", "quarterfinalHost", {"region": x[0], "seed": x[1]}, hx, {"region": y[0], "seed": y[1]}, hy, season), "data")
      for x, y in HOST_PAIRS for hx in (0, 1, 2) for hy in (0, 1, 2) for season in (2025, 2026)],
]  # fmt: skip


@pytest.fixture(scope="module")
def js_answers() -> dict[str, object]:
    """Every case's JavaScript answer, from one Node run."""
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("Node is needed for the renderer parity tests (CI sets it up before the Python tests)")
        pytest.skip("Node isn't installed; CI runs these")
    flat = []
    for _, _, js, _ in CASES:
        flat.extend(js if isinstance(js, list) else [js])
    out = subprocess.run([node, str(RUNNER)], input=json.dumps(flat), capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr
    results = iter(json.loads(out.stdout))
    return {name: [next(results) for _ in js] if isinstance(js, list) else next(results) for name, _, js, _ in CASES}


@pytest.mark.parametrize(("name", "python", "how"), [(n, p, h) for n, p, _, h in CASES], ids=[c[0] for c in CASES])
def test_python_and_javascript_agree(js_answers, name, python, how):
    """The pre-renderer's answer is the app's answer."""
    js = js_answers[name]
    if how == "words":
        assert _words(python) == _words(js)
    elif how == "html":
        assert python == js
    elif how == "host":
        assert python == js["host"]
    elif how == "schools":
        assert python == [t["school"] for t in js]
    elif how == "columns":
        assert json.loads(json.dumps(python)) == [[[g["game"]["id"], g["feeders"]] for g in c["games"]] for c in js]
    else:
        assert _snake(json.loads(json.dumps(python))) == _snake(js)


# ------------------------------------------------- app.js's own sentences
# app.js draws the pages and touches the document as it loads, so it can't run under Node like the
# modules above. Its fixed wording that the pre-rendered pages repeat is checked as text instead:
# each sentence (or label table) must be in both app.js and what static_pages.py draws.

APP_JS = (ROOT / "nginx" / "html" / "static" / "js" / "app.js").read_text()


def _drawn() -> str:
    """Everything the pre-renderer draws for the test region, class, bracket and front page, as words."""
    from backend.tests.unit.static_pages_test import BRACKET_CTX, STAMP, _far_out, _region

    ties = [{**_TIE, "teams": ["A", "B"], "records": ["2-0", "1-0"], "places": [1, 2]}]
    bye = {**BRACKET[2], "side_b": {**BRACKET[2]["side_b"], "occupants": [], "bye": True}, "matchups": []}
    parts = [
        sp.region_body(3, 6, _region(remaining_games=[], tiebreaks=ties), STAMP, "projected", {}),
        sp.region_body(3, 6, _region(), STAMP, "projected", {}),
        sp.bracket_body(3, BRACKET, BRACKET_CTX, STAMP),
        sp.bracket_body(3, BRACKET, {**BRACKET_CTX, "seeds": {}}, STAMP),  # a locked team without its seed
        sp.insight_preview({**_far_out(), "clazz": 3, "region": 6}, {}),
        sp._sheet(BRACKET[0], BRACKET_CTX),
        sp._sheet(bye, BRACKET_CTX),
        sp._tree_card(bye, BRACKET_CTX, False),
        sp.landing_body(None, {}),
    ]
    return _words(" ".join(parts))


SHARED_SENTENCES = [
    "How the ties were broken",
    "The MHSAA region tiebreakers, step by step, with the actual results.",
    "How the tiebreakers work",
    "Full scenarios appear once five or fewer region games remain;",
    "Until then, these are results that settle a spot no matter what else happens.",
    "Select a game to see all possible matchups and locations, and pick a team to follow its path.",
    sp.TABLE_HINT,
    "Clinched a playoff spot",
    "Locked in: ",
    "More on how the odds work",
    "BYE",
    "gets a bye.",
]


@pytest.mark.parametrize("sentence", SHARED_SENTENCES)
def test_app_js_and_the_pre_renderer_say_the_same_sentence(sentence):
    """A sentence both draw is word for word the same in each."""
    assert sentence in APP_JS
    assert _words(sentence) in _drawn()


def test_app_js_labels_match_the_pre_renderers():
    """The odds columns' labels and the bracket's round, half and state names are the same tables."""
    for key, label, full in sp.ODDS_COLUMNS:
        assert re.search(rf'key: "{key}", label: "{re.escape(label)}",.*full: "{re.escape(full)}"', APP_JS), key
    for table, name in (
        (sp.ROUND_SHORT, "ROUND_SHORT"),
        (sp.HALF_NAMES, "HALF_NAMES"),
        (sp.STATE_LABEL, "STATE_LABEL"),
    ):
        js = re.search(rf"const {name} = \{{(.*?)\}};", APP_JS).group(1)
        pairs = {k.strip(): v for k, v in re.findall(r'"?([\w ]+?)"?: "([^"]*)"', js)}
        assert pairs == table, name
