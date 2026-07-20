"""JSON serialization and deserialization for scenario atom data structures.

Converts between Python dataclasses (GameResult, MarginCondition) and plain
JSON-compatible dicts so that scenario data can be persisted to PostgreSQL JSONB
columns and reconstructed without re-running the tiebreaker engine.

Round-trip guarantee:
    deserialize_atom(serialize_atom(atom)) == atom          # for any atom list
    deserialize_scenario_atoms(serialize_scenario_atoms(sa)) == sa
    deserialize_complete_scenarios(serialize_complete_scenarios(cs)) == cs
"""

from typing import cast

from backend.helpers.data_classes import (
    GameResult,
    HomeGameCondition,
    HomeGameScenario,
    MarginCondition,
    PDRankCondition,
)

# ---------------------------------------------------------------------------
# Individual condition serialization
# ---------------------------------------------------------------------------


def serialize_condition(cond) -> dict:
    """Serialize a single GameResult or MarginCondition to a JSON-safe dict."""
    if isinstance(cond, GameResult):
        return {
            "type": "game_result",
            "winner": cond.winner,
            "loser": cond.loser,
            "min_margin": cond.min_margin,
            "max_margin": cond.max_margin,
        }
    if isinstance(cond, MarginCondition):
        return {
            "type": "margin_condition",
            "add": [list(pair) for pair in cond.add],
            "sub": [list(pair) for pair in cond.sub],
            "op": cond.op,
            "threshold": cond.threshold,
        }
    if isinstance(cond, PDRankCondition):
        return {
            "type": "pd_rank_condition",
            "team": cond.team,
            "rank": cond.rank,
            "group": list(cond.group),
        }
    if isinstance(cond, HomeGameCondition):
        return {
            "type": "home_game_condition",
            "kind": cond.kind,
            "round_name": cond.round_name,
            "region": cond.region,
            "seed": cond.seed,
            "team_name": cond.team_name,
        }
    raise TypeError(f"Cannot serialize condition of type {type(cond).__name__!r}")


def deserialize_condition(d: dict) -> GameResult | MarginCondition | PDRankCondition | HomeGameCondition:
    """Deserialize a dict produced by serialize_condition back to a dataclass."""
    t = d["type"]
    if t == "game_result":
        return GameResult(
            winner=d["winner"],
            loser=d["loser"],
            min_margin=d["min_margin"],
            max_margin=d["max_margin"],
        )
    if t == "margin_condition":
        return MarginCondition(
            add=tuple(tuple(p) for p in d["add"]),
            sub=tuple(tuple(p) for p in d["sub"]),
            op=d["op"],
            threshold=d["threshold"],
        )
    if t == "pd_rank_condition":
        return PDRankCondition(
            team=d["team"],
            rank=d["rank"],
            group=tuple(d["group"]),
        )
    if t == "home_game_condition":
        return HomeGameCondition(
            kind=d["kind"],
            round_name=d["round_name"],
            region=d["region"],
            seed=d["seed"],
            team_name=d["team_name"],
        )
    raise ValueError(f"Unknown condition type: {t!r}")


# ---------------------------------------------------------------------------
# Atom (list of conditions) serialization
# ---------------------------------------------------------------------------


def serialize_atom(atom: list) -> list[dict]:
    """Serialize a list of conditions (one atom) to a list of dicts."""
    return [serialize_condition(c) for c in atom]


def deserialize_atom(data: list[dict]) -> list:
    """Deserialize a list of condition dicts back to a list of dataclasses."""
    return [deserialize_condition(d) for d in data]


# ---------------------------------------------------------------------------
# HomeGameScenario (a condition tuple + explanation, hosting-domain container)
# ---------------------------------------------------------------------------


def serialize_home_game_scenario(sc: HomeGameScenario) -> dict:
    """Serialize a single HomeGameScenario to a JSON-safe dict."""
    return {
        "conditions": [serialize_condition(c) for c in sc.conditions],
        "explanation": sc.explanation,
    }


def deserialize_home_game_scenario(d: dict) -> HomeGameScenario:
    """Deserialize a dict produced by serialize_home_game_scenario back to a HomeGameScenario."""
    return HomeGameScenario(
        conditions=tuple(cast(HomeGameCondition, deserialize_condition(c)) for c in d["conditions"]),
        explanation=d["explanation"],
    )


# ---------------------------------------------------------------------------
# scenario_atoms: dict[str, dict[int, list[list]]]
# ---------------------------------------------------------------------------


def serialize_scenario_atoms(scenario_atoms: dict) -> dict:
    """Serialize the scenario_atoms dict to a JSON-safe structure.

    JSON object keys must be strings, so integer seed keys are converted to
    strings (``1`` → ``"1"``).  Deserializing reverses this.
    """
    return {
        team: {str(seed): [serialize_atom(atom) for atom in atoms] for seed, atoms in seed_map.items()}
        for team, seed_map in scenario_atoms.items()
    }


def deserialize_scenario_atoms(data: dict) -> dict:
    """Deserialize a JSON structure back to scenario_atoms.

    String seed keys (``"1"``) are converted back to integers (``1``).
    """
    return {
        team: {
            int(seed_str): [deserialize_atom(atom_data) for atom_data in atoms_data]
            for seed_str, atoms_data in seed_map_data.items()
        }
        for team, seed_map_data in data.items()
    }


# ---------------------------------------------------------------------------
# complete_scenarios: list[dict] from enumerate_division_scenarios()
# ---------------------------------------------------------------------------


def serialize_complete_scenarios(scenarios: list[dict]) -> list[dict]:
    """Serialize the output of enumerate_division_scenarios() to JSON-safe dicts.

    Each scenario dict becomes:
    {
        "scenario_num": int,
        "sub_label": str,
        "game_winners": [[winner, loser], ...],
        "conditions_atom": [condition_dict, ...] | null,
        "tiebreaker_groups": [[team, ...], ...] | null,
        "coinflip_groups": [[team, ...], ...] | null,
        "seeding": [team, ...]
    }
    """
    result = []
    for sc in scenarios:
        atom = sc.get("conditions_atom")
        result.append(
            {
                "scenario_num": sc["scenario_num"],
                "sub_label": sc["sub_label"],
                "game_winners": [list(gw) for gw in sc["game_winners"]],
                "conditions_atom": serialize_atom(atom) if atom is not None else None,
                "tiebreaker_groups": sc.get("tiebreaker_groups"),
                "coinflip_groups": sc.get("coinflip_groups"),
                "seeding": list(sc["seeding"]),
            }
        )
    return result


def deserialize_complete_scenarios(data: list[dict]) -> list[dict]:
    """Deserialize JSON scenario list back to the enumerate_division_scenarios() format."""
    result = []
    for sc in data:
        atom_data = sc.get("conditions_atom")
        result.append(
            {
                "scenario_num": sc["scenario_num"],
                "sub_label": sc["sub_label"],
                "game_winners": [tuple(gw) for gw in sc["game_winners"]],
                "conditions_atom": deserialize_atom(atom_data) if atom_data is not None else None,
                "tiebreaker_groups": sc.get("tiebreaker_groups"),
                "coinflip_groups": sc.get("coinflip_groups"),
                "seeding": tuple(sc["seeding"]),
            }
        )
    return result


# ---------------------------------------------------------------------------
# remaining_games: list[RemainingGame]
# ---------------------------------------------------------------------------


def serialize_remaining_games(remaining) -> list[dict]:
    """Serialize a list of RemainingGame to JSON-safe dicts."""
    return [{"a": rg.a, "b": rg.b} for rg in remaining]


def deserialize_remaining_games(data: list[dict]):
    """Deserialize a list of dicts back to RemainingGame instances."""
    from backend.helpers.data_classes import RemainingGame

    return [RemainingGame(a=d["a"], b=d["b"]) for d in data]
