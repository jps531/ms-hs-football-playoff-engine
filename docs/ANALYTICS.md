# Analytics

Visit and feature counts go to PostHog Cloud (US), set up so that nothing
personal leaves the browser. The methodology page's "What we measure" section
is the public description of this; keep the two in step.

## How it's wired

- **Off unless configured.** `GET /api/v1/client-config` returns
  `posthog_key` from `POSTHOG_PROJECT_KEY`. With no key, the app loads nothing
  and sends nothing (local runs and tests stay quiet).
- **No outside script.** `nginx/html/static/js/vendor/posthog-js.js` is
  posthog-js 1.438.21's `dist/module.no-external.js`, vendored, so the CSP
  stays `script-src 'self'`. To update it, replace the file from the npm
  package and change the version in its header comment and here.
- **Events go out through this site.** The library posts to `/relay/`, and
  nginx forwards that to `us.i.posthog.com` (the `location ^~ /relay/` block),
  so `connect-src` stays `'self'` and most ad blockers leave it alone. nginx
  passes the visitor's address as `X-Forwarded-For` and drops cookies and
  `Authorization` both ways.
- **No cookies or browser storage.** `cookieless_mode: "always"`: PostHog
  counts unique visitors per day from a hash of the address and browser,
  computed on its side with a salt that changes daily.
- **Only what's named.** Page views (including the app's in-page navigation,
  `capture_pageview: "history_change"`) and the events below. No autocapture,
  session recording, heatmaps, surveys, feature flags or exception capture.
- **Ad-click IDs are dropped.** `fbclid`, `gclid` and the rest are removed from
  every event's properties and URLs before it's sent (`analytics.js`).
- **The moderation page sends nothing.** Only `app.js` loads `analytics.js`.

## Events

| Event | When | Properties |
|---|---|---|
| `$pageview` | Every page, including in-app navigation | PostHog's defaults: URL, title, referrer, campaign tags, browser, OS, device, screen and window size, language, time zone |
| `odds_changed` | Projected/Toss-up switch | `value` |
| `week_changed`, `season_changed` | The week or season picker | `value` |
| `team_picked` | Selecting a team in the standings or the bracket sheet | `from` (`standings`/`bracket`), `team` |
| `team_search_used` | Choosing a team from the search box | `team` |
| `bracket_game_opened` | Opening a game's sheet | `class`, `round`, `game` |
| `bracket_half_changed` | The North/South/Both control | `half` |
| `scenarios_opened` | Opening a folded scenario group | `section` (its heading) |
| `feedback_opened` | Opening the feedback form | `kind` (`score`, `odds`, `other`) |
| `feedback_sent` | A report sent | `kind` (`score`, `feedback`) |

No event carries what anyone typed: not the feedback message, email or search
text.

## Setting it up

1. Create a project on PostHog's **US** cloud (for the EU cloud, change the
   host in nginx's `/relay/` block to `eu.i.posthog.com`).
2. In the project's settings, turn on **cookieless server hash mode** (cookieless
   events are dropped without it), and turn on **Discard client IP data** so
   addresses aren't stored with events. The methodology page says addresses
   aren't kept, so check this before setting the key.
3. Put the project API key (`phc_…`) in `.env.local` as `POSTHOG_PROJECT_KEY`,
   and the project's web analytics URL (for example
   `https://us.posthog.com/project/12345/web`) as `POSTHOG_DASHBOARD_URL`, then
   recreate the API and nginx. The owner sees an **Analytics** link next to
   **Prefect** on `/moderate`.

## Tagging the links you share

Links opened from texts, iMessage and some app browsers arrive with no
referrer and count as "direct". Tagging the links you post makes them count:

```
https://mshsfootball.com/standings/3a/6?utm_source=facebook&utm_medium=social&utm_campaign=week9
```

- `utm_source`: where the link is posted (`facebook`, `x`, `instagram`,
  `newsletter`, a booster club's name).
- `utm_medium`: the kind of place (`social`, `email`, `partner`).
- `utm_campaign`: what it's for (`week9`, `playoffs`, `launch`).

The tags work on any page and alongside the page's own options
(`?team=raleigh&utm_source=facebook`). Once the visit is counted they come off
the address bar, so a link copied from the page doesn't carry them on, and
they never appear in the pages' canonical links.
