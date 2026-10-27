# ms-hs-football-playoff-engine

An application that calculates standings and playoff scenarios for Mississippi high school football (MHSAA).

## How It Works

- Four Prefect pipelines ingest data from MHSAA (region assignments and school identity), the NCES EDGE API (school locations), and AHSFHS (schedules) into PostgreSQL.
- Once game results are in, the tiebreaker engine works through the remaining region games (every outcome while there are 15 or fewer, and every winning margin while there are 5 or fewer; 50,000 simulated seasons per odds mode above 15), applies the [6-step MHSAA tiebreaker procedure](docs/architecture/SCENARIO_RULES.md) (head-to-head → results against the highest-finishing teams → capped point differential among the tied teams → capped point differential against the highest-finishing teams → fewest points allowed → coin flip) to determine seedings, and uses boolean minimization to reduce the scenario space into concise human-readable conditions. Ties are explained step by step with the actual results (`backend/helpers/tiebreak_explainer.py`): on each scenario card whose playoff seeding goes to the tiebreakers while 5 or fewer games remain, and in the standings once a region's games are all played. See [docs/architecture/SCENARIO_COMPUTATION.md](docs/architecture/SCENARIO_COMPUTATION.md) for how computation tiers, margin sensitivity, and the R threshold interact.
- Results are stored as dated snapshots so the API can answer historical "what were the odds on date X?" queries without recomputation.
- The FastAPI layer serves those snapshots for live requests, falls back to on-demand in-memory recomputation when no snapshot exists, and has what-if simulation endpoints that apply hypothetical results (owner only for now, like its win-probability, rankings and ratings endpoints: the public API serves what the site shows).
- Elo ratings with a margin-of-victory multiplier and cross-season carryover drive pregame win probability, while a separate in-game model uses score margin and time remaining (plus MHSAA's untimed alternating-possession OT format) for live probability estimates.

## Documentation

[docs/README.md](docs/README.md) lists every doc in one line each: how the engine works, the API reference, running the site, and the design briefs. The data model (each table, and the entity-relationship diagram) is in [docs/architecture/SCHEMA.md](docs/architecture/SCHEMA.md). Working on the code: [CONTRIBUTING.md](CONTRIBUTING.md).

## Prerequisites

Before starting, create accounts and note your credentials for:

- **Auth0** (auth0.com) — you'll need `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` from your tenant settings
- **Cloudinary** (cloudinary.com) — you'll need `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET`

## Setting Up Your Environment

### Backend

Local development runs the database, the API and Prefect in Docker. nginx is production-only: its config answers only for `mshsfootball.com` over HTTPS, so the local overlay (`docker-compose.local.yml`) leaves it out and publishes the API and the Prefect UI directly.

#### Configure Auth0

Auth0 issues the RS256 JWT tokens the API validates. For local development you need its **API resource** (the token's audience) and an **application** for signing in to Swagger UI; the `/moderate` page has its own on the server. [docs/operations/AUTH0_SETUP.md](docs/operations/AUTH0_SETUP.md) has every step.

#### Fill in the environment file

```
cp .env.example .env.local
```

Four values must be filled in; everything else has a working default or turns its feature off when blank:

| Variable | Value |
|---|---|
| `POSTGRES_PASSWORD` | Any strong password (`openssl rand -hex 32`). It's set when the database is first created; changing it later doesn't change an existing database's password. |
| `AUTH0_DOMAIN`, `AUTH0_AUDIENCE` | From Configure Auth0 |
| `SESSION_SECRET_KEY` | `openssl rand -hex 32` |

Keep `ENVIRONMENT=local` (Swagger UI on, local CORS) and `POSTGRES_HOST=db` (the database's name inside Docker). Leave `API_DB_*` and `PIPELINE_DB_*` blank unless you've created those roles (see [Database roles](docs/operations/VM_DEPLOYMENT.md#database-roles)); blank, the services connect as `POSTGRES_USER`. `CLOUDINARY_*` is only needed for image uploads and image URLs.

#### Start the containers

```
docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.local --profile local-db up --build -d
```

`--profile local-db` starts the local PostgreSQL container (`db`). On a VM with an external database, omit it.

| Service | Where |
|---|---|
| API | `http://localhost:8000`, Swagger UI at `http://localhost:8000/docs` |
| Prefect UI | `http://localhost:4200` |
| PostgreSQL | `localhost:5432` |
| Prefect worker | internal (runs the pipelines) |

All three are published on `127.0.0.1` only. Locally the Prefect UI needs no sign-in, since only your machine can reach it; on the server it's behind nginx at `/prefect/`, for the owner only: sign in at `/moderate` and use its **Prefect** link, which sets the session cookie that lets it open.

```
docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.local --profile local-db logs -f api
docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.local --profile local-db up --build -d api prefect-worker
```

The first streams the API's logs. The second picks up a code change: the code is copied into the images rather than mounted, so the API (`backend/api`, `backend/helpers`) and the worker (the pipelines) need a rebuild to see it.

> **Apple Silicon:** the overlay sets `OPENSSL_armcap=0` for the API and Prefect. Docker's Linux VM on Apple Silicon advertises CPU features that OpenSSL then tries to use but the VM can't run, so anything that loads it (the `cryptography` package, which the API's token checks and Prefect use) dies with "Illegal instruction" (exit code 132). The setting turns off OpenSSL's ARM feature detection; it's ignored on Intel, and production doesn't use it.

The site's pages need nginx (server-side includes, the static files, the routes), so they aren't served locally; the front-end's logic is covered by the JavaScript tests (see [Frontend](#frontend-2026-interim-ui)).

#### Promote yourself to owner

The owner role grants access to admin and moderation endpoints. Without it, your account is a base `user` and you won't be able to approve submissions, manage other users, or access the Prefect UI.

User rows are lazy-provisioned on the first authenticated API request, so you need to log in before the SQL update will find anything. Create your user in the Auth0 dashboard first (on the server, signing in once at `/moderate` does the same):

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
  "UPDATE users SET role = 'owner' WHERE auth0_id = 'auth0|YOUR_SUB_HERE';"
```

To reset the database and re-run the schema from scratch (e.g. after a schema change):

```
docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.local --profile local-db down -v
docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.local --profile local-db up --build -d
```

The `-v` flag removes the postgres data volume; the container will re-run `sql/init.sql` on startup.

#### Production / VM deployment

See [docs/operations/VM_DEPLOYMENT.md](docs/operations/VM_DEPLOYMENT.md) for the full AWS Lightsail setup guide (instance creation, DNS, SSL, the database roles and backups, and deploying updates).

#### Once per season (pre-season setup)

Run these in order — each depends on the previous step's data being in the database.

1. Open the Prefect UI (locally `http://localhost:4200`; on the server, the **Prefect** link on `/moderate`, signed in as the owner) and go to **Deployments**
2. Do a "Quick Run" of **Regions Data Flow** (`regions-data-pipeline`) — populates `school_seasons` (class/region assignments)
   - The pipeline defaults to the current year. Use a **Custom Run** in the Prefect UI to target a different season.
3. Do a "Quick Run" of **NCES School Geographic Data Flow** (`nces-school-pipeline`) — fills in city, zip, latitude, and longitude for all public schools from the NCES EDGE API, then applies the private-school location seed for schools not in NCES
4. Do a "Quick Run" of **MHSAA School Identity Data Flow** (`misshsaa-school-pipeline`) — scrapes mascot and primary/secondary colors from the MHSAA school directory
5. Run **AHSFHS Schedule Data Flow** (`ahsfhs-schedule-data-pipeline`) — writes the season's `games` rows from each school's AHSFHS schedule (a Quick Run is the current year; a Custom Run takes another season)
6. Run **Region Scenarios Data Flow** (`region-scenarios-data-pipeline`) for the same season — computes seeding odds, standings, and scenarios and writes the current snapshot to the database

Re-run steps 3-4 if schools move or rebrand. Re-run step 2 if MHSAA reclassifies schools (every two years). A new season's playoff bracket format is a separate step: see [New Season Setup](#new-season-setup).

The bracket structure for 2025 and 2026 (`playoff_formats`, `playoff_format_slots`) is seeded when the database is created, from `sql/seeds/playoff_formats_2025.sql` and `_2026.sql` (mounted into `docker-entrypoint-initdb.d` by `docker-compose.yml`). A later season is added by hand: see [New Season Setup](#new-season-setup).

#### Every day (automatic)

The `daily-update` deployment runs at 9:00 AM America/Chicago: it pulls the scores (**AHSFHS Schedule Data Flow**), then recalculates everything from them (**Region Scenarios Data Flow**, which writes `region_standings` and `region_scenarios`, runs **Playoff Bracket Update** for classes in the playoffs, and finishes by redrawing the share cards and page content). Nothing needs to be run by hand during the season.

To run either half on its own (after a fix, or to target another season with a **Custom Run**), use `ahsfhs-schedule-data-pipeline` or `region-scenarios-data-pipeline`. Both default to the current calendar year. The moderation digest email (7:00 AM) and a temporary Friday/Saturday score-timing probe are scheduled too; [docs/operations/PIPELINES.md](docs/operations/PIPELINES.md) lists every deployment and when to run each by hand.

#### After each playoff round

The daily update covers it: from a class's first completed playoff game on, the region run leaves that class's `region_standings` rows alone and finishes by running **Playoff Bracket Update** (`playoff-bracket-update`), which reads the completed playoff results, marks eliminated teams, and writes one `region_standings` snapshot per class/region dated to that round's game date. (The regular-season odds ignore playoff results, and a newer row would hide the playoff-aware ones.) Run `playoff-bracket-update` by hand only to refresh the playoff rows on their own.

#### Once per season (after importing a full historical season)

After steps 1–6, run **Backfill Historical Snapshots** (`backfill-historical-snapshots`, a Custom Run for the season) to write a snapshot for every game date, so past weeks show the odds as they stood then. It also runs **Playoff Bracket Update** for the playoff dates, and deletes the season's regular-season rows dated on days without games, which would otherwise shadow the game-date rows. Run it again after re-importing a season's games, and after a change to `MODEL_VERSION`, so past weeks use the current model. Each snapshot uses only the games played by its date (`get_standings_for_region` applies the date to every aggregate), so records and odds are as they were then.

### New Season Setup

When MHSAA reclassifies schools or consolidations occur mid-cycle, additional manual steps are required after the pipelines run. See [docs/operations/SEASON_SETUP.md](docs/operations/SEASON_SETUP.md) for the full guide covering playoff bracket format seeding and school consolidation/closure procedures.

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
```

### Testing

CI (`.github/workflows/ci.yml`) runs on every pull request and every push to `main`, and a PR should be green before it's merged:

- **tests:** `ruff check backend`, the Python tests, and the JavaScript tests (`node --test nginx/tests/*.test.mjs`).
- **images:** both compose files resolve, the API and worker images build, the API image imports as a non-root user, a real Prefect flow runs in the worker image, and nginx accepts its config.

To run the Python tests the way CI does (in parallel, without coverage; the fastest way through the whole suite):

```
uv run pytest backend/tests -q -p no:cacheprovider -o addopts="" -n auto
```

With coverage, which `pyproject.toml` turns on by default (slower: one process):

```
uv run pytest
```

Or with verbose output:

```
uv run pytest -vv
```

Coverage is measured with branch analysis and reported in the terminal after every run. It covers `backend/helpers/`, except `database_helpers.py` and `web_helpers.py`; the Prefect pipelines and the API (`backend/api/`), which need a live database or Prefect, are left out (`[tool.coverage]` in `pyproject.toml`).

To generate a browsable HTML report:

```
uv run pytest --cov-report=html
open htmlcov/index.html
```

### Frontend (2026 interim UI)

The public site is static HTML/CSS/JS served by nginx from `nginx/html/`, with no build step. [docs/architecture/FRONTEND.md](docs/architecture/FRONTEND.md) covers the pages, how each is drawn twice (ahead of time in Python for search engines and link previews, then by the app), the JavaScript modules, styles and fonts. Its look follows the design system in [docs/design/2026_INTERIM_UI_BRIEF.md](docs/design/2026_INTERIM_UI_BRIEF.md) (§§2–7).

The pages take these query parameters: `season`, `week` (a past week's snapshot; omitted = latest), `odds=tossup` (default is Projected, the Elo-weighted columns), and `team` (opens that team's playoff path and shows only its scenarios).

```
node --test nginx/tests/*.test.mjs
```

### Docstring coverage

Check that all public functions and modules have docstrings:

```
uv run docstr-coverage backend -e "backend/prefect/|backend/tests" --skip-magic --skip-init
```

That leaves out the Prefect pipelines and the tests, and skips magic methods and `__init__` (docstr-coverage doesn't read `pyproject.toml`, so the options go on the command line). It prints the current coverage and lists what's missing.

### API Reference

Interactive docs are at [localhost:8000/docs](http://localhost:8000/docs) when the server is running. For the complete endpoint reference see [docs/reference/API_REFERENCE.md](docs/reference/API_REFERENCE.md).

Key endpoints summary (**owner** marks the ones only the owner can call; see the reference's opening note):
- `/api/v1/standings/{clazz}/{region}` — seeding odds + scenarios + bracket/home-game odds snapshots
- `/api/v1/standings/{clazz}` — full standings tables for every region in one class, no scenarios
- `/api/v1/standings/summary` — statewide grand-view summary: leader, clinch/elimination counts, and volatility per region across every class
- `/api/v1/hosting/{clazz}/{region}` — playoff hosting odds (p_host_given_reach + p_host_overall, raw + Elo-weighted) per round
- `/api/v1/bracket` — bracket advancement odds per (region, seed) slot, including Elo-weighted advancement, non-weighted and weighted hosting odds per round
- `/api/v1/bracket/matchups` — who might play whom, and where, in every game of a class's bracket (the bracket page)
- `/api/v1/bracket/slots/{slot}` — every team still alive for one bracket slot/round pre-clinch, ranked by chance of reaching it, with raw + Elo-weighted reach/hosting odds
- `/api/v1/seasons/{season}/dates` — notable game dates for a timeline scrubber (round, week, game count, human `description`); optional `class` filter resolves 1A-4A/5A-7A's offset playoff schedules unambiguously
- **owner:** `/api/v1/rankings/{clazz}` (cross-region ranked list by any odds metric or Elo/RPI, with rank movement) and `/api/v1/ratings` (Elo and RPI snapshots per team)
- **owner:** the `…/simulate` endpoints under standings, hosting and bracket, which apply hypothetical results (by school name; the bracket and hosting ones also take (region, seed) slot references)

## Disclaimer

Win probabilities, seeding odds, and playoff advancement percentages are statistical estimates for informational and entertainment purposes only — not gambling advice. See [docs/reference/ODDS_DISCLAIMER.md](docs/reference/ODDS_DISCLAIMER.md) for full details.

## License

Copyright © 2025–2026 Paul Sullivan. All rights reserved.

The code is public so anyone can read it and see how the site works, but it's source-available, not open source: using, copying or hosting it needs the author's written permission. Third-party components keep their own licenses. See [LICENSE](LICENSE).
