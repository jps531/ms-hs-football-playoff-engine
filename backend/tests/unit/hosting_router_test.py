"""Unit tests for pure helpers in backend.api.routers.hosting."""

from backend.api.models.requests import BracketGameResultRequest, ParticipantRef
from backend.api.routers.hosting import _to_school_only_results


def _result(
    winner_school: str | None = None,
    winner_region: int | None = None,
    winner_seed: int | None = None,
    loser_school: str | None = None,
    loser_region: int | None = None,
    loser_seed: int | None = None,
    round_: str | None = None,
) -> BracketGameResultRequest:
    """Build a BracketGameResultRequest from either school names or (region, seed) slot refs."""
    winner = ParticipantRef(school=winner_school, region=winner_region, seed=winner_seed)
    loser = (
        None
        if loser_school is None and loser_region is None and loser_seed is None and round_ is not None
        else ParticipantRef(school=loser_school, region=loser_region, seed=loser_seed)
    )
    return BracketGameResultRequest(winner=winner, loser=loser, round=round_)


class TestToSchoolOnlyResults:
    """_to_school_only_results converts school-name results, dropping slot-ref/round-only entries."""

    def test_school_vs_school_included(self):
        """A result with both winner and loser identified by school name is converted."""
        results = [_result(winner_school="Alpha", loser_school="Beta")]
        out = _to_school_only_results(results)
        assert len(out) == 1
        assert (out[0].winner, out[0].loser) == ("Alpha", "Beta")

    def test_slot_ref_only_result_dropped(self):
        """A result identified purely by (region, seed) slot refs (no school) is dropped."""
        results = [_result(winner_region=1, winner_seed=1, loser_region=1, loser_seed=2)]
        assert _to_school_only_results(results) == []

    def test_round_based_result_dropped_not_crashed(self):
        """A round-based result (loser=None) is dropped rather than raising AttributeError."""
        results = [_result(winner_school="Alpha", round_="quarterfinals")]
        assert _to_school_only_results(results) == []

    def test_mixed_results_filters_to_school_only(self):
        """A mix of school-based, slot-ref-based, and round-based results keeps only school-based ones."""
        results = [
            _result(winner_school="Alpha", loser_school="Beta"),
            _result(winner_region=2, winner_seed=1, loser_region=2, loser_seed=2),
            _result(winner_school="Gamma", round_="semifinals"),
        ]
        out = _to_school_only_results(results)
        assert len(out) == 1
        assert (out[0].winner, out[0].loser) == ("Alpha", "Beta")

    def test_scores_preserved(self):
        """winner_score/loser_score pass through unchanged."""
        winner = ParticipantRef(school="Alpha")
        loser = ParticipantRef(school="Beta")
        result = BracketGameResultRequest(winner=winner, loser=loser, winner_score=21, loser_score=14)
        out = _to_school_only_results([result])
        assert (out[0].winner_score, out[0].loser_score) == (21, 14)
