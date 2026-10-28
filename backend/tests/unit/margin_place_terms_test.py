"""A tie too varied to list as scenarios still says, team by team, exactly which margins give each place.

The fixture is 2026's Region 5-1A with two games left (Ethel at Sebastopol, McAdams at Nanih Waiya). If
Sebastopol and McAdams both win, all five teams finish 2-2 and the two margins decide nine different
orders: too many to list, so the scenario leaves the tie open, but each team's places are stated in
margin ranges and comparisons between the two margins.
"""

import pytest

from backend.helpers.data_classes import GameResult, MarginCondition, RemainingGame
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenario_renderer import _render_atom, _render_margin_condition, atoms_from_complete_scenarios
from backend.helpers.scenario_serializers import deserialize_complete_scenarios, serialize_complete_scenarios
from backend.helpers.scenario_viewer import _linear_pieces, enumerate_division_scenarios
from backend.tests.data.results_2025_ground_truth import expand_results
from backend.tests.scenario_coverage import team_path_problems

_GAMES = [
    ("2026-10-01", "Noxapater", 35, "Sebastopol", 20),
    ("2026-10-02", "Ethel", 21, "McAdams", 18),
    ("2026-10-08", "Sebastopol", 36, "McAdams", 6),
    ("2026-10-08", "Nanih Waiya", 27, "Noxapater", 13),
    ("2026-10-16", "Noxapater", 20, "Ethel", 14),
    ("2026-10-16", "Nanih Waiya", 42, "Sebastopol", 19),
    ("2026-10-23", "Ethel", 21, "Nanih Waiya", 6),
    ("2026-10-23", "McAdams", 26, "Noxapater", 25),
]
TEAMS = ["Ethel", "McAdams", "Nanih Waiya", "Noxapater", "Sebastopol"]
COMPLETED = get_completed_games(
    expand_results(
        [{"date": d, "winner": w, "winner_score": ws, "loser": l, "loser_score": ls} for d, w, ws, l, ls in _GAMES]
    )
)
REMAINING = [RemainingGame("Ethel", "Sebastopol"), RemainingGame("McAdams", "Nanih Waiya")]
CAP = " (a margin over 12 counts as 12)"


@pytest.fixture(scope="module")
def scenarios():
    # Through a snapshot and back, as the API reads them.
    """The region's complete scenarios, through a snapshot and back as the API reads them."""
    built = enumerate_division_scenarios(TEAMS, COMPLETED, REMAINING)
    return deserialize_complete_scenarios(serialize_complete_scenarios(built))


@pytest.fixture(scope="module")
def atoms(scenarios):
    """Each team's seed conditions, read off the scenarios."""
    return atoms_from_complete_scenarios(scenarios)


def test_five_way_tie_states_every_teams_places(scenarios):
    """The scenario where all five finish 2-2 states places for every team."""
    tie = next(s for s in scenarios if s.get("place_terms"))
    assert set(tie["game_winners"]) == {("Sebastopol", "Ethel"), ("McAdams", "Nanih Waiya")}
    assert set(tie["place_terms"]) == set(TEAMS)


def test_paths_are_exact(atoms):
    """Every path holds exactly when the team takes that place, for every winner and margin."""
    report = team_path_problems(TEAMS, COMPLETED, REMAINING, atoms)
    assert report.checked == 4 * 144
    assert report.false == [] and report.missing == []


def _cards(atoms, team, seed):
    """The rendered conditions for *team* finishing *seed* that turn on a margin."""
    return sorted(
        _render_atom(a)
        for a in atoms[team][seed]
        if any(isinstance(c, MarginCondition) or c.max_margin or c.min_margin > 1 for c in a)
    )


def test_cards_read_as_margins(atoms):
    """Each team's margin-dependent places read as margin ranges and comparisons between the two margins."""
    both = "Sebastopol beats Ethel AND McAdams beats Nanih Waiya"
    assert _cards(atoms, "Sebastopol", 5) == [f"{both} AND McAdams wins by at least 3 more points than Sebastopol{CAP}"]
    assert _cards(atoms, "Sebastopol", 3) == ["Sebastopol beats Ethel by 11 or more AND McAdams beats Nanih Waiya"]
    assert _cards(atoms, "Ethel", 5) == [
        "Sebastopol beats Ethel by 12 or more AND McAdams beats Nanih Waiya by 12 or more"
    ]
    assert _cards(atoms, "Nanih Waiya", 1) == [
        f"Sebastopol beats Ethel AND McAdams beats Nanih Waiya by 1–7 AND McAdams wins by no more than 2 more points than Sebastopol{CAP}"
    ]
    assert _cards(atoms, "Noxapater", 1) == [
        "Sebastopol beats Ethel by 4 or more AND McAdams beats Nanih Waiya by 8 or more"
    ]


def test_pieces_are_exact_and_limited():
    """A diagonal band is one piece (a range and a comparison); a checkerboard takes too many."""
    band = {(s, m) for s in range(1, 11) for m in range(1, 13) if m <= s + 2}
    (piece,) = _linear_pieces(band, 2, 2)
    assert sorted(piece) == [
        ((1, -1), -2, None),
        ((1, 0), None, 10),
    ]  # Sebastopol by 10 or less, McAdams by at most 2 more
    checker = {(s, m) for s in range(1, 13) for m in range(1, 13) if (s + m) % 2}
    assert _linear_pieces(checker, 2, 2) is None


@pytest.mark.parametrize(
    ("op", "threshold", "text"),
    [
        (">=", 3, "McAdams wins by at least 3 more points than Sebastopol"),
        ("<=", 2, "McAdams wins by no more than 2 more points than Sebastopol"),
        ("<=", -1, "Sebastopol wins by at least 1 more point than McAdams"),
        (">=", -4, "Sebastopol wins by no more than 4 more points than McAdams"),
        (">", 0, "McAdams wins by at least 1 more point than Sebastopol"),
        (">=", 0, "McAdams wins by at least as many points as Sebastopol"),
    ],
)
def test_comparison_wording(op, threshold, text):
    """A comparison between the two margins reads in words for each operator and threshold."""
    atom = [GameResult("Sebastopol", "Ethel"), GameResult("McAdams", "Nanih Waiya")]
    cond = MarginCondition(
        add=(("McAdams", "Nanih Waiya"),), sub=(("Ethel", "Sebastopol"),), op=op, threshold=threshold
    )
    assert _render_margin_condition(cond, atom) == text + CAP
