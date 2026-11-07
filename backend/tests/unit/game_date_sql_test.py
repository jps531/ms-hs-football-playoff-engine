"""``games_effective.game_date`` gives a game one date in both schools' rows. The migrations repeat the
view (``sql/init.sql``) and the standings function (``sql/get_standings_for_region.sql``); these fail until
the newest migration of each matches, and until every date cutoff on games goes by ``game_date``."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = (ROOT / "sql/migrations/2026_10_game_date.sql").read_text()

# The newest migration that re-creates the view (file names don't sort by date).
VIEW_MIGRATION = (ROOT / "sql/migrations/2026_11_opponent_corrections.sql").read_text()


def _view(sql: str) -> str:
    """The ``games_effective`` view's definition in *sql*."""
    match = re.search(r"CREATE OR REPLACE VIEW games_effective AS.*?\) pick;", sql, re.S)
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


def test_a_game_has_one_score_in_both_schools_rows():
    """A row not yet final takes the other school's final score; two final rows that disagree read as
    not final with no score; a correction on either row wins. (The cases are checked against Postgres
    in the PR; these keep the rules in the view.)"""
    view = _view(VIEW_MIGRATION)
    assert "WHERE o.game_id = games.game_id AND o.school = games.opponent" in view
    assert "WHEN own.corrected THEN 'own'" in view
    assert "WHEN other.corrected AND other.final IS TRUE THEN 'borrow'" in view
    assert "WHEN own.final IS NOT TRUE AND other.final IS TRUE AND other.result IS NOT NULL THEN 'borrow'" in view
    assert "CASE pick.mode WHEN 'disagree' THEN FALSE WHEN 'canceled' THEN FALSE WHEN 'borrow' THEN TRUE" in view
    assert "WHEN pick.mode = 'borrow' THEN other.points_against ELSE own.points_for END AS points_for" in view
    # The view's columns keep their order (CREATE OR REPLACE VIEW only adds columns at the end).
    assert view.rstrip().split("pick.mode = 'borrow' AS score_from_opponent,")[1].split("FROM games")[0].strip() == (
        "pick.mode = 'disagree' AS scores_disagree"
    )


def test_a_canceled_game_is_never_final_and_has_no_score():
    """First in the order, and neither row's final counts while it's canceled (so nothing is borrowed)."""
    view = _view(VIEW_MIGRATION)
    assert view.index("WHEN own.game_status = 'canceled' THEN 'canceled'") < view.index("WHEN own.corrected THEN")
    assert "CASE WHEN pick.mode IN ('disagree', 'canceled') THEN NULL" in view
    assert view.count("game_status, '') <> 'canceled' AS final") == 2


def _functions(sql: str) -> dict[str, str]:
    """The opponent-correction functions in *sql*, by name."""
    return {
        m.group(1): m.group(0)
        for m in re.finditer(r"CREATE OR REPLACE FUNCTION (\w+_game_opponent)\(.*?\$\$ LANGUAGE \w+;", sql, re.S)
    }


def test_the_migration_creates_the_opponent_functions_override_helpers_does():
    helpers = _functions((ROOT / "sql/override_helpers.sql").read_text())
    assert set(helpers) == {"set_game_opponent", "clear_game_opponent"}
    assert _functions(VIEW_MIGRATION) == helpers


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
