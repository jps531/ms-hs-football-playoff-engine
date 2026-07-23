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
