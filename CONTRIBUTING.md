# Contributing

How changes are made here. Local setup is in the [README](README.md); every doc
is listed in [docs/README.md](docs/README.md).

## First: everything a reader sees must be true

The site's case rests on its numbers and sentences being right. A page, a card,
an API field or a doc that says something untrue is a bug, whatever its size:

- Don't state what the engine hasn't established. Scenarios, insights and
  headlines say only what holds; 0% and 100% appear only for certainties
  ([SCENARIO_COMPUTATION.md](docs/architecture/SCENARIO_COMPUTATION.md#certainty-when-a-chance-reads-0-or-100)).
- When code changes what something does, change what it says in the same PR:
  the page text, the API reference, the docs, the comments.
- In a PR description, quote any change to wording people read (pages, cards,
  emails), so it can be reviewed as wording.

## Pull requests

- **One topic per PR.** A fix found along the way that's off topic gets its own PR.
- **CI must be green** before merging (`.github/workflows/ci.yml`): lint, the
  Python and JavaScript tests, both compose files, the image builds, and nginx's
  config. Run the same locally first:

  ```
  uv run --frozen ruff check backend
  uv run pytest backend/tests -q -p no:cacheprovider -o addopts="" -n auto
  node --test nginx/tests/*.test.mjs
  ```

- **Say what a deploy needs** in the description when it needs more than a pull and
  a rebuild: a migration, a new setting, a backfill, a file installed by hand.
  [VM_DEPLOYMENT.md](docs/operations/VM_DEPLOYMENT.md#deploying-updates) is the checklist.
- Commit messages say why, not only what.

## Things that must change together

| When you change… | …also change |
|---|---|
| A page's content, a card, or a label in the JavaScript (`nginx/html/static/js/`) | Its Python mirror in `backend/helpers/static_pages.py` (pre-rendered pages) and both sets of tests ([FRONTEND.md](docs/architecture/FRONTEND.md)). The share cards' text helpers mirror `format.js` the same way. |
| An analytics event or property | [ANALYTICS.md](docs/reference/ANALYTICS.md)'s table and the About page's description (`nginx/html/about.html#measure`). |
| An endpoint, a parameter or a response field | [API_REFERENCE.md](docs/reference/API_REFERENCE.md), and the README's key endpoints if it's listed there. |
| The database schema | `sql/init.sql` (new databases), a migration in `sql/migrations/` (existing ones), and [SCHEMA.md](docs/architecture/SCHEMA.md). A migration starts with a header saying how to apply it and is safe to run more than once. |
| Anything that changes the odds themselves (Elo, home-field advantage, tiebreakers, simulation counts, bracket or hosting rules) | Bump `MODEL_VERSION` in `backend/prefect/region_scenarios_pipeline.py`, and say in the PR that past seasons need `backfill-historical-snapshots` ([CALIBRATION_DATA.md](docs/architecture/CALIBRATION_DATA.md)). |
| A setting read from the environment | `.env.example`, the service's `environment:` in `docker-compose.yml`, and the doc for the feature. |
| A Prefect deployment or its schedule | [PIPELINES.md](docs/operations/PIPELINES.md). |

## Don't

- **Don't commit the Nippo font.** Its license doesn't allow it in a public
  repository; the files are git-ignored and installed on the server by hand
  ([backend/assets/fonts/README.md](backend/assets/fonts/README.md)).
- **Don't commit secrets**: `.env.local`, API keys, PostHog personal keys. Only
  `.env.example`, with blank or placeholder values, is tracked.
- **Don't skip or weaken a test to get green.** Fix the cause.
