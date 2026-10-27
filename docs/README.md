# Documentation

Setting up a local copy is in [LOCAL_DEVELOPMENT.md](operations/LOCAL_DEVELOPMENT.md);
working on the code is in [CONTRIBUTING.md](../CONTRIBUTING.md).

## How it works (`architecture/`)

| Doc | What's in it |
|---|---|
| [SCENARIO_RULES.md](architecture/SCENARIO_RULES.md) | The MHSAA region tiebreaker procedure the engine implements, with the handbook text. |
| [PLAYOFF_HOME_RULES.md](architecture/PLAYOFF_HOME_RULES.md) | MHSAA's rules for which team hosts each playoff round. |
| [SCENARIO_COMPUTATION.md](architecture/SCENARIO_COMPUTATION.md) | What the engine computes and stores at each number of games left: odds, scenarios, insights, tie explanations, and when 0% and 100% are shown. |
| [SCHEMA.md](architecture/SCHEMA.md) | Every table, and the entity-relationship diagram. |
| [FRONTEND.md](architecture/FRONTEND.md) | The site's pages, how each is drawn ahead of time and again by the app, and the JavaScript modules. |
| [CALIBRATION_DATA.md](architecture/CALIBRATION_DATA.md) | The archive of odds as published, for measuring how often they came true. |

## Reference (`reference/`)

| Doc | What's in it |
|---|---|
| [API_REFERENCE.md](reference/API_REFERENCE.md) | Every endpoint, its parameters and response fields, and which are owner-only. |
| [ANALYTICS.md](reference/ANALYTICS.md) | What the site counts in PostHog, how it's wired, and the dashboard. |
| [ODDS_DISCLAIMER.md](reference/ODDS_DISCLAIMER.md) | What the odds are, and that they aren't for gambling. |

## Running the site (`operations/`)

| Doc | What's in it |
|---|---|
| [LOCAL_DEVELOPMENT.md](operations/LOCAL_DEVELOPMENT.md) | Running the database, the API and Prefect locally in Docker, and making yourself the owner. |
| [VM_DEPLOYMENT.md](operations/VM_DEPLOYMENT.md) | The server: setup, HTTPS, database roles, backups, deploying updates, share cards, moderation and spam protection. |
| [PIPELINES.md](operations/PIPELINES.md) | Every Prefect deployment and script, its schedule, and when to run it by hand. |
| [SEASON_SETUP.md](operations/SEASON_SETUP.md) | A new season's playoff format, championship venues, school consolidations and renames, data corrections. |
| [AUTH0_SETUP.md](operations/AUTH0_SETUP.md) | Every Auth0 piece (the API, the Swagger and `/moderate` applications) and user roles. |
| [DEPLOYMENT_SECURITY.md](operations/DEPLOYMENT_SECURITY.md) | The security checklist: what's done on the server, and what's still open. |
| [SEO.md](operations/SEO.md) | How the site presents itself to search engines, and what to do outside the code. |
| [API_TESTING_CHECKLIST.md](operations/API_TESTING_CHECKLIST.md) | Spot checks to run after loading a full season. |

## Design (`design/`)

The 2026 interim UI briefs, in order. Each opens with its status.

| Doc | What's in it |
|---|---|
| [2026_INTERIM_UI_BRIEF.md](design/2026_INTERIM_UI_BRIEF.md) | The design system (§§2–7), which still governs the site. |
| [2026_INTERIM_UI_UPDATE.md](design/2026_INTERIM_UI_UPDATE.md) | The URL shape, the bracket view and share images. |
| [2026_INTERIM_UI_BRIEF_V3.md](design/2026_INTERIM_UI_BRIEF_V3.md) | Pre-rendered pages, the visible Elo rating, the About page's limits, labeling rules. |

## Proposals (`proposals/`)

| Doc | What's in it |
|---|---|
| [LIVE_SCORES_PROPOSAL.md](proposals/LIVE_SCORES_PROPOSAL.md) | A design for live scores from X/Twitter. Not built. |

Elsewhere: [SECURITY.md](../SECURITY.md) (reporting a vulnerability) and
[backend/assets/fonts/README.md](../backend/assets/fonts/README.md) (the fonts and their licenses).
