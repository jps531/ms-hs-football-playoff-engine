# ms-hs-football-playoff-engine

A web application that calculates standings and playoff scenarios for Mississippi High School Football.

`docker compose --env-file .env.local down`
`docker compose --env-file .env.local up --build -d`

## Setting Up Your Environment

### Once per season (pre-season setup)

Run these in order — each depends on the previous step's data being in the database.

1. Navigate to [the Local Prefect UI](http://localhost:4200/deployments)
2. Do a "Quick Run" of the **Regions Data Pipeline** — populates `school_seasons` (class/region assignments)
3. Do a "Quick Run" of the **MaxPreps Data Pipeline** — populates `schools` (metadata) and seeds `games` rows for the schedule
4. Do a "Quick Run" of the **School Info Data Pipeline** — fills in school identity details (colors, mascot, etc.)

Re-run these if MHSAA reclassifies schools (every two years) or if the playoff format changes.

### Once per week (during the season)

1. Do a "Quick Run" of the **AHSFHS Schedule Data Pipeline** — fetches the latest scores and marks games `final=TRUE`
2. Do a "Quick Run" of the **Region Scenarios Pipeline** — reads the updated game results, runs the tiebreaker engine, and writes pre-computed standings odds and scenario data to `region_standings` and `region_scenarios`

### Frontend Helper Functions

The frontend reads from pre-computed data — no tiebreaker computation happens at request time. All dict-producing functions live in `backend/helpers/scenario_renderer.py`.

#### Loading pre-computed region data

```python
from backend.helpers.database_helpers import read_region_scenarios

data = read_region_scenarios(conn, season=2025, clazz=7, region=3)
# data["scenario_atoms"]    → per-team seeding condition atoms
# data["complete_scenarios"] → full division scenario list
# data["remaining_games"]   → unplayed games for this region
```

---

#### `division_scenarios_as_dict(scenarios, playoff_seeds=4)`

All possible seeding outcomes for a division, keyed by scenario label. Use this for a "what if" table showing every possible final seeding.

```python
from backend.helpers.scenario_renderer import division_scenarios_as_dict

d = division_scenarios_as_dict(data["complete_scenarios"])
# {
#   "1":  {"title": "Petal beats NWR AND Pearl beats OG", "one_seed": "Petal", "two_seed": "Pearl", "three_seed": "Oak Grove", "four_seed": "Brandon", "eliminated": ["Meridian", "Northwest Rankin"]},
#   "4a": {"title": "Pearl beats OG AND combined margin == 10", "one_seed": "Oak Grove", ...},
#   ...
# }
```

Each entry:

| Key | Type | Description |
|---|---|---|
| `title` | `str` | Human-readable AND-joined condition string |
| `one_seed` | `str` | Team finishing 1st |
| `two_seed` | `str` | Team finishing 2nd |
| `three_seed` | `str` | Team finishing 3rd |
| `four_seed` | `str` | Team finishing 4th |
| `eliminated` | `list[str]` | Teams finishing outside the top seeds |

---

#### `team_scenarios_as_dict(scenarios, playoff_seeds=4, odds=None, weighted_odds=None)`

Per-team seeding scenarios, keyed by team name then seed. Use this to render a per-team card showing what each team needs to achieve each seed.

```python
from backend.helpers.scenario_renderer import team_scenarios_as_dict

d = team_scenarios_as_dict(
    data["scenario_atoms"],
    odds=standings_odds_by_team,           # dict[team → StandingsOdds], optional
    weighted_odds=weighted_odds_by_team,   # dict[team → StandingsOdds], optional
)
# {
#   "Pearl": {
#     1: {"odds": 0.25, "weighted_odds": 0.31, "scenarios": ["Petal beats NWR AND Pearl beats OG by 8+", ...]},
#     2: {"odds": 0.50, "weighted_odds": 0.48, "scenarios": ["Pearl beats OG", ...]},
#     "eliminated": {"odds": 0.25, "weighted_odds": 0.21, "scenarios": ["OG beats Pearl AND NWR beats Petal"]},
#   },
#   ...
# }
```

Each seed entry (integer keys `1`–`playoff_seeds` and the string `"eliminated"`):

| Key | Type | Description |
|---|---|---|
| `odds` | `float \| None` | Equal-probability chance of this outcome |
| `weighted_odds` | `float \| None` | Win-probability-weighted chance |
| `scenarios` | `list[str]` | Condition strings; empty list for a clinched/eliminated team |

---

#### `team_home_scenarios_as_dict(team, home_scenarios)`

Condition-list view of when a team will host vs. travel in each playoff round. Use this to show the "if X advances and Y advances, Team hosts" logic.

```python
from backend.helpers.home_game_scenarios import enumerate_home_game_scenarios
from backend.helpers.scenario_renderer import team_home_scenarios_as_dict

rounds = enumerate_home_game_scenarios(
    region=8, seed=1, slots=slots, season=2025,
    p_reach_by_round=..., p_host_conditional_by_round=..., p_host_marginal_by_round=...,
    team_lookup=team_lookup,
)
d = team_home_scenarios_as_dict("Taylorsville", rounds)
```

Top-level keys: `"first_round"`, `"second_round"` (1A–4A only), `"quarterfinals"`, `"semifinals"`.

Each round entry:

| Key | Type | Description |
|---|---|---|
| `p_reach` | `float \| None` | P(team reaches this round) |
| `p_host_conditional` | `float \| None` | P(hosts \| reaches) |
| `p_host_marginal` | `float \| None` | P(reaches AND hosts) |
| `p_reach_weighted` | `float \| None` | Weighted equivalent of `p_reach` |
| `p_host_conditional_weighted` | `float \| None` | Weighted equivalent |
| `p_host_marginal_weighted` | `float \| None` | Weighted equivalent |
| `will_host` | `list[scenario]` | Paths that lead to the team hosting |
| `will_not_host` | `list[scenario]` | Paths that lead to the team travelling |

Each scenario in `will_host` / `will_not_host`:

```python
{
    "conditions": [
        {
            "kind": "advances" | "seed_required",
            "round": str | None,      # e.g. "Quarterfinals"
            "region": int | None,
            "seed": int | None,
            "team": str | None,       # resolved school name, or None
        },
        ...
    ],
    "explanation": str | None,    # e.g. "Higher seed (#1) hosts"
}
```

Multiple conditions within a scenario are AND-joined. Multiple scenarios within `will_host` or `will_not_host` are OR-joined (any one path suffices). See [`docs/taylorsville_home_scenarios_2025.md`](docs/taylorsville_home_scenarios_2025.md) for a full worked example.

---

#### `team_matchups_as_dict(round_matchups)`

Opponent-centric view of every possible playoff matchup — one entry per `(opponent, home/away)` combination. Use this to render a list like "Region 7 #4 West Lincoln at Taylorsville (100%)". Unlike `team_home_scenarios_as_dict`, this view is flat (no nested condition lists) and includes per-matchup probabilities.

```python
from backend.helpers.home_game_scenarios import enumerate_team_matchups
from backend.helpers.scenario_renderer import team_matchups_as_dict

rounds = enumerate_team_matchups(
    region=8, seed=1, slots=slots, season=2025,
    p_reach_by_round=..., p_host_conditional_by_round=..., p_host_marginal_by_round=...,
    team_lookup=team_lookup,
)
d = team_matchups_as_dict(rounds)
```

Top-level keys: `"first_round"`, `"second_round"` (1A–4A only), `"quarterfinals"`, `"semifinals"`.

Each round entry has the same six round-level odds fields as `team_home_scenarios_as_dict`, plus:

| Key | Type | Description |
|---|---|---|
| `matchups` | `list[matchup]` | All `(opponent, home/away)` combos, home-first then by `(region, seed)` |

Each matchup:

| Key | Type | Description |
|---|---|---|
| `opponent` | `str` | School name, or `"Region X #Y Seed"` if lookup unavailable |
| `opponent_region` | `int` | Opponent's region number |
| `opponent_seed` | `int` | Opponent's seed (1 = best) |
| `home` | `bool` | `True` if the given team is the home team |
| `p_conditional` | `float \| None` | P(this matchup \| team reaches round) — values sum to 1.0 per round |
| `p_conditional_weighted` | `float \| None` | Weighted equivalent (placeholder for `WinProbFn`) |
| `p_marginal` | `float \| None` | P(reaches AND this matchup) = `p_conditional × p_reach` |
| `p_marginal_weighted` | `float \| None` | Weighted equivalent |
| `explanation` | `str \| None` | Rule reason, e.g. `"Higher seed (#1) hosts"` |

> **Note on split entries:** The same opponent may appear twice in a round (once with `home=True`, once `home=False`) when the home-team determination depends on which path the opponent took through an earlier round. Their `p_conditional` values sum to the total probability of facing that opponent. See the Leake County example in [`docs/taylorsville_home_scenarios_2025.md`](docs/taylorsville_home_scenarios_2025.md).

---

#### `resolve_with_results(teams, completed, remaining, results, margins=None)`

Resolve the final seeding for a specific set of hypothetical game results (e.g. a user entering scores). From `backend/helpers/tiebreakers.py`.

- **`results`** — `dict[(team1, team2) → winner]`; teams may be in either order
- **`margins`** — optional `dict[(team1, team2) → int]`; omit if scores are unknown

Returns `(seeding, messages)`:
- **`seeding`** — `list[str]` of team names in seed order (seed 1 first)
- **`messages`** — `list[str]` describing any games where a margin would change the outcome; empty when all tiebreakers are margin-independent

```python
seeding, messages = resolve_with_results(
    teams, completed_games, remaining_games,
    results={("Oak Grove", "Pearl"): "Oak Grove", ("Northwest Rankin", "Petal"): "Northwest Rankin"},
    margins={("Oak Grove", "Pearl"): 21, ("Northwest Rankin", "Petal"): 6},
)
# seeding  → ["Oak Grove", "Petal", "Brandon", "Northwest Rankin", "Pearl", "Meridian"]
# messages → []
```

## Development Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management and [ruff](https://docs.astral.sh/ruff/) for linting/formatting.

Install dependencies (creates `.venv` automatically):

```
uv sync --dev
```

### Linting

```
uv run ruff check .          # lint
uv run ruff check --fix .    # auto-fix safe issues
uv run ruff format .         # format (black-compatible)
```

## Testing

Run the test suite (coverage is enabled by default via `pyproject.toml`):

```
uv run pytest
```

Or with verbose output:

```
uv run pytest -vv
```

Coverage is measured with branch analysis and reported in the terminal after every run. The report excludes Prefect pipeline files (which require a live DB/Prefect environment) and focuses on the pure-logic modules: `tiebreakers.py`, `scenarios.py`, `data_helpers.py`, and `data_classes.py`.

To generate a browsable HTML report:

```
uv run pytest --cov-report=html
open htmlcov/index.html
```

### Docstring coverage

Check that all public functions and modules have docstrings:

```
uv run docstr-coverage backend
```

The report excludes pipeline files (same omit list as test coverage) and skips magic methods and `__init__`. Current baseline: 100%.

### Coverage gaps

Known tiebreaker paths not yet exercised by the Region 3-7A test data are documented in [`docs/COVERAGE_GAPS.md`](docs/COVERAGE_GAPS.md). Each gap requires synthetic game data to test exhaustively.