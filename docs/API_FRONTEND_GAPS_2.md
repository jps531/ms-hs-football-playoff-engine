# API Gaps for Frontend, Round 2 — Implementation Spec

Context: follow-up to API_FRONTEND_GAPS.md (the original nine aggregation-read
gaps). This round covers gaps identified while speccing the profile/attended
games, submissions/admin, helmet browser, image system, rankings, and
geography features. Same conventions as round 1: public reads take `season` +
optional `date` params where applicable, read from existing tables, follow
existing error shapes, get README table entries and tests.

Also included: two pre-launch hardening tasks and one auth change that are
backend work but frontend-blocking.

---

## 1. Helmet detail + stats exposure ✅

**UI purpose:** helmet browser detail page (/helmets/{id}) shows a design's
images, metadata, appearances, W-L record when worn, and the list of games it
was worn in. The browser grid also wants a "recently added" sort.

**Changes:**
- `GET /helmets/{id}` — single design with full metadata + images, plus:
  `stats: {appearances, wins, losses, ties?}` and
  `games_worn: [{school, date, opponent, points_for, points_against, result,
  round}]`, computed from games rows where `helmet_design_id = id`.
- Add `created_at` (timestamptz, default now()) to `helmet_designs` if not
  present; expose it and support `sort=created_at` on `GET /helmets`.
- Embed the same lightweight `stats` object in `GET /helmets` list items
  (cheap aggregate join) so the browser can badge records without N+1 calls.

**Integrity rule (must hold in API, not just UI):** stats count ONLY games
with an explicit `helmet_design_id` assignment. Games where the design would
merely be inferred as the team's primary are never counted. Include
`games_tracked` vs `games_played` (for the seasons the design spans) so the
UI can render "6–1 in 7 tracked games (of 11 played)."

---

## 2. Primary helmet concept ✅

**UI purpose:** game pages and team headers need a default helmet to display
when no per-game assignment exists; frontend and OG share cards must resolve
identically.

**Changes:**
- Add `is_primary` boolean to `helmet_designs` (default false) with a partial
  unique constraint: at most one primary per school.
- Expose in `GET /teams/{team}/helmets`, `GET /helmets`, and admin CRUD
  (`POST /admin/helmets`, `PATCH /admin/helmets/{id}` accept it; setting
  true clears any existing primary for that school atomically).
- Document the display resolution order in the API docs (single source of
  truth for frontend + share-card rendering):
  1. game's explicit `helmet_design_id`
  2. school's primary design whose `year_first_worn`–`year_last_worn` range
     covers the game's season
  3. most recent design covering that season
  4. none → frontend renders silhouette fallback

---

## 3. Helmet info on game rows ✅

**UI purpose:** game pages render the helmets each school wore ("Helmets
worn" row on finals; period-accurate headers on historical games) without
extra lookups per game.

**Change:** `GET /games` rows gain `helmet_design_id` (already a column) plus
a small resolved object when non-null: `helmet: {id, image_left, color}`.
Null when unassigned — the frontend applies the §2 resolution order for
display, but only explicit assignments come back on the row (keeps §1's
integrity rule enforceable client-side too).

---

## 4. helmet_assignment submission type (the "confirm" flow) ✅

**UI purpose:** on final game pages, logged-in users one-tap confirm that a
team wore its primary helmet ("Wearing their usual? ✓") or pick a different
design from that team's list. This is the crowd-sourced coverage engine for
§1's stats.

**Changes:**
- `POST /submissions/helmet-assignments` (optional Bearer, same conventions
  as other submission endpoints). Body: `{school, date, helmet_design_id}`.
  404 if the game or design doesn't exist or the design belongs to a
  different school. Enters the moderation queue as type `helmet_assignment`.
- Moderation approve auto-applies via the existing per-game helmet
  assignment write (same effect as `PUT /admin/games/{school}/{date}/helmet`).
- Add `helmet_assignment` to the moderation `type` filter enum.
- Duplicate handling: if an assignment already exists for that game+school,
  409 (or auto-resolve as already-correct confirmation — pick one, document
  it).

---

## 5. Submission image slot labels ✅

**UI purpose:** the helmet submission form presents labeled upload slots
(Left side, Right side, Front, Logo 2D/flat, Other) so moderators know which
reference image is which.

**Change:** `POST /submissions/helmets` accepts an optional per-image label
(multipart field `image_labels` parallel to `images`, or filename-prefix
convention — pick one). Labels stored in the submission payload and returned
by `GET /moderation/submissions/{id}` so the moderation detail view can
caption the gallery. Allowed values: `left`, `right`, `front`, `logo`,
`other` (free `other_note` optional).

---

## 6. Needs-mockup lane linkage ✅

**UI purpose:** the moderation UI's "needs mockup" tab lists approved helmet
submissions that don't yet have a created helmet design record.

**Change:** add nullable `helmet_design_id` FK to `submissions` (set when the
moderator creates the design record from the submission). Expose it in
moderation list/detail responses, and support
`GET /moderation/submissions?type=helmet&status_filter=approved&unlinked=true`
(or equivalent filter) so the tab is one query. When creating a design via
`POST /admin/helmets`, accept an optional `from_submission_id` that sets the
linkage in the same transaction.

---

## 7. Championship venues read endpoint ✅

**UI purpose:** the /championships almanac page (list + map, era-grouped)
renders venue history back to 1992. The `championship_venues` table already
exists — this is exposure only.

**Change:** `GET /championships` — params: optional `season`, optional
`clazz`. Returns rows joined to locations:
`[{season, class?, location: {id, name, city, latitude, longitude}}]`.
For seasons with imported game data, include `has_games: true` so the UI
knows it can link through to championship game pages; pre-import seasons
return `has_games: false` and render as pure almanac entries.

---

## 8. Travel/distance logic + roadmap + travel insights

**UI purpose:** three consumers of one distance system: (a) the playoff
roadmap map view on team pages ("Road to Jackson" polyline with per-hop
miles), (b) travel insight kinds in the statewide insights feed ("longest
road trip this week"), (c) the attended-games miles stat.

**Changes:**
- One haversine helper (straight-line; all distances in the product are
  straight-line and labeled as such — never compute driving distances).
- `GET /teams/{team}/roadmap?season=` — the team's playoff games in round
  order: `[{round, date, opponent, location: {name, city, lat, lon},
  is_home, distance_miles}]` plus `total_miles` and
  `championship_distance_miles` (straight-line from school to the season's
  championship venue via §7). Games with null/unknown venue return
  `distance_miles: null` — the UI renders a dotted skip; never guess a
  venue.
- Travel insight kinds added to the `/insights` feed (from round 1 §3):
  computed entries such as `travel_longest_week` ("Longest road trip this
  week: X traveled ~148 mi to Y") and `travel_longest_season` (farthest
  cumulative regular-season travel). Same insight shape (as_of_date, teams,
  human_text, kind); regenerate per snapshot date.
- `GET /users/me/attended-games` rows gain the game's venue coordinates and
  `distance_miles` from the user's favorite/each attended school (decide the
  anchor: distance from the ATTENDED school's campus to the venue — i.e.,
  the trip the team made — is the honest default; document it). Enables the
  "miles of Friday nights" stat and the map pins without N follow-up calls.

---

## 9. Rankings/ratings reconciliation ✅

**UI purpose:** the Rankings page treats rankings = positions, ratings =
numbers. There are reportedly both "ratings" and "rankings" endpoints now —
reconcile before frontend work:

- If the rankings endpoint returns ratings-sorted order per class: the page
  consumes it directly; ensure it includes rank, previous-snapshot rank (or
  delta) for the movement column, record, elo, rpi.
- If it returns an independent ordering (statewide top-25, own methodology):
  it feeds the featured module atop the same page; document its methodology
  string for the UI's "How this is ranked" link.
- Either way: rank movement requires the previous snapshot's ordering —
  expose `rank_prev` or `rank_delta` server-side rather than making the
  client fetch two dates.

---

## 10. Pre-launch hardening (backend, frontend-blocking)

- **Anonymous submission endpoints:** rate limiting (per-IP) and max upload
  size/content-type validation on all `POST /submissions/*` — the public
  submission UI makes these endpoints discoverable day one.
- **Prefect cookie auth:** extend the nginx `auth_request` verify endpoint
  to accept the web app's session cookie alongside Bearer JWT, so the admin
  dashboard's Prefect link works in a browser and the ModHeader workaround
  retires. (Pairs with the /admin route group.)

---

## Priority order

1. §2 + §3 (primary helmet + game-row helmet info — blocks game page and
   team header display logic) ✅
2. §7 (championships read — trivial exposure, unblocks an entire page) ✅
3. §1 (helmet detail/stats — blocks browser detail page) ✅
4. §4 + §5 + §6 (submission/moderation helmet loop — ship together) ✅
5. §8 (roadmap + travel insights — target the playoffs window)
6. §9 (reconciliation — a decision more than a build; do before Rankings
   page implementation) ✅
7. §10 (hardening — required before public launch, independent of Figma)
