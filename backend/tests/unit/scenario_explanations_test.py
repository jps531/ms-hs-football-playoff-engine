"""Each scenario card's "why this order": for every result a card covers, the explanations whose
conditions hold are exactly the explanation of that result, worked out on its own.

A card's explanation is worked out once per set of winners and labelled with the results that
pick it out among the card's sets of winners (``when``). These checks don't take that on trust:
they walk every winner and margin, find the cards each result is covered by (as the coverage
checks do), explain the result from scratch at its own margins, and compare.
"""

from itertools import product

import pytest

from backend.helpers.data_classes import TiebreakDecision
from backend.helpers.tiebreak_explainer import explain_scenario_ties
from backend.helpers.tiebreakers import resolve_standings_for_mask
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025
from backend.tests.scenario_coverage import MARGINS, _matches
from backend.tests.unit.scenario_coverage_test import _cut, _scenarios


def _holds(entry: dict, mask: int, remaining) -> bool:
    """True when the explanation's ``when`` holds for this set of winners (empty: always)."""
    if not entry["when"]:
        return True
    index = {(g.a, g.b): i for i, g in enumerate(remaining)}

    def won(w, l):
        """True when *w* beat *l* in this set of winners."""
        i = index.get((w, l), index.get((l, w)))
        return (mask >> i & 1) == (1 if (w, l) in index else 0)

    return any(all(won(w, l) for w, l in cube) for cube in entry["when"])


def _key(teams, places, steps) -> tuple:
    """An explanation's identity: its teams, places and steps."""
    return frozenset(teams), tuple(places), tuple(steps)


def check(key, left, *, step: int = 1):
    """Every result (every *step*-th margin combination) of *key* with *left* games left."""
    teams, completed, remaining = _cut(REGION_RESULTS_2025[key]["games"], left)
    scenarios = _scenarios(teams, completed, remaining)
    pairs = [(g.a, g.b) for g in remaining]
    checked = 0
    for mask in range(1 << len(pairs)):
        for n, combo in enumerate(product(MARGINS, repeat=len(pairs))):
            if n % step:
                continue
            margins = dict(zip(pairs, combo, strict=True))
            raw: list = []
            resolve_standings_for_mask(teams, completed, remaining, mask, margins, decision_collector=raw)
            decisions = {TiebreakDecision(s, g, p) for s, g, p in raw}
            want = {
                _key(t.teams, t.places, t.steps)
                for t in explain_scenario_ties(teams, completed, remaining, mask, margins)
            }
            for sc in scenarios:
                if not _matches(sc, mask, margins, remaining, decisions):
                    continue
                got = {
                    _key(e["teams"], e["places"], e["steps"]) for e in sc["explanation"] if _holds(e, mask, remaining)
                }
                assert got == want, (key, left, mask, combo, sc["scenario_num"], sc["sub_label"])
                checked += 1
    return checked


@pytest.mark.parametrize("key", sorted(REGION_RESULTS_2025))
def test_two_games_left_every_margin(key):
    """Every 2025 region with two games left, every winner and margin."""
    assert check(key, 2) > 0


@pytest.mark.parametrize("key", sorted(REGION_RESULTS_2025)[::5])
def test_three_games_left_sampled_margins(key):
    """Every fifth 2025 region with three games left, one margin combination in 7."""
    assert check(key, 3, step=7) > 0


def test_no_explanations_where_margins_are_ignored():
    """With margins ignored (more than five games left), a step that turns on one could be explained
    wrongly, so those scenarios carry no explanation; they aren't shown then anyway."""
    from backend.helpers.scenario_viewer import enumerate_division_scenarios, enumerate_outcomes

    key = sorted(REGION_RESULTS_2025)[0]
    teams, completed, remaining = _cut(REGION_RESULTS_2025[key]["games"], 3)
    exact = enumerate_division_scenarios(teams, completed, remaining)
    assert all("explanation" in sc for sc in exact)
    pre = enumerate_outcomes(teams, completed, remaining, ignore_margins=True)
    assert not any("explanation" in sc for sc in enumerate_division_scenarios(teams, completed, remaining, precomputed=pre))
