"""Tests for game status parsing utilities in data_helpers.py."""

from backend.helpers.data_classes import GameStatus
from backend.helpers.data_helpers import (
    game_seconds_remaining,
    normalize_game_status,
    parse_game_clock,
)

# ---------------------------------------------------------------------------
# normalize_game_status
# ---------------------------------------------------------------------------


class TestNormalizeGameStatus:
    """normalize_game_status maps raw scraper strings to canonical GameStatus values."""

    def test_none_returns_not_started(self):
        """None input maps to NOT_STARTED."""
        assert normalize_game_status(None) == GameStatus.NOT_STARTED

    def test_empty_string_returns_not_started(self):
        """Empty string maps to NOT_STARTED."""
        assert normalize_game_status("") == GameStatus.NOT_STARTED

    def test_final(self):
        """'Final' maps to FINAL."""
        assert normalize_game_status("Final") == GameStatus.FINAL

    def test_final_forfeit(self):
        """'Final - Forfeit' maps to FINAL_FORFEIT."""
        assert normalize_game_status("Final - Forfeit") == GameStatus.FINAL_FORFEIT

    def test_end_1q(self):
        """'End 1Q' maps to END_1Q."""
        assert normalize_game_status("End 1Q") == GameStatus.END_1Q

    def test_halftime(self):
        """'Halftime' maps to HALFTIME."""
        assert normalize_game_status("Halftime") == GameStatus.HALFTIME

    def test_end_3q(self):
        """'End 3Q' maps to END_3Q."""
        assert normalize_game_status("End 3Q") == GameStatus.END_3Q

    def test_end_4q(self):
        """'End 4Q' maps to END_4Q."""
        assert normalize_game_status("End 4Q") == GameStatus.END_4Q

    def test_postponed(self):
        """'Postponed' maps to POSTPONED."""
        assert normalize_game_status("Postponed") == GameStatus.POSTPONED

    def test_canceled(self):
        """'Canceled' maps to CANCELED."""
        assert normalize_game_status("Canceled") == GameStatus.CANCELED

    def test_cancelled_alternate_spelling(self):
        """'Cancelled' (double-l) also maps to CANCELED."""
        assert normalize_game_status("Cancelled") == GameStatus.CANCELED

    def test_suspended(self):
        """'Suspended' maps to SUSPENDED."""
        assert normalize_game_status("Suspended") == GameStatus.SUSPENDED

    def test_reg_clock_q1(self):
        """Regulation clock string in Q1 maps to IN_PROGRESS."""
        assert normalize_game_status("8:00 1Q") == GameStatus.IN_PROGRESS

    def test_reg_clock_q4(self):
        """Regulation clock string in Q4 maps to IN_PROGRESS."""
        assert normalize_game_status("0:24 4Q") == GameStatus.IN_PROGRESS

    def test_ot_bare(self):
        """'OT' (no number) maps to IN_PROGRESS."""
        assert normalize_game_status("OT") == GameStatus.IN_PROGRESS

    def test_ot_numbered_1(self):
        """'1OT' maps to IN_PROGRESS."""
        assert normalize_game_status("1OT") == GameStatus.IN_PROGRESS

    def test_ot_numbered_2(self):
        """'2OT' maps to IN_PROGRESS."""
        assert normalize_game_status("2OT") == GameStatus.IN_PROGRESS

    def test_ot_numbered_3(self):
        """'3OT' maps to IN_PROGRESS."""
        assert normalize_game_status("3OT") == GameStatus.IN_PROGRESS

    def test_end_ot_bare(self):
        """'End OT' maps to END_OT."""
        assert normalize_game_status("End OT") == GameStatus.END_OT

    def test_end_ot_numbered_1(self):
        """'End 1OT' maps to END_OT."""
        assert normalize_game_status("End 1OT") == GameStatus.END_OT

    def test_end_ot_numbered_2(self):
        """'End 2OT' maps to END_OT."""
        assert normalize_game_status("End 2OT") == GameStatus.END_OT

    def test_unrecognized_string_returns_not_started(self):
        """An unrecognized string falls back to NOT_STARTED."""
        assert normalize_game_status("Unknown Status") == GameStatus.NOT_STARTED


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
