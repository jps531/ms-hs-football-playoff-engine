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

The frontend reads from these tables at request time — no tiebreaker computation happens on the frontend.

To render scenario text, call `read_region_scenarios(conn, season, clazz, region)` to load the pre-computed data, then pass it to one of the two render functions:

- **`render_scenarios(data["complete_scenarios"])`** — outputs the full division view, one scenario per distinct seeding outcome:
  ```
  Scenario 1: Petal beats Northwest Rankin AND Pearl beats Oak Grove
  1. Petal
  2. Pearl
  3. Oak Grove
  4. Brandon
  Eliminated: Meridian, Northwest Rankin

  Scenario 4a: Pearl beats Oak Grove AND Pearl's margin and Oak Grove's margin combined total exactly 10
  1. Oak Grove
  ...
  ```

- **`render_team_scenarios(team, data["scenario_atoms"])`** — outputs the per-team view, grouped by seed the team can achieve:
  ```
  Pearl

  #1 seed if:
  1. Petal beats Northwest Rankin AND Pearl beats Oak Grove by 8 or more
  2. ...

  #2 seed if:
  1. Pearl beats Oak Grove
  2. ...

  Eliminated if:
  1. Oak Grove beats Pearl AND Northwest Rankin beats Petal
  ```

To resolve seeding for a specific set of game results (e.g. a user entering scores for remaining games), call `resolve_with_results(teams, completed, remaining, results, margins)` from `backend/helpers/tiebreakers.py`:

- **`results`** — dict mapping `(team1, team2)` → winner name; teams may be in either order
- **`margins`** — optional dict mapping `(team1, team2)` → winning margin (positive int); omit if scores aren't known yet

Returns `(seeding, messages)`:
- **`seeding`** — list of team names in seed order (seed 1 first)
- **`messages`** — list of human-readable strings for any games where the margin was not provided but would affect the tiebreaker outcome; empty if all ties are resolved without margin data

```python
seeding, messages = resolve_with_results(
    teams,
    completed_games,
    remaining_games,
    results={("Oak Grove", "Pearl"): "Oak Grove", ("Northwest Rankin", "Petal"): "Northwest Rankin", ("Brandon", "Meridian"): "Brandon"},
    margins={("Oak Grove", "Pearl"): 21, ("Northwest Rankin", "Petal"): 6},
)
# seeding → ["Oak Grove", "Petal", "Brandon", "Northwest Rankin", "Pearl", "Meridian"]
# messages → []
```

If margins are omitted and any tied teams played each other in a remaining game whose margin would change the seeding, `messages` will describe which teams are affected:

```python
seeding, messages = resolve_with_results(teams, completed, remaining, results)
# messages → ["Point differential needed for Pearl over Oak Grove: margin affects seeding of Northwest Rankin, Oak Grove, Pearl, Petal."]
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