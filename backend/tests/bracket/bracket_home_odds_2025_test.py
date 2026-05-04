"""Ground-truth tests: 2025 playoff bracket → correct deterministic home team.

For each actual 2025 MHSAA playoff game at each round, verifies that the
deterministic home-team rule functions (``r2_home_team``, ``qf_home_team``,
``sf_home_team``) return the correct home team given the actual bracket path.

How it works
------------
Each team's pre-round home-game history is derived from data already in
``PLAYOFF_BRACKETS_2025``:

* Round-1 home/away is deterministic from the ``FormatSlot`` list.
* Round-2 home/away (1A-4A only) is taken directly from the ``second_round``
  entries.

The deterministic functions then apply the MHSAA rules with certainty:
golden rule for same-region pairs, home-games-played → seed → region
tiebreak for cross-region QF, seed → region tiebreak for SF.

Tests are parametrized from ``PLAYOFF_BRACKETS_2025``; rounds with empty
game lists are automatically skipped (data not yet provided).
"""

import pytest

from backend.helpers.bracket_home_odds import qf_home_team, r2_home_team, sf_home_team
from backend.helpers.data_classes import FormatSlot
from backend.tests.data.playoff_brackets_2025 import (
    PLAYOFF_BRACKETS_2025,
    SLOTS_1A_4A_2025,
    SLOTS_5A_7A_2025,
)

SEASON = 2025


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slots(clazz: int) -> list[FormatSlot]:
    """Return the correct FormatSlot list for the given class."""
    return SLOTS_5A_7A_2025 if clazz >= 5 else SLOTS_1A_4A_2025


def _r1_home(region: int, seed: int, slots: list[FormatSlot]) -> bool:
    """Return True if (region, seed) occupies the home position in their R1 slot."""
    for s in slots:
        if s.home_region == region and s.home_seed == seed:
            return True
        if s.away_region == region and s.away_seed == seed:
            return False
    raise ValueError(f"No R1 slot found for region={region}, seed={seed}")


def _r2_home(region: int, seed: int, second_round: list[tuple[int, int, int, int]]) -> bool:
    """Return True if (region, seed) was the home team in their R2 game."""
    for hr, hs, ar, as_ in second_round:
        if hr == region and hs == seed:
            return True
        if ar == region and as_ == seed:
            return False
    raise ValueError(f"No R2 game found for region={region}, seed={seed}")


# ---------------------------------------------------------------------------
# Parametrize
# ---------------------------------------------------------------------------

_R2_PARAMS: list = []
_QF_PARAMS: list = []
_SF_PARAMS: list = []

for _clazz, _bracket in sorted(PLAYOFF_BRACKETS_2025.items()):
    for _hr, _hs, _ar, _as in _bracket.get("second_round", []):
        _R2_PARAMS.append(
            pytest.param(
                _clazz,
                _hr,
                _hs,
                _ar,
                _as,
                id=f"{_clazz}A_r2_R{_hr}s{_hs}_v_R{_ar}s{_as}",
            )
        )
    for _hr, _hs, _ar, _as in _bracket.get("quarterfinals", []):
        _QF_PARAMS.append(
            pytest.param(
                _clazz,
                _hr,
                _hs,
                _ar,
                _as,
                id=f"{_clazz}A_qf_R{_hr}s{_hs}_v_R{_ar}s{_as}",
            )
        )
    for _hr, _hs, _ar, _as in _bracket.get("semifinals", []):
        _SF_PARAMS.append(
            pytest.param(
                _clazz,
                _hr,
                _hs,
                _ar,
                _as,
                id=f"{_clazz}A_sf_R{_hr}s{_hs}_v_R{_ar}s{_as}",
            )
        )

_SKIP = pytest.mark.skip(reason="No bracket data provided yet")

if not _R2_PARAMS:
    _R2_PARAMS = [pytest.param(None, None, None, None, None, id="no_data_yet", marks=_SKIP)]
if not _QF_PARAMS:
    _QF_PARAMS = [pytest.param(None, None, None, None, None, id="no_data_yet", marks=_SKIP)]
if not _SF_PARAMS:
    _SF_PARAMS = [pytest.param(None, None, None, None, None, id="no_data_yet", marks=_SKIP)]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clazz,home_region,home_seed,away_region,away_seed", _R2_PARAMS)
def test_r2_home_team_2025(clazz, home_region, home_seed, away_region, away_seed):
    """r2_home_team must return the actual 2025 R2 home team for every game."""
    result = r2_home_team(home_region, home_seed, away_region, away_seed, season=2025)
    assert result == (home_region, home_seed), (
        f"{clazz}A R2: expected R{home_region}s{home_seed} to host R{away_region}s{away_seed}, "
        f"but got R{result[0]}s{result[1]}"
    )


@pytest.mark.parametrize("clazz,home_region,home_seed,away_region,away_seed", _QF_PARAMS)
def test_qf_home_team_2025(clazz, home_region, home_seed, away_region, away_seed):
    """qf_home_team must return the actual 2025 QF home team for every game."""
    slots = _slots(clazz)
    second_round = PLAYOFF_BRACKETS_2025[clazz].get("second_round", [])

    r1h1 = _r1_home(home_region, home_seed, slots)
    r1h2 = _r1_home(away_region, away_seed, slots)
    r2h1 = _r2_home(home_region, home_seed, second_round) if second_round else False
    r2h2 = _r2_home(away_region, away_seed, second_round) if second_round else False

    result = qf_home_team(
        home_region,
        home_seed,
        r1h1,
        r2h1,
        away_region,
        away_seed,
        r1h2,
        r2h2,
        SEASON,
    )
    assert result == (home_region, home_seed), (
        f"{clazz}A QF: expected R{home_region}s{home_seed} "
        f"(R1_home={r1h1}, R2_home={r2h1}, total={r1h1 + r2h1}) to host "
        f"R{away_region}s{away_seed} "
        f"(R1_home={r1h2}, R2_home={r2h2}, total={r1h2 + r2h2}), "
        f"but got R{result[0]}s{result[1]}"
    )


@pytest.mark.parametrize("clazz,home_region,home_seed,away_region,away_seed", _SF_PARAMS)
def test_sf_home_team_2025(clazz, home_region, home_seed, away_region, away_seed):
    """sf_home_team must return the actual 2025 SF home team for every game."""
    result = sf_home_team(home_region, home_seed, away_region, away_seed, SEASON)
    assert result == (home_region, home_seed), (
        f"{clazz}A SF: expected R{home_region}s{home_seed} to host R{away_region}s{away_seed}, "
        f"but got R{result[0]}s{result[1]}"
    )
