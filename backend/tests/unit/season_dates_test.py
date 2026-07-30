"""Unit tests for backend.helpers.api_helpers.build_season_dates (GET /seasons/{season}/dates)."""

from datetime import date

from backend.helpers.api_helpers import _format_class_range, build_season_dates

GameRow = tuple[date, str | None, int, str, str]

# 2025-08-28 is a Thursday, 08-29 Friday, 08-30 Saturday -- all in the same Mon-Sun week.
WEEK1_THU = date(2025, 8, 28)
WEEK1_FRI = date(2025, 8, 29)
WEEK1_SAT = date(2025, 8, 30)
WEEK2_FRI = date(2025, 9, 5)
FIRST_ROUND = date(2025, 11, 7)
CHAMPIONSHIP = date(2025, 12, 5)


def _entries_by_date(game_rows: list[GameRow]):
    """Index build_season_dates' output by date for convenient per-date assertions."""
    return {e.date: e for e in build_season_dates(game_rows)}


class TestFormatClassRange:
    """Coverage for collapsing a sorted list of class numbers into MHSAA-style shorthand."""

    def test_single_class(self):
        """A single class renders without a range."""
        assert _format_class_range([3]) == "3A"

    def test_contiguous_run(self):
        """A contiguous run of classes collapses to a lo-hi range."""
        assert _format_class_range([1, 2, 3, 4]) == "1A-4A"

    def test_multiple_contiguous_runs(self):
        """A single contiguous run still collapses correctly at its boundaries."""
        assert _format_class_range([5, 6, 7]) == "5A-7A"

    def test_non_contiguous_falls_back_to_comma_list(self):
        """Non-contiguous classes fall back to a comma-separated list."""
        assert _format_class_range([1, 3]) == "1A, 3A"

    def test_empty_list(self):
        """An empty class list renders as an empty string."""
        assert _format_class_range([]) == ""


class TestGamesDatesUnambiguous:
    """Coverage for dates where every class agrees on week/round, so no ambiguity handling kicks in."""

    def test_thu_fri_sat_collapse_into_one_monday_anchored_week(self):
        """Thursday, Friday, and Saturday games in the same week all get the same week number."""
        rows: list[GameRow] = [
            (WEEK1_THU, None, 1, "Alpha", "Beta"),
            (WEEK1_FRI, None, 1, "Gamma", "Delta"),
            (WEEK1_SAT, None, 1, "Epsilon", "Zeta"),
        ]
        entries = _entries_by_date(rows)
        assert entries[WEEK1_THU].week == 1
        assert entries[WEEK1_FRI].week == 1
        assert entries[WEEK1_SAT].week == 1

    def test_num_games_dedupes_the_two_school_perspective_rows(self):
        """Each contest's two school-perspective rows dedupe into a single game count."""
        rows: list[GameRow] = [
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
        """A game with only one in-state row (e.g. an out-of-state opponent) still counts once."""
        rows: list[GameRow] = [(WEEK1_THU, None, 1, "Alpha", "Out Of State School")]
        assert _entries_by_date(rows)[WEEK1_THU].num_games == 1

    def test_distinct_weeks_are_dense_ranked_ascending(self):
        """Distinct weeks get consecutive, ascending, dense-ranked week numbers."""
        rows: list[GameRow] = [
            (WEEK1_THU, None, 1, "Alpha", "Beta"),
            (WEEK2_FRI, None, 1, "Gamma", "Delta"),
        ]
        entries = _entries_by_date(rows)
        assert entries[WEEK1_THU].week == 1
        assert entries[WEEK2_FRI].week == 2

    def test_clean_playoff_date_all_classes_agree(self):
        """A playoff date where every class agrees on the round resolves to that round unambiguously."""
        rows: list[GameRow] = [
            (FIRST_ROUND, "First Round", 1, "Alpha", "Beta"),
            (FIRST_ROUND, "First Round", 2, "Gamma", "Delta"),
        ]
        e = _entries_by_date(rows)[FIRST_ROUND]
        assert e.round == "first_round"
        assert e.week == 1  # only date in the pool -> week 1, not null: weeks count through the playoffs
        assert e.description == "First Round"

    def test_championship_game_round_normalizes_but_description_stays_raw(self):
        """The normalized snake_case `round` and the human-readable `description` diverge as expected."""
        rows: list[GameRow] = [(CHAMPIONSHIP, "Championship Game", 7, "Alpha", "Beta")]
        e = _entries_by_date(rows)[CHAMPIONSHIP]
        assert e.round == "championship_game"
        assert e.week == 1
        assert e.description == "Championship Game"


class TestCrossClassAmbiguity:
    """1A-4A and 5A-7A run offset playoff schedules: a date can mean different things per class."""

    def test_regular_season_vs_playoff_split_is_ambiguous_unscoped(self):
        """A date that's regular season for one class and playoffs for another is ambiguous unscoped."""
        rows: list[GameRow] = [
            (FIRST_ROUND, None, 6, "Alpha5A7A", "Beta5A7A"),  # 5A-7A: still regular season
            (FIRST_ROUND, "First Round", 1, "Gamma1A4A", "Delta1A4A"),  # 1A-4A: playoffs
        ]
        e = _entries_by_date(rows)[FIRST_ROUND]
        assert e.round is None
        assert e.week == 1  # only date in the pool; week is populated even though round is ambiguous
        assert e.num_games == 2
        assert e.description is not None
        assert "First Round (1A)" in e.description
        assert "Week 1 (6A)" in e.description
        assert e.description.count(" / ") == 1

    def test_two_different_playoff_rounds_on_the_same_date_is_ambiguous(self):
        """A date that's a different playoff round per class is ambiguous."""
        rows: list[GameRow] = [
            (date(2025, 11, 14), "First Round", 6, "Alpha", "Beta"),
            (date(2025, 11, 14), "Second Round", 1, "Gamma", "Delta"),
        ]
        e = _entries_by_date(rows)[date(2025, 11, 14)]
        assert e.round is None
        assert e.week == 1
        assert e.description is not None
        assert "First Round (6A)" in e.description
        assert "Second Round (1A)" in e.description

    def test_scoping_to_one_class_removes_the_ambiguity(self):
        """Pre-filtering game_rows to a single class (as the router does via `class`) always resolves cleanly."""
        rows: list[GameRow] = [(FIRST_ROUND, None, 6, "Alpha5A7A", "Beta5A7A")]
        e = _entries_by_date(rows)[FIRST_ROUND]
        assert e.round is None
        assert e.week == 1
        assert e.description == "Week 1"

    def test_disagreeing_classes_grouped_together_in_description(self):
        """Multiple classes agreeing on a round are grouped into one range within the description."""
        rows: list[GameRow] = [
            (FIRST_ROUND, "First Round", 1, "A", "B"),
            (FIRST_ROUND, "First Round", 2, "C", "D"),
            (FIRST_ROUND, "First Round", 3, "E", "F"),
            (FIRST_ROUND, "First Round", 4, "G", "H"),
            (FIRST_ROUND, None, 6, "I", "J"),
        ]
        e = _entries_by_date(rows)[FIRST_ROUND]
        assert e.description is not None
        assert "First Round (1A-4A)" in e.description
        assert "Week 1 (6A)" in e.description


class TestSeasonStart:
    """Coverage for the synthetic season_start entry."""

    def test_season_start_is_one_day_before_the_first_game(self):
        """The season_start entry lands one day before the earliest game, regardless of row order."""
        rows: list[GameRow] = [
            (WEEK2_FRI, None, 1, "Alpha", "Beta"),
            (WEEK1_THU, None, 1, "Gamma", "Delta"),
        ]
        entries = build_season_dates(rows)
        start = entries[0]
        assert start.date == date(2025, 8, 27)
        assert start.kind == "season_start"
        assert start.description == "Season Start"
        assert start.week == 0
        assert start.round is None
        assert start.num_games is None

    def test_no_rows_produces_no_season_start_entry(self):
        """An empty game_rows list produces no entries at all."""
        assert build_season_dates([]) == []


class TestContinuousWeekNumbering:
    """Reproduces the real 2025 season shape: weeks count 0-15, season_start through championship."""

    def test_weeks_count_continuously_through_the_playoffs(self):
        """Week numbers count continuously from regular season through the championship."""
        rows: list[GameRow] = [
            (date(2025, 8, 28), None, 1, "A1", "B1"),  # week 1
            (date(2025, 9, 4), None, 1, "A2", "B2"),  # week 2
            (date(2025, 9, 11), None, 1, "A3", "B3"),  # week 3
            (date(2025, 9, 18), None, 1, "A4", "B4"),  # week 4
            (date(2025, 9, 25), None, 1, "A5", "B5"),  # week 5
            (date(2025, 10, 2), None, 1, "A6", "B6"),  # week 6
            (date(2025, 10, 9), None, 1, "A7", "B7"),  # week 7
            (date(2025, 10, 16), None, 1, "A8", "B8"),  # week 8
            (date(2025, 10, 23), None, 1, "A9", "B9"),  # week 9
            (date(2025, 10, 30), None, 1, "A10", "B10"),  # week 10
            (date(2025, 11, 6), "First Round", 1, "A11a", "B11a"),  # week 11: 1A-4A playoffs, ...
            (date(2025, 11, 6), None, 6, "A11b", "B11b"),  # ... 5A-7A still regular season
            (date(2025, 11, 14), "Second Round", 1, "A12a", "B12a"),  # week 12: mixed rounds
            (date(2025, 11, 14), "First Round", 6, "A12b", "B12b"),
            (date(2025, 11, 21), "Quarterfinals", 1, "A13", "B13"),  # week 13: clean
            (date(2025, 11, 21), "Quarterfinals", 6, "A13b", "B13b"),
            (date(2025, 11, 28), "Semifinals", 1, "A14", "B14"),  # week 14: clean
            (date(2025, 12, 4), "Championship Game", 1, "A15", "B15"),  # week 15: clean
        ]
        entries = _entries_by_date(rows)

        assert entries[date(2025, 8, 27)].week == 0  # season_start
        assert entries[date(2025, 8, 27)].kind == "season_start"

        for i, d in enumerate(
            [date(2025, 8, 28), date(2025, 9, 4), date(2025, 9, 11), date(2025, 9, 18),
             date(2025, 9, 25), date(2025, 10, 2), date(2025, 10, 9), date(2025, 10, 16),
             date(2025, 10, 23), date(2025, 10, 30)],
            start=1,
        ):
            assert entries[d].week == i
            assert entries[d].round is None

        assert entries[date(2025, 11, 6)].week == 11
        assert entries[date(2025, 11, 6)].round is None  # ambiguous

        assert entries[date(2025, 11, 14)].week == 12
        assert entries[date(2025, 11, 14)].round is None  # ambiguous (two different rounds)

        assert entries[date(2025, 11, 21)].week == 13
        assert entries[date(2025, 11, 21)].round == "quarterfinals"

        assert entries[date(2025, 11, 28)].week == 14
        assert entries[date(2025, 11, 28)].round == "semifinals"

        assert entries[date(2025, 12, 4)].week == 15
        assert entries[date(2025, 12, 4)].round == "championship_game"


class TestOrdering:
    """Coverage for the ordering of the returned entries list."""

    def test_entries_sorted_by_date_ascending(self):
        """Entries are always returned sorted by date ascending, regardless of input row order."""
        rows: list[GameRow] = [
            (FIRST_ROUND, "First Round", 1, "A", "B"),
            (WEEK1_THU, None, 1, "C", "D"),
        ]
        entries = build_season_dates(rows)
        assert [e.date for e in entries] == [date(2025, 8, 27), WEEK1_THU, FIRST_ROUND]
