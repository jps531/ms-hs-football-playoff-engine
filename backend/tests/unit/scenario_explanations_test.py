"""Each scenario card's "why this order": for every result a card covers, the explanations whose
conditions hold are exactly the ties of that result, and each says what the tiebreaker did there.

A card's explanation is worked out over many results at once (those with the same winners where
the tiebreaker takes the same steps, a number that varies over them stated as a range) and
labelled with the results that pick it out (``when``, margins included). These checks don't take
that on trust: they walk every winner and margin, find the cards each result is covered by (as
the coverage checks do), run the tiebreaker on the result itself, and check that the explanations
whose ``when`` holds are its ties. Then, for each explanation, the results it was found to apply
to are explained again from scratch, together, as each set of winners and steps: the words must
come out the same, so every range stated is exactly the least and greatest over those results.
"""

from collections import defaultdict
from itertools import product

import pytest

from backend.helpers.data_classes import TiebreakDecision
from backend.helpers.tiebreak_explainer import MergedTrace, scenario_trace
from backend.helpers.tiebreakers import resolve_standings_for_mask
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025
from backend.tests.scenario_coverage import MARGINS, _matches
from backend.tests.unit.scenario_coverage_test import _cut, _scenarios


def _holds(entry: dict, mask: int, margins: dict, remaining) -> bool:
    """True when the explanation's ``when`` holds for this result (empty: always). A condition is
    [winner, loser, least margin, greatest margin + 1 or None]; older snapshots store [winner, loser]."""
    if not entry["when"]:
        return True
    index = {(g.a, g.b): i for i, g in enumerate(remaining)}

    def met(cond) -> bool:
        """True when *cond*'s winner won, by a margin in its range."""
        w, l, lo, hi = (*cond, 1, None) if len(cond) == 2 else cond
        pair = (w, l) if (w, l) in index else (l, w)
        if (mask >> index[pair] & 1) != (1 if pair == (w, l) else 0):
            return False
        m = margins[pair]
        return lo <= m and (hi is None or m < hi)

    return any(all(met(c) for c in cube) for cube in entry["when"])


def _key(teams, places, steps) -> tuple:
    """An explanation's identity: its teams, places and steps."""
    return frozenset(teams), tuple(places), tuple(steps)


def check(key, left):
    """Every result of *key* with *left* games left."""
    teams, completed, remaining = _cut(REGION_RESULTS_2025[key]["games"], left)
    scenarios = _scenarios(teams, completed, remaining)
    pairs = [(g.a, g.b) for g in remaining]
    # (explanation, winners, steps taken, ties left open) -> the results it was found to apply to.
    found: dict[tuple, MergedTrace] = {}
    checked = 0
    for mask in range(1 << len(pairs)):
        for combo in product(MARGINS, repeat=len(pairs)):
            margins = dict(zip(pairs, combo, strict=True))
            raw: list = []
            resolve_standings_for_mask(teams, completed, remaining, mask, margins, decision_collector=raw)
            decisions = {TiebreakDecision(s, g, p) for s, g, p in raw}
            run = scenario_trace(teams, completed, remaining, mask, margins)
            for sc in scenarios:
                if not _matches(sc, mask, margins, remaining, decisions):
                    continue
                left_open = tuple(tuple(g) for s, g in sc["open_groups"] or () if s <= 4)
                want = {
                    (frozenset(t.teams), t.places)
                    for t in MergedTrace(run).ties(teams, completed, remaining, mask, left_open=left_open)
                }
                got = [e for e in sc["explanation"] if _holds(e, mask, margins, remaining)]
                assert {(frozenset(e["teams"]), tuple(e["places"])) for e in got} == want, (
                    key,
                    left,
                    mask,
                    combo,
                    sc["scenario_num"],
                    sc["sub_label"],
                )
                for e in got:
                    k = (_key(e["teams"], e["places"], e["steps"]), mask, run.key, left_open)
                    if k in found:
                        found[k].add(run)
                    else:
                        found[k] = MergedTrace(run)
                checked += 1
    for (ident, mask, _, left_open), merged in found.items():
        again = {
            _key(t.teams, t.places, t.steps)
            for t in merged.ties(teams, completed, remaining, mask, left_open=left_open)
        }
        assert ident in again, (key, left, mask, ident)
    return checked


@pytest.mark.parametrize("key", sorted(REGION_RESULTS_2025))
def test_two_games_left_every_margin(key):
    """Every 2025 region with two games left, every winner and margin."""
    assert check(key, 2) > 0


@pytest.mark.parametrize("key", sorted(REGION_RESULTS_2025)[::5])
def test_three_games_left_every_margin(key):
    """Every fifth 2025 region with three games left, every winner and margin (every one, so each
    range can be checked against all the results it covers)."""
    assert check(key, 3) > 0


def test_region_8_1a_states_the_margins_its_order_turns_on():
    """Region 8-1A, two games left (Oct 24): Lumberton beating Taylorsville by 12+ with Stringer beating
    Resurrection levels all three at 0 in point differential among them, and the step after it
    decides; by 1-11, that point differential decides. Each says so with the numbers, under the
    card's own conditions."""
    teams, completed, remaining = _cut(REGION_RESULTS_2025[(1, 8)]["games"], 2)
    by_finish: dict[tuple, list] = defaultdict(list)
    for sc in _scenarios(teams, completed, remaining):
        by_finish[tuple(sc["seeding"][:4])].extend(sc["explanation"])
    three = frozenset({"Lumberton", "Stringer", "Taylorsville"})
    lumberton_first = [
        e for e in by_finish[("Lumberton", "Taylorsville", "Stringer", "Richton")] if set(e["teams"]) == three
    ]
    assert lumberton_first[0]["when"] == [
        [["Stringer", "Resurrection", 1, None], ["Lumberton", "Taylorsville", 12, None]]
    ]
    assert lumberton_first[0]["steps"][2:] == [
        "Point differential in their games against each other, capped at 12 a game: Lumberton 0, Stringer 0, "
        "Taylorsville 0 (Stringer beat Lumberton 46-20, counted as 12; Lumberton beats Taylorsville by 12+, "
        "counted as 12; Taylorsville beat Stringer 49-12, counted as 12). That doesn't separate them.",
        "Point differential against the highest-placed region teams outside the tie, capped at 12 a game, working "
        "down: against Richton: Lumberton +12, Taylorsville +12, Stringer +4. Lumberton and Taylorsville are still "
        "tied; Stringer finishes 3rd.",
        "Lumberton and Taylorsville start over at head-to-head: Lumberton beats Taylorsville. Lumberton finishes 1st; "
        "Taylorsville finishes 2nd.",
    ]
    taylorsville_first = [
        e for e in by_finish[("Taylorsville", "Stringer", "Lumberton", "Richton")] if set(e["teams"]) == three
    ]
    assert taylorsville_first[0]["when"] == [
        [["Stringer", "Resurrection", 1, None], ["Lumberton", "Taylorsville", 1, 12]]
    ]
    assert "Taylorsville +1 to +11, Stringer 0, Lumberton −11 to −1" in taylorsville_first[0]["steps"][2]


def test_a_finish_too_varied_to_label_is_explained_by_winners(monkeypatch):
    """A finish with more results than its conditions can be worked out over is explained by winners
    alone: each tie stops at the first step counting a margin still to come, and ``when`` names only
    winners. Still exact: at every result, the explanations whose ``when`` holds are its ties, in
    those words."""
    from backend.helpers import scenario_viewer

    monkeypatch.setattr(scenario_viewer, "_MAX_LABEL_POINTS", 0)
    teams, completed, remaining = _cut(REGION_RESULTS_2025[(1, 8)]["games"], 2)
    scenarios = _scenarios(teams, completed, remaining)
    pairs = [(g.a, g.b) for g in remaining]
    stops = 0
    for mask in range(1 << len(pairs)):
        for combo in product(MARGINS, repeat=len(pairs)):
            margins = dict(zip(pairs, combo, strict=True))
            raw: list = []
            resolve_standings_for_mask(teams, completed, remaining, mask, margins, decision_collector=raw)
            decisions = {TiebreakDecision(s, g, p) for s, g, p in raw}
            run = scenario_trace(teams, completed, remaining, mask, margins)
            want = {
                _key(t.teams, t.places, t.steps)
                for t in MergedTrace(run).ties(teams, completed, remaining, mask, left_open=True)
            }
            for sc in scenarios:
                if _matches(sc, mask, margins, remaining, decisions):
                    got = [e for e in sc["explanation"] if _holds(e, mask, margins, remaining)]
                    assert {_key(e["teams"], e["places"], e["steps"]) for e in got} == want, (mask, combo)
                    assert all(
                        len(c) == 4 and (c[2], c[3]) == (1, None) for e in got for cube in e["when"] for c in cube
                    )
                    stops += sum("decides it from here" in step for e in got for step in e["steps"])
    assert stops


def test_no_explanations_where_margins_are_ignored():
    """With margins ignored (more than five games left), a step that turns on one could be explained
    wrongly, so those scenarios carry no explanation; they aren't shown then anyway."""
    from backend.helpers.scenario_viewer import enumerate_division_scenarios, enumerate_outcomes

    key = sorted(REGION_RESULTS_2025)[0]
    teams, completed, remaining = _cut(REGION_RESULTS_2025[key]["games"], 3)
    exact = enumerate_division_scenarios(teams, completed, remaining)
    assert all("explanation" in sc for sc in exact)
    pre = enumerate_outcomes(teams, completed, remaining, ignore_margins=True)
    assert not any(
        "explanation" in sc for sc in enumerate_division_scenarios(teams, completed, remaining, precomputed=pre)
    )
