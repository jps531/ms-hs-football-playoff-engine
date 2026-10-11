"""Unit tests for backend.prefect.ahsfhs_schedule_pipeline.

Covers round-name sanitization in parse_ahsfhs_schedule, in particular the
classification-dependent mapping of "2nd Round Playoffs" (5A-7A brackets
have no real second round, so their round 2 is the Quarterfinals; 1A-4A
brackets have a real Second Round as round 2, with Quarterfinals as round 3).
"""

import logging

import pytest

import backend.prefect.ahsfhs_schedule_pipeline as pipeline
from backend.prefect.ahsfhs_schedule_pipeline import parse_ahsfhs_schedule

SEASON = 2025


@pytest.fixture(autouse=True)
def _stub_run_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    """parse_ahsfhs_schedule calls Prefect's get_run_logger(), which requires a live
    flow/task run context; stub it so the pure parsing logic is testable in isolation."""
    monkeypatch.setattr(pipeline, "get_run_logger", lambda: logging.getLogger("test"))


def _schedule_text(game_line: str) -> str:
    """Wrap a single game line in the "Opponent Score" / "Season Totals" section markers parse_ahsfhs_schedule expects."""
    return f"Opponent Score {game_line} {SEASON} Season Totals"


def test_second_round_playoffs_maps_to_quarterfinals_for_5a_7a() -> None:
    """5A-7A brackets have no real Second Round, so round 2 is the Quarterfinals."""
    text = _schedule_text("Fri., Nov. 14 vs WEST JONES 21 14 W 2nd Round Playoffs")
    games = parse_ahsfhs_schedule(text, season=SEASON, school_name="Test School", url="http://x", clazz=6)
    assert len(games) == 1
    assert games[0].round == "Quarterfinals"


def test_second_round_playoffs_maps_to_second_round_for_1a_4a() -> None:
    """1A-4A brackets have a real Second Round as round 2."""
    text = _schedule_text("Fri., Nov. 14 vs WEST JONES 21 14 W 2nd Round Playoffs")
    games = parse_ahsfhs_schedule(text, season=SEASON, school_name="Test School", url="http://x", clazz=2)
    assert len(games) == 1
    assert games[0].round == "Second Round"


def test_first_round_playoffs_maps_to_first_round_for_both_groups() -> None:
    """The 1st-round mapping to "First Round" is unconditional across classifications."""
    text = _schedule_text("Fri., Nov. 7 vs WEST JONES 21 14 W 1st Round Playoffs")
    for clazz in (2, 6):
        games = parse_ahsfhs_schedule(text, season=SEASON, school_name="Test School", url="http://x", clazz=clazz)
        assert games[0].round == "First Round"


def test_third_round_playoffs_maps_to_quarterfinals_for_1a_4a() -> None:
    """Only 1A-4A brackets literally reach "3rd Round Playoffs" text (their round 3)."""
    text = _schedule_text("Fri., Nov. 21 vs WEST JONES 21 14 W 3rd Round Playoffs")
    games = parse_ahsfhs_schedule(text, season=SEASON, school_name="Test School", url="http://x", clazz=2)
    assert games[0].round == "Quarterfinals"


def test_semifinals_playoffs_maps_to_semifinals_for_both_groups() -> None:
    """The semifinals mapping to "Semifinals" is unconditional across classifications."""
    text = _schedule_text("Fri., Nov. 28 vs WEST JONES 21 14 W Semi-finals Playoffs")
    for clazz in (2, 6):
        games = parse_ahsfhs_schedule(text, season=SEASON, school_name="Test School", url="http://x", clazz=clazz)
        assert games[0].round == "Semifinals"


# ---------------------------------------------------------------------------
# remove_unlisted_games: rows a school's AHSFHS page no longer lists
# ---------------------------------------------------------------------------


def _mock_db(monkeypatch: pytest.MonkeyPatch, deleted: list, kept: list):
    """Point the pipeline at a mocked connection; return its cursor."""
    from unittest.mock import MagicMock

    cur = MagicMock()
    cur.fetchall.side_effect = [deleted, kept]
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    monkeypatch.setattr(
        pipeline,
        "get_database_connection",
        MagicMock(return_value=MagicMock(__enter__=lambda s: conn, __exit__=lambda *a: None)),
    )
    return cur, conn


def _game(school: str, iso: str):
    """A scraped game stand-in: only school and date matter here."""
    from datetime import date as _date
    from types import SimpleNamespace

    return SimpleNamespace(school=school, date=_date.fromisoformat(iso))


def test_unlisted_games_are_removed_per_scraped_school(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each scraped school's listed dates are sent once, and deleted rows are counted."""
    import json
    from datetime import date as _date

    cur, conn = _mock_db(monkeypatch, deleted=[("Alpha", _date(2026, 8, 21), "Echo")], kept=[])
    games = [_game("Alpha", "2026-09-04"), _game("Alpha", "2026-08-28"), _game("Bravo", "2026-08-28")]

    assert pipeline.remove_unlisted_games.fn(games, 2026) == 1

    delete_sql, (listed, season) = cur.execute.call_args_list[0].args
    assert season == 2026
    assert json.loads(listed) == {"Alpha": ["2026-08-28", "2026-09-04"], "Bravo": ["2026-08-28"]}
    assert "DELETE FROM games" in delete_sql
    # Finished games and hand-corrected rows are never deleted.
    assert "g.final IS NOT TRUE" in delete_sql
    assert "g.overrides = '{}'::jsonb" in delete_sql
    conn.commit.assert_called_once()


def test_kept_unlisted_games_are_reported(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """Unlisted games that are protected (finished or overridden) are logged, not deleted."""
    from datetime import date as _date

    _mock_db(
        monkeypatch,
        deleted=[],
        kept=[
            ("Alpha", _date(2026, 9, 4), "Delta", True, False),
            ("Alpha", _date(2026, 9, 11), "Charlie", False, True),
        ],
    )
    with caplog.at_level(logging.WARNING):
        assert pipeline.remove_unlisted_games.fn([_game("Alpha", "2026-08-28")], 2026) == 0
    assert "kept because it's a finished game" in caplog.text
    assert "kept because it has manual overrides" in caplog.text


def test_nothing_scraped_touches_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no scraped games (every fetch failed, say), the database isn't touched."""
    cur, _ = _mock_db(monkeypatch, deleted=[], kept=[])
    assert pipeline.remove_unlisted_games.fn([], 2026) == 0
    cur.execute.assert_not_called()
