"""Each complete scenario carries the chance of its finish, and those chances add up the way the odds do."""

import random
from collections import defaultdict

import pytest

from backend.api.models.responses import ScenarioEntry
from backend.helpers.api_helpers import scenarios_to_entries
from backend.helpers.scenario_serializers import deserialize_complete_scenarios, serialize_complete_scenarios
from backend.helpers.scenario_viewer import enumerate_division_scenarios
from backend.helpers.scenarios import determine_scenarios
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025
from backend.tests.unit.scenario_coverage_test import _cut


def _finishes(scenarios):
    """{finish: (p, p_weighted)}, checking every scenario of one finish carries the same chance."""
    out = {}
    for s in scenarios:
        key = (tuple(s["seeding"]), repr(s["open_groups"]), repr(sorted((s["open_places"] or {}).items())))
        assert out.setdefault(key, (s["p"], s["p_weighted"])) == (s["p"], s["p_weighted"])
    return out


def _cases():
    for (clazz, region), fixture in sorted(REGION_RESULTS_2025.items()):
        for left in (1, 2):
            if len(fixture["games"]) > left:
                yield pytest.param(clazz, region, left, id=f"{clazz}A-{region}-{left}left")


@pytest.mark.parametrize(("clazz", "region", "left"), list(_cases()))
def test_finish_odds_add_up_and_match_the_region_odds_2025(clazz, region, left):
    """The finishes' chances add to 1 in both modes; with no tie left open, each team's chance of #1
    read off them is the region's odds exactly."""
    teams, completed, remaining = _cut(REGION_RESULTS_2025[(clazz, region)]["games"], left)
    rng = random.Random(clazz * 100 + region * 10 + left)
    probs = [rng.uniform(0.1, 0.9) for _ in remaining]
    scenarios = enumerate_division_scenarios(teams, completed, remaining, scenario_odds=True, win_probs=probs)
    finishes = _finishes(scenarios)
    assert sum(p for p, _ in finishes.values()) == pytest.approx(1, abs=1e-9)
    assert sum(w for _, w in finishes.values()) == pytest.approx(1, abs=1e-9)
    if any(s["open_groups"] for s in scenarios):
        return
    by_pair = {(g.a, g.b): p for g, p in zip(remaining, probs, strict=True)}

    def win_prob(a, b, _date, _loc):
        """P(a beats b), from *probs*."""
        return by_pair[(a, b)] if (a, b) in by_pair else 1 - by_pair[(b, a)]

    odds = determine_scenarios(teams, completed, remaining, win_prob_fn=win_prob)
    first = [defaultdict(float), defaultdict(float)]
    for (seeding, _, _), (p, w) in finishes.items():
        first[0][seeding[0]] += p
        first[1][seeding[0]] += w
    for team in teams:
        assert first[0][team] == pytest.approx(odds.first_counts[team] / odds.denom, abs=1e-9)
        assert first[1][team] == pytest.approx(odds.first_counts_weighted[team] / odds.denom_weighted, abs=1e-9)


def test_scenarios_without_odds_carry_none():
    """Callers that don't ask (team paths) get no odds, and pay nothing for them."""
    teams, completed, remaining = _cut(REGION_RESULTS_2025[(7, 2)]["games"], 2)
    assert all("p" not in s for s in enumerate_division_scenarios(teams, completed, remaining))


def test_a_finish_reached_two_ways_shares_its_chance():
    """7A-2 with two left: Clinton beating Madison Central and Starkville beating Oxford, or Clinton
    winning by 8 or more, reach the same standings. Both scenarios carry that finish's whole chance."""
    teams, completed, remaining = _cut(REGION_RESULTS_2025[(7, 2)]["games"], 2)
    scenarios = enumerate_division_scenarios(teams, completed, remaining, scenario_odds=True)
    same = [s for s in scenarios if s["seeding"][:4] == ("Oxford", "Germantown", "Starkville", "Clinton")]
    assert len(same) == 2 and same[0]["p"] == same[1]["p"] == same[0]["p_weighted"]
    assert sum(p for p, _ in _finishes(scenarios).values()) == pytest.approx(1)


def test_odds_are_stored_and_served():
    """The finish's chance survives storage and reaches the API's scenario entries."""
    teams, completed, remaining = _cut(REGION_RESULTS_2025[(7, 2)]["games"], 2)
    scenarios = enumerate_division_scenarios(teams, completed, remaining, scenario_odds=True, win_probs=[0.7, 0.4])
    stored = deserialize_complete_scenarios(serialize_complete_scenarios(scenarios))
    assert [(s["p"], s["p_weighted"]) for s in stored] == [(s["p"], s["p_weighted"]) for s in scenarios]
    entries = scenarios_to_entries(stored)
    assert [(e.p, e.p_weighted) for e in entries] == [(s["p"], s["p_weighted"]) for s in scenarios]
    old = serialize_complete_scenarios(enumerate_division_scenarios(teams, completed, remaining))
    assert all(e.p is None for e in scenarios_to_entries(deserialize_complete_scenarios(old)))
    assert ScenarioEntry.model_fields["p"].default is None


def test_odds_count_every_margin_a_tied_team_plays():
    """2A-4 (2025) with four left: a tied team's games against the rest of the region decide step 4,
    with no game left among the tied teams themselves. The odds used to work through margins only
    when such a game remained, putting East Webster at 58.1% for #1; every result and margin gives
    61.2%, as the finishes do. (60.3% before steps 2 and 4 stopped at the first outside team that
    separates the tied teams: going on down the list gave the #1 seed to the wrong team in some
    margins.)"""
    teams, completed, remaining = _cut(REGION_RESULTS_2025[(2, 4)]["games"], 4)
    r = determine_scenarios(teams, completed, remaining)
    assert r.first_counts["East Webster"] / r.denom == pytest.approx(0.612081, abs=1e-6)
    assert r.first_counts["Kemper County"] / r.denom == pytest.approx(0.137919, abs=1e-6)
    finishes = _finishes(enumerate_division_scenarios(teams, completed, remaining, scenario_odds=True))
    first = defaultdict(float)
    for (seeding, _, _), (p, _) in finishes.items():
        first[seeding[0]] += p
    for team in teams:
        assert first[team] == pytest.approx(r.first_counts[team] / r.denom, abs=1e-9)
