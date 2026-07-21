# ms-hs-football-playoff-engine

An application that calculates standings and playoff scenarios for Mississippi High School Football.

## How It Works

- Four Prefect pipelines ingest data from MHSAA (region assignments and school identity), the NCES EDGE API (school locations), and AHSFHS (schedules) into PostgreSQL.
- Once game results are in, the tiebreaker engine enumerates every possible outcome across the 2^R remaining region games, applies the [7-step MHSAA tiebreaker algorithm](docs/SCENARIO_RULES.md) (head-to-head record → point differential vs. highest-ranked opponent → capped per-game margin → coin flip) to determine seedings, and uses boolean minimization to reduce the scenario space into concise human-readable conditions. See [docs/SCENARIO_COMPUTATION.md](docs/SCENARIO_COMPUTATION.md) for how computation tiers, margin sensitivity, and the R threshold interact.
- Results are stored as dated snapshots so the API can answer historical "what were the odds on date X?" queries without recomputation.
- The FastAPI layer serves those snapshots for live requests, falls back to on-demand in-memory recomputation when no snapshot exists, and exposes a simulation endpoint that lets callers apply hypothetical results to explore what-if outcomes.
- Elo ratings with a margin-of-victory multiplier and cross-season carryover drive pregame win probability, while a separate in-game model uses score margin and time remaining (plus MSHAA's untimed alternating-possession OT format) for live probability estimates.

## Data Model

The following data model describes how data is stored and controlled in this application.

### Tables

| Table | Description |
|-------|-------------|
| `schools` | Static school identity: location (city, zip, lat/lon), mascot, colors, and Cloudinary logo paths (`logo_primary`, `logo_secondary`, `logo_tertiary`). Never duplicated across seasons. |
| `helmet_designs` | Per-school helmet design history. One row per distinct design; `year_first_worn`/`year_last_worn` span multiple seasons. Stores Cloudinary image paths for left-view mockup, right-view mockup, and photo. |
| `school_seasons` | Per-season class and region assignments (can change on MHSAA's two-year cycle). FK anchor for all season-scoped data. |
| `locations` | Physical venues. Referenced by `games` for geocoding and home-field logic. |
| `games` | School-perspective game rows — two rows per contest, so scores and results are always relative to the `school` column. Covers regular season and playoffs. |
| `region_standings` | Dated snapshots of seeding odds (1st–4th, raw and strength-weighted), playoff odds, playoff bracket advancement odds (2nd round through champion, raw and Elo-weighted), and [home-game odds per round](docs/PLAYOFF_HOME_RULES.md) (raw and Elo-weighted). Appended each pipeline run; never overwritten. |
| `team_ratings` | Dated Elo and RPI snapshots. One row per school per season per `as_of_date`. |
| `region_scenarios` | Serialized tiebreaker scenario trees (complete outcomes + minimized per-team conditions) plus pre-computed key insights (simple, unconditionally-true conditional statements like "Taylorsville clinches 1st seed: Taylorsville beats Stringer"). Computed once per pipeline run, read at request time. |
| `region_computation_state` | Tracks background margin-sensitivity upgrade status per region (the two-phase computation model for regions with 5–6 games remaining). |
| `playoff_formats` | Bracket template per class/season: size, number of regions, rounds. |
| `playoff_format_slots` | First-round matchup slots. Adjacent pairs implicitly define the bracket tree for round-2 and beyond. |
| `submissions` | User-submitted corrections and new assets (logos, helmet designs, colors, GPS coordinates, scores, feedback). Rows enter the queue with `status='pending'` and are approved or rejected by a moderator via the moderation API. Approved submissions are auto-applied to the live tables (except helmet submissions, which require manual mockup creation). Has an optional `user_id` FK for linking submissions to registered users. |
| `users` | Registered user accounts with role (`user`/`moderator`/`owner`), profile fields (display name, phone, hometown), and a favorite team FK. Identity is managed by Auth0; `auth0_id` stores the Auth0 `sub` claim. Rows are lazy-provisioned on first authenticated request. |
| `user_followed_teams` | Many-to-many join between users and the schools they follow. |
| `user_attended_games` | Many-to-many join between users and games they marked as attended. References the composite PK `(school, date)` on `games`. |

See [docs/SCHEMA.md](docs/SCHEMA.md) for the full entity-relationship diagram.

## Prerequisites

Before starting, create accounts and note your credentials for:

- **Auth0** (auth0.com) — you'll need `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` from your tenant settings
- **Cloudinary** (cloudinary.com) — you'll need `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET`

## Setting Up Your Environment

### Backend

#### Start the Docker Containers

Copy the environment template, fill in `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` from your Auth0 dashboard (see **Configure Auth0** below), then bring up the stack:

```
cp .env.example .env.local
docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.local --profile local-db up --build -d
```

The `--profile local-db` flag is required to start the local PostgreSQL container (`db` service). On a VM with an external database, omit it.

This starts nginx (`localhost:80`), Prefect server/worker (internal), and a local PostgreSQL instance (`localhost:5432`).

> **nginx reverse proxy**: All traffic enters through nginx on port 80. The Prefect UI is accessible at `http://localhost/prefect/` but requires a valid moderator `Authorization: Bearer <token>` header.

#### Accessing the Prefect UI (temporary workaround)

Browsers can't set custom headers on navigation requests, so until an admin frontend exists, use the **[ModHeader](https://modheader.com)** browser extension (Chrome/Firefox):

1. Install ModHeader and add a request header:
   - **Name**: `Authorization`
   - **Value**: `Bearer <your token>`
   - Set a URL filter to `localhost` so it only applies locally
2. Get your token from Swagger UI — after authorizing, execute any endpoint (e.g. `GET /api/v1/users/me`) and copy the token from the `Authorization: Bearer ...` line in the curl command shown
3. Navigate to `http://localhost/prefect/`

Auth0 access tokens expire (typically after 24 hours), so you'll need to copy a fresh token from Swagger UI when that happens.

> **Future**: once an admin frontend exists, this will be replaced by cookie-based session auth so the Prefect UI is accessible via a normal link after logging in.

#### Configure Auth0

Auth0 issues the RS256 JWT tokens the API validates. You need an **API resource** (sets the audience claim) and an **Application** (sets your domain and gives you Swagger UI login credentials). See [docs/AUTH0_SETUP.md](docs/AUTH0_SETUP.md) for step-by-step instructions.

Copy the resulting values to both `.env.local` and `.env.non-docker.local`:

```
AUTH0_DOMAIN=<your Auth0 domain>
AUTH0_AUDIENCE=<your API identifier>
```

#### Start the API (local development)

The FastAPI API runs **outside Docker** in local development due to a Docker Desktop on Apple Silicon limitation with asymmetric crypto. Run it natively against the Dockerized PostgreSQL:

```
cp .env.example .env.non-docker.local   # fill in all vars + POSTGRES_HOST=localhost
backend/scripts/start-api.sh
```

The script checks that the port is free, starts the server in the background, and waits until it's ready before returning. Logs go to `api.log` in the project root. Can be run from any directory.

```
tail -f api.log                    # stream logs
backend/scripts/stop-api.sh       # stop the server
```

The API is then available directly at `http://localhost:8000`. Swagger UI is at `http://localhost:8000/docs`.

#### Promote yourself to owner

The owner role grants access to admin and moderation endpoints. Without it, your account is a base `user` and you won't be able to approve submissions, manage other users, or access the Prefect UI.

User rows are lazy-provisioned on the first authenticated API request, so you need to log in before the SQL update will find anything. Since there is no frontend yet, create your user directly in the Auth0 dashboard first:

1. In the Auth0 dashboard, go to **User Management → Users → Create User**.
2. Enter an email and password. Leave **Connection** as `Username-Password-Authentication`. Click **Create**.

Then log in via the Swagger UI to provision your row:

3. Open the Swagger UI at `http://localhost:8000/docs`
4. Click **Authorize**. Fill in the dialog fields:
   - **client_id**: Client ID from Configure Auth0 Step 2
   - **client_secret**: Client Secret from Configure Auth0 Step 2
   - Leave **scope** blank
5. Click **Authorize** — Auth0's Universal Login page will open. Log in with the user you created above.
6. After login, Auth0 redirects back to Swagger UI automatically. Click **Close**.
7. Call `GET /api/v1/users/me` — this provisions your row

Then run the promotion. Replace `auth0|YOUR_SUB_HERE` with your Auth0 user ID (the `sub` claim) — find it by decoding your JWT at jwt.io or in the Auth0 dashboard under User Management → Users → User ID. The full `auth0|...` prefix is required.

```
docker exec -it ms-hs-football-playoff-engine-db-1 psql -U postgres -d mshsfootball -c \
  "UPDATE users SET role = 'owner' WHERE auth0_id = 'auth0|69f62102dc24a5830fa59fab';"
```

To reset the database and re-run the schema from scratch (e.g. after a schema change):

```
docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.local --profile local-db down -v
docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.local --profile local-db up --build -d
```

The `-v` flag removes the postgres data volume; the container will re-run `sql/init.sql` on startup.

#### Production / VM deployment

See [docs/VM_DEPLOYMENT.md](docs/VM_DEPLOYMENT.md) for the full AWS Lightsail setup guide (instance creation, DNS, SSL, Auth0 URL updates, and deploying updates).

#### Once per season (pre-season setup)

Run these in order — each depends on the previous step's data being in the database.

1. Navigate to [the Local Prefect UI](http://localhost:4200/deployments)
2. Do a "Quick Run" of the **Regions Data Pipeline** — populates `school_seasons` (class/region assignments)
   - The pipeline defaults to the current year. Use a **Custom Run** in the Prefect UI to target a different season.
3. Do a "Quick Run" of the **NCES School Geographic Data Flow** — fills in city, zip, latitude, and longitude for all public schools from the NCES EDGE API, then applies the private-school location seed for schools not in NCES
4. Do a "Quick Run" of the **MHSAA School Identity Data Flow** — scrapes mascot and primary/secondary colors from the MHSAA school directory
5. Do a "Quick Run" of the **AHSFHS Schedule Data Pipeline** with the target season — seeds `schools` and `games` rows from the schedule
6. Do a "Quick Run" of the **Region Scenarios Data Pipeline** with the target season — computes seeding odds, standings, and scenarios and writes the current snapshot to the database

Re-run steps 3-4 if schools move or rebrand. Re-run step 2 if MHSAA reclassifies schools (every two years) or if the playoff format changes.

To backfill a **completed historical season** after steps 1-6, continue with the steps below.

The `playoff_formats` and `playoff_format_slots` tables (which define the bracket structure) are **automatically seeded for 2025 and 2026** when the database is created — `sql/seeds/playoff_formats_2025.sql` and `sql/seeds/playoff_formats_2026.sql` are mounted as `docker-entrypoint-initdb.d` volumes in `docker-compose.yml` (with numeric prefixes, `05_`/`06_`, added at the mount target to control init order — the source filenames themselves have no prefix). No manual step is needed. See [New Season Setup](#new-season-setup) below for adding a future season.

#### Once per week (regular season)

1. Do a "Quick Run" of the **AHSFHS Schedule Data Pipeline** — fetches the latest scores and marks games `final=TRUE`
2. Do a "Quick Run" of the **Region Scenarios Pipeline** — reads the updated game results, runs the tiebreaker engine, and writes pre-computed standings odds and scenario data to `region_standings` and `region_scenarios`

> **Season parameter:** Both of these pipelines default to the current calendar year. Use a **Custom Run** in the Prefect UI to target a different season.

The API reads its data from these pre-computed snapshots; run this pipeline before serving fresh results.

#### After each playoff round

1. Do a "Quick Run" of the **AHSFHS Schedule Data Pipeline** — fetches playoff scores and marks games `final=TRUE`
2. Do a "Quick Run" of the **Playoff Bracket Update** pipeline — reads completed playoff results, marks eliminated teams, sets alive teams to deterministic 1.0/0.0 seeding odds, and writes one `region_standings` snapshot per class/region dated to that round's game date

> **Season parameter:** This pipeline defaults to the current calendar year. Use a **Custom Run** in the Prefect UI to target a different season.

Run this after each round concludes (first round, second round, semifinals, finals). The Region Scenarios Pipeline does **not** need to re-run during the playoffs — seedings are fully determined at that point.

#### Once per season (after importing a full historical season)

After the pre-season setup steps (1–6) have completed for a season, run the following two pipelines to build a full per-gameday snapshot history:

7. **Backfill Historical Snapshots** (Custom Run, target season) — writes `team_ratings`, `region_standings`, `region_scenarios`, and `region_computation_state` rows for every unique game-date in the season so the timeline API can serve historical odds for any past date without recomputation. Only needs to run once per season (or again after re-importing a full season's games). Both the seeding odds and W/L records in each snapshot are historically accurate — the `get_standings_for_region` stored proc applies a date filter to all aggregations.

8. **Playoff Bracket Update** (Custom Run, target season) — self-backfilling: reads all completed playoff games and writes one `region_standings` snapshot per playoff round date, overwriting the backfill's regular-season-style odds for playoff dates with deterministic 1.0/0.0 seedings. Requires step 6 to have populated `region_standings` with `clinched` flags first.

> **Season parameter:** Both pipelines default to the current calendar year. Use a **Custom Run** in the Prefect UI to target a different season.

### New Season Setup

When MHSAA reclassifies schools or consolidations occur mid-cycle, additional manual steps are required after the pipelines run. See [docs/SEASON_SETUP.md](docs/SEASON_SETUP.md) for the full guide covering playoff bracket format seeding and school consolidation/closure procedures.

## Development Reference

### Setup

#### UV

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
uv run pyright               # pyright
```

### Testing

Run the test suite from the repo root (coverage is enabled by default via `pyproject.toml`):

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

### API Reference

Interactive docs are at [localhost:8000/docs](http://localhost:8000/docs) when the server is running. For the complete endpoint reference see [docs/API_REFERENCE.md](docs/API_REFERENCE.md).

Key endpoints summary:
- `/api/v1/standings/{clazz}/{region}` — seeding odds + scenarios + bracket/home-game odds snapshots
- `/api/v1/hosting/{clazz}/{region}` — playoff hosting odds (p_host_given_reach + p_host_overall, raw + Elo-weighted) per round; simulate endpoint accepts winner/loser school names
- `/api/v1/bracket` — bracket advancement odds per (region, seed) slot, including Elo-weighted advancement, non-weighted and weighted hosting odds per round; simulate endpoint (playoff mode only, same winner/loser format) returns the same full set of fields
- `/api/v1/ratings` — Elo and RPI snapshots per team

## Disclaimer

Win probabilities, seeding odds, and playoff advancement percentages are statistical estimates for informational and entertainment purposes only — not gambling advice. See [docs/ODDS_DISCLAIMER.md](docs/ODDS_DISCLAIMER.md) for full details.

## License

Copyright © 2025–2026 Paul Sullivan. All rights reserved. This software is proprietary and confidential — see [LICENSE](LICENSE).
