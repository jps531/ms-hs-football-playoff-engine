# Contributing

How changes are made here. Local setup is in
[LOCAL_DEVELOPMENT.md](docs/operations/LOCAL_DEVELOPMENT.md); every doc
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

- **Say what a deploy needs** in the description when it needs more than the automatic deploy
  does (images, migrations, restarts: [VM_DEPLOYMENT.md](docs/operations/VM_DEPLOYMENT.md#automatic-deploys)):
  a new setting in `.env.local`, a backfill, a `share-assets` run, a file installed by hand.
- Commit messages say why, not only what.

## Tools

The project uses [uv](https://docs.astral.sh/uv/) for dependencies and
[ruff](https://docs.astral.sh/ruff/) for linting and formatting. `uv sync --dev`
installs everything into `.venv`.

```
uv run ruff check .          # lint
uv run ruff check --fix .    # auto-fix safe issues
uv run ruff format .         # format
```

**Tests.** The CI command above runs the Python suite in parallel without
coverage, the fastest way through it. Plain `uv run pytest` (add `-vv` for
verbose output) runs in one process with coverage, which `pyproject.toml` turns
on by default: branch coverage of `backend/helpers/`, except `database_helpers.py`
and `web_helpers.py`. The Prefect pipelines and the API (`backend/api/`), which
need a live database or Prefect, are left out (`[tool.coverage]`). For a
browsable report: `uv run pytest --cov-report=html`, then open `htmlcov/index.html`.

**Docstrings.** Every module, class and function in `backend/` has one, tests and
nested helpers included. To check (`-v 3` lists anything missing):

```
uv run docstr-coverage backend --skip-magic --skip-init
```

That skips magic methods and `__init__` (docstr-coverage doesn't read
`pyproject.toml`, so the options go on the command line). To leave a folder out,
`-e` takes a pattern matched against the full path from its start, so it needs a
leading `.*`: `-e ".*/(prefect|tests)/.*"` checks only the API and helpers.

## Things that must change together

| When you change… | …also change |
|---|---|
| A page's content, a card, or a label in the JavaScript (`nginx/html/static/js/`) | Its Python mirror in `backend/helpers/static_pages.py` (pre-rendered pages) and both sets of tests ([FRONTEND.md](docs/architecture/FRONTEND.md)). The share cards' text helpers mirror `format.js` the same way. `renderer_parity_test.py` fails if the two disagree. |
| A setting the site states in words (`backend/helpers/engine_settings.py`: the games-left cutoffs, the sample count, the 0.5% listing floor; the daily update's hour in `flows.py`) | The wording on About, the front page, the footers and in `app.js`. `copy_settings_test.py` fails until they match. |
| The header, tab bar or footer of one HTML page | The same lines in the other three (`index.html`, `about.html`, `404.html`, `moderate.html`); `page_chrome_test.py` lists the differences that are on purpose. |
| A feedback form limit (`feedback.js`) | The API's field limit in `backend/api/models/requests.py`, and the other way round. |
| An analytics event or property | [ANALYTICS.md](docs/reference/ANALYTICS.md)'s table and the About page's description (`nginx/html/about.html#measure`). |
| An endpoint, a parameter or a response field | [API_REFERENCE.md](docs/reference/API_REFERENCE.md). |
| The database schema | `sql/init.sql` (new databases), a migration in `sql/migrations/` (existing ones), and [SCHEMA.md](docs/architecture/SCHEMA.md). A migration is named `NNNN_name.sql`, the next number after the last (`0001_add_thing.sql`, `0002_...`), starts with a header saying what it does, and is safe to run more than once: `scripts/migrate.py` applies each once, in number order, on the server, and a new database gets it from `init.sql` and then runs it too. |
| Anything that changes the odds themselves (Elo, home-field advantage, tiebreakers, simulation counts, bracket or hosting rules) | Bump `MODEL_VERSION` in `backend/prefect/region_scenarios_pipeline.py`, and say in the PR that past seasons need `backfill-historical-snapshots` ([CALIBRATION_DATA.md](docs/architecture/CALIBRATION_DATA.md)). |
| A setting read from the environment | `.env.example`, the service's `environment:` in `docker-compose.yml`, and the doc for the feature. |
| A Prefect deployment or its schedule | [PIPELINES.md](docs/operations/PIPELINES.md). |
| The site's version (`backend/version.py`) | `pyproject.toml` (then `uv lock`), the footer of the four HTML pages, and an entry in [CHANGELOG.md](CHANGELOG.md). `version_test.py` fails until they match. See [Releases](#releases). |

## Releases

The site's version (`VERSION` in `backend/version.py`, shown in every page's footer) is MAJOR.MINOR.PATCH:
MAJOR for a change in what the site is (a new sport, a redesign), MINOR for a new feature or a change
in how the numbers are worked out, PATCH for a fix. It is not `MODEL_VERSION`
(`region_scenarios_pipeline.py`), which marks snapshots computed by a different odds model.

A PR that changes what readers get bumps it, with its CHANGELOG.md entry, in that same PR; a PR that
changes only docs, tests or tooling doesn't. Once it merges and CI passes on main, the Release workflow
(`.github/workflows/release.yml`, `scripts/release.py`) tags the merge commit `vX.Y.Z` and publishes a
GitHub release with the CHANGELOG entry as its notes; a merge that doesn't bump the version releases
nothing. Older versions without a release are released with `scripts/backfill_releases.sh`, run once
from a checkout of `main` with the GitHub CLI signed in as you: each at the commit where it first
appeared. It can't run in Actions, whose token isn't allowed to create a tag on an old commit (one whose
workflow files differ from `main`'s).

## Feature flags

A change to the pages can ship switched off, be tried on the live site by you alone, and then be
released to everyone. Every visitor sees the same thing; nothing is stored in a browser to choose who
sees what, so there are no percentage rollouts or A/B tests.

The version and the CHANGELOG say what readers get, so they change when a flagged change is released,
not when its code ships switched off. A release is a PR, not the toggle: that way the change, the
footer's version and the CHANGELOG entry reach readers in the same deploy.

1. **Declare it** in `FLAGS` in `backend/helpers/feature_flags.py`: a name (`lowercase_words`) and what
   it switches on, in words you'll recognize on `/moderate`.
2. **Check it** in the page's code: `if (await feature("new_bracket_view")) { … }` (`features.js`).
   Keep the old way working while it's off: that's what everyone sees. The check waits for the client
   config the page already loads, so draw the old way, or nothing, until it answers rather than drawing
   one and swapping.
3. **Ship it off.** Merge and deploy. Readers see no change, so the PR doesn't bump the version.
4. **Try it on yourself:** under Feature flags on `/moderate`, choose **Only me**. It shows in the
   browsers where you've opened `/moderate`, signed in, in the last day (the owner's session cookie), and
   nowhere else. A page picks a change up the next time it loads; **Off** puts it back.
5. **Release it** with a go-live PR that deletes the check, the old way and the `FLAGS` entry together,
   and bumps the version with the CHANGELOG entry for the change. Once that deploys, it's part of the
   site for everyone. To take it back after that, revert the PR, or deploy the previous commit again
   (Actions → Deploy → Run workflow).

**Everyone** turns a flag on for all readers without a deploy, ahead of its go-live PR: for a short
trial with an instant off switch (a busy game night, say). Readers then see a change the version and the
CHANGELOG don't mention yet, so keep it short: merge the go-live PR within a day or so, or turn it back
off.

`feature_flags_test.py` fails if a page checks a flag that isn't declared (a typo would be off forever)
or a declared flag is checked nowhere (a toggle that does nothing). The server-rendered parts of a page
(`static_pages.py`) can't check a flag: they're drawn once for everyone, before anyone's browser asks.

## Branches

Trunk-based: `main` is what's live, and every change reaches it through a pull request from a
short-lived branch, merged once CI passes. `main`'s protection (Settings → Rules → Rulesets, targeting
the default branch):

- **Require a pull request before merging** (with 0 required approvals: GitHub doesn't let an author
  approve their own PR, so for one maintainer the checks are the gate).
- **Require status checks to pass**, with the branch up to date: `tests` and `images` (CI).
- **Block force pushes** and **restrict deletions**.
- **Allowed merge method: squash**, so `main` reads as one commit per pull request.

The Release workflow pushes only tags, which the rules above don't cover, so it needs no bypass.

## Don't

- **Don't commit the Nippo font.** Its license doesn't allow it in a public
  repository; the files are git-ignored and installed on the server by hand
  ([backend/assets/fonts/README.md](backend/assets/fonts/README.md)).
- **Don't commit secrets**: `.env.local`, API keys, PostHog personal keys. Only
  `.env.example`, with blank or placeholder values, is tracked.
- **Don't skip or weaken a test to get green.** Fix the cause.
