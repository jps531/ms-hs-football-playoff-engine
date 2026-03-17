"""Static test fixtures for Region 3-7A (2025 season) standings and scenario tests."""

from backend.helpers.data_classes import CompletedGame, RawCompletedGame, RemainingGame, StandingsOdds

# ----------- Test Data for Class 7A Region 3 (2025 season) ----------

# Teams in Class 7A Region 3 for the 2025 season
teams_3_7a: list[str] = ["Meridian", "Oak Grove", "Pearl", "Petal", "Brandon", "Northwest Rankin"]

# ---------------------------------------------------------------------------
# PRE-FINAL-WEEK state (games played through 2025-11-02, 3 games remaining)
# ---------------------------------------------------------------------------

# Raw completed game results — both perspectives for each game
raw_3_7a_region_results: list[RawCompletedGame] = [
    {"school": "Meridian", "opponent": "Pearl", "date": "2025-10-10", "result": "L", "points_for": 17, "points_against": 38},
    {"school": "Meridian", "opponent": "Oak Grove", "date": "2025-10-17", "result": "L", "points_for": 21, "points_against": 42},
    {"school": "Meridian", "opponent": "Northwest Rankin", "date": "2025-10-24", "result": "L", "points_for": 12, "points_against": 31},
    {"school": "Meridian", "opponent": "Petal", "date": "2025-10-31", "result": "L", "points_for": 14, "points_against": 42},
    {"school": "Petal", "opponent": "Oak Grove", "date": "2025-10-10", "result": "W", "points_for": 28, "points_against": 21},
    {"school": "Petal", "opponent": "Brandon", "date": "2025-10-17", "result": "W", "points_for": 27, "points_against": 21},
    {"school": "Petal", "opponent": "Pearl", "date": "2025-10-24", "result": "L", "points_for": 14, "points_against": 21},
    {"school": "Petal", "opponent": "Meridian", "date": "2025-10-31", "result": "W", "points_for": 42, "points_against": 14},
    {"school": "Northwest Rankin", "opponent": "Brandon", "date": "2025-10-03", "result": "L", "points_for": 0, "points_against": 3},
    {"school": "Northwest Rankin", "opponent": "Pearl", "date": "2025-10-17", "result": "W", "points_for": 33, "points_against": 29},
    {"school": "Northwest Rankin", "opponent": "Meridian", "date": "2025-10-24", "result": "W", "points_for": 31, "points_against": 12},
    {"school": "Northwest Rankin", "opponent": "Oak Grove", "date": "2025-10-31", "result": "L", "points_for": 34, "points_against": 37},
    {"school": "Brandon", "opponent": "Northwest Rankin", "date": "2025-10-03", "result": "W", "points_for": 3, "points_against": 0},
    {"school": "Brandon", "opponent": "Petal", "date": "2025-10-17", "result": "L", "points_for": 21, "points_against": 27},
    {"school": "Brandon", "opponent": "Oak Grove", "date": "2025-10-24", "result": "L", "points_for": 7, "points_against": 20},
    {"school": "Brandon", "opponent": "Pearl", "date": "2025-10-31", "result": "W", "points_for": 17, "points_against": 10},
    {"school": "Oak Grove", "opponent": "Petal", "date": "2025-10-10", "result": "L", "points_for": 21, "points_against": 28},
    {"school": "Oak Grove", "opponent": "Meridian", "date": "2025-10-17", "result": "W", "points_for": 42, "points_against": 21},
    {"school": "Oak Grove", "opponent": "Brandon", "date": "2025-10-24", "result": "W", "points_for": 20, "points_against": 7},
    {"school": "Oak Grove", "opponent": "Northwest Rankin", "date": "2025-10-31", "result": "W", "points_for": 37, "points_against": 34},
]

# Expected CompletedGame objects — 12 completed games, sorted by (a, b)
expected_3_7a_completed_games: list[CompletedGame] = [
    CompletedGame("Brandon", "Northwest Rankin", 1, 3, 0, 3),
    CompletedGame("Brandon", "Oak Grove", -1, -13, 20, 7),
    CompletedGame("Brandon", "Pearl", 1, 7, 10, 17),
    CompletedGame("Brandon", "Petal", -1, -6, 27, 21),
    CompletedGame("Meridian", "Northwest Rankin", -1, -19, 31, 12),
    CompletedGame("Meridian", "Oak Grove", -1, -21, 42, 21),
    CompletedGame("Meridian", "Pearl", -1, -21, 38, 17),
    CompletedGame("Meridian", "Petal", -1, -28, 42, 14),
    CompletedGame("Northwest Rankin", "Oak Grove", -1, -3, 37, 34),
    CompletedGame("Northwest Rankin", "Pearl", 1, 4, 29, 33),
    CompletedGame("Oak Grove", "Petal", -1, -7, 28, 21),
    CompletedGame("Pearl", "Petal", 1, 7, 14, 21),
]

# Remaining games heading into final week
expected_3_7a_remaining_games: list[RemainingGame] = [
    RemainingGame("Brandon", "Meridian"),
    RemainingGame("Oak Grove", "Pearl"),
    RemainingGame("Northwest Rankin", "Petal"),
]

# Scenario counts — fractional due to margin-sensitive tiebreaker branches
# denom = 8.0 (2^3 remaining games)
expected_3_7a_first_counts: dict[str, float] = {
    "Petal": 4.104166666666667,
    "Northwest Rankin": 1.1874999999999998,
    "Oak Grove": 2.375,
    "Pearl": 0.33333333333333337,
}
expected_3_7a_second_counts: dict[str, float] = {
    "Pearl": 3.2500000000000004,
    "Oak Grove": 2.0416666666666665,
    "Petal": 1.1458333333333333,
    "Northwest Rankin": 1.5625,
}
expected_3_7a_third_counts: dict[str, float] = {
    "Oak Grove": 2.243055555555556,
    "Brandon": 3,
    "Petal": 2.4861111111111107,
    "Northwest Rankin": 0.14583333333333334,
    "Pearl": 0.125,
}
expected_3_7a_fourth_counts: dict[str, float] = {
    "Brandon": 3,
    "Northwest Rankin": 3.1041666666666665,
    "Oak Grove": 1.3402777777777775,
    "Pearl": 0.29166666666666674,
    "Petal": 0.2638888888888889,
}

# Minimized scenario atoms per team per seed position
expected_3_7a_minimized_scenarios: dict = {
    "Petal": {
        1: [
            {"Northwest Rankin>Petal": False},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal_GE1": True, "Northwest Rankin>Petal_GE4": False, "Pearl>Oak Grove_GE3": True, "Pearl>Oak Grove_GE9": False},
        ],
        2: [
            {"Brandon>Meridian": True, "Northwest Rankin>Petal": True, "Oak Grove>Pearl": True},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal_GE1": True, "Northwest Rankin>Petal_GE4": False, "Pearl>Oak Grove_GE1": True},
        ],
        3: [
            {"Brandon>Meridian": False, "Northwest Rankin>Petal": True},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal_GE5": True, "Pearl>Oak Grove_GE1": True},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal_GE4": True, "Northwest Rankin>Petal_GE5": False, "Oak Grove>Pearl": False, "Pearl>Oak Grove": True},
        ],
        4: [
            {"Brandon>Meridian": True, "Northwest Rankin>Petal_GE5": True, "Pearl>Oak Grove_GE4": True, "Pearl>Oak Grove_GE9": False},
        ],
    },
    "Pearl": {
        1: [
            {"Brandon>Meridian": True, "Northwest Rankin>Petal": True, "Pearl>Oak Grove_GE9": True},
        ],
        2: [
            {"Northwest Rankin>Petal": False, "Oak Grove>Pearl": False},
            {"Brandon>Meridian": False, "Northwest Rankin>Petal": True, "Oak Grove>Pearl": False},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal": True, "Pearl>Oak Grove_GE6": True, "Pearl>Oak Grove_GE9": False},
        ],
        3: [
            {"Brandon>Meridian": True, "Northwest Rankin>Petal_GE1": True, "Pearl>Oak Grove_GE4": True, "Pearl>Oak Grove_GE6": False},
        ],
        4: [
            {"Brandon>Meridian": True, "Northwest Rankin>Petal": True, "Pearl>Oak Grove_GE1": True, "Pearl>Oak Grove_GE4": False},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal_GE3": True, "Northwest Rankin>Petal_GE6": False, "Pearl>Oak Grove_GE4": True, "Pearl>Oak Grove_GE6": False},
        ],
        5: [
            {"Oak Grove>Pearl": True},
        ],
    },
    "Oak Grove": {
        1: [
            {"Northwest Rankin>Petal": True, "Oak Grove>Pearl": True},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal_GE3": True, "Pearl>Oak Grove_GE3": True, "Pearl>Oak Grove_GE6": False},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal": True, "Pearl>Oak Grove_GE1": True, "Pearl>Oak Grove_GE3": False},
        ],
        2: [
            {"Northwest Rankin>Petal": False, "Oak Grove>Pearl": True},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal_GE1": True, "Northwest Rankin>Petal_GE3": False, "Pearl>Oak Grove_GE3": True, "Pearl>Oak Grove_GE6": False},
        ],
        3: [
            {"Northwest Rankin>Petal": False, "Oak Grove>Pearl": False},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal_GE1": True, "Pearl>Oak Grove_GE10": False, "Pearl>Oak Grove_GE6": True},
        ],
        4: [
            {"Brandon>Meridian": False, "Northwest Rankin>Petal": True, "Oak Grove>Pearl": False},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal": True, "Pearl>Oak Grove_GE10": True},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal_GE3": True, "Pearl>Oak Grove_GE10": False, "Pearl>Oak Grove_GE6": True},
        ],
    },
    "Brandon": {
        3: [
            {"Northwest Rankin>Petal": False, "Oak Grove>Pearl": True},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal": True, "Oak Grove>Pearl": True},
        ],
        4: [
            {"Northwest Rankin>Petal": False, "Oak Grove>Pearl": False},
            {"Brandon>Meridian": False, "Northwest Rankin>Petal": True, "Oak Grove>Pearl": True},
        ],
        5: [
            {"Brandon>Meridian": False, "Northwest Rankin>Petal": True, "Oak Grove>Pearl": False},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal": True, "Oak Grove>Pearl": False, "Pearl>Oak Grove": True},
        ],
    },
    "Northwest Rankin": {
        1: [
            {"Brandon>Meridian": False, "Northwest Rankin>Petal": True, "Oak Grove>Pearl": False},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal_GE4": True, "Pearl>Oak Grove_GE6": True, "Pearl>Oak Grove_GE9": False},
        ],
        2: [
            {"Brandon>Meridian": True, "Northwest Rankin>Petal_GE4": True, "Pearl>Oak Grove_GE1": True},
            {"Brandon>Meridian": False, "Northwest Rankin>Petal": True, "Oak Grove>Pearl": True},
        ],
        3: [
            {"Brandon>Meridian": True, "Northwest Rankin>Petal_GE1": True, "Northwest Rankin>Petal_GE4": False, "Pearl>Oak Grove_GE1": True},
        ],
        4: [
            {"Northwest Rankin>Petal": False, "Oak Grove>Pearl": True},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal": True, "Oak Grove>Pearl": True},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal_GE1": True, "Northwest Rankin>Petal_GE4": False, "Pearl>Oak Grove_GE10": False, "Pearl>Oak Grove_GE4": True},
        ],
        5: [
            {"Northwest Rankin>Petal": False, "Oak Grove>Pearl": False},
        ],
    },
    "Meridian": {
        6: [
            {"Northwest Rankin>Petal": False},
            {"Brandon>Meridian": False, "Northwest Rankin>Petal": True},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal": True, "Oak Grove>Pearl": True},
            {"Brandon>Meridian": True, "Northwest Rankin>Petal": True, "Oak Grove>Pearl": False, "Pearl>Oak Grove": True},
        ],
    },
}

# Odds for each team heading into final week
expected_3_7a_odds: dict[str, StandingsOdds] = {
    "Meridian": StandingsOdds("Meridian", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False, True),
    "Oak Grove": StandingsOdds("Oak Grove", 0.296875, 0.2552083333333333, 0.2803819444444445, 0.16753472222222218, 0.9999999999999999, 1.0, True, False),
    "Pearl": StandingsOdds("Pearl", 0.04166666666666667, 0.40625000000000006, 0.015625, 0.03645833333333334, 0.5000000000000001, 0.5000000000000001, False, False),
    "Petal": StandingsOdds("Petal", 0.5130208333333334, 0.14322916666666666, 0.31076388888888884, 0.03298611111111111, 1.0, 1.0, True, False),
    "Brandon": StandingsOdds("Brandon", 0.0, 0.0, 0.375, 0.375, 0.75, 0.75, False, False),
    "Northwest Rankin": StandingsOdds("Northwest Rankin", 0.14843749999999997, 0.1953125, 0.018229166666666668, 0.3880208333333333, 0.75, 0.75, False, False),
}

# ---------------------------------------------------------------------------
# FULL SEASON state (all 15 games played, 0 remaining)
# Ground truth: seeds 1-4 = Oak Grove, Petal, Brandon, Northwest Rankin
# ---------------------------------------------------------------------------

raw_3_7a_region_results_full: list[RawCompletedGame] = list(raw_3_7a_region_results) + [
    {"school": "Brandon", "opponent": "Meridian", "date": "2025-11-07", "result": "W", "points_for": 40, "points_against": 13},
    {"school": "Meridian", "opponent": "Brandon", "date": "2025-11-07", "result": "L", "points_for": 13, "points_against": 40},
    {"school": "Oak Grove", "opponent": "Pearl", "date": "2025-11-07", "result": "W", "points_for": 28, "points_against": 7},
    {"school": "Pearl", "opponent": "Oak Grove", "date": "2025-11-07", "result": "L", "points_for": 7, "points_against": 28},
    {"school": "Northwest Rankin", "opponent": "Petal", "date": "2025-11-07", "result": "W", "points_for": 34, "points_against": 28},
    {"school": "Petal", "opponent": "Northwest Rankin", "date": "2025-11-07", "result": "L", "points_for": 28, "points_against": 34},
]

expected_3_7a_completed_games_full: list[CompletedGame] = [
    CompletedGame("Brandon", "Meridian", 1, 27, 13, 40),
    CompletedGame("Brandon", "Northwest Rankin", 1, 3, 0, 3),
    CompletedGame("Brandon", "Oak Grove", -1, -13, 20, 7),
    CompletedGame("Brandon", "Pearl", 1, 7, 10, 17),
    CompletedGame("Brandon", "Petal", -1, -6, 27, 21),
    CompletedGame("Meridian", "Northwest Rankin", -1, -19, 31, 12),
    CompletedGame("Meridian", "Oak Grove", -1, -21, 42, 21),
    CompletedGame("Meridian", "Pearl", -1, -21, 38, 17),
    CompletedGame("Meridian", "Petal", -1, -28, 42, 14),
    CompletedGame("Northwest Rankin", "Oak Grove", -1, -3, 37, 34),
    CompletedGame("Northwest Rankin", "Pearl", 1, 4, 29, 33),
    CompletedGame("Northwest Rankin", "Petal", 1, 6, 28, 34),
    CompletedGame("Oak Grove", "Pearl", 1, 21, 7, 28),
    CompletedGame("Oak Grove", "Petal", -1, -7, 28, 21),
    CompletedGame("Pearl", "Petal", 1, 7, 14, 21),
]

# No remaining games after final week
expected_3_7a_remaining_games_full: list[RemainingGame] = []

# Full-season counts: deterministic (denom = 1.0), each team has exactly one seed
expected_3_7a_first_counts_full: dict[str, float] = {"Oak Grove": 1}
expected_3_7a_second_counts_full: dict[str, float] = {"Petal": 1}
expected_3_7a_third_counts_full: dict[str, float] = {"Brandon": 1}
expected_3_7a_fourth_counts_full: dict[str, float] = {"Northwest Rankin": 1}

# No scenario tree for full-season (no remaining games, no ties)
expected_3_7a_minimized_scenarios_full: dict = {}

expected_3_7a_odds_full: dict[str, StandingsOdds] = {
    "Meridian": StandingsOdds("Meridian", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False, True),
    "Oak Grove": StandingsOdds("Oak Grove", 1.0, 0.0, 0.0, 0.0, 1.0, 1.0, True, False),
    "Pearl": StandingsOdds("Pearl", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False, True),
    "Petal": StandingsOdds("Petal", 0.0, 1.0, 0.0, 0.0, 1.0, 1.0, True, False),
    "Brandon": StandingsOdds("Brandon", 0.0, 0.0, 1.0, 0.0, 1.0, 1.0, True, False),
    "Northwest Rankin": StandingsOdds("Northwest Rankin", 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, True, False),
}
