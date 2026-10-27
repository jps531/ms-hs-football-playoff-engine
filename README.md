# ms-hs-football-playoff-engine

Standings, playoff odds and scenarios for Mississippi high school football
(MHSAA), published at [mshsfootball.com](https://mshsfootball.com).

## How it works

- **Data.** Prefect pipelines load region assignments and school identity from MHSAA, school locations from the NCES EDGE API, and schedules and scores from AHSFHS into PostgreSQL ([PIPELINES.md](docs/operations/PIPELINES.md)).
- **The engine.** For each region it works through the remaining games (every outcome while 15 or fewer are left, every winning margin while 5 or fewer are; 50,000 simulated seasons per odds mode above 15), applies the [MHSAA tiebreaker procedure](docs/architecture/SCENARIO_RULES.md) to each, and reduces the results to short, readable conditions. Ties are explained step by step with the actual results ([SCENARIO_COMPUTATION.md](docs/architecture/SCENARIO_COMPUTATION.md)).
- **Two kinds of odds.** Toss-up treats every remaining game as a coin flip; Projected weights each by the teams' Elo ratings (with a margin-of-victory multiplier, carried over between seasons).
- **Snapshots.** Results are stored by date, so a past week shows the odds as they stood then (`region_standings` in [SCHEMA.md](docs/architecture/SCHEMA.md)).
- **The site and API.** FastAPI serves the snapshots; the site is static HTML and JavaScript served by nginx, with each page also drawn ahead of time for search engines and link previews ([FRONTEND.md](docs/architecture/FRONTEND.md)).

## Quick start

The database, the API and Prefect run locally in Docker.

1. Set up Auth0's API resource and Swagger UI application: sections 1 and 2 of [AUTH0_SETUP.md](docs/operations/AUTH0_SETUP.md).
2. `cp .env.example .env.local`, then fill in `POSTGRES_PASSWORD`, `AUTH0_DOMAIN`, `AUTH0_AUDIENCE` and `SESSION_SECRET_KEY`.
3. Start the containers:

   ```
   docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.local --profile local-db up --build -d
   ```

4. Open Swagger UI at `http://localhost:8000/docs` and the Prefect UI at `http://localhost:4200`.

[LOCAL_DEVELOPMENT.md](docs/operations/LOCAL_DEVELOPMENT.md) has the rest: what each setting does, loading data, rebuilding after a change, making yourself the owner, resetting the database, and a fix for Apple Silicon.

## Running the site

- **The server:** [VM_DEPLOYMENT.md](docs/operations/VM_DEPLOYMENT.md): setup, HTTPS, backups, deploying updates.
- **The pipelines:** [PIPELINES.md](docs/operations/PIPELINES.md): what runs before a season, and every deployment. The daily update runs on its own at 9:00 AM Central, so nothing needs running by hand during the season.
- **A new season:** [SEASON_SETUP.md](docs/operations/SEASON_SETUP.md): the playoff format, venues, school consolidations and renames.

## Working on the code

```
uv sync --dev
uv run --frozen ruff check backend
uv run pytest backend/tests -q -p no:cacheprovider -o addopts="" -n auto
node --test nginx/tests/*.test.mjs
```

The last three are CI's lint and tests (it also builds the images); a PR should be green before it's merged. [CONTRIBUTING.md](CONTRIBUTING.md) has the rules (above all: everything a reader sees must be true), what must change together, and the other tools.

## Documentation

[docs/README.md](docs/README.md) lists every doc in a line each. The endpoints are in [API_REFERENCE.md](docs/reference/API_REFERENCE.md); the tables in [SCHEMA.md](docs/architecture/SCHEMA.md).

## Disclaimer

Win probabilities, seeding odds, and playoff advancement percentages are statistical estimates for informational and entertainment purposes only — not gambling advice. See [docs/reference/ODDS_DISCLAIMER.md](docs/reference/ODDS_DISCLAIMER.md) for full details.

## License

Copyright © 2025–2026 Paul Sullivan. All rights reserved.

The code is public so anyone can read it and see how the site works, but it's source-available, not open source: using, copying or hosting it needs the author's written permission. Third-party components keep their own licenses. See [LICENSE](LICENSE).
