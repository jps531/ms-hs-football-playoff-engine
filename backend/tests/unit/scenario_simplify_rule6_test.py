"""Rule 6 of _simplify_atom_list: a branch needn't say a game's other winner when an earlier branch is that
game's winner plus only conditions the branch already has."""

import itertools
import random

from backend.helpers.data_classes import GameResult as G
from backend.helpers.data_classes import MarginCondition
from backend.helpers.scenario_viewer import _simplify_atom_list


def test_the_redundant_opposite_is_dropped():
    """Lanier beats Vicksburg, or Provine and Florence win and Vicksburg beats Lanier: the last says nothing."""
    atoms = [
        [G("Lanier", "Vicksburg")],
        [G("Provine", "Cleveland Central"), G("Florence", "Holmes County Central"), G("Vicksburg", "Lanier")],
    ]
    assert _simplify_atom_list(atoms) == [
        [G("Lanier", "Vicksburg")],
        [G("Provine", "Cleveland Central"), G("Florence", "Holmes County Central")],
    ]


def test_it_keeps_the_opposite_when_dropping_it_would_change_the_meaning():
    # The first branch needs a margin, so "Vicksburg beats Lanier" isn't all that's left.
    margin = [[G("Lanier", "Vicksburg", 7)], [G("Provine", "Cleveland Central"), G("Vicksburg", "Lanier")]]
    assert _simplify_atom_list(margin) == margin
    # The first branch needs something the second doesn't have.
    extra = [
        [G("Lanier", "Vicksburg"), G("Leake", "Florence")],
        [G("Provine", "Cleveland Central"), G("Vicksburg", "Lanier")],
    ]
    assert _simplify_atom_list(extra) == extra
    # A margin condition on the game ties it to who wins it.
    mc = MarginCondition(add=(("Lanier", "Vicksburg"),), sub=(), op=">=", threshold=5)
    tied = [[G("Lanier", "Vicksburg")], [G("Vicksburg", "Lanier"), G("Provine", "Cleveland Central"), mc]]
    assert _simplify_atom_list(tied) == tied


def test_simplifying_never_changes_which_results_satisfy_the_list():
    """Random lists over four games, plain winners only: the same truth table before and after."""
    games = [("A", "B"), ("C", "D"), ("E", "F"), ("G", "H")]
    rng = random.Random(6)

    def holds(atoms, outcome):
        """Whether *outcome* (each game's winner) satisfies some atom."""
        return any(
            all(
                outcome[(c.winner, c.loser) if (c.winner, c.loser) in outcome else (c.loser, c.winner)] == c.winner
                for c in a
            )
            for a in atoms
        )

    for _ in range(300):
        atoms = []
        for _ in range(rng.randint(1, 4)):
            picked = rng.sample(games, rng.randint(1, 4))
            atoms.append([G(*g) if rng.random() < 0.5 else G(g[1], g[0]) for g in picked])
        simplified = _simplify_atom_list([list(a) for a in atoms])
        for winners in itertools.product(*games):
            outcome = {g: w for g, w in zip(games, winners)}
            assert holds(atoms, outcome) == holds(simplified, outcome), (atoms, simplified, outcome)


def test_two_identical_ways_in_another_order_keep_one():
    """Each covers the other; one must stay, or the list would say nothing can happen."""
    a = [G("Provine", "Cleveland Central"), G("Florence", "Holmes County Central")]
    out = _simplify_atom_list([a, list(reversed(a))])
    assert len(out) == 1 and set(out[0]) == set(a)


def test_a_way_stating_a_tiebreaker_keeps_its_games():
    """A tiebreaker presumes the games that make the tie, so the game stays with it (Region 4-4A: Gentry)."""
    from backend.helpers.data_classes import TiebreakDecision

    tie = TiebreakDecision(step=3, group=("Gentry", "Greenwood", "Yazoo City"), parts=(("Gentry", "Greenwood"), ("Yazoo City",)))
    atoms = [[G("Gentry", "Yazoo City")], [G("Yazoo City", "Gentry"), G("Louisville", "Greenwood"), tie]]
    assert _simplify_atom_list(atoms) == atoms
