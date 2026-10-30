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
    text = _schedule_text("Fri., Nov. 14 vs. WEST JONES 21 14 W 2nd Round Playoffs")
    games = parse_ahsfhs_schedule(text, season=SEASON, school_name="Test School", url="http://x", clazz=6)
    assert len(games) == 1
    assert games[0].round == "Quarterfinals"


def test_second_round_playoffs_maps_to_second_round_for_1a_4a() -> None:
    """1A-4A brackets have a real Second Round as round 2."""
    text = _schedule_text("Fri., Nov. 14 vs. WEST JONES 21 14 W 2nd Round Playoffs")
    games = parse_ahsfhs_schedule(text, season=SEASON, school_name="Test School", url="http://x", clazz=2)
    assert len(games) == 1
    assert games[0].round == "Second Round"


def test_first_round_playoffs_maps_to_first_round_for_both_groups() -> None:
    """The 1st-round mapping to "First Round" is unconditional across classifications."""
    text = _schedule_text("Fri., Nov. 7 vs. WEST JONES 21 14 W 1st Round Playoffs")
    for clazz in (2, 6):
        games = parse_ahsfhs_schedule(text, season=SEASON, school_name="Test School", url="http://x", clazz=clazz)
        assert games[0].round == "First Round"


def test_third_round_playoffs_maps_to_quarterfinals_for_1a_4a() -> None:
    """Only 1A-4A brackets literally reach "3rd Round Playoffs" text (their round 3)."""
    text = _schedule_text("Fri., Nov. 21 vs. WEST JONES 21 14 W 3rd Round Playoffs")
    games = parse_ahsfhs_schedule(text, season=SEASON, school_name="Test School", url="http://x", clazz=2)
    assert games[0].round == "Quarterfinals"


def test_semifinals_playoffs_maps_to_semifinals_for_both_groups() -> None:
    """The semifinals mapping to "Semifinals" is unconditional across classifications."""
    text = _schedule_text("Fri., Nov. 28 vs. WEST JONES 21 14 W Semi-finals Playoffs")
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


# ---------------------------------------------------------------------------
# insert_rows: a moved game keeps its corrections; AHSFHS changes under one are reported
# ---------------------------------------------------------------------------


def _scraped(school: str, iso: str):
    """A scraped game stand-in with the one method insert_rows calls."""
    from types import SimpleNamespace

    return SimpleNamespace(school=school, season=2026, as_db_tuple=lambda: (school, iso))


def _insert_db(
    monkeypatch: pytest.MonkeyPatch, moved: list, removed: list, kept: list, changed: list, season_rows: list = ()
):
    """A mocked connection answering insert_rows' five reads in order (the last is the season's rows
    for reconcile_game_ids); return its cursor."""
    cur, conn = _mock_db(monkeypatch, deleted=[], kept=[])
    cur.fetchall.side_effect = [moved, removed, kept, changed, list(season_rows)]
    monkeypatch.setattr(pipeline, "execute_values", lambda *a, **k: None)
    return cur, conn


def test_insert_moves_a_game_before_pruning_and_upserting(monkeypatch: pytest.MonkeyPatch) -> None:
    """The move runs before anything near the new date is removed, so the moved row (with its
    corrections, helmet and attendance) is the one updated, all in one transaction."""
    from datetime import date as _date

    cur, conn = _insert_db(
        monkeypatch,
        moved=[("Alpha", _date(2026, 10, 23), _date(2026, 10, 24), "Beta")],
        removed=[],
        kept=[],
        changed=[],
    )
    assert pipeline.insert_rows.fn([_scraped("Alpha", "2026-10-24")]) == 1

    statements = [c.args[0] for c in cur.execute.call_args_list]
    move = statements.index("UPDATE games SET date = %s WHERE school = %s AND date = %s")
    assert cur.execute.call_args_list[move].args[1] == (_date(2026, 10, 24), "Alpha", _date(2026, 10, 23))
    assert statements.index(pipeline._MOVED_GAMES_SQL) < move < statements.index(pipeline._STALE_NEARBY_SQL)
    assert statements.index(pipeline._CHANGED_UNDER_CORRECTION_SQL) < statements.index(pipeline._UPSERT_SQL)
    conn.commit.assert_called_once()


def test_insert_gives_a_new_row_its_opponents_game_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """After the upsert, the season's rows are re-paired: Beta's new row joins Alpha's game, and a
    submission that named Beta's row by its old id follows it."""
    from datetime import date as _date

    d = _date(2026, 10, 23)
    cur, conn = _insert_db(
        monkeypatch,
        moved=[],
        removed=[],
        kept=[],
        changed=[],
        season_rows=[("Alpha", d, "Beta", 5), ("Beta", d, "Alpha", 9)],
    )
    pipeline.insert_rows.fn([_scraped("Beta", "2026-10-23")])

    calls = [(c.args[0], c.args[1] if len(c.args) > 1 else None) for c in cur.execute.call_args_list]
    upsert = [sql for sql, _ in calls].index(pipeline._UPSERT_SQL)
    assert (pipeline._SET_GAME_ID_SQL, (5, "Beta", d)) in calls[upsert:]
    assert (pipeline._REMAP_SUBMISSIONS_SQL, (5, "Beta", 9)) in calls[upsert:]
    conn.commit.assert_called_once()


def test_insert_never_removes_a_finished_or_corrected_row() -> None:
    assert "g.final IS NOT TRUE" in pipeline._STALE_NEARBY_SQL
    assert "g.overrides = '{}'::jsonb" in pipeline._STALE_NEARBY_SQL
    assert "DELETE" not in pipeline._UPSERT_SQL
    assert "overrides" not in pipeline._UPSERT_SQL.split("ON CONFLICT")[0]


def test_insert_stores_ahsfhs_scores_so_a_later_change_shows() -> None:
    """The score fields take AHSFHS's value even when corrected (games_effective reads the correction first)."""
    for field in pipeline._SCORE_FIELDS:
        line = next(x for x in pipeline._UPSERT_SQL.splitlines() if x.strip().startswith(field))
        assert "overrides" not in line, line


def test_insert_reports_score_changes_under_a_correction(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from datetime import date as _date

    _insert_db(
        monkeypatch,
        moved=[],
        removed=[],
        kept=[("Alpha", _date(2026, 10, 23), "Beta", True)],
        changed=[
            ("Alpha", _date(2026, 10, 24), "Beta", "points_for", "14", "17", "21"),
            ("Alpha", _date(2026, 10, 24), "Beta", "result", "L", "W", "W"),
        ],
    )
    with caplog.at_level(logging.INFO):
        pipeline.insert_rows.fn([_scraped("Alpha", "2026-10-24")])
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("points_for 14 -> 17, which still differs from the approved correction (21)" in m for m in warnings)
    assert any("kept because it has manual overrides" in m for m in warnings)
    # AHSFHS catching up with a reported score is routine: logged, not a warning.
    assert not any("result" in m and "agrees" in m for m in warnings)
    assert "AHSFHS now agrees with the approved correction to Alpha's 2026-10-24 game vs Beta: result W" in caplog.text


def test_attended_games_follow_a_moved_game() -> None:
    """Moving a game's row fails unless the attendance rows' foreign key cascades the new date."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    fk = "FOREIGN KEY (school, date) REFERENCES games(school, date) ON UPDATE CASCADE ON DELETE CASCADE"
    assert fk in (root / "sql/init.sql").read_text()
    assert fk in (root / "sql/migrations/2026_10_attended_games_follow_moves.sql").read_text()


# ---------------------------------------------------------------- results, overtime, sites
# How a game line on an AHSFHS schedule becomes a game row: these decide the scores, the
# overtime count, forfeits, home/away and region games everything downstream reads.


def _one(game_line: str, clazz: int = 3):
    """The single game parsed from *game_line*."""
    [game] = parse_ahsfhs_schedule(
        _schedule_text(game_line), season=SEASON, school_name="Test School", url="http://x", clazz=clazz
    )
    return game


def test_a_played_game_keeps_its_score_result_and_site() -> None:
    """Home ("vs."), the score from the school's side, W/L, final, no overtime."""
    game = _one("Fri., Oct. 3 vs. WEST JONES 21 14 W")
    assert (game.points_for, game.points_against, game.result) == (21, 14, "W")
    assert (game.location, game.final, game.game_status, game.overtime) == ("home", True, "final", 0)
    away = _one("Fri., Oct. 10 @ WEST JONES 7 28 L")
    assert (away.location, away.result, away.points_for, away.points_against) == ("away", "L", 7, 28)


def test_a_game_with_no_site_marker_is_at_a_neutral_site() -> None:
    """Neither "vs." nor "@": the game is at a neutral site."""
    assert _one("Sat., Nov. 29 WEST JONES 35 21 W Championship Game").location == "neutral"


def test_overtime_counts_its_periods() -> None:
    """ "(OT)" is one overtime; "(3OT)" is three."""
    assert _one("Fri., Oct. 3 vs. WEST JONES 28 21 W (OT)").overtime == 1
    assert _one("Fri., Oct. 3 vs. WEST JONES 28 27 L (3OT)").overtime == 3


def test_a_forfeit_is_final_with_its_result_and_status() -> None:
    """ "#Won" and "#Lost" are forfeits: final, the result kept, marked as a forfeit."""
    won = _one("Fri., Oct. 3 vs. WEST JONES 1 0 #Won")
    assert (won.result, won.game_status, won.final) == ("W", "final_forfeit", True)
    lost = _one("Fri., Oct. 3 @ WEST JONES 0 1 #Lost")
    assert (lost.result, lost.game_status, lost.final) == ("L", "final_forfeit", True)


def test_a_game_not_yet_played_has_no_score_or_result() -> None:
    """No score on the line: not final, no result, no points."""
    game = _one("Fri., Oct. 31 vs. WEST JONES")
    assert (game.points_for, game.points_against, game.result) == (None, None, None)
    assert (game.final, game.overtime) == (False, 0) and not game.game_status


def test_a_star_marks_a_region_game() -> None:
    """AHSFHS stars region games, before or after the score."""
    assert _one("Fri., Oct. 3 vs. WEST JONES* 21 14 W").region_game is True
    assert _one("Fri., Oct. 3 vs. WEST JONES 21 14 W").region_game is False


def test_open_weeks_are_skipped() -> None:
    """An OPEN week isn't a game."""
    text = _schedule_text("Fri., Sep. 26 OPEN Fri., Oct. 3 vs. WEST JONES 21 14 W")
    games = parse_ahsfhs_schedule(text, season=SEASON, school_name="Test School", url="http://x", clazz=3)
    assert [g.points_for for g in games] == [21]


def test_a_whole_schedule_parses_game_by_game() -> None:
    """Several games on one page, in order, each with its own date and result."""
    text = _schedule_text(
        "Fri., Aug. 29 vs. WEST JONES 21 14 W Fri., Sep. 5 @ LAUREL 10 17 L Fri., Sep. 12 vs. MAGEE* 35 0 W"
    )
    games = parse_ahsfhs_schedule(text, season=SEASON, school_name="Test School", url="http://x", clazz=3)
    assert [(g.date.isoformat(), g.result, g.location, g.region_game) for g in games] == [
        (f"{SEASON}-08-29", "W", "home", False),
        (f"{SEASON}-09-05", "L", "away", False),
        (f"{SEASON}-09-12", "W", "home", True),
    ]
