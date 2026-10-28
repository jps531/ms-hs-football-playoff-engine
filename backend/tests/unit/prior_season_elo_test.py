"""fetch_prior_season_elo (backend/prefect/region_scenarios_pipeline.py): the rating a team carries into a new
season is its last one from the season before, not whichever of that season's dated snapshots the database
happens to return last."""

import re
from contextlib import contextmanager

import backend.prefect.region_scenarios_pipeline as pipeline


def _fetch(monkeypatch, rows: list[tuple[str, float]]) -> tuple[dict[str, float], str, tuple]:
    """Run the task against a cursor that returns *rows*; return its result and the SQL and params it sent."""
    seen: dict = {}

    class Cursor:
        """Records the query and hands back *rows*."""

        def execute(self, sql, params):
            """Record what would be sent."""
            seen.update(sql=sql, params=params)

        def fetchall(self):
            """The rows the database would return."""
            return rows

    class Conn:
        """A connection that only needs cursor()."""

        @contextmanager
        def cursor(self):
            """Yield the recording cursor."""
            yield Cursor()

    @contextmanager
    def connect():
        """Yield the fake connection."""
        yield Conn()

    monkeypatch.setattr(pipeline, "get_database_connection", connect)
    return pipeline.fetch_prior_season_elo.fn(2025), seen["sql"], seen["params"]


def test_each_school_gets_its_latest_dated_rating(monkeypatch):
    """team_ratings has a row per snapshot date; the query must keep one per school, the most recent."""
    result, sql, params = _fetch(monkeypatch, [("Oxford", 1412.5), ("Raleigh", 1188.0)])
    flat = " ".join(sql.split())
    assert "DISTINCT ON (school)" in flat
    assert re.search(r"ORDER BY school, as_of_date DESC\b", flat)
    assert params == (2025,)
    assert result == {"Oxford": 1412.5, "Raleigh": 1188.0}


def test_no_prior_season_means_no_carryover(monkeypatch):
    """With no ratings from the season before, no team carries a rating over."""
    result, _, _ = _fetch(monkeypatch, [])
    assert result == {}
