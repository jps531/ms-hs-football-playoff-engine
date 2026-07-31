# API Reference

All endpoints are under `/api/v1`. Interactive docs are at [localhost:8000/docs](http://localhost:8000/docs) when the server is running.

**Rate limits**: simulate endpoints (Standings, Hosting, Bracket) and most Submissions endpoints are IP-rate-limited via `slowapi` and return `429` when exceeded. Limits are noted per-row below.

## Meta

| Method | Path | Description |
|--------|------|-------------|
| GET | `/seasons` | List all seasons that have enrolled teams |
| GET | `/seasons/{season}/structure` | All classes and regions with team counts for a season |
| GET | `/seasons/{season}/dates` | Notable game dates for a timeline scrubber (round, week, game count); optional `class` filter. Params: `season`, `class` |
| GET | `/teams` | List teams; `season` required, optional `class` and `region` filters |
| GET | `/teams/{team}` | Metadata for a single team in a season — includes `latitude`, `longitude`, `zip`, and `secondary_color_hex` when available |
| GET | `/teams/{team}/helmets` | All helmet designs for a team; optional `year` filter |
| GET | `/teams/{team}/helmets/resolved` | The single default helmet design to display for a team in a season — see "Primary helmet & display resolution order" below. Params: `season` (required) |
| GET | `/teams/{team}/roadmap` | The team's full-season roadmap (regular season + playoffs) — see below. Params: `season` (required) |
| GET | `/helmets` | Browse helmets across all teams; filters: `team`, `color`, `finish`, `tag`, `sort` (`created_at` for newest-added first; default order is `school`, `year_first_worn`) |
| GET | `/helmets/{id}` | Single helmet design with full metadata, images, `stats`, and `games_worn` — see below |
| GET | `/championships` | Championship venue history (back to 1992) for the almanac page. Optional `season`, `class` filters |

**`GET /helmets` / `GET /helmets/{id}`** — every design (list items and the detail record) carries `created_at` and a `stats` object: `{appearances, games_tracked, wins, losses, ties, games_played}`. `appearances`/`games_tracked` are the same count — games with an explicit `helmet_design_id` assignment for this design (a design that's merely inferred as a team's primary is never counted, per the integrity rule below). `wins`/`losses`/`ties` are counted among those assigned games that have a result. `games_played` is the school's total **final** games across the seasons this design spans (see `helmet_covers_season` below), so the UI can render e.g. "6–1 in 7 tracked games (of 11 played)". `GET /helmets/{id}` additionally returns `games_worn: [{school, date, opponent, points_for, points_against, result, round}]` for every explicitly-assigned game, oldest first. 404 if the id doesn't exist.

**`GET /championships`** — response: `[{season, class_, location: {id, name, city, home_team, latitude, longitude}, has_games}, ...]`, ordered newest season first. `has_games` is `true` once that season/class's Championship Game has been imported into `/games` (so the UI can link through to the game page); pre-import seasons return `has_games: false` and render as pure almanac entries.

**`GET /teams/{team}/roadmap`** — response: `{school, season, games: [{round, date, opponent, location, is_home, distance_miles}], total_miles, championship_distance_miles}`. Covers every game in the season, regular season and playoffs alike, oldest first; `round` is `null` for regular-season games. All distances are straight-line miles, never driving distance. Home games always show `distance_miles: 0` (no travel). Away games resolve to an explicit venue on record, else fall back to the opponent's home venue (same campus-coordinate fallback `GET /insights/travel` uses) — so most away games resolve to a real distance even without a `locations` row. Neutral games only get a distance when the game has an explicit venue on record — no team's campus is a reasonable stand-in for a true neutral site — except the championship game, whose venue is resolved from the season/class's known championship venue (see `GET /championships`). Unresolved games return `location`/`distance_miles: null` and the UI should render a dotted skip rather than guess. `total_miles` sums the known hops across the whole season. `championship_distance_miles` is computed independently, so it's populated even before the team has clinched a spot there.

**`GET /seasons/{season}/dates`** — response: `{season, dates: [...]}`. Each entry:
- `date`, `kind` (`"games"` or `"season_start"` — one entry, one day before the season's first game, always `week: 0`).
- `week` — derived 1-indexed week number (Monday-Sunday buckets, so e.g. Thursday/Friday/Saturday games in the same MHSAA week share one number), counting continuously through the whole season **including the playoffs**. Always populated for `"games"` dates — it is not a signal for "is this a playoff date"; use `round is not null` for that instead.
- `round` — set only for unambiguous playoff game dates (`first_round`, `second_round`, `quarterfinals`, `semifinals`, `championship_game`); `null` for regular-season dates and for dates where classes disagree (see `description` below).
- `num_games` — set only for `"games"` dates; deduplicated contest count (not the raw per-school row count), statewide unless scoped by `class`.
- `description` — always populated for `"games"` dates. 1A-4A and 5A-7A run offset playoff schedules, so a single date can be a playoff date for one group of classes and still regular season (or a different round) for another (e.g. late in the regular season, 1A-4A may already be in the First Round while 5A-7A has one more regular-season week). Pass `class` to resolve `round` unambiguously for one classification (`week` is always unambiguous); unscoped, a disagreeing date leaves `round` `null` but `description` still composes a human label per group, e.g. `"Week 11 (5A-7A) / First Round (1A-4A)"`. On an unambiguous date, `description` is just the single label (e.g. `"Week 13"`, `"First Round"`) — except the championship, where an unscoped `description` reads `"Championship Games"` (plural, since a statewide date usually covers several classes' separate games) while `class`-scoped stays `"Championship Game"` (singular). `round` is unaffected either way (`"championship_game"`).

## Standings — `/standings`

Team ordering across every endpoint below reflects actual current standing:
the MHSAA tiebreaker procedure applied to completed games (head-to-head,
point differential, etc.), with any team that has mathematically clinched a
specific seed pinned to that exact position — not alphabetical order.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/summary` | Statewide summary: one card per region across every class. Params: `season` (required), `date` (optional, default latest). Returns `leader`, `num_teams`, `num_clinched`, `num_eliminated`, `teams_alive`, `volatility`, and per-team `statuses` for every region. Each entry in `statuses[]` includes `status`, `clinched_seed` (the specific seed number the team has mathematically locked in, or `null`), and `record` (overall + region W/L/T). No scenario data is read. |
| GET | `/{clazz}` | Full standings tables for every region in one class, one request. Params: `season` (required), `date` (optional, default latest). Each region returns the same per-team detail as `/{clazz}/{region}` (`odds`, `bracket_odds`, `home_game_odds`, `clinched`, `eliminated`, `coin_flip_needed`) minus `scenarios`/`computation_state`. Only reads from stored snapshots (no on-demand fallback); 404 if the class has no data yet. |
| GET | `/{clazz}/{region}` | Seeding odds for all teams; includes human-readable scenarios when ≤6 games remain and key insights (simple clinch/elimination facts) when ≤10 games remain. Params: `season`, `date`, `include_team_scenarios` (bool, default `false` — adds a per-team `paths` breakdown to each team entry). See [SCENARIO_COMPUTATION.md](SCENARIO_COMPUTATION.md) for the full computation model. |
| GET | `/{clazz}/{region}/teams/{team}` | Same, filtered to one team. Same params. |
| POST | `/{clazz}/{region}/simulate` | Apply hypothetical game results and return updated seeding odds. Same `include_team_scenarios` param. Rate limited: 10/minute. |
| POST | `/{clazz}/{region}/teams/{team}/simulate` | Same, filtered to one team. Rate limited: 10/minute. |

**Response fields per team** (`teams[]`):
- `odds` — seeding probabilities `p1`–`p4` and `p_playoffs`, plus margin-weighted variants `p1_weighted`–`p_playoffs_weighted`
- `bracket_odds` — probability of advancing to each playoff round (`second_round` through `champion`), unweighted and weighted. `null` for on-demand/simulate paths.
- `home_game_odds` — P(hosts round | reaches round) for each round (`first_round` through `semifinals`), unweighted and weighted. `null` for on-demand/simulate paths.
- `clinched`, `eliminated`, `coin_flip_needed`
- `paths` — only present when `include_team_scenarios=true` and scenarios are available. Minimized, machine-readable per-team conditions for condition "chips," a team-page "Paths" module, and "Play this out" (mapping conditions to simulate-mode picks). One entry per achievable outcome:
  - `outcome` — `{"type": "seed", "value": N}`, `{"type": "playoffs"}` (any seed), or `{"type": "eliminated"}`
  - `p` — the outcome's existing unweighted probability (`p1`–`p4` / `p_playoffs` / `1 - p_playoffs`) — not a per-branch probability
  - `conditions` — OR-of-AND-groups (outer array = alternative paths, inner array = conditions that must all hold), already ordered broadest/most-likely-first by the boolean minimizer. Each condition is tagged by `type`: `"game_result"` (the common case — `school`/`date`/`opponent`/`required_result`/`margin_class`, `school` always from the winner's perspective), `"margin_sum"` (a linear margin constraint spanning multiple games — `games`/`op`/`threshold` instead of a single school/opponent), or `"coin_flip"`/`"pd_rank"` (tiebreaker-only, not tied to any remaining game — `description` text only). `date` is `null` when the underlying game's date can't be resolved. `margin_class` is `null` except at R≤5 (margin-sensitive tier) — see SCENARIO_COMPUTATION.md.
  - `human_text` — fallback copy only; the structured `conditions` form is the contract, not this string

**Top-level response fields**:
- `scenarios` — when `scenarios_available` is `true`, each entry includes `game_winners` (which team wins each remaining game to produce this seeding), `tiebreaker_groups`, `coinflip_groups`, and `outcomes` (team → seed number)
- `computation_state` — `margin_sensitive` (bool), `margin_compute_status` (`not_needed` / `pending` / `running` / `complete` / `skipped`), and timestamps. Use `margin_compute_status` to show a "refining odds…" indicator while background margin computation is running.

## Rankings — `/rankings`

Cross-region ranked list of teams for a given class (or statewide), sorted by any single odds metric or by Elo/RPI rating — the reconciliation point between "rankings" (positions) and "ratings" (numbers): every entry carries both, regardless of which one is the active sort key. Equivalent to a `SELECT DISTINCT ON (school) … ORDER BY <metric> DESC` across `region_standings` (joined to `team_ratings` for `elo`/`rpi`), but served as a typed API response with server-computed rank and rank movement.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/{clazz}` | All teams in a class ranked by the chosen metric. Required params: `season`, `sort_by`. Optional: `date`, `region`, `min_odds`, `limit` |
| GET | `/statewide` | Top teams across all classes, ranked by Elo (the only metric that's meaningfully comparable across class sizes — playoff-odds columns aren't, since each class runs its own bracket). Params: `season` (required), `date`, `limit` (default 25) |

**`sort_by` values** (`/{clazz}` only):

*Seeding odds* — `odds_1st`, `odds_2nd`, `odds_3rd`, `odds_4th`, `odds_playoffs` and their `_weighted` variants

*Bracket advancement* — `odds_second_round`, `odds_quarterfinals`, `odds_semifinals`, `odds_finals`, `odds_champion` and their `_weighted` variants

*Home-game odds* — `odds_first_round_home`, `odds_second_round_home`, `odds_quarterfinals_home`, `odds_semifinals_home` and their `_weighted` variants

*Rating* — `elo`, `rpi` (sourced from `team_ratings`, joined in on matching `season`/`as_of_date`)

**Optional params (`/{clazz}`):**
- `date` — use the most recent snapshot on or before this date (defaults to today)
- `region` — restricts which rows are *returned*; never changes a team's `rank`, which always reflects position within the full class (this endpoint is cross-region by design)
- `min_odds` — exclude teams with `sort_by` value ≤ this threshold (e.g. `0.001` drops eliminated teams). No natural equivalent for `elo`/`rpi`; a no-op there at the default of `0.0`
- `limit` — max teams returned; 1–200, default 25

Each entry in `teams[]` includes `record`, `seeding_odds`, `bracket`, `home`, `elo`, `rpi`, `sort_value` (the value of the ranked metric for that team), `rank` (1-indexed position for the chosen `sort_by`, among the full class for `/{clazz}` or the full state for `/statewide`), and `rank_prev`/`rank_delta` against the previous snapshot (`rank_delta = rank_prev - rank`, positive meaning the team moved up) — both `null` on a class's/state's first-ever snapshot of the season, so the frontend's movement column has no false "unchanged" reading before there's anything to compare against.

**How this is ranked** (for the `/statewide` list's "How this is ranked" link): Elo rating, carried over season-to-season blended with a classification prior (1A=1000 … 7A=1300, step 50) and updated with a margin-of-victory multiplier — see the `COMMENT ON COLUMN team_ratings.elo` in `sql/init.sql` for the full model.

## Hosting — `/hosting`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/{clazz}` | Playoff home-game odds per round for every region in a class, in one call. Params: `season`, `date`, `include_scenarios` (bool, default `false` — adds hosting-condition text per team). Returns `{ season, class_, as_of_date, regions: [...] }`, one region-shaped entry (see below) per region in the class. |
| GET | `/{clazz}/{region}` | Playoff home-game odds per round (1st round through semifinals), computed on-demand from seeding odds + bracket format. Params: `season`, `date`, `include_scenarios` (bool, default `false` — adds hosting-condition text per team). |
| GET | `/{clazz}/{region}/teams/{team}` | Same, filtered to one team. Same params. |
| POST | `/{clazz}/simulate` | Apply hypothetical results and return updated hosting odds for every region in the class. Same query params as `GET /{clazz}`, plus a request body (see simulate input format under Bracket). Rate limited: 10/minute. |
| POST | `/{clazz}/{region}/simulate` | Apply hypothetical results and return updated hosting odds. See simulate input format under Bracket. Rate limited: 10/minute. |
| POST | `/{clazz}/{region}/teams/{team}/simulate` | Same, filtered to one team. Rate limited: 10/minute. |

**Response fields per team** (`teams[]`):

Each team has four round entries (`first_round`, `second_round`, `quarterfinals`, `semifinals`), each with:
- `p_host_given_reach` — P(hosts round | reaches round). `null` if the team cannot reach this round.
- `p_host_overall` — P(hosts round) = p_host_given_reach × P(reaches round).
- `p_host_given_reach_weighted` — Elo-weighted version of `p_host_given_reach`. `null` if the team cannot reach this round.
- `p_host_overall_weighted` — Elo-weighted version of `p_host_overall`.

For 1A–4A classes, all four rounds are populated. For 5A–7A, `second_round` is always `null` (teams go directly to quarterfinals). Weighted fields (`p_host_given_reach_weighted`, `p_host_overall_weighted`) are populated on both GET and simulate paths when Elo ratings are available for the season; `null` for seasons with no ratings data.

## Bracket — `/bracket`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Advancement odds for every seed slot in a class. Params: `season`, `class`, `date` |
| GET | `/slots/{slot}` | Every team still alive for one bracket slot/round, ranked by chance of reaching it. Params: `season`, `class`, `round` (default `first_round`), `date`, `include_conditions` (default `false`) |
| POST | `/simulate` | Apply hypothetical bracket results and return updated odds. Rate limited: 10/minute. |

**`GET /slots/{slot}`** — `slot` is a first-round slot number from `playoff_format_slots`. `round` addresses the derived round-2+ game implied by the group of first-round slots feeding it (`second_round` is 1A-4A only; requesting it for 5A-7A returns 404). Unlike `GET /`, which shows one occupant per `(region, seed)` slot, this returns every team still mathematically alive for the slot pre-clinch, each with:
- `school`, `p_reach` — probability the team plays in this slot's game.
- `p_host_given_reach`, `p_host_overall` — `p_host_overall` is always `p_reach * p_host_given_reach`, computed server-side for consistency.
- `p_reach_weighted`, `p_host_given_reach_weighted`, `p_host_overall_weighted` — Elo-weighted counterparts; `null` when no Elo ratings exist for the season.
- `host_conditions` — `null` unless `include_conditions=true` is passed; when present, the OR-of-AND-groups of conditions under which this team would host, given it reaches the round (an empty list means "computed, but this team never hosts"). Each condition is the same `PathConditionModel` envelope §8's `paths` feature uses, with `type` values `bracket_advances` (another bracket position must advance) and `seed_required` (the team must finish with a specific seed — expanded into the underlying regular-season game(s) that determine it when that's computable, otherwise left as a descriptive condition). Pass `include_conditions=true` to populate it — this mirrors `/hosting`'s `include_scenarios`, since it runs the same combinatorially-guarded scenario computation (once per region feeding the slot).
- `reach_conditions` — `null` unless `include_conditions=true` is passed (same flag as `host_conditions`, no separate opt-in); when present, the OR-of-AND-groups of conditions under which this team reaches the round *at all* — i.e. wins every round strictly before it (reaching a round means playing in it, not winning it). Never an empty list for a team present in `teams[]` (unlike `host_conditions`, which can be `[]` for a team that never hosts) — a single empty AND-group (`[[]]`) means reaching is unconditional (e.g. `first_round`, where nothing needs to be won). Uses `seed_required` (same as `host_conditions`) plus a new `bracket_win` type: the team must beat a specific opponent (identified by `region`/`seed`/`school`) in `round_name`. Enumerates every possible opponent per prior round (not a coarser "must win N rounds" summary) — bounded by bracket depth, up to 8 groups for a 1A-4A team reaching the semifinals.

**Response fields per slot** (`teams[]`):
- `region`, `seed` — bracket slot identifier. `school` is set only when a team has clinched that seed; otherwise `null`.
- All 32 bracket slots are always returned. Eliminated teams appear with `school` populated and zero odds for all remaining rounds.
- Advancement odds: `second_round`, `quarterfinals`, `semifinals`, `finals`, `champion` (non-weighted, 50/50 matchups).
- Weighted advancement: `second_round_weighted`, `quarterfinals_weighted`, `semifinals_weighted`, `finals_weighted`, `champion_weighted` — Elo-weighted. `null` when no Elo ratings exist for the season.
- `hosting` — nested object with four round entries (`first_round`, `second_round`, `quarterfinals`, `semifinals`), each with the same `p_host_given_reach`/`p_host_overall`/`p_host_given_reach_weighted`/`p_host_overall_weighted` fields as the hosting endpoint. For 5A–7A, `hosting.second_round` is `null` (no second round). Weighted hosting fields follow the same `null` rule as weighted advancement.

**`bracket_layout`** — pre-built bracket tree enriched with per-game participants and results so the UI does not need to cross-reference other response fields.

Structure:
- `halves` — `{ "N": [...rounds...], "S": [...rounds...] }`. Each half is a list of rounds; `rounds[0]` is R1 (leaf nodes with `slot` set and participants pre-populated), subsequent rounds have `feeds_from` (pair of 0-based indices into the previous round).
- `championship` — the final game node with `feeds_from_halves: ["N", "S"]`.

Each `BracketGame` node:
- `slot` — set on R1 leaf nodes only; `null` for all R2+ nodes.
- `feeds_from` — set on R2+ nodes; indices into the previous round's game list.
- `round` — the round name for this game: `"first_round"`, `"second_round"` (1A–4A only), `"quarterfinals"`, or `"semifinals"`.
- `participant_a`, `participant_b` — `{ region, seed, school }` objects identifying the two teams. `participant_a` corresponds to the `home` format slot on R1 nodes and to the `feeds_from[0]` winner on R2+ nodes — positional only, not a hosting indicator. `school` is `null` when the team is not yet known. Both are `null` pre-playoff.
- `home_team` — `{ region, seed, school }` identifying who hosts this game. Always set on R1 nodes (region/seed known from the bracket format; `school` null until seedings clinch). Set on R2+ nodes when one participant's `p_host_given_reach` hosting odds are 1.0; `null` when hosting is not yet determined or no participants are known.
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
| GET | `/probability` | Pre-game win probability (Elo-based). Params: `team_a`, `team_b`, `season`, `location`, `date` (optional — pins both teams' Elo ratings to the most recent snapshot on or before this date; defaults to the latest available) |
| POST | `/probability/live` | In-game win probability. Body: `pregame_prob`, `current_margin`, `seconds_remaining` |
| POST | `/probability/overtime` | MSHAA OT win probability. Body: `pregame_prob`, `ot_scored_margin` |
| GET | `/upsets` | Finished games sorted by the winner's pregame win probability, ascending (biggest upsets first). Params: `season` (required), `date_from`/`date_to` (optional, independent bounds — without either, defaults to the week containing the most recent final game so newly-finalized upsets appear immediately), `limit` (default 10) |

Each game includes `final` (bool), `round` (e.g. `"first_round"`, `"quarterfinals"` — `null` for regular season), `kickoff_time`, `overtime` (0 for regulation), `game_quarter`, `game_clock`, and `source`.

Each game also includes `helmet_a` / `helmet_b` — the full helmet design record (see `/helmets` below) worn by `team_a`/`team_b` in that game, or `null`. These are populated **only** from that team's explicit `helmet_design_id` assignment on the game (see `PUT /games/{school}/{date}/helmet` below) — never inferred from a school's primary or most-recent design. A `null` value means the frontend should apply the resolution order documented under "Helmet designs CRUD" to pick a fallback for display.

Each game also includes embedded win probability, always from `team_a`'s perspective (so `P(team_b) = 1 - P(team_a)`):
- `pregame_prob` (float | null) — Elo-based pregame win probability. For final games this is the value persisted at finalization (computed from ratings as of the game's own date — never a later snapshot, so it never reflects the game's own result). For not-yet-final games it's computed on the fly from the latest available ratings. `null` if either team is unrated.
- `live_prob` (float | null) — non-null only while the game is in progress (`status` is one of the in-progress states). Regulation games route through the in-game model using `game_quarter`/`game_clock`; overtime games (`game_quarter > 4`) route through the OT model using the manually-tracked `ot_period_start_score_for`/`ot_period_start_score_against`/`ot_next_possession` state (see below) — `null`/incomplete OT state falls back to `pregame_prob`.
- `prob_as_of` (timestamp | null) — when `pregame_prob` was computed (persisted finalization time), or now if `live_prob` is set.

**Live-game state is currently manual-only** — no automated live-score pipeline exists yet, so `game_quarter`, `game_clock`, `game_status`, `overtime`, and the `ot_*` fields only change via the admin override endpoints below (see "Games (manual-only columns)").

## Ratings — `/ratings`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Elo and RPI for teams; filter by `season`, `class`, `region`, `team`; sorted by Elo descending. Without `date`: all stored snapshots for the season (one row per school per pipeline run). With `date`: one row per school — the most recent snapshot on or before that date. |
| GET | `/{team}/trend` | Elo time-series for one team. Optional `date_from` / `date_to` |
| GET | `/movers` | Biggest Elo risers/fallers between two rating snapshots. Params: `season` (required), `date_from`/`date_to` (optional — both given: used as the before/after snapshot targets directly; only `date_to`: paired with the snapshot immediately before it; only `date_from`: paired with the latest snapshot overall; neither: the two most recent snapshot dates for the season), `limit` (default 10, applied per direction). Teams present in only one snapshot are excluded. Returns `{"risers": [...], "fallers": [...]}`, each entry with `school`, `class_`, `region`, `elo_before`, `elo_after`, `delta` |

Each rating entry includes `as_of_date` (pipeline run date), `games_played`, and `computed_at` (timestamp) for freshness tracking.

## Insights — `/insights`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/insights` | Statewide, deduped, newest-first feed of key playoff-scenario insights (clinch/elimination facts). Params: `season` (required), `date_from`/`date_to`, `class`, `region`, `team`, `limit` (default 50). Read from pre-computed `region_scenarios` snapshots — an empty list is normal for a season with no snapshots yet. |
| GET | `/insights/travel` | Statewide travel highlights, computed live (not snapshot-based — a deliberately separate model from `/insights` above, since travel is statewide and has no scenario to dedupe against). Params: `season` (required), `date_from`, `date_to`, `limit` (default 10, max 50 — applied to each list independently). Returns `longest_trips` (individual away games ranked by distance) and `longest_cumulative` (schools ranked by total **regular-season** away-game mileage). Without `date_from`, `longest_trips` defaults to the current Monday-Sunday week and `longest_cumulative` defaults to season-to-date; passing `date_from`/`date_to` scopes both to that explicit range instead (e.g. "longest trip in October"). `longest_trips` entries have `school`, `opponent`, `date`, `distance_miles`, `human_text`; `longest_cumulative` entries have `school`, `distance_miles`, `human_text` (no single opponent/date — it's a sum across games). All distances are straight-line, never driving distance. Venue resolution per away game: an explicit `locations` row wins, else the opponent's home venue (campus-coordinate fallback). |

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
| PUT | `/games/{school}/{date}/overrides` | Set one override field on a game row (e.g. fix a miscategorized region game or a wrong score, or manually drive a game's live state — see below). Valid fields: `location`, `location_id`, `points_for`, `points_against`, `region_game`, `round`, `kickoff_time`, `game_status`, `game_quarter`, `game_clock`, `overtime`, `ot_period_start_score_for`, `ot_period_start_score_against`, `ot_next_possession` |
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
| PUT | `/school-seasons/{school}/{season}` | Create or overwrite a `school_seasons` row with explicit `class`, `region`, and `is_active` (upsert — safe to re-run). Creates the parent `schools` row if it doesn't exist. Use for mid-cycle changes the Regions pipeline can't handle: consolidations, closures, new schools. Requires moderator+. Body: `{ "class": 5, "region": 2, "is_active": true, "copy_identity_from": "Old School Name" }` — `copy_identity_from` is optional; when supplied, copies mascot, colors, city, zip, latitude, and longitude from that school into the new school's base columns immediately, before the MHSAA identity and NCES pipelines have run. 404s if the source school does not exist. See [SEASON_SETUP.md](SEASON_SETUP.md) for a worked consolidation example. |

**Locations CRUD** — the pipeline never writes this table; venues are otherwise seeded by SQL only.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/locations` | List all venues (id, name, city, home_team); use to look up `location_id` for other admin calls |
| POST | `/locations` | Add a new venue. Body: `name` (required), `city`, `home_team`, `latitude`, `longitude`. Returns full record including `id`. 409 on duplicate `(name, city, home_team)` |
| PATCH | `/locations/{id}` | Partial update of any venue field. Only provided fields are written |

**Helmet designs CRUD** — the pipeline never writes this table. Create a record first to get an `id`, then upload images via `POST /images/helmets/{id}/{type}`.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/helmets` | Create a new helmet design record. Body: `school` (required), `year_first_worn` (required), plus optional `year_last_worn`, `years_worn`, `color`, `finish`, `facemask_color`, `logo`, `stripe`, `tags`, `notes`, `is_primary` (default `false`), `from_submission_id` (links the design back to the helmet submission it was created from — sets `submissions.helmet_design_id`; 404 if the submission doesn't exist, 422 if it isn't a `helmet`-type submission, 409 if already linked). Returns full record including generated `id` |
| PATCH | `/helmets/{id}` | Partial update of any metadata field (not image columns), including `is_primary`. Only provided fields are written |
| DELETE | `/helmets/{id}` | Delete a helmet design. Any games referencing it have `helmet_design_id` set to NULL automatically |

**Primary helmet & display resolution order** — `is_primary` marks a school's default design; the DB enforces at most one primary per school (partial unique index), and setting `is_primary: true` via `POST`/`PATCH` atomically clears any existing primary for that school first. This is the single source of truth for how the frontend and OG share-card rendering should pick a helmet to display, in order:

1. The game's explicit `helmet_design_id` assignment (`GET /games`'s `helmet_a`/`helmet_b`, or `PUT /games/{school}/{date}/helmet`) — never overridden by primary/fallback logic.
2. The school's primary design that covers the relevant season — `GET /teams/{team}/helmets/resolved?season=`.
3. If no primary covers that season, the most recently introduced design that does (same endpoint — steps 2 and 3 are resolved together server-side).
4. If nothing covers that season, `null` — render the silhouette fallback client-side; never guess.

"Covers the season" is decided by the Postgres helper `helmet_covers_season()`: when a design's `years_worn` (non-contiguous spans, e.g. a throwback worn 2001–2005 and again in 2007) is set, a season counts only if it falls inside one of those spans; otherwise it falls back to the `year_first_worn`–`year_last_worn` outer bound (open-ended when `year_last_worn` is `null`). The same function backs `stats.games_played` on `GET /helmets`/`GET /helmets/{id}` below.

## Images — `/images`

Upload images to Cloudinary and write the resulting path back to the database. Returns `{ "path": "...", "url": "https://..." }`. Every endpoint in this router requires moderator+ (`Authorization: Bearer <token>`) — there is no anonymous image upload path.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/logos/{school}/{logo_type}` | Bearer (moderator+) | Upload a school logo (`primary`, `secondary`, or `tertiary`). Updates `schools.logo_{type}`. |
| POST | `/helmets/{helmet_design_id}/{image_type}` | Bearer (moderator+) | Upload a helmet image (`left`, `right`, or `photo`). Looks up school and year from the existing `helmet_designs` row, uploads to `helmets/{type}/{School}_{year}_{id}`, and updates the corresponding column. |

## Auth — `/auth`

Authentication is handled by **Auth0**. Users log in via Auth0 and receive an RS256-signed JWT access token, which they pass as `Authorization: Bearer <token>` on every request. The API validates tokens against Auth0's JWKS endpoint and lazy-provisions a `users` row on first authenticated request.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/verify-moderator` | Bearer or session cookie (moderator+) | Internal endpoint called by nginx `auth_request` to gate the Prefect UI. Returns 200 for moderator/owner via either credential, 401/403 otherwise. Not shown in Swagger. |
| POST | `/session` | Bearer | Mint a first-party session cookie for the caller (any authenticated user — role is checked at verify time, not mint time). Sets an httponly, `SameSite=Lax` cookie (`secure` outside local dev). Call once after Auth0 login completes; needed for contexts a Bearer header can't reach, e.g. navigating to the Prefect UI link. |
| DELETE | `/session` | none | Clear the session cookie. Bearer-token access is unaffected. |

**Session cookie**: `SESSION_SECRET_KEY`-signed (HS256, app-owned — separate from Auth0's RS256), 24h expiry, carries `db_id`/`role`. This is additive to the Bearer flow, not a replacement — see `nginx/nginx.conf`'s `/internal/auth/verify-moderator` location, which now forwards both `Authorization` and `Cookie` to the verify endpoint.

## Users — `/users`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/me` | Bearer | Own profile: display name, phone, hometown, favorite team, followed teams, attended game count. |
| PATCH | `/me` | Bearer | Update display name, phone, hometown, or favorite team. |
| GET | `/me/followed-teams` | Bearer | List followed school names. |
| PUT | `/me/followed-teams/{school}` | Bearer | Follow a team (idempotent). 404 if school not found. |
| DELETE | `/me/followed-teams/{school}` | Bearer | Unfollow. |
| GET | `/me/attended-games` | Bearer | List attended games with opponent, result, `venue`, and `distance_miles`. |
| PUT | `/me/attended-games/{school}/{date}` | Bearer | Mark a game as attended (idempotent). 404 if game not found. |
| DELETE | `/me/attended-games/{school}/{date}` | Bearer | Remove attendance record. |

**`GET /me/attended-games`** — `distance_miles` is straight-line from the attended school's own campus to the game's venue (the trip that team made, not the viewing user's location). Venue resolution: an explicit `locations` row wins; else the attended school's own venue for a home game; else the opponent's venue for an away game (campus-coordinate fallback, same as the travel insights above); `null` only for an unresolvable neutral-site game. Home games always show `distance_miles: 0`.
| GET | `/me/submissions` | Bearer | List own submissions. |
| GET | `/` | Owner | List all user accounts (admin view). |
| PATCH | `/{user_id}/role` | Owner | Promote/demote to `user` or `moderator` (cannot set `owner`). |
| PATCH | `/{user_id}/active` | Owner | Activate or deactivate an account. |

## Submissions — `/submissions`

Open endpoints — no authentication required. Submissions enter a moderation queue with `status='pending'` and are not applied to the live database until approved via the moderation API.

If a valid `Authorization: Bearer <token>` header is included, the submission is linked to the authenticated user (`user_id`). This is optional but enables future features like auto-approval for trusted contributors. Anonymous submissions are accepted normally with `user_id=NULL`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/logos` | optional Bearer | Submit a school logo for moderator review. Multipart: `school`, `logo_type` (`primary`/`secondary`/`tertiary`), `file`. Image is staged on Cloudinary and promoted to production on approval. 404 if school not found. Rate limited: 3/minute. |
| POST | `/helmets` | optional Bearer | Submit a helmet design for moderator review. Multipart: `school`, `year_first_worn`, `description`, plus optional metadata fields, `other_note`, up to 5 reference images (`images`), optional `image_labels` (parallel to `images` — one of `left`/`right`/`front`/`logo`/`other` per image; 422 if the length doesn't match or a label is invalid), and an optional logo image (`logo_image`). Moderator creates the helmet record manually from the submitted info (see `from_submission_id` under Helmet designs CRUD). 404 if school not found. Rate limited: 3/minute. |
| POST | `/colors` | optional Bearer | Submit a school color correction. Body: `school`, optional `primary_color` `{name, hex}`, optional `secondary_colors` array. Auto-applied on approval via `set_school_override`. 404 if school not found. Rate limited: 10/minute. |
| POST | `/locations` | optional Bearer | Submit corrected GPS coordinates for a school. Body: `school`, `latitude`, `longitude`. Auto-applied on approval via `set_school_override`. 404 if school not found. Rate limited: 10/minute. |
| POST | `/scores` | optional Bearer | Submit a corrected game score. Body: `school`, `date`, `points_for`, `points_against`. Both the school and the game row must already exist. Auto-applied on approval via `set_game_override`. 404 if school or game not found. Rate limited: 10/minute. |
| POST | `/helmet-assignments` | optional Bearer | Submit or confirm which helmet a school wore in a game — the crowd-sourced input to §1's helmet stats. Body: `school`, `date`, `helmet_design_id`. 404 if the school, game, or design doesn't exist, or the design belongs to a different school. Auto-applied on approval the same way as `PUT /admin/games/{school}/{date}/helmet`. If the game's helmet is already set to the submitted design, no submission is queued — responds `200` with `{ "already_confirmed": true, ... }` instead of `201`. Rate limited: 10/minute. |
| POST | `/feedback` | optional Bearer | Submit general feedback (no school required). Body: `subject`, `message`. No DB action is taken on approval. Rate limited: 10/minute. |

## Moderation — `/moderation`

Requires a valid `Authorization: Bearer <token>` header with `moderator` or `owner` role.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/submissions` | List submissions. Optional query params: `type` (`logo`/`helmet`/`colors`/`location`/`score`/`feedback`/`helmet_assignment`), `status_filter` (`pending`/`approved`/`rejected`), `unlinked` (bool — restricts to submissions with/without a linked `helmet_design_id`; `type=helmet&status_filter=approved&unlinked=true` is the "needs mockup" tab), `limit` (default 50), `offset` |
| GET | `/submissions/{id}` | Get a single submission with its full payload. 404 if not found. |
| POST | `/submissions/{id}/approve` | Approve a pending submission and auto-apply it to the live database. Optional body: `{ "notes": "..." }`. 404 if not found; 409 if already reviewed. |
| POST | `/submissions/{id}/reject` | Reject a pending submission. No changes are applied to the database. Optional body: `{ "notes": "..." }`. 404 if not found; 409 if already reviewed. |

List and detail responses both include `helmet_design_id` — `null` except on `helmet`-type submissions once a moderator has created the design record via `from_submission_id`.
