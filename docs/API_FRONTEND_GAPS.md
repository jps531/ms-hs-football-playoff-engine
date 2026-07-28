# API Gaps for Frontend — Implementation Spec

Context: the frontend (Next.js, not yet built) needs several read endpoints that
don't exist yet. The existing per-region/per-team API is complete; every gap
below is a **statewide or cross-region aggregation read** over snapshot tables
that are already populated (`region_standings`, `region_scenarios`,
`team_ratings`, `games`), plus one contract fix. All new endpoints are
**public GET reads** (no auth), follow the existing `season` + `date` query
param conventions, and should read from dated snapshots (falling back to the
latest snapshot ≤ `date`, same as existing standings behavior). Add each to the
README API Reference tables and cover with tests per the existing patterns.

---

## 3. `GET /insights` — statewide key-insights feed

**UI purpose:** Home page "insights feed": plain-English clinch/elimination
facts from across ALL regions, newest first ("Taylorsville clinched Region
3-4A last night"). Insights currently exist only inside per-region standings
responses (`region_scenarios.key_insights`).

**Params:** `season` (required), `since` (optional date), `limit` (default 50),
optional `clazz`, `region`, `team` filters.

**Response:**
```json
{
  "insights": [
    {
      "as_of_date": "2025-10-14",
      "class": "4A",
      "region": 3,
      "teams": ["Taylorsville"],
      "human_text": "Taylorsville clinches 1st seed: Taylorsville beats Stringer",
      "kind": "clinch_seed_1"
    }
  ]
}
```
- `teams` = every school named in the insight (UI renders helmet chips + links).
- `kind` = machine tag if derivable from the stored insight structure
  (`clinch_seed_N`, `clinch_playoffs`, `eliminated`, ...); `null` if not.

**Dedup semantics (important):** the same insight text persists across
consecutive snapshots until resolved. The feed must show each insight ONCE,
dated to the FIRST snapshot where it appeared. Implementation: for each
region, walk `region_scenarios` snapshots in date order and emit an insight
with the `as_of_date` of the first snapshot containing it (string or
structural equality); skip re-appearances. Order the response newest-first.

---

## 4. Win probability on game rows (+ live)

**UI purpose:** game pages and the scoreboard grid render a pregame "tug of
war" probability bar and a live-updating probability per game. Today the
frontend would need 1–2 extra calls per game (`/games/probability` takes team
names; `/probability/live` requires the caller to compute `seconds_remaining`).
A scoreboard polling 40 live games cannot make 80 calls per tick.

**Change:** embed probability directly in `GET /games` responses. Games are
school-perspective rows (two per contest), so all probabilities are **from the
perspective of the row's `school`**:

- `pregame_prob` (float | null) — Elo-based P(school wins), computed from
  `team_ratings` **as of the game date** (snapshots exist via backfill), with
  the existing home-field/location adjustment. Null if either team unrated.
- `live_prob` (float | null) — only non-null when the game is in progress:
  derive `seconds_remaining` server-side from `game_quarter` + `game_clock`
  (12-minute quarters), route through the existing live model; when
  `overtime > 0`, route through the existing OT model instead.
- `prob_as_of` (timestamp) — when the probability was computed, so the UI can
  show staleness ("as of 8:47 · Q3").

Keep the existing `/games/probability*` endpoints unchanged (still useful for
hypothetical matchups).

**Implementation notes:** pregame prob for FINAL games must use ratings as of
the game date, NOT current ratings — this is what makes the upset ledger (§5)
and historical timeline honest. Consider persisting `pregame_prob` onto the
game row when the score pipeline marks it final, to avoid recompute; live
values stay computed-at-read.

---

## 5. `GET /games/upsets` + `GET /ratings/movers`

**UI purpose:** two home-page modules.
- **Upset ledger:** finished games where the winner had a low pregame
  probability ("Enterprise had 12% — and won"). Builds model trust by
  celebrating misses.
- **Biggest movers:** largest Elo changes over a window ("Poplarville +64").

**`GET /games/upsets`** — params: `season` (required), `date_from`/`date_to`
(optional, default: the most recent completed game week), `limit` (default 10).
Returns final games sorted by winner's pregame prob ascending:
```json
{"upsets": [{"school": "Enterprise", "opponent": "...", "date": "2025-10-10",
  "points_for": 21, "points_against": 17, "pregame_prob": 0.12,
  "class": "2A", "region": 5, "region_game": true}]}
```
One row per CONTEST (deduplicate the two school-perspective rows; return the
winner's perspective). Depends on §4's dated pregame probabilities.

**`GET /ratings/movers`** — params: `season` (required), `date_from`/`date_to`
(optional, default: the two most recent rating snapshot dates), `limit`
(default 10 each direction). Returns
`{"risers": [{"school", "class", "region", "elo_before", "elo_after",
"delta"}...], "fallers": [...]}` sorted by |delta|. Reads two dated
`team_ratings` snapshots; teams present in only one snapshot are excluded.

---

## 6. `date` param on `GET /ratings`

**UI purpose:** the app has a GLOBAL timeline mode — every surface can be
viewed "as of" a past date via `?date=`. `/ratings` is the only major read
without a `date` param, which breaks time travel on the ratings page.

**Change:** add optional `date` to `GET /ratings`; resolve to the latest
`team_ratings` snapshot ≤ date, matching standings behavior exactly. (The
table is already dated; this is exposure, not computation.)

---

## 7. `GET /bracket/slots/{slot}` — playoff game/slot outlook

**UI purpose:** the playoff game page for a future/TBD matchup: every team
still alive for that slot, ordered by chance of reaching it, each with a
nested hosting bar (reach %, host-if-reached %, overall host %) and the
conditions under which they'd host. Currently this requires the frontend to
join bracket advancement + hosting odds + format slots per team.

**Params:** `season`, `class` (required); path `slot` identifies a
first-round slot from `playoff_format_slots`; optional `round` (default
`first_round`) addresses the derived round-2+ games implied by adjacent slot
pairs; optional `date`.

**Response:**
```json
{
  "class": "4A", "round": "quarterfinals", "slot": 3,
  "as_of_date": "2025-10-28",
  "teams": [
    {
      "school": "Taylorsville",
      "p_reach": 0.34,
      "p_host_given_reach": 0.82,
      "p_host_overall": 0.28,
      "reach_conditions": <structured conditions, §8 format, or null>,
      "host_conditions": <structured conditions, §8 format, or null>
    }
  ]
}
```
- `p_reach` comes from bracket advancement odds; `p_host_given_reach` from the
  hosting computation; `p_host_overall` is their product — compute it
  server-side so the three values are always consistent.
- `host_conditions` derive from seed-comparison logic against the bracket
  format (hosting can depend on games neither team plays in; that's expected).
  If condition derivation is expensive, ship the three probabilities first and
  add conditions in a follow-up — but keep the fields in the schema as null.

**Existing building blocks:** `enumerate_team_matchups()`
(`backend/helpers/home_game_scenarios.py`) and `team_matchups_as_dict()`
(`backend/helpers/scenario_renderer.py`) already compute per-team, per-round
`p_reach`/`p_host_given_reach`/`p_host_overall` with this exact consistency
guarantee, and the structured-condition types backing
`reach_conditions`/`host_conditions` already exist and are serialized
elsewhere (`ScenarioEntry.conditions`, `KeyInsightModel.conditions`). Neither
is currently called from any router. Implementing this endpoint is largely
inverting that team-keyed data into the slot-keyed shape above and renaming
the condition fields, not computing from scratch.

---

## 9. `GET /seasons/{season}/dates` — timeline scrubber data

**UI purpose:** a global timeline scrubber (app shell chrome) needs the set of
valid dates to snap to, without downloading full schedules.

**Response:**
```json
{
  "season": 2025,
  "dates": [
    {"date": "2025-10-10", "kind": "games", "week": 8, "num_games": 112},
    {"date": "2025-10-14", "kind": "snapshot", "week": 8},
    {"date": "2025-11-07", "kind": "games", "week": null,
     "round": "first_round", "num_games": 96}
  ]
}
```
- `kind` ∈ `games | snapshot` (a date can appear once with `kind: "games"`
  even if both apply; include snapshot-only dates separately).
- `round` non-null for playoff dates; `week` for regular season if week
  numbers are derivable, else null (the UI can label by date alone).
- Tiny payload; cache aggressively.

---

## Priority order for implementation

1. §4 (blocks game pages + scoreboard)
2. §3 (home page feed)
3. §7 (playoff game pages + naming contract)
4. §6, §9 (small; timeline completeness)
5. §5 (home page modules; depends on §4)
