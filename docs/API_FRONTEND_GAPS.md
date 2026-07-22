# API Gaps for Frontend — Implementation Spec

Context: the frontend (Next.js, not yet built) needs several read endpoints that
don't exist yet. The existing per-region/per-team API is complete; every gap
below is a **statewide or cross-region aggregation read** over snapshot tables
that are already populated (`region_standings`, `region_scenarios`,
`team_ratings`, `games`), plus two contract fixes. All new endpoints are
**public GET reads** (no auth), follow the existing `season` + `date` query
param conventions, and should read from dated snapshots (falling back to the
latest snapshot ≤ `date`, same as existing standings behavior). Add each to the
README API Reference tables and cover with tests per the existing patterns.

Naming contract used throughout (also a rename task, see §7):
- `p_reach` — probability of reaching a given playoff round/game
- `p_host_given_reach` — probability of hosting that game, conditional on reaching it
- `p_host_overall` — `p_reach × p_host_given_reach`
- Never use the words "conditional" or "marginal" in field names, docs, or UI copy.

---

## 1. `GET /standings/summary` — statewide summary (grand view)

**UI purpose:** The standings "grand view" — a grid of compact cards, one per
region across every class, showing at a glance: leader, clinch/elimination
counts, and how unsettled the race is. Must load in ONE request.

**Params:** `season` (required), `date` (optional, default latest).

**Response:**
```json
{
  "season": 2025,
  "as_of_date": "2025-10-14",
  "classes": [
    {
      "class": "4A",
      "regions": [
        {
          "region": 3,
          "leader": {"school": "Taylorsville", "region_wins": 5, "region_losses": 0},
          "num_teams": 6,
          "num_clinched": 1,
          "num_eliminated": 2,
          "teams_alive": 3,
          "volatility": 0.62,
          "statuses": [
            {"school": "Taylorsville", "status": "clinched"},
            {"school": "Heidelberg", "status": "alive"},
            {"school": "Mize", "status": "eliminated"}
          ]
        }
      ]
    }
  ]
}
```
- `leader` = current #1 by the same ordering the standings endpoint uses.
- `statuses` is ordered by current standing (drives a per-team status dot strip
  in the UI). `status` ∈ `clinched | alive | eliminated`.
- `volatility` ∈ [0,1]: how unsettled the region is. Suggested definition:
  mean over non-eliminated teams of the normalized Shannon entropy of each
  team's seed distribution `[p1, p2, p3, p4, 1 − p_playoffs]` (entropy / log 5).
  Fully decided region → 0. Put the formula in one helper with a docstring;
  it may get tuned later. Use unweighted odds.

**Implementation:** one query over the latest `region_standings` snapshot per
region for the season/date; no scenario data needed. Should be fast enough to
compute per request; cacheable.

---

## 2. `GET /standings/{clazz}` — all regions in a class (class view)

**UI purpose:** The standings "class view": full standings tables for every
region in one class, one request. Same table shape the UI already gets from
`GET /standings/{clazz}/{region}`, minus scenarios.

**Params:** `season` (required), `date` (optional).

**Response:** `{"class": "4A", "as_of_date": ..., "regions": [ <existing
per-region standings response, WITHOUT the scenarios and computation_state
blocks — teams[] with odds/bracket_odds/home_game_odds/clinched/eliminated/
coin_flip_needed only> ]}`

**Implementation:** reuse the existing per-region read path in a loop or single
query; explicitly exclude scenario payloads (they're large and the class view
doesn't render them).

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

## 7. `GET /bracket/slots/{slot}` — playoff game/slot outlook (+ naming/simulate fixes)

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

**Two related fixes while in this code:**
1. **Rename** hosting/bracket response fields to the naming contract:
   `home_game_odds` entries become `p_host_given_reach` (+ `_weighted`), and
   anywhere docs/fields say "conditional probability of hosting," use the
   contract names. Advancement odds may keep their round-keyed shape but
   document them as `p_reach` semantics.
2. **Simulate parity:** `bracket_odds` and `home_game_odds` are currently
   `null` on simulate paths. The UI's simulate mode re-resolves hosting and
   advancement odds after each pick (this is a core feature on the bracket
   page). At minimum, `POST /bracket/simulate` and the hosting simulate
   endpoints must return real (non-null) advancement + hosting numbers;
   standings simulate may keep them null if computing them there is
   prohibitive, but document which paths return what.

---

## 8. Structured per-team scenario conditions (contract check)

**UI purpose:** three features consume MINIMIZED per-team conditions (stored
in `region_scenarios.scenario_atoms`):
- condition "chips" (e.g., [beats Stringer] AND [Mize loses to Raleigh]),
- a team-page "Paths" module (all achievable outcomes, best→worst, each with
  its conditions),
- "Play this out" — converting a scenario's conditions into simulate-mode
  picks via URL.

The standings response currently exposes `scenarios` as complete outcome
enumerations (`game_winners` → `outcomes`) — right for the region scenario
explorer, but NOT sufficient for the above. Verify/expose the minimized
per-team form with this structure (on both
`GET /standings/{clazz}/{region}` per team and the `/teams/{team}` variant):

```json
"paths": [
  {
    "outcome": {"type": "seed", "value": 1},
    "p": 0.41,
    "conditions": [
      [
        {"school": "Taylorsville", "date": "2025-10-17",
         "opponent": "Stringer", "required_result": "win",
         "margin_class": null},
        {"school": "Mize", "date": "2025-10-17",
         "opponent": "Raleigh", "required_result": "loss",
         "margin_class": null}
      ],
      [ ...alternative AND-group... ]
    ],
    "human_text": "Taylorsville clinches the 1 seed with a win, or if Mize loses"
  }
]
```
- Outer array = OR groups; inner array = ANDed atomic conditions. An
  unconditional/clinched outcome has `conditions: []`.
- Each atom references a game by its composite key (`school`, `date`) so the
  frontend can map conditions to simulate picks and to schedule rows.
- `outcome.type` ∈ `seed | playoffs | eliminated`; include `p` (unweighted)
  so the UI can order OR branches by likelihood ("Play this out" picks the
  most probable branch).
- `margin_class` carries margin-sensitive conditions when applicable (use the
  existing margin bucket vocabulary); null otherwise.
- Keep `human_text` as fallback copy, but the structured form is the contract —
  the frontend must never parse English.

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

1. §1 + §2 (blocks two of three standings views — the app's core surface)
2. §8 (blocks chips/Paths/"play this out" — verify before frontend starts)
3. §4 (blocks game pages + scoreboard)
4. §3 (home page feed)
5. §7 (playoff game pages + naming contract; do renames early to avoid churn)
6. §6, §9 (small; timeline completeness)
7. §5 (home page modules; depends on §4)
