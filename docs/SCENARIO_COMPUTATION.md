# Scenario Computation Model

This document describes how the tiebreaker engine decides what to compute and store at each stage of the season, and what gets exposed to the frontend.

## Background: What Gets Computed

The engine produces two distinct things for each class/region/date snapshot:

1. **Seeding odds** — per-team probabilities of finishing 1st, 2nd, 3rd, 4th, and making playoffs. Always computed and stored, regardless of how many games remain.

2. **Scenario data** — the explicit list of game outcomes that lead to each seeding result. Two layers:
   - `scenario_atoms`: a compact per-team, per-seed boolean expression (e.g., "Pearl beats Petal AND wins by ≥3"). Used to generate human-readable scenario text.
   - `complete_scenarios`: the full cross-product enumeration of all outcome combinations, each paired with its resulting seeding. Drives the rendered scenario list shown in the UI.

---

## R: Remaining Region Games

`R` is the count of unplayed region games at a given snapshot date. It determines how the engine behaves. For reference, the 2025 season regions have:

- 4–5 team regions: ~6 total region games, R reaches 0 after ~3 game-weeks
- 6–7 team regions: up to 21 total region games (C(7,2) = 21 for a 7-team round-robin), R reaches 0 after all games are played

---

## Computation Tiers

### R ≤ 4 — Full margin-sensitive computation

The engine runs the complete `12^R × 2^R` enumeration: every possible win/loss combination AND every possible point margin combination for each outcome. This produces exact, margin-aware scenario atoms and complete scenarios.

Both `scenario_atoms` and `complete_scenarios` are stored and are eligible for UI display (subject to the display threshold below).

**Why the full enumeration is feasible here:** R ≤ 4 means at most `12^4 × 2^4 = 248,832` combinations — runs in well under a second.

### R 5–6 — Win/loss first, margin upgrade in background

With R = 5 or 6, the full `12^R` margin enumeration is slower (~seconds). The engine uses a two-phase approach:

1. **Phase 1 (synchronous):** Enumerate all 2^R win/loss outcomes without margin sensitivity. Write `scenario_atoms` and `complete_scenarios` to the DB immediately so the API can serve them.
2. **Phase 2 (background task):** Run the full `12^R` margin enumeration and overwrite with the margin-accurate version.

During the window between Phase 1 and Phase 2 completing, the stored data is marked `margin_compute_status = "pending"`. The API can surface this state to the frontend if needed (e.g., "Margin tiebreakers not yet computed").

Historical backfill skips Phase 2 — past data is final, so win/loss-only is used for those snapshots.

### R 7–10 — Win/loss enumeration, no margin

Margin sensitivity is skipped entirely. All 2^R outcomes are enumerated once at a fixed default margin. `scenario_atoms` and `complete_scenarios` are stored.

Note: `build_scenario_atoms` uses boolean minimization (Quine-McCluskey) over the 2^R outcome space. At R = 10, this is 1,024 outcomes × 4 seeds × 7 teams — still manageable in a few seconds. At R = 11+, the QMC complexity grows quadratically and `build_scenario_atoms` returns `{}` early (see next tier).

### R 11–15 — Win/loss enumeration, atoms always empty

`build_scenario_atoms` returns `{}` for R > 10. The `enumerate_division_scenarios` step still runs over all 2^R outcomes and stores `complete_scenarios`, but without atoms the results are flat enumerations without human-readable conditions attached.

`complete_scenarios` is stored but not shown in the UI (see display threshold below).

### R > 15 — Monte Carlo odds, no scenario enumeration

At this range (common for 7-team regions early in the season, where R can reach 20+), full 2^R enumeration becomes impractical — 2^20 = 1,048,576 outcome masks produces millions of complete scenarios.

The engine switches to **Monte Carlo sampling** (50,000 draws). Each sample draws a win/loss outcome for every remaining game according to each team's Elo win probability — so the resulting odds are **Elo-weighted**, not uniform. The sample frequency of any seeding outcome is proportional to its true probability under the Elo model.

`scenario_atoms` and `complete_scenarios` are both written as empty (`{}` / `[]`). With 15+ games remaining, scenario descriptions are not actionable ("to clinch 1st, Pearl needs to win the next 15 games and one of ~37,000 specific combinations of other results") and the storage cost would be enormous.

---

## Frontend Display Threshold: R ≤ 6

Even though scenario data is stored for R ≤ 15, the frontend only **renders the human-readable scenario list** when **R ≤ 6** (approximately the final two weeks of region play for every 2025 region).

At R ≤ 6, the engine guarantees full margin accuracy (synchronously for R ≤ 4, after background upgrade for R = 5–6). Scenarios at this range are compact and actionable: at most 64 distinct outcomes for a 6-game remaining window.

At R > 6, the number of distinct outcomes and conditions grows too large to present readably. The frontend shows seeding odds (always available) but omits the scenario list.

**API contract:** The `scenarios_available` flag on every standings response is `true` when `r_remaining ≤ 6`. This is computed at read time from the stored `r_remaining` field — no separate stored flag.

---

## Summary Table

| Remaining games (R) | Odds method | Atoms stored | Complete scenarios stored | Shown in UI |
|---|---|---|---|---|
| 0 | Exact (1 outcome) | Yes | Yes | Yes |
| 1–4 | Exact (2^R × 12^R) | Yes, margin-accurate | Yes | Yes |
| 5–6 | Exact (2^R, margin upgraded in background) | Yes | Yes | Yes |
| 7–10 | Exact (2^R, no margin) | Yes, win/loss only | Yes | No |
| 11–15 | Exact (2^R, no margin) | Empty (QMC limit) | Yes, flat | No |
| > 15 | Monte Carlo, 50K samples, Elo-weighted | Empty | Empty | No |

---

## Relevant constants in `region_scenarios_pipeline.py`

```python
_R_ALWAYS_MARGIN = 4   # R ≤ this: full 12^R margin enumeration, synchronous
_R_BACKGROUND_MAX = 6  # R ≤ this (> _R_ALWAYS_MARGIN): win/loss first, margin upgraded async
_R_MAX_COMPUTE = 15    # R > this: Monte Carlo odds only, skip all scenario enumeration
```

And in `scenario_viewer.py`:

```python
# build_scenario_atoms() line ~1479:
if R > 10:
    return {}  # QMC complexity too high; atoms are empty at this range
```
