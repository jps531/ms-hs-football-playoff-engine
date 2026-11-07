"""Past games one school's AHSFHS page lists and its opponent's doesn't, in the daily email."""

from contextlib import contextmanager
from datetime import date

import backend.helpers.schedule_conflicts as sc
from backend.helpers import attention

# (date, school, opponent, result, points_for, points_against, what the opponent's page lists that week)
AMANDA_ELZY = (date(2026, 8, 28), "Amanda Elzy", "Leflore County", "L", 0, 42, "Shaw")


def test_each_game_says_what_each_page_lists():
    """The school's page with its score, and the opponent's page that week (or nothing)."""
    rows = [
        AMANDA_ELZY,
        (date(2025, 9, 12), "Forest Hill", "Bay Springs", "W", 22, 20, "Jim Hill"),
        (date(2026, 9, 18), "Pearl", "Brandon", None, None, None, None),
    ]
    assert sc.conflict_lines(rows) == [
        "Fri, Aug 28: Amanda Elzy's page lists Leflore County (L 0–42); Leflore County's page lists Shaw that week",
        "Fri, Sep 12: Forest Hill's page lists Bay Springs (W 22–20); Bay Springs' page lists Jim Hill that week",
        "Fri, Sep 18: Pearl's page lists Brandon; Brandon's page has no game that week",
    ]


def test_the_query_asks_for_past_unpaired_games_against_in_state_schools():
    """In-state opponents only (school_seasons), none canceled, dated before today, and no row of the
    same game from the opponent."""
    sql = " ".join(sc._SQL.split())
    assert "JOIN school_seasons os ON os.school = g.opponent AND os.season = g.season" in sql
    assert "g.date < %s" in sql and "COALESCE(g.game_status, '') <> 'canceled'" in sql
    assert "NOT EXISTS (SELECT 1 FROM games x WHERE x.game_id = g.game_id AND x.school = g.opponent)" in sql


def test_each_conflict_is_noted_for_the_email(monkeypatch):
    """The season's games before today (Central), each noted under its own heading."""
    asked = []

    class Cursor:
        def execute(self, sql, params):
            asked.append(params)

        def fetchall(self):
            return [AMANDA_ELZY]

    class Conn:
        @contextmanager
        def cursor(self):
            yield Cursor()

    @contextmanager
    def connection():
        yield Conn()

    monkeypatch.setattr(sc, "get_database_connection", connection)
    attention.clear()
    assert sc.note_schedule_conflicts(2026, today=date(2026, 11, 8)) == 1
    assert asked == [(2026, date(2026, 11, 8))]
    assert list(attention.take()) == [attention.SCHEDULES_DISAGREE]
