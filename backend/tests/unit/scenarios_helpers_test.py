"""Unit tests for pure helper functions in scenarios.py.

These tests require no game data — they exercise formatting utilities
and playoff probability calculators directly.
"""

import pytest

from backend.helpers.data_classes import BracketOdds, StandingsOdds
from backend.helpers.scenarios import (
    compute_bracket_odds,
    compute_first_round_home_odds,
    pct_str,
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
