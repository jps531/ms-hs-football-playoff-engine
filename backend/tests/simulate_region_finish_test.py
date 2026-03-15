"""Tests for simulate_region_finish.py — pure helpers, integration, and golden-output snapshot.

Group 1: Unit tests for pure helper functions (no game data needed).
Group 2: Integration tests using 3-7A fixture data.
Group 3: Golden-output snapshot test for scenarios_text_from_team_seed_ordered.
"""

import math

import pytest

from backend.scripts.simulate_region_finish import (
    EnumerateRegionResult,
    _band_sort_key,
    _block_sort_key,
    _canon_matchup,
    _canon_pair,
    _classify_clause,
    _coverage_collapse_blocks,
    _expand_signature_atoms_global,
    _flip,
    _global_partitions_for_base,
    _interval_for_base,
    _interval_of_clause,
    _is_complement,
    _is_ge_key,
    _normalize_clause_text,
    _parse_ge,
    _render_clause_lines_ordered,
    _touching,
    _try_merge_neighbor,
    _union_intervals,
    clauses_for_m,
    enumerate_region_pure,
    extract_pair,
    scenarios_text_from_team_seed_ordered,
)
from backend.tests.data.test_region_standings import (
    expected_3_7a_completed_games,
    expected_3_7a_completed_games_full,
    expected_3_7a_first_counts,
    expected_3_7a_first_counts_full,
    expected_3_7a_fourth_counts,
    expected_3_7a_fourth_counts_full,
    expected_3_7a_remaining_games,
    expected_3_7a_remaining_games_full,
    expected_3_7a_second_counts,
    expected_3_7a_second_counts_full,
    expected_3_7a_third_counts,
    expected_3_7a_third_counts_full,
    teams_3_7a,
)

# ---------------------------------------------------------------------------
# GROUP 1: Pure helper unit tests
# ---------------------------------------------------------------------------


class TestIsGeKey:
    """Tests for _is_ge_key — detects margin-encoded GE keys."""

    def test_ge_key_detected(self):
        """Key with both '>' and '_GE' is a GE key."""
        assert _is_ge_key("A>B_GE5") is True

    def test_non_ge_key_plain_win(self):
        """Plain win key without '_GE' is not a GE key."""
        assert _is_ge_key("A>B") is False

    def test_ge_key_no_arrow_rejected(self):
        """Key with '_GE' but no '>' arrow is not a GE key."""
        # has _GE but no > — should return False
        assert _is_ge_key("X_GE3") is False


class TestParseGe:
    """Tests for _parse_ge — splits a GE key into (base_key, threshold)."""

    def test_splits_base_and_threshold(self):
        """Standard GE key returns (base, integer threshold)."""
        assert _parse_ge("A>B_GE7") == ("A>B", 7)

    def test_large_threshold(self):
        """GE key with multi-word team names and double-digit threshold parses correctly."""
        assert _parse_ge("Team One>Team Two_GE12") == ("Team One>Team Two", 12)


class TestFlip:
    """Tests for _flip — reverses team order in an A>B key."""

    def test_flips_teams(self):
        """Multi-character team names flip correctly."""
        assert _flip("Alpha>Beta") == "Beta>Alpha"

    def test_single_char_teams(self):
        """Single-character team names flip correctly."""
        assert _flip("A>B") == "B>A"


class TestCanonPair:
    """Tests for _canon_pair — splits an A>B key into a (team_a, team_b) tuple."""

    def test_splits_into_tuple(self):
        """A>B key is split at '>' into a two-element tuple."""
        assert _canon_pair("Alpha>Beta") == ("Alpha", "Beta")


class TestIntervalForBase:
    """Tests for _interval_for_base — extracts the margin interval and winner from a minterm atom."""

    def test_base_winner_no_ge(self):
        """Plain win (no GE keys) yields interval [1, ∞) with A as winner."""
        atom = {"A>B": True}
        lo, hi, winner = _interval_for_base(atom, "A>B")
        assert lo == 1
        assert hi == math.inf
        assert winner == "A>B"

    def test_flip_winner(self):
        """When base key is False, the winner is the flipped orientation (B>A)."""
        # A>B is False => B wins => winner orientation is B>A
        atom = {"A>B": False}
        _lo, _hi, winner = _interval_for_base(atom, "A>B")
        assert winner == "B>A"

    def test_ge_true_sets_lo(self):
        """GE key True sets the lower bound of the margin interval."""
        atom = {"A>B_GE5": True}
        lo, _hi, winner = _interval_for_base(atom, "A>B")
        assert lo == 5
        assert winner == "A>B"

    def test_ge_false_sets_hi(self):
        """GE key False sets the upper bound; GE key True sets the lower bound."""
        # GE9 False => hi=9; GE3 True => lo=3
        atom = {"A>B_GE9": False, "A>B_GE3": True}
        lo, hi, _winner = _interval_for_base(atom, "A>B")
        assert lo == 3
        assert hi == 9

    def test_ge_only_no_base_key_winner_inferred(self):
        """When only a GE key is present (no plain base key), winner is inferred as base."""
        # Only a GE key present with no plain base key → winner inferred as base
        atom = {"A>B_GE4": True}
        _lo, _hi, winner = _interval_for_base(atom, "A>B")
        assert winner == "A>B"


class TestRenderClauseLinesOrdered:
    """Tests for _render_clause_lines_ordered — converts a minterm atom into human-readable lines."""

    def test_simple_win(self):
        """Plain win renders as 'A Win over B'."""
        atom = {"A>B": True}
        lines = _render_clause_lines_ordered(atom, ["A>B"])
        assert lines == ["A Win over B"]

    def test_simple_loss(self):
        """When A loses (False), renders as 'B Win over A'."""
        atom = {"A>B": False}
        lines = _render_clause_lines_ordered(atom, ["A>B"])
        assert lines == ["B Win over A"]

    def test_ge_margin(self):
        """GE margin renders as 'A Win over B by ≥ 5'."""
        atom = {"A>B_GE5": True}
        lines = _render_clause_lines_ordered(atom, ["A>B"])
        assert len(lines) == 1
        assert "≥ 5" in lines[0]

    def test_lt_margin(self):
        """GE1 True and GE8 False renders as 'by < 8' (lo=1 is implicit)."""
        # GE1 True, GE8 False => lo=1, hi=8 => "by < 8"
        atom = {"A>B_GE1": True, "A>B_GE8": False}
        lines = _render_clause_lines_ordered(atom, ["A>B"])
        assert len(lines) == 1
        assert "< 8" in lines[0]

    def test_ge_and_lt(self):
        """Both GE lower and upper bounds render as 'by ≥ 3 and < 9'."""
        atom = {"A>B_GE3": True, "A>B_GE9": False}
        lines = _render_clause_lines_ordered(atom, ["A>B"])
        assert len(lines) == 1
        assert "≥ 3" in lines[0]
        assert "< 9" in lines[0]

    def test_game_not_in_atom_produces_degenerate_clause(self):
        """A game listed in games_order but absent from the atom produces a degenerate clause, not silence."""
        # When a game in games_order has no data in the atom, _interval_for_base returns
        # the degenerate (1, 1, base) result, which renders as "by < 1 points".
        # The function does NOT silently skip such games.
        atom = {"A>B": True}
        lines = _render_clause_lines_ordered(atom, ["A>B", "C>D"])
        assert "A Win over B" in lines[0]
        # C>D has no data — degenerate clause is emitted (not silently skipped)
        assert any("C" in line for line in lines)


class TestTouching:
    """Tests for _touching — checks whether two margin intervals are adjacent or overlapping."""

    def test_touching_at_boundary(self):
        """Intervals that share an endpoint are touching."""
        assert _touching((1, 5), (5, math.inf)) is True

    def test_overlapping(self):
        """Overlapping intervals are touching."""
        assert _touching((1, 7), (4, 10)) is True

    def test_gap_between(self):
        """Intervals with a gap between them are not touching."""
        assert _touching((1, 3), (5, 7)) is False


class TestTryMergeNeighbor:
    """Tests for _try_merge_neighbor using games_order = ['A>B', 'C>D']."""

    games_order = ["A>B", "C>D"]

    def _make_bands(self, ab_lo, ab_hi, ab_winner, cd_lo, cd_hi, cd_winner):
        """Build a bands dict with intervals for A>B and C>D."""
        return {
            "A>B": (ab_lo, ab_hi, ab_winner),
            "C>D": (cd_lo, cd_hi, cd_winner),
        }

    def test_merge_adjacent_bands(self):
        """Adjacent bands with same winner on A>B merge into [1,∞)."""
        # A>B bands [1,5) and [5,inf) — same winner, should merge to [1,inf)
        a_bands = self._make_bands(1, 5, "A>B", 1, math.inf, "C>D")
        b_bands = self._make_bands(5, math.inf, "A>B", 1, math.inf, "C>D")
        merged, result = _try_merge_neighbor(a_bands, b_bands, True, self.games_order)
        assert merged is True
        assert result["A>B"][0] == 1
        assert result["A>B"][1] == math.inf

    def test_no_merge_seed_mismatch(self):
        """Same-seed flag False prevents merging even if bands are adjacent."""
        a_bands = self._make_bands(1, 5, "A>B", 1, math.inf, "C>D")
        b_bands = self._make_bands(5, math.inf, "A>B", 1, math.inf, "C>D")
        merged, result = _try_merge_neighbor(a_bands, b_bands, False, self.games_order)
        assert merged is False
        assert result is a_bands

    def test_no_merge_two_games_differ(self):
        """Two differing game bands means more than one diff → merge rejected."""
        # Both A>B and C>D differ on their bands — two diffs → no merge
        a_bands = self._make_bands(1, 5, "A>B", 1, 5, "C>D")
        b_bands = self._make_bands(5, math.inf, "A>B", 5, math.inf, "C>D")
        merged, _result = _try_merge_neighbor(a_bands, b_bands, True, self.games_order)
        assert merged is False

    def test_no_merge_non_touching(self):
        """Non-touching bands on A>B are not merged."""
        # [1,3) and [7,inf) are not touching
        a_bands = self._make_bands(1, 3, "A>B", 1, math.inf, "C>D")
        b_bands = self._make_bands(7, math.inf, "A>B", 1, math.inf, "C>D")
        merged, _result = _try_merge_neighbor(a_bands, b_bands, True, self.games_order)
        assert merged is False

    def test_merge_identical(self):
        """Identical bands trivially merge (zero diffs); returns the first bands dict unchanged."""
        # Identical bands → trivially merged
        a_bands = self._make_bands(1, math.inf, "A>B", 1, math.inf, "C>D")
        b_bands = self._make_bands(1, math.inf, "A>B", 1, math.inf, "C>D")
        merged, result = _try_merge_neighbor(a_bands, b_bands, True, self.games_order)
        assert merged is True
        assert result is a_bands


class TestNormalizeClauseText:
    """Tests for _normalize_clause_text — drops redundant ≥1 and <13 margin qualifiers."""

    def test_ge1_and_lt_simplifies(self):
        """'by ≥ 1 and < N' simplifies to 'by < N' (≥1 is always true for a win)."""
        result = _normalize_clause_text("A Win over B by ≥ 1 and < 7 points")
        assert result == "A Win over B by < 7 points"

    def test_ge1_only_drops_margin(self):
        """'by ≥ 1' alone is dropped entirely, leaving just the win statement."""
        result = _normalize_clause_text("A Win over B by ≥ 1 points")
        assert result == "A Win over B"

    def test_lt13_drops_margin(self):
        """'by < 13' is dropped (the PD cap is 12, so < 13 is always true)."""
        result = _normalize_clause_text("A Win over B by < 13 points")
        assert result == "A Win over B"

    def test_ge1_lt13_drops_both(self):
        """Both '≥ 1' and '< 13' are redundant and both are dropped."""
        result = _normalize_clause_text("A Win over B by ≥ 1 and < 13 points")
        assert result == "A Win over B"

    def test_ge5_unchanged(self):
        """Meaningful margin constraints (≥5) are preserved unchanged."""
        result = _normalize_clause_text("A Win over B by ≥ 5 points")
        assert result == "A Win over B by ≥ 5 points"


class TestExtractPair:
    """Tests for extract_pair — parses a rendered clause back into (team_a, team_b, kind, threshold)."""

    def test_base_win(self):
        """Plain 'X Win over Y' returns kind='base' with no threshold."""
        assert extract_pair("Brandon Win over Meridian") == ("Brandon", "Meridian", "base", None)

    def test_ge_margin(self):
        """'by ≥ N' returns kind='ge' with the threshold."""
        assert extract_pair("Brandon Win over Meridian by ≥ 5 points") == ("Brandon", "Meridian", "ge", 5)

    def test_lt_margin(self):
        """'by < N' returns kind='lt' with the threshold."""
        assert extract_pair("Brandon Win over Meridian by < 8 points") == ("Brandon", "Meridian", "lt", 8)

    def test_no_win_over(self):
        """Text without 'Win over' returns None."""
        assert extract_pair("some other text") is None

    def test_ge_non_int_threshold_returns_none_thr(self):
        """Non-integer threshold after 'by ≥' is caught and returns thr=None."""
        result = extract_pair("A Win over B by ≥ not-a-number points")
        assert result is not None
        _a, _b, kind, thr = result
        assert kind == "ge"
        assert thr is None

    def test_lt_non_int_threshold_returns_none_thr(self):
        """Non-integer threshold after 'by <' is caught and returns thr=None."""
        result = extract_pair("A Win over B by < not-a-number points")
        assert result is not None
        _a, _b, kind, thr = result
        assert kind == "lt"
        assert thr is None


class TestIsComplement:
    """Tests for _is_complement — determines if two parsed clause pairs are logical complements."""

    def test_base_complements(self):
        """'A beats B' and 'B beats A' are complements."""
        assert _is_complement(("A", "B", "base", None), ("B", "A", "base", None)) is True

    def test_base_non_complement(self):
        """Two identical 'A beats B' clauses are not complements."""
        assert _is_complement(("A", "B", "base", None), ("A", "B", "base", None)) is False

    def test_margin_complements(self):
        """'ge N' and 'lt N' for the same matchup and threshold are complements."""
        # same a, b, threshold; kinds are "ge" and "lt" → complements
        assert _is_complement(("A", "B", "ge", 5), ("A", "B", "lt", 5)) is True

    def test_none_input(self):
        """None input returns False (not a complement of anything)."""
        assert _is_complement(None, ("A", "B", "base", None)) is False

    def test_non_matching_kinds_return_false(self):
        """Two 'ge' clauses with different thresholds are not complements."""
        assert _is_complement(("A", "B", "ge", 5), ("A", "B", "ge", 7)) is False

    def test_same_direction_base_not_complement(self):
        """Two clauses pointing the same direction are not complements even with different teams."""
        assert _is_complement(("A", "B", "base", None), ("A", "C", "base", None)) is False


class TestScenariosTextFromTeamSeedOrdered:
    """Tests for scenarios_text_from_team_seed_ordered with small synthetic inputs."""

    def _minimal_map(self):
        """A minimal team_seed_map: team A, seed 1, one minterm A>B=True."""
        return {"A": {1: [{"A>B": True}]}}

    def test_contains_scenario_label(self):
        """Output includes a 'Scenario A' label."""
        text = scenarios_text_from_team_seed_ordered(self._minimal_map(), ["A>B"])
        assert "Scenario A" in text

    def test_winner_rendered_in_output(self):
        """The winning team's name appears in the rendered text."""
        text = scenarios_text_from_team_seed_ordered(self._minimal_map(), ["A>B"])
        assert "A Win over B" in text



# ---------------------------------------------------------------------------
# GROUP 2: Integration tests using 3-7A fixture data
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def result_3_7a():
    """Run enumerate_region_pure once for the pre-final-week 3-7A scenario."""
    return enumerate_region_pure(
        teams_3_7a,
        expected_3_7a_completed_games,
        expected_3_7a_remaining_games,
    )


@pytest.fixture(scope="module")
def result_3_7a_full():
    """Run enumerate_region_pure once for the full-season 3-7A scenario."""
    return enumerate_region_pure(
        teams_3_7a,
        expected_3_7a_completed_games_full,
        expected_3_7a_remaining_games_full,
    )


class TestEnumerateRegionPure37A:
    """Pre-final-week tests: 3 remaining games, margin-sensitive tiebreakers."""

    def test_returns_correct_type(self, result_3_7a):
        """enumerate_region_pure returns an EnumerateRegionResult."""
        assert isinstance(result_3_7a, EnumerateRegionResult)

    def test_boolean_game_vars(self, result_3_7a):
        """boolean_game_vars lists all 3 remaining games in fixture order."""
        # Order mirrors the RemainingGame list in the fixture
        expected = [
            ("Brandon>Meridian", "Brandon", "Meridian"),
            ("Oak Grove>Pearl", "Oak Grove", "Pearl"),
            ("Northwest Rankin>Petal", "Northwest Rankin", "Petal"),
        ]
        assert result_3_7a.boolean_game_vars == expected

    def test_denom(self, result_3_7a):
        """3 remaining games → denominator is 2^3 = 8."""
        assert result_3_7a.denom == pytest.approx(8.0)

    def test_first_counts(self, result_3_7a):
        """First-seed counts match the 3-7A fixture; teams absent from fixture have count 0."""
        # Fixture only includes teams with nonzero counts; check those and verify
        # remaining teams are zero.
        for team, count in expected_3_7a_first_counts.items():
            assert result_3_7a.first_counts.get(team, 0.0) == pytest.approx(count)
        for team in teams_3_7a:
            if team not in expected_3_7a_first_counts:
                assert result_3_7a.first_counts.get(team, 0.0) == pytest.approx(0.0)

    def test_second_counts(self, result_3_7a):
        """Second-seed counts match the 3-7A fixture."""
        for team, count in expected_3_7a_second_counts.items():
            assert result_3_7a.second_counts.get(team, 0.0) == pytest.approx(count)
        for team in teams_3_7a:
            if team not in expected_3_7a_second_counts:
                assert result_3_7a.second_counts.get(team, 0.0) == pytest.approx(0.0)

    def test_third_counts(self, result_3_7a):
        """Third-seed counts match the 3-7A fixture."""
        for team, count in expected_3_7a_third_counts.items():
            assert result_3_7a.third_counts.get(team, 0.0) == pytest.approx(count)
        for team in teams_3_7a:
            if team not in expected_3_7a_third_counts:
                assert result_3_7a.third_counts.get(team, 0.0) == pytest.approx(0.0)

    def test_fourth_counts(self, result_3_7a):
        """Fourth-seed counts match the 3-7A fixture."""
        for team, count in expected_3_7a_fourth_counts.items():
            assert result_3_7a.fourth_counts.get(team, 0.0) == pytest.approx(count)
        for team in teams_3_7a:
            if team not in expected_3_7a_fourth_counts:
                assert result_3_7a.fourth_counts.get(team, 0.0) == pytest.approx(0.0)

    def test_results_length(self, result_3_7a):
        """Results list has one entry per team."""
        assert len(result_3_7a.results) == len(teams_3_7a)

    def test_results_meridian_eliminated(self, result_3_7a):
        """Meridian is eliminated in the pre-final-week fixture (0 paths to playoffs)."""
        meridian_row = next(r for r in result_3_7a.results if r[0] == "Meridian")
        # Index 8 is the 'eliminated' field: (school, p1, p2, p3, p4, p_playoffs, final_playoffs, clinched, eliminated)
        eliminated = meridian_row[8]
        assert eliminated is True

    def test_results_oak_grove_clinched(self, result_3_7a):
        """Oak Grove has clinched a playoff spot in the pre-final-week fixture."""
        oak_row = next(r for r in result_3_7a.results if r[0] == "Oak Grove")
        clinched = oak_row[7]
        assert clinched is True

    def test_scenario_minterms_has_all_teams_except_meridian(self, result_3_7a):
        """Meridian is eliminated so it has no in-playoff seeds in scenario_minterms."""
        # Meridian is eliminated; it should either be absent from scenario_minterms
        # or all its seeds should be >= 5 (out of playoffs)
        smt = result_3_7a.scenario_minterms
        if "Meridian" in smt:
            seeds = list(smt["Meridian"].keys())
            assert all(s >= 5 for s in seeds), f"Meridian has in-playoff seeds: {seeds}"


class TestEnumerateRegionPureFull37A:
    """Full-season tests: 0 remaining games, deterministic outcome."""

    def test_denom_is_one(self, result_3_7a_full):
        """No remaining games → only one outcome → denom is 1."""
        assert result_3_7a_full.denom == pytest.approx(1.0)

    def test_boolean_game_vars_empty(self, result_3_7a_full):
        """Full season with no remaining games has an empty boolean_game_vars list."""
        assert result_3_7a_full.boolean_game_vars == []

    def test_first_counts_oak_grove(self, result_3_7a_full):
        """Oak Grove is the sole 1-seed; all other teams have first-count 0."""
        # Fixture only contains the one team with count=1; rest should be 0
        for team, count in expected_3_7a_first_counts_full.items():
            assert result_3_7a_full.first_counts.get(team, 0.0) == pytest.approx(count)
        for team in teams_3_7a:
            if team not in expected_3_7a_first_counts_full:
                assert result_3_7a_full.first_counts.get(team, 0.0) == pytest.approx(0.0)

    def test_second_counts_petal(self, result_3_7a_full):
        """Petal is the sole 2-seed in the full-season fixture."""
        for team, count in expected_3_7a_second_counts_full.items():
            assert result_3_7a_full.second_counts.get(team, 0.0) == pytest.approx(count)
        for team in teams_3_7a:
            if team not in expected_3_7a_second_counts_full:
                assert result_3_7a_full.second_counts.get(team, 0.0) == pytest.approx(0.0)

    def test_third_counts_brandon(self, result_3_7a_full):
        """Brandon is the sole 3-seed in the full-season fixture."""
        for team, count in expected_3_7a_third_counts_full.items():
            assert result_3_7a_full.third_counts.get(team, 0.0) == pytest.approx(count)
        for team in teams_3_7a:
            if team not in expected_3_7a_third_counts_full:
                assert result_3_7a_full.third_counts.get(team, 0.0) == pytest.approx(0.0)

    def test_fourth_counts_nwr(self, result_3_7a_full):
        """Northwest Rankin is the sole 4-seed in the full-season fixture."""
        for team, count in expected_3_7a_fourth_counts_full.items():
            assert result_3_7a_full.fourth_counts.get(team, 0.0) == pytest.approx(count)
        for team in teams_3_7a:
            if team not in expected_3_7a_fourth_counts_full:
                assert result_3_7a_full.fourth_counts.get(team, 0.0) == pytest.approx(0.0)

    def test_results_oak_grove_p1_is_one(self, result_3_7a_full):
        """Oak Grove's first-seed probability is 1.0 in the full-season result."""
        oak_row = next(r for r in result_3_7a_full.results if r[0] == "Oak Grove")
        p1 = oak_row[1]
        assert p1 == pytest.approx(1.0)

    def test_results_clinched_teams(self, result_3_7a_full):
        """Oak Grove, Petal, Brandon, NW Rankin are clinched; Meridian and Pearl are eliminated."""
        # Oak Grove, Petal, Brandon, NW Rankin all clinched; Meridian and Pearl eliminated
        result_map = {r[0]: r for r in result_3_7a_full.results}
        # clinched = index 7, eliminated = index 8
        for team in ["Oak Grove", "Petal", "Brandon", "Northwest Rankin"]:
            assert result_map[team][7] is True, f"{team} should be clinched"
        for team in ["Meridian", "Pearl"]:
            assert result_map[team][8] is True, f"{team} should be eliminated"


# ---------------------------------------------------------------------------
# GROUP 3: Golden-output snapshot test
# ---------------------------------------------------------------------------

# Generated by running enumerate_region_pure + scenarios_text_from_team_seed_ordered
# against the 3-7A pre-final-week fixture data. Regenerate if rendering logic changes intentionally.
_EXPECTED_3_7A_SCENARIOS_TEXT = (
    "Scenario A\nMeridian Win over Brandon\n    AND Pearl Win over Oak Grove\n    AND Petal Win over Northwest Rankin\n:\n1 Seed: Petal\n2 Seed: Pearl\n3 Seed: Oak Grove\n4 Seed: Brandon\n\n"
    "Scenario B\nMeridian Win over Brandon\n    AND Pearl Win over Oak Grove\n    AND Northwest Rankin Win over Petal\n:\n1 Seed: Northwest Rankin\n2 Seed: Pearl\n3 Seed: Petal\n4 Seed: Oak Grove\n\n"
    "Scenario C\nMeridian Win over Brandon\n    AND Oak Grove Win over Pearl\n    AND Petal Win over Northwest Rankin\n:\n1 Seed: Petal\n2 Seed: Oak Grove\n3 Seed: Brandon\n4 Seed: Northwest Rankin\n\n"
    "Scenario D\nMeridian Win over Brandon\n    AND Oak Grove Win over Pearl\n    AND Northwest Rankin Win over Petal\n:\n1 Seed: Oak Grove\n2 Seed: Northwest Rankin\n3 Seed: Petal\n4 Seed: Brandon\n\n"
    "Scenario E\nBrandon Win over Meridian\n    AND Pearl Win over Oak Grove\n    AND Petal Win over Northwest Rankin\n:\n1 Seed: Petal\n2 Seed: Pearl\n3 Seed: Oak Grove\n4 Seed: Brandon\n\n"
    "Scenario F\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl\n    AND Petal Win over Northwest Rankin\n:\n1 Seed: Petal\n2 Seed: Oak Grove\n3 Seed: Brandon\n4 Seed: Northwest Rankin\n\n"
    "Scenario G\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl\n    AND Northwest Rankin Win over Petal\n:\n1 Seed: Oak Grove\n2 Seed: Petal\n3 Seed: Brandon\n4 Seed: Northwest Rankin\n\n"
    "Scenario H\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl by < 1 points\n    AND Northwest Rankin Win over Petal by < 4 points\n:\n1 Seed: Oak Grove\n2 Seed: Petal\n3 Seed: Brandon\n4 Seed: Northwest Rankin\n\n"
    "Scenario I\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl by < 1 points\n    AND Northwest Rankin Win over Petal by \u2265 3 and < 4 points\n:\n1 Seed: Oak Grove\n2 Seed: Petal\n3 Seed: Northwest Rankin\n4 Seed: Pearl\n\n"
    "Scenario J\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl by < 1 points\n    AND Northwest Rankin Win over Petal by \u2265 3 and < 4 points\n:\n1 Seed: Petal\n2 Seed: Pearl\n3 Seed: Oak Grove\n4 Seed: Northwest Rankin\n\n"
    "Scenario K\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl by < 1 points\n    AND Northwest Rankin Win over Petal by \u2265 3 and < 4 points\n:\n1 Seed: Pearl\n2 Seed: Petal\n3 Seed: Northwest Rankin\n4 Seed: Oak Grove\n\n"
    "Scenario L\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl by < 1 points\n    AND Northwest Rankin Win over Petal by \u2265 4 and < 5 points\n:\n1 Seed: Oak Grove\n2 Seed: Petal\n3 Seed: Brandon\n4 Seed: Northwest Rankin\n\n"
    "Scenario M\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl by < 1 points\n    AND Northwest Rankin Win over Petal by \u2265 4 and < 5 points\n:\n1 Seed: Oak Grove\n2 Seed: Northwest Rankin\n3 Seed: Petal\n4 Seed: Pearl\n\n"
    "Scenario N\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl by < 1 points\n    AND Northwest Rankin Win over Petal by \u2265 4 and < 5 points\n:\n1 Seed: Northwest Rankin\n2 Seed: Pearl\n3 Seed: Petal\n4 Seed: Oak Grove\n\n"
    "Scenario O\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl by < 1 points\n    AND Northwest Rankin Win over Petal by \u2265 4 and < 5 points\n:\n1 Seed: Pearl\n2 Seed: Northwest Rankin\n3 Seed: Petal\n4 Seed: Oak Grove\n\n"
    "Scenario P\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl by < 1 points\n    AND Northwest Rankin Win over Petal by \u2265 5 and < 6 points\n:\n1 Seed: Oak Grove\n2 Seed: Petal\n3 Seed: Brandon\n4 Seed: Northwest Rankin\n\n"
    "Scenario Q\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl by < 1 points\n    AND Northwest Rankin Win over Petal by \u2265 5 and < 6 points\n:\n1 Seed: Oak Grove\n2 Seed: Northwest Rankin\n3 Seed: Petal\n4 Seed: Pearl\n\n"
    "Scenario R\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl by < 1 points\n    AND Northwest Rankin Win over Petal by \u2265 5 and < 6 points\n:\n1 Seed: Northwest Rankin\n2 Seed: Pearl\n3 Seed: Oak Grove\n4 Seed: Petal\n\n"
    "Scenario S\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl by < 1 points\n    AND Northwest Rankin Win over Petal by \u2265 5 and < 6 points\n:\n1 Seed: Pearl\n2 Seed: Northwest Rankin\n3 Seed: Petal\n4 Seed: Oak Grove\n\n"
    "Scenario T\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl by < 1 points\n    AND Northwest Rankin Win over Petal by \u2265 6 points\n:\n1 Seed: Oak Grove\n2 Seed: Petal\n3 Seed: Brandon\n4 Seed: Northwest Rankin\n\n"
    "Scenario U\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl by < 1 points\n    AND Northwest Rankin Win over Petal by \u2265 6 points\n:\n1 Seed: Oak Grove\n2 Seed: Northwest Rankin\n3 Seed: Petal\n4 Seed: Pearl\n\n"
    "Scenario V\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl by < 1 points\n    AND Northwest Rankin Win over Petal by \u2265 6 points\n:\n1 Seed: Oak Grove\n2 Seed: Northwest Rankin\n3 Seed: Pearl\n4 Seed: Petal\n\n"
    "Scenario W\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl by < 1 points\n    AND Northwest Rankin Win over Petal by \u2265 6 points\n:\n1 Seed: Northwest Rankin\n2 Seed: Pearl\n3 Seed: Oak Grove\n4 Seed: Petal\n\n"
    "Scenario X\nBrandon Win over Meridian\n    AND Oak Grove Win over Pearl by < 1 points\n    AND Northwest Rankin Win over Petal by \u2265 6 points\n:\n1 Seed: Pearl\n2 Seed: Northwest Rankin\n3 Seed: Petal\n4 Seed: Oak Grove"
)


class TestScenariosTextSnapshot37A:
    """Golden-output snapshot tests for scenarios_text_from_team_seed_ordered against 3-7A data."""

    def test_scenarios_text_matches_golden(self, result_3_7a):
        """Rendered scenario text matches the pre-captured golden snapshot."""
        if _EXPECTED_3_7A_SCENARIOS_TEXT is None:
            pytest.skip("Golden snapshot not yet captured — run this file directly to generate it.")
        games_order = [var_name for var_name, _a, _b in result_3_7a.boolean_game_vars]
        text = scenarios_text_from_team_seed_ordered(result_3_7a.scenario_minterms, games_order)
        assert text == _EXPECTED_3_7A_SCENARIOS_TEXT


# ---------------------------------------------------------------------------
# GROUP 4: Missing branches in already-covered helpers
# ---------------------------------------------------------------------------


class TestIntervalForBaseMissingBranches:
    """Additional branches not exercised by Group 1 tests."""

    def test_flip_winner_with_ge_keys(self):
        """When base is False AND GE keys are present, the GE info is ignored and (1,1,flip) is returned."""
        # winner == _flip(base) fires before the has_ge block
        atom = {"A>B": False, "A>B_GE5": True}
        lo, hi, winner = _interval_for_base(atom, "A>B")
        assert winner == "B>A"
        assert (lo, hi) == (1, 1)

    def test_contradictory_ge_keys_returns_degenerate(self):
        """lo >= hi from contradictory GE keys (GE5=True, GE3=False) returns (1, 1, base)."""
        atom = {"A>B_GE5": True, "A>B_GE3": False}
        lo, hi, winner = _interval_for_base(atom, "A>B")
        assert (lo, hi) == (1, 1)
        assert winner == "A>B"

    def test_no_info_for_base_returns_base_as_winner(self):
        """Atom with no keys for the requested base returns (1,1,base) with base as winner."""
        lo, hi, winner = _interval_for_base({}, "A>B")
        assert winner == "A>B"
        assert (lo, hi) == (1, 1)


class TestTouchingMissingBranches:
    """Degenerate _touching case not covered in Group 1."""

    def test_degenerate_inf_lo_b_is_inf(self):
        """When hi_a is inf AND lo_b is inf the function returns False (degenerate guard)."""
        assert _touching((1, math.inf), (math.inf, math.inf)) is False


class TestTryMergeNeighborMissingBranches:
    """Winner-mismatch path not covered in Group 1."""

    games_order = ["A>B", "C>D"]

    def test_no_merge_winner_mismatch(self):
        """Different winners on any game short-circuits merge with False."""
        a_bands = {"A>B": (1, math.inf, "A>B"), "C>D": (1, math.inf, "C>D")}
        b_bands = {"A>B": (1, math.inf, "B>A"), "C>D": (1, math.inf, "C>D")}
        merged, result = _try_merge_neighbor(a_bands, b_bands, True, self.games_order)
        assert merged is False
        assert result is a_bands


class TestBandSortKey:
    """Tests for _band_sort_key including the loser_first=False branch."""

    def test_loser_first_true_flip_wins_group_zero(self):
        """loser_first=True: flip winner gets group 0 (losses listed first)."""
        atom = {"A>B": False}
        wg, _gran, _hir = _band_sort_key("A>B", atom, loser_first=True)
        assert wg == 0

    def test_loser_first_true_base_wins_group_one(self):
        """loser_first=True: base winner gets group 1."""
        atom = {"A>B": True}
        wg, _gran, _hir = _band_sort_key("A>B", atom, loser_first=True)
        assert wg == 1

    def test_loser_first_false_base_wins_group_zero(self):
        """loser_first=False: base winner gets group 0 (wins listed first)."""
        atom = {"A>B": True}
        wg, _gran, _hir = _band_sort_key("A>B", atom, loser_first=False)
        assert wg == 0

    def test_loser_first_false_flip_wins_group_one(self):
        """loser_first=False: flip winner gets group 1."""
        atom = {"A>B": False}
        wg, _gran, _hir = _band_sort_key("A>B", atom, loser_first=False)
        assert wg == 1


class TestGlobalPartitionsForBase:
    """Tests for _global_partitions_for_base, including the no-tail path."""

    def test_base_absent_returns_empty(self):
        """When the base has no global cuts, return []."""
        assert _global_partitions_for_base("A>B", {}, [(1, math.inf)]) == []

    def test_no_tail_path_omits_last_partition(self):
        """When no input band has hi=inf, the open-ended tail is NOT appended."""
        global_cuts = {"A>B": [1, 5, 9]}
        # All bands are finite — no tail
        bands = [(1, 5), (5, 9)]
        parts = _global_partitions_for_base("A>B", global_cuts, bands)
        assert all(hi != math.inf for (_, hi) in parts)

    def test_with_tail_appends_last_partition(self):
        """When at least one input band has hi=inf, the open-ended tail is included."""
        global_cuts = {"A>B": [1, 5, 9]}
        bands = [(1, math.inf)]
        parts = _global_partitions_for_base("A>B", global_cuts, bands)
        assert any(hi == math.inf for (_, hi) in parts)

    def test_uncovered_intermediate_piece_not_appended(self):
        """A piece between two cuts that is not covered by any input band is omitted."""
        # cuts = [1, 3, 7]; bands only covers [1, 3)
        # [3, 7) is not covered by bands → should be absent from result
        global_cuts = {"A>B": [1, 3, 7]}
        bands = [(1.0, 3.0)]
        parts = _global_partitions_for_base("A>B", global_cuts, bands)
        assert (1, 3) in parts
        assert all(lo < 3 or lo >= 7 for (lo, _hi) in parts)


class TestExpandSignatureAtomsGlobal:
    """Tests for _expand_signature_atoms_global, including the empty-group early return."""

    def test_empty_group_returns_empty(self):
        """An empty signature_group returns [] immediately."""
        assert _expand_signature_atoms_global([], {}) == []

    def test_fixed_only_returns_single_atom(self):
        """A group with no GE keys returns the fixed base assignment as a single atom."""
        group = [{"A>B": True}]
        global_cuts = {"A>B": [1]}
        result = _expand_signature_atoms_global(group, global_cuts)
        assert len(result) == 1
        assert result[0].get("A>B") is True


# ---------------------------------------------------------------------------
# GROUP 5: Legacy rendering pipeline (zero-coverage functions)
# ---------------------------------------------------------------------------


class TestCanonMatchup:
    """Tests for _canon_matchup — canonical (lesser, greater) pair."""

    def test_already_ordered(self):
        """Teams already in alphabetical order are returned as-is."""
        assert _canon_matchup("Alpha", "Beta") == ("Alpha", "Beta")

    def test_reversed_when_b_less(self):
        """When b < a alphabetically, order is swapped."""
        assert _canon_matchup("Zeta", "Alpha") == ("Alpha", "Zeta")

    def test_single_char(self):
        """Single-character teams follow the same rule."""
        assert _canon_matchup("B", "A") == ("A", "B")


class TestClassifyClause:
    """Tests for _classify_clause — sort key (idx, comp_rank, text)."""

    _matchup_index = {"Brandon>Meridian": 0, "Oak Grove>Pearl": 1}

    def test_base_clause_comp_rank_zero(self):
        """A plain 'Win over' clause has comparator rank 0."""
        result = _classify_clause("Brandon Win over Meridian", self._matchup_index)
        assert result[1] == 0

    def test_ge_clause_comp_rank_one(self):
        """A '≥ N' clause has comparator rank 1."""
        result = _classify_clause("Brandon Win over Meridian by ≥ 5 points", self._matchup_index)
        assert result[1] == 1

    def test_lt_clause_comp_rank_two(self):
        """A '< N' clause has comparator rank 2."""
        result = _classify_clause("Brandon Win over Meridian by < 5 points", self._matchup_index)
        assert result[1] == 2

    def test_known_matchup_uses_index(self):
        """A known matchup returns its index from matchup_index."""
        result = _classify_clause("Brandon Win over Meridian", self._matchup_index)
        assert result[0] == 0

    def test_second_matchup_index(self):
        """The second matchup in the index gets index 1."""
        result = _classify_clause("Oak Grove Win over Pearl", self._matchup_index)
        assert result[0] == 1

    def test_unknown_matchup_fallback_index(self):
        """An unknown matchup returns a large fallback index."""
        result = _classify_clause("Unknown Win over Team", self._matchup_index)
        assert result[0] == 10**6

    def test_unparseable_clause_all_fallback(self):
        """A clause with no 'Win over' returns (10^6, 99, text)."""
        result = _classify_clause("some random text", self._matchup_index)
        assert result == (10**6, 99, "some random text")


class TestClausesForM:
    """Tests for clauses_for_m — minterm → sorted human-readable clause list."""

    _bgv = [("A>B", "A", "B"), ("C>D", "C", "D")]

    def test_base_win_produces_win_clause(self):
        """A plain base=True minterm produces 'A Win over B'."""
        clauses = clauses_for_m({"A>B": True}, self._bgv)
        assert clauses == ["A Win over B"]

    def test_base_loss_produces_flipped_clause(self):
        """A plain base=False minterm produces 'B Win over A'."""
        clauses = clauses_for_m({"A>B": False}, self._bgv)
        assert clauses == ["B Win over A"]

    def test_ge_margin_produces_ge_clause(self):
        """A GE=True threshold produces a '≥ N' clause."""
        clauses = clauses_for_m({"A>B": True, "A>B_GE5": True}, self._bgv)
        assert len(clauses) == 1
        assert "≥ 5" in clauses[0]

    def test_lt_bound_produces_lt_clause(self):
        """GE1=True and GE8=False produces a '< 8' clause."""
        clauses = clauses_for_m({"A>B": True, "A>B_GE1": True, "A>B_GE8": False}, self._bgv)
        assert len(clauses) == 1
        assert "< 8" in clauses[0]

    def test_ge_and_lt_produces_range_clause(self):
        """GE3=True and GE9=False produces a '≥ 3 and < 9' clause."""
        clauses = clauses_for_m({"A>B": True, "A>B_GE3": True, "A>B_GE9": False}, self._bgv)
        assert len(clauses) == 1
        assert "≥ 3" in clauses[0]
        assert "< 9" in clauses[0]

    def test_fully_open_ge_produces_plain_win(self):
        """GE1=True and GE13=False (fully open) normalizes to a plain win clause."""
        clauses = clauses_for_m({"A>B": True, "A>B_GE1": True, "A>B_GE13": False}, self._bgv)
        assert clauses == ["A Win over B"]

    def test_multiple_matchups_sorted_by_index(self):
        """Two matchups are sorted by their position in boolean_game_vars."""
        clauses = clauses_for_m({"C>D": True, "A>B": True}, self._bgv)
        assert clauses.index("A Win over B") < clauses.index("C Win over D")

    def test_ge_key_with_no_base_key_uses_fallback_orientation(self):
        """A GE key with no corresponding base key still produces a clause."""
        # No base key present; orientation inferred from context (fallback winner=A>B)
        clauses = clauses_for_m({"A>B_GE4": True}, self._bgv)
        assert len(clauses) == 1
        assert "A" in clauses[0]

    def test_ge_key_with_flipped_base_infers_winner_from_flip(self):
        """When a GE key's base is absent but its flipped key is present, winner is inferred from the flip."""
        # "A>B_GE5": True with no "A>B" key, but "B>A": True is present
        # → base_val=None, flip_val=True → winner=B, loser=A
        clauses = clauses_for_m({"A>B_GE5": True, "B>A": True}, self._bgv)
        assert len(clauses) == 1
        # B wins (flip_val=True), so should say "B Win over A ..."
        assert "B Win over A" in clauses[0]


class TestBlockSortKey:
    """Tests for _block_sort_key — sort key for a list of clause strings."""

    _bgv = [("A>B", "A", "B"), ("C>D", "C", "D")]

    def test_returns_tuple(self):
        """_block_sort_key returns a tuple."""
        key = _block_sort_key(["A Win over B"], self._bgv)
        assert isinstance(key, tuple)

    def test_known_first_clause_uses_index(self):
        """A block whose first clause matches the first matchup has idx=0."""
        key = _block_sort_key(["A Win over B"], self._bgv)
        assert key[0] == 0

    def test_clause_count_embedded_in_key(self):
        """Clause count appears in the sort key (used as a tiebreaker when other fields match)."""
        key_one = _block_sort_key(["A Win over B"], self._bgv)
        key_two = _block_sort_key(["A Win over B", "C Win over D"], self._bgv)
        # Clause count is at index 4 of the key tuple
        assert key_one[4] == 1
        assert key_two[4] == 2


class TestIntervalOfClause:
    """Tests for _interval_of_clause — parse a clause back into (key, dir, interval)."""

    def test_base_win_clause(self):
        """Plain 'A Win over B' returns (('A','B'), 'a>b', None)."""
        result = _interval_of_clause("A Win over B")
        assert result == (("A", "B"), "a>b", None)

    def test_lt_clause_parses_interval(self):
        """'by < k' clause returns interval (1, k)."""
        result = _interval_of_clause("A Win over B by < 7 points")
        assert result is not None
        _key, _dir, interval = result
        assert interval == (1, 7)

    def test_ge_clause_parses_interval(self):
        """'by ≥ L' clause returns interval (L, 13)."""
        result = _interval_of_clause("A Win over B by ≥ 5 points")
        assert result is not None
        _key, _dir, interval = result
        assert interval == (5, 13)

    def test_ge_and_lt_clause_parses_interval(self):
        """'by ≥ L and < k' clause returns interval (L, k)."""
        result = _interval_of_clause("A Win over B by ≥ 3 and < 9 points")
        assert result is not None
        _key, _dir, interval = result
        assert interval == (3, 9)

    def test_canonical_key_ordering(self):
        """Result key uses canonical (lesser, greater) ordering."""
        result = _interval_of_clause("Z Win over A")
        assert result is not None
        key, _dir, _interval = result
        assert key == ("A", "Z")

    def test_unparseable_returns_none(self):
        """Clause without 'Win over' returns None."""
        assert _interval_of_clause("some random text") is None


class TestUnionIntervals:
    """Tests for _union_intervals — merge overlapping/adjacent intervals."""

    def test_empty_list(self):
        """Empty input returns empty list."""
        assert _union_intervals([]) == []

    def test_single_interval_unchanged(self):
        """Single interval is returned as-is."""
        assert _union_intervals([(1, 5)]) == [(1, 5)]

    def test_adjacent_intervals_merged(self):
        """Adjacent intervals [1,5) and [5,10) merge to [1,10)."""
        assert _union_intervals([(1, 5), (5, 10)]) == [(1, 10)]

    def test_overlapping_intervals_merged(self):
        """Overlapping intervals [1,7) and [4,13) merge to [1,13)."""
        assert _union_intervals([(1, 7), (4, 13)]) == [(1, 13)]

    def test_disjoint_intervals_preserved(self):
        """Disjoint intervals [1,3) and [5,7) are not merged."""
        assert _union_intervals([(1, 3), (5, 7)]) == [(1, 3), (5, 7)]

    def test_unsorted_input_is_sorted_first(self):
        """Unsorted input is sorted before merging."""
        assert _union_intervals([(5, 10), (1, 5)]) == [(1, 10)]


class TestCoverageCollapseBlocks:
    """Tests for _coverage_collapse_blocks — dedup and coverage collapse."""

    def test_empty_blocks_list(self):
        """Empty input returns empty list."""
        assert _coverage_collapse_blocks([]) == []

    def test_identical_blocks_deduped(self):
        """Duplicate blocks are removed; the result has only one copy."""
        blocks = [
            ["A Win over B", "C Win over D"],
            ["A Win over B", "C Win over D"],
        ]
        result = _coverage_collapse_blocks(blocks)
        assert len(result) == 1

    def test_distinct_blocks_collapsed_when_full_coverage(self):
        """Two blocks that together cover all outcomes for a matchup are collapsed to one."""
        # "C Win over D" and "D Win over C" together cover all C vs D outcomes,
        # so with the shared pivot "A Win over B", they collapse to ["A Win over B"].
        blocks = [
            ["A Win over B", "C Win over D"],
            ["A Win over B", "D Win over C"],
        ]
        result = _coverage_collapse_blocks(blocks)
        assert result == [["A Win over B"]]

    def test_output_clauses_are_sorted(self):
        """Each output block's clauses are in sorted order (reconstruction step)."""
        blocks = [["C Win over D", "A Win over B"]]
        result = _coverage_collapse_blocks(blocks)
        assert result[0] == sorted(result[0])


class TestScenariosTextDictFormat:
    """Test scenarios_text_from_team_seed_ordered with dict-format scen_dist."""

    def test_dict_format_scen_dist_does_not_crash(self):
        """Passing a dict as scen_dist exercises the isinstance(scen_dist, dict) branch."""
        # dict keys are strings (not dicts), so the inner isinstance(k, dict) check
        # is False and no minterms are added — but the branch is exercised.
        team_seed_map = {"A": {1: {"minterm_key": {"A>B": True}}}}
        # Should not raise; output may be empty since no minterms are extracted
        result = scenarios_text_from_team_seed_ordered(team_seed_map, ["A>B"])
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Snapshot capture helper — run this file directly to generate the golden value
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    r = enumerate_region_pure(
        teams_3_7a,
        expected_3_7a_completed_games,
        expected_3_7a_remaining_games,
    )
    games_order = [var_name for var_name, _a, _b in r.boolean_game_vars]
    text = scenarios_text_from_team_seed_ordered(r.scenario_minterms, games_order)
    print(repr(text))
