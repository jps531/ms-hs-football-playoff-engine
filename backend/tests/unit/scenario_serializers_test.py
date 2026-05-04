"""Tests for scenario_serializers: round-trip fidelity for all serialization functions."""

from backend.helpers.data_classes import GameResult, MarginCondition, PDRankCondition, RemainingGame
from backend.helpers.scenario_serializers import (
    deserialize_atom,
    deserialize_complete_scenarios,
    deserialize_condition,
    deserialize_remaining_games,
    deserialize_scenario_atoms,
    serialize_atom,
    serialize_complete_scenarios,
    serialize_condition,
    serialize_remaining_games,
    serialize_scenario_atoms,
)
from backend.helpers.scenario_viewer import enumerate_division_scenarios, render_scenarios
from backend.tests.data.standings_2025_3_7a import (
    expected_3_7a_completed_games,
    expected_3_7a_remaining_games,
    expected_3_7a_scenarios,
    teams_3_7a,
)

# ---------------------------------------------------------------------------
# GameResult serialization
# ---------------------------------------------------------------------------


def test_game_result_serialize():
    """serialize_condition produces the expected dict for a GameResult."""
    gr = GameResult(winner="Pearl", loser="Petal", min_margin=1, max_margin=None)
    d = serialize_condition(gr)
    assert d == {"type": "game_result", "winner": "Pearl", "loser": "Petal", "min_margin": 1, "max_margin": None}


def test_game_result_roundtrip():
    """A GameResult survives a serialize → deserialize round-trip unchanged."""
    gr = GameResult(winner="Pearl", loser="Petal", min_margin=1, max_margin=None)
    assert deserialize_condition(serialize_condition(gr)) == gr


def test_game_result_roundtrip_with_max_margin():
    """A GameResult with both min and max_margin survives a round-trip unchanged."""
    gr = GameResult(winner="Brandon", loser="Meridian", min_margin=3, max_margin=7)
    assert deserialize_condition(serialize_condition(gr)) == gr


# ---------------------------------------------------------------------------
# MarginCondition serialization
# ---------------------------------------------------------------------------


def test_margin_condition_serialize():
    """serialize_condition produces the expected dict for a MarginCondition."""
    mc = MarginCondition(
        add=(("Pearl", "Petal"), ("Oak Grove", "Brandon")),
        sub=(("Meridian", "NWR"),),
        op=">=",
        threshold=5,
    )
    d = serialize_condition(mc)
    assert d["type"] == "margin_condition"
    assert d["op"] == ">="
    assert d["threshold"] == 5
    assert d["add"] == [["Pearl", "Petal"], ["Oak Grove", "Brandon"]]
    assert d["sub"] == [["Meridian", "NWR"]]


def test_margin_condition_roundtrip_ge():
    """A MarginCondition with op '>=' survives a round-trip unchanged."""
    mc = MarginCondition(
        add=(("Pearl", "NWR"),),
        sub=(),
        op=">=",
        threshold=8,
    )
    assert deserialize_condition(serialize_condition(mc)) == mc


def test_margin_condition_roundtrip_le():
    """A MarginCondition with op '<=' and two add pairs survives a round-trip unchanged."""
    mc = MarginCondition(
        add=(("Pearl", "NWR"), ("Petal", "Brandon")),
        sub=(),
        op="<=",
        threshold=10,
    )
    assert deserialize_condition(serialize_condition(mc)) == mc


def test_margin_condition_roundtrip_eq():
    """A MarginCondition with op '==' and a sub pair survives a round-trip unchanged."""
    mc = MarginCondition(
        add=(("Pearl", "NWR"),),
        sub=(("Petal", "Brandon"),),
        op="==",
        threshold=2,
    )
    assert deserialize_condition(serialize_condition(mc)) == mc


# ---------------------------------------------------------------------------
# PDRankCondition serialization
# ---------------------------------------------------------------------------


def test_pd_rank_condition_serialize():
    """serialize_condition produces the expected dict for a PDRankCondition."""
    cond = PDRankCondition(team="Hamilton", rank=1, group=("Hamilton", "Hatley", "Walnut"))
    d = serialize_condition(cond)
    assert d == {
        "type": "pd_rank_condition",
        "team": "Hamilton",
        "rank": 1,
        "group": ["Hamilton", "Hatley", "Walnut"],
    }


def test_pd_rank_condition_roundtrip():
    """A PDRankCondition survives a serialize → deserialize round-trip unchanged."""
    cond = PDRankCondition(team="Hatley", rank=2, group=("Hamilton", "Hatley", "Walnut"))
    assert deserialize_condition(serialize_condition(cond)) == cond


def test_pd_rank_condition_group_is_tuple_after_roundtrip():
    """The group field is restored as a tuple (not a list) after deserialization."""
    cond = PDRankCondition(team="Walnut", rank=3, group=("Hamilton", "Hatley", "Walnut"))
    result = deserialize_condition(serialize_condition(cond))
    assert isinstance(result, PDRankCondition)
    assert isinstance(result.group, tuple)


def test_atom_roundtrip_with_pd_rank_condition():
    """An atom mixing a GameResult and PDRankCondition round-trips correctly."""
    atom = [
        GameResult(winner="Hamilton", loser="Hatley", min_margin=1, max_margin=None),
        PDRankCondition(team="Hamilton", rank=1, group=("Hamilton", "Hatley", "Walnut")),
    ]
    assert deserialize_atom(serialize_atom(atom)) == atom


def test_serialize_condition_unknown_type_raises():
    """serialize_condition raises TypeError for unsupported condition types."""
    import pytest

    with pytest.raises(TypeError):
        serialize_condition("not_a_condition")


def test_deserialize_condition_unknown_type_raises():
    """deserialize_condition raises ValueError for unrecognised type strings."""
    import pytest

    with pytest.raises(ValueError):
        deserialize_condition({"type": "unknown_type"})


# ---------------------------------------------------------------------------
# Atom (list of conditions) serialization
# ---------------------------------------------------------------------------


def test_atom_roundtrip_empty():
    """An empty atom (no conditions) round-trips to an empty list."""
    assert deserialize_atom(serialize_atom([])) == []


def test_atom_roundtrip_single_game_result():
    """A single-element atom with a GameResult round-trips correctly."""
    atom = [GameResult(winner="Pearl", loser="Petal", min_margin=1, max_margin=None)]
    assert deserialize_atom(serialize_atom(atom)) == atom


def test_atom_roundtrip_mixed():
    """An atom containing both a GameResult and a MarginCondition round-trips correctly."""
    atom = [
        GameResult(winner="Pearl", loser="Petal", min_margin=1, max_margin=None),
        MarginCondition(add=(("Pearl", "NWR"),), sub=(), op=">=", threshold=5),
    ]
    result = deserialize_atom(serialize_atom(atom))
    assert result == atom


# ---------------------------------------------------------------------------
# scenario_atoms: dict[str, dict[int, list[list]]]
# ---------------------------------------------------------------------------


def test_scenario_atoms_seed_keys_become_strings():
    """serialize_scenario_atoms converts integer seed keys to strings for JSON compatibility."""
    atoms = {
        "Pearl": {1: [[GameResult("Pearl", "Petal", 1, None)]], 2: []},
    }
    serialized = serialize_scenario_atoms(atoms)
    assert "1" in serialized["Pearl"]
    assert "2" in serialized["Pearl"]
    assert 1 not in serialized["Pearl"]


def test_scenario_atoms_roundtrip_seed_keys_become_int():
    """deserialize_scenario_atoms restores seed keys as integers after a round-trip."""
    atoms = {
        "Pearl": {1: [[GameResult("Pearl", "Petal", 1, None)]], 2: []},
    }
    result = deserialize_scenario_atoms(serialize_scenario_atoms(atoms))
    assert 1 in result["Pearl"]
    assert isinstance(list(result["Pearl"].keys())[0], int)


def test_scenario_atoms_roundtrip_full():
    """A multi-team, multi-seed scenario_atoms dict round-trips with all conditions preserved."""
    atoms = {
        "Pearl": {
            1: [
                [
                    GameResult("Pearl", "Petal", 1, None),
                    MarginCondition(add=(("Pearl", "NWR"),), sub=(), op=">=", threshold=5),
                ]
            ],
            2: [],
        },
        "Petal": {
            1: [],
            2: [[GameResult("Petal", "Pearl", 1, None)]],
        },
    }
    result = deserialize_scenario_atoms(serialize_scenario_atoms(atoms))
    assert result["Pearl"][1] == atoms["Pearl"][1]
    assert result["Petal"][2] == atoms["Petal"][2]


# ---------------------------------------------------------------------------
# complete_scenarios: list[dict]
# ---------------------------------------------------------------------------


def test_complete_scenarios_roundtrip_no_atom():
    """A complete scenario with conditions_atom=None round-trips with all fields intact."""
    scenarios = [
        {
            "scenario_num": 1,
            "sub_label": "",
            "game_winners": [("Pearl", "Petal"), ("Oak Grove", "Brandon")],
            "conditions_atom": None,
            "seeding": ("Pearl", "Petal", "Oak Grove", "Brandon", "Meridian", "NWR"),
        }
    ]
    result = deserialize_complete_scenarios(serialize_complete_scenarios(scenarios))
    assert result[0]["scenario_num"] == 1
    assert result[0]["sub_label"] == ""
    assert result[0]["game_winners"] == [("Pearl", "Petal"), ("Oak Grove", "Brandon")]
    assert result[0]["conditions_atom"] is None
    assert result[0]["seeding"] == ("Pearl", "Petal", "Oak Grove", "Brandon", "Meridian", "NWR")


def test_complete_scenarios_roundtrip_with_atom():
    """A complete scenario with a non-None conditions_atom round-trips with the atom preserved."""
    scenarios = [
        {
            "scenario_num": 4,
            "sub_label": "a",
            "game_winners": [("Pearl", "Petal")],
            "conditions_atom": [GameResult("Pearl", "Petal", 1, None)],
            "seeding": ("Pearl", "Petal", "Oak Grove", "Brandon", "Meridian", "NWR"),
        }
    ]
    result = deserialize_complete_scenarios(serialize_complete_scenarios(scenarios))
    assert result[0]["conditions_atom"] == [GameResult("Pearl", "Petal", 1, None)]


def test_complete_scenarios_game_winners_are_tuples_after_roundtrip():
    """game_winners entries are restored as tuples (not lists) after deserialization."""
    scenarios = [
        {
            "scenario_num": 1,
            "sub_label": "",
            "game_winners": [("Pearl", "Petal")],
            "conditions_atom": None,
            "seeding": ("Pearl", "Petal"),
        }
    ]
    result = deserialize_complete_scenarios(serialize_complete_scenarios(scenarios))
    assert isinstance(result[0]["game_winners"][0], tuple)
    assert isinstance(result[0]["seeding"], tuple)


def test_complete_scenarios_seeding_is_tuple_after_roundtrip():
    """The seeding field is restored as a tuple (not a list) after deserialization."""
    scenarios = [
        {
            "scenario_num": 1,
            "sub_label": "",
            "game_winners": [],
            "conditions_atom": None,
            "seeding": ("Pearl", "Petal", "Oak Grove", "Brandon"),
        }
    ]
    result = deserialize_complete_scenarios(serialize_complete_scenarios(scenarios))
    assert isinstance(result[0]["seeding"], tuple)


# ---------------------------------------------------------------------------
# remaining_games
# ---------------------------------------------------------------------------


def test_remaining_games_roundtrip():
    """A list of RemainingGame objects round-trips with all a/b fields preserved."""
    remaining = [RemainingGame(a="Pearl", b="Petal"), RemainingGame(a="Oak Grove", b="Brandon")]
    result = deserialize_remaining_games(serialize_remaining_games(remaining))
    assert result[0].a == "Pearl"
    assert result[0].b == "Petal"
    assert result[1].a == "Oak Grove"
    assert result[1].b == "Brandon"


def test_remaining_games_roundtrip_preserves_order():
    """Deserialized remaining games appear in the same order as the original list."""
    remaining = [RemainingGame(a="A", b="B"), RemainingGame(a="C", b="D"), RemainingGame(a="E", b="F")]
    result = deserialize_remaining_games(serialize_remaining_games(remaining))
    assert [(r.a, r.b) for r in result] == [("A", "B"), ("C", "D"), ("E", "F")]


# ---------------------------------------------------------------------------
# Full round-trip: enumerate → serialize → deserialize → render
# ---------------------------------------------------------------------------


def test_render_scenarios_from_deserialized_matches_direct():
    """render_scenarios() on deserialized output matches render on original."""
    complete_scenarios = enumerate_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        expected_3_7a_remaining_games,
        scenario_atoms=expected_3_7a_scenarios,
    )

    serialized = serialize_complete_scenarios(complete_scenarios)
    deserialized = deserialize_complete_scenarios(serialized)

    direct_text = render_scenarios(complete_scenarios)
    roundtrip_text = render_scenarios(deserialized)
    assert direct_text == roundtrip_text


def test_scenario_atoms_from_deserialized_matches_original():
    """scenario_atoms round-trips preserve equality of all conditions."""
    atoms = expected_3_7a_scenarios
    result = deserialize_scenario_atoms(serialize_scenario_atoms(atoms))

    for team in atoms:
        assert team in result
        for seed in atoms[team]:
            assert seed in result[team]
            assert result[team][seed] == atoms[team][seed]


def test_remaining_games_roundtrip_3_7a():
    """The real 3-7A remaining games round-trip with order and values preserved."""
    remaining = expected_3_7a_remaining_games
    result = deserialize_remaining_games(serialize_remaining_games(remaining))
    assert [(r.a, r.b) for r in result] == [(rg.a, rg.b) for rg in remaining]
