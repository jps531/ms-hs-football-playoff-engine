"""Unit tests for backend.helpers.api_helpers.build_season_dates (GET /seasons/{season}/dates)."""

from datetime import date

from backend.helpers.api_helpers import build_season_dates

WEEK8A = date(2025, 10, 10)
WEEK8B = date(2025, 10, 11)
WEEK9 = date(2025, 10, 17)
FIRST_ROUND = date(2025, 11, 7)
QUARTERFINALS = date(2025, 11, 14)


def _entries_by_date(game_rows, snapshot_dates):
    return {e.date: e for e in build_season_dates(game_rows, snapshot_dates)}


class TestGamesDates:
    def test_num_games_dedupes_the_two_school_perspective_rows(self):
        rows = [
            (WEEK8A, None, "Alpha", "Beta"),
            (WEEK8A, None, "Beta", "Alpha"),
            (WEEK8A, None, "Gamma", "Delta"),
            (WEEK8A, None, "Delta", "Gamma"),
        ]
        entries = _entries_by_date(rows, set())
        assert entries[WEEK8A].kind == "games"
        assert entries[WEEK8A].num_games == 2
        assert entries[WEEK8A].round is None

    def test_one_sided_row_still_counts_as_one_game(self):
        """An out-of-state opponent with no mirrored row in this DB still counts once."""
        rows = [(WEEK8A, None, "Alpha", "Out Of State School")]
        entries = _entries_by_date(rows, set())
        assert entries[WEEK8A].num_games == 1

    def test_playoff_date_has_round_and_no_week(self):
        rows = [(FIRST_ROUND, "First Round", "Alpha", "Beta")]
        entries = _entries_by_date(rows, set())
        assert entries[FIRST_ROUND].round == "first_round"
        assert entries[FIRST_ROUND].week is None

    def test_championship_game_round_normalizes_to_snake_case(self):
        rows = [(date(2025, 12, 5), "Championship Game", "Alpha", "Beta")]
        entries = _entries_by_date(rows, set())
        assert entries[date(2025, 12, 5)].round == "championship_game"

    def test_regular_season_weeks_are_dense_ranked_ascending(self):
        rows = [
            (WEEK8A, None, "Alpha", "Beta"),
            (WEEK9, None, "Gamma", "Delta"),
        ]
        entries = _entries_by_date(rows, set())
        assert entries[WEEK8A].week == 1
        assert entries[WEEK9].week == 2

    def test_mixed_round_values_on_one_date_last_non_null_wins_without_error(self):
        """Documented simplification: doesn't validate a single date has one round statewide."""
        rows = [
            (FIRST_ROUND, "First Round", "Alpha", "Beta"),
            (FIRST_ROUND, "Second Round", "Gamma", "Delta"),
        ]
        entries = _entries_by_date(rows, set())
        assert entries[FIRST_ROUND].round == "second_round"


class TestSnapshotDates:
    def test_snapshot_only_date_between_game_dates_inherits_prior_week(self):
        rows = [
            (WEEK8A, None, "Alpha", "Beta"),
            (WEEK9, None, "Gamma", "Delta"),
        ]
        mid_week_snapshot = date(2025, 10, 14)
        entries = _entries_by_date(rows, {mid_week_snapshot})
        e = entries[mid_week_snapshot]
        assert e.kind == "snapshot"
        assert e.week == 1  # inherits WEEK8A's week, not WEEK9's

    def test_snapshot_during_playoffs_has_no_week(self):
        rows = [
            (WEEK8A, None, "Alpha", "Beta"),
            (FIRST_ROUND, "First Round", "Alpha", "Beta"),
        ]
        during_playoffs_snapshot = date(2025, 11, 10)
        entries = _entries_by_date(rows, {during_playoffs_snapshot})
        assert entries[during_playoffs_snapshot].kind == "snapshot"
        assert entries[during_playoffs_snapshot].week is None

    def test_snapshot_before_any_regular_season_date_has_no_week(self):
        rows = [(WEEK9, None, "Gamma", "Delta")]
        early_snapshot = date(2025, 10, 1)
        entries = _entries_by_date(rows, {early_snapshot})
        assert entries[early_snapshot].week is None

    def test_snapshot_coinciding_with_a_games_date_is_not_duplicated(self):
        rows = [(WEEK8A, None, "Alpha", "Beta")]
        entries = build_season_dates(rows, {WEEK8A})
        matching = [e for e in entries if e.date == WEEK8A]
        assert len(matching) == 1
        assert matching[0].kind == "games"

    def test_no_game_rows_or_snapshots_returns_empty_list(self):
        assert build_season_dates([], set()) == []


class TestSpecExampleReproduction:
    """Reproduces the exact three-row example from docs/API_FRONTEND_GAPS.md §4."""

    def test_full_example(self):
        d1, d2, d3 = date(2025, 10, 10), date(2025, 10, 14), date(2025, 11, 7)
        game_rows = [(d1, None, f"School{i}A", f"School{i}B") for i in range(112)]
        game_rows += [(d3, "First Round", f"PSchool{i}A", f"PSchool{i}B") for i in range(96)]
        entries = _entries_by_date(game_rows, {d2})

        assert entries[d1].kind == "games"
        assert entries[d1].week == 1
        assert entries[d1].num_games == 112
        assert entries[d1].round is None

        assert entries[d2].kind == "snapshot"
        assert entries[d2].week == 1

        assert entries[d3].kind == "games"
        assert entries[d3].week is None
        assert entries[d3].round == "first_round"
        assert entries[d3].num_games == 96

    def test_results_sorted_by_date_ascending(self):
        d1, d2, d3 = date(2025, 10, 10), date(2025, 10, 14), date(2025, 11, 7)
        rows = [(d3, "First Round", "A", "B"), (d1, None, "C", "D")]
        entries = build_season_dates(rows, {d2})
        assert [e.date for e in entries] == [d1, d2, d3]
