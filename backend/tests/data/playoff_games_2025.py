"""Loader for the 2025 MHSAA playoff game records.

Parses ``playoff_games_2025.json`` (school-perspective DB rows for all
completed 2025 playoff games) into ``Game`` objects suitable for use in
``survivors_from_games`` tests.
"""

import json
from datetime import date
from pathlib import Path

from backend.helpers.data_classes import Game

_JSON_PATH = Path(__file__).parent / "playoff_games_2025.json"


def load_playoff_games_2025() -> list[Game]:
    """Return all 2025 playoff Game records parsed from the JSON fixture."""
    with _JSON_PATH.open() as f:
        data = json.load(f)

    games: list[Game] = []
    for raw in data["games"]:
        row = dict(raw)
        row["date"] = date.fromisoformat(row["date"])
        game = Game.from_db_tuple(row)
        if game is not None:
            games.append(game)
    return games


PLAYOFF_GAMES_2025: list[Game] = load_playoff_games_2025()
