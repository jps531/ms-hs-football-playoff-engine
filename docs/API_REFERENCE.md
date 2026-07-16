# API Reference

All endpoints are under `/api/v1`. Interactive docs are at [localhost:8000/docs](http://localhost:8000/docs) when the server is running.

## Meta

| Method | Path | Description |
|--------|------|-------------|
| GET | `/seasons` | List all seasons that have enrolled teams |
| GET | `/seasons/{season}/structure` | All classes and regions with team counts for a season |
| GET | `/teams` | List teams; `season` required, optional `class` and `region` filters |
| GET | `/teams/{team}` | Metadata for a single team in a season — includes `latitude`, `longitude`, `zip`, and `secondary_color_hex` when available |
| GET | `/teams/{team}/helmets` | All helmet designs for a team; optional `year` filter |
| GET | `/helmets` | Browse helmets across all teams; filters: `team`, `color`, `finish`, `tag` |

## Standings — `/standings`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/{clazz}/{region}` | Seeding odds for all teams; includes human-readable scenarios when ≤6 games remain and key insights (simple clinch/elimination facts) when ≤10 games remain. Params: `season`, `date`. See [SCENARIO_COMPUTATION.md](SCENARIO_COMPUTATION.md) for the full computation model. |
| GET | `/{clazz}/{region}/teams/{team}` | Same, filtered to one team |
| POST | `/{clazz}/{region}/simulate` | Apply hypothetical game results and return updated seeding odds |
| POST | `/{clazz}/{region}/teams/{team}/simulate` | Same, filtered to one team |

**Response fields per team** (`teams[]`):
- `odds` — seeding probabilities `p1`–`p4` and `p_playoffs`, plus margin-weighted variants `p1_weighted`–`p_playoffs_weighted`
- `bracket_odds` — probability of advancing to each playoff round (`second_round` through `champion`), unweighted and weighted. `null` for on-demand/simulate paths.
- `home_game_odds` — conditional probability of hosting each round (`first_round` through `semifinals`), unweighted and weighted. `null` for on-demand/simulate paths.
- `clinched`, `eliminated`, `coin_flip_needed`

**Top-level response fields**:
- `scenarios` — when `scenarios_available` is `true`, each entry includes `game_winners` (which team wins each remaining game to produce this seeding), `tiebreaker_groups`, `coinflip_groups`, and `outcomes` (team → seed number)
- `computation_state` — `margin_sensitive` (bool), `margin_compute_status` (`not_needed` / `pending` / `running` / `complete` / `skipped`), and timestamps. Use `margin_compute_status` to show a "refining odds…" indicator while background margin computation is running.

## Rankings — `/rankings`

Cross-region ranked list of teams for a given class, sorted by any single odds metric. Equivalent to a `SELECT DISTINCT ON (school) … ORDER BY <metric> DESC` across `region_standings`, but served as a typed API response.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/{clazz}` | All teams in a class ranked by the chosen odds metric. Required params: `season`, `sort_by`. Optional: `as_of`, `region`, `min_odds`, `limit` |

**`sort_by` values** (any `region_standings` odds column):

*Seeding odds* — `odds_1st`, `odds_2nd`, `odds_3rd`, `odds_4th`, `odds_playoffs` and their `_weighted` variants

*Bracket advancement* — `odds_second_round`, `odds_quarterfinals`, `odds_semifinals`, `odds_finals`, `odds_champion` and their `_weighted` variants

*Home-game odds* — `odds_first_round_home`, `odds_second_round_home`, `odds_quarterfinals_home`, `odds_semifinals_home` and their `_weighted` variants

**Optional params:**
- `as_of` — use the most recent snapshot on or before this date (defaults to today)
- `region` — restrict to one region within the class
- `min_odds` — exclude teams with `sort_by` value ≤ this threshold (e.g. `0.001` drops eliminated teams)
- `limit` — max teams returned; 1–200, default 25

Each entry in `teams[]` includes `record`, `seeding_odds`, `bracket`, `home`, and `sort_value` (the value of the ranked metric for that team).

## Hosting — `/hosting`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/{clazz}/{region}` | Playoff home-game odds per round (1st round through semifinals), computed on-demand from seeding odds + bracket format |
| GET | `/{clazz}/{region}/teams/{team}` | Same, filtered to one team |
| POST | `/{clazz}/{region}/simulate` | Apply hypothetical results and return updated hosting odds. See simulate input format under Bracket. |
| POST | `/{clazz}/{region}/teams/{team}/simulate` | Same, filtered to one team |

**Response fields per team** (`teams[]`):

Each team has four round entries (`first_round`, `second_round`, `quarterfinals`, `semifinals`), each with:
- `conditional` — P(hosts round | reaches round). `null` if the team cannot reach this round.
- `marginal` — P(hosts round) = conditional × P(reaches round).
- `conditional_weighted` — Elo-weighted version of `conditional`. `null` if the team cannot reach this round.
- `marginal_weighted` — Elo-weighted version of `marginal`.

For 1A–4A classes, all four rounds are populated. For 5A–7A, `second_round` is always `null` (teams go directly to quarterfinals). Weighted fields (`conditional_weighted`, `marginal_weighted`) are populated on both GET and simulate paths when Elo ratings are available for the season; `null` for seasons with no ratings data.

## Bracket — `/bracket`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Advancement odds for every seed slot in a class. Params: `season`, `class`, `date` |
| POST | `/simulate` | Apply hypothetical bracket results and return updated odds |

**Response fields per slot** (`teams[]`):
- `region`, `seed` — bracket slot identifier. `school` is set only when a team has clinched that seed; otherwise `null`.
- All 32 bracket slots are always returned. Eliminated teams appear with `school` populated and zero odds for all remaining rounds.
- Advancement odds: `second_round`, `quarterfinals`, `semifinals`, `finals`, `champion` (non-weighted, 50/50 matchups).
- Weighted advancement: `second_round_weighted`, `quarterfinals_weighted`, `semifinals_weighted`, `finals_weighted`, `champion_weighted` — Elo-weighted. `null` when no Elo ratings exist for the season.
- `hosting` — nested object with four round entries (`first_round`, `second_round`, `quarterfinals`, `semifinals`), each with the same `conditional`/`marginal`/`conditional_weighted`/`marginal_weighted` fields as the hosting endpoint. For 5A–7A, `hosting.second_round` is `null` (no second round). Weighted hosting fields follow the same `null` rule as weighted advancement.

**`bracket_layout`** — pre-built bracket tree enriched with per-game participants and results so the UI does not need to cross-reference other response fields.

Structure:
- `halves` — `{ "N": [...rounds...], "S": [...rounds...] }`. Each half is a list of rounds; `rounds[0]` is R1 (leaf nodes with `slot` set and participants pre-populated), subsequent rounds have `feeds_from` (pair of 0-based indices into the previous round).
- `championship` — the final game node with `feeds_from_halves: ["N", "S"]`.

Each `BracketGame` node:
- `slot` — set on R1 leaf nodes only; `null` for all R2+ nodes.
- `feeds_from` — set on R2+ nodes; indices into the previous round's game list.
- `round` — the round name for this game: `"first_round"`, `"second_round"` (1A–4A only), `"quarterfinals"`, or `"semifinals"`.
- `participant_a`, `participant_b` — `{ region, seed, school }` objects identifying the two teams. `participant_a` corresponds to the `home` format slot on R1 nodes and to the `feeds_from[0]` winner on R2+ nodes — positional only, not a hosting indicator. `school` is `null` when the team is not yet known. Both are `null` pre-playoff.
- `home_team` — `{ region, seed, school }` identifying who hosts this game. Always set on R1 nodes (region/seed known from the bracket format; `school` null until seedings clinch). Set on R2+ nodes when one participant's conditional hosting odds are 1.0; `null` when hosting is not yet determined or no participants are known.
- `result` — set when the game has a confirmed or simulated outcome (see below). `null` when not yet played.

`BracketGameResult`:
- `winner` — `{ region, seed, school }` participant who won.
- `loser` — `{ region, seed, school }` participant who lost; `null` when the result was submitted without a named opponent (round-based simulate).
- `winner_score`, `loser_score` — final scores; default to 12/0 when omitted from a simulate request.
- `simulated` — `false` for confirmed DB results, `true` for results supplied in a `/simulate` request body.

`ChampionshipGame` (the `championship` node):
- `feeds_from_halves: ["N", "S"]`
- `north_participant`, `south_participant` — the SF winners from each half; `null` until the semifinals are complete.
- `result` — same `BracketGameResult` shape as regular game nodes.

**Simulate input** (all three simulate endpoints — `POST /bracket/simulate`, `POST /hosting/{clazz}/simulate`, `POST /hosting/{clazz}/{region}/simulate`):

Each result identifies participants by school name, (region, seed) slot ref, or a mix. Provide either `loser` (specific opponent) **or** `round` (unspecified opponent) — not both:

```json
{ "results": [
  { "winner": "School Name", "loser": { "region": 1, "seed": 2 } },
  { "winner": { "region": 3, "seed": 1 }, "loser": "Other School", "winner_score": 28, "loser_score": 14 },
  { "winner": "Leake County", "round": "quarterfinals" }
]}
```

- `loser` — specific opponent. Mutually exclusive with `round`.
- `round` — one of `"second_round"`, `"quarterfinals"`, `"semifinals"`. When used instead of `loser`, all teams that could have been the opponent in that round are marked eliminated, so they do not appear in later rounds. The winner advances to the next round in `bracket_layout` with `result.loser = null`. Use this to simulate a team's run without enumerating every game (e.g. `[{"winner": "X", "round": "second_round"}, {"winner": "X", "round": "quarterfinals"}]` advances X to the semifinals).
- `winner_score` / `loser_score` — optional. Defaults to 12/0 (forfeit) when omitted on all simulate endpoints.

A plain string for `winner` or `loser` is shorthand for `{"school": "Name"}`. Confirmed DB results are never overridden by simulated ones for the same matchup.

**Bracket simulate** (`POST /bracket/simulate`): works in two modes:
- *Playoff mode* (some or all seedings clinched): school names and slot refs both resolve to known teams. The returned `bracket_layout` merges confirmed DB results (marked `simulated: false`) with the hypothetical results in the request body (marked `simulated: true`), and propagates winners into downstream game participants.
- *Pre-clinching mode* (no seedings clinched yet): only slot refs are meaningful; school-name refs are silently skipped. `bracket_layout` game nodes will have `null` participants and results. Round-based (loser-less) results require seedings to be clinched and have no effect in pre-clinching mode.

**Hosting simulate** (`POST /hosting/{clazz}/simulate`, `POST /hosting/{clazz}/{region}/simulate`): slot refs apply only in playoff mode (seedings clinched); they are silently skipped in regular-season mode where school names are required.

## Games — `/games`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Game schedule; filter by `season`, `class`, `region`, `team`, `date_from`, `date_to` |
| GET | `/probability` | Pre-game win probability (Elo-based). Params: `team_a`, `team_b`, `season`, `location` |
| POST | `/probability/live` | In-game win probability. Body: `pregame_prob`, `current_margin`, `seconds_remaining` |
| POST | `/probability/overtime` | MSHAA OT win probability. Body: `pregame_prob`, `ot_scored_margin` |

Each game includes `final` (bool), `round` (e.g. `"first_round"`, `"quarterfinals"` — `null` for regular season), `kickoff_time`, `overtime` (0 for regulation), `game_quarter`, `game_clock`, and `source`.

## Ratings — `/ratings`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Elo and RPI for teams; filter by `season`, `class`, `region`, `team`; sorted by Elo descending. Without `as_of`: all stored snapshots for the season (one row per school per pipeline run). With `as_of`: one row per school — the most recent snapshot on or before that date. |
| GET | `/{team}/trend` | Elo time-series for one team. Optional `date_from` / `date_to` |

Each rating entry includes `as_of_date` (pipeline run date), `games_played`, and `computed_at` (timestamp) for freshness tracking.

## Admin — `/admin`

**Season setup**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/playoff-format` | Seed `playoff_formats` + `playoff_format_slots` for a new season. Idempotent. `?dry_run=true` to preview counts without writing |
| POST | `/championship-venue` | Set `location_id = neutral` on all Championship Game rows for a season. `?dry_run=true` to preview affected rows without writing |

**Overrides** — the three base tables (`schools`, `games`, `locations`) each have an `overrides` JSONB column that wins over the pipeline-written value on read (via the `*_effective` views). Use these endpoints instead of raw SQL when you need to correct a pipeline error without touching the source data.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/overrides` | Audit all active manual overrides across schools, locations, and games |
| PUT | `/schools/{school}/overrides` | Set one override field on a school. Body: `{ "field": "display_name", "value": "West Jones" }`. Valid fields: `display_name`, `mascot`, `primary_color`, `secondary_color`, `primary_color_hex`, `secondary_color_hex`, `latitude`, `longitude` |
| DELETE | `/schools/{school}/overrides/{field}` | Clear one override field, restoring the pipeline-written value |
| PUT | `/games/{school}/{date}/overrides` | Set one override field on a game row (e.g. fix a miscategorized region game or a wrong score). Valid fields: `location`, `location_id`, `points_for`, `points_against`, `region_game`, `round`, `kickoff_time` |
| DELETE | `/games/{school}/{date}/overrides/{field}` | Clear one override field on a game row |
| PUT | `/locations/{id}/overrides` | Set one override field on a venue. Valid fields: `home_team`, `latitude`, `longitude` |
| DELETE | `/locations/{id}/overrides/{field}` | Clear one override field on a venue |

**Games (manual-only columns)**

| Method | Path | Description |
|--------|------|-------------|
| PUT | `/games/{school}/{date}/helmet` | Assign or clear the helmet design worn by `school` in a game. Body: `{ "helmet_design_id": 42 }` (or `null` to clear) |

**School seasons**

| Method | Path | Description |
|--------|------|-------------|
| PATCH | `/school-seasons/{school}/{season}` | Toggle `is_active` for a school in a season (pipeline never writes this column). Body: `{ "is_active": false }` |

**Locations CRUD** — the pipeline never writes this table; venues are otherwise seeded by SQL only.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/locations` | List all venues (id, name, city, home_team); use to look up `location_id` for other admin calls |
| POST | `/locations` | Add a new venue. Body: `name` (required), `city`, `home_team`, `latitude`, `longitude`. Returns full record including `id`. 409 on duplicate `(name, city, home_team)` |
| PATCH | `/locations/{id}` | Partial update of any venue field. Only provided fields are written |

**Helmet designs CRUD** — the pipeline never writes this table. Create a record first to get an `id`, then upload images via `POST /images/helmets/{id}/{type}`.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/helmets` | Create a new helmet design record. Body: `school` (required), `year_first_worn` (required), plus optional `year_last_worn`, `years_worn`, `color`, `finish`, `facemask_color`, `logo`, `stripe`, `tags`, `notes`. Returns full record including generated `id` |
| PATCH | `/helmets/{id}` | Partial update of any metadata field (not image columns). Only provided fields are written |
| DELETE | `/helmets/{id}` | Delete a helmet design. Any games referencing it have `helmet_design_id` set to NULL automatically |

## Images — `/images`

Upload images to Cloudinary and write the resulting path back to the database. Returns `{ "path": "...", "url": "https://..." }`.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/logos/{school}/{logo_type}` | Upload a school logo (`primary`, `secondary`, or `tertiary`). Updates `schools.logo_{type}`. |
| POST | `/helmets/{helmet_design_id}/{image_type}` | Upload a helmet image (`left`, `right`, or `photo`). Looks up school and year from the existing `helmet_designs` row, uploads to `helmets/{type}/{School}_{year}_{id}`, and updates the corresponding column. |

## Auth — `/auth`

Authentication is handled by **Auth0**. Users log in via Auth0 and receive an RS256-signed JWT access token, which they pass as `Authorization: Bearer <token>` on every request. The API validates tokens against Auth0's JWKS endpoint and lazy-provisions a `users` row on first authenticated request.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/verify-moderator` | Bearer (moderator+) | Internal endpoint called by nginx `auth_request` to gate the Prefect UI. Returns 200 for moderator/owner, 401/403 otherwise. Not shown in Swagger. |

## Users — `/users`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/me` | Bearer | Own profile: display name, phone, hometown, favorite team, followed teams, attended game count. |
| PATCH | `/me` | Bearer | Update display name, phone, hometown, or favorite team. |
| GET | `/me/followed-teams` | Bearer | List followed school names. |
| PUT | `/me/followed-teams/{school}` | Bearer | Follow a team (idempotent). 404 if school not found. |
| DELETE | `/me/followed-teams/{school}` | Bearer | Unfollow. |
| GET | `/me/attended-games` | Bearer | List attended games with opponent and result. |
| PUT | `/me/attended-games/{school}/{date}` | Bearer | Mark a game as attended (idempotent). 404 if game not found. |
| DELETE | `/me/attended-games/{school}/{date}` | Bearer | Remove attendance record. |
| GET | `/me/submissions` | Bearer | List own submissions. |
| GET | `/` | Owner | List all user accounts (admin view). |
| PATCH | `/{user_id}/role` | Owner | Promote/demote to `user` or `moderator` (cannot set `owner`). |
| PATCH | `/{user_id}/active` | Owner | Activate or deactivate an account. |

## Submissions — `/submissions`

Open endpoints — no authentication required. Submissions enter a moderation queue with `status='pending'` and are not applied to the live database until approved via the moderation API.

If a valid `Authorization: Bearer <token>` header is included, the submission is linked to the authenticated user (`user_id`). This is optional but enables future features like auto-approval for trusted contributors. Anonymous submissions are accepted normally with `user_id=NULL`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/logos` | optional Bearer | Submit a school logo for moderator review. Multipart: `school`, `logo_type` (`primary`/`secondary`/`tertiary`), `file`. Image is staged on Cloudinary and promoted to production on approval. 404 if school not found. |
| POST | `/helmets` | optional Bearer | Submit a helmet design for moderator review. Multipart: `school`, `year_first_worn`, `description`, plus optional metadata fields and up to 5 reference images (`images`) and an optional logo image (`logo_image`). Moderator creates the helmet record manually from the submitted info. 404 if school not found. |
| POST | `/colors` | optional Bearer | Submit a school color correction. Body: `school`, optional `primary_color` `{name, hex}`, optional `secondary_colors` array. Auto-applied on approval via `set_school_override`. 404 if school not found. |
| POST | `/locations` | optional Bearer | Submit corrected GPS coordinates for a school. Body: `school`, `latitude`, `longitude`. Auto-applied on approval via `set_school_override`. 404 if school not found. |
| POST | `/scores` | optional Bearer | Submit a corrected game score. Body: `school`, `date`, `points_for`, `points_against`. Both the school and the game row must already exist. Auto-applied on approval via `set_game_override`. 404 if school or game not found. |
| POST | `/feedback` | optional Bearer | Submit general feedback (no school required). Body: `subject`, `message`. No DB action is taken on approval. |

## Moderation — `/moderation`

Requires a valid `Authorization: Bearer <token>` header with `moderator` or `owner` role.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/submissions` | List submissions. Optional query params: `type` (`logo`/`helmet`/`colors`/`location`/`score`/`feedback`), `status_filter` (`pending`/`approved`/`rejected`), `limit` (default 50), `offset` |
| GET | `/submissions/{id}` | Get a single submission with its full payload. 404 if not found. |
| POST | `/submissions/{id}/approve` | Approve a pending submission and auto-apply it to the live database. Optional body: `{ "notes": "..." }`. 404 if not found; 409 if already reviewed. |
| POST | `/submissions/{id}/reject` | Reject a pending submission. No changes are applied to the database. Optional body: `{ "notes": "..." }`. 404 if not found; 409 if already reviewed. |
