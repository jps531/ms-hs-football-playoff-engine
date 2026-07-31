"""Unit tests for pure helpers in backend.api.routers.bracket."""

from backend.api.models.responses import BracketSlotHosting, RoundHostingOdds, TeamBracketEntry
from backend.api.routers.bracket import (
    _build_p_host_given_reach_by_team,
    _invert_school_to_seed,
    _seeds_by_region_for_slot,
)
from backend.helpers.data_classes import FormatSlot


class TestInvertSchoolToSeed:
    """_invert_school_to_seed turns a school->(region, seed) map into (region, seed)->school."""

    def test_inverts_mapping(self):
        """Each (region, seed) key maps back to its original school."""
        result = _invert_school_to_seed({"Alpha": (1, 1), "Beta": (1, 2)})
        assert result == {(1, 1): "Alpha", (1, 2): "Beta"}

    def test_empty_input_returns_empty_dict(self):
        """An empty school_to_seed map produces an empty result."""
        assert _invert_school_to_seed({}) == {}


def _entry(school: str | None, hosting: BracketSlotHosting | None) -> TeamBracketEntry:
    """Build a minimal TeamBracketEntry for testing _build_p_host_given_reach_by_team."""
    return TeamBracketEntry(
        region=1,
        seed=1,
        school=school,
        second_round=0.5,
        quarterfinals=0.4,
        semifinals=0.3,
        finals=0.2,
        champion=0.1,
        hosting=hosting,
    )


class TestBuildPHostGivenReachByTeam:
    """_build_p_host_given_reach_by_team extracts per-round p_host_given_reach from clinched entries."""

    def test_extracts_all_rounds_for_clinched_entry_with_hosting(self):
        """A clinched entry (school set) with hosting odds contributes all four rounds."""
        hosting = BracketSlotHosting(
            first_round=RoundHostingOdds(p_host_given_reach=1.0, p_host_overall=0.9),
            second_round=RoundHostingOdds(p_host_given_reach=0.7, p_host_overall=0.5),
            quarterfinals=RoundHostingOdds(p_host_given_reach=0.5, p_host_overall=0.3),
            semifinals=RoundHostingOdds(p_host_given_reach=0.3, p_host_overall=0.2),
        )
        entries = [_entry("Alpha", hosting)]
        result = _build_p_host_given_reach_by_team(entries)
        assert result == {
            "Alpha": {
                "first_round": 1.0,
                "second_round": 0.7,
                "quarterfinals": 0.5,
                "semifinals": 0.3,
            }
        }

    def test_none_p_host_given_reach_when_not_applicable(self):
        """A second_round with p_host_given_reach=None (5A-7A classes) maps to None rather than raising."""
        hosting = BracketSlotHosting(
            first_round=RoundHostingOdds(p_host_given_reach=1.0, p_host_overall=0.9),
            second_round=RoundHostingOdds(p_host_given_reach=None, p_host_overall=None),
            quarterfinals=RoundHostingOdds(p_host_given_reach=0.5, p_host_overall=0.3),
            semifinals=RoundHostingOdds(p_host_given_reach=0.3, p_host_overall=0.2),
        )
        entries = [_entry("Alpha", hosting)]
        result = _build_p_host_given_reach_by_team(entries)
        assert result["Alpha"]["second_round"] is None

    def test_unclinched_entry_excluded(self):
        """An entry with school=None (not yet clinched) is excluded from the result."""
        hosting = BracketSlotHosting(
            first_round=RoundHostingOdds(p_host_given_reach=1.0, p_host_overall=0.9),
            second_round=RoundHostingOdds(p_host_given_reach=0.7, p_host_overall=0.5),
            quarterfinals=RoundHostingOdds(p_host_given_reach=0.5, p_host_overall=0.3),
            semifinals=RoundHostingOdds(p_host_given_reach=0.3, p_host_overall=0.2),
        )
        entries = [_entry(None, hosting)]
        assert _build_p_host_given_reach_by_team(entries) == {}

    def test_entry_without_hosting_excluded(self):
        """An entry with hosting=None is excluded from the result even if clinched."""
        entries = [_entry("Alpha", None)]
        assert _build_p_host_given_reach_by_team(entries) == {}


def _slot(slot: int, home_region: int, home_seed: int, away_region: int, away_seed: int) -> FormatSlot:
    """Build a minimal FormatSlot for testing _seeds_by_region_for_slot."""
    return FormatSlot(
        slot=slot, home_region=home_region, home_seed=home_seed,
        away_region=away_region, away_seed=away_seed, north_south="N",
    )


class TestSeedsByRegionForSlot:
    """_seeds_by_region_for_slot returns the candidate (region -> seeds) map for a slot group."""

    def test_first_round_uses_only_the_single_slots_two_positions(self):
        """first_round returns exactly the group's one slot's home/away (region, seed) positions."""
        group = [_slot(1, home_region=1, home_seed=1, away_region=2, away_seed=4)]
        result = _seeds_by_region_for_slot(group, "first_round")
        assert result == {1: {1}, 2: {4}}

    def test_later_round_delegates_to_candidate_seeds_by_region(self):
        """A non-first_round group unions seeds across every slot in the group (both R1 games feeding it)."""
        group = [
            _slot(1, home_region=1, home_seed=1, away_region=1, away_seed=4),
            _slot(2, home_region=1, home_seed=2, away_region=1, away_seed=3),
        ]
        result = _seeds_by_region_for_slot(group, "second_round")
        assert result == {1: {1, 2, 3, 4}}
