"""Unit tests for resolve_with_results using Region 3-7A (2025 season) data.

Covers: correct seeding, no-message cases, margin-warning cases, specific margin cases, and error handling.
"""

import pytest

from backend.helpers.tiebreakers import resolve_with_results
from backend.tests.data.standings_2025_3_7a import (
    expected_3_7a_completed_games,
    expected_3_7a_remaining_games,
    teams_3_7a,
)

# Fixtures shared across tests
COMPLETED = expected_3_7a_completed_games
REMAINING = expected_3_7a_remaining_games
TEAMS = teams_3_7a

# Convenience shorthands for game result dicts
_BRANDON_WINS = ("Brandon", "Meridian"), "Brandon"
_OG_WINS = ("Oak Grove", "Pearl"), "Oak Grove"
_PEARL_WINS = ("Oak Grove", "Pearl"), "Pearl"
_NWR_WINS = ("Northwest Rankin", "Petal"), "Northwest Rankin"
_PETAL_WINS = ("Northwest Rankin", "Petal"), "Petal"


def _results(*pairs):
    """Build a game-results dict from (key, value) pairs for use in test fixtures."""
    return dict(pairs)


# ---------------------------------------------------------------------------
# Actual 2025 outcome (Brandon W, OG W, NWR W) — ground truth: OG 1, Petal 2,
# Brandon 3, Northwest Rankin 4
# ---------------------------------------------------------------------------


def test_actual_2025_with_margins():
    """Actual final-week results + real margins produce the correct 2025 seeds."""
    results = _results(_BRANDON_WINS, _OG_WINS, _NWR_WINS)
    margins = {("Northwest Rankin", "Petal"): 6, ("Oak Grove", "Pearl"): 21}

    seeding, messages = resolve_with_results(TEAMS, COMPLETED, REMAINING, results, margins)

    assert seeding == ["Oak Grove", "Petal", "Brandon", "Northwest Rankin", "Pearl", "Meridian"]
    assert messages == []


def test_actual_2025_without_margins():
    """Actual final-week results without margins still resolves correctly (margin irrelevant here)."""
    results = _results(_BRANDON_WINS, _OG_WINS, _NWR_WINS)

    seeding, messages = resolve_with_results(TEAMS, COMPLETED, REMAINING, results)

    assert seeding == ["Oak Grove", "Petal", "Brandon", "Northwest Rankin", "Pearl", "Meridian"]
    assert messages == []


# ---------------------------------------------------------------------------
# Alternate: Petal wins NWR (mask=3: Brandon W, OG W, Petal W)
# No intra-bucket remaining game — OG & Petal are in the same 4-1 bucket but
# played each other in a completed game, not a remaining one.
# ---------------------------------------------------------------------------


def test_petal_wins_nwr_no_margin_sensitivity():
    """Brandon W, OG W, Petal W → Petal 1st over OG, clean 3-way tail, no margin messages."""
    results = _results(_BRANDON_WINS, _OG_WINS, _PETAL_WINS)

    seeding, messages = resolve_with_results(TEAMS, COMPLETED, REMAINING, results)

    assert seeding == ["Petal", "Oak Grove", "Brandon", "Northwest Rankin", "Pearl", "Meridian"]
    assert messages == []


# ---------------------------------------------------------------------------
# Alternate: 5-way tie (mask=5: Brandon W, Pearl W OG, NWR W Petal)
# Both OG-Pearl and NWR-Petal margins affect the Step-3 H2H PD tiebreaker.
# ---------------------------------------------------------------------------


def test_five_way_tie_no_margins_warns_about_both_games():
    """Five-way tie scenario without margins → two margin-needed messages, one per margin-sensitive game."""
    results = _results(_BRANDON_WINS, _PEARL_WINS, _NWR_WINS)

    _seeding, messages = resolve_with_results(TEAMS, COMPLETED, REMAINING, results)

    # Seeding is computed with default margins (7); two margin-sensitive games remain
    assert len(messages) == 2
    pearl_og_msg = next((m for m in messages if "Pearl" in m and "Oak Grove" in m), None)
    nwr_petal_msg = next((m for m in messages if "Northwest Rankin" in m and "Petal" in m), None)
    assert pearl_og_msg is not None, "Expected a message about Pearl over Oak Grove margin"
    assert nwr_petal_msg is not None, "Expected a message about Northwest Rankin over Petal margin"
    # Each message names the affected teams
    assert "margin affects seeding of" in pearl_og_msg
    assert "margin affects seeding of" in nwr_petal_msg


def test_five_way_tie_with_margins_resolves_cleanly():
    """Five-way tie with both margins provided → specific seeding, no messages."""
    results = _results(_BRANDON_WINS, _PEARL_WINS, _NWR_WINS)
    margins = {("Oak Grove", "Pearl"): 10, ("Northwest Rankin", "Petal"): 7}

    seeding, messages = resolve_with_results(TEAMS, COMPLETED, REMAINING, results, margins)

    assert seeding == ["Pearl", "Northwest Rankin", "Petal", "Oak Grove", "Brandon", "Meridian"]
    assert messages == []


def test_five_way_tie_partial_margins_warns_about_missing_game():
    """Five-way tie with only one margin provided → message only for the missing game."""
    results = _results(_BRANDON_WINS, _PEARL_WINS, _NWR_WINS)
    # Provide only the NWR-Petal margin; OG-Pearl margin is still missing
    margins = {("Northwest Rankin", "Petal"): 7}

    _, messages = resolve_with_results(TEAMS, COMPLETED, REMAINING, results, margins)

    assert len(messages) == 1
    assert "Pearl" in messages[0] and "Oak Grove" in messages[0]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_missing_result_raises():
    """Omitting a result for any remaining game raises ValueError."""
    results = _results(_BRANDON_WINS, _OG_WINS)  # missing NWR vs Petal

    with pytest.raises(ValueError, match="Northwest Rankin"):
        resolve_with_results(TEAMS, COMPLETED, REMAINING, results)


def test_invalid_winner_raises():
    """Providing a winner name that is not a participant in the game raises ValueError."""
    results = _results(_BRANDON_WINS, _OG_WINS, (("Northwest Rankin", "Petal"), "Brandon"))

    with pytest.raises(ValueError, match="Brandon"):
        resolve_with_results(TEAMS, COMPLETED, REMAINING, results)
