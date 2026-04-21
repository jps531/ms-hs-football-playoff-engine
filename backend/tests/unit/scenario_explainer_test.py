"""Unit tests for scenario_explainer.py.

Fixtures are small, hand-computable regions so expected seedings and
explanation strings can be verified by inspection.

Fixture overview
----------------
THREE_TEAM (all-alone):
    Alpha 2-0, Beta 1-1, Gamma 0-2 after a full round-robin with no
    remaining games (mask=0).  Scores: Alpha beat Beta 14-7, Alpha beat
    Gamma 21-0, Beta beat Gamma 7-0.  No ties.

FOUR_TEAM (2-way H2H tie):
    Alpha/Beta both finish 2-1; Gamma/Delta both finish 1-2.
    Alpha beat Beta 14-7 (H2H separates the top pair).
    Gamma beat Delta 14-7 (H2H separates the bottom pair).

FIVE_TEAM (3-way tie):
    Epsilon 3-1, Alpha/Beta/Gamma all 2-2, Delta 1-3.
    Within the tied group: Alpha beat Beta and Gamma; Beta beat Gamma.
    Outside: Alpha lost to both Epsilon and Delta; Beta beat Delta, lost
    to Epsilon; Gamma beat Delta and Epsilon.  (Epsilon and Delta are not
    in the 3-way bucket so H2H-within-bucket determines the order.)

STEP2 (2-way Step-2 resolution — partial schedule, no H2H between tied pair):
    Five-team partial schedule.  Alpha and Beta both finish 2-1 but never
    played each other.  Gamma (3-1) is the first outside team in base
    seeding order.  Alpha beat Gamma; Beta lost to Gamma.  Step 2 (record
    vs outside opponents) places Alpha above Beta.
    Final overall order: Gamma 1st, Alpha 2nd, Beta 3rd, Omega 4th, Delta 5th.
"""

from collections import defaultdict

from backend.helpers.data_classes import CompletedGame, RemainingGame
from backend.helpers.scenario_explainer import (
    BucketStepData,
    _explain_bucket,
    _game_score_str,
    _join_names,
    _non_h2h_clause,
    _record_str,
    _seed_label,
    explain_seeding_outcome,
)

# ---------------------------------------------------------------------------
# THREE_TEAM fixture  (all alone, no remaining games, mask=0)
# ---------------------------------------------------------------------------

_THREE_TEAMS = ["Alpha", "Beta", "Gamma"]

_THREE_COMPLETED = [
    CompletedGame(a="Alpha", b="Beta", res_a=1, pd_a=7, pa_a=7, pa_b=14),
    CompletedGame(a="Alpha", b="Gamma", res_a=1, pd_a=21, pa_a=0, pa_b=21),
    CompletedGame(a="Beta", b="Gamma", res_a=1, pd_a=7, pa_a=0, pa_b=7),
]

_THREE_REMAINING: list[RemainingGame] = []
_THREE_MARGINS = {("Alpha", "Beta"): 7, ("Alpha", "Gamma"): 21, ("Beta", "Gamma"): 7}

# ---------------------------------------------------------------------------
# FOUR_TEAM fixture  (2-way H2H ties at top and bottom)
# ---------------------------------------------------------------------------
#
# Results (all as completed, mask=0 / no remaining):
#   Alpha beat Beta  14-7   → Alpha 1-0 vs Beta,  Beta 0-1 vs Alpha
#   Alpha beat Gamma 21-0   → Alpha 1-0 vs Gamma, Gamma 0-1 vs Alpha
#   Alpha lost to Delta 0-7 → Alpha 0-1 vs Delta, Delta 1-0 vs Alpha
#   Beta beat Gamma  14-7   → Beta  1-0 vs Gamma, Gamma 0-1 vs Beta
#   Beta beat Delta  14-7   → Beta  1-0 vs Delta, Delta 0-1 vs Beta
#   Gamma beat Delta 14-7   → Gamma 1-0 vs Delta, Delta 0-1 vs Gamma
#
# Final records: Alpha 2-1, Beta 2-1, Gamma 1-2, Delta 1-2.
# H2H in the {Alpha,Beta} bucket: Alpha beat Beta → Alpha 1st, Beta 2nd.
# H2H in the {Gamma,Delta} bucket: Gamma beat Delta → Gamma 3rd, Delta 4th.

_FOUR_TEAMS = ["Alpha", "Beta", "Delta", "Gamma"]  # alpha-sorted

_FOUR_COMPLETED = [
    CompletedGame(a="Alpha", b="Beta", res_a=1, pd_a=7, pa_a=7, pa_b=14),
    CompletedGame(a="Alpha", b="Delta", res_a=-1, pd_a=-7, pa_a=7, pa_b=0),
    CompletedGame(a="Alpha", b="Gamma", res_a=1, pd_a=21, pa_a=0, pa_b=21),
    CompletedGame(a="Beta", b="Delta", res_a=1, pd_a=7, pa_a=7, pa_b=14),
    CompletedGame(a="Beta", b="Gamma", res_a=1, pd_a=7, pa_a=7, pa_b=14),
    CompletedGame(a="Delta", b="Gamma", res_a=-1, pd_a=-7, pa_a=7, pa_b=0),
]

_FOUR_REMAINING: list[RemainingGame] = []
_FOUR_MARGINS = {
    ("Alpha", "Beta"): 7,
    ("Alpha", "Delta"): 7,
    ("Alpha", "Gamma"): 21,
    ("Beta", "Delta"): 7,
    ("Beta", "Gamma"): 7,
    ("Delta", "Gamma"): 7,
}

# ---------------------------------------------------------------------------
# FIVE_TEAM fixture  (3-way tie in the middle)
# ---------------------------------------------------------------------------
#
# Teams: Alpha, Beta, Delta, Epsilon, Gamma  (alpha-sorted)
# Each team plays 4 region games.
#
# Completed results (all lex-normalised):
#   Alpha  beat  Beta     21-0
#   Alpha  beat  Gamma    14-7
#   Alpha  lost  Delta    0-7   (Delta beat Alpha)
#   Alpha  lost  Epsilon  0-14  (Epsilon beat Alpha)
#   Beta   beat  Delta    14-7
#   Beta   lost  Epsilon  0-7   (Epsilon beat Beta)
#   Beta   lost  Gamma    0-14  (Gamma beat Beta)   ← wait, need to check
# Actually let me reconsider...
# We need Alpha/Beta/Gamma all at 2-2, Epsilon 3-1, Delta 1-3.
#
# Within-bucket H2H: Alpha beat Beta AND Gamma; Beta beat Gamma.
# → Alpha 1st in bucket (beat both), Beta 2nd (beat Gamma, lost to Alpha), Gamma 3rd (lost to both).
#
# Each plays 4 games (round-robin of 5).
# Alpha: beat Beta, beat Gamma, lost to Delta, lost to Epsilon → 2-2 ✓
# Beta:  lost to Alpha, beat Delta, lost to Epsilon, beat Gamma ← wait Beta 2-2?
#        Actually: beat Gamma ✓, beat Delta ✓, lost to Alpha ✗, lost to Epsilon ✗ → 2-2 ✓
# Gamma: lost to Alpha, lost to Beta, beat Delta, beat Epsilon → 2-2 ✓
# Delta: beat Alpha, lost to Beta, lost to Gamma, lost to Epsilon → 1-3 ✓
# Epsilon: beat Alpha, beat Beta, lost to Gamma, beat Delta → 3-1 ✓
#
# Cross-check: games = 5*4/2=10. Let's list all 10:
#   Alpha-Beta:    Alpha wins
#   Alpha-Delta:   Delta wins
#   Alpha-Epsilon: Epsilon wins
#   Alpha-Gamma:   Alpha wins
#   Beta-Delta:    Beta wins
#   Beta-Epsilon:  Epsilon wins
#   Beta-Gamma:    Beta wins
#   Delta-Epsilon: Epsilon wins
#   Delta-Gamma:   Gamma wins
#   Epsilon-Gamma: Gamma wins

_FIVE_TEAMS = ["Alpha", "Beta", "Delta", "Epsilon", "Gamma"]

_FIVE_COMPLETED = [
    CompletedGame(a="Alpha", b="Beta", res_a=1, pd_a=21, pa_a=0, pa_b=21),
    CompletedGame(a="Alpha", b="Delta", res_a=-1, pd_a=-7, pa_a=7, pa_b=0),
    CompletedGame(a="Alpha", b="Epsilon", res_a=-1, pd_a=-14, pa_a=14, pa_b=0),
    CompletedGame(a="Alpha", b="Gamma", res_a=1, pd_a=7, pa_a=7, pa_b=14),
    CompletedGame(a="Beta", b="Delta", res_a=1, pd_a=7, pa_a=7, pa_b=14),
    CompletedGame(a="Beta", b="Epsilon", res_a=-1, pd_a=-7, pa_a=7, pa_b=0),
    CompletedGame(a="Beta", b="Gamma", res_a=1, pd_a=14, pa_a=0, pa_b=14),
    CompletedGame(a="Delta", b="Epsilon", res_a=-1, pd_a=-14, pa_a=14, pa_b=0),
    CompletedGame(a="Delta", b="Gamma", res_a=-1, pd_a=-7, pa_a=7, pa_b=0),
    CompletedGame(a="Epsilon", b="Gamma", res_a=-1, pd_a=-7, pa_a=7, pa_b=0),
]

_FIVE_REMAINING: list[RemainingGame] = []
_FIVE_MARGINS = {
    ("Alpha", "Beta"): 21,
    ("Alpha", "Delta"): 7,
    ("Alpha", "Epsilon"): 14,
    ("Alpha", "Gamma"): 7,
    ("Beta", "Delta"): 7,
    ("Beta", "Epsilon"): 7,
    ("Beta", "Gamma"): 14,
    ("Delta", "Epsilon"): 14,
    ("Delta", "Gamma"): 7,
    ("Epsilon", "Gamma"): 7,
}

# ---------------------------------------------------------------------------
# STEP2 fixture  (2-way tie resolved by Step 2 — partial schedule, no H2H)
# ---------------------------------------------------------------------------
#
# 5 teams, partial schedule (Alpha and Beta never play each other).
# Each of Alpha and Beta plays Delta, Gamma, Omega.
#
#   Alpha (2-1): beat Delta 14-7, beat Gamma 21-0, lost to Omega 0-7
#   Beta  (2-1): beat Delta 7-0, lost to Gamma 0-14, beat Omega 14-7
#   Gamma (3-1): beat Beta, beat Delta, beat Omega, lost to Alpha
#   Omega (2-2): beat Alpha, lost to Beta, beat Delta, lost to Gamma
#   Delta (0-4): lost to all four opponents
#
# Tie bucket {Alpha, Beta}: Step 1 = 0.0 (no H2H game played).
# Outside order (base_order): Gamma, Alpha, Beta, Omega, Delta.
# Outside for the bucket: [Gamma, Omega, Delta].
#
# step2[Alpha] = [2, 0, 2]  — beat Gamma, lost to Omega, beat Delta
# step2[Beta]  = [0, 2, 2]  — lost to Gamma, beat Omega, beat Delta
#
# First differentiating outside team: Gamma (index 0).
# Alpha beat Gamma → Alpha finishes 2nd; Beta lost to Gamma → Beta finishes 3rd.

_STEP2_TEAMS = ["Alpha", "Beta", "Delta", "Gamma", "Omega"]

_STEP2_COMPLETED = [
    # Alpha's games (no game vs Beta)
    CompletedGame(a="Alpha", b="Delta", res_a=1,  pd_a=7,   pa_a=7,   pa_b=14),
    CompletedGame(a="Alpha", b="Gamma", res_a=1,  pd_a=21,  pa_a=0,   pa_b=21),
    CompletedGame(a="Alpha", b="Omega", res_a=-1, pd_a=-7,  pa_a=7,   pa_b=0),
    # Beta's games (no game vs Alpha)
    CompletedGame(a="Beta",  b="Delta", res_a=1,  pd_a=7,   pa_a=0,   pa_b=7),
    CompletedGame(a="Beta",  b="Gamma", res_a=-1, pd_a=-14, pa_a=14,  pa_b=0),
    CompletedGame(a="Beta",  b="Omega", res_a=1,  pd_a=7,   pa_a=7,   pa_b=14),
    # Other games (Delta, Gamma, Omega round-robin)
    CompletedGame(a="Delta", b="Gamma", res_a=-1, pd_a=-7,  pa_a=14,  pa_b=7),
    CompletedGame(a="Delta", b="Omega", res_a=-1, pd_a=-14, pa_a=14,  pa_b=0),
    CompletedGame(a="Gamma", b="Omega", res_a=1,  pd_a=7,   pa_a=0,   pa_b=7),
]

_STEP2_REMAINING: list[RemainingGame] = []

_STEP2_MARGINS = {
    ("Alpha", "Delta"): 7,   ("Alpha", "Gamma"): 21,  ("Alpha", "Omega"): 7,
    ("Beta",  "Delta"): 7,   ("Beta",  "Gamma"): 14,  ("Beta",  "Omega"): 7,
    ("Delta", "Gamma"): 7,   ("Delta", "Omega"): 14,  ("Gamma", "Omega"): 7,
}


# ===========================================================================
# Formatting helper tests
# ===========================================================================


class TestSeedLabel:
    """Tests for the _seed_label ordinal formatter."""

    def test_first(self):
        """1 maps to '1st'."""
        assert _seed_label(1) == "1st"

    def test_second(self):
        """2 maps to '2nd'."""
        assert _seed_label(2) == "2nd"

    def test_third(self):
        """3 maps to '3rd'."""
        assert _seed_label(3) == "3rd"

    def test_fifth_fallback(self):
        """5 maps to '5th' via the fallback path."""
        assert _seed_label(5) == "5th"


class TestRecordStr:
    """Tests for _record_str W-L[-T] formatting."""

    def test_no_ties(self):
        """Record with zero ties is formatted as W-L."""
        assert _record_str({"w": 3, "l": 1, "t": 0}) == "3-1"

    def test_with_tie(self):
        """Record with a tie is formatted as W-L-T."""
        assert _record_str({"w": 2, "l": 1, "t": 1}) == "2-1-1"


class TestJoinNames:
    """Tests for Oxford-comma name joining."""

    def test_one(self):
        """Single name returns as-is."""
        assert _join_names(["Alpha"]) == "Alpha"

    def test_two(self):
        """Two names joined with 'and' (no comma)."""
        assert _join_names(["Alpha", "Beta"]) == "Alpha and Beta"

    def test_three(self):
        """Three names use Oxford comma."""
        assert _join_names(["A", "B", "C"]) == "A, B, and C"


class TestGameScoreStr:
    """Tests for _game_score_str score lookup from team's POV."""

    def test_team_is_lex_first_winner(self):
        """Alpha (lex-first) beat Beta 14-7: Alpha's score str is ' 14-7'."""
        score = _game_score_str("Alpha", "Beta", _THREE_COMPLETED)
        assert score == " 14-7"

    def test_team_is_lex_second_winner(self):
        """Beta beat Gamma 7-0: from Beta's POV, score is ' 7-0'."""
        score = _game_score_str("Beta", "Gamma", _THREE_COMPLETED)
        assert score == " 7-0"

    def test_team_is_loser(self):
        """Alpha beat Beta 14-7: from Beta's (loser) POV, score is ' 7-14'."""
        score = _game_score_str("Beta", "Alpha", _THREE_COMPLETED)
        assert score == " 7-14"

    def test_no_score_data(self):
        """Returns None when pa_a == 0 and pa_b == 0 (no score recorded)."""
        no_score = [CompletedGame(a="Alpha", b="Beta", res_a=1, pd_a=7, pa_a=0, pa_b=0)]
        assert _game_score_str("Alpha", "Beta", no_score) is None

    def test_game_not_found(self):
        """Returns None when no matching CompletedGame exists."""
        assert _game_score_str("Alpha", "Delta", _THREE_COMPLETED) is None


# ===========================================================================
# explain_seeding_outcome — all-alone (3-team round-robin)
# ===========================================================================


class TestExplainAllAlone:
    """Tests for solo (all-alone) seeding explanations."""

    def test_alpha_all_alone_first(self):
        """2-0 Alpha finishes all alone in 1st."""
        result = explain_seeding_outcome(_THREE_TEAMS, _THREE_COMPLETED, _THREE_REMAINING, 0, _THREE_MARGINS)
        assert result["Alpha"] == "Alpha finishes 2-0, all alone in 1st"

    def test_beta_all_alone_second(self):
        """1-1 Beta finishes all alone in 2nd."""
        result = explain_seeding_outcome(_THREE_TEAMS, _THREE_COMPLETED, _THREE_REMAINING, 0, _THREE_MARGINS)
        assert result["Beta"] == "Beta finishes 1-1, all alone in 2nd"

    def test_gamma_all_alone_third(self):
        """0-2 Gamma finishes all alone in 3rd."""
        result = explain_seeding_outcome(_THREE_TEAMS, _THREE_COMPLETED, _THREE_REMAINING, 0, _THREE_MARGINS)
        assert result["Gamma"] == "Gamma finishes 0-2, all alone in 3rd"

    def test_returns_all_teams(self):
        """explain_seeding_outcome returns an entry for every team."""
        result = explain_seeding_outcome(_THREE_TEAMS, _THREE_COMPLETED, _THREE_REMAINING, 0, _THREE_MARGINS)
        assert set(result.keys()) == set(_THREE_TEAMS)


# ===========================================================================
# explain_seeding_outcome — 2-way H2H tie (4-team fixture)
# ===========================================================================


class TestExplainTwoWayH2H:
    """Tests for 2-way H2H tie explanations with scores."""

    def _result(self):
        """Run explain_seeding_outcome on the 4-team fixture."""
        return explain_seeding_outcome(_FOUR_TEAMS, _FOUR_COMPLETED, _FOUR_REMAINING, 0, _FOUR_MARGINS)

    def test_alpha_beat_beta(self):
        """Alpha (2-1) finishes 1st, tied with Beta whom they beat 14-7."""
        r = self._result()
        assert r["Alpha"] == "Alpha finishes 2-1, tied with Beta, who they beat 14-7"

    def test_beta_lost_to_alpha(self):
        """Beta (2-1) finishes 2nd, tied with Alpha whom they lost to 7-14."""
        r = self._result()
        assert r["Beta"] == "Beta finishes 2-1, tied with Alpha, who they lost to 7-14"

    def test_gamma_beat_delta(self):
        """Gamma (1-2) finishes 3rd, tied with Delta whom they beat 7-0."""
        r = self._result()
        assert r["Gamma"] == "Gamma finishes 1-2, tied with Delta, who they beat 7-0"

    def test_delta_lost_to_gamma(self):
        """Delta (1-2) finishes 4th, tied with Gamma whom they lost to 0-7."""
        r = self._result()
        assert r["Delta"] == "Delta finishes 1-2, tied with Gamma, who they lost to 0-7"


# ===========================================================================
# explain_seeding_outcome — 3-way tie (5-team fixture)
# ===========================================================================


class TestExplainThreeWayTie:
    """Tests for 3-way H2H tie explanations (beat-both, lost-to-both, beat-one-lost-one)."""

    def _result(self):
        """Run explain_seeding_outcome on the 5-team fixture."""
        return explain_seeding_outcome(_FIVE_TEAMS, _FIVE_COMPLETED, _FIVE_REMAINING, 0, _FIVE_MARGINS)

    def test_alpha_beat_both(self):
        """Alpha (2-2) finishes 2nd (behind Epsilon), beating both Beta and Gamma."""
        r = self._result()
        assert "Alpha" in r["Alpha"]
        assert "2-2" in r["Alpha"]
        assert "both of whom they beat" in r["Alpha"]

    def test_gamma_lost_to_both(self):
        """Gamma (2-2) finishes 4th (ahead of Delta), losing to both Alpha and Beta."""
        r = self._result()
        assert "Gamma" in r["Gamma"]
        assert "2-2" in r["Gamma"]
        assert "both of whom they lost to" in r["Gamma"]

    def test_beta_beat_one_lost_one(self):
        """Beta (2-2) finishes 3rd — beat Gamma, lost to Alpha.

        Phase 2: the 3-way bucket has unequal step-1 values (Alpha=2, Beta=1,
        Gamma=0), so H2H within sub-buckets fully resolved the order.  The
        explanation drops "via tiebreaker" in favour of "giving Beta 3rd".
        """
        r = self._result()
        assert "Beta" in r["Beta"]
        assert "2-2" in r["Beta"]
        assert "They beat Gamma but lost to Alpha" in r["Beta"]
        assert "giving Beta 3rd" in r["Beta"]
        assert "via tiebreaker" not in r["Beta"]

    def test_epsilon_all_alone_first(self):
        """Epsilon (3-1) is not in the tie bucket and finishes all alone in 1st."""
        r = self._result()
        assert r["Epsilon"] == "Epsilon finishes 3-1, all alone in 1st"

    def test_delta_all_alone_last(self):
        """Delta (1-3) is not in the tie bucket and finishes all alone in 5th."""
        r = self._result()
        assert r["Delta"] == "Delta finishes 1-3, all alone in 5th"


# ===========================================================================
# _explain_bucket — coin flip path (unit test with synthetic inputs)
# ===========================================================================


class TestExplainBucketCoinFlip:
    """Tests for the coin-flip branch in _explain_bucket."""

    def test_coin_flip_two_way(self):
        """When coin_flip_groups contains both tied teams, the explanation says 'coin-flip'."""

        h2h: dict = defaultdict(float)
        # Symmetric H2H — no winner
        h2h[("Alpha", "Beta")] = 0.0
        h2h[("Beta", "Alpha")] = 0.0

        result = _explain_bucket(
            team="Alpha",
            bucket=["Alpha", "Beta"],
            seed=1,
            record="2-1",
            completed=[],
            coin_flip_groups=[["Alpha", "Beta"]],
            h2h_pts=h2h,
        )
        assert "coin-flip" in result

    def test_no_coin_flip_two_way_h2h_wins(self):
        """When no coin flip group exists for this pair, H2H resolution is used."""

        h2h: dict = defaultdict(float)
        h2h[("Alpha", "Beta")] = 1.0  # Alpha beat Beta

        result = _explain_bucket(
            team="Alpha",
            bucket=["Alpha", "Beta"],
            seed=1,
            record="2-1",
            completed=[CompletedGame(a="Alpha", b="Beta", res_a=1, pd_a=7, pa_a=7, pa_b=14)],
            coin_flip_groups=[],
            h2h_pts=h2h,
        )
        assert "who they beat" in result
        assert "coin-flip" not in result


# ===========================================================================
# _explain_bucket — 4-way+ tie fallback
# ===========================================================================


class TestExplainBucketFourWayFallback:
    """Tests for the generic tiebreaker fallback for large tie buckets."""

    def test_four_way_tie_fallback(self):
        """A 4-way tie bucket with no dominant team uses the generic fallback."""

        h2h: dict = defaultdict(float)
        bucket = ["Alpha", "Beta", "Gamma", "Delta"]

        result = _explain_bucket(
            team="Alpha",
            bucket=bucket,
            seed=1,
            record="2-2",
            completed=[],
            coin_flip_groups=[],
            h2h_pts=h2h,
        )
        assert "4-way tie" in result
        assert "via tiebreaker" in result
        assert "Beta" in result


class TestExplainBucketEdgeCases:
    """Tests for remaining _explain_bucket branches: non-H2H 2-way and 3-way mixed fallback."""

    def test_two_way_non_h2h_tiebreaker(self):
        """When H2H is symmetric and no coin flip, the 2-way fallback says 'via tiebreaker'."""

        h2h: dict = defaultdict(float)
        # Both teams have 0.5 H2H points (e.g. no H2H game played between them)
        # so neither > the other — falls through to the non-H2H fallback.
        h2h[("Alpha", "Beta")] = 0.5
        h2h[("Beta", "Alpha")] = 0.5

        result = _explain_bucket(
            team="Alpha",
            bucket=["Alpha", "Beta"],
            seed=1,
            record="2-1",
            completed=[],
            coin_flip_groups=[],
            h2h_pts=h2h,
        )
        assert "via tiebreaker" in result
        assert "coin-flip" not in result

    def test_three_way_mixed_fallback(self):
        """A 3-way bucket where one matchup is tied (0-0 H2H) uses the generic fallback."""

        h2h: dict = defaultdict(float)
        # Alpha beat Beta, but Alpha vs Gamma is unknown (0-0).
        # → len(beat)==1, len(lost_to)==0 — neither beat-both nor the beat1/lost1 path.
        h2h[("Alpha", "Beta")] = 1.0
        h2h[("Beta", "Alpha")] = 0.0
        # Alpha vs Gamma: both zero → neither wins H2H

        result = _explain_bucket(
            team="Alpha",
            bucket=["Alpha", "Beta", "Gamma"],
            seed=1,
            record="2-1",
            completed=[],
            coin_flip_groups=[],
            h2h_pts=h2h,
        )
        assert "3-way tie" in result
        assert "via tiebreaker" in result


# ===========================================================================
# Phase 2: Step-2 resolution (2-way tie, no H2H) — integration tests
# ===========================================================================


class TestExplainTwoWayStep2:
    """Integration tests for 2-way ties resolved by Step 2 (record vs outside)."""

    def _result(self):
        """Run explain_seeding_outcome on the STEP2 fixture (mask=0, no remaining games)."""
        return explain_seeding_outcome(_STEP2_TEAMS, _STEP2_COMPLETED, _STEP2_REMAINING, 0, _STEP2_MARGINS)

    def test_alpha_placed_higher_via_step2(self):
        """Alpha beat Gamma (best outside team) while Beta lost — Step 2 places Alpha 2nd."""
        r = self._result()
        assert "Alpha" in r["Alpha"]
        assert "2-1" in r["Alpha"]
        assert "beat Gamma" in r["Alpha"]
        assert "Beta lost" in r["Alpha"]
        assert "placing Alpha 2nd" in r["Alpha"]
        assert "via tiebreaker" not in r["Alpha"]

    def test_beta_placed_lower_via_step2(self):
        """Beta lost to Gamma while Alpha won — Step 2 places Beta 3rd."""
        r = self._result()
        assert "Beta" in r["Beta"]
        assert "2-1" in r["Beta"]
        assert "lost to Gamma" in r["Beta"]
        assert "Alpha won" in r["Beta"]
        assert "placing Beta 3rd" in r["Beta"]
        assert "via tiebreaker" not in r["Beta"]

    def test_gamma_alone_first(self):
        """Gamma (3-1) is not in the tie bucket and finishes all alone in 1st."""
        r = self._result()
        assert r["Gamma"] == "Gamma finishes 3-1, all alone in 1st"

    def test_delta_alone_last(self):
        """Delta (0-4) is not in the tie bucket and finishes all alone in 5th."""
        r = self._result()
        assert r["Delta"] == "Delta finishes 0-4, all alone in 5th"


# ===========================================================================
# Phase 2: _non_h2h_clause unit tests
# ===========================================================================


def _make_step_data(step2, step4, h2h_pd_cap_dict, wl_totals, outside):
    """Build a BucketStepData from plain dicts for unit testing."""
    h2h: dict = defaultdict(int)
    h2h.update(h2h_pd_cap_dict)
    return BucketStepData(step2=step2, step4=step4, h2h_pd_cap=h2h, wl_totals=wl_totals, outside=outside)


class TestNonH2HClause:
    """Unit tests for _non_h2h_clause — the per-step explanation helper."""

    def test_step2_team_wins(self):
        """Team beat the first outside opponent while other lost — reports the win."""
        sd = _make_step_data(
            step2={"Alpha": [2], "Beta": [0]},
            step4={"Alpha": [7], "Beta": [0]},
            h2h_pd_cap_dict={},
            wl_totals={"Alpha": {"pa": 10}, "Beta": {"pa": 20}},
            outside=["Wayne"],
        )
        clause = _non_h2h_clause("Alpha", "Beta", ["Alpha", "Beta"], sd)
        assert clause is not None
        assert "beat Wayne" in clause
        assert "Beta lost" in clause

    def test_step2_team_loses(self):
        """Team lost to the first outside opponent while other won — reports the loss."""
        sd = _make_step_data(
            step2={"Alpha": [0], "Beta": [2]},
            step4={"Alpha": [0], "Beta": [7]},
            h2h_pd_cap_dict={},
            wl_totals={"Alpha": {"pa": 20}, "Beta": {"pa": 10}},
            outside=["Wayne"],
        )
        clause = _non_h2h_clause("Alpha", "Beta", ["Alpha", "Beta"], sd)
        assert clause is not None
        assert "lost to Wayne" in clause
        assert "Beta won" in clause

    def test_step2_first_tied_second_differs(self):
        """First outside opponent tied; second differentiates — reports the second."""
        sd = _make_step_data(
            step2={"Alpha": [2, 2], "Beta": [2, 0]},
            step4={"Alpha": [7, 7], "Beta": [7, 0]},
            h2h_pd_cap_dict={},
            wl_totals={"Alpha": {"pa": 10}, "Beta": {"pa": 20}},
            outside=["Wayne", "Jones"],
        )
        clause = _non_h2h_clause("Alpha", "Beta", ["Alpha", "Beta"], sd)
        assert clause is not None
        assert "Jones" in clause

    def test_step3_resolves_when_step2_tied(self):
        """Step 2 fully tied; Step 3 (H2H PD within sub-bucket) resolves."""
        sd = _make_step_data(
            step2={"Alpha": [2], "Beta": [2]},
            step4={"Alpha": [7], "Beta": [7]},
            h2h_pd_cap_dict={("Alpha", "Beta"): 8, ("Beta", "Alpha"): -8},
            wl_totals={"Alpha": {"pa": 10}, "Beta": {"pa": 20}},
            outside=["Wayne"],
        )
        clause = _non_h2h_clause("Alpha", "Beta", ["Alpha", "Beta"], sd)
        assert clause is not None
        assert "H2H point margin" in clause
        assert "8" in clause

    def test_step4_resolves_when_steps_2_3_tied(self):
        """Steps 2 and 3 tied; Step 4 (PD vs outside) resolves."""
        sd = _make_step_data(
            step2={"Alpha": [2], "Beta": [2]},
            step4={"Alpha": [12], "Beta": [7]},
            h2h_pd_cap_dict={("Alpha", "Beta"): 0, ("Beta", "Alpha"): 0},
            wl_totals={"Alpha": {"pa": 10}, "Beta": {"pa": 20}},
            outside=["Wayne"],
        )
        clause = _non_h2h_clause("Alpha", "Beta", ["Alpha", "Beta"], sd)
        assert clause is not None
        assert "point differentials" in clause

    def test_step5_resolves_when_steps_2_3_4_tied(self):
        """Steps 2-4 tied; Step 5 (fewest PA) resolves."""
        sd = _make_step_data(
            step2={"Alpha": [2], "Beta": [2]},
            step4={"Alpha": [7], "Beta": [7]},
            h2h_pd_cap_dict={("Alpha", "Beta"): 0, ("Beta", "Alpha"): 0},
            wl_totals={"Alpha": {"pa": 14}, "Beta": {"pa": 28}},
            outside=["Wayne"],
        )
        clause = _non_h2h_clause("Alpha", "Beta", ["Alpha", "Beta"], sd)
        assert clause is not None
        assert "allowed fewer points" in clause
        assert "14" in clause
        assert "28" in clause

    def test_returns_none_when_all_tied(self):
        """Returns None when all tiebreaker steps are equal (coin flip needed)."""
        sd = _make_step_data(
            step2={"Alpha": [2], "Beta": [2]},
            step4={"Alpha": [7], "Beta": [7]},
            h2h_pd_cap_dict={("Alpha", "Beta"): 0, ("Beta", "Alpha"): 0},
            wl_totals={"Alpha": {"pa": 14}, "Beta": {"pa": 14}},
            outside=["Wayne"],
        )
        assert _non_h2h_clause("Alpha", "Beta", ["Alpha", "Beta"], sd) is None

    def test_step2_team_wins_no_opponent_game(self):
        """Team beat outside opponent while other team didn't play them — reports the difference."""
        sd = _make_step_data(
            step2={"Alpha": [2], "Beta": [None]},
            step4={"Alpha": [7], "Beta": [None]},
            h2h_pd_cap_dict={},
            wl_totals={"Alpha": {"pa": 10}, "Beta": {"pa": 20}},
            outside=["Wayne"],
        )
        clause = _non_h2h_clause("Alpha", "Beta", ["Alpha", "Beta"], sd)
        assert clause is not None
        assert "Wayne" in clause
        assert "Alpha" not in clause or "beat" in clause


# ===========================================================================
# Phase 2: circular 3-way tie — _explain_bucket unit tests
# ===========================================================================


class TestExplainBucketCircularThreeWay:
    """Tests for circular 3-way ties (all step-1 equal) with Phase-2 step data.

    Circular setup: Alpha beats Beta, Beta beats Gamma, Gamma beats Alpha.
    Step 2 fully resolves: Alpha beat Jones while Beta lost; Beta beat Wayne
    while Gamma lost; each team has a different step-2 profile.
    Final bucket order: Alpha 1st, Beta 2nd, Gamma 3rd (within the bucket).
    """

    _BUCKET = ["Alpha", "Beta", "Gamma"]
    _H2H: dict = defaultdict(float, {
        ("Alpha", "Beta"): 1.0, ("Beta", "Alpha"): 0.0,
        ("Beta", "Gamma"): 1.0, ("Gamma", "Beta"): 0.0,
        ("Gamma", "Alpha"): 1.0, ("Alpha", "Gamma"): 0.0,
    })
    # step2 fully resolves all three (all distinct keys)
    _SD = _make_step_data(
        step2={"Alpha": [2, 2], "Beta": [2, 0], "Gamma": [0, 2]},
        step4={"Alpha": [7, 7], "Beta": [7, 0], "Gamma": [0, 7]},
        h2h_pd_cap_dict={
            ("Alpha", "Beta"): 7, ("Beta", "Alpha"): -7,
            ("Beta", "Gamma"): 7, ("Gamma", "Beta"): -7,
            ("Gamma", "Alpha"): 7, ("Alpha", "Gamma"): -7,
        },
        wl_totals={"Alpha": {"pa": 10}, "Beta": {"pa": 20}, "Gamma": {"pa": 15}},
        outside=["Wayne", "Jones"],
    )
    _SEED_ORDER = ["Alpha", "Beta", "Gamma"]  # Alpha=1st, Beta=2nd, Gamma=3rd

    def _call(self, team, seed):
        """Invoke _explain_bucket for one team with Phase-2 data."""
        return _explain_bucket(
            team=team,
            bucket=self._BUCKET,
            seed=seed,
            record="2-2",
            completed=[],
            coin_flip_groups=[],
            h2h_pts=self._H2H,
            step_data=self._SD,
            bucket_seed_order=self._SEED_ORDER,
        )

    def test_top_team_beat_adjacent_outside(self):
        """Alpha (1st): beat Beta in H2H but lost to Gamma; Step 2 beat Jones clinches 1st."""
        result = self._call("Alpha", 1)
        assert "beat Beta but lost to Gamma" in result
        assert "Jones" in result
        assert "placing Alpha 1st" in result
        assert "via tiebreaker" not in result

    def test_middle_team_beat_adjacent_outside(self):
        """Beta (2nd): beat Gamma but lost to Alpha; Step 2 beat Wayne clinches 2nd."""
        result = self._call("Beta", 2)
        assert "beat Gamma but lost to Alpha" in result
        assert "Wayne" in result
        assert "placing Beta 2nd" in result
        assert "via tiebreaker" not in result

    def test_bottom_team_lost_to_adjacent_outside(self):
        """Gamma (3rd): beat Alpha but lost to Beta; Step 2 lost to Wayne places Gamma 3rd."""
        result = self._call("Gamma", 3)
        assert "beat Alpha but lost to Beta" in result
        assert "Wayne" in result
        assert "placing Gamma 3rd" in result
        assert "via tiebreaker" not in result


# ===========================================================================
# Phase 2: partial-split 3-way — "giving Nth" replaces "via tiebreaker"
# ===========================================================================


class TestExplainBucketPartialSplit:
    """Tests that partial-split beat1/lost1 cases say 'giving Nth' not 'via tiebreaker'.

    Setup: A(step1=2), B(step1=1), C(step1=0) in bucket {A,B,C}.
    Step 1 fully resolves (all different).  Phase 2 should drop 'via tiebreaker'
    and instead say 'giving B 2nd' since the H2H record tells the whole story.
    """

    _H2H: dict = defaultdict(float, {
        ("Alpha", "Beta"): 1.0, ("Beta", "Alpha"): 0.0,
        ("Alpha", "Gamma"): 1.0, ("Gamma", "Alpha"): 0.0,
        ("Beta", "Gamma"): 1.0, ("Gamma", "Beta"): 0.0,
    })

    def _call(self, team, seed):
        """Invoke _explain_bucket for one team; step_data is irrelevant here."""
        return _explain_bucket(
            team=team,
            bucket=["Alpha", "Beta", "Gamma"],
            seed=seed,
            record="2-1",
            completed=[],
            coin_flip_groups=[],
            h2h_pts=self._H2H,
        )

    def test_middle_team_gives_nth_not_via_tiebreaker(self):
        """Beat Gamma but lost to Alpha — Phase 2 says 'giving Beta 2nd', not 'via tiebreaker'."""
        result = self._call("Beta", 2)
        assert "They beat Gamma but lost to Alpha" in result
        assert "giving Beta 2nd" in result
        assert "via tiebreaker" not in result

    def test_last_team_says_giving_nth(self):
        """Gamma lost to both — 'lost to both' branch still works (Phase 1, unaffected)."""
        result = self._call("Gamma", 3)
        assert "both of whom they lost to" in result


# ===========================================================================
# Phase 2: additional _non_h2h_clause branches
# ===========================================================================


class TestNonH2HClauseAdditional:
    """Tests for less common _non_h2h_clause result combinations."""

    def test_step2_generic_better(self):
        """Team tied an outside opponent while other lost — generic 'better result' clause."""
        sd = _make_step_data(
            step2={"Alpha": [1], "Beta": [0]},
            step4={"Alpha": [0], "Beta": [-7]},
            h2h_pd_cap_dict={},
            wl_totals={"Alpha": {"pa": 10}, "Beta": {"pa": 20}},
            outside=["Wayne"],
        )
        clause = _non_h2h_clause("Alpha", "Beta", ["Alpha", "Beta"], sd)
        assert clause is not None
        assert "better result vs Wayne" in clause

    def test_step2_team_didnt_play_other_won(self):
        """Team didn't play outside opponent but other won — reports the no-game disadvantage."""
        sd = _make_step_data(
            step2={"Alpha": [None], "Beta": [2]},
            step4={"Alpha": [None], "Beta": [7]},
            h2h_pd_cap_dict={},
            wl_totals={"Alpha": {"pa": 10}, "Beta": {"pa": 20}},
            outside=["Wayne"],
        )
        clause = _non_h2h_clause("Alpha", "Beta", ["Alpha", "Beta"], sd)
        assert clause is not None
        assert "Wayne" in clause
        assert "Beta won" in clause

    def test_step2_generic_worse(self):
        """Team lost to outside opponent while other only tied — generic 'worse result' clause."""
        sd = _make_step_data(
            step2={"Alpha": [0], "Beta": [1]},
            step4={"Alpha": [-7], "Beta": [0]},
            h2h_pd_cap_dict={},
            wl_totals={"Alpha": {"pa": 10}, "Beta": {"pa": 20}},
            outside=["Wayne"],
        )
        clause = _non_h2h_clause("Alpha", "Beta", ["Alpha", "Beta"], sd)
        assert clause is not None
        assert "worse result vs Wayne" in clause

    def test_step3_loser_branch(self):
        """Step 2 tied; team has worse H2H point margin than other."""
        sd = _make_step_data(
            step2={"Alpha": [2], "Beta": [2]},
            step4={"Alpha": [7], "Beta": [7]},
            h2h_pd_cap_dict={("Alpha", "Beta"): -5, ("Beta", "Alpha"): 5},
            wl_totals={"Alpha": {"pa": 10}, "Beta": {"pa": 20}},
            outside=["Wayne"],
        )
        clause = _non_h2h_clause("Alpha", "Beta", ["Alpha", "Beta"], sd)
        assert clause is not None
        assert "worse H2H point margin" in clause

    def test_step4_loser_branch(self):
        """Steps 2-3 tied; team has worse PD vs outside opponents."""
        sd = _make_step_data(
            step2={"Alpha": [2], "Beta": [2]},
            step4={"Alpha": [0], "Beta": [12]},
            h2h_pd_cap_dict={("Alpha", "Beta"): 0, ("Beta", "Alpha"): 0},
            wl_totals={"Alpha": {"pa": 10}, "Beta": {"pa": 20}},
            outside=["Wayne"],
        )
        clause = _non_h2h_clause("Alpha", "Beta", ["Alpha", "Beta"], sd)
        assert clause is not None
        assert "worse point differentials" in clause

    def test_step5_loser_branch(self):
        """Steps 2-4 tied; team allowed MORE points — reports the disadvantage."""
        sd = _make_step_data(
            step2={"Alpha": [2], "Beta": [2]},
            step4={"Alpha": [7], "Beta": [7]},
            h2h_pd_cap_dict={("Alpha", "Beta"): 0, ("Beta", "Alpha"): 0},
            wl_totals={"Alpha": {"pa": 42}, "Beta": {"pa": 14}},
            outside=["Wayne"],
        )
        clause = _non_h2h_clause("Alpha", "Beta", ["Alpha", "Beta"], sd)
        assert clause is not None
        assert "allowed more points" in clause
        assert "42" in clause


# ===========================================================================
# Phase 2: fallback paths when step_data is None or clause is None
# ===========================================================================


class TestExplainBucketFallbackPaths:
    """Tests for code paths that still say 'via tiebreaker' after Phase 2."""

    def test_two_way_step_data_all_tied_falls_to_via_tiebreaker(self):
        """2-way with step_data where _non_h2h_clause returns None → 'via tiebreaker'."""
        h2h: dict = defaultdict(float)
        # H2H equal; all step data also tied → clause is None → fallback
        sd = _make_step_data(
            step2={"Alpha": [2], "Beta": [2]},
            step4={"Alpha": [7], "Beta": [7]},
            h2h_pd_cap_dict={("Alpha", "Beta"): 0, ("Beta", "Alpha"): 0},
            wl_totals={"Alpha": {"pa": 14}, "Beta": {"pa": 14}},
            outside=["Wayne"],
        )
        result = _explain_bucket(
            team="Alpha",
            bucket=["Alpha", "Beta"],
            seed=1,
            record="2-1",
            completed=[],
            coin_flip_groups=[],
            h2h_pts=h2h,
            step_data=sd,
        )
        assert "via tiebreaker" in result

    def test_circular_three_way_no_step_data_falls_to_via_tiebreaker(self):
        """Circular beat1/lost1 without step_data → 'via tiebreaker' fallback (line 387)."""
        h2h: dict = defaultdict(float, {
            ("Alpha", "Beta"): 1.0, ("Beta", "Alpha"): 0.0,
            ("Beta", "Gamma"): 1.0, ("Gamma", "Beta"): 0.0,
            ("Gamma", "Alpha"): 1.0, ("Alpha", "Gamma"): 0.0,
        })
        result = _explain_bucket(
            team="Alpha",
            bucket=["Alpha", "Beta", "Gamma"],
            seed=1,
            record="2-2",
            completed=[],
            coin_flip_groups=[],
            h2h_pts=h2h,
        )
        assert "beat Beta but lost to Gamma" in result
        assert "via tiebreaker" in result

    def test_three_way_mixed_fallback_with_step_data(self):
        """3-way mixed bucket (beat one, haven't played other) with step_data provides specific clause."""
        h2h: dict = defaultdict(float, {
            ("Alpha", "Beta"): 1.0, ("Beta", "Alpha"): 0.0,
            # Alpha vs Gamma: no H2H → 0.0 each (not played)
        })
        sd = _make_step_data(
            step2={"Alpha": [2], "Beta": [0], "Gamma": [2]},
            step4={"Alpha": [7], "Beta": [0], "Gamma": [7]},
            h2h_pd_cap_dict={},
            wl_totals={"Alpha": {"pa": 10}, "Beta": {"pa": 20}, "Gamma": {"pa": 15}},
            outside=["Wayne"],
        )
        result = _explain_bucket(
            team="Alpha",
            bucket=["Alpha", "Beta", "Gamma"],
            seed=1,
            record="2-1",
            completed=[],
            coin_flip_groups=[],
            h2h_pts=h2h,
            step_data=sd,
            bucket_seed_order=["Alpha", "Gamma", "Beta"],
        )
        assert "3-way tie" in result
        assert "placing Alpha 1st" in result
        assert "via tiebreaker" not in result

    def test_circular_three_way_with_step_data_all_tied_falls_to_via_tiebreaker(self):
        """Circular beat1/lost1 WITH step_data where clause is None → 'via tiebreaker' (line 381→387)."""
        h2h: dict = defaultdict(float, {
            ("Alpha", "Beta"): 1.0, ("Beta", "Alpha"): 0.0,
            ("Beta", "Gamma"): 1.0, ("Gamma", "Beta"): 0.0,
            ("Gamma", "Alpha"): 1.0, ("Alpha", "Gamma"): 0.0,
        })
        sd = _make_step_data(
            step2={"Alpha": [2], "Beta": [2], "Gamma": [2]},
            step4={"Alpha": [7], "Beta": [7], "Gamma": [7]},
            h2h_pd_cap_dict={
                ("Alpha", "Beta"): 0, ("Beta", "Alpha"): 0,
                ("Beta", "Gamma"): 0, ("Gamma", "Beta"): 0,
                ("Alpha", "Gamma"): 0, ("Gamma", "Alpha"): 0,
            },
            wl_totals={"Alpha": {"pa": 14}, "Beta": {"pa": 14}, "Gamma": {"pa": 14}},
            outside=["Wayne"],
        )
        result = _explain_bucket(
            team="Alpha",
            bucket=["Alpha", "Beta", "Gamma"],
            seed=1,
            record="2-2",
            completed=[],
            coin_flip_groups=[],
            h2h_pts=h2h,
            step_data=sd,
            bucket_seed_order=["Alpha", "Beta", "Gamma"],
        )
        assert "beat Beta but lost to Gamma" in result
        assert "via tiebreaker" in result

    def test_mixed_three_way_with_step_data_all_tied_falls_to_via_tiebreaker(self):
        """3-way mixed bucket with step_data where clause is None → 'via tiebreaker' (line 401→403)."""
        h2h: dict = defaultdict(float, {
            ("Alpha", "Beta"): 1.0, ("Beta", "Alpha"): 0.0,
        })
        sd = _make_step_data(
            step2={"Alpha": [2], "Beta": [2], "Gamma": [2]},
            step4={"Alpha": [7], "Beta": [7], "Gamma": [7]},
            h2h_pd_cap_dict={},
            wl_totals={"Alpha": {"pa": 14}, "Beta": {"pa": 14}, "Gamma": {"pa": 14}},
            outside=["Wayne"],
        )
        result = _explain_bucket(
            team="Alpha",
            bucket=["Alpha", "Beta", "Gamma"],
            seed=1,
            record="2-1",
            completed=[],
            coin_flip_groups=[],
            h2h_pts=h2h,
            step_data=sd,
            bucket_seed_order=["Alpha", "Gamma", "Beta"],
        )
        assert "3-way tie" in result
        assert "via tiebreaker" in result
