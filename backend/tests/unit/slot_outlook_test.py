"""Unit tests for the GET /bracket/slots/{slot} building blocks in backend.helpers.api_helpers.

``_resolve_slot_group`` and ``_candidate_seeds_by_region`` are pure bracket-tree
navigation; ``build_slot_outlook_teams`` wires them to the existing
``compute_bracket_advancement_odds``/``compute_*_home_odds`` functions
(already covered by backend/tests/bracket/bracket_home_odds_probabilistic_test.py)
and is cross-checked against those functions directly rather than re-deriving
the underlying probability math here.
"""

import pytest

from backend.helpers.api_helpers import (
    _candidate_seeds_by_region,
    _resolve_slot_group,
    build_slot_outlook_teams,
)
from backend.helpers.bracket_home_odds import (
    compute_bracket_advancement_odds,
    compute_quarterfinal_home_odds,
    compute_second_round_home_odds,
    compute_semifinal_home_odds,
    equal_matchup_prob,
)
from backend.helpers.data_classes import StandingsOdds
from backend.tests.data.playoff_brackets_2025 import SLOTS_1A_4A_2025, SLOTS_5A_7A_2025

SEASON = 2025


def _odds(school: str, p1: float = 0.0, p2: float = 0.0, p3: float = 0.0, p4: float = 0.0) -> StandingsOdds:
    """Build a StandingsOdds with arbitrary per-seed probabilities."""
    p = p1 + p2 + p3 + p4
    return StandingsOdds(
        school=school, p1=p1, p2=p2, p3=p3, p4=p4,
        p_playoffs=p, final_playoffs=p, clinched=p >= 0.999, eliminated=p <= 0.0,
    )


def _locked(school: str, seed: int) -> StandingsOdds:
    """Build a StandingsOdds certain to hold exactly one seed (mirrors production fixtures)."""
    return _odds(school, **{f"p{seed}": 1.0})


# ---------------------------------------------------------------------------
# _resolve_slot_group
# ---------------------------------------------------------------------------


class TestResolveSlotGroupFirstRound:
    """first_round needs no grouping -- the requested slot is the game."""

    def test_5a_7a_returns_only_the_target_slot(self):
        """5A-7A first_round groups to just the requested slot."""
        group = _resolve_slot_group(1, "first_round", SLOTS_5A_7A_2025)
        assert group is not None
        assert [s.slot for s in group] == [1]

    def test_1a_4a_returns_only_the_target_slot(self):
        """1A-4A first_round groups to just the requested slot."""
        group = _resolve_slot_group(5, "first_round", SLOTS_1A_4A_2025)
        assert group is not None
        assert [s.slot for s in group] == [5]

    def test_unknown_slot_returns_none(self):
        """A slot number absent from the format's slots resolves to None."""
        assert _resolve_slot_group(999, "first_round", SLOTS_5A_7A_2025) is None


class TestResolveSlotGroup5A7A:
    """5A-7A: 4 slots/half, no second_round, QF=offset 1, SF=offset 2."""

    def test_second_round_is_unavailable(self):
        """5A-7A has no second round, so that round_name always resolves to None."""
        assert _resolve_slot_group(1, "second_round", SLOTS_5A_7A_2025) is None

    def test_quarterfinals_pairs_adjacent_slots(self):
        """Quarterfinals group two adjacent first-round slots."""
        group = _resolve_slot_group(1, "quarterfinals", SLOTS_5A_7A_2025)
        assert group is not None
        assert {s.slot for s in group} == {1, 2}

    def test_quarterfinals_from_either_slot_in_the_pair_agrees(self):
        """Either slot in a quarterfinal pair resolves to the same group."""
        group_from_1 = _resolve_slot_group(1, "quarterfinals", SLOTS_5A_7A_2025)
        group_from_2 = _resolve_slot_group(2, "quarterfinals", SLOTS_5A_7A_2025)
        assert group_from_1 is not None
        assert group_from_2 is not None
        assert {s.slot for s in group_from_1} == {s.slot for s in group_from_2}

    def test_semifinals_spans_the_whole_half(self):
        """Semifinals group all four slots in the north half."""
        group = _resolve_slot_group(1, "semifinals", SLOTS_5A_7A_2025)
        assert group is not None
        assert {s.slot for s in group} == {1, 2, 3, 4}

    def test_south_half_is_independent_of_north(self):
        """The south half's semifinal group doesn't include north-half slots."""
        group = _resolve_slot_group(5, "semifinals", SLOTS_5A_7A_2025)
        assert group is not None
        assert {s.slot for s in group} == {5, 6, 7, 8}


class TestResolveSlotGroup1A4A:
    """1A-4A: 8 slots/half, second_round=offset 1, QF=offset 2, SF=offset 3."""

    def test_second_round_pairs_adjacent_slots(self):
        """Second round groups two adjacent first-round slots."""
        group = _resolve_slot_group(1, "second_round", SLOTS_1A_4A_2025)
        assert group is not None
        assert {s.slot for s in group} == {1, 2}

    def test_quarterfinals_spans_four_slots(self):
        """Quarterfinals group four first-round slots."""
        group = _resolve_slot_group(1, "quarterfinals", SLOTS_1A_4A_2025)
        assert group is not None
        assert {s.slot for s in group} == {1, 2, 3, 4}

    def test_quarterfinals_from_slot_three_agrees_with_slot_one(self):
        """Any slot within a quarterfinal group of four resolves to the same group."""
        group = _resolve_slot_group(3, "quarterfinals", SLOTS_1A_4A_2025)
        assert group is not None
        assert {s.slot for s in group} == {1, 2, 3, 4}

    def test_semifinals_spans_the_whole_half(self):
        """Semifinals group all eight slots in the half."""
        group = _resolve_slot_group(1, "semifinals", SLOTS_1A_4A_2025)
        assert group is not None
        assert {s.slot for s in group} == {1, 2, 3, 4, 5, 6, 7, 8}


# ---------------------------------------------------------------------------
# _candidate_seeds_by_region
# ---------------------------------------------------------------------------


class TestCandidateSeedsByRegion:
    """Coverage for mapping a first-round slot group to its (region, seed) candidates."""

    def test_first_round_slot_yields_home_and_away_seed(self):
        """A single first-round slot yields exactly its home and away (region, seed)."""
        group = _resolve_slot_group(1, "first_round", SLOTS_5A_7A_2025)
        assert group is not None
        assert _candidate_seeds_by_region(group) == {1: {1}, 2: {4}}

    def test_1a_4a_quarterfinal_group_covers_all_four_regions(self):
        """A 1A-4A quarterfinal group's four slots cover all four regions' candidate seeds."""
        group = _resolve_slot_group(1, "quarterfinals", SLOTS_1A_4A_2025)
        assert group is not None
        assert _candidate_seeds_by_region(group) == {
            1: {1, 4},
            2: {1, 4},
            3: {2, 3},
            4: {2, 3},
        }


# ---------------------------------------------------------------------------
# build_slot_outlook_teams -- first_round (special-cased: no compute_* calls)
# ---------------------------------------------------------------------------


class TestBuildSlotOutlookTeamsFirstRound:
    """Coverage for the first_round branch of build_slot_outlook_teams."""

    def test_contested_slot_returns_every_candidate_ranked_by_p_reach(self):
        """A contested slot returns every nonzero candidate, ranked by descending p_reach."""
        by_region = {
            1: {"Alpha": _odds("Alpha", p1=0.6), "Beta": _odds("Beta", p1=0.3)},
            2: {"Gamma": _odds("Gamma", p4=0.4), "Delta": _odds("Delta", p4=0.5)},
        }
        teams = build_slot_outlook_teams(1, "first_round", by_region, SLOTS_5A_7A_2025, SEASON)
        assert teams is not None
        assert [t.school for t in teams] == ["Alpha", "Delta", "Gamma", "Beta"]

        by_school = {t.school: t for t in teams}
        assert by_school["Alpha"].p_reach == pytest.approx(0.6)
        assert by_school["Alpha"].p_host_given_reach == pytest.approx(1.0)  # home seed
        assert by_school["Alpha"].p_host_overall == pytest.approx(0.6)
        assert by_school["Gamma"].p_reach == pytest.approx(0.4)
        assert by_school["Gamma"].p_host_given_reach == pytest.approx(0.0)  # away seed
        assert by_school["Gamma"].p_host_overall == pytest.approx(0.0)

    def test_zero_probability_candidates_excluded(self):
        """Candidates with zero probability of holding the relevant seed are excluded."""
        by_region = {1: {"Alpha": _odds("Alpha", p1=1.0), "Zero": _odds("Zero", p1=0.0)}, 2: {}}
        teams = build_slot_outlook_teams(1, "first_round", by_region, SLOTS_5A_7A_2025, SEASON)
        assert teams is not None
        assert [t.school for t in teams] == ["Alpha"]

    def test_clinched_slot_has_exactly_one_team_per_side(self):
        """A clinched slot yields exactly one team per side, each with p_reach == 1.0."""
        by_region = {1: {"Alpha": _locked("Alpha", 1)}, 2: {"Beta": _locked("Beta", 4)}}
        teams = build_slot_outlook_teams(1, "first_round", by_region, SLOTS_5A_7A_2025, SEASON)
        assert teams is not None
        assert {t.school: t.p_reach for t in teams} == {"Alpha": pytest.approx(1.0), "Beta": pytest.approx(1.0)}

    def test_p_host_overall_always_equals_p_reach_times_p_host_given_reach(self):
        """p_host_overall is always the product of p_reach and p_host_given_reach."""
        by_region = {
            1: {"Alpha": _odds("Alpha", p1=0.6), "Beta": _odds("Beta", p1=0.3)},
            2: {"Gamma": _odds("Gamma", p4=0.4)},
        }
        teams = build_slot_outlook_teams(1, "first_round", by_region, SLOTS_5A_7A_2025, SEASON)
        assert teams is not None
        for t in teams:
            assert t.p_host_given_reach is not None
            assert t.p_host_overall == pytest.approx(t.p_reach * t.p_host_given_reach)

    def test_no_weighted_fn_leaves_weighted_fields_none(self):
        """Without a weighted win-probability function, all *_weighted fields stay None."""
        by_region = {1: {"Alpha": _odds("Alpha", p1=1.0)}, 2: {"Beta": _odds("Beta", p4=1.0)}}
        teams = build_slot_outlook_teams(1, "first_round", by_region, SLOTS_5A_7A_2025, SEASON)
        assert teams is not None
        for t in teams:
            assert t.p_reach_weighted is None
            assert t.p_host_given_reach_weighted is None
            assert t.p_host_overall_weighted is None

    def test_weighted_fn_mirrors_unweighted_for_first_round(self):
        """No Elo-weighted variant of a seeding probability exists; weighted == unweighted."""
        by_region = {1: {"Alpha": _odds("Alpha", p1=0.6)}, 2: {"Beta": _odds("Beta", p4=0.4)}}
        teams = build_slot_outlook_teams(
            1, "first_round", by_region, SLOTS_5A_7A_2025, SEASON, win_prob_fn_weighted=equal_matchup_prob
        )
        assert teams is not None
        for t in teams:
            assert t.p_reach_weighted == pytest.approx(t.p_reach)
            assert t.p_host_given_reach_weighted == pytest.approx(t.p_host_given_reach)
            assert t.p_host_overall_weighted == pytest.approx(t.p_host_overall)


# ---------------------------------------------------------------------------
# build_slot_outlook_teams -- later rounds (cross-checked against direct calls)
# ---------------------------------------------------------------------------


class TestBuildSlotOutlookTeamsLaterRounds:
    """Coverage for the second_round/quarterfinals/semifinals branch of build_slot_outlook_teams."""

    def test_locked_quarterfinal_group_matches_direct_compute_calls(self):
        """A locked quarterfinal group's outputs match direct compute_* calls per region."""
        by_region = {
            1: {"R1S1": _locked("R1S1", 1)},
            2: {"R2S4": _locked("R2S4", 4)},
            3: {"R3S2": _locked("R3S2", 2)},
            4: {"R4S3": _locked("R4S3", 3)},
        }
        teams = build_slot_outlook_teams(1, "quarterfinals", by_region, SLOTS_1A_4A_2025, SEASON)
        assert teams is not None
        by_school = {t.school: t for t in teams}
        assert set(by_school) == {"R1S1", "R2S4", "R3S2", "R4S3"}

        for region, school in ((1, "R1S1"), (2, "R2S4"), (3, "R3S2"), (4, "R4S3")):
            region_odds = by_region[region]
            expected_reach = compute_bracket_advancement_odds(region, region_odds, SLOTS_1A_4A_2025)[
                school
            ].quarterfinals
            expected_host = compute_quarterfinal_home_odds(region, region_odds, SLOTS_1A_4A_2025, SEASON)[school]
            t = by_school[school]
            assert t.p_reach == pytest.approx(expected_reach)
            assert t.p_host_overall == pytest.approx(expected_host)
            assert t.p_host_given_reach is not None
            assert t.p_host_overall == pytest.approx(t.p_reach * t.p_host_given_reach)

    def test_locked_second_round_group_matches_direct_compute_calls(self):
        """A locked second-round group's outputs match direct compute_* calls per region."""
        by_region = {1: {"R1S1": _locked("R1S1", 1)}, 2: {"R2S4": _locked("R2S4", 4)}}
        teams = build_slot_outlook_teams(1, "second_round", by_region, SLOTS_1A_4A_2025, SEASON)
        assert teams is not None
        by_school = {t.school: t for t in teams}
        for region, school in ((1, "R1S1"), (2, "R2S4")):
            region_odds = by_region[region]
            expected_reach = compute_bracket_advancement_odds(region, region_odds, SLOTS_1A_4A_2025)[
                school
            ].second_round
            expected_host = compute_second_round_home_odds(region, region_odds, SLOTS_1A_4A_2025, SEASON)[school]
            assert by_school[school].p_reach == pytest.approx(expected_reach)
            assert by_school[school].p_host_overall == pytest.approx(expected_host)

    def test_locked_semifinal_group_matches_direct_compute_calls(self):
        """A locked semifinal group's outputs match direct compute_* calls per region."""
        by_region = {
            1: {"R1S1": _locked("R1S1", 1)},
            2: {"R2S4": _locked("R2S4", 4)},
            3: {"R3S2": _locked("R3S2", 2)},
            4: {"R4S3": _locked("R4S3", 3)},
        }
        teams = build_slot_outlook_teams(1, "semifinals", by_region, SLOTS_1A_4A_2025, SEASON)
        assert teams is not None
        by_school = {t.school: t for t in teams}
        for region, school in ((1, "R1S1"), (2, "R2S4"), (3, "R3S2"), (4, "R4S3")):
            region_odds = by_region[region]
            expected_reach = compute_bracket_advancement_odds(region, region_odds, SLOTS_1A_4A_2025)[
                school
            ].semifinals
            expected_host = compute_semifinal_home_odds(region, region_odds, SLOTS_1A_4A_2025, SEASON)[school]
            assert by_school[school].p_reach == pytest.approx(expected_reach)
            assert by_school[school].p_host_overall == pytest.approx(expected_host)

    def test_contested_region_returns_multiple_candidates(self):
        """A region with no clear seed favorite still yields every candidate with p_reach > 0."""
        by_region = {
            1: {"Alpha": _odds("Alpha", p1=0.4, p2=0.35, p3=0.25), "Beta": _odds("Beta", p4=1.0)},
        }
        # Widen to a full QF group so region 1's contested seed 1/2/3 candidates are all included.
        by_region[2] = {"Gamma": _locked("Gamma", 4)}
        by_region[3] = {"Delta": _locked("Delta", 2)}
        by_region[4] = {"Epsilon": _locked("Epsilon", 3)}
        teams = build_slot_outlook_teams(1, "quarterfinals", by_region, SLOTS_1A_4A_2025, SEASON)
        assert teams is not None
        assert "Alpha" in {t.school for t in teams}
        alpha = next(t for t in teams if t.school == "Alpha")
        assert alpha.p_reach > 0.0

    def test_weighted_fn_populates_weighted_fields(self):
        """Passing a weighted win-probability function populates the *_weighted fields."""
        by_region = {1: {"R1S1": _locked("R1S1", 1)}, 2: {"R2S4": _locked("R2S4", 4)}}
        teams = build_slot_outlook_teams(
            1, "second_round", by_region, SLOTS_1A_4A_2025, SEASON, win_prob_fn_weighted=equal_matchup_prob
        )
        assert teams is not None
        for t in teams:
            assert t.p_reach_weighted is not None
            assert t.p_host_overall_weighted is not None
            assert t.p_host_overall_weighted == pytest.approx(t.p_reach_weighted * (t.p_host_given_reach_weighted or 0))


# ---------------------------------------------------------------------------
# build_slot_outlook_teams -- edge cases signalling a 404 to the caller
# ---------------------------------------------------------------------------


class TestBuildSlotOutlookTeamsInvalid:
    """Coverage for inputs that should signal a 404 to the API caller."""

    def test_unknown_slot_returns_none(self):
        """An unknown slot number returns None."""
        assert build_slot_outlook_teams(999, "first_round", {}, SLOTS_5A_7A_2025, SEASON) is None

    def test_second_round_on_5a_7a_returns_none(self):
        """Requesting second_round for the 5A-7A format (which has none) returns None."""
        by_region = {1: {"Alpha": _locked("Alpha", 1)}, 2: {"Beta": _locked("Beta", 4)}}
        assert build_slot_outlook_teams(1, "second_round", by_region, SLOTS_5A_7A_2025, SEASON) is None
