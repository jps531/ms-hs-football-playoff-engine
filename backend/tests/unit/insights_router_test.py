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
    """Build a KeyInsight for test use."""
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
    """Build a raw snapshot row tuple as read from the DB, for test use."""
    return (clazz, region, as_of, serialize_insights(insights))


class TestInsightKind:
    """_insight_kind: maps an insight's raw type (+ seed) to its display kind."""

    def test_clinch_seed_includes_seed_number(self):
        """A clinch_seed insight's kind includes the specific seed number."""
        assert _insight_kind("clinch_seed", 1) == "clinch_seed_1"
        assert _insight_kind("clinch_seed", 4) == "clinch_seed_4"

    def test_clinch_playoffs_and_already_clinched_share_kind(self):
        """clinch_playoffs and already_clinched both map to the clinch_playoffs kind."""
        assert _insight_kind("clinch_playoffs", None) == "clinch_playoffs"
        assert _insight_kind("already_clinched", None) == "clinch_playoffs"

    def test_eliminated_variants_share_kind(self):
        """eliminated_if and already_eliminated both map to the eliminated kind."""
        assert _insight_kind("eliminated_if", None) == "eliminated"
        assert _insight_kind("already_eliminated", None) == "eliminated"

    def test_unknown_type_is_null(self):
        """An unrecognized insight type has no kind."""
        assert _insight_kind("something_new", None) is None

    def test_clinch_seed_without_seed_is_null(self):
        """A clinch_seed insight missing its seed number has no kind."""
        assert _insight_kind("clinch_seed", None) is None


class TestInsightTeams:
    """_insight_teams: which teams an insight involves, subject first."""

    def test_zero_condition_insight_is_just_the_subject_team(self):
        """An insight with no conditions involves only its subject team."""
        ins = _insight("already_clinched", "Taylorsville")
        assert _insight_teams(ins) == ["Taylorsville"]

    def test_conditions_add_winner_and_loser_in_order(self):
        """A condition's winner and loser are appended after the subject team."""
        ins = _insight(
            "clinch_seed",
            "Taylorsville",
            seed=1,
            conditions=(GameResult("Taylorsville", "Stringer"),),
        )
        assert _insight_teams(ins) == ["Taylorsville", "Stringer"]

    def test_duplicate_teams_across_conditions_deduped_preserving_first_order(self):
        """A team appearing in multiple conditions is listed once, at its first occurrence."""
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
    """_insights_from_snapshot_rows: dedup, filter, sort, and truncate raw snapshot rows into a feed."""

    def test_persisting_insight_deduped_to_first_appearance_date(self):
        """The same insight across 3 consecutive snapshots appears once, dated to the first."""
        ins = _insight("already_clinched", "Taylorsville", rendered="Taylorsville has clinched a playoff spot")
        rows = [
            _row("4", 3, date(2025, 10, 3), [ins]),
            _row("4", 3, date(2025, 10, 10), [ins]),
            _row("4", 3, date(2025, 10, 17), [ins]),
        ]
        feed = _insights_from_snapshot_rows(rows, date_from=None, date_to=None, team=None, limit=50)
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
        feed = _insights_from_snapshot_rows(rows, date_from=None, date_to=None, team=None, limit=50)
        assert len(feed) == 2
        dates = {i.as_of_date for i in feed}
        assert dates == {date(2025, 10, 3), date(2025, 10, 10)}

    def test_newest_first_ordering_across_regions(self):
        """Insights are sorted newest-first regardless of which class/region they came from."""
        ins_a = _insight("already_clinched", "Alpha", rendered="Alpha clinched")
        ins_b = _insight("already_clinched", "Bravo", rendered="Bravo clinched")
        rows = [
            _row("4", 3, date(2025, 10, 3), [ins_a]),
            _row("5", 1, date(2025, 10, 10), [ins_b]),
        ]
        feed = _insights_from_snapshot_rows(rows, date_from=None, date_to=None, team=None, limit=50)
        assert [i.human_text for i in feed] == ["Bravo clinched", "Alpha clinched"]

    def test_date_from_filter_excludes_insights_that_first_appeared_earlier(self):
        """An insight whose true first-appearance date precedes date_from is dropped."""
        ins = _insight("already_clinched", "Taylorsville", rendered="Taylorsville clinched")
        rows = [
            _row("4", 3, date(2025, 10, 3), [ins]),
            _row("4", 3, date(2025, 10, 10), [ins]),
        ]
        feed = _insights_from_snapshot_rows(rows, date_from=date(2025, 10, 5), date_to=None, team=None, limit=50)
        assert feed == []

    def test_date_from_filter_includes_insights_first_appearing_on_or_after(self):
        """An insight first appearing exactly on date_from is included."""
        ins = _insight("already_clinched", "Taylorsville", rendered="Taylorsville clinched")
        rows = [_row("4", 3, date(2025, 10, 10), [ins])]
        feed = _insights_from_snapshot_rows(rows, date_from=date(2025, 10, 10), date_to=None, team=None, limit=50)
        assert len(feed) == 1

    def test_date_to_excludes_insight_that_first_appears_after_the_scrub_point(self):
        """Timeline scrubbing: an insight that hadn't happened yet as of date_to must not appear."""
        ins = _insight("already_clinched", "Taylorsville", rendered="Taylorsville clinched")
        rows = [_row("4", 3, date(2025, 10, 24), [ins])]
        feed = _insights_from_snapshot_rows(rows, date_from=None, date_to=date(2025, 10, 10), team=None, limit=50)
        assert feed == []

    def test_date_to_includes_insight_dated_to_true_first_appearance_not_clipped(self):
        """An insight first seen before date_to keeps its real first-appearance date, unclipped."""
        ins = _insight("already_clinched", "Taylorsville", rendered="Taylorsville clinched")
        rows = [
            _row("4", 3, date(2025, 10, 3), [ins]),
            _row("4", 3, date(2025, 10, 10), [ins]),
            _row("4", 3, date(2025, 10, 17), [ins]),
        ]
        feed = _insights_from_snapshot_rows(rows, date_from=None, date_to=date(2025, 10, 10), team=None, limit=50)
        assert len(feed) == 1
        assert feed[0].as_of_date == date(2025, 10, 3)

    def test_date_from_and_date_to_together_select_a_scrub_window(self):
        """Dragging a timeline scrubber from A to B: only insights new within that window."""
        before = _insight("already_clinched", "Alpha", rendered="Alpha clinched")
        within = _insight("already_clinched", "Bravo", rendered="Bravo clinched")
        after = _insight("already_clinched", "Charlie", rendered="Charlie clinched")
        rows = [
            _row("4", 3, date(2025, 10, 1), [before]),
            _row("4", 3, date(2025, 10, 10), [within]),
            _row("4", 3, date(2025, 10, 20), [after]),
        ]
        feed = _insights_from_snapshot_rows(
            rows, date_from=date(2025, 10, 5), date_to=date(2025, 10, 15), team=None, limit=50
        )
        assert [i.human_text for i in feed] == ["Bravo clinched"]

    def test_team_filter_matches_subject_team(self):
        """The team filter matches an insight whose subject is that team."""
        ins = _insight("already_clinched", "Taylorsville", rendered="Taylorsville clinched")
        rows = [_row("4", 3, date(2025, 10, 10), [ins])]
        feed = _insights_from_snapshot_rows(rows, date_from=None, date_to=None, team="Taylorsville", limit=50)
        assert len(feed) == 1

    def test_team_filter_matches_condition_participant_not_just_subject(self):
        """The team filter also matches a team named only in a condition, not just the subject."""
        ins = _insight(
            "clinch_seed",
            "Taylorsville",
            seed=1,
            conditions=(GameResult("Taylorsville", "Stringer"),),
            rendered="Taylorsville clinches 1st seed: Taylorsville beats Stringer",
        )
        rows = [_row("4", 3, date(2025, 10, 10), [ins])]
        feed = _insights_from_snapshot_rows(rows, date_from=None, date_to=None, team="Stringer", limit=50)
        assert len(feed) == 1

    def test_team_filter_excludes_unrelated_insight(self):
        """The team filter excludes an insight that names neither the subject nor any condition team."""
        ins = _insight("already_clinched", "Taylorsville", rendered="Taylorsville clinched")
        rows = [_row("4", 3, date(2025, 10, 10), [ins])]
        feed = _insights_from_snapshot_rows(rows, date_from=None, date_to=None, team="Petal", limit=50)
        assert feed == []

    def test_limit_truncates_after_sorting_newest_first(self):
        """limit caps the feed at its most recent N insights, applied after sorting."""
        rows = [
            _row(
                "4",
                3,
                date(2025, 10, d),
                [_insight("already_clinched", f"Team{d}", rendered=f"Team{d} clinched")],
            )
            for d in (3, 10, 17)
        ]
        feed = _insights_from_snapshot_rows(rows, date_from=None, date_to=None, team=None, limit=2)
        assert len(feed) == 2
        assert feed[0].human_text == "Team17 clinched"
        assert feed[1].human_text == "Team10 clinched"

    def test_class_and_region_pass_through_as_ints(self):
        """The row's class and region strings/ints are carried through as ints on the output entry."""
        ins = _insight("already_clinched", "Taylorsville", rendered="Taylorsville clinched")
        rows = [_row("4", 3, date(2025, 10, 10), [ins])]
        feed = _insights_from_snapshot_rows(rows, date_from=None, date_to=None, team=None, limit=50)
        assert feed[0].class_ == 4
        assert feed[0].region == 3

    def test_kind_derived_on_output(self):
        """Each output entry's kind is derived via _insight_kind from its type and seed."""
        ins = _insight("clinch_seed", "Taylorsville", seed=2, rendered="Taylorsville clinches 2nd seed")
        rows = [_row("4", 3, date(2025, 10, 10), [ins])]
        feed = _insights_from_snapshot_rows(rows, date_from=None, date_to=None, team=None, limit=50)
        assert feed[0].kind == "clinch_seed_2"

    def test_empty_rows_returns_empty_feed(self):
        """No snapshot rows produces an empty feed."""
        assert _insights_from_snapshot_rows([], date_from=None, date_to=None, team=None, limit=50) == []
