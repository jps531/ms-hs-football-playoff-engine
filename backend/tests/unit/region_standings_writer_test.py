"""write_region_standings (backend/prefect/region_scenarios_pipeline.py): every row is stamped with the model
version and computation time that the archive trigger copies, and the SQL's columns, placeholders and row
values stay in step."""

import re
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import backend.prefect.region_scenarios_pipeline as pipeline
from backend.helpers.data_classes import Standings, StandingsOdds

SQL_DIR = Path(__file__).resolve().parents[3] / "sql"


def _capture(monkeypatch) -> dict:
    """Stub the connection and execute_values; return where the call's SQL, rows and template land."""
    seen: dict = {}

    class Conn:
        """A connection that only needs cursor() and commit()."""

        @contextmanager
        def cursor(self):
            """Yield a dummy cursor."""
            yield object()

        def commit(self):
            """Nothing to commit."""

    @contextmanager
    def connect():
        """Yield the fake connection."""
        yield Conn()

    def execute_values(cur, sql, rows, template, page_size):
        """Record what would be sent."""
        seen.update(sql=sql, rows=rows, template=template)

    monkeypatch.setattr(pipeline, "get_database_connection", connect)
    monkeypatch.setattr(pipeline, "execute_values", execute_values)
    return seen


def test_rows_carry_model_version_and_counts_line_up(monkeypatch):
    """Each row ends with MODEL_VERSION; computed_at is NOW() in the template; columns match values."""
    seen = _capture(monkeypatch)
    standings = [Standings("Oxford", 7, 2, 2026, 6, 1, 0, 3, 0, 0)]
    odds = {"Oxford": StandingsOdds("Oxford", 0.5, 0.3, 0.1, 0.05, 0.95, 0.95, False, False)}

    assert pipeline.write_region_standings.fn(standings, odds, 7, 2, 2026, as_of_date=date(2026, 10, 16)) == 1

    (row,) = seen["rows"]
    assert row[-1] == pipeline.MODEL_VERSION
    columns = re.search(r"INSERT INTO region_standings \((.*?)\)\s*VALUES", seen["sql"], re.S).group(1)
    names = [c.strip() for c in columns.split(",")]
    assert names[-2:] == ["model_version", "computed_at"]
    assert seen["template"].count("%s") == len(row) == len(names) - 1
    assert seen["template"].endswith("NOW())")
    assert "model_version = EXCLUDED.model_version" in seen["sql"]
    assert "computed_at = EXCLUDED.computed_at" in seen["sql"]


def test_fresh_databases_get_the_archive_too():
    """init.sql (fresh installs) and the migration (existing ones) both create the archive and its triggers."""
    init = (SQL_DIR / "init.sql").read_text()
    migration = (SQL_DIR / "migrations" / "2026_10_region_standings_archive.sql").read_text()
    for text in (init, migration):
        assert "CREATE TABLE IF NOT EXISTS region_standings_archive" in text
        assert "CREATE TRIGGER region_standings_archive_write" in text
        assert "CREATE TRIGGER region_standings_archive_guard" in text
    assert "model_version   TEXT" in init
