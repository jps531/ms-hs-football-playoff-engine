# Analytics

Visit and feature counts go to PostHog Cloud (US), set up so that nothing
personal is stored: the only personal data PostHog receives is the IP address
and browser that every request carries, which it hashes into a daily visitor
count and then discards. The methodology page's "What we measure" section
(`nginx/html/methodology.html#measure`) is the public description of this;
keep the two in step: a new event or property means a new line there.

## How it's wired

- **Off unless configured.** `GET /api/v1/client-config` returns
  `posthog_key` from `POSTHOG_PROJECT_KEY`. With no key, the app loads nothing
  and sends nothing (local runs and tests stay quiet).
- **No outside script.** `nginx/html/static/js/vendor/posthog-js.js` is
  posthog-js 1.438.21's `dist/module.no-external.js`, vendored, so the CSP
  stays `script-src 'self'`. To update it, replace the file from the npm
  package and change the version in its header comment and here.
- **Events go out through this site.** The library posts to `/relay/`, and
  nginx forwards that to `us.i.posthog.com` (the `location ^~ /relay/` block,
  following [PostHog's nginx proxy guide](https://posthog.com/docs/advanced/proxy/nginx)),
  so `connect-src` stays `'self'` and most ad blockers leave it alone. nginx
  passes the visitor's address as `X-Forwarded-For` (PostHog's
  [Cloudflare proxy guide](https://posthog.com/docs/advanced/proxy/cloudflare)
  does the same, so visitors aren't all counted as the server) and drops cookies
  and `Authorization` both ways. The vendored library needs no `/static/` or
  `/array/` assets proxied, and flags are off, so the API host is all it uses.
- **No cookies or browser storage.** `cookieless_mode: "always"` with
  `person_profiles: "never"`: PostHog counts unique visitors per day from
  `hash(project, daily salt, IP address, user agent, hostname)`, computed on its
  servers; the salt changes daily and is deleted once that day's events are
  processed ([PostHog: cookieless tracking](https://posthog.com/tutorials/cookieless-tracking)).
  The trade-offs: someone who visits on two days counts as two visitors (weekly
  and monthly uniques run high), two people on one network with the same browser
  can count as one, and there's no location data: PostHog strips the IP before
  its GeoIP step, so the web analytics world map stays empty.
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
| `home_link_clicked` | Following a link on the front page | `to` (the link's path), `section` (the front-page section it's in: its heading id without `landing-`, or `classes` for the class buttons) |
| `feedback_opened` | Opening the feedback form | `kind` (`score`, `odds`, `other`) |
| `feedback_sent` | A report sent | `kind` (`score`, `feedback`) |

No event carries what anyone typed: not the feedback message, email or search
text.

## Setting it up

1. Create a project on PostHog's **US** cloud (for the EU cloud, change the
   host in nginx's `/relay/` block to `eu.i.posthog.com`).
2. In the project's settings:
   - **Settings → Project → Web analytics → Enable cookieless tracking**, and
     save. Without it PostHog ignores cookieless events.
   - **Settings → Project → Privacy → IP data capture configuration**: discard
     client IP data, so addresses aren't stored with events. (A US
     organization doesn't discard by default.) The methodology page says
     addresses aren't kept, so check this before setting the key.
3. Put the project API key (`phc_…`) in `.env.local` as `POSTHOG_PROJECT_KEY`,
   and the project's web analytics URL (for example
   `https://us.posthog.com/project/12345/web`) as `POSTHOG_DASHBOARD_URL`, then
   recreate the API and nginx. The owner sees an **Analytics** link next to
   **Prefect** on `/moderate`.

## The dashboard

`scripts/posthog_dashboard.py` builds a PostHog dashboard named "Site activity" from these
events: bar charts of the most viewed classes, regions and brackets (from page addresses), the
most picked teams, the front-page links followed, the scenario groups opened, and the bracket
games opened. Each panel shows the last 30 days, and the dashboard's date picker changes them.
The numbers are views and clicks, not people: opening the same page twice counts twice.

1. In PostHog, **Settings → User → Personal API keys**, create a key with the
   `dashboard:write` and `insight:write` scopes. This is not the `phc_` project key, and it
   doesn't go in `.env.local` or the repo: it can read and change the project.
2. On any machine with Python 3:

   ```
   POSTHOG_PERSONAL_API_KEY=phx_... POSTHOG_PROJECT_ID=12345 python3 scripts/posthog_dashboard.py
   ```

   (or pass `POSTHOG_DASHBOARD_URL` instead of `POSTHOG_PROJECT_ID`). It prints the
   dashboard's link; put that in `.env.local` as `POSTHOG_ACTIVITY_URL` and recreate the
   API, and the owner sees an **Activity** link beside **Analytics** on `/moderate`. Run it once; if the dashboard exists it changes nothing, so delete the
   dashboard in PostHog first to rebuild it after the script changes.
3. Delete the key afterwards if you won't run the script again.

The methodology page doesn't load `analytics.js`, so views of it aren't counted; a click
from the front page to it is (`home_link_clicked`).

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
