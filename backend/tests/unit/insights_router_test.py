"""Unit tests for the pure dedup/derivation logic behind GET /insights."""

from datetime import date

from backend.helpers.api_helpers import (
    _insight_kind,
    _insight_teams,
    _insights_from_snapshot_rows,
)
from backend.helpers.data_classes import GameResult
from backend.helpers.insights import KeyInsight, serialize_insights


def _insight(
    insight_type: str,
    team: str,
    seed: int | None = None,
    conditions: tuple = (),
    rendered: str = "rendered text",
) -> KeyInsight:
    return KeyInsight(
        insight_type=insight_type,
        team=team,
        seed=seed,
        conditions=conditions,
        margin_verified=True,
        rendered=rendered,
        r_computed=5,
    )


def _row(clazz: str, region: int, as_of: date, insights: list[KeyInsight]) -> tuple:
    return (clazz, region, as_of, serialize_insights(insights))


class TestInsightKind:
    def test_clinch_seed_includes_seed_number(self):
        assert _insight_kind("clinch_seed", 1) == "clinch_seed_1"
        assert _insight_kind("clinch_seed", 4) == "clinch_seed_4"

    def test_clinch_playoffs_and_already_clinched_share_kind(self):
        assert _insight_kind("clinch_playoffs", None) == "clinch_playoffs"
        assert _insight_kind("already_clinched", None) == "clinch_playoffs"

    def test_eliminated_variants_share_kind(self):
        assert _insight_kind("eliminated_if", None) == "eliminated"
        assert _insight_kind("already_eliminated", None) == "eliminated"

    def test_unknown_type_is_null(self):
        assert _insight_kind("something_new", None) is None

    def test_clinch_seed_without_seed_is_null(self):
        assert _insight_kind("clinch_seed", None) is None


class TestInsightTeams:
    def test_zero_condition_insight_is_just_the_subject_team(self):
        ins = _insight("already_clinched", "Taylorsville")
        assert _insight_teams(ins) == ["Taylorsville"]

    def test_conditions_add_winner_and_loser_in_order(self):
        ins = _insight(
            "clinch_seed",
            "Taylorsville",
            seed=1,
            conditions=(GameResult("Taylorsville", "Stringer"),),
        )
        assert _insight_teams(ins) == ["Taylorsville", "Stringer"]

    def test_duplicate_teams_across_conditions_deduped_preserving_first_order(self):
        ins = _insight(
            "clinch_playoffs",
            "Taylorsville",
            conditions=(
                GameResult("Taylorsville", "Stringer"),
                GameResult("Forest", "Taylorsville"),
            ),
        )
        assert _insight_teams(ins) == ["Taylorsville", "Stringer", "Forest"]


class TestInsightsFromSnapshotRows:
    def test_persisting_insight_deduped_to_first_appearance_date(self):
        """The same insight across 3 consecutive snapshots appears once, dated to the first."""
        ins = _insight("already_clinched", "Taylorsville", rendered="Taylorsville has clinched a playoff spot")
        rows = [
            _row("4", 3, date(2025, 10, 3), [ins]),
            _row("4", 3, date(2025, 10, 10), [ins]),
            _row("4", 3, date(2025, 10, 17), [ins]),
        ]
        feed = _insights_from_snapshot_rows(rows, since=None, team=None, limit=50)
        assert len(feed) == 1
        assert feed[0].as_of_date == date(2025, 10, 3)
        assert feed[0].human_text == "Taylorsville has clinched a playoff spot"

    def test_different_conditions_for_same_team_and_type_are_distinct(self):
        """A resolved insight followed by a new, differently-conditioned one is a second entry."""
        early = _insight(
            "eliminated_if",
            "Murrah",
            conditions=(GameResult("Starkville", "Terry"),),
            rendered="Murrah is eliminated if Starkville beats Terry",
        )
        later = _insight(
            "eliminated_if",
            "Murrah",
            conditions=(GameResult("Callaway", "Terry"),),
            rendered="Murrah is eliminated if Callaway beats Terry",
        )
        rows = [
            _row("4", 3, date(2025, 10, 3), [early]),
            _row("4", 3, date(2025, 10, 10), [later]),
        ]
        feed = _insights_from_snapshot_rows(rows, since=None, team=None, limit=50)
        assert len(feed) == 2
        dates = {i.as_of_date for i in feed}
        assert dates == {date(2025, 10, 3), date(2025, 10, 10)}

    def test_newest_first_ordering_across_regions(self):
        ins_a = _insight("already_clinched", "Alpha", rendered="Alpha clinched")
        ins_b = _insight("already_clinched", "Bravo", rendered="Bravo clinched")
        rows = [
            _row("4", 3, date(2025, 10, 3), [ins_a]),
            _row("5", 1, date(2025, 10, 10), [ins_b]),
        ]
        feed = _insights_from_snapshot_rows(rows, since=None, team=None, limit=50)
        assert [i.human_text for i in feed] == ["Bravo clinched", "Alpha clinched"]

    def test_since_filter_excludes_insights_that_first_appeared_earlier(self):
        ins = _insight("already_clinched", "Taylorsville", rendered="Taylorsville clinched")
        rows = [
            _row("4", 3, date(2025, 10, 3), [ins]),
            _row("4", 3, date(2025, 10, 10), [ins]),
        ]
        feed = _insights_from_snapshot_rows(rows, since=date(2025, 10, 5), team=None, limit=50)
        assert feed == []

    def test_since_filter_includes_insights_first_appearing_on_or_after(self):
        ins = _insight("already_clinched", "Taylorsville", rendered="Taylorsville clinched")
        rows = [_row("4", 3, date(2025, 10, 10), [ins])]
        feed = _insights_from_snapshot_rows(rows, since=date(2025, 10, 10), team=None, limit=50)
        assert len(feed) == 1

    def test_team_filter_matches_subject_team(self):
        ins = _insight("already_clinched", "Taylorsville", rendered="Taylorsville clinched")
        rows = [_row("4", 3, date(2025, 10, 10), [ins])]
        feed = _insights_from_snapshot_rows(rows, since=None, team="Taylorsville", limit=50)
        assert len(feed) == 1

    def test_team_filter_matches_condition_participant_not_just_subject(self):
        ins = _insight(
            "clinch_seed",
            "Taylorsville",
            seed=1,
            conditions=(GameResult("Taylorsville", "Stringer"),),
            rendered="Taylorsville clinches 1st seed: Taylorsville beats Stringer",
        )
        rows = [_row("4", 3, date(2025, 10, 10), [ins])]
        feed = _insights_from_snapshot_rows(rows, since=None, team="Stringer", limit=50)
        assert len(feed) == 1

    def test_team_filter_excludes_unrelated_insight(self):
        ins = _insight("already_clinched", "Taylorsville", rendered="Taylorsville clinched")
        rows = [_row("4", 3, date(2025, 10, 10), [ins])]
        feed = _insights_from_snapshot_rows(rows, since=None, team="Petal", limit=50)
        assert feed == []

    def test_limit_truncates_after_sorting_newest_first(self):
        rows = [
            _row(
                "4",
                3,
                date(2025, 10, d),
                [_insight("already_clinched", f"Team{d}", rendered=f"Team{d} clinched")],
            )
            for d in (3, 10, 17)
        ]
        feed = _insights_from_snapshot_rows(rows, since=None, team=None, limit=2)
        assert len(feed) == 2
        assert feed[0].human_text == "Team17 clinched"
        assert feed[1].human_text == "Team10 clinched"

    def test_class_and_region_pass_through_as_ints(self):
        ins = _insight("already_clinched", "Taylorsville", rendered="Taylorsville clinched")
        rows = [_row("4", 3, date(2025, 10, 10), [ins])]
        feed = _insights_from_snapshot_rows(rows, since=None, team=None, limit=50)
        assert feed[0].class_ == 4
        assert feed[0].region == 3

    def test_kind_derived_on_output(self):
        ins = _insight("clinch_seed", "Taylorsville", seed=2, rendered="Taylorsville clinches 2nd seed")
        rows = [_row("4", 3, date(2025, 10, 10), [ins])]
        feed = _insights_from_snapshot_rows(rows, since=None, team=None, limit=50)
        assert feed[0].kind == "clinch_seed_2"

    def test_empty_rows_returns_empty_feed(self):
        assert _insights_from_snapshot_rows([], since=None, team=None, limit=50) == []
