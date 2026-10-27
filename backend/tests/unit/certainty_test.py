"""0% and 100% (and clinched and eliminated) only for certainties, in both odds modes."""

from itertools import combinations

import pytest

from backend.api.models.responses import BracketAdvancementOdds, HomeGameOdds
from backend.helpers.certainty import (
    CERTAIN_EPS,
    UNCERTAIN_FLOOR,
    is_certain,
    is_impossible,
    keep_uncertain,
    settle,
    settle_pair,
)
from backend.helpers.data_classes import RemainingGame
from backend.helpers.scenarios import determine_odds, determine_scenarios, odds_from_results
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025
from backend.tests.unit.scenario_coverage_test import _cut


def _fields(o):
    return (o.p1, o.p2, o.p3, o.p4, o.p_playoffs)


def _honest(p):
    """Exactly 0 or 1, or at least the floor away from both."""
    return p in (0.0, 1.0) or UNCERTAIN_FLOOR <= p <= 1 - UNCERTAIN_FLOOR


class TestHelpers:
    def test_floor_is_far_outside_the_cutoff(self):
        """Every reader's cutoff sits well inside the floor, so a kept-uncertain chance never reads as certain."""
        assert CERTAIN_EPS < UNCERTAIN_FLOOR
        assert not is_certain(1 - UNCERTAIN_FLOOR) and not is_impossible(UNCERTAIN_FLOOR)

    def test_keep_uncertain(self):
        assert keep_uncertain(0.0) == UNCERTAIN_FLOOR
        assert keep_uncertain(1.0) == 1 - UNCERTAIN_FLOOR
        assert keep_uncertain(0.3) == 0.3

    def test_settle_snaps_float_noise_and_keeps_the_rest(self):
        assert settle(1e-15) == 0.0
        assert settle(0.9999999999999998) == 1.0
        assert settle(1e-10) == UNCERTAIN_FLOOR
        assert settle(1 - 1e-10) == 1 - UNCERTAIN_FLOOR

    def test_projected_follows_tossup_certainty(self):
        """A Projected chance is certain exactly when its Toss-up twin is, however lopsided the games."""
        assert settle_pair(1.0, 0.97) == (1.0, 1.0)
        assert settle_pair(0.0, 1e-3) == (0.0, 0.0)
        assert settle_pair(0.5, 1e-30) == (0.5, UNCERTAIN_FLOOR)
        assert settle_pair(0.5, None) == (0.5, None)


class TestDetermineOdds:
    def test_tiny_real_chance_is_not_zero(self):
        """A seed some ending gives, with a share smaller than any rounding keeps, isn't 0%."""
        counts = ({"A": 1.0 - 1e-20, "B": 1e-20}, {"A": 1e-20, "B": 1.0 - 1e-20}, {}, {})
        odds = determine_odds(["A", "B"], *counts, 1.0, places_seen={"A": {1, 2}, "B": {1, 2}})
        assert odds["B"].p1 == UNCERTAIN_FLOOR
        assert odds["A"].p1 == 1 - UNCERTAIN_FLOOR
        assert odds["A"].clinched and odds["B"].clinched  # both always in the top four

    def test_counts_alone_keep_tiny_chances(self):
        """Without the places, a count of 0 is the only 0%: a tiny share still reads as possible."""
        odds = determine_odds(["A", "B"], {"A": 1.0, "B": 1e-20}, {"B": 1.0}, {}, {}, 1.0)
        assert odds["B"].p1 == UNCERTAIN_FLOOR and odds["A"].p1 == 1.0

    def test_only_place_is_certain(self):
        counts = ({"A": 0.5, "B": 0.5}, {"A": 0.5, "B": 0.5}, {"C": 1.0}, {})
        seen = {"A": {1, 2}, "B": {1, 2}, "C": {3}, "D": {5}}
        odds = determine_odds(["A", "B", "C", "D"], *counts, 1.0, places_seen=seen)
        assert odds["C"].p3 == 1.0
        assert odds["D"].eliminated and odds["D"].p_playoffs == 0.0

    def test_playoff_spot_one_ending_misses_is_not_certain(self):
        """However close to 1 the sum, a team some ending leaves out hasn't clinched."""
        counts = ({"A": 1.0 - 1e-15}, {}, {}, {})
        odds = determine_odds(["A", "B"], *counts, 1.0, places_seen={"A": {1, 5}, "B": {1, 5}})
        assert not odds["A"].clinched
        assert odds["A"].p_playoffs == 1 - UNCERTAIN_FLOOR

    def test_sampled_odds_are_never_certain(self):
        counts = ({"A": 1.0}, {"B": 1.0}, {"C": 1.0}, {"D": 1.0})
        odds = determine_odds(["A", "B", "C", "D", "E"], *counts, 1.0, sampled=True)
        for o in odds.values():
            assert not o.clinched and not o.eliminated
            assert all(UNCERTAIN_FLOOR <= p <= 1 - UNCERTAIN_FLOOR for p in _fields(o))


def _round_robin(teams):
    return [RemainingGame(a, b) for a, b in combinations(sorted(teams), 2)]


class TestDetermineScenarios:
    def test_four_team_region_everyone_clinched(self):
        """Four teams, four spots: every team is in whatever happens, in both modes."""
        teams = ["A", "B", "C", "D"]
        r = determine_scenarios(teams, [], _round_robin(teams), win_prob_fn=lambda a, b, d, loc: 0.9, ignore_margins=True)
        odds, odds_w = odds_from_results(teams, r)
        assert all(5 not in seen for seen in r.places_seen.values()) and not r.sampled
        for t in teams:
            assert odds[t].clinched and odds_w[t].clinched
            assert odds[t].p_playoffs == 1.0 and odds_w[t].p_playoffs == 1.0

    def test_lopsided_projected_chance_is_kept(self):
        """A heavy underdog in every game: its Projected chance of #1 is tiny but possible, so not 0%."""
        teams = ["A", "B", "C", "D", "E"]

        def win_prob(a, b, d, loc):
            return 1e-6 if a == "A" else (1 - 1e-6 if b == "A" else 0.5)

        r = determine_scenarios(teams, [], _round_robin(teams), win_prob_fn=win_prob, ignore_margins=True)
        odds, odds_w = odds_from_results(teams, r)
        assert 0.0 < odds["A"].p1 < 1.0
        assert odds_w["A"].p1 >= UNCERTAIN_FLOOR
        assert not odds_w["A"].eliminated

    def test_sampling_proves_nothing(self):
        teams = ["A", "B", "C", "D", "E"]
        r = determine_scenarios(teams, [], _round_robin(teams), n_samples=50)
        assert r.sampled
        odds, odds_w = odds_from_results(teams, r)
        for o in (*odds.values(), *odds_w.values()):
            assert not o.clinched and not o.eliminated

    @pytest.mark.parametrize("key", sorted(REGION_RESULTS_2025)[:12])
    def test_real_regions_flags_match_the_endings(self, key):
        """2025 regions with three games left: clinched exactly when no ending leaves the team out, every
        chance 0, 1 or kept uncertain, and the two modes certain together."""
        teams, completed, remaining = _cut(REGION_RESULTS_2025[key]["games"], 3)
        r = determine_scenarios(teams, completed, remaining, win_prob_fn=lambda a, b, d, loc: 0.8)
        odds, odds_w = odds_from_results(teams, r)
        for t in teams:
            assert odds[t].clinched == (5 not in r.places_seen[t])
            for p, pw in zip(_fields(odds[t]), _fields(odds_w[t])):
                assert _honest(p) and _honest(pw)
                assert (p in (0.0, 1.0)) == (pw in (0.0, 1.0)) and (p == pw or p not in (0.0, 1.0))


class TestResponseModels:
    def test_bracket_odds_settle_on_demand_values(self):
        b = BracketAdvancementOdds(
            second_round=0.9999999999999998,
            quarterfinals=0.0,
            semifinals=0.25,
            finals=0.1,
            champion=1e-9,
            second_round_weighted=0.99,
            quarterfinals_weighted=0.0,
            semifinals_weighted=1e-14,
            finals_weighted=0.2,
            champion_weighted=1e-15,
        )
        assert (b.second_round, b.second_round_weighted) == (1.0, 1.0)
        assert (b.quarterfinals, b.quarterfinals_weighted) == (0.0, 0.0)
        assert b.semifinals_weighted == UNCERTAIN_FLOOR
        assert (b.champion, b.champion_weighted) == (UNCERTAIN_FLOOR, UNCERTAIN_FLOOR)

    def test_home_odds_stored_values_pass_through(self):
        values = dict(first_round=1.0, second_round=0.0, quarterfinals=0.4, semifinals=UNCERTAIN_FLOOR)
        h = HomeGameOdds(**values, **{f"{k}_weighted": v for k, v in values.items()})
        assert h.model_dump() == {**values, **{f"{k}_weighted": v for k, v in values.items()}}


def test_site_reads_with_the_same_cutoff():
    """format.js's EPS is CERTAIN_EPS, so the browser and the server agree on what reads as certain."""
    import re
    from pathlib import Path

    js = (Path(__file__).parents[3] / "nginx/html/static/js/format.js").read_text()
    assert float(re.search(r"export const EPS = ([0-9.e-]+);", js).group(1)) == CERTAIN_EPS


@pytest.mark.parametrize("key", sorted(REGION_RESULTS_2025))
def test_seven_point_shortcut_never_claims_a_certainty_margins_break(key):
    """Past five games left every game is scored at 7 points, so a tie on point differential is left
    open: every place a team can take with all margins worked through is still open to it, and a team
    the full enumeration doesn't call clinched or eliminated isn't called that either. (Without the
    widening, 2025's 6A Region 3 had Forest Hill eliminated at three games left when it wasn't.)"""
    teams, completed, remaining = _cut(REGION_RESULTS_2025[key]["games"], 3)
    full = determine_scenarios(teams, completed, remaining)
    fast = determine_scenarios(teams, completed, remaining, ignore_margins=True)
    fast_odds, _ = odds_from_results(teams, fast)
    full_odds, _ = odds_from_results(teams, full)
    for t in teams:
        assert full.places_seen[t] <= fast.places_seen[t]
        assert not fast_odds[t].clinched or full_odds[t].clinched
        assert not fast_odds[t].eliminated or full_odds[t].eliminated
