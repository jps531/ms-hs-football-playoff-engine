# API Gaps for Frontend — Implementation Spec

Context: the frontend (Next.js, not yet built) needs several read endpoints that
don't exist yet. The existing per-region/per-team API is complete; every gap
below is a **statewide or cross-region aggregation read** over snapshot tables
that are already populated (`region_standings`, `region_scenarios`,
`team_ratings`, `games`). All new endpoints are **public GET reads** (no auth),
follow the existing `season` + `date` query param conventions, and should read
from dated snapshots (falling back to the latest snapshot ≤ `date`, same as
existing standings behavior). Add each to the README API Reference tables and
cover with tests per the existing patterns.

(Historical numbering note: `GET /insights` and `date` on `GET /ratings` — both
originally listed here as §3 and §6 — have since shipped and are documented in
`API_REFERENCE.md`; those numbers are retired and unrelated to the current §3
below. A repo-wide sweep also confirmed every other snapshot-backed endpoint
already supports `date`/`date_from`/`date_to`, and `/rankings`, `/ratings`, and
`/games/probability` were renamed from `as_of` to `date` for naming
consistency. §8 — the `paths` structured-condition contract on `/standings` —
has also shipped; see its use below and in `API_REFERENCE.md`.)

---

## 1. `GET /bracket/slots/{slot}` — playoff slot probabilities

**UI purpose:** the playoff game page for a future/TBD matchup: every team
still alive for that slot, ordered by chance of reaching it, each with a
nested hosting bar (reach %, host-if-reached %, overall host %). Currently
this requires the frontend to join bracket advancement + hosting odds +
format slots per team.

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
      "reach_conditions": null,
      "host_conditions": null
    }
  ]
}
```
- `p_reach` comes from bracket advancement odds; `p_host_given_reach` from the
  hosting computation; `p_host_overall` is their product — compute it
  server-side so the three values are always consistent, mirroring the
  existing `overall_home_odds()` pattern (`backend/helpers/bracket_home_odds.py`).
- `reach_conditions`/`host_conditions` are always `null` for this section —
  see §2 and §3.

**Building blocks — corrected from an earlier draft of this spec:** the
functions once proposed here (`enumerate_team_matchups()`,
`team_matchups_as_dict()` in `home_game_scenarios.py`/`scenario_renderer.py`)
are unused in production, require an already-clinched seed (no pre-clinch
path), and carry only a free-text `explanation`, not structured data. Do not
build this endpoint on top of them.

The real starting point is `TeamBracketEntry`
(`backend/api/models/responses.py`), already served by `GET /api/v1/bracket`
via `build_bracket_entries()` (`backend/helpers/api_helpers.py`). It's already
slot-keyed (`region`+`seed`) and already carries the exact three-number
consistency guarantee via its nested `hosting: BracketSlotHosting`. Two things
are still genuinely new work, not a reshape of existing output:
1. `TeamBracketEntry` is single-occupant per slot (`school` nullable
   pre-clinch). This endpoint needs every team still mathematically alive for
   a slot pre-clinch, enumerated from per-region seeding odds (the `p1..p4`
   concept already computed for `/rankings`), collapsing to one school once
   `p_seed >= 0.999` (the same clinch threshold `TeamBracketEntry` already
   uses).
2. `playoff_format_slots.slot` only identifies first-round games — there is
   no persisted ID for round-2+ slots. `round=second_round`/`quarterfinals`/
   `semifinals` must be resolved by grouping the underlying first-round slots
   via the existing `opponent_slot_indices()`/`opponent_slots()` logic in
   `bracket_home_odds.py`.

---

## 2. `host_conditions` for `GET /bracket/slots/{slot}` (follow-up)

**UI purpose:** the conditions under which a team would host, if it reaches
the slot's round — nested under each team in §1's response once available.

**Depends on:** §1 shipping first.

`host_conditions` should reuse the same structured-condition envelope §8's
`paths` feature already ships (`ScenarioPathModel`/`PathConditionModel`,
`backend/api/models/responses.py`) — but §8's atom types (`game_result`,
`margin_sum`, `coin_flip`, `pd_rank`) are all keyed to a concrete, dated,
named-opponent regular-season game, and bracket hosting conditions are about
hypothetical future playoff games with no fixed date and often no fixed
opponent yet (hosting can depend on games neither team plays in). Before
implementing, decide:
- (a) add a new `PathConditionModel` atom type (e.g. `bracket_advances`/
  `seed_required`) mirroring `HomeGameCondition`'s fields (`kind`,
  `round_name`, `region`, `seed`, `team_name` —
  `backend/helpers/data_classes.py`), so this endpoint can genuinely reuse
  the §8 envelope; or
- (b) give bracket conditions their own sibling model instead of stretching
  §8's schema to a domain it wasn't built for.

Either way, the underlying data already exists and is reachable: adapt the
`HomeGameCondition` + `serialize_condition()` + `team_home_scenarios_as_dict()`
pipeline already used for hosting explanations in
`backend/api/routers/hosting.py`'s `_attach_hosting_scenarios()`.

---

## 3. `reach_conditions` for `GET /bracket/slots/{slot}` (undesigned — separate effort)

**UI purpose:** the conditions under which a team reaches the slot's round at
all — distinct from §2's "conditions under which they'd host, given they
reached."

No structured-condition type for this exists anywhere in the codebase today
— neither §8's regular-season-game atoms nor `HomeGameCondition` (which only
models hosting/advancement facts about *other* bracket positions, not the
reasons a specific team advances). This needs its own design pass before
estimating or building; don't bundle it into §2's scope.

---

## 4. `GET /seasons/{season}/dates` — timeline scrubber data

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
winner's perspective). Depends on `/games/probability`'s dated pregame
probabilities (already shipped; see `API_REFERENCE.md`).

**`GET /ratings/movers`** — params: `season` (required), `date_from`/`date_to`
(optional, default: the two most recent rating snapshot dates), `limit`
(default 10 each direction). Returns
`{"risers": [{"school", "class", "region", "elo_before", "elo_after",
"delta"}...], "fallers": [...]}` sorted by |delta|. Reads two dated
`team_ratings` snapshots; teams present in only one snapshot are excluded.

---

## Priority order for implementation

1. §1 (playoff game pages + naming contract — ship the three probabilities
   first, `reach_conditions`/`host_conditions` as `null`)
2. §4 (small; timeline completeness)
3. §5 (home page modules; depends on already-shipped `/games/probability`
   dated pregame probabilities)
4. §2 (`host_conditions` follow-up, once §1 ships)
5. §3 (`reach_conditions` — separate, undesigned effort; scope before
   estimating)
