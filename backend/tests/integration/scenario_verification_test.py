"""Two-way verification of expected_3_7a_scenarios against resolve_standings_for_mask.

Uses the same forward/backward approach as scenario_verification_test.py but
validates the new GameResult / MarginCondition schema atoms instead of the
legacy GE-key dict atoms.

Forward check: for each atom, construct a concrete (outcome_mask, margins)
satisfying all conditions and assert the team lands at the claimed seed.

Backward check: enumerate all 8 × 12^3 = 13,824 outcome branches and assert
that each (team, seed) result is covered by at least one atom.
"""

import pytest

from backend.helpers.tiebreakers import rank_to_slots, resolve_standings_for_mask
from backend.tests.data.standings_2025_3_7a import (
    expected_3_7a_completed_games,
    expected_3_7a_remaining_games,
    expected_3_7a_scenarios,
    teams_3_7a,
)

_PA_WIN = 14
_BASE_MARGIN_DEFAULT = 7

_REMAINING = expected_3_7a_remaining_games


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _atom_satisfied(atom: list, outcome_mask: int, margins: dict) -> bool:
    """Return True if every condition in atom holds under (outcome_mask, margins)."""
    return all(cond.satisfied_by(outcome_mask, margins, _REMAINING) for cond in atom)


def _find_satisfying_scenario(atom: list) -> tuple[int, dict] | None:
    """Find a concrete (outcome_mask, margins) satisfying all atom conditions.

    Searches all 8 × 12^3 combinations; returns the first match.
    """
    games = _REMAINING
    pairs = [(rg.a, rg.b) for rg in games]
    for outcome_mask in range(1 << len(games)):
        for m0 in range(1, 13):
            for m1 in range(1, 13):
                for m2 in range(1, 13):
                    margins = {pairs[0]: m0, pairs[1]: m1, pairs[2]: m2}
                    if _atom_satisfied(atom, outcome_mask, margins):
                        return outcome_mask, margins
    return None


# ---------------------------------------------------------------------------
# Forward check
# ---------------------------------------------------------------------------


def _forward_cases():
    """Yield (team, seed, atom_index, atom) for every atom in the new schema."""
    for team, seed_map in expected_3_7a_scenarios.items():
        for seed, atoms in seed_map.items():
            for i, atom in enumerate(atoms):
                yield team, seed, i, atom


@pytest.mark.parametrize(
    "team,seed,atom_idx,atom",
    _forward_cases(),
    ids=lambda x: str(x)[:60],
)
def test_atom_forward_validity(team, seed, atom_idx, atom):
    """A concrete scenario satisfying this atom must give the team the claimed seed."""
    result = _find_satisfying_scenario(atom)
    assert result is not None, (
        f"{team} seed {seed} atom #{atom_idx}: no satisfying scenario found\n  conditions: {[str(c) for c in atom]}"
    )
    outcome_mask, margins = result

    final_order = resolve_standings_for_mask(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        outcome_mask,
        margins=margins,
        base_margin_default=_BASE_MARGIN_DEFAULT,
        pa_win=_PA_WIN,
    )
    lo, hi = rank_to_slots(final_order)[team]
    assert lo <= seed <= hi, (
        f"{team} expected seed {seed} but got slot ({lo},{hi})\n"
        f"  atom #{atom_idx}: {[str(c) for c in atom]}\n"
        f"  mask={outcome_mask}, margins={margins}\n"
        f"  order={final_order}"
    )


# ---------------------------------------------------------------------------
# Backward check
# ---------------------------------------------------------------------------


def _all_outcome_branches():
    """Yield (outcome_mask, margins) for all 8 × 12^3 combinations."""
    pairs = [(rg.a, rg.b) for rg in _REMAINING]
    for outcome_mask in range(1 << len(_REMAINING)):
        for m0 in range(1, 13):
            for m1 in range(1, 13):
                for m2 in range(1, 13):
                    yield outcome_mask, {pairs[0]: m0, pairs[1]: m1, pairs[2]: m2}


def test_backward_coverage():
    """Every enumerated outcome branch must be covered by at least one atom."""
    failures = []

    for outcome_mask, margins in _all_outcome_branches():
        final_order = resolve_standings_for_mask(
            teams_3_7a,
            expected_3_7a_completed_games,
            _REMAINING,
            outcome_mask,
            margins=margins,
            base_margin_default=_BASE_MARGIN_DEFAULT,
            pa_win=_PA_WIN,
        )
        slots = rank_to_slots(final_order)

        for team, (lo, hi) in slots.items():
            if team not in expected_3_7a_scenarios:
                continue
            seed = lo
            if seed not in expected_3_7a_scenarios[team]:
                seed = hi
                if seed not in expected_3_7a_scenarios[team]:
                    continue

            atoms = expected_3_7a_scenarios[team][seed]
            covered = any(_atom_satisfied(atom, outcome_mask, margins) for atom in atoms)
            if not covered:
                failures.append(f"{team} seed {seed}: no atom covers mask={outcome_mask} margins={margins}")

    assert not failures, f"{len(failures)} uncovered outcome(s):\n" + "\n".join(failures[:20])
