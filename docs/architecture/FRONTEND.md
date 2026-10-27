# Frontend

How the public site's pages are put together: static files nginx serves, a
JavaScript app that renders from the public API, and a copy of each page's
content written ahead of time so it reads without JavaScript. The look and
feel follow the design system in
[2026_INTERIM_UI_BRIEF.md](../design/2026_INTERIM_UI_BRIEF.md) (§§2–7).

There is no build step: what's in `nginx/html/` is what's served.

## Pages

| Route | File | What draws it |
|---|---|---|
| `/` | `index.html` | The front page: written by the pipeline (`landing_body` in `backend/helpers/static_pages.py`) and fetched as `/share/front.html`; `landing.js` holds the fallback for when it isn't there. |
| `/standings/{class}a`, `/standings/{class}a/{region}`, `/brackets/{class}a` | `index.html` | `static/js/app.js`, from the `/api/v1` endpoints, reading the path and query (`routes.js`). |
| `/feedback` | `index.html` | `app.js`, with `feedback.js` and `turnstile.js`. |
| `/about` | `about.html` | Plain HTML. `/methodology`, its old address, redirects there. |
| `/moderate` | `moderate.html` | `moderate.js` (with `auth.js` and `moderation.js`), after an Auth0 sign-in. |
| anything else | `404.html` | A real 404 status (nginx only sends the app its page routes). |

## Each page is drawn twice, the same way

1. **Ahead of time, in Python.** After the daily update, the share-assets
   pipeline (`backend/prefect/share_assets_pipeline.py`) reads the site's own
   API and writes, into a volume nginx serves:
   - each page's content as HTML (`body/*.html`, drawn by `backend/helpers/static_pages.py`);
   - its `<head>` tags (`meta/*.html`): title, description, share-card tags;
   - its share card (`og/*.png`, `backend/helpers/share_cards.py`);
   - `sitemap.xml`.
2. **In the browser, in JavaScript.** nginx serves `index.html` with
   server-side includes that splice the page's `meta` file into `<head>` and its
   `body` file into `<main>`. Search engines, link previews and browsers without
   JavaScript get the real race. The app then replaces `<main>` with the same
   markup it draws itself, so nothing moves.

Links to an older week, season or odds mode skip the pre-rendered content, since
it reflects the latest snapshot (see
[VM_DEPLOYMENT.md](../operations/VM_DEPLOYMENT.md#share-cards-link-previews)).

**The two renderers must agree.** `static_pages.py` mirrors the JavaScript
modules function by function (its docstrings name the JS function each one
matches, e.g. `complete_scenario_cards` ↔ `completeScenarioCards`), and
`backend/tests/unit/static_pages_test.py` mirrors the JavaScript tests. A change
to a card, a label or a sentence goes in both places, with both tests. The
share cards' text helpers mirror `format.js` the same way.

## Page parameters

The path says what's shown and the query how (`routes.js`); defaults stay out of
the URL. The pages take `season`, `week` (a past week's snapshot; omitted means
the latest), `odds=tossup` (the default is Projected, the Elo-weighted odds) and
`team` (opens that team's playoff path and shows only its scenarios).

## The JavaScript modules

`static/js/`, as ES modules. Most are pure, with no DOM access, so the tests
run them under Node.

| Module | Role |
|---|---|
| `app.js` | The app: routing, fetching, rendering each page, the bracket's game sheet and the scenario explanation sheet. |
| `routes.js` | URL shape: path for what's shown, query for how; former team slugs. |
| `components.js` | Reusable pieces that return HTML strings: odds cells, badges, condition chips, scenario cards, breadcrumbs. |
| `format.js` | Odds rounding (0% and 100% only for certainties), records, dates. |
| `standings.js` | Standings-table shaping: tie-aware positions, playoff paths, tie headings. |
| `scenarios.js` | The API's paths, insights and complete scenarios turned into the outcome cards, explanations included. |
| `bracket.js` | Bracket shaping: game states, occupants, matchups, layout. |
| `landing.js` | The front page's URL and fallback. |
| `search.js` | Team search matching. |
| `feedback.js`, `turnstile.js` | The feedback form's data and the Turnstile spam check. |
| `analytics.js` | PostHog counts ([ANALYTICS.md](../reference/ANALYTICS.md)). |
| `nav.js`, `theme.js` | The header and tab bar's current page; light/dark/system theme. |
| `config.js` | The public client settings from `GET /api/v1/client-config`. |
| `moderate.js`, `moderation.js`, `auth.js` | The moderation page, its pure parts, and the Auth0 PKCE sign-in. |
| `vendor/` | Vendored third-party code (posthog-js), so the CSP stays `script-src 'self'`. |

Tests: `node --test nginx/tests/*.test.mjs`: a file for each of `analytics`, `bracket`,
`components`, `feedback`, `format`, `landing`, `moderation`, `routes`, `scenarios`,
`search`, `standings` and `turnstile`, plus `css.test.mjs` for the stylesheet.

## Styles and fonts

One stylesheet, `static/css/app.css`, with the design tokens at the top and a
dark theme on the same tokens. Fonts are self-hosted in `static/fonts/`: Inter
(SIL OFL) for text, and Nippo for titles, which is installed on the server by
hand because its license doesn't allow it in a public repository
([backend/assets/fonts/README.md](../../backend/assets/fonts/README.md)).

## Local development

The site's pages need nginx (the server-side includes, the static files, the
routes), and nginx only runs on the server, so pages aren't served locally. The
JavaScript tests, the Python mirror tests and the API (`http://localhost:8000`)
cover the logic; see [LOCAL_DEVELOPMENT.md](../operations/LOCAL_DEVELOPMENT.md).
