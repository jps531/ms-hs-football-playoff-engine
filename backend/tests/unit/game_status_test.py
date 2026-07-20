"""Tests for game status parsing utilities in data_helpers.py."""

import pytest

from backend.helpers.data_classes import GameStatus
from backend.helpers.data_helpers import (
    game_seconds_remaining,
    normalize_game_status,
    parse_game_clock,
)

# ---------------------------------------------------------------------------
# normalize_game_status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, GameStatus.NOT_STARTED),  # no status yet
        ("", GameStatus.NOT_STARTED),  # empty string
        ("Final", GameStatus.FINAL),
        ("Final - Forfeit", GameStatus.FINAL_FORFEIT),
        ("End 1Q", GameStatus.END_1Q),
        ("Halftime", GameStatus.HALFTIME),
        ("End 3Q", GameStatus.END_3Q),
        ("End 4Q", GameStatus.END_4Q),
        ("Postponed", GameStatus.POSTPONED),
        ("Canceled", GameStatus.CANCELED),
        ("Cancelled", GameStatus.CANCELED),  # alternate (double-l) spelling
        ("Suspended", GameStatus.SUSPENDED),
        ("8:00 1Q", GameStatus.IN_PROGRESS),  # regulation clock, Q1
        ("0:24 4Q", GameStatus.IN_PROGRESS),  # regulation clock, Q4
        ("OT", GameStatus.IN_PROGRESS),  # bare OT (no number)
        ("1OT", GameStatus.IN_PROGRESS),
        ("2OT", GameStatus.IN_PROGRESS),
        ("3OT", GameStatus.IN_PROGRESS),
        ("End OT", GameStatus.END_OT),  # bare OT (no number)
        ("End 1OT", GameStatus.END_OT),
        ("End 2OT", GameStatus.END_OT),
        ("Unknown Status", GameStatus.NOT_STARTED),  # unrecognized string falls back
    ],
)
def test_normalize_game_status(raw, expected):
    """normalize_game_status maps raw scraper strings to canonical GameStatus values."""
    assert normalize_game_status(raw) == expected


# ---------------------------------------------------------------------------
# parse_game_clock
# ---------------------------------------------------------------------------


class TestParseGameClock:
    """parse_game_clock builds a GameClock from a raw status string."""

    def test_reg_clock_q1(self):
        """Regulation clock in Q1 extracts quarter and clock correctly."""
        gc = parse_game_clock("8:00 1Q")
        assert gc.status == GameStatus.IN_PROGRESS
        assert gc.quarter == 1
        assert gc.clock == "8:00"

    def test_reg_clock_q4_sub_minute(self):
        """Sub-minute regulation clock in Q4 parses correctly."""
        gc = parse_game_clock("0:24 4Q")
        assert gc.status == GameStatus.IN_PROGRESS
        assert gc.quarter == 4
        assert gc.clock == "0:24"

    def test_reg_clock_q2(self):
        """Regulation clock in Q2 sets quarter=2."""
        gc = parse_game_clock("8:00 2Q")
        assert gc.quarter == 2

    def test_ot_bare_maps_to_quarter_5(self):
        """'OT' (first OT) maps to quarter=5 with no clock."""
        gc = parse_game_clock("OT")
        assert gc.status == GameStatus.IN_PROGRESS
        assert gc.quarter == 5
        assert gc.clock is None

    def test_ot_numbered_1_maps_to_quarter_5(self):
        """'1OT' maps to quarter=5."""
        gc = parse_game_clock("1OT")
        assert gc.quarter == 5

    def test_ot_numbered_2_maps_to_quarter_6(self):
        """'2OT' maps to quarter=6."""
        gc = parse_game_clock("2OT")
        assert gc.quarter == 6

    def test_end_ot_numbered_1(self):
        """'End 1OT' produces END_OT status with quarter=5."""
        gc = parse_game_clock("End 1OT")
        assert gc.status == GameStatus.END_OT
        assert gc.quarter == 5
        assert gc.clock is None

    def test_end_ot_numbered_2(self):
        """'End 2OT' produces END_OT status with quarter=6."""
        gc = parse_game_clock("End 2OT")
        assert gc.status == GameStatus.END_OT
        assert gc.quarter == 6

    def test_terminal_state_no_quarter(self):
        """Terminal states have quarter=None and clock=None."""
        gc = parse_game_clock("Final")
        assert gc.status == GameStatus.FINAL
        assert gc.quarter is None
        assert gc.clock is None

    def test_halftime_no_quarter(self):
        """Halftime produces quarter=None (not in a live quarter)."""
        gc = parse_game_clock("Halftime")
        assert gc.quarter is None

    def test_none_returns_not_started(self):
        """None input produces NOT_STARTED with no quarter or clock."""
        gc = parse_game_clock(None)
        assert gc.status == GameStatus.NOT_STARTED
        assert gc.quarter is None


# ---------------------------------------------------------------------------
# game_seconds_remaining
# ---------------------------------------------------------------------------


class TestGameSecondsRemaining:
    """game_seconds_remaining converts (quarter, clock) to total regulation seconds left."""

    def test_start_of_game(self):
        """Q1 with full 12:00 → 4 full quarters = 2880 s."""
        assert game_seconds_remaining(1, "12:00") == 2880

    def test_start_of_second_half(self):
        """Q3 with 12:00 → 2 full quarters = 1440 s."""
        assert game_seconds_remaining(3, "12:00") == 1440

    def test_final_seconds_q4(self):
        """0:24 left in Q4 → 24 s."""
        assert game_seconds_remaining(4, "0:24") == 24

    def test_mid_q2(self):
        """8:00 left in Q2 → 480 s this quarter + 2 more quarters (1440) = 1920."""
        assert game_seconds_remaining(2, "8:00") == 1920

    def test_end_of_q1(self):
        """0:00 Q1 → 0 remaining in Q1 + 3 full quarters = 2160."""
        assert game_seconds_remaining(1, "0:00") == 2160

    def test_ot_returns_zero(self):
        """OT is untimed — function returns 0 for quarter > 4."""
        assert game_seconds_remaining(5, "0:00") == 0
