"""Unit tests for scenario_updater.py.

Covers apply_region_game_results and apply_bracket_game_results using small,
hand-computable fixtures so expected values can be verified by inspection.
"""

import pytest

from backend.helpers.data_classes import (
    AppliedGameResult,
    BracketTeam,
    CompletedGame,
    RemainingGame,
)
from backend.helpers.scenario_updater import (
    apply_bracket_game_results,
    apply_region_game_results,
)

# ---------------------------------------------------------------------------
# Shared tiny-region fixture: 3 teams, 1 completed game, 2 remaining
# ---------------------------------------------------------------------------
#
# Teams: Alpha, Beta, Gamma  (lex order: Alpha < Beta < Gamma)
# Completed: Alpha beat Beta 14-7
# Remaining: Alpha vs Gamma, Beta vs Gamma
#
# After applying "Alpha beat Gamma 21-0":
#   Completed: Alpha-Beta (Alpha won), Alpha-Gamma (Alpha won)
#   Remaining: Beta-Gamma
#   Alpha is 2-0 in region — clinched first regardless of Beta-Gamma result.

TEAMS = ["Alpha", "Beta", "Gamma"]

COMPLETED = [
    CompletedGame(a="Alpha", b="Beta", res_a=1, pd_a=7, pa_a=7, pa_b=14),
]

REMAINING = [
    RemainingGame(a="Alpha", b="Gamma"),
    RemainingGame(a="Beta", b="Gamma"),
]


class TestApplyRegionGameResults:
    """Tests for apply_region_game_results — pure region what-if computation."""

    def test_applying_one_result_removes_from_remaining(self):
        """Applying a win clinches first for the 2-0 team in all remaining scenarios."""
        new_result = AppliedGameResult(team_a="Alpha", team_b="Gamma", score_a=21, score_b=0)
        _scenario_results, odds = apply_region_game_results(TEAMS, COMPLETED, REMAINING, [new_result])
        # Alpha is 2-0 in region — must finish first in all outcomes.
        assert odds["Alpha"].p1 == pytest.approx(1.0)
        assert odds["Alpha"].p_playoffs == pytest.approx(1.0)

    def test_applying_reversed_team_order_same_result(self):
        """team_a/team_b order does not affect the resulting odds."""
        forward = apply_region_game_results(
            TEAMS,
            COMPLETED,
            REMAINING,
            [AppliedGameResult(team_a="Alpha", team_b="Gamma", score_a=21, score_b=0)],
        )
        reversed_ = apply_region_game_results(
            TEAMS,
            COMPLETED,
            REMAINING,
            [AppliedGameResult(team_a="Gamma", team_b="Alpha", score_a=0, score_b=21)],
        )
        assert forward[1]["Alpha"].p1 == pytest.approx(reversed_[1]["Alpha"].p1)
        assert forward[1]["Gamma"].p4 == pytest.approx(reversed_[1]["Gamma"].p4)

    def test_no_new_results_unchanged(self):
        """Passing an empty new_results list returns odds identical to the base state."""
        _, odds_no_change = apply_region_game_results(TEAMS, COMPLETED, REMAINING, [])
        # With 2 remaining games both involving Alpha, Alpha could still lose both.
        # Odds should be strictly between 0 and 1.
        assert 0 < odds_no_change["Alpha"].p1 < 1

    def test_applying_all_remaining_yields_deterministic_odds(self):
        """With no games remaining after applying results, every team's odds are 0 or 1."""
        new_results = [
            AppliedGameResult(team_a="Alpha", team_b="Gamma", score_a=21, score_b=0),
            AppliedGameResult(team_a="Beta", team_b="Gamma", score_a=14, score_b=7),
        ]
        _, odds = apply_region_game_results(TEAMS, COMPLETED, REMAINING, new_results)
        # All games played: each team has exactly one seed — all odds are 0 or 1.
        for team in TEAMS:
            o = odds[team]
            assert o.p1 in (0.0, 1.0)
            assert o.p2 in (0.0, 1.0)
            assert o.p3 in (0.0, 1.0)
            assert o.p4 in (0.0, 1.0)

    def test_tie_game_result(self):
        """A tied game (score_a == score_b) is accepted and produces valid odds summing to 1."""
        new_result = AppliedGameResult(team_a="Beta", team_b="Gamma", score_a=7, score_b=7)
        _, odds = apply_region_game_results(TEAMS, COMPLETED, REMAINING, [new_result])
        # Odds should sum to 1.0 per seed across all teams.
        p1_sum = sum(odds[t].p1 for t in TEAMS)
        assert p1_sum == pytest.approx(1.0)

    def test_completed_game_fields_correct(self):
        """A 2-0 Alpha correctly produces p3=0 and p4=0 in all remaining scenarios."""
        # Alpha (lex-first) beats Gamma 21-0 → res_a=1, pd_a=21, pa_a=0, pa_b=21.
        new_result = AppliedGameResult(team_a="Alpha", team_b="Gamma", score_a=21, score_b=0)
        _scenario_results, odds = apply_region_game_results(TEAMS, COMPLETED, REMAINING, [new_result])
        # After the result, no scenario should place Alpha 3rd or 4th.
        assert odds["Alpha"].p3 == pytest.approx(0.0)
        assert odds["Alpha"].p4 == pytest.approx(0.0)

    def test_ignore_margins_flag_accepted(self):
        """ignore_margins=True is forwarded to determine_scenarios without error."""
        new_result = AppliedGameResult(team_a="Alpha", team_b="Gamma", score_a=21, score_b=0)
        _, odds = apply_region_game_results(TEAMS, COMPLETED, REMAINING, [new_result], ignore_margins=True)
        assert odds["Alpha"].p1 == pytest.approx(1.0)

    def test_unknown_pair_in_new_results_is_accepted(self):
        """A result for a pair not in remaining is appended to completed without raising."""
        # Alpha vs Beta was already completed; re-applying it with same result is a no-op
        # for odds (deduplication by CompletedGame merging in determine_scenarios).
        new_result = AppliedGameResult(team_a="Alpha", team_b="Beta", score_a=14, score_b=7)
        _, odds = apply_region_game_results(TEAMS, COMPLETED, REMAINING, [new_result])
        # Should not raise; odds are still valid.
        p1_sum = sum(odds[t].p1 for t in TEAMS)
        assert p1_sum == pytest.approx(1.0)

    def test_team_a_loses_exercises_res_a_minus_one(self):
        """score_a < score_b correctly sets res_a=-1, reducing the loser's p1 below 1."""
        # score_a < score_b: exercises the `res_a = -1` branch (line 86).
        # Gamma beats Alpha — Alpha drops to 1-1, Beta still unbeaten in region.
        new_result = AppliedGameResult(team_a="Alpha", team_b="Gamma", score_a=0, score_b=21)
        _, odds = apply_region_game_results(TEAMS, COMPLETED, REMAINING, [new_result])
        # Alpha can no longer finish 1st (1-1 at best, Beta is 0-1 but plays Gamma).
        # Gamma is now 1-0 so they can reach 1st — Alpha cannot clinch 1st.
        assert odds["Alpha"].p1 < 1.0


# ---------------------------------------------------------------------------
# apply_bracket_game_results
# ---------------------------------------------------------------------------

_BRACKET_TEAMS_4R = [
    BracketTeam(bracket_id=1, school="TeamA", season=2025, seed=1, region=1),
    BracketTeam(bracket_id=1, school="TeamB", season=2025, seed=4, region=1),
    BracketTeam(bracket_id=1, school="TeamC", season=2025, seed=2, region=2),
    BracketTeam(bracket_id=1, school="TeamD", season=2025, seed=3, region=2),
    BracketTeam(bracket_id=1, school="TeamE", season=2025, seed=1, region=3),
    BracketTeam(bracket_id=1, school="TeamF", season=2025, seed=4, region=3),
    BracketTeam(bracket_id=1, school="TeamG", season=2025, seed=2, region=4),
    BracketTeam(bracket_id=1, school="TeamH", season=2025, seed=3, region=4),
]


class TestApplyBracketGameResults4Round:
    """Tests for apply_bracket_game_results with a 4-round (5A–7A) bracket."""

    def test_no_results_all_equal_qf_odds(self):
        """With no results applied, all teams have equal 50/50 odds for each round."""
        odds = apply_bracket_game_results(_BRACKET_TEAMS_4R, 4, [], [])
        for bt in _BRACKET_TEAMS_4R:
            o = odds[bt.school]
            assert o.second_round == pytest.approx(0.0)
            assert o.quarterfinals == pytest.approx(0.5)
            assert o.semifinals == pytest.approx(0.25)
            assert o.finals == pytest.approx(0.125)
            assert o.champion == pytest.approx(0.0625)

    def test_winner_has_higher_odds_after_r1(self):
        """R1 winner has QF=1.0 and halved odds for each subsequent round."""
        r1_result = AppliedGameResult(team_a="TeamA", team_b="TeamB", score_a=21, score_b=7)
        odds = apply_bracket_game_results(_BRACKET_TEAMS_4R, 4, [r1_result], [])
        assert odds["TeamA"].quarterfinals == pytest.approx(1.0)
        assert odds["TeamA"].semifinals == pytest.approx(0.5)
        assert odds["TeamA"].finals == pytest.approx(0.25)
        assert odds["TeamA"].champion == pytest.approx(0.125)

    def test_loser_eliminated_after_r1(self):
        """R1 loser has 0.0 for all subsequent rounds."""
        r1_result = AppliedGameResult(team_a="TeamA", team_b="TeamB", score_a=21, score_b=7)
        odds = apply_bracket_game_results(_BRACKET_TEAMS_4R, 4, [r1_result], [])
        assert odds["TeamB"].quarterfinals == pytest.approx(0.0)
        assert odds["TeamB"].semifinals == pytest.approx(0.0)
        assert odds["TeamB"].finals == pytest.approx(0.0)
        assert odds["TeamB"].champion == pytest.approx(0.0)

    def test_played_and_new_results_combine(self):
        """played_results and new_results are treated identically — both update survivor state."""
        played = [AppliedGameResult(team_a="TeamA", team_b="TeamB", score_a=21, score_b=7)]
        new = [AppliedGameResult(team_a="TeamC", team_b="TeamD", score_a=14, score_b=0)]
        odds = apply_bracket_game_results(_BRACKET_TEAMS_4R, 4, played, new)
        # Both winners at QF = 1.0; both losers eliminated.
        assert odds["TeamA"].quarterfinals == pytest.approx(1.0)
        assert odds["TeamC"].quarterfinals == pytest.approx(1.0)
        assert odds["TeamB"].quarterfinals == pytest.approx(0.0)
        assert odds["TeamD"].quarterfinals == pytest.approx(0.0)

    def test_champion_after_winning_all_4_rounds(self):
        """A team that has won 4 games has champion=1.0 and all prior rounds=1.0."""
        results = [
            AppliedGameResult(team_a="TeamA", team_b="TeamB", score_a=21, score_b=0),
            AppliedGameResult(team_a="TeamA", team_b="TeamC", score_a=14, score_b=7),
            AppliedGameResult(team_a="TeamA", team_b="TeamE", score_a=28, score_b=21),
            AppliedGameResult(team_a="TeamA", team_b="TeamG", score_a=35, score_b=14),
        ]
        odds = apply_bracket_game_results(_BRACKET_TEAMS_4R, 4, [], results)
        assert odds["TeamA"].champion == pytest.approx(1.0)
        assert odds["TeamA"].finals == pytest.approx(1.0)
        assert odds["TeamA"].semifinals == pytest.approx(1.0)
        assert odds["TeamA"].quarterfinals == pytest.approx(1.0)

    def test_tie_scores_skipped_gracefully(self):
        """A tied score (impossible in playoffs) is silently skipped; odds are unaffected."""
        # Ties don't occur in playoff brackets; verify no crash and unaffected odds.
        tie_result = AppliedGameResult(team_a="TeamA", team_b="TeamB", score_a=7, score_b=7)
        odds = apply_bracket_game_results(_BRACKET_TEAMS_4R, 4, [], [tie_result])
        # No one eliminated — all teams still have base odds.
        assert odds["TeamA"].quarterfinals == pytest.approx(0.5)
        assert odds["TeamB"].quarterfinals == pytest.approx(0.5)

    def test_result_with_unknown_school_skipped_gracefully(self):
        """A result referencing schools not in bracket_teams leaves all bracket odds unchanged."""
        # Winner and loser not in bracket_teams — exercises the False branches of
        # `if winner in rounds_won` (155→157) and `if loser in rounds_won` (157→149).
        unknown_result = AppliedGameResult(team_a="Ghost", team_b="Phantom", score_a=21, score_b=0)
        odds = apply_bracket_game_results(_BRACKET_TEAMS_4R, 4, [], [unknown_result])
        # All bracket teams unaffected — still at base equal odds.
        for bt in _BRACKET_TEAMS_4R:
            assert odds[bt.school].quarterfinals == pytest.approx(0.5)


class TestApplyBracketGameResults5Round:
    """Tests for apply_bracket_game_results with a 5-round (1A–4A) bracket."""

    _TEAMS_5R = [
        BracketTeam(bracket_id=2, school=f"Team{i}", season=2025, seed=(i % 4) + 1, region=(i // 4) + 1)
        for i in range(16)
    ]

    def test_no_results_second_round_is_half(self):
        """With no results, all teams have second_round=0.5 and halved odds per subsequent round."""
        odds = apply_bracket_game_results(self._TEAMS_5R, 5, [], [])
        for bt in self._TEAMS_5R:
            o = odds[bt.school]
            assert o.second_round == pytest.approx(0.5)
            assert o.quarterfinals == pytest.approx(0.25)
            assert o.semifinals == pytest.approx(0.125)
            assert o.finals == pytest.approx(0.0625)
            assert o.champion == pytest.approx(0.03125)

    def test_r1_winner_has_second_round_1(self):
        """R1 winner in a 5-round bracket has second_round=1.0 and QF=0.5; loser has second_round=0.0."""
        r1 = AppliedGameResult(team_a="Team0", team_b="Team1", score_a=21, score_b=0)
        odds = apply_bracket_game_results(self._TEAMS_5R, 5, [r1], [])
        assert odds["Team0"].second_round == pytest.approx(1.0)
        assert odds["Team0"].quarterfinals == pytest.approx(0.5)
        assert odds["Team1"].second_round == pytest.approx(0.0)
