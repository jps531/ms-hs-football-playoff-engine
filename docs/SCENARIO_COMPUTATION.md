# Scenario Computation Model

This document describes how the tiebreaker engine decides what to compute and store at each stage of the season, and what gets exposed to the frontend. For the underlying MHSAA policy this engine implements, see [SCENARIO_RULES.md](SCENARIO_RULES.md) (region tiebreaker procedure) and [PLAYOFF_HOME_RULES.md](PLAYOFF_HOME_RULES.md) (playoff home-site rules).

## Background: What Gets Computed

The engine produces three distinct things for each class/region/date snapshot:

1. **Seeding odds** — per-team probabilities of finishing 1st, 2nd, 3rd, 4th, and making playoffs. Always computed and stored, regardless of how many games remain.

2. **Scenario data** — the explicit list of game outcomes that lead to each seeding result. Two layers:
   - `scenario_atoms`: a compact per-team, per-seed boolean expression (e.g., "Pearl beats Petal AND wins by ≥3"). Used to generate human-readable scenario text, and read directly by the API (`include_team_scenarios=true`) to build the `paths` field described below.
   - `complete_scenarios`: the full cross-product enumeration of all outcome combinations, each paired with its resulting seeding. Drives the rendered scenario list shown in the UI. At R ≤ 5 the pipeline also gives each one `p` and `p_weighted`: the chance of its finish (seeding plus any ties left open), Toss-up and Projected, summed over every set of winners and margins that produces it, with margins weighted as the odds weight them. Several scenarios can reach one finish by different results and then share its chance; the UI shows one card per finish, its ways joined by OR, so the cards' chances add up to 100%.

   **`paths` (API-level, not separately stored):** `GET /standings/{clazz}/{region}?include_team_scenarios=true` exposes each team's `scenario_atoms` entry as a `paths` list — one entry per achievable outcome (a specific seed, "playoffs" regardless of seed, or "eliminated"), each with its OR-of-AND conditions and the outcome's existing `p1`–`p4`/`p_playoffs` probability. This is computed at request time from the stored `scenario_atoms` (plus a live lookup of each condition's game date) — no separate column. The "playoffs" outcome doesn't exist as its own `scenario_atoms` bucket; it's derived by unioning the per-seed atom lists and re-running the same boolean minimizer (`_simplify_atom_list`) used internally by `build_scenario_atoms`. See `backend.helpers.api_helpers.build_team_paths`.

3. **Key insights** — simple, unconditionally-true conditional statements extracted from `scenario_atoms` (e.g., "Taylorsville clinches 1st seed: Taylorsville beats Stringer" or "Murrah is eliminated: Starkville beats Terry"). Each insight has 1–3 `GameResult` conditions and is margin-verified before storage. Stored at all tiers where atoms exist (R ≤ 10). They feed each region's headline at every R, and they're the only scenario-level content shown at R 6–10.

> **Note on margin accuracy above R = 5:** For R > 5, the odds are win/loss-only: a tie that reaches point differential (steps 3–4) is broken as if every remaining game were won by 7, so those odds are close but not exact. Scenarios don't guess: `enumerate_division_scenarios` leaves such a tie open ("order decided by the tiebreaker"), so they stay accurate, just less specific. Full margin-sensitive computation is bounded at R ≤ 5 due to the memory cost of 12^6 enumeration at backfill scale, and the scenario list is shown only there, where a point-differential race is stated exactly (see the display threshold below). Key insights stay exact at any R ≤ 10 because each is margin-verified.

---

## R: Remaining Region Games

`R` is the count of unplayed region games at a given snapshot date. It determines how the engine behaves. For reference, the 2025 season regions have:

- 4-team regions: 6 region games (C(4,2)), played over 3 game-weeks
- 5-team regions: 10 region games, over 5 game-weeks
- 6–7 team regions: 15 or 21 region games (C(7,2) = 21 for a 7-team round-robin), over 5 or 7 game-weeks

---

## Computation Tiers

### R ≤ 5 — Full margin-sensitive computation

The engine runs the complete `12^R × 2^R` enumeration: every possible win/loss combination AND every possible point margin combination for each outcome. This produces exact, margin-aware scenario atoms and complete scenarios.

For the odds, each margin combination is weighted by how often those margins happened in 2025's 483 region games (`scenarios.py`): league-wide (`_MARGIN_SHARE`) for Toss-up odds, and by the winner's pregame Elo chance (`projected_margin_share`) for Projected odds. When a tie reaches fewest points allowed (step 5) with a tied team still to play, the remaining games' scores are drawn from 2025's score shapes (`_resolve_with_scores`), so an order only points allowed can give gets its share.

Both `scenario_atoms` and `complete_scenarios` are stored and are eligible for UI display (subject to the display threshold below).

**Why the full enumeration is feasible here:** R ≤ 5 means at most `12^5 × 2^5 = ~8M` combinations — runs in a few seconds. `_is_margin_sensitive_mask()` skips the 12^R inner loop for masks where margin doesn't affect tiebreakers, so actual runtime is typically well under this ceiling.

### R 6–10 — Win/loss enumeration, no margin

Margin sensitivity is skipped entirely. For the odds, all 2^R outcomes are enumerated once at a fixed default margin of 7 points. `scenario_atoms` and `complete_scenarios` are stored; any tie that reaches point differential is left open in them rather than settled at that default. The scenario list isn't shown at this tier (see the display threshold below).

Key insights are extracted and stored at this tier. Because atoms are computed with `ignore_margins=True`, each insight candidate is spot-checked across all 12^k margin combinations for its k condition games before being emitted — only claims that hold for every combination are stored (`margin_verified=True`). This makes them unconditionally true even at this tier despite the win/loss-only atoms.

Note: `build_scenario_atoms` uses boolean minimization (Quine-McCluskey) over the 2^R outcome space. At R = 10, this is 1,024 outcomes × 4 seeds × 7 teams — still manageable in a few seconds. At R = 11+, the QMC complexity grows quadratically and `build_scenario_atoms` returns `{}` early (see next tier).

### R 11–15 — Win/loss enumeration, atoms always empty

`build_scenario_atoms` returns `{}` for R > 10. The `enumerate_division_scenarios` step still runs over all 2^R outcomes and stores `complete_scenarios`, but without atoms the results are flat enumerations without human-readable conditions attached.

`complete_scenarios` is stored but not shown in the UI (see display threshold below).

### R > 15 — Monte Carlo odds, no scenario enumeration

At this range (common for 7-team regions early in the season, where R can reach 20+), full 2^R enumeration becomes impractical — 2^20 = 1,048,576 outcome masks produces millions of complete scenarios.

The engine switches to **Monte Carlo sampling**, two runs of 50,000 draws each. For Projected odds, each sample draws a win/loss outcome for every remaining game according to each team's Elo win probability, so the sample frequency of any seeding outcome is its probability under the Elo model. For Toss-up odds, a separate run draws every game as a coin flip. (Without win probabilities the two runs would be identical, so one serves both.)

`scenario_atoms` and `complete_scenarios` are both written as empty (`{}` / `[]`). With 15+ games remaining, scenario descriptions are not actionable ("to clinch 1st, Pearl needs to win the next 15 games and one of ~37,000 specific combinations of other results") and the storage cost would be enormous.

---

## Frontend Display Threshold: R ≤ 5

Even though scenario data is stored for R ≤ 15, the frontend only **renders the human-readable scenario list** when **R ≤ 5** (`DISPLAY_THRESHOLD` in `api_helpers.py`), the range where the engine works through every winning margin, so a race that turns on point differential is stated exactly. Above it, scenarios would leave such a tie open; they'd be accurate but less specific, and the list is withheld as a product choice.

At R > 5, the frontend shows seeding odds (always available) and key insights (when atoms exist, R ≤ 10, each margin-verified), but omits the full scenario list. The hosting page's per-team scenarios follow the same threshold.

**API contract:** The `scenarios_available` flag on every standings response is `true` when `r_remaining ≤ 5`. The `key_insights` list is non-empty whenever actionable insights were extractable from the stored atoms (R ≤ 10, non-trivial standings). Both are computed at pipeline time and read directly from the snapshot.

---

## Certainty: when a chance reads 0% or 100%

The site shows 0% and 100%, and "clinched" and "eliminated", only for certainties (`backend/helpers/certainty.py`). Certainty is never read off a float, since an Elo-weighted chance can be smaller than any rounding keeps:

- **From the endings, not the odds.** Enumeration records every place each team can take (1–4, or out) in some ending, however small its share (`ScenarioResults.places_seen`). A seed no ending gives a team is 0%; the only place a team can take is 100%; a team that no ending leaves out has clinched. Toss-up and Projected weigh the same endings, so they're certain together.
- **Margins left open.** At R 6–15 every game is scored at 7 points. A tie that reaches point differential (step 3) with a tied team still to play could fall the other way at another margin, so each team in it can take any place the tie spans. A team is called clinched or eliminated only when that holds at every margin.
- **Simulation proves nothing.** At R > 15 an ending no run drew is still possible, so no chance is 0% or 100% and nobody is clinched or eliminated.
- **Everything else is kept uncertain.** A chance that isn't certain is stored at least one in a million (`UNCERTAIN_FLOOR`) away from 0 and 1, so every reader shows it as "<1%" or ">99%". The site uses one cutoff for "certain" everywhere (`CERTAIN_EPS`, the same in `format.js`). Advancement and hosting odds, built from the seed odds, are settled the same way in pairs (the pipeline writer and the API response models), with float noise within 1e-12 of 0 or 1 snapped to it (so a derived chance under one in a trillion would read as 0%).

The odds columns are `DOUBLE PRECISION` (`sql/migrations/2026_10_odds_double_precision.sql`); as `REAL` they rounded anything within about 6e-8 of 1 to exactly 1.

---

## Summary Table

| Remaining games (R) | Odds method | Atoms stored | Complete scenarios stored | Key insights stored | Shown in UI |
|---|---|---|---|---|---|
| 0 | Exact (1 outcome) | Yes | Yes | Yes (facts only) | Yes |
| 1–5 | Exact (2^R × 12^R, margins weighted by 2025 frequency) | Yes, margin-accurate | Yes | Yes, margin-accurate | Yes |
| 6–10 | 2^R at a default 7-point margin | Yes, win/loss only | Yes | Yes, 12^k verified | Key insights only |
| 11–15 | 2^R at a default 7-point margin | Empty (QMC limit) | Yes, flat | Empty | No |
| > 15 | Monte Carlo, 50K samples per mode (Elo for Projected, coin flips for Toss-up) | Empty | Empty | Empty | No |

---

## Relevant constants in `region_scenarios_pipeline.py`

```python
_R_ALWAYS_MARGIN = 5   # R ≤ this: full 12^R margin enumeration, synchronous
_R_MAX_COMPUTE = 15    # R > this: Monte Carlo odds only, skip all scenario enumeration
_R_MAX_ATOMS = 10      # R > this: no per-team atoms
```

In `api_helpers.py`:

```python
DISPLAY_THRESHOLD = 5  # R ≤ this: the scenario list is shown (equal to _R_ALWAYS_MARGIN)
```

And in `scenario_viewer.py`:

```python
# build_scenario_atoms():
if not remaining or len(remaining) > 10:
    return {}  # QMC complexity too high; atoms are empty at this range
```
