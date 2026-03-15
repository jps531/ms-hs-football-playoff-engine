"""Unit tests for pure helper functions in scenarios.py (Groups 1 & 4).

These tests require no game data — they exercise formatting utilities,
key-parsing helpers, minterm consolidation primitives, and playoff
probability calculators directly.
"""

import pytest

from backend.helpers.data_classes import BracketOdds, StandingsOdds
from backend.helpers.scenarios import (
    _flip_base_key,
    _parse_ge_key,
    compute_bracket_odds,
    compute_first_round_home_odds,
    consolidate_all,
    final_consolidation,
    merge_full_partition_remove_base,
    merge_ge_union_by_signature,
    merge_ge_union_unified,
    pct_str,
)

# ---------------------------------------------------------------------------
# pct_str
# ---------------------------------------------------------------------------


class TestPctStr:
    def test_round_percentages(self):
        assert pct_str(0.0) == "0%"
        assert pct_str(0.5) == "50%"
        assert pct_str(1.0) == "100%"
        assert pct_str(0.25) == "25%"

    def test_non_round_percentage(self):
        # 1/3 → 33.333...% — takes the else branch
        result = pct_str(1 / 3)
        assert result == "33%"

    def test_non_round_two_thirds(self):
        result = pct_str(2 / 3)
        assert result == "67%"


# ---------------------------------------------------------------------------
# _parse_ge_key
# ---------------------------------------------------------------------------


class TestParseGeKey:
    def test_valid_key(self):
        assert _parse_ge_key("A>B_GE3") == ("A>B", 3)

    def test_no_ge_marker_returns_none(self):
        # Line 115 — key has no _GE
        assert _parse_ge_key("A>B") is None

    def test_non_integer_threshold_returns_none(self):
        # Lines 119-120 — ValueError path
        assert _parse_ge_key("A>B_GExyz") is None

    def test_ge_zero(self):
        assert _parse_ge_key("A>B_GE0") == ("A>B", 0)


# ---------------------------------------------------------------------------
# _flip_base_key
# ---------------------------------------------------------------------------


class TestFlipBaseKey:
    def test_flips_matchup_key(self):
        assert _flip_base_key("A>B") == "B>A"

    def test_no_arrow_returns_unchanged(self):
        # Line 412 — key with no ">"
        assert _flip_base_key("NOARROW") == "NOARROW"

    def test_empty_string(self):
        assert _flip_base_key("") == ""


# ---------------------------------------------------------------------------
# final_consolidation
# ---------------------------------------------------------------------------


class TestFinalConsolidation:
    def test_removes_contradictory_keys(self):
        # "A>B" appears True and False → stripped; "C>D" is constant → kept
        dicts = [
            {"A>B": True, "C>D": True},
            {"A>B": False, "C>D": True},
        ]
        result = final_consolidation(dicts)
        assert result == [{"C>D": True}]

    def test_deduplicates_after_stripping(self):
        # After stripping "A>B", both dicts become {"C>D": True} — deduplicated to one
        dicts = [
            {"A>B": True, "C>D": True},
            {"A>B": False, "C>D": True},
            {"A>B": True, "C>D": True},
        ]
        result = final_consolidation(dicts)
        assert len(result) == 1
        assert result[0] == {"C>D": True}

    def test_no_contradictions_passthrough(self):
        dicts = [{"A>B": True}, {"C>D": False}]
        result = final_consolidation(dicts)
        assert len(result) == 2

    def test_all_contradictory_produces_empty_dicts(self):
        # All keys contradictory → every dict stripped to {} → empty dicts filtered
        dicts = [{"A>B": True}, {"A>B": False}]
        result = final_consolidation(dicts)
        assert result == []


# ---------------------------------------------------------------------------
# consolidate_all — debug=True path
# ---------------------------------------------------------------------------


class TestConsolidateAllDebug:
    def test_debug_mode_produces_same_result(self, capsys):
        dicts = [{"A>B": True, "C>D": True}, {"A>B": False, "C>D": True}]
        normal = consolidate_all(dicts, debug=False)
        debug_result = consolidate_all(dicts, debug=True)
        assert debug_result == normal

    def test_debug_mode_prints_output(self, capsys):
        dicts = [{"A>B": True}]
        consolidate_all(dicts, debug=True)
        captured = capsys.readouterr()
        assert "Starting full consolidation" in captured.out


# ---------------------------------------------------------------------------
# compute_bracket_odds
# ---------------------------------------------------------------------------


def _make_odds(school: str, p_playoffs: float) -> StandingsOdds:
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
    def test_4_round_bracket_second_round_is_zero(self):
        # 5A–7A have 4 rounds — no second_round game
        odds = {"TeamA": _make_odds("TeamA", 1.0)}
        result = compute_bracket_odds(4, odds)
        assert result["TeamA"].second_round == pytest.approx(0.0)

    def test_5_round_bracket_second_round_nonzero(self):
        # 1A–4A have 5 rounds — second_round = p * 0.5
        odds = {"TeamA": _make_odds("TeamA", 1.0)}
        result = compute_bracket_odds(5, odds)
        assert result["TeamA"].second_round == pytest.approx(0.5)

    def test_4_round_probabilities(self):
        odds = {"TeamA": _make_odds("TeamA", 1.0)}
        r = compute_bracket_odds(4, odds)["TeamA"]
        assert r.quarterfinals == pytest.approx(0.5)  # 0.5^1
        assert r.semifinals == pytest.approx(0.25)  # 0.5^2
        assert r.finals == pytest.approx(0.125)  # 0.5^3
        assert r.champion == pytest.approx(0.0625)  # 0.5^4

    def test_5_round_probabilities(self):
        odds = {"TeamA": _make_odds("TeamA", 1.0)}
        r = compute_bracket_odds(5, odds)["TeamA"]
        assert r.second_round == pytest.approx(0.5)  # 0.5^1
        assert r.quarterfinals == pytest.approx(0.25)  # 0.5^2
        assert r.semifinals == pytest.approx(0.125)  # 0.5^3
        assert r.finals == pytest.approx(0.0625)  # 0.5^4
        assert r.champion == pytest.approx(0.03125)  # 0.5^5

    def test_scales_with_p_playoffs(self):
        odds = {"TeamA": _make_odds("TeamA", 0.5)}
        r = compute_bracket_odds(4, odds)["TeamA"]
        assert r.champion == pytest.approx(0.5 * 0.0625)

    def test_returns_bracket_odds_type(self):
        odds = {"TeamA": _make_odds("TeamA", 1.0)}
        result = compute_bracket_odds(4, odds)
        assert isinstance(result["TeamA"], BracketOdds)


# ---------------------------------------------------------------------------
# compute_first_round_home_odds
# ---------------------------------------------------------------------------


def _make_full_odds(school: str, p1: float, p2: float, p3: float, p4: float) -> StandingsOdds:
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
    def test_seeds_1_and_2_are_home(self):
        odds = {"TeamA": _make_full_odds("TeamA", 0.5, 0.3, 0.2, 0.0)}
        result = compute_first_round_home_odds(frozenset({1, 2}), odds)
        assert result["TeamA"] == pytest.approx(0.8)

    def test_only_seed_1_is_home(self):
        odds = {"TeamA": _make_full_odds("TeamA", 0.5, 0.3, 0.2, 0.0)}
        result = compute_first_round_home_odds(frozenset({1}), odds)
        assert result["TeamA"] == pytest.approx(0.5)

    def test_no_home_seeds(self):
        odds = {"TeamA": _make_full_odds("TeamA", 0.5, 0.3, 0.2, 0.0)}
        result = compute_first_round_home_odds(frozenset(), odds)
        assert result["TeamA"] == pytest.approx(0.0)

    def test_all_four_seeds_home(self):
        odds = {"TeamA": _make_full_odds("TeamA", 0.25, 0.25, 0.25, 0.25)}
        result = compute_first_round_home_odds(frozenset({1, 2, 3, 4}), odds)
        assert result["TeamA"] == pytest.approx(1.0)

    def test_eliminated_team_zero(self):
        odds = {"TeamA": _make_full_odds("TeamA", 0.0, 0.0, 0.0, 0.0)}
        result = compute_first_round_home_odds(frozenset({1, 2}), odds)
        assert result["TeamA"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# merge_full_partition_remove_base
# ---------------------------------------------------------------------------


class TestMergeFullPartitionRemoveBase:
    def test_nonoverlapping_intervals_no_collapse(self):
        # Two disjoint GE intervals don't cover [1,inf) — no collapse.
        # Covers the interval-merging loop (lines 353-362) with merged len > 1.
        dicts = [
            {"A>B": False},
            {"A>B_GE1": True, "A>B_GE3": False},
            {"A>B_GE5": True, "A>B_GE7": False},
        ]
        result = merge_full_partition_remove_base(dicts)
        assert result == dicts

    def test_overlapping_intervals_collapse_to_empty_sig(self):
        # [1,3) ∪ [2,inf) → [1,inf): full partition → base key dropped entirely.
        # Covers collapse path (lines 364-367) and replacement dedup (372-375).
        dicts = [
            {"A>B": False},
            {"A>B_GE1": True, "A>B_GE3": False},
            {"A>B_GE2": True},
        ]
        result = merge_full_partition_remove_base(dicts)
        assert result == [{}]

    def test_base_true_adds_win_threshold_interval(self):
        # has_base_true appends (win_threshold, inf) — covers line 349.
        # False + True together cover the full domain → collapse.
        dicts = [
            {"A>B": False},
            {"A>B": True},
        ]
        result = merge_full_partition_remove_base(dicts)
        assert result == [{}]

    def test_base_true_adds_win_threshold_interval_with_context(self):
        # Same as above but dicts share a non-A>B key, so sig is non-empty.
        dicts = [
            {"A>B": False, "C>D": True},
            {"A>B": True, "C>D": True},
        ]
        result = merge_full_partition_remove_base(dicts)
        assert result == [{"C>D": True}]

    def test_contradictory_ge_bounds_no_interval_recorded(self):
        # lo=5 > hi=3 → interval skipped (line 335->337).
        # No valid intervals and no base_true → intervals list stays empty → no collapse.
        dicts = [
            {"A>B": False},
            {"A>B_GE5": True, "A>B_GE3": False},
        ]
        result = merge_full_partition_remove_base(dicts)
        assert result == dicts

    def test_no_base_false_no_collapse(self):
        # has_base_false is never set → condition at line 345 skips the group.
        dicts = [
            {"A>B_GE1": True, "A>B_GE3": False},
            {"A>B_GE3": True},
        ]
        result = merge_full_partition_remove_base(dicts)
        assert result == dicts


# ---------------------------------------------------------------------------
# merge_ge_union_unified
# ---------------------------------------------------------------------------


class TestMergeGeUnionUnified:
    def test_adjacent_intervals_collapse_to_base_true(self):
        # [1,3) and [3,inf) are adjacent → merge to [1,inf) → base=True (line 480).
        dicts = [
            {"A>B_GE1": True, "A>B_GE3": False},
            {"A>B_GE3": True},
        ]
        result = merge_ge_union_unified(dicts)
        assert result == [{"A>B": True}]

    def test_adjacent_finite_intervals_collapse_to_ge_range(self):
        # [2,4) and [4,5) → merge to [2,5): finite both ends → GE range (lines 481-483).
        dicts = [
            {"A>B_GE2": True, "A>B_GE4": False, "C>D": True},
            {"A>B_GE4": True, "A>B_GE5": False, "C>D": True},
        ]
        result = merge_ge_union_unified(dicts)
        assert result == [{"C>D": True, "A>B_GE2": True, "A>B_GE5": False}]

    def test_single_high_inf_interval_not_collapsed(self):
        # [2,inf) ∪ [3,inf) → [2,inf), L=2 > win_threshold=1, R=inf → else: continue (line 484).
        dicts = [
            {"A>B_GE2": True, "C>D": True},
            {"A>B_GE3": True, "C>D": True},
        ]
        result = merge_ge_union_unified(dicts)
        assert result == dicts

    def test_single_entry_skipped(self):
        # Only 1 entry for the (sig, base) group → len < 2 → skipped (line 456).
        dicts = [{"A>B_GE1": True}]
        result = merge_ge_union_unified(dicts)
        assert result == dicts

    def test_base_explicitly_present_skipped(self):
        # Bare "A>B" key exists alongside GE keys → base_presence set → skipped (line 458).
        dicts = [
            {"A>B": True, "A>B_GE2": True},
            {"A>B_GE3": True},
        ]
        result = merge_ge_union_unified(dicts)
        assert result == dicts

    def test_nonadjacent_intervals_not_collapsed(self):
        # [1,3) and [5,7) don't merge to a single interval → skipped (line 473).
        dicts = [
            {"A>B_GE1": True, "A>B_GE3": False},
            {"A>B_GE5": True, "A>B_GE7": False},
        ]
        result = merge_ge_union_unified(dicts)
        assert result == dicts


# ---------------------------------------------------------------------------
# merge_ge_union_by_signature
# ---------------------------------------------------------------------------


class TestMergeGeUnionBySignature:
    def test_skips_contradictory_ge_bounds(self):
        # lo=5 > hi=3 → interval not added (line 551->548) → no valid intervals (line 562).
        dicts = [{"A>B_GE5": True, "A>B_GE3": False}]
        result = merge_ge_union_by_signature(dicts)
        assert result == dicts

    def test_skips_base_with_explicit_key(self):
        # "A>B" is an explicit non-GE key → base_explicit_present → skipped (line 559).
        dicts = [{"A>B": True, "A>B_GE2": True}]
        result = merge_ge_union_by_signature(dicts)
        assert result == dicts

    def test_single_high_inf_interval_aggressive_upper(self):
        # [2,inf) ∪ [3,inf) → [2,inf), L=2 > win_threshold=1, aggressive_upper=True
        # → emits base_GE2: True (line 583-584).
        dicts = [
            {"A>B_GE2": True},
            {"A>B_GE3": True},
        ]
        result = merge_ge_union_by_signature(dicts)
        assert result == [{"A>B_GE2": True}]

    def test_multiple_intervals_one_inf_aggressive_upper(self):
        # [1,3) ∪ [5,inf) → 2 pieces, one reaches inf, aggressive_upper=True
        # → emits base_GEl_min: True (lines 586-588).
        dicts = [
            {"A>B_GE1": True, "A>B_GE3": False},
            {"A>B_GE5": True},
        ]
        result = merge_ge_union_by_signature(dicts)
        assert result == [{"A>B_GE1": True}]

    def test_multiple_intervals_no_inf_aggressive_upper_false(self):
        # [1,3) and [5,7) — two finite intervals, aggressive_upper=False
        # → part={} (line 590) → no collapse (line 592->557).
        dicts = [
            {"A>B_GE1": True, "A>B_GE3": False},
            {"A>B_GE5": True, "A>B_GE7": False},
        ]
        result = merge_ge_union_by_signature(dicts, aggressive_upper=False)
        assert result == dicts

    def test_single_finite_interval_collapses_to_ge_range(self):
        # [2,inf) with L <= win_threshold: [1,inf) collapses to base=True.
        dicts = [
            {"A>B_GE1": True, "A>B_GE3": False},
            {"A>B_GE3": True},
        ]
        result = merge_ge_union_by_signature(dicts)
        assert result == [{"A>B": True}]
