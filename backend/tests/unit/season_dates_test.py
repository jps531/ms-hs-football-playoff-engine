"""Unit tests for backend.helpers.api_helpers.build_season_dates (GET /seasons/{season}/dates)."""

from datetime import date

from backend.helpers.api_helpers import _format_class_range, build_season_dates

# 2025-08-28 is a Thursday, 08-29 Friday, 08-30 Saturday -- all in the same Mon-Sun week.
WEEK1_THU = date(2025, 8, 28)
WEEK1_FRI = date(2025, 8, 29)
WEEK1_SAT = date(2025, 8, 30)
WEEK2_FRI = date(2025, 9, 5)
FIRST_ROUND = date(2025, 11, 7)
CHAMPIONSHIP = date(2025, 12, 5)


def _entries_by_date(game_rows):
    return {e.date: e for e in build_season_dates(game_rows)}


class TestFormatClassRange:
    def test_single_class(self):
        assert _format_class_range([3]) == "3A"

    def test_contiguous_run(self):
        assert _format_class_range([1, 2, 3, 4]) == "1A-4A"

    def test_multiple_contiguous_runs(self):
        assert _format_class_range([5, 6, 7]) == "5A-7A"

    def test_non_contiguous_falls_back_to_comma_list(self):
        assert _format_class_range([1, 3]) == "1A, 3A"

    def test_empty_list(self):
        assert _format_class_range([]) == ""


class TestGamesDatesUnambiguous:
    def test_thu_fri_sat_collapse_into_one_monday_anchored_week(self):
        rows = [
            (WEEK1_THU, None, 1, "Alpha", "Beta"),
            (WEEK1_FRI, None, 1, "Gamma", "Delta"),
            (WEEK1_SAT, None, 1, "Epsilon", "Zeta"),
        ]
        entries = _entries_by_date(rows)
        assert entries[WEEK1_THU].week == 1
        assert entries[WEEK1_FRI].week == 1
        assert entries[WEEK1_SAT].week == 1

    def test_num_games_dedupes_the_two_school_perspective_rows(self):
        rows = [
            (WEEK1_THU, None, 1, "Alpha", "Beta"),
            (WEEK1_THU, None, 1, "Beta", "Alpha"),
            (WEEK1_THU, None, 1, "Gamma", "Delta"),
            (WEEK1_THU, None, 1, "Delta", "Gamma"),
        ]
        entries = _entries_by_date(rows)
        assert entries[WEEK1_THU].kind == "games"
        assert entries[WEEK1_THU].num_games == 2
        assert entries[WEEK1_THU].round is None
        assert entries[WEEK1_THU].description == "Week 1"

    def test_one_sided_row_still_counts_as_one_game(self):
        rows = [(WEEK1_THU, None, 1, "Alpha", "Out Of State School")]
        assert _entries_by_date(rows)[WEEK1_THU].num_games == 1

    def test_distinct_weeks_are_dense_ranked_ascending(self):
        rows = [
            (WEEK1_THU, None, 1, "Alpha", "Beta"),
            (WEEK2_FRI, None, 1, "Gamma", "Delta"),
        ]
        entries = _entries_by_date(rows)
        assert entries[WEEK1_THU].week == 1
        assert entries[WEEK2_FRI].week == 2

    def test_clean_playoff_date_all_classes_agree(self):
        rows = [
            (FIRST_ROUND, "First Round", 1, "Alpha", "Beta"),
            (FIRST_ROUND, "First Round", 2, "Gamma", "Delta"),
        ]
        e = _entries_by_date(rows)[FIRST_ROUND]
        assert e.round == "first_round"
        assert e.week is None
        assert e.description == "First Round"

    def test_championship_game_round_normalizes_but_description_stays_raw(self):
        rows = [(CHAMPIONSHIP, "Championship Game", 7, "Alpha", "Beta")]
        e = _entries_by_date(rows)[CHAMPIONSHIP]
        assert e.round == "championship_game"
        assert e.description == "Championship Game"


class TestCrossClassAmbiguity:
    """1A-4A and 5A-7A run offset playoff schedules: a date can mean different things per class."""

    def test_regular_season_vs_playoff_split_is_ambiguous_unscoped(self):
        rows = [
            (FIRST_ROUND, None, 6, "Alpha5A7A", "Beta5A7A"),  # 5A-7A: still regular season
            (FIRST_ROUND, "First Round", 1, "Gamma1A4A", "Delta1A4A"),  # 1A-4A: playoffs
        ]
        e = _entries_by_date(rows)[FIRST_ROUND]
        assert e.round is None
        assert e.week is None
        assert e.num_games == 2
        assert "First Round (1A)" in e.description
        assert "Week 1 (6A)" in e.description
        assert e.description.count(" / ") == 1

    def test_two_different_playoff_rounds_on_the_same_date_is_ambiguous(self):
        rows = [
            (date(2025, 11, 14), "First Round", 6, "Alpha", "Beta"),
            (date(2025, 11, 14), "Second Round", 1, "Gamma", "Delta"),
        ]
        e = _entries_by_date(rows)[date(2025, 11, 14)]
        assert e.round is None
        assert e.week is None
        assert "First Round (6A)" in e.description
        assert "Second Round (1A)" in e.description

    def test_scoping_to_one_class_removes_the_ambiguity(self):
        """Pre-filtering game_rows to a single class (as the router does via `class`) always resolves cleanly."""
        rows = [(FIRST_ROUND, None, 6, "Alpha5A7A", "Beta5A7A")]
        e = _entries_by_date(rows)[FIRST_ROUND]
        assert e.round is None
        assert e.week == 1
        assert e.description == "Week 1"

    def test_disagreeing_classes_grouped_together_in_description(self):
        rows = [
            (FIRST_ROUND, "First Round", 1, "A", "B"),
            (FIRST_ROUND, "First Round", 2, "C", "D"),
            (FIRST_ROUND, "First Round", 3, "E", "F"),
            (FIRST_ROUND, "First Round", 4, "G", "H"),
            (FIRST_ROUND, None, 6, "I", "J"),
        ]
        e = _entries_by_date(rows)[FIRST_ROUND]
        assert "First Round (1A-4A)" in e.description
        assert "Week 1 (6A)" in e.description


class TestSeasonStart:
    def test_season_start_is_one_day_before_the_first_game(self):
        rows = [(WEEK2_FRI, None, 1, "Alpha", "Beta"), (WEEK1_THU, None, 1, "Gamma", "Delta")]
        entries = build_season_dates(rows)
        start = entries[0]
        assert start.date == date(2025, 8, 27)
        assert start.kind == "season_start"
        assert start.description == "Season Start"
        assert start.week is None
        assert start.round is None
        assert start.num_games is None

    def test_no_rows_produces_no_season_start_entry(self):
        assert build_season_dates([]) == []


class TestOrdering:
    def test_entries_sorted_by_date_ascending(self):
        rows = [
            (FIRST_ROUND, "First Round", 1, "A", "B"),
            (WEEK1_THU, None, 1, "C", "D"),
        ]
        entries = build_season_dates(rows)
        assert [e.date for e in entries] == [date(2025, 8, 27), WEEK1_THU, FIRST_ROUND]
