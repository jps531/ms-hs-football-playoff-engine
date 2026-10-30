"""``games_effective.game_date`` gives a game one date in both schools' rows. The migrations repeat the
view (``sql/init.sql``) and the standings function (``sql/get_standings_for_region.sql``); these fail until
the newest migration of each matches, and until every date cutoff on games goes by ``game_date``."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = (ROOT / "sql/migrations/2026_10_game_date.sql").read_text()

# The newest migration that re-creates the view (file names don't sort by date).
VIEW_MIGRATION = (ROOT / "sql/migrations/2026_10_game_id.sql").read_text()


def _view(sql: str) -> str:
    """The ``games_effective`` view's definition in *sql*."""
    match = re.search(r"CREATE OR REPLACE VIEW games_effective AS.*?FROM games;", sql, re.S)
    assert match, "no games_effective view"
    return match.group(0)


def _function(sql: str) -> str:
    """The ``get_standings_for_region`` definition in *sql*."""
    match = re.search(r"CREATE OR REPLACE FUNCTION public\.get_standings_for_region.*?\$function\$\s*;", sql, re.S)
    assert match, "no get_standings_for_region"
    return match.group(0)


def test_the_latest_migration_creates_the_view_init_sql_does():
    assert _view(VIEW_MIGRATION) == _view((ROOT / "sql/init.sql").read_text())


def test_the_migration_creates_the_standings_function_its_file_does():
    assert _function(MIGRATION) == _function((ROOT / "sql/get_standings_for_region.sql").read_text())


def test_game_date_is_the_latest_date_of_the_games_rows():
    """Both schools' rows share a game_id (paired within a few days, so a playoff rematch is its own game)."""
    view = _view(VIEW_MIGRATION)
    assert "(SELECT MAX(o.date) FROM games o WHERE o.game_id = games.game_id) AS game_date" in view


def test_the_standings_cutoff_goes_by_game_date():
    fn = _function(MIGRATION)
    assert "p_cutoff_date IS NULL OR g.game_date <= p_cutoff_date" in fn
    assert not re.search(r"\bg\.date\b", fn)


def test_no_pipeline_or_api_cutoff_on_games_goes_by_the_row_date():
    """A cutoff on a row's own date counts a game for one school and not the other when the source
    dates the two rows apart. The travel stats are the exception: they read only the away school's
    own row, so its own date is the one that school played on."""
    for path in ("backend/prefect/region_scenarios_pipeline.py", "backend/helpers/api_helpers.py"):
        lines = (ROOT / path).read_text().splitlines()
        cutoffs = [
            line
            for line in lines
            if re.search(r"(?<![\w.])(?:g\.)?date\s*(?:<=|>)\s*%s", line) and "g.location = 'away'" not in line
        ]
        assert not cutoffs, (path, cutoffs)
