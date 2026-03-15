# ms-hs-football-playoff-engine

A web application that calculates standings and playoff scenarios for Mississippi High School Football.

`docker compose --env-file .env.local down`
`docker compose --env-file .env.local up --build -d`

## Setting Up Your Environment

1. Navigate to [the Local Prefect UI](http://localhost:4200/deployments)
2. Do a "Quick Run" of the **Regions Data Pipeline**
3. Do a "Quick Run" of the **MaxPreps Data Pipeline**
4. Do a "Quick Run" of the **School Info Data Pipeline**
5. Do a "Quick Run" of the **AHSFHS Schedule Data Pipeline**

## Debugging

Run all region scenarios:

`python backend/scripts/enumerate_all_regions_scenarios.py --season 2025 --dsn "postgresql://postgres:postgres@0.0.0.0:5432/mshsfootball"`

Run a specific region scenario:

`python backend/scripts/simulate_region_finish.py \
  --class 1 --region 8 --season 2025 \
  --dsn "postgresql://postgres:postgres@0.0.0.0:5432/mshsfootball" \
  --out-scenarios "scenarios.txt"`

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