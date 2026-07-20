"""Unit tests for pure helpers in backend.api.routers.bracket."""

from backend.api.models.responses import BracketSlotHosting, RoundHostingOdds, TeamBracketEntry
from backend.api.routers.bracket import _build_p_host_given_reach_by_team, _invert_school_to_seed


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
