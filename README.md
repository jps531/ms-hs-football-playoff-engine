# ms-hs-football-playoff-engine

An application that calculates standings and playoff scenarios for Mississippi high school football (MHSAA).

## How It Works

- Four Prefect pipelines ingest data from MHSAA (region assignments and school identity), the NCES EDGE API (school locations), and AHSFHS (schedules) into PostgreSQL.
- Once game results are in, the tiebreaker engine works through the remaining region games (every outcome while there are 15 or fewer, and every winning margin while there are 5 or fewer; 50,000 simulated seasons per odds mode above 15), applies the [6-step MHSAA tiebreaker procedure](docs/architecture/SCENARIO_RULES.md) (head-to-head → results against the highest-finishing teams → capped point differential among the tied teams → capped point differential against the highest-finishing teams → fewest points allowed → coin flip) to determine seedings, and uses boolean minimization to reduce the scenario space into concise human-readable conditions. Ties are explained step by step with the actual results (`backend/helpers/tiebreak_explainer.py`): on each scenario card whose playoff seeding goes to the tiebreakers while 5 or fewer games remain, and in the standings once a region's games are all played. See [docs/architecture/SCENARIO_COMPUTATION.md](docs/architecture/SCENARIO_COMPUTATION.md) for how computation tiers, margin sensitivity, and the R threshold interact.
- Results are stored as dated snapshots so the API can answer historical "what were the odds on date X?" queries without recomputation.
- The FastAPI layer serves those snapshots for live requests, falls back to on-demand in-memory recomputation when no snapshot exists, and has what-if simulation endpoints that apply hypothetical results (owner only for now, like its win-probability, rankings and ratings endpoints: the public API serves what the site shows).
- Elo ratings with a margin-of-victory multiplier and cross-season carryover drive pregame win probability, while a separate in-game model uses score margin and time remaining (plus MHSAA's untimed alternating-possession OT format) for live probability estimates.

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
| `region_standings` | Dated snapshots of seeding odds (1st–4th, raw and strength-weighted), playoff odds, playoff bracket advancement odds (2nd round through champion, raw and Elo-weighted), and [home-game odds per round](docs/architecture/PLAYOFF_HOME_RULES.md) (raw and Elo-weighted). One snapshot per school per date: a rerun on the same day replaces that day's rows, and `region_standings_archive` keeps every version written. |
| `team_ratings` | Dated Elo and RPI snapshots. One row per school per season per `as_of_date`. |
| `region_scenarios` | Serialized tiebreaker scenario trees (complete outcomes + minimized per-team conditions) plus pre-computed key insights (simple, unconditionally-true conditional statements like "Taylorsville clinches 1st seed: Taylorsville beats Stringer"). Computed once per pipeline run, read at request time. |
| `region_computation_state` | Per region and snapshot date: how many region games remained, whether every winning margin was worked through (5 or fewer left), and when it was computed. |
| `region_seed_pairs` | Per region and snapshot date: the chance that two teams land on two given seeds together, which the bracket matchups need. |
| `region_standings_archive` | Append-only copy of every write to `region_standings`, for measuring published odds against results (see [docs/architecture/CALIBRATION_DATA.md](docs/architecture/CALIBRATION_DATA.md)). |
| `team_logos` | Per-school logo asset history (primary, secondary, tertiary lines), mirroring `helmet_designs`. |
| `playoff_formats` | Bracket template per class/season: size, number of regions, rounds. |
| `playoff_format_slots` | First-round matchup slots. Adjacent pairs implicitly define the bracket tree for round-2 and beyond. |
| `championship_venues` | One row per season/class recording which location hosts (or hosted) that class's championship game. Independent of `games` — can be set before that season's Championship Game rows exist; an explicit `games.location_id` wins over this table when both are present. |
| `submissions` | User-submitted corrections and new assets (logos, helmet designs, colors, GPS coordinates, scores, feedback). Rows enter the queue with `status='pending'` and are approved or rejected by a moderator via the moderation API. Approved submissions are auto-applied to the live tables (except helmet submissions, which require manual mockup creation). Has an optional `user_id` FK for linking submissions to registered users. |
| `users` | Registered user accounts with role (`user`/`moderator`/`owner`), profile fields (display name, phone, hometown), and a favorite team FK. Identity is managed by Auth0; `auth0_id` stores the Auth0 `sub` claim. Rows are lazy-provisioned on first authenticated request. |
| `user_followed_teams` | Many-to-many join between users and the schools they follow. |
| `user_attended_games` | Many-to-many join between users and games they marked as attended. References the composite PK `(school, date)` on `games`. |

See [docs/architecture/SCHEMA.md](docs/architecture/SCHEMA.md) for the full entity-relationship diagram.

## Prerequisites

Before starting, create accounts and note your credentials for:

- **Auth0** (auth0.com) — you'll need `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` from your tenant settings
- **Cloudinary** (cloudinary.com) — you'll need `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET`

## Setting Up Your Environment

### Backend

Local development runs the database, the API and Prefect in Docker. nginx is production-only: its config answers only for `mshsfootball.com` over HTTPS, so the local overlay (`docker-compose.local.yml`) leaves it out and publishes the API and the Prefect UI directly.

#### Configure Auth0

Auth0 issues the RS256 JWT tokens the API validates. You need an **API resource** (sets the audience claim) and an **Application** (sets your domain and gives you Swagger UI login credentials). See [docs/operations/AUTH0_SETUP.md](docs/operations/AUTH0_SETUP.md) for step-by-step instructions.

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

See [docs/operations/VM_DEPLOYMENT.md](docs/operations/VM_DEPLOYMENT.md) for the full AWS Lightsail setup guide (instance creation, DNS, SSL, Auth0 URL updates, and deploying updates).

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

To backfill a **completed historical season** after steps 1-6, continue with the steps below.

The `playoff_formats` and `playoff_format_slots` tables (which define the bracket structure) are **automatically seeded for 2025 and 2026** when the database is created — `sql/seeds/playoff_formats_2025.sql` and `sql/seeds/playoff_formats_2026.sql` are mounted as `docker-entrypoint-initdb.d` volumes in `docker-compose.yml` (with numeric prefixes, `05_`/`06_`, added at the mount target to control init order — the source filenames themselves have no prefix). No manual step is needed. See [New Season Setup](#new-season-setup) below for adding a future season.

#### Every day (automatic)

The `daily-update` deployment runs at 9:00 AM America/Chicago: it pulls the scores (**AHSFHS Schedule Data Flow**), then recalculates everything from them (**Region Scenarios Data Flow**, which writes `region_standings` and `region_scenarios`, runs **Playoff Bracket Update** for classes in the playoffs, and finishes by redrawing the share cards and page content). Nothing needs to be run by hand during the season.

To run either half on its own (after a fix, or to target another season with a **Custom Run**), use `ahsfhs-schedule-data-pipeline` or `region-scenarios-data-pipeline`. Both default to the current calendar year. The moderation digest email (7:00 AM) and a temporary Friday/Saturday score-timing probe are scheduled too; [docs/operations/PIPELINES.md](docs/operations/PIPELINES.md) lists every deployment and when to run each by hand.

#### After each playoff round

The daily update covers it: from a class's first completed playoff game on, the region run leaves that class's `region_standings` rows alone and finishes by running **Playoff Bracket Update** (`playoff-bracket-update`), which reads the completed playoff results, marks eliminated teams, and writes one `region_standings` snapshot per class/region dated to that round's game date. (The regular-season odds ignore playoff results, and a newer row would hide the playoff-aware ones.) Run `playoff-bracket-update` by hand only to refresh the playoff rows on their own.

#### Once per season (after importing a full historical season)

After the pre-season setup steps (1–6) have completed for a season, run the following two pipelines to build a full per-gameday snapshot history:

7. **Backfill Historical Snapshots** (Custom Run, target season) — writes `team_ratings`, `region_standings`, `region_scenarios`, `region_seed_pairs` and `region_computation_state` rows for every unique game-date in the season so the timeline API can serve historical odds for any past date without recomputation, then deletes the season's regular-season rows dated on days without games (the daily update's rows, which would otherwise shadow the game-date rows it just wrote; each had the same games as the game date before it). Run it once per season, again after re-importing a full season's games, and after a model change so past weeks use the current model. Both the seeding odds and W/L records in each snapshot are historically accurate — the `get_standings_for_region` stored proc applies a date filter to all aggregations.

8. **Playoff Bracket Update** (Custom Run, target season) — self-backfilling: reads all completed playoff games and writes one `region_standings` snapshot per playoff round date with deterministic 1.0/0.0 seedings. Requires step 6 to have populated `region_standings` with `clinched` flags first. Step 7 now runs this itself as its last step (and skips each class's playoff dates beforehand), so a separate run is only needed to refresh playoff rows on their own.

> **Season parameter:** Both pipelines default to the current calendar year. Use a **Custom Run** in the Prefect UI to target a different season.

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

The public site is static HTML/CSS/JS served by nginx from `nginx/html/` — no build step. Its look and feel follow the design system in [docs/design/2026_INTERIM_UI_BRIEF.md](docs/design/2026_INTERIM_UI_BRIEF.md) (§§2–7: what to avoid, color, type, components, pages, accessibility). That brief's scope (§1) has since been widened by its follow-ups, [docs/design/2026_INTERIM_UI_UPDATE.md](docs/design/2026_INTERIM_UI_UPDATE.md) and [docs/design/2026_INTERIM_UI_BRIEF_V3.md](docs/design/2026_INTERIM_UI_BRIEF_V3.md), which added the brackets and share images among other things.

- `index.html` — the front page (`/`), the class view (`/standings/7a`), the region view (`/standings/7a/2`) and the bracket (`/brackets/7a`), rendered by `static/js/app.js` from the public `/api/v1` endpoints. Optional parameters: `season`, `week` (a past week's snapshot; omitted = latest), `odds=tossup` (default is Projected, the Elo-weighted columns), and `team` (opens that team's playoff path and shows only its scenarios — set by the header's team search or by picking the team's row)
- `about.html` — served at `/about` (`/methodology`, its old address, redirects there)
- `static/js/format.js`, `components.js`, `scenarios.js`, `standings.js` — pure, DOM-free modules (honest odds rounding, the odds ramp, badges, condition chips, outcome cards, tie-aware positions, playoff paths, region results), tested with Node's built-in runner:

```
node --test nginx/tests/*.test.mjs
```

Both fonts are self-hosted in `static/fonts/`: Inter (SIL OFL) and Nippo, the display face (ITF Free Font License). Nippo's license doesn't allow it in a public repository, so it's installed on the server by hand and titles fall back to Inter without it; see [backend/assets/fonts/README.md](backend/assets/fonts/README.md).

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
