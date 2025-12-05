
from typing import List, TypedDict
from prefect_files.data_classes import CompletedGame, RawCompletedGame, RemainingGame, StandingsOdds

# ----------- Test Data for Class 7A Region 3 (2025 season) ----------

# Teams in Class 7A Region 3 for the 2025 season
teams_3_7a: List[str] = [
		"Meridian",
		"Oak Grove",
		"Pearl",
		"Petal",
		"Brandon",
		"Northwest Rankin"
]

# Raw completed game results for Class 7A Region 3 in the 2025 season
raw_3_7a_region_results: List[RawCompletedGame] = [
	{
		"school" : "Meridian",
		"opponent" : "Pearl",
		"date" : "2025-10-10",
		"result" : "L",
		"points_for" : 17,
		"points_against" : 38
	},
	{
		"school" : "Meridian",
		"opponent" : "Oak Grove",
		"date" : "2025-10-17",
		"result" : "L",
		"points_for" : 21,
		"points_against" : 42
	},
	{
		"school" : "Meridian",
		"opponent" : "Northwest Rankin",
		"date" : "2025-10-24",
		"result" : "L",
		"points_for" : 12,
		"points_against" : 31
	},
	{
		"school" : "Meridian",
		"opponent" : "Petal",
		"date" : "2025-10-31",
		"result" : "L",
		"points_for" : 14,
		"points_against" : 42
	},
	{
		"school" : "Petal",
		"opponent" : "Oak Grove",
		"date" : "2025-10-10",
		"result" : "W",
		"points_for" : 28,
		"points_against" : 21
	},
	{
		"school" : "Petal",
		"opponent" : "Brandon",
		"date" : "2025-10-17",
		"result" : "W",
		"points_for" : 27,
		"points_against" : 21
	},
	{
		"school" : "Petal",
		"opponent" : "Pearl",
		"date" : "2025-10-24",
		"result" : "L",
		"points_for" : 14,
		"points_against" : 21
	},
	{
		"school" : "Petal",
		"opponent" : "Meridian",
		"date" : "2025-10-31",
		"result" : "W",
		"points_for" : 42,
		"points_against" : 14
	},
	{
		"school" : "Northwest Rankin",
		"opponent" : "Brandon",
		"date" : "2025-10-03",
		"result" : "L",
		"points_for" : 0,
		"points_against" : 3
	},
	{
		"school" : "Northwest Rankin",
		"opponent" : "Pearl",
		"date" : "2025-10-17",
		"result" : "W",
		"points_for" : 33,
		"points_against" : 29
	},
	{
		"school" : "Northwest Rankin",
		"opponent" : "Meridian",
		"date" : "2025-10-24",
		"result" : "W",
		"points_for" : 31,
		"points_against" : 12
	},
	{
		"school" : "Northwest Rankin",
		"opponent" : "Oak Grove",
		"date" : "2025-10-31",
		"result" : "L",
		"points_for" : 34,
		"points_against" : 37
	},
	{
		"school" : "Brandon",
		"opponent" : "Northwest Rankin",
		"date" : "2025-10-03",
		"result" : "W",
		"points_for" : 3,
		"points_against" : 0
	},
	{
		"school" : "Brandon",
		"opponent" : "Petal",
		"date" : "2025-10-17",
		"result" : "L",
		"points_for" : 21,
		"points_against" : 27
	},
	{
		"school" : "Brandon",
		"opponent" : "Oak Grove",
		"date" : "2025-10-24",
		"result" : "L",
		"points_for" : 7,
		"points_against" : 20
	},
	{
		"school" : "Brandon",
		"opponent" : "Pearl",
		"date" : "2025-10-31",
		"result" : "W",
		"points_for" : 17,
		"points_against" : 10
	},
	{
		"school" : "Oak Grove",
		"opponent" : "Petal",
		"date" : "2025-10-10",
		"result" : "L",
		"points_for" : 21,
		"points_against" : 28
	},
	{
		"school" : "Oak Grove",
		"opponent" : "Meridian",
		"date" : "2025-10-17",
		"result" : "W",
		"points_for" : 42,
		"points_against" : 21
	},
	{
		"school" : "Oak Grove",
		"opponent" : "Brandon",
		"date" : "2025-10-24",
		"result" : "W",
		"points_for" : 20,
		"points_against" : 7
	},
	{
		"school" : "Oak Grove",
		"opponent" : "Northwest Rankin",
		"date" : "2025-10-31",
		"result" : "W",
		"points_for" : 37,
		"points_against" : 34
	}
]

# Expected CompletedGame instances for Class 7A Region 3 in the 2025 season
expected_3_7a_completed_games: List[CompletedGame] = [
  CompletedGame("Brandon", "Northwest Rankin", 1, 3, 3, 0),
	CompletedGame("Brandon", "Oak Grove", -1, -8, 28, 20),
	CompletedGame("Brandon", "Pearl", 1, 7, 17, 10),
	CompletedGame("Brandon", "Petal", -1, -6, 21, 27),
	CompletedGame("Oak Grove", "Meridian", 1, 21, 42, 21),
	CompletedGame("Oak Grove", "Northwest Rankin", 1, 3, 37, 34),
	CompletedGame("Oak Grove", "Petal", -1, -7, 21, 28),
	CompletedGame("Meridian", "Northwest Rankin", -1, -19, 31, 12),
	CompletedGame("Meridian", "Pearl", -1, -21, 38, 17),
	CompletedGame("Meridian", "Petal", -1, -28, 14, 42),
	CompletedGame("Northwest Rankin", "Pearl", 1, 4, 33, 29),
	CompletedGame("Petal", "Pearl", -1, -7, 14, 21)
]

# Expected RemainingGames instances for Class 7A Region 3 in the 2025 season
expected_3_7a_remaining_games: List[RemainingGame] = [
  RemainingGame("Brandon", "Meridian"),
	RemainingGame("Oak Grove", "Pearl"),
	RemainingGame("Northwest Rankin", "Petal")
]

# Expected First Counts for Class 7A Region 3 in the 2025 season
expected_3_7a_first_counts: dict[str, int] = {}

# Expected Second Counts for Class 7A Region 3 in the 2025 season
expected_3_7a_second_counts: dict[str, int] = {}

# Expected Third Counts for Class 7A Region 3 in the 2025 season
expected_3_7a_third_counts: dict[str, int] = {}

# Expected Fourth Counts for Class 7A Region 3 in the 2025 season
expected_3_7a_fourth_counts: dict[str, int] = {}

# Expected Minimized Scenarios for Class 7A Region 3 in the 2025 season
expected_3_7a_minimized_scenarios: dict[str, dict[int, List[dict[str, bool]]]] = {}

# Expected Odds for Class 7A Region 3 in the 2025 season
expected_3_7a_odds: dict[str, StandingsOdds] = {}