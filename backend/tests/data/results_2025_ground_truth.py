"""2025 full-season region game results and known playoff seeds for all MHSAA regions.

Each entry in ``REGION_RESULTS_2025`` is keyed by ``(class, region)`` and holds:

* ``games`` — list of completed region games in compact form.  Each game is a
  dict with keys ``date``, ``winner``, ``winner_score``, ``loser``,
  ``loser_score``.  List each matchup **once**; the helper expands both sides.

* ``seeds`` — dict mapping seed number (1-4) to the school name that actually
  earned that seed in the 2025 playoffs.

* ``eliminated`` — set of school names that did **not** make the playoffs
  (finished 5th or worse in the region).

Ground-truth seeds are verified against the official 2025 MHSAA playoff bracket.
"""

from typing import TypedDict

from backend.helpers.data_classes import RawCompletedGame


class RegionGame(TypedDict):
    """Compact representation of a single completed region game."""

    date: str
    winner: str
    winner_score: int
    loser: str
    loser_score: int


class RegionFixture(TypedDict):
    """Full fixture for one (class, region) combination."""

    games: list[RegionGame]
    seeds: dict[int, str]  # {1: "School", 2: "School", 3: "School", 4: "School"}
    eliminated: set[str]


def expand_results(games: list[RegionGame]) -> list[RawCompletedGame]:
    """Expand compact game list to ``RawCompletedGame`` format (both perspectives).

    Args:
        games: List of compact game records, each listed once.

    Returns:
        List of raw game dicts suitable for ``get_completed_games()``, with
        one entry per team per game (two entries total per game).
    """
    raw = []
    for g in games:
        raw.append(
            {
                "school": g["winner"],
                "opponent": g["loser"],
                "date": g["date"],
                "result": "W",
                "points_for": g["winner_score"],
                "points_against": g["loser_score"],
            }
        )
        raw.append(
            {
                "school": g["loser"],
                "opponent": g["winner"],
                "date": g["date"],
                "result": "L",
                "points_for": g["loser_score"],
                "points_against": g["winner_score"],
            }
        )
    return raw


def teams_from_games(games: list[RegionGame]) -> list[str]:
    """Derive sorted team list from a compact game list.

    Args:
        games: Compact game records for a region.

    Returns:
        Alphabetically sorted list of unique team names.
    """
    names: set[str] = set()
    for g in games:
        names.add(g["winner"])
        names.add(g["loser"])
    return sorted(names)


# ---------------------------------------------------------------------------
# 2025 region results — fill in one entry per (class, region)
# ---------------------------------------------------------------------------
# fmt: off

REGION_RESULTS_2025: dict[tuple[int, int], RegionFixture] = {

    # -----------------------------------------------------------------------
    # 7A
    # -----------------------------------------------------------------------

    (7, 1): {
        "games": [
            {"date": "2025-10-03", "winner": "Hernando", "winner_score": 22, "loser": "Horn Lake", "loser_score": 21},
            {"date": "2025-10-10", "winner": "Desoto Central", "winner_score": 49, "loser": "Lewisburg", "loser_score": 14},
            {"date": "2025-10-10", "winner": "Tupelo", "winner_score": 43, "loser": "Southaven", "loser_score": 20},
            {"date": "2025-10-17", "winner": "Horn Lake", "winner_score": 35, "loser": "Desoto Central", "loser_score": 20},
            {"date": "2025-10-17", "winner": "Southaven", "winner_score": 31, "loser": "Lewisburg", "loser_score":  7},
            {"date": "2025-10-17", "winner": "Tupelo", "winner_score": 35, "loser": "Hernando", "loser_score": 17},
            {"date": "2025-10-24", "winner": "Desoto Central", "winner_score": 28, "loser": "Southaven", "loser_score": 21},
            {"date": "2025-10-24", "winner": "Hernando", "winner_score": 52, "loser": "Lewisburg", "loser_score": 31},
            {"date": "2025-10-24", "winner": "Tupelo", "winner_score": 38, "loser": "Horn Lake", "loser_score": 13},
            {"date": "2025-10-30", "winner": "Desoto Central", "winner_score": 42, "loser": "Hernando", "loser_score": 21},
            {"date": "2025-10-30", "winner": "Tupelo", "winner_score": 49, "loser": "Lewisburg", "loser_score":  0},
            {"date": "2025-10-31", "winner": "Horn Lake", "winner_score": 31, "loser": "Southaven", "loser_score": 14},
            {"date": "2025-11-06", "winner": "Hernando", "winner_score": 31, "loser": "Southaven", "loser_score": 14},
            {"date": "2025-11-06", "winner": "Horn Lake", "winner_score": 40, "loser": "Lewisburg", "loser_score": 17},
            {"date": "2025-11-06", "winner": "Tupelo", "winner_score": 42, "loser": "Desoto Central", "loser_score": 19},
        ],
        "seeds": {1: "Tupelo", 2: "Horn Lake", 3: "Desoto Central", 4: "Hernando"},
        "eliminated": {"Lewisburg", "Southaven"},
    },

    (7, 2): {
        "games": [
            {"date": "2025-10-03", "winner": "Oxford", "winner_score": 16, "loser": "Madison Central", "loser_score": 14},
            {"date": "2025-10-09", "winner": "Clinton", "winner_score": 35, "loser": "Murrah", "loser_score":  0},
            {"date": "2025-10-10", "winner": "Germantown", "winner_score": 45, "loser": "Starkville", "loser_score": 28},
            {"date": "2025-10-17", "winner": "Madison Central", "winner_score": 45, "loser": "Murrah", "loser_score": 12},
            {"date": "2025-10-17", "winner": "Oxford", "winner_score": 43, "loser": "Germantown", "loser_score": 42},
            {"date": "2025-10-17", "winner": "Starkville", "winner_score": 28, "loser": "Clinton", "loser_score":  7},
            {"date": "2025-10-24", "winner": "Germantown", "winner_score": 21, "loser": "Madison Central", "loser_score": 17},
            {"date": "2025-10-24", "winner": "Oxford", "winner_score": 33, "loser": "Clinton", "loser_score": 23},
            {"date": "2025-10-24", "winner": "Starkville", "winner_score": 55, "loser": "Murrah", "loser_score": 14},
            {"date": "2025-10-30", "winner": "Oxford", "winner_score": 42, "loser": "Murrah", "loser_score":  0},
            {"date": "2025-10-31", "winner": "Germantown", "winner_score": 47, "loser": "Clinton", "loser_score": 17},
            {"date": "2025-10-31", "winner": "Madison Central", "winner_score": 38, "loser": "Starkville", "loser_score": 35},
            {"date": "2025-11-06", "winner": "Germantown", "winner_score": 56, "loser": "Murrah", "loser_score":  0},
            {"date": "2025-11-06", "winner": "Madison Central", "winner_score": 28, "loser": "Clinton", "loser_score": 16},
            {"date": "2025-11-06", "winner": "Oxford", "winner_score": 27, "loser": "Starkville", "loser_score": 21},
        ],
        "seeds": {1: "Oxford", 2: "Germantown", 3: "Madison Central", 4: "Starkville"},
        "eliminated": {"Clinton", "Murrah"},
    },

    (7, 3): {
        "games": [
            {"date": "2025-10-03", "winner": "Brandon",        "winner_score":  3, "loser": "Northwest Rankin", "loser_score":  0},
            {"date": "2025-10-10", "winner": "Petal",          "winner_score": 28, "loser": "Oak Grove",        "loser_score": 21},
            {"date": "2025-10-10", "winner": "Pearl",          "winner_score": 38, "loser": "Meridian",         "loser_score": 17},
            {"date": "2025-10-17", "winner": "Oak Grove",      "winner_score": 42, "loser": "Meridian",         "loser_score": 21},
            {"date": "2025-10-17", "winner": "Petal",          "winner_score": 27, "loser": "Brandon",          "loser_score": 21},
            {"date": "2025-10-17", "winner": "Northwest Rankin","winner_score": 33, "loser": "Pearl",            "loser_score": 29},
            {"date": "2025-10-24", "winner": "Oak Grove",      "winner_score": 20, "loser": "Brandon",          "loser_score":  7},
            {"date": "2025-10-24", "winner": "Northwest Rankin","winner_score": 31, "loser": "Meridian",         "loser_score": 12},
            {"date": "2025-10-24", "winner": "Pearl",          "winner_score": 21, "loser": "Petal",            "loser_score": 14},
            {"date": "2025-10-31", "winner": "Oak Grove",      "winner_score": 37, "loser": "Northwest Rankin", "loser_score": 34},
            {"date": "2025-10-31", "winner": "Petal",          "winner_score": 42, "loser": "Meridian",         "loser_score": 14},
            {"date": "2025-10-31", "winner": "Brandon",        "winner_score": 17, "loser": "Pearl",            "loser_score": 10},
            {"date": "2025-11-07", "winner": "Oak Grove",        "winner_score": 28, "loser": "Pearl",   "loser_score":  7},
            {"date": "2025-11-07", "winner": "Northwest Rankin","winner_score": 34, "loser": "Petal",   "loser_score": 28},
            {"date": "2025-11-07", "winner": "Brandon",        "winner_score": 40, "loser": "Meridian",        "loser_score": 13},
        ],
        "seeds": {1: "Oak Grove", 2: "Petal", 3: "Brandon", 4: "Northwest Rankin"},
        "eliminated": {"Meridian", "Pearl"},
    },

    (7, 4): {
        "games": [
            {"date": "2025-09-26", "winner": "D\'Iberville", "winner_score": 42, "loser": "Harrison Central", "loser_score":  6},
            {"date": "2025-09-26", "winner": "Ocean Springs", "winner_score": 31, "loser": "Biloxi", "loser_score":  6},
            {"date": "2025-09-26", "winner": "West Harrison", "winner_score": 26, "loser": "St. Martin", "loser_score": 21},
            {"date": "2025-10-03", "winner": "D\'Iberville", "winner_score": 25, "loser": "West Harrison", "loser_score":  7},
            {"date": "2025-10-03", "winner": "Gulfport", "winner_score": 41, "loser": "Ocean Springs", "loser_score": 28},
            {"date": "2025-10-03", "winner": "St. Martin", "winner_score": 28, "loser": "Biloxi", "loser_score": 24},
            {"date": "2025-10-09", "winner": "West Harrison", "winner_score": 18, "loser": "Harrison Central", "loser_score":  0},
            {"date": "2025-10-10", "winner": "Gulfport", "winner_score": 40, "loser": "St. Martin", "loser_score":  0},
            {"date": "2025-10-10", "winner": "Ocean Springs", "winner_score": 42, "loser": "D\'Iberville", "loser_score": 21},
            {"date": "2025-10-17", "winner": "Biloxi", "winner_score": 31, "loser": "Harrison Central", "loser_score":  6},
            {"date": "2025-10-17", "winner": "D\'Iberville", "winner_score": 46, "loser": "St. Martin", "loser_score": 10},
            {"date": "2025-10-17", "winner": "Gulfport", "winner_score": 42, "loser": "West Harrison", "loser_score": 14},
            {"date": "2025-10-24", "winner": "Gulfport", "winner_score": 35, "loser": "Biloxi", "loser_score":  0},
            {"date": "2025-10-24", "winner": "Ocean Springs", "winner_score": 56, "loser": "West Harrison", "loser_score": 21},
            {"date": "2025-10-24", "winner": "St. Martin", "winner_score": 50, "loser": "Harrison Central", "loser_score": 13},
            {"date": "2025-10-31", "winner": "Biloxi", "winner_score": 42, "loser": "West Harrison", "loser_score": 35},
            {"date": "2025-10-31", "winner": "Gulfport", "winner_score": 38, "loser": "D\'Iberville", "loser_score": 35},
            {"date": "2025-10-31", "winner": "Ocean Springs", "winner_score": 35, "loser": "Harrison Central", "loser_score":  0},
            {"date": "2025-11-06", "winner": "D\'Iberville", "winner_score": 28, "loser": "Biloxi", "loser_score":  0},
            {"date": "2025-11-06", "winner": "Gulfport", "winner_score": 45, "loser": "Harrison Central", "loser_score": 13},
            {"date": "2025-11-06", "winner": "Ocean Springs", "winner_score": 49, "loser": "St. Martin", "loser_score": 21},
        ],
        "seeds": {1: "Gulfport", 2: "Ocean Springs", 3: "D'Iberville", 4: "Biloxi"},
        "eliminated": {"Harrison Central", "St. Martin", "West Harrison"},
    },

    # -----------------------------------------------------------------------
    # 6A
    # -----------------------------------------------------------------------

    (6, 1): {
        "games": [
            {"date": "2025-10-09", "winner": "Saltillo", "winner_score": 28, "loser": "Olive Branch", "loser_score": 21},
            {"date": "2025-10-10", "winner": "Grenada", "winner_score": 42, "loser": "Center Hill", "loser_score": 11},
            {"date": "2025-10-10", "winner": "South Panola", "winner_score": 27, "loser": "Lake Cormorant", "loser_score": 20},
            {"date": "2025-10-17", "winner": "Grenada", "winner_score": 48, "loser": "Olive Branch", "loser_score":  6},
            {"date": "2025-10-17", "winner": "Lake Cormorant", "winner_score": 30, "loser": "Center Hill", "loser_score": 14},
            {"date": "2025-10-17", "winner": "South Panola", "winner_score": 52, "loser": "Saltillo", "loser_score": 26},
            {"date": "2025-10-24", "winner": "Center Hill", "winner_score": 32, "loser": "Olive Branch", "loser_score": 15},
            {"date": "2025-10-24", "winner": "Lake Cormorant", "winner_score": 41, "loser": "Saltillo", "loser_score":  7},
            {"date": "2025-10-24", "winner": "South Panola", "winner_score": 48, "loser": "Grenada", "loser_score": 41},
            {"date": "2025-10-31", "winner": "Center Hill", "winner_score": 27, "loser": "Saltillo", "loser_score": 14},
            {"date": "2025-10-31", "winner": "Lake Cormorant", "winner_score": 28, "loser": "Grenada", "loser_score": 26},
            {"date": "2025-10-31", "winner": "South Panola", "winner_score": 41, "loser": "Olive Branch", "loser_score":  7},
            {"date": "2025-11-06", "winner": "Grenada", "winner_score": 49, "loser": "Saltillo", "loser_score": 16},
            {"date": "2025-11-06", "winner": "Lake Cormorant", "winner_score": 49, "loser": "Olive Branch", "loser_score": 35},
            {"date": "2025-11-06", "winner": "South Panola", "winner_score": 31, "loser": "Center Hill", "loser_score":  7},
        ],
        "seeds": {1: "South Panola", 2: "Lake Cormorant", 3: "Grenada", 4: "Center Hill"},
        "eliminated": {"Olive Branch", "Saltillo"},
    },

    (6, 2): {
        "games": [
            {"date": "2025-10-09", "winner": "Callaway", "winner_score": 28, "loser": "Canton", "loser_score": 21},
            {"date": "2025-10-10", "winner": "Neshoba Central", "winner_score": 35, "loser": "Greenville", "loser_score": 22},
            {"date": "2025-10-10", "winner": "Warren Central", "winner_score": 21, "loser": "Ridgeland", "loser_score": 14},
            {"date": "2025-10-16", "winner": "Ridgeland", "winner_score": 48, "loser": "Callaway", "loser_score": 15},
            {"date": "2025-10-17", "winner": "Neshoba Central", "winner_score": 56, "loser": "Canton", "loser_score": 50},
            {"date": "2025-10-17", "winner": "Warren Central", "winner_score": 36, "loser": "Greenville", "loser_score":  6},
            {"date": "2025-10-23", "winner": "Ridgeland", "winner_score": 49, "loser": "Canton", "loser_score": 21},
            {"date": "2025-10-24", "winner": "Callaway", "winner_score": 13, "loser": "Greenville", "loser_score":  8},
            {"date": "2025-10-24", "winner": "Warren Central", "winner_score": 42, "loser": "Neshoba Central", "loser_score": 13},
            {"date": "2025-10-31", "winner": "Canton", "winner_score": 49, "loser": "Greenville", "loser_score": 28},
            {"date": "2025-10-31", "winner": "Ridgeland", "winner_score": 43, "loser": "Neshoba Central", "loser_score": 37},
            {"date": "2025-10-31", "winner": "Warren Central", "winner_score": 31, "loser": "Callaway", "loser_score":  7},
            {"date": "2025-11-06", "winner": "Ridgeland", "winner_score": 58, "loser": "Greenville", "loser_score": 16},
            {"date": "2025-11-06", "winner": "Warren Central", "winner_score": 34, "loser": "Canton", "loser_score": 14},
            {"date": "2025-11-07", "winner": "Callaway", "winner_score": 26, "loser": "Neshoba Central", "loser_score":  0},
        ],
        "seeds": {1: "Warren Central", 2: "Ridgeland", 3: "Callaway", 4: "Neshoba Central"},
        "eliminated": {"Canton", "Greenville"},
    },

    (6, 3): {
        "games": [
            {"date": "2025-10-09", "winner": "Hattiesburg", "winner_score": 43, "loser": "Jim Hill", "loser_score":  0},
            {"date": "2025-10-10", "winner": "Terry", "winner_score": 24, "loser": "Forest Hill", "loser_score":  6},
            {"date": "2025-10-10", "winner": "West Jones", "winner_score": 55, "loser": "George County", "loser_score": 21},
            {"date": "2025-10-16", "winner": "Hattiesburg", "winner_score": 35, "loser": "Forest Hill", "loser_score":  6},
            {"date": "2025-10-17", "winner": "George County", "winner_score": 30, "loser": "Jim Hill", "loser_score":  6},
            {"date": "2025-10-17", "winner": "West Jones", "winner_score": 28, "loser": "Terry", "loser_score": 19},
            {"date": "2025-10-24", "winner": "Hattiesburg", "winner_score": 42, "loser": "George County", "loser_score": 21},
            {"date": "2025-10-24", "winner": "Terry", "winner_score": 55, "loser": "Jim Hill", "loser_score":  6},
            {"date": "2025-10-24", "winner": "West Jones", "winner_score": 41, "loser": "Forest Hill", "loser_score":  0},
            {"date": "2025-10-31", "winner": "Hattiesburg", "winner_score": 41, "loser": "West Jones", "loser_score": 20},
            {"date": "2025-10-31", "winner": "Jim Hill", "winner_score": 12, "loser": "Forest Hill", "loser_score":  6},
            {"date": "2025-10-31", "winner": "Terry", "winner_score": 27, "loser": "George County", "loser_score": 20},
            {"date": "2025-11-06", "winner": "Forest Hill", "winner_score": 32, "loser": "George County", "loser_score": 25},
            {"date": "2025-11-06", "winner": "Hattiesburg", "winner_score": 48, "loser": "Terry", "loser_score": 21},
            {"date": "2025-11-06", "winner": "West Jones", "winner_score": 50, "loser": "Jim Hill", "loser_score":  0},
        ],
        "seeds": {1: "Hattiesburg", 2: "West Jones", 3: "Terry", 4: "George County"},
        "eliminated": {"Forest Hill", "Jim Hill"},
    },

    (6, 4): {
        "games": [
            {"date": "2025-10-10", "winner": "Gautier", "winner_score": 28, "loser": "Long Beach", "loser_score":  6},
            {"date": "2025-10-10", "winner": "Hancock", "winner_score": 41, "loser": "Pearl River Central", "loser_score": 21},
            {"date": "2025-10-10", "winner": "Picayune", "winner_score": 38, "loser": "Pascagoula", "loser_score": 36},
            {"date": "2025-10-17", "winner": "Pascagoula", "winner_score": 47, "loser": "Long Beach", "loser_score": 14},
            {"date": "2025-10-17", "winner": "Pearl River Central", "winner_score": 17, "loser": "Gautier", "loser_score": 14},
            {"date": "2025-10-17", "winner": "Picayune", "winner_score": 59, "loser": "Hancock", "loser_score": 28},
            {"date": "2025-10-24", "winner": "Hancock", "winner_score": 28, "loser": "Gautier", "loser_score": 27},
            {"date": "2025-10-24", "winner": "Pascagoula", "winner_score": 42, "loser": "Pearl River Central", "loser_score":  0},
            {"date": "2025-10-24", "winner": "Picayune", "winner_score": 42, "loser": "Long Beach", "loser_score":  7},
            {"date": "2025-10-31", "winner": "Pascagoula", "winner_score": 35, "loser": "Hancock", "loser_score":  0},
            {"date": "2025-10-31", "winner": "Pearl River Central", "winner_score": 49, "loser": "Long Beach", "loser_score": 21},
            {"date": "2025-10-31", "winner": "Picayune", "winner_score": 35, "loser": "Gautier", "loser_score": 31},
            {"date": "2025-11-06", "winner": "Hancock", "winner_score": 41, "loser": "Long Beach", "loser_score": 13},
            {"date": "2025-11-06", "winner": "Pascagoula", "winner_score": 49, "loser": "Gautier", "loser_score": 12},
            {"date": "2025-11-06", "winner": "Pearl River Central", "winner_score": 28, "loser": "Picayune", "loser_score": 21},
        ],
        "seeds": {1: "Picayune", 2: "Pascagoula", 3: "Hancock", 4: "Pearl River Central"},
        "eliminated": {"Gautier", "Long Beach"},
    },

    # -----------------------------------------------------------------------
    # 5A
    # -----------------------------------------------------------------------

    (5, 1): {
        "games": [
            {"date": "2025-10-10", "winner": "Caledonia", "winner_score": 34, "loser": "Columbus", "loser_score": 14},
            {"date": "2025-10-10", "winner": "New Hope", "winner_score": 42, "loser": "Lafayette", "loser_score": 27},
            {"date": "2025-10-10", "winner": "West Point", "winner_score": 50, "loser": "Pontotoc", "loser_score": 13},
            {"date": "2025-10-16", "winner": "New Hope", "winner_score": 42, "loser": "Columbus", "loser_score": 13},
            {"date": "2025-10-16", "winner": "Pontotoc", "winner_score": 26, "loser": "Caledonia", "loser_score": 13},
            {"date": "2025-10-17", "winner": "West Point", "winner_score": 41, "loser": "Lafayette", "loser_score":  6},
            {"date": "2025-10-24", "winner": "Lafayette", "winner_score": 27, "loser": "Columbus", "loser_score": 14},
            {"date": "2025-10-24", "winner": "New Hope", "winner_score": 20, "loser": "Pontotoc", "loser_score":  0},
            {"date": "2025-10-24", "winner": "West Point", "winner_score": 51, "loser": "Caledonia", "loser_score":  7},
            {"date": "2025-10-31", "winner": "Lafayette", "winner_score": 42, "loser": "Caledonia", "loser_score": 17},
            {"date": "2025-10-31", "winner": "Pontotoc", "winner_score": 27, "loser": "Columbus", "loser_score": 20},
            {"date": "2025-10-31", "winner": "West Point", "winner_score": 38, "loser": "New Hope", "loser_score":  7},
            {"date": "2025-11-06", "winner": "New Hope", "winner_score": 55, "loser": "Caledonia", "loser_score": 22},
            {"date": "2025-11-06", "winner": "Pontotoc", "winner_score": 41, "loser": "Lafayette", "loser_score": 21},
            {"date": "2025-11-06", "winner": "West Point", "winner_score": 49, "loser": "Columbus", "loser_score":  0},
        ],
        "seeds": {1: "West Point", 2: "New Hope", 3: "Pontotoc", 4: "Lafayette"},
        "eliminated": {"Caledonia", "Columbus"},
    },

    (5, 2): {
        "games": [
            {"date": "2025-10-03", "winner": "Vicksburg", "winner_score": 39, "loser": "Florence", "loser_score": 35},
            {"date": "2025-10-09", "winner": "Cleveland Central", "winner_score": 48, "loser": "Holmes County Central", "loser_score": 34},
            {"date": "2025-10-10", "winner": "Lanier", "winner_score": 30, "loser": "Provine", "loser_score":  8},
            {"date": "2025-10-16", "winner": "Lanier", "winner_score": 38, "loser": "Holmes County Central", "loser_score": 22},
            {"date": "2025-10-17", "winner": "Florence", "winner_score": 21, "loser": "Cleveland Central", "loser_score": 18},
            {"date": "2025-10-17", "winner": "Vicksburg", "winner_score": 55, "loser": "Provine", "loser_score":  6},
            {"date": "2025-10-24", "winner": "Cleveland Central", "winner_score": 34, "loser": "Vicksburg", "loser_score": 10},
            {"date": "2025-10-24", "winner": "Holmes County Central", "winner_score": 42, "loser": "Provine", "loser_score":  0},
            {"date": "2025-10-24", "winner": "Lanier", "winner_score": 34, "loser": "Florence", "loser_score": 28},
            {"date": "2025-10-30", "winner": "Cleveland Central", "winner_score": 22, "loser": "Lanier", "loser_score": 12},
            {"date": "2025-10-31", "winner": "Florence", "winner_score": 35, "loser": "Provine", "loser_score":  8},
            {"date": "2025-10-31", "winner": "Holmes County Central", "winner_score": 22, "loser": "Vicksburg", "loser_score": 16},
            {"date": "2025-11-06", "winner": "Cleveland Central", "winner_score": 49, "loser": "Provine", "loser_score":  8},
            {"date": "2025-11-06", "winner": "Holmes County Central", "winner_score": 56, "loser": "Florence", "loser_score": 14},
            {"date": "2025-11-06", "winner": "Lanier", "winner_score": 32, "loser": "Vicksburg", "loser_score":  8},
        ],
        "seeds": {1: "Cleveland Central", 2: "Lanier", 3: "Holmes County Central", 4: "Vicksburg"},
        "eliminated": {"Florence", "Provine"},
    },

    (5, 3): {
        "games": [
            {"date": "2025-10-10", "winner": "Brookhaven", "winner_score": 14, "loser": "Laurel", "loser_score":  6},
            {"date": "2025-10-10", "winner": "Natchez", "winner_score": 44, "loser": "North Pike", "loser_score": 14},
            {"date": "2025-10-10", "winner": "South Jones", "winner_score":  6, "loser": "Sumrall", "loser_score":  0},
            {"date": "2025-10-17", "winner": "Brookhaven", "winner_score": 21, "loser": "Sumrall", "loser_score":  9},
            {"date": "2025-10-17", "winner": "Laurel", "winner_score": 17, "loser": "Natchez", "loser_score": 12},
            {"date": "2025-10-17", "winner": "North Pike", "winner_score": 21, "loser": "South Jones", "loser_score":  5},
            {"date": "2025-10-24", "winner": "Brookhaven", "winner_score": 42, "loser": "South Jones", "loser_score": 24},
            {"date": "2025-10-24", "winner": "Laurel", "winner_score": 39, "loser": "North Pike", "loser_score":  0},
            {"date": "2025-10-24", "winner": "Sumrall", "winner_score": 33, "loser": "Natchez", "loser_score": 18},
            {"date": "2025-10-31", "winner": "Brookhaven", "winner_score": 41, "loser": "North Pike", "loser_score":  6},
            {"date": "2025-10-31", "winner": "Laurel", "winner_score": 14, "loser": "Sumrall", "loser_score": 10},
            {"date": "2025-10-31", "winner": "South Jones", "winner_score": 17, "loser": "Natchez", "loser_score":  0},
            {"date": "2025-11-06", "winner": "Brookhaven", "winner_score": 38, "loser": "Natchez", "loser_score":  0},
            {"date": "2025-11-06", "winner": "Laurel", "winner_score":  7, "loser": "South Jones", "loser_score":  3},
            {"date": "2025-11-06", "winner": "Sumrall", "winner_score": 24, "loser": "North Pike", "loser_score": 17},
        ],
        "seeds": {1: "Brookhaven", 2: "Laurel", 3: "South Jones", 4: "Sumrall"},
        "eliminated": {"Natchez", "North Pike"},
    },

    (5, 4): {
        "games": [
            {"date": "2025-10-10", "winner": "Purvis", "winner_score": 26, "loser": "East Central", "loser_score": 16},
            {"date": "2025-10-10", "winner": "Stone", "winner_score": 30, "loser": "Wayne County", "loser_score": 21},
            {"date": "2025-10-10", "winner": "Vancleave", "winner_score": 13, "loser": "Northeast Jones", "loser_score": 10},
            {"date": "2025-10-17", "winner": "Northeast Jones", "winner_score": 21, "loser": "East Central", "loser_score":  0},
            {"date": "2025-10-17", "winner": "Stone", "winner_score": 26, "loser": "Purvis", "loser_score":  0},
            {"date": "2025-10-17", "winner": "Wayne County", "winner_score": 41, "loser": "Vancleave", "loser_score": 30},
            {"date": "2025-10-24", "winner": "Purvis", "winner_score": 28, "loser": "Northeast Jones", "loser_score": 21},
            {"date": "2025-10-24", "winner": "Stone", "winner_score": 30, "loser": "Vancleave", "loser_score": 21},
            {"date": "2025-10-24", "winner": "Wayne County", "winner_score": 27, "loser": "East Central", "loser_score": 21},
            {"date": "2025-10-31", "winner": "East Central", "winner_score": 27, "loser": "Vancleave", "loser_score": 24},
            {"date": "2025-10-31", "winner": "Stone", "winner_score": 17, "loser": "Northeast Jones", "loser_score":  7},
            {"date": "2025-10-31", "winner": "Wayne County", "winner_score": 27, "loser": "Purvis", "loser_score": 17},
            {"date": "2025-11-06", "winner": "Northeast Jones", "winner_score": 14, "loser": "Wayne County", "loser_score":  7},
            {"date": "2025-11-06", "winner": "Purvis", "winner_score": 33, "loser": "Vancleave", "loser_score":  0},
            {"date": "2025-11-06", "winner": "Stone", "winner_score": 35, "loser": "East Central", "loser_score": 21},
        ],
        "seeds": {1: "Stone", 2: "Wayne County", 3: "Purvis", 4: "Northeast Jones"},
        "eliminated": {"East Central", "Vancleave"},
    },

    # -----------------------------------------------------------------------
    # 4A (8 regions)
    # -----------------------------------------------------------------------

    (4, 1): {
        "games": [
            {"date": "2025-10-03", "winner": "Corinth", "winner_score": 63, "loser": "South Pontotoc", "loser_score":  0},
            {"date": "2025-10-03", "winner": "North Pontotoc", "winner_score": 26, "loser": "New Albany", "loser_score": 22},
            {"date": "2025-10-10", "winner": "Corinth", "winner_score": 52, "loser": "North Pontotoc", "loser_score":  6},
            {"date": "2025-10-10", "winner": "Tishomingo County", "winner_score": 56, "loser": "South Pontotoc", "loser_score": 21},
            {"date": "2025-10-17", "winner": "Corinth", "winner_score": 56, "loser": "Tishomingo County", "loser_score":  0},
            {"date": "2025-10-17", "winner": "New Albany", "winner_score": 42, "loser": "South Pontotoc", "loser_score":  0},
            {"date": "2025-10-24", "winner": "New Albany", "winner_score": 52, "loser": "Tishomingo County", "loser_score": 21},
            {"date": "2025-10-24", "winner": "North Pontotoc", "winner_score": 63, "loser": "South Pontotoc", "loser_score": 22},
            {"date": "2025-10-30", "winner": "Corinth", "winner_score": 26, "loser": "New Albany", "loser_score": 24},
            {"date": "2025-10-31", "winner": "North Pontotoc", "winner_score": 55, "loser": "Tishomingo County", "loser_score": 34},
        ],
        "seeds": {1: "Corinth",          2: "North Pontotoc", 3: "New Albany",    4: "Tishomingo County"},
        "eliminated": {"South Pontotoc"},
    },
    (4, 2): {
        "games": [
            {"date": "2025-10-03", "winner": "Houston", "winner_score": 40, "loser": "Amory", "loser_score": 33},
            {"date": "2025-10-03", "winner": "Itawamba Agricultural", "winner_score": 41, "loser": "Mooreville", "loser_score": 10},
            {"date": "2025-10-09", "winner": "Amory", "winner_score": 27, "loser": "Mooreville", "loser_score": 24},
            {"date": "2025-10-10", "winner": "Shannon", "winner_score": 14, "loser": "Houston", "loser_score":  6},
            {"date": "2025-10-17", "winner": "Itawamba Agricultural", "winner_score": 35, "loser": "Houston", "loser_score": 14},
            {"date": "2025-10-17", "winner": "Shannon", "winner_score": 44, "loser": "Amory", "loser_score":  7},
            {"date": "2025-10-24", "winner": "Houston", "winner_score": 56, "loser": "Mooreville", "loser_score": 22},
            {"date": "2025-10-24", "winner": "Itawamba Agricultural", "winner_score": 25, "loser": "Shannon", "loser_score": 18},
            {"date": "2025-10-30", "winner": "Shannon", "winner_score": 52, "loser": "Mooreville", "loser_score":  6},
            {"date": "2025-10-31", "winner": "Itawamba Agricultural", "winner_score": 48, "loser": "Amory", "loser_score": 27},
        ],
        "seeds": {1: "Itawamba Agricultural", 2: "Shannon",    3: "Houston",      4: "Amory"},
        "eliminated": {"Mooreville"},
    },
    (4, 3): {
        "games": [
            {"date": "2025-10-02", "winner": "Senatobia", "winner_score": 39, "loser": "Byhalia", "loser_score":  6},
            {"date": "2025-10-03", "winner": "Clarksdale", "winner_score": 43, "loser": "Ripley", "loser_score": 14},
            {"date": "2025-10-09", "winner": "Rosa Fort", "winner_score": 54, "loser": "Byhalia", "loser_score": 14},
            {"date": "2025-10-10", "winner": "Clarksdale", "winner_score": 16, "loser": "Senatobia", "loser_score":  7},
            {"date": "2025-10-17", "winner": "Ripley", "winner_score": 34, "loser": "Byhalia", "loser_score":  0},
            {"date": "2025-10-17", "winner": "Senatobia", "winner_score": 43, "loser": "Rosa Fort", "loser_score":  6},
            {"date": "2025-10-24", "winner": "Clarksdale", "winner_score": 42, "loser": "Byhalia", "loser_score":  6},
            {"date": "2025-10-24", "winner": "Rosa Fort", "winner_score": 52, "loser": "Ripley", "loser_score": 13},
            {"date": "2025-10-30", "winner": "Clarksdale", "winner_score": 32, "loser": "Rosa Fort", "loser_score": 30},
            {"date": "2025-10-30", "winner": "Senatobia", "winner_score": 35, "loser": "Ripley", "loser_score":  7},
        ],
        "seeds": {1: "Clarksdale",       2: "Senatobia",      3: "Rosa Fort",    4: "Ripley"},
        "eliminated": {"Byhalia"},
    },
    (4, 4): {
        "games": [
            {"date": "2025-10-03", "winner": "Kosciusko", "winner_score": 45, "loser": "Gentry", "loser_score":  8},
            {"date": "2025-10-03", "winner": "Louisville", "winner_score": 42, "loser": "Yazoo City", "loser_score":  8},
            {"date": "2025-10-10", "winner": "Greenwood", "winner_score": 15, "loser": "Yazoo City", "loser_score":  6},
            {"date": "2025-10-10", "winner": "Louisville", "winner_score": 29, "loser": "Kosciusko", "loser_score": 24},
            {"date": "2025-10-17", "winner": "Kosciusko", "winner_score": 28, "loser": "Greenwood", "loser_score":  7},
            {"date": "2025-10-17", "winner": "Louisville", "winner_score": 44, "loser": "Gentry", "loser_score":  6},
            {"date": "2025-10-24", "winner": "Greenwood", "winner_score": 32, "loser": "Gentry", "loser_score": 10},
            {"date": "2025-10-24", "winner": "Kosciusko", "winner_score": 46, "loser": "Yazoo City", "loser_score":  0},
            {"date": "2025-10-30", "winner": "Yazoo City", "winner_score": 32, "loser": "Gentry", "loser_score":  0},
            {"date": "2025-10-31", "winner": "Louisville", "winner_score": 37, "loser": "Greenwood", "loser_score":  6},
        ],
        "seeds": {1: "Louisville",       2: "Kosciusko",      3: "Greenwood",    4: "Yazoo City"},
        "eliminated": {"Gentry"},
    },
    (4, 5): {
        "games": [
            {"date": "2025-10-03", "winner": "Leake Central", "winner_score": 60, "loser": "Choctaw Central", "loser_score": 27},
            {"date": "2025-10-03", "winner": "Newton County", "winner_score": 39, "loser": "Northeast Lauderdale", "loser_score":  6},
            {"date": "2025-10-10", "winner": "Choctaw Central", "winner_score": 21, "loser": "Northeast Lauderdale", "loser_score": 20},
            {"date": "2025-10-10", "winner": "Newton County", "winner_score": 22, "loser": "West Lauderdale", "loser_score": 16},
            {"date": "2025-10-17", "winner": "Leake Central", "winner_score": 48, "loser": "West Lauderdale", "loser_score": 28},
            {"date": "2025-10-17", "winner": "Newton County", "winner_score": 42, "loser": "Choctaw Central", "loser_score":  7},
            {"date": "2025-10-24", "winner": "Leake Central", "winner_score": 25, "loser": "Newton County", "loser_score": 22},
            {"date": "2025-10-24", "winner": "West Lauderdale", "winner_score": 35, "loser": "Northeast Lauderdale", "loser_score": 13},
            {"date": "2025-10-30", "winner": "Leake Central", "winner_score": 41, "loser": "Northeast Lauderdale", "loser_score":  6},
            {"date": "2025-10-30", "winner": "West Lauderdale", "winner_score": 46, "loser": "Choctaw Central", "loser_score": 21},
        ],
        "seeds": {1: "Leake Central",    2: "Newton County",  3: "West Lauderdale", 4: "Choctaw Central"},
        "eliminated": {"Northeast Lauderdale"},
    },
    (4, 6): {
        "games": [
            {"date": "2025-10-03", "winner": "Forest", "winner_score": 37, "loser": "Mendenhall", "loser_score": 26},
            {"date": "2025-10-03", "winner": "Morton", "winner_score": 51, "loser": "Richland", "loser_score":  7},
            {"date": "2025-10-10", "winner": "Morton", "winner_score": 14, "loser": "Mendenhall", "loser_score":  7},
            {"date": "2025-10-10", "winner": "Richland", "winner_score": 36, "loser": "Raymond", "loser_score":  0},
            {"date": "2025-10-17", "winner": "Forest", "winner_score": 28, "loser": "Raymond", "loser_score":  6},
            {"date": "2025-10-17", "winner": "Mendenhall", "winner_score": 49, "loser": "Richland", "loser_score": 13},
            {"date": "2025-10-23", "winner": "Morton", "winner_score": 73, "loser": "Raymond", "loser_score": 28},
            {"date": "2025-10-24", "winner": "Forest", "winner_score": 41, "loser": "Richland", "loser_score":  3},
            {"date": "2025-10-30", "winner": "Forest", "winner_score": 20, "loser": "Morton", "loser_score": 14},
            {"date": "2025-10-30", "winner": "Mendenhall", "winner_score": 32, "loser": "Raymond", "loser_score":  0},
        ],
        "seeds": {1: "Forest",           2: "Morton",         3: "Mendenhall",   4: "Richland"},
        "eliminated": {"Raymond"},
    },
    (4, 7): {
        "games": [
            {"date": "2025-10-03", "winner": "Columbia", "winner_score": 48, "loser": "Lawrence County", "loser_score":  0},
            {"date": "2025-10-03", "winner": "McComb", "winner_score": 35, "loser": "Poplarville", "loser_score": 34},
            {"date": "2025-10-10", "winner": "Columbia", "winner_score": 38, "loser": "McComb", "loser_score": 14},
            {"date": "2025-10-10", "winner": "South Pike", "winner_score": 42, "loser": "Lawrence County", "loser_score":  7},
            {"date": "2025-10-17", "winner": "McComb", "winner_score": 42, "loser": "Lawrence County", "loser_score":  7},
            {"date": "2025-10-17", "winner": "Poplarville", "winner_score": 62, "loser": "South Pike", "loser_score": 24},
            {"date": "2025-10-24", "winner": "Columbia", "winner_score": 49, "loser": "South Pike", "loser_score": 36},
            {"date": "2025-10-24", "winner": "Poplarville", "winner_score": 48, "loser": "Lawrence County", "loser_score":  7},
            {"date": "2025-10-30", "winner": "Columbia", "winner_score": 49, "loser": "Poplarville", "loser_score": 28},
            {"date": "2025-10-31", "winner": "McComb", "winner_score": 41, "loser": "South Pike", "loser_score": 12},
        ],
        "seeds": {1: "Columbia",         2: "McComb",         3: "Poplarville",  4: "South Pike"},
        "eliminated": {"Lawrence County"},
    },
    (4, 8): {
        "games": [
            {"date": "2025-10-03", "winner": "Forrest County Agricultural", "winner_score":  6, "loser": "Moss Point", "loser_score":  0},
            {"date": "2025-10-03", "winner": "Pass Christian", "winner_score": 28, "loser": "Greene County", "loser_score": 14},
            {"date": "2025-10-10", "winner": "Moss Point", "winner_score": 14, "loser": "Bay", "loser_score": 13},
            {"date": "2025-10-10", "winner": "Pass Christian", "winner_score": 36, "loser": "Forrest County Agricultural", "loser_score":  8},
            {"date": "2025-10-17", "winner": "Greene County", "winner_score": 42, "loser": "Bay", "loser_score":  0},
            {"date": "2025-10-17", "winner": "Pass Christian", "winner_score": 49, "loser": "Moss Point", "loser_score":  0},
            {"date": "2025-10-24", "winner": "Forrest County Agricultural", "winner_score": 34, "loser": "Bay", "loser_score":  0},
            {"date": "2025-10-24", "winner": "Greene County", "winner_score": 35, "loser": "Moss Point", "loser_score":  6},
            {"date": "2025-10-30", "winner": "Forrest County Agricultural", "winner_score": 21, "loser": "Greene County", "loser_score": 14},
            {"date": "2025-10-30", "winner": "Pass Christian", "winner_score": 48, "loser": "Bay", "loser_score":  0},
        ],
        "seeds": {1: "Pass Christian",   2: "Forrest County Agricultural", 3: "Greene County", 4: "Moss Point"},
        "eliminated": {"Bay"},
    },

    # -----------------------------------------------------------------------
    # 3A (8 regions)
    # -----------------------------------------------------------------------

    (3, 1): {
        "games": [
            {"date": "2025-10-03", "winner": "Belmont", "winner_score": 22, "loser": "Alcorn Central", "loser_score":  6},
            {"date": "2025-10-03", "winner": "Kossuth", "winner_score": 37, "loser": "Booneville", "loser_score": 10},
            {"date": "2025-10-10", "winner": "Alcorn Central", "winner_score": 20, "loser": "Mantachie", "loser_score": 14},
            {"date": "2025-10-10", "winner": "Booneville", "winner_score": 32, "loser": "Belmont", "loser_score": 14},
            {"date": "2025-10-17", "winner": "Booneville", "winner_score": 35, "loser": "Mantachie", "loser_score": 28},
            {"date": "2025-10-17", "winner": "Kossuth", "winner_score": 40, "loser": "Belmont", "loser_score": 28},
            {"date": "2025-10-23", "winner": "Booneville", "winner_score": 42, "loser": "Alcorn Central", "loser_score": 28},
            {"date": "2025-10-24", "winner": "Kossuth", "winner_score": 47, "loser": "Mantachie", "loser_score":  7},
            {"date": "2025-10-30", "winner": "Belmont", "winner_score": 36, "loser": "Mantachie", "loser_score": 13},
            {"date": "2025-10-30", "winner": "Kossuth", "winner_score": 49, "loser": "Alcorn Central", "loser_score": 15},
        ],
        "seeds": {1: "Kossuth",         2: "Booneville",           3: "Belmont",             4: "Alcorn Central"},
        "eliminated": {"Mantachie"},
    },
    (3, 2): {
        "games": [
            {"date": "2025-10-03", "winner": "Independence", "winner_score": 47, "loser": "Holly Springs", "loser_score":  6},
            {"date": "2025-10-10", "winner": "Coahoma County", "winner_score": 36, "loser": "North Panola", "loser_score": 12},
            {"date": "2025-10-17", "winner": "North Panola", "winner_score": 20, "loser": "Independence", "loser_score": 14},
            {"date": "2025-10-24", "winner": "Coahoma County", "winner_score": 52, "loser": "Holly Springs", "loser_score":  6},
            {"date": "2025-10-30", "winner": "Coahoma County", "winner_score": 30, "loser": "Independence", "loser_score":  0},
            {"date": "2025-10-30", "winner": "North Panola", "winner_score": 34, "loser": "Holly Springs", "loser_score": 14},
        ],
        "seeds": {1: "Coahoma County",  2: "North Panola",          3: "Independence",        4: "Holly Springs"},
        "eliminated": set(),
    },
    (3, 3): {
        "games": [
            {"date": "2025-10-03", "winner": "Humphreys County", "winner_score": 32, "loser": "Amanda Elzy", "loser_score":  8},
            {"date": "2025-10-03", "winner": "Thomas E. Edwards", "winner_score": 20, "loser": "O'Bannon", "loser_score":  8},
            {"date": "2025-10-09", "winner": "Thomas E. Edwards", "winner_score": 20, "loser": "Amanda Elzy", "loser_score":  0},
            {"date": "2025-10-10", "winner": "Yazoo County", "winner_score": 17, "loser": "O'Bannon", "loser_score":  8},
            {"date": "2025-10-17", "winner": "Humphreys County", "winner_score": 24, "loser": "Thomas E. Edwards", "loser_score": 16},
            {"date": "2025-10-17", "winner": "Yazoo County", "winner_score": 21, "loser": "Amanda Elzy", "loser_score": 18},
            {"date": "2025-10-24", "winner": "Humphreys County", "winner_score": 14, "loser": "Yazoo County", "loser_score": 12},
            {"date": "2025-10-24", "winner": "O'Bannon", "winner_score": 50, "loser": "Amanda Elzy", "loser_score": 26},
            {"date": "2025-10-30", "winner": "Humphreys County", "winner_score": 22, "loser": "O'Bannon", "loser_score": 20},
            {"date": "2025-10-31", "winner": "Thomas E. Edwards", "winner_score": 22, "loser": "Yazoo County", "loser_score": 15},
        ],
        "seeds": {1: "Humphreys County", 2: "Thomas E. Edwards",               3: "Yazoo County",        4: "O'Bannon"},
        "eliminated": {"Amanda Elzy"},
    },
    (3, 4): {
        "games": [
            {"date": "2025-10-03", "winner": "Aberdeen", "winner_score": 44, "loser": "Winona", "loser_score": 36},
            {"date": "2025-10-03", "winner": "Choctaw County", "winner_score": 48, "loser": "Nettleton", "loser_score":  6},
            {"date": "2025-10-10", "winner": "Choctaw County", "winner_score": 43, "loser": "Aberdeen", "loser_score":  8},
            {"date": "2025-10-10", "winner": "Winona", "winner_score": 31, "loser": "Noxubee County", "loser_score": 26},
            {"date": "2025-10-17", "winner": "Aberdeen", "winner_score": 58, "loser": "Nettleton", "loser_score": 12},
            {"date": "2025-10-17", "winner": "Noxubee County", "winner_score":  8, "loser": "Choctaw County", "loser_score":  7},
            {"date": "2025-10-24", "winner": "Noxubee County", "winner_score": 46, "loser": "Nettleton", "loser_score": 13},
            {"date": "2025-10-24", "winner": "Winona", "winner_score": 24, "loser": "Choctaw County", "loser_score": 21},
            {"date": "2025-10-30", "winner": "Noxubee County", "winner_score": 48, "loser": "Aberdeen", "loser_score": 26},
            {"date": "2025-10-30", "winner": "Winona", "winner_score": 42, "loser": "Nettleton", "loser_score": 14},
        ],
        "seeds": {1: "Winona",          2: "Noxubee County",        3: "Choctaw County",      4: "Aberdeen"},
        "eliminated": {"Nettleton"},
    },
    (3, 5): {
        "games": [
            {"date": "2025-10-03", "winner": "Southeast Lauderdale", "winner_score": 14, "loser": "Pisgah", "loser_score":  7},
            {"date": "2025-10-03", "winner": "Union", "winner_score": 21, "loser": "Quitman", "loser_score": 15},
            {"date": "2025-10-09", "winner": "Quitman", "winner_score": 50, "loser": "Pisgah", "loser_score":  2},
            {"date": "2025-10-10", "winner": "Southeast Lauderdale", "winner_score": 26, "loser": "St. Andrew's", "loser_score": 15},
            {"date": "2025-10-17", "winner": "Pisgah", "winner_score": 28, "loser": "St. Andrew's", "loser_score":  6},
            {"date": "2025-10-17", "winner": "Union", "winner_score": 43, "loser": "Southeast Lauderdale", "loser_score":  6},
            {"date": "2025-10-24", "winner": "Quitman", "winner_score": 35, "loser": "Southeast Lauderdale", "loser_score":  0},
            {"date": "2025-10-24", "winner": "Union", "winner_score": 42, "loser": "St. Andrew's", "loser_score":  7},
            {"date": "2025-10-30", "winner": "Union", "winner_score": 35, "loser": "Pisgah", "loser_score":  6},
            {"date": "2025-10-31", "winner": "Quitman", "winner_score": 42, "loser": "St. Andrew's", "loser_score":  8},
        ],
        "seeds": {1: "Union",           2: "Quitman",               3: "Southeast Lauderdale",4: "Pisgah"},
        "eliminated": {"St. Andrew's"},
    },
    (3, 6): {
        "games": [
            {"date": "2025-10-03", "winner": "Magee", "winner_score": 36, "loser": "Jefferson Davis County", "loser_score": 35},
            {"date": "2025-10-03", "winner": "Raleigh", "winner_score": 56, "loser": "McLaurin", "loser_score":  0},
            {"date": "2025-10-10", "winner": "Magee", "winner_score": 47, "loser": "McLaurin", "loser_score":  8},
            {"date": "2025-10-10", "winner": "Seminary", "winner_score": 20, "loser": "Jefferson Davis County", "loser_score":  0},
            {"date": "2025-10-17", "winner": "Raleigh", "winner_score": 35, "loser": "Magee", "loser_score":  6},
            {"date": "2025-10-17", "winner": "Seminary", "winner_score": 61, "loser": "McLaurin", "loser_score":  0},
            {"date": "2025-10-24", "winner": "Jefferson Davis County", "winner_score": 47, "loser": "McLaurin", "loser_score":  3},
            {"date": "2025-10-24", "winner": "Raleigh", "winner_score": 27, "loser": "Seminary", "loser_score": 21},
            {"date": "2025-10-30", "winner": "Raleigh", "winner_score": 40, "loser": "Jefferson Davis County", "loser_score": 22},
            {"date": "2025-10-30", "winner": "Seminary", "winner_score": 30, "loser": "Magee", "loser_score": 27},
        ],
        "seeds": {1: "Raleigh",         2: "Seminary",              3: "Magee",               4: "Jefferson Davis County"},
        "eliminated": {"McLaurin"},
    },
    (3, 7): {
        "games": [
            {"date": "2025-10-03", "winner": "Franklin County", "winner_score": 42, "loser": "Crystal Springs", "loser_score":  6},
            {"date": "2025-10-03", "winner": "Hazlehurst", "winner_score": 44, "loser": "Port Gibson", "loser_score": 20},
            {"date": "2025-10-10", "winner": "Franklin County", "winner_score": 49, "loser": "Port Gibson", "loser_score": 20},
            {"date": "2025-10-10", "winner": "Jefferson County", "winner_score": 42, "loser": "Crystal Springs", "loser_score":  0},
            {"date": "2025-10-17", "winner": "Franklin County", "winner_score": 24, "loser": "Hazlehurst", "loser_score": 21},
            {"date": "2025-10-17", "winner": "Jefferson County", "winner_score": 18, "loser": "Port Gibson", "loser_score": 16},
            {"date": "2025-10-24", "winner": "Hazlehurst", "winner_score": 35, "loser": "Jefferson County", "loser_score":  6},
            {"date": "2025-10-24", "winner": "Port Gibson", "winner_score": 46, "loser": "Crystal Springs", "loser_score":  0},
            {"date": "2025-10-30", "winner": "Franklin County", "winner_score": 14, "loser": "Jefferson County", "loser_score":  6},
            {"date": "2025-10-30", "winner": "Hazlehurst", "winner_score": 45, "loser": "Crystal Springs", "loser_score":  0},
        ],
        "seeds": {1: "Franklin County", 2: "Hazlehurst",            3: "Jefferson County",    4: "Port Gibson"},
        "eliminated": {"Crystal Springs"},
    },
    (3, 8): {
        "games": [
            {"date": "2025-10-03", "winner": "Presbyterian Christian", "winner_score": 36, "loser": "St. Patrick", "loser_score":  0},
            {"date": "2025-10-03", "winner": "West Marion", "winner_score": 35, "loser": "Tylertown", "loser_score": 34},
            {"date": "2025-10-10", "winner": "Tylertown", "winner_score": 32, "loser": "St. Stanislaus", "loser_score":  0},
            {"date": "2025-10-10", "winner": "West Marion", "winner_score": 49, "loser": "St. Patrick", "loser_score":  7},
            {"date": "2025-10-17", "winner": "St. Patrick", "winner_score": 38, "loser": "St. Stanislaus", "loser_score": 21},
            {"date": "2025-10-17", "winner": "West Marion", "winner_score": 33, "loser": "Presbyterian Christian", "loser_score": 21},
            {"date": "2025-10-24", "winner": "Presbyterian Christian", "winner_score": 42, "loser": "St. Stanislaus", "loser_score":  7},
            {"date": "2025-10-24", "winner": "Tylertown", "winner_score": 42, "loser": "St. Patrick", "loser_score":  7},
            {"date": "2025-10-30", "winner": "West Marion", "winner_score": 47, "loser": "St. Stanislaus", "loser_score": 14},
            {"date": "2025-10-31", "winner": "Presbyterian Christian", "winner_score": 33, "loser": "Tylertown", "loser_score": 14},
        ],
        "seeds": {1: "West Marion",     2: "Presbyterian Christian",3: "Tylertown",           4: "St. Patrick"},
        "eliminated": {"St. Stanislaus"},
    },

    # -----------------------------------------------------------------------
    # 2A (8 regions)
    # -----------------------------------------------------------------------

    (2, 1): {
        "games": [
            {"date": "2025-10-16", "winner": "Hamilton", "winner_score": 49, "loser": "Walnut", "loser_score": 22},
            {"date": "2025-10-17", "winner": "Baldwyn", "winner_score": 53, "loser": "Hatley", "loser_score": 18},
            {"date": "2025-10-24", "winner": "Baldwyn", "winner_score": 38, "loser": "Hamilton", "loser_score": 28},
            {"date": "2025-10-24", "winner": "Hatley", "winner_score": 22, "loser": "Walnut", "loser_score": 14},
            {"date": "2025-10-30", "winner": "Baldwyn", "winner_score": 36, "loser": "Walnut", "loser_score": 12},
            {"date": "2025-10-31", "winner": "Hamilton", "winner_score": 53, "loser": "Hatley", "loser_score": 52},
        ],
        "seeds": {1: "Baldwyn",      2: "Hamilton",    3: "Hatley",      4: "Walnut"},
        "eliminated": set(),
    },
    (2, 2): {
        "games": [
            {"date": "2025-10-03", "winner": "Myrtle", "winner_score": 35, "loser": "East Union", "loser_score":  6},
            {"date": "2025-10-03", "winner": "Water Valley", "winner_score": 34, "loser": "Bruce", "loser_score": 20},
            {"date": "2025-10-09", "winner": "East Union", "winner_score": 40, "loser": "Bruce", "loser_score": 34},
            {"date": "2025-10-09", "winner": "Myrtle", "winner_score": 48, "loser": "Strayhorn", "loser_score":  0},
            {"date": "2025-10-17", "winner": "Strayhorn", "winner_score": 40, "loser": "East Union", "loser_score": 36},
            {"date": "2025-10-17", "winner": "Water Valley", "winner_score": 21, "loser": "Myrtle", "loser_score": 20},
            {"date": "2025-10-24", "winner": "Myrtle", "winner_score": 36, "loser": "Bruce", "loser_score": 20},
            {"date": "2025-10-24", "winner": "Water Valley", "winner_score": 42, "loser": "Strayhorn", "loser_score": 28},
            {"date": "2025-10-30", "winner": "Strayhorn", "winner_score": 32, "loser": "Bruce", "loser_score": 28},
            {"date": "2025-10-30", "winner": "Water Valley", "winner_score": 32, "loser": "East Union", "loser_score": 22},
        ],
        "seeds": {1: "Water Valley", 2: "Myrtle",      3: "Strayhorn",   4: "East Union"},
        "eliminated": {"Bruce"},
    },
    (2, 3): {
        "games": [
            {"date": "2025-10-03", "winner": "Leland", "winner_score": 36, "loser": "M. S. Palmer", "loser_score":  8},
            {"date": "2025-10-03", "winner": "Northside", "winner_score": 44, "loser": "J Z George", "loser_score":  0},
            {"date": "2025-10-10", "winner": "Charleston", "winner_score": 38, "loser": "Leland", "loser_score":  8},
            {"date": "2025-10-10", "winner": "Northside", "winner_score": 50, "loser": "M. S. Palmer", "loser_score":  0},
            {"date": "2025-10-17", "winner": "Charleston", "winner_score": 42, "loser": "J Z George", "loser_score": 12},
            {"date": "2025-10-17", "winner": "Northside", "winner_score": 46, "loser": "Leland", "loser_score":  0},
            {"date": "2025-10-24", "winner": "Charleston", "winner_score": 48, "loser": "Northside", "loser_score": 28},
            {"date": "2025-10-24", "winner": "J Z George", "winner_score":  8, "loser": "M. S. Palmer", "loser_score":  6},
            {"date": "2025-10-30", "winner": "Charleston", "winner_score": 48, "loser": "M. S. Palmer", "loser_score":  6},
            {"date": "2025-10-30", "winner": "J Z George", "winner_score": 10, "loser": "Leland", "loser_score":  6},
        ],
        "seeds": {1: "Charleston",   2: "Northside",   3: "J Z George",  4: "Leland"},
        "eliminated": {"M. S. Palmer"},
    },
    (2, 4): {
        "games": [
            {"date": "2025-10-03", "winner": "East Webster", "winner_score": 49, "loser": "Kemper County", "loser_score": 20},
            {"date": "2025-10-03", "winner": "Velma Jackson", "winner_score": 24, "loser": "Eupora", "loser_score": 20},
            {"date": "2025-10-09", "winner": "East Webster", "winner_score": 29, "loser": "Philadelphia", "loser_score":  6},
            {"date": "2025-10-10", "winner": "Kemper County", "winner_score": 34, "loser": "Velma Jackson", "loser_score": 16},
            {"date": "2025-10-17", "winner": "Kemper County", "winner_score": 70, "loser": "Eupora", "loser_score": 44},
            {"date": "2025-10-17", "winner": "Velma Jackson", "winner_score":  8, "loser": "Philadelphia", "loser_score":  6},
            {"date": "2025-10-24", "winner": "East Webster", "winner_score": 35, "loser": "Velma Jackson", "loser_score":  0},
            {"date": "2025-10-24", "winner": "Philadelphia", "winner_score": 26, "loser": "Eupora", "loser_score": 20},
            {"date": "2025-10-31", "winner": "East Webster", "winner_score": 26, "loser": "Eupora", "loser_score":  0},
            {"date": "2025-10-31", "winner": "Kemper County", "winner_score": 40, "loser": "Philadelphia", "loser_score":  6},
        ],
        "seeds": {1: "East Webster", 2: "Kemper County",3: "Velma Jackson",4: "Philadelphia"},
        "eliminated": {"Eupora"},
    },
    (2, 5): {
        "games": [
            {"date": "2025-10-03", "winner": "Lake", "winner_score": 38, "loser": "Newton", "loser_score": 14},
            {"date": "2025-10-03", "winner": "Scott Central", "winner_score": 49, "loser": "Puckett", "loser_score":  0},
            {"date": "2025-10-09", "winner": "Lake", "winner_score": 36, "loser": "Puckett", "loser_score":  0},
            {"date": "2025-10-09", "winner": "Pelahatchie", "winner_score": 48, "loser": "Newton", "loser_score": 32},
            {"date": "2025-10-16", "winner": "Lake", "winner_score": 32, "loser": "Pelahatchie", "loser_score": 24},
            {"date": "2025-10-17", "winner": "Scott Central", "winner_score": 42, "loser": "Newton", "loser_score":  6},
            {"date": "2025-10-24", "winner": "Newton", "winner_score": 42, "loser": "Puckett", "loser_score":  8},
            {"date": "2025-10-24", "winner": "Pelahatchie", "winner_score": 17, "loser": "Scott Central", "loser_score": 16},
            {"date": "2025-10-30", "winner": "Pelahatchie", "winner_score": 55, "loser": "Puckett", "loser_score":  0},
            {"date": "2025-10-30", "winner": "Scott Central", "winner_score": 35, "loser": "Lake", "loser_score": 28},
        ],
        "seeds": {1: "Scott Central",2: "Lake",        3: "Pelahatchie", 4: "Newton"},
        "eliminated": {"Puckett"},
    },
    (2, 6): {
        "games": [
            {"date": "2025-10-03", "winner": "Clarkdale", "winner_score": 12, "loser": "Bay Springs", "loser_score":  6},
            {"date": "2025-10-03", "winner": "Heidelberg", "winner_score": 58, "loser": "Enterprise Clarke", "loser_score":  0},
            {"date": "2025-10-10", "winner": "Bay Springs", "winner_score": 34, "loser": "Enterprise Clarke", "loser_score":  7},
            {"date": "2025-10-10", "winner": "Heidelberg", "winner_score": 50, "loser": "Mize", "loser_score":  0},
            {"date": "2025-10-17", "winner": "Heidelberg", "winner_score": 12, "loser": "Bay Springs", "loser_score":  0},
            {"date": "2025-10-17", "winner": "Mize", "winner_score": 45, "loser": "Clarkdale", "loser_score":  0},
            {"date": "2025-10-24", "winner": "Bay Springs", "winner_score": 28, "loser": "Mize", "loser_score": 17},
            {"date": "2025-10-24", "winner": "Clarkdale", "winner_score": 23, "loser": "Enterprise Clarke", "loser_score": 14},
            {"date": "2025-10-30", "winner": "Heidelberg", "winner_score": 60, "loser": "Clarkdale", "loser_score":  7},
            {"date": "2025-10-30", "winner": "Mize", "winner_score": 38, "loser": "Enterprise Clarke", "loser_score":  0},
        ],
        "seeds": {1: "Heidelberg",   2: "Bay Springs", 3: "Mize",        4: "Clarkdale"},
        "eliminated": {"Enterprise Clarke"},
    },
    (2, 7): {
        "games": [
            {"date": "2025-10-03", "winner": "Loyd Star", "winner_score": 29, "loser": "Wilkinson County", "loser_score": 18},
            {"date": "2025-10-03", "winner": "Wesson", "winner_score": 48, "loser": "Enterprise Lincoln", "loser_score":  6},
            {"date": "2025-10-10", "winner": "Amite County", "winner_score": 20, "loser": "Wilkinson County", "loser_score":  8},
            {"date": "2025-10-10", "winner": "Wesson", "winner_score": 49, "loser": "Loyd Star", "loser_score": 41},
            {"date": "2025-10-17", "winner": "Loyd Star", "winner_score": 50, "loser": "Enterprise Lincoln", "loser_score": 12},
            {"date": "2025-10-17", "winner": "Wesson", "winner_score": 49, "loser": "Amite County", "loser_score": 26},
            {"date": "2025-10-24", "winner": "Amite County", "winner_score": 46, "loser": "Enterprise Lincoln", "loser_score":  6},
            {"date": "2025-10-24", "winner": "Wesson", "winner_score": 48, "loser": "Wilkinson County", "loser_score":  0},
            {"date": "2025-10-30", "winner": "Amite County", "winner_score": 46, "loser": "Loyd Star", "loser_score": 21},
            {"date": "2025-10-30", "winner": "Wilkinson County", "winner_score": 46, "loser": "Enterprise Lincoln", "loser_score":  0},
        ],
        "seeds": {1: "Wesson",       2: "Amite County",3: "Loyd Star",   4: "Wilkinson County"},
        "eliminated": {"Enterprise Lincoln"},
    },
    (2, 8): {
        "games": [
            {"date": "2025-10-03", "winner": "East Marion", "winner_score": 36, "loser": "Sacred Heart", "loser_score": 14},
            {"date": "2025-10-03", "winner": "North Forrest", "winner_score": 30, "loser": "Collins", "loser_score": 20},
            {"date": "2025-10-10", "winner": "Collins", "winner_score": 42, "loser": "Perry Central", "loser_score": 34},
            {"date": "2025-10-10", "winner": "East Marion", "winner_score": 38, "loser": "North Forrest", "loser_score":  6},
            {"date": "2025-10-17", "winner": "North Forrest", "winner_score": 27, "loser": "Sacred Heart", "loser_score": 19},
            {"date": "2025-10-17", "winner": "Perry Central", "winner_score": 26, "loser": "East Marion", "loser_score":  6},
            {"date": "2025-10-24", "winner": "Collins", "winner_score": 40, "loser": "Sacred Heart", "loser_score": 34},
            {"date": "2025-10-24", "winner": "North Forrest", "winner_score": 35, "loser": "Perry Central", "loser_score": 24},
            {"date": "2025-10-30", "winner": "East Marion", "winner_score": 30, "loser": "Collins", "loser_score": 14},
            {"date": "2025-10-30", "winner": "Perry Central", "winner_score": 20, "loser": "Sacred Heart", "loser_score":  3},
        ],
        "seeds": {1: "East Marion",  2: "North Forrest",3: "Collins",    4: "Perry Central"},
        "eliminated": {"Sacred Heart"},
    },

    # -----------------------------------------------------------------------
    # 1A (8 regions)
    # -----------------------------------------------------------------------

    (1, 1): {
        "games": [
            {"date": "2025-10-17", "winner": "Biggersville", "winner_score": 38, "loser": "Tupelo Christian", "loser_score":  0},
            {"date": "2025-10-17", "winner": "Smithville", "winner_score": 43, "loser": "Thrasher", "loser_score":  0},
            {"date": "2025-10-23", "winner": "Tupelo Christian", "winner_score": 41, "loser": "Thrasher", "loser_score":  0},
            {"date": "2025-10-24", "winner": "Biggersville", "winner_score": 62, "loser": "Smithville", "loser_score": 13},
            {"date": "2025-10-30", "winner": "Biggersville", "winner_score": 49, "loser": "Thrasher", "loser_score":  8},
            {"date": "2025-10-30", "winner": "Tupelo Christian", "winner_score": 41, "loser": "Smithville", "loser_score":  0},
        ],
        "seeds": {1: "Biggersville",    2: "Tupelo Christian",      3: "Smithville",  4: "Thrasher"},
        "eliminated": set(),
    },
    (1, 2): {
        "games": [
            {"date": "2025-10-17", "winner": "Falkner", "winner_score": 36, "loser": "Ashland", "loser_score":  8},
            {"date": "2025-10-17", "winner": "H. W. Byers", "winner_score": 47, "loser": "Potts Camp", "loser_score": 32},
            {"date": "2025-10-23", "winner": "Falkner", "winner_score": 56, "loser": "H. W. Byers", "loser_score": 26},
            {"date": "2025-10-24", "winner": "Potts Camp", "winner_score": 38, "loser": "Ashland", "loser_score":  6},
            {"date": "2025-10-30", "winner": "Falkner", "winner_score": 50, "loser": "Potts Camp", "loser_score": 27},
            {"date": "2025-10-30", "winner": "H. W. Byers", "winner_score": 39, "loser": "Ashland", "loser_score":  0},
        ],
        "seeds": {1: "Falkner",         2: "H. W. Byers",                  3: "Potts Camp",  4: "Ashland"},
        "eliminated": set(),
    },
    (1, 3): {
        "games": [
            {"date": "2025-10-17", "winner": "Calhoun City", "winner_score": 46, "loser": "Okolona", "loser_score":  7},
            {"date": "2025-10-17", "winner": "West Lowndes", "winner_score": 34, "loser": "Vardaman", "loser_score": 14},
            {"date": "2025-10-24", "winner": "Calhoun City", "winner_score": 54, "loser": "Vardaman", "loser_score":  0},
            {"date": "2025-10-24", "winner": "West Lowndes", "winner_score": 50, "loser": "Okolona", "loser_score": 12},
            {"date": "2025-10-30", "winner": "Calhoun City", "winner_score": 40, "loser": "West Lowndes", "loser_score":  0},
            {"date": "2025-10-30", "winner": "Okolona", "winner_score": 34, "loser": "Vardaman", "loser_score": 26},
        ],
        "seeds": {1: "Calhoun City",    2: "West Lowndes",          3: "Okolona",     4: "Vardaman"},
        "eliminated": set(),
    },
    (1, 4): {
        "games": [
            {"date": "2025-10-17", "winner": "Leflore County", "winner_score": 44, "loser": "French Camp", "loser_score":  0},
            {"date": "2025-10-17", "winner": "West Tallahatchie", "winner_score": 36, "loser": "Coffeeville", "loser_score":  0},
            {"date": "2025-10-24", "winner": "Leflore County", "winner_score": 52, "loser": "Coffeeville", "loser_score":  0},
            {"date": "2025-10-24", "winner": "West Tallahatchie", "winner_score": 16, "loser": "French Camp", "loser_score":  7},
            {"date": "2025-10-30", "winner": "Coffeeville", "winner_score": 20, "loser": "French Camp", "loser_score":  7},
            {"date": "2025-10-30", "winner": "Leflore County", "winner_score": 34, "loser": "West Tallahatchie", "loser_score": 26},
        ],
        "seeds": {1: "Leflore County",  2: "West Tallahatchie",     3: "Coffeeville", 4: "French Camp"},
        "eliminated": set(),
    },
    (1, 5): {
        "games": [
            {"date": "2025-10-03", "winner": "Ethel", "winner_score": 28, "loser": "McAdams", "loser_score": 14},
            {"date": "2025-10-03", "winner": "Nanih Waiya", "winner_score": 20, "loser": "Leake County", "loser_score": 14},
            {"date": "2025-10-03", "winner": "Noxapater", "winner_score":  6, "loser": "Sebastopol", "loser_score":  0},
            {"date": "2025-10-09", "winner": "Nanih Waiya", "winner_score": 41, "loser": "Noxapater", "loser_score": 16},
            {"date": "2025-10-10", "winner": "Leake County", "winner_score": 28, "loser": "Ethel", "loser_score":  0},
            {"date": "2025-10-10", "winner": "Sebastopol", "winner_score": 28, "loser": "McAdams", "loser_score": 18},
            {"date": "2025-10-16", "winner": "Ethel", "winner_score": 30, "loser": "Noxapater", "loser_score": 26},
            {"date": "2025-10-17", "winner": "Leake County", "winner_score": 48, "loser": "McAdams", "loser_score":  6},
            {"date": "2025-10-17", "winner": "Nanih Waiya", "winner_score": 49, "loser": "Sebastopol", "loser_score": 14},
            {"date": "2025-10-24", "winner": "Leake County", "winner_score": 22, "loser": "Sebastopol", "loser_score":  0},
            {"date": "2025-10-24", "winner": "Nanih Waiya", "winner_score": 40, "loser": "Ethel", "loser_score": 16},
            {"date": "2025-10-24", "winner": "Noxapater", "winner_score": 46, "loser": "McAdams", "loser_score":  0},
            {"date": "2025-10-30", "winner": "Ethel", "winner_score": 32, "loser": "Sebastopol", "loser_score": 12},
            {"date": "2025-10-30", "winner": "Leake County", "winner_score": 30, "loser": "Noxapater", "loser_score":  8},
            {"date": "2025-10-30", "winner": "Nanih Waiya", "winner_score": 42, "loser": "McAdams", "loser_score": 12},
        ],
        "seeds": {1: "Nanih Waiya",     2: "Leake County",          3: "Ethel",       4: "Noxapater"},
        "eliminated": {"McAdams", "Sebastopol"},
    },
    (1, 6): {
        "games": [
            {"date": "2025-10-03", "winner": "South Delta", "winner_score": 30, "loser": "Shaw", "loser_score": 22},
            {"date": "2025-10-03", "winner": "West Bolivar", "winner_score": 38, "loser": "Riverside", "loser_score":  0},
            {"date": "2025-10-09", "winner": "Shaw", "winner_score": 12, "loser": "West Bolivar", "loser_score":  6},
            {"date": "2025-10-10", "winner": "Simmons", "winner_score": 37, "loser": "South Delta", "loser_score":  8},
            {"date": "2025-10-17", "winner": "Simmons", "winner_score": 34, "loser": "Shaw", "loser_score":  0},
            {"date": "2025-10-17", "winner": "South Delta", "winner_score": 34, "loser": "Riverside", "loser_score":  0},
            {"date": "2025-10-23", "winner": "Simmons", "winner_score": 43, "loser": "Riverside", "loser_score":  0},
            {"date": "2025-10-24", "winner": "South Delta", "winner_score": 46, "loser": "West Bolivar", "loser_score": 26},
            {"date": "2025-10-30", "winner": "Simmons", "winner_score": 62, "loser": "West Bolivar", "loser_score": 16},
            {"date": "2025-10-31", "winner": "Shaw", "winner_score": 22, "loser": "Riverside", "loser_score":  0},
        ],
        "seeds": {1: "Simmons",         2: "South Delta",           3: "Shaw",        4: "West Bolivar"},
        "eliminated": {"Riverside"},
    },
    (1, 7): {
        "games": [
            {"date": "2025-10-10", "winner": "Salem", "winner_score": 56, "loser": "West Lincoln", "loser_score":  6},
            {"date": "2025-10-17", "winner": "Bogue Chitto", "winner_score": 28, "loser": "Mount Olive", "loser_score": 12},
            {"date": "2025-10-24", "winner": "Bogue Chitto", "winner_score": 46, "loser": "West Lincoln", "loser_score": 10},
            {"date": "2025-10-24", "winner": "Salem", "winner_score": 58, "loser": "Mount Olive", "loser_score": 52},
            {"date": "2025-10-30", "winner": "Bogue Chitto", "winner_score": 45, "loser": "Salem", "loser_score":  8},
            {"date": "2025-10-30", "winner": "Mount Olive", "winner_score": 50, "loser": "West Lincoln", "loser_score":  7},
        ],
        "seeds": {1: "Bogue Chitto",    2: "Salem",                 3: "Mount Olive", 4: "West Lincoln"},
        "eliminated": set(),
    },
    (1, 8): {
        "games": [
            {"date": "2025-10-03", "winner": "Richton", "winner_score": 28, "loser": "Resurrection", "loser_score":  7},
            {"date": "2025-10-03", "winner": "Taylorsville", "winner_score": 49, "loser": "Stringer", "loser_score": 12},
            {"date": "2025-10-10", "winner": "Lumberton", "winner_score": 19, "loser": "Richton", "loser_score":  6},
            {"date": "2025-10-10", "winner": "Taylorsville", "winner_score": 41, "loser": "Resurrection", "loser_score":  9},
            {"date": "2025-10-17", "winner": "Lumberton", "winner_score": 34, "loser": "Resurrection", "loser_score":  3},
            {"date": "2025-10-17", "winner": "Stringer", "winner_score": 34, "loser": "Richton", "loser_score": 30},
            {"date": "2025-10-24", "winner": "Stringer", "winner_score": 46, "loser": "Lumberton", "loser_score": 20},
            {"date": "2025-10-24", "winner": "Taylorsville", "winner_score": 38, "loser": "Richton", "loser_score": 12},
            {"date": "2025-10-30", "winner": "Stringer", "winner_score": 40, "loser": "Resurrection", "loser_score":  7},
            {"date": "2025-10-30", "winner": "Taylorsville", "winner_score": 32, "loser": "Lumberton", "loser_score":  7},
        ],
        "seeds": {1: "Taylorsville",    2: "Stringer",              3: "Lumberton",   4: "Richton"},
        "eliminated": {"Resurrection"},
    },
}
# fmt: on
