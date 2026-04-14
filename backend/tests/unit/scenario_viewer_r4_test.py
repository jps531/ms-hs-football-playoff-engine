"""Scenario-viewer tests for Region 3-7A with 4 remaining games (R=4).

Extends the existing 3-7A R=3 fixture one week earlier by adding the Oak
Grove vs Northwest Rankin game (2025-10-31) as a remaining game alongside
all three final-week (2025-11-07) games.  The other two 2025-10-31 games
(Petal-Meridian and Brandon-Pearl) are treated as completed.

Remaining games (4):
  bit 0: Northwest Rankin vs Oak Grove   (2025-10-31, OG won 37–34)
  bit 1: Brandon vs Meridian             (2025-11-07, Brandon won 40–13)
  bit 2: Oak Grove vs Pearl              (2025-11-07, OG won 28–7)
  bit 3: Northwest Rankin vs Petal       (2025-11-07, NWR won 34–28)

Completed games (11):
  All 9 games through 2025-10-24, plus:
    Brandon 17, Pearl 10    (2025-10-31)
    Petal 42, Meridian 14   (2025-10-31)

Pre-remaining standings:
  Petal            3-1
  Oak Grove        2-1
  Northwest Rankin 2-1
  Brandon          2-2
  Pearl            2-2
  Meridian         0-4  (eliminated)

Purpose: exercises build_scenario_atoms and _simplify_atom_list with a
larger atom list (16 masks, 12^4 margin combos) than the R=3 fixture,
increasing the likelihood of triggering the outer stability-loop second
pass (scenario_viewer.py lines 892+) and the _try_rule4 structural
rejects (lines 859, 864).

Backward coverage (test_backward_coverage) iterates all
16 × 12^4 = 331,776 (mask, margins) combinations — roughly 24× the R=3
fixture — and verifies every outcome maps to a scenario seeding.
"""

from itertools import product

from backend.helpers.data_classes import GameResult, RemainingGame
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenario_viewer import build_scenario_atoms, enumerate_division_scenarios
from backend.helpers.tiebreakers import resolve_standings_for_mask
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025, expand_results, teams_from_games

_PA_WIN = 14
_BASE_MARGIN_DEFAULT = 7

_FIXTURE = REGION_RESULTS_2025[(7, 3)]
_ALL_GAMES = _FIXTURE["games"]
_TEAMS = teams_from_games(_ALL_GAMES)

# The 4 game pairs left as remaining, identified by team set rather than date
# so that the two other 2025-10-31 games are treated as completed.
_REMAINING_PAIRS = {
    frozenset(["Oak Grove", "Northwest Rankin"]),  # 2025-10-31
    frozenset(["Brandon", "Meridian"]),             # 2025-11-07
    frozenset(["Oak Grove", "Pearl"]),              # 2025-11-07
    frozenset(["Northwest Rankin", "Petal"]),       # 2025-11-07
}

_REMAINING = [
    RemainingGame(*sorted([g["winner"], g["loser"]]))
    for g in _ALL_GAMES
    if frozenset([g["winner"], g["loser"]]) in _REMAINING_PAIRS
]
_PAIRS = [(rg.a, rg.b) for rg in _REMAINING]

_COMPLETED = get_completed_games(expand_results([
    g for g in _ALL_GAMES
    if frozenset([g["winner"], g["loser"]]) not in _REMAINING_PAIRS
]))

# Module-level build — the heavy lifting that exercises _simplify_atom_list.
_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
_SCENARIOS = enumerate_division_scenarios(_TEAMS, _COMPLETED, _REMAINING, scenario_atoms=_ATOMS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_outcome_branches():
    """Yield (mask, margins) for all 16 × 12^4 = 331,776 combinations."""
    for mask in range(1 << len(_REMAINING)):
        for m0, m1, m2, m3 in product(range(1, 13), repeat=4):
            yield mask, {_PAIRS[0]: m0, _PAIRS[1]: m1, _PAIRS[2]: m2, _PAIRS[3]: m3}


# ---------------------------------------------------------------------------
# Fixture structure
# ---------------------------------------------------------------------------


def test_remaining_game_count():
    """Exactly 4 games remain."""
    assert len(_REMAINING) == 4


def test_completed_game_count():
    """Exactly 11 games are completed (15 total minus 4 remaining)."""
    assert len(_COMPLETED) == 11


def test_remaining_game_pairs():
    """All four expected matchups appear in _REMAINING."""
    pair_set = {frozenset([rg.a, rg.b]) for rg in _REMAINING}
    assert frozenset(["Northwest Rankin", "Oak Grove"]) in pair_set
    assert frozenset(["Brandon", "Meridian"]) in pair_set
    assert frozenset(["Oak Grove", "Pearl"]) in pair_set
    assert frozenset(["Northwest Rankin", "Petal"]) in pair_set


# ---------------------------------------------------------------------------
# Scenario structure
# ---------------------------------------------------------------------------


def test_scenario_count_exceeds_r3():
    """R=4 produces more distinct seeding scenarios than the R=3 fixture (17)."""
    assert len(_SCENARIOS) > 17


def test_all_scenarios_have_full_seedings():
    """Every scenario produces a complete seeding of all 6 teams."""
    for sc in _SCENARIOS:
        assert len(sc["seeding"]) == len(_TEAMS), (
            f"Scenario {sc['scenario_num']}{sc['sub_label']} has "
            f"{len(sc['seeding'])} teams, expected {len(_TEAMS)}"
        )


def test_margin_sensitive_scenarios_exist():
    """At least one mask produces margin-sensitive sub-scenarios (lettered labels)."""
    sub_scenarios = [sc for sc in _SCENARIOS if sc["sub_label"]]
    assert len(sub_scenarios) > 0


def test_meridian_always_eliminated():
    """Meridian is 0-4 at the cutoff and never places in the top 4."""
    for sc in _SCENARIOS:
        meridian_pos = sc["seeding"].index("Meridian") + 1  # 1-indexed
        assert meridian_pos >= 5, (
            f"Meridian unexpectedly at seed {meridian_pos} in "
            f"scenario {sc['scenario_num']}{sc['sub_label']}"
        )


# ---------------------------------------------------------------------------
# Atom quality
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """build_scenario_atoms returns an entry for every team in the region."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_contain_range_based_conditions():
    """build_scenario_atoms is not stuck in the old "sample-point" mode.

    The old regression was that every atom was built from a single (mask, margins)
    sample, producing only unit-width GameResults.  With R=4, exact-margin
    tiebreaker boundaries legitimately arise (H2H PD flips at a specific value),
    so some point-sample conditions are expected and correct.

    This test verifies the opposite of the regression: at least some atoms across
    the full atom set contain multi-margin or unbounded GameResults, confirming that
    the builder is using range enumeration rather than point sampling.
    """
    multi_margin_count = 0
    for team, seed_map in _ATOMS.items():
        for seed, atom_list in seed_map.items():
            for atom in atom_list:
                for cond in atom:
                    if isinstance(cond, GameResult):
                        if cond.max_margin is None or (cond.max_margin - cond.min_margin) > 1:
                            multi_margin_count += 1
    assert multi_margin_count > 0, "All GameResult conditions are point samples — old regression detected"


# ---------------------------------------------------------------------------
# Backward coverage (exhaustive)
# ---------------------------------------------------------------------------


def test_backward_coverage():
    """Every (mask, margins) combination maps to a seeding present in _SCENARIOS.

    Iterates all 16 masks × 12^4 = 331,776 margin combinations and verifies
    that resolve_standings_for_mask produces a seeding that matches some
    scenario.  This is the completeness guarantee: no outcome is unaccounted for.
    """
    seeding_map = {sc["seeding"]: sc for sc in _SCENARIOS}
    failures = []
    for mask, margins in _all_outcome_branches():
        order = resolve_standings_for_mask(
            _TEAMS,
            _COMPLETED,
            _REMAINING,
            mask,
            margins,
            _BASE_MARGIN_DEFAULT,
            _PA_WIN,
        )
        if tuple(order) not in seeding_map:
            failures.append(
                f"mask={mask:04b} margins={margins}: {tuple(order)} not in scenarios"
            )
    assert not failures, f"{len(failures)} uncovered:\n" + "\n".join(failures[:5])
