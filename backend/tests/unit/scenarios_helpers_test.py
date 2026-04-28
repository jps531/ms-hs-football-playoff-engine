"""Unit tests for pure helper functions in scenarios.py.

These tests require no game data — they exercise formatting utilities
and playoff probability calculators directly.
"""

import pytest

from backend.helpers.data_classes import BracketOdds, StandingsOdds
from backend.helpers.scenarios import (
    compute_bracket_odds,
    compute_first_round_home_odds,
    determine_scenarios,
    pct_str,
)
from backend.tests.data.standings_2025_3_7a import (
    expected_3_7a_completed_games_full,
    expected_3_7a_remaining_games_full,
    teams_3_7a,
)

# ---------------------------------------------------------------------------
# pct_str
# ---------------------------------------------------------------------------


class TestPctStr:
    """Tests for pct_str formatting helper."""

    def test_round_percentages(self):
        """Round percentages (0%, 25%, 50%, 100%) render without decimal noise."""
        assert pct_str(0.0) == "0%"
        assert pct_str(0.5) == "50%"
        assert pct_str(1.0) == "100%"
        assert pct_str(0.25) == "25%"

    def test_non_round_percentage(self):
        """Non-integer percentages are rounded to the nearest whole number."""
        # 1/3 → 33.333...% — takes the else branch
        result = pct_str(1 / 3)
        assert result == "33%"

    def test_non_round_two_thirds(self):
        """Two-thirds rounds up to 67%."""
        result = pct_str(2 / 3)
        assert result == "67%"


# ---------------------------------------------------------------------------
# compute_bracket_odds
# ---------------------------------------------------------------------------


def _make_odds(school: str, p_playoffs: float) -> StandingsOdds:
    """Build a minimal StandingsOdds with all probability in p_playoffs (p1=p_playoffs, rest 0)."""
    return StandingsOdds(
        school=school,
        p1=p_playoffs,
        p2=0.0,
        p3=0.0,
        p4=0.0,
        p_playoffs=p_playoffs,
        final_playoffs=p_playoffs,
        clinched=p_playoffs >= 0.999,
        eliminated=p_playoffs <= 0.001,
    )


class TestComputeBracketOdds:
    """Tests for compute_bracket_odds — converts p_playoffs into round-by-round probabilities."""

    def test_4_round_bracket_second_round_is_zero(self):
        """4-round bracket (5A–7A) has no second_round game; that field is 0."""
        # 5A–7A have 4 rounds — no second_round game
        odds = {"TeamA": _make_odds("TeamA", 1.0)}
        result = compute_bracket_odds(4, odds)
        assert result["TeamA"].second_round == pytest.approx(0.0)

    def test_5_round_bracket_second_round_nonzero(self):
        """5-round bracket (1A–4A) includes a second_round game at p * 0.5."""
        # 1A–4A have 5 rounds — second_round = p * 0.5
        odds = {"TeamA": _make_odds("TeamA", 1.0)}
        result = compute_bracket_odds(5, odds)
        assert result["TeamA"].second_round == pytest.approx(0.5)

    def test_4_round_probabilities(self):
        """4-round bracket round probabilities are correct powers of 0.5."""
        odds = {"TeamA": _make_odds("TeamA", 1.0)}
        r = compute_bracket_odds(4, odds)["TeamA"]
        assert r.quarterfinals == pytest.approx(0.5)  # 0.5^1
        assert r.semifinals == pytest.approx(0.25)  # 0.5^2
        assert r.finals == pytest.approx(0.125)  # 0.5^3
        assert r.champion == pytest.approx(0.0625)  # 0.5^4

    def test_5_round_probabilities(self):
        """5-round bracket round probabilities are correct powers of 0.5."""
        odds = {"TeamA": _make_odds("TeamA", 1.0)}
        r = compute_bracket_odds(5, odds)["TeamA"]
        assert r.second_round == pytest.approx(0.5)  # 0.5^1
        assert r.quarterfinals == pytest.approx(0.25)  # 0.5^2
        assert r.semifinals == pytest.approx(0.125)  # 0.5^3
        assert r.finals == pytest.approx(0.0625)  # 0.5^4
        assert r.champion == pytest.approx(0.03125)  # 0.5^5

    def test_scales_with_p_playoffs(self):
        """All round probabilities scale linearly with p_playoffs."""
        odds = {"TeamA": _make_odds("TeamA", 0.5)}
        r = compute_bracket_odds(4, odds)["TeamA"]
        assert r.champion == pytest.approx(0.5 * 0.0625)

    def test_returns_bracket_odds_type(self):
        """Result values are BracketOdds instances."""
        odds = {"TeamA": _make_odds("TeamA", 1.0)}
        result = compute_bracket_odds(4, odds)
        assert isinstance(result["TeamA"], BracketOdds)


# ---------------------------------------------------------------------------
# compute_first_round_home_odds
# ---------------------------------------------------------------------------


def _make_full_odds(school: str, p1: float, p2: float, p3: float, p4: float) -> StandingsOdds:
    """Build a StandingsOdds with explicit per-seed probabilities; p_playoffs is their sum."""
    p_playoffs = p1 + p2 + p3 + p4
    return StandingsOdds(
        school=school,
        p1=p1,
        p2=p2,
        p3=p3,
        p4=p4,
        p_playoffs=p_playoffs,
        final_playoffs=p_playoffs,
        clinched=p_playoffs >= 0.999,
        eliminated=p_playoffs <= 0.001,
    )


class TestComputeFirstRoundHomeOdds:
    """Tests for compute_first_round_home_odds — probability of hosting a first-round home game."""

    def test_seeds_1_and_2_are_home(self):
        """When seeds 1 and 2 are home, p_home = p1 + p2."""
        odds = {"TeamA": _make_full_odds("TeamA", 0.5, 0.3, 0.2, 0.0)}
        result = compute_first_round_home_odds(frozenset({1, 2}), odds)
        assert result["TeamA"] == pytest.approx(0.8)

    def test_only_seed_1_is_home(self):
        """When only seed 1 is home, p_home = p1."""
        odds = {"TeamA": _make_full_odds("TeamA", 0.5, 0.3, 0.2, 0.0)}
        result = compute_first_round_home_odds(frozenset({1}), odds)
        assert result["TeamA"] == pytest.approx(0.5)

    def test_no_home_seeds(self):
        """Empty home seed set yields p_home = 0 for all teams."""
        odds = {"TeamA": _make_full_odds("TeamA", 0.5, 0.3, 0.2, 0.0)}
        result = compute_first_round_home_odds(frozenset(), odds)
        assert result["TeamA"] == pytest.approx(0.0)

    def test_all_four_seeds_home(self):
        """All four seeds home → p_home = p_playoffs = 1.0."""
        odds = {"TeamA": _make_full_odds("TeamA", 0.25, 0.25, 0.25, 0.25)}
        result = compute_first_round_home_odds(frozenset({1, 2, 3, 4}), odds)
        assert result["TeamA"] == pytest.approx(1.0)

    def test_eliminated_team_zero(self):
        """Eliminated team (all seed probs 0) always has p_home = 0."""
        odds = {"TeamA": _make_full_odds("TeamA", 0.0, 0.0, 0.0, 0.0)}
        result = compute_first_round_home_odds(frozenset({1, 2}), odds)
        assert result["TeamA"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# determine_scenarios — num_remaining == 0 path
# ---------------------------------------------------------------------------


class TestDetermineScenariosFullSeason:
    """Tests for determine_scenarios when the season is already complete (R=0).

    Exercises the num_remaining == 0 branch (lines 192–212 of scenarios.py):
    a single resolve_standings_for_mask call with mask=0 and denom=1.0.
    """

    # 3-7A final standings: Oak Grove #1, Petal #2, Brandon #3, Northwest Rankin #4.
    # Meridian and Pearl are eliminated (outside top 4).

    def _result(self):
        """Run determine_scenarios on the 3-7A full-season fixture."""
        return determine_scenarios(
            teams_3_7a,
            expected_3_7a_completed_games_full,
            expected_3_7a_remaining_games_full,
        )

    def test_denom_is_one(self):
        """With no remaining games the denominator is exactly 1."""
        assert self._result().denom == pytest.approx(1.0)

    def test_each_team_has_exactly_one_seed_count(self):
        """Every team's seed counts sum to 1.0 across all four seed buckets."""
        r = self._result()
        for team in teams_3_7a:
            total = (
                r.first_counts[team]
                + r.second_counts[team]
                + r.third_counts[team]
                + r.fourth_counts[team]
            )
            # Playoff teams land in exactly one seed; eliminated teams land nowhere.
            assert total == pytest.approx(0.0) or total == pytest.approx(1.0), (
                f"{team}: seed counts sum to {total}"
            )

    def test_seed_counts_match_final_standings(self):
        """Seed counts reflect the known 3-7A final standings."""
        r = self._result()
        assert r.first_counts["Oak Grove"] == pytest.approx(1.0)
        assert r.second_counts["Petal"] == pytest.approx(1.0)
        assert r.third_counts["Brandon"] == pytest.approx(1.0)
        assert r.fourth_counts["Northwest Rankin"] == pytest.approx(1.0)

    def test_eliminated_teams_have_zero_seed_counts(self):
        """Teams outside the top 4 contribute nothing to any seed count."""
        r = self._result()
        for team in ("Meridian", "Pearl"):
            assert r.first_counts[team] == pytest.approx(0.0)
            assert r.second_counts[team] == pytest.approx(0.0)
            assert r.third_counts[team] == pytest.approx(0.0)
            assert r.fourth_counts[team] == pytest.approx(0.0)

    def test_no_coin_flips(self):
        """A fully-determined final season has no coin flip events."""
        r = self._result()
        assert r.coinflip_teams == set()


# ---------------------------------------------------------------------------
# Monte Carlo sampling path
# ---------------------------------------------------------------------------


class TestDetermineScenariosMonteCarlo:
    """Tests for the n_samples Monte Carlo path in determine_scenarios."""

    TEAMS = ["A", "B", "C", "D", "E", "F", "G"]

    def _make_remaining(self):
        """Build C(7,2)=21 round-robin remaining games for 7 teams."""
        from backend.helpers.data_classes import RemainingGame

        games = []
        for i, a in enumerate(self.TEAMS):
            for b in self.TEAMS[i + 1 :]:
                games.append(RemainingGame(a=a, b=b))
        return games

    def _run(self, n_samples: int = 2_000):
        """Run determine_scenarios with all remaining games and return the result."""
        remaining = self._make_remaining()
        return determine_scenarios(
            self.TEAMS,
            completed=[],
            remaining=remaining,
            n_samples=n_samples,
        )

    def test_denom_equals_n_samples(self):
        """denom and denom_weighted both equal n_samples."""
        r = self._run(n_samples=500)
        assert r.denom == pytest.approx(500.0)
        assert r.denom_weighted == pytest.approx(500.0)

    def test_seed_probabilities_sum_to_at_most_one_per_team(self):
        """Each team's p1+p2+p3+p4 sums to ≤1.0; with 7 teams only 4 qualify so ~4/7 ≈ 57%."""
        r = self._run()
        for team in self.TEAMS:
            total = (
                r.first_counts[team] / r.denom
                + r.second_counts[team] / r.denom
                + r.third_counts[team] / r.denom
                + r.fourth_counts[team] / r.denom
            )
            assert 0.0 <= total <= 1.0 + 1e-9, f"{team}: seed probs sum to {total}"
            assert total > 0.0, f"{team} never earned any seed in 2000 samples"

    def test_weighted_and_unweighted_close_at_equal_prob(self):
        """With no win_prob_fn (50/50), weighted and unweighted odds should be nearly identical."""
        r = self._run(n_samples=2_000)
        for team in self.TEAMS:
            p_unw = r.first_counts[team] / r.denom
            p_w = r.first_counts_weighted[team] / r.denom_weighted
            assert abs(p_unw - p_w) < 0.15, f"{team}: unweighted={p_unw:.3f} vs weighted={p_w:.3f}"

    def test_all_teams_have_nonzero_first_seed_chance(self):
        """With all games remaining and equal strength, every team can win the region."""
        r = self._run(n_samples=2_000)
        for team in self.TEAMS:
            assert r.first_counts[team] > 0, f"{team} never seeded 1st in 2000 samples"
