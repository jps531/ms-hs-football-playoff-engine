"""Playoff-round odds: what the bracket math runs on vs. what region_standings stores.

During the playoffs the bracket math needs knocked-out teams at zero so they
drop out of later rounds, but the stored seeding odds are what readers see:
a team that lost in the quarterfinals is still the No. 2 seed that made the
playoffs, so its stored odds must keep that seeding for the rest of the season.
"""

from datetime import date
from unittest.mock import MagicMock

from backend.prefect import playoff_pipeline
from backend.prefect.playoff_pipeline import playoff_round_odds

TEAMS = ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]
SEEDS = {"Alpha": 1, "Bravo": 2, "Charlie": 3, "Delta": 4}  # Echo missed the playoffs


def _seed_vector(o):
    """(p1, p2, p3, p4, p_playoffs) for one StandingsOdds."""
    return (o.p1, o.p2, o.p3, o.p4, o.p_playoffs)


class TestPlayoffRoundOdds:
    """Alive odds for the bracket math, final seeding for the stored row."""

    def test_alive_team_holds_its_seed_in_both(self):
        """A team still in the bracket is 1.0 for its seed and the playoffs either way."""
        alive, stored = playoff_round_odds(TEAMS, SEEDS, alive_seeds={1, 3})
        for odds in (alive, stored):
            assert _seed_vector(odds["Alpha"]) == (1.0, 0.0, 0.0, 0.0, 1.0)
            assert odds["Alpha"].clinched and not odds["Alpha"].eliminated

    def test_knocked_out_team_keeps_its_seeding_in_the_stored_row(self):
        """Out of the bracket: zero for the bracket math, but the stored row keeps No. 2 and the playoffs."""
        alive, stored = playoff_round_odds(TEAMS, SEEDS, alive_seeds={1, 3})
        assert _seed_vector(alive["Bravo"]) == (0.0, 0.0, 0.0, 0.0, 0.0)
        assert _seed_vector(stored["Bravo"]) == (0.0, 1.0, 0.0, 0.0, 1.0)
        assert stored["Bravo"].final_playoffs == 1.0
        for odds in (alive, stored):
            assert odds["Bravo"].clinched and odds["Bravo"].eliminated

    def test_team_that_missed_the_playoffs_stays_out(self):
        """A non-playoff team is zero, not clinched, and eliminated in both."""
        alive, stored = playoff_round_odds(TEAMS, SEEDS, alive_seeds={1, 3})
        for odds in (alive, stored):
            assert _seed_vector(odds["Echo"]) == (0.0, 0.0, 0.0, 0.0, 0.0)
            assert not odds["Echo"].clinched and odds["Echo"].eliminated

    def test_whole_region_out_still_stores_every_seed(self):
        """Even once every team from the region is out, the stored rows keep all four seeds."""
        _, stored = playoff_round_odds(TEAMS, SEEDS, alive_seeds=set())
        assert [next(s for s in (1, 2, 3, 4) if getattr(stored[t], f"p{s}") == 1.0) for t in SEEDS] == [1, 2, 3, 4]


class TestFetchActualSeedings:
    """Seeds come from each school's latest locked-seed row before the playoffs."""

    def _run(self, monkeypatch, rows, **kwargs):
        """Run the task body against a mocked cursor; return (result, executed SQL, params)."""
        cur = MagicMock()
        cur.fetchall.return_value = rows
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        monkeypatch.setattr(
            playoff_pipeline,
            "get_database_connection",
            MagicMock(return_value=MagicMock(__enter__=lambda s: conn, __exit__=lambda *a: None)),
        )
        result = playoff_pipeline.fetch_actual_seedings.fn(2025, 1, **kwargs)
        sql, params = cur.execute.call_args.args
        return result, sql, params

    def test_reads_per_school_before_the_first_playoff_date(self, monkeypatch):
        """The cutoff is passed through, and the query picks each school's own newest locked row."""
        result, sql, params = self._run(monkeypatch, [("Alpha", 1, 1), ("Bravo", 1, 2)], before=date(2025, 11, 7))
        assert result == {"Alpha": (1, 1), "Bravo": (1, 2)}
        assert params == (2025, 1, date(2025, 11, 7), date(2025, 11, 7))
        assert "DISTINCT ON (rs.school)" in sql
        assert "rs.as_of_date < %s::date" in sql

    def test_rows_without_a_locked_seed_are_skipped(self, monkeypatch):
        """A row whose seed can't be read is left out rather than guessed."""
        result, _, params = self._run(monkeypatch, [("Alpha", 1, 1), ("Echo", 1, None)])
        assert result == {"Alpha": (1, 1)}
        assert params == (2025, 1, None, None)


class TestClearStalePlayoffSnapshots:
    """Snapshots dated in a class's playoffs, off its playoff dates, would shadow the final playoff rows."""

    def test_deletes_off_date_rows_in_every_snapshot_table(self, monkeypatch):
        """Each table is cleared from the first playoff date on, keeping the playoff dates themselves."""
        cur = MagicMock()
        cur.rowcount = 2
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        monkeypatch.setattr(
            playoff_pipeline,
            "get_database_connection",
            MagicMock(return_value=MagicMock(__enter__=lambda s: conn, __exit__=lambda *a: None)),
        )
        keep = [date(2025, 11, 7), date(2025, 12, 4)]
        deleted = playoff_pipeline.clear_stale_playoff_snapshots.fn(2025, 1, date(2025, 11, 7), keep)

        assert deleted == {"region_standings": 2, "region_computation_state": 2, "region_scenarios": 2}
        calls = [c.args for c in cur.execute.call_args_list]
        assert [sql.split()[2] for sql, _ in calls] == [
            "region_standings",
            "region_computation_state",
            "region_scenarios",
        ]
        for sql, _ in calls:
            assert "as_of_date >= %s AND NOT (as_of_date = ANY(%s))" in sql
        # region_scenarios stores class as text; the others as an integer.
        assert [params for _, params in calls] == [
            (2025, 1, date(2025, 11, 7), keep),
            (2025, 1, date(2025, 11, 7), keep),
            (2025, "1", date(2025, 11, 7), keep),
        ]
        conn.commit.assert_called_once()
