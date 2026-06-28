# Scenario Computation Model

This document describes how the tiebreaker engine decides what to compute and store at each stage of the season, and what gets exposed to the frontend.

## Background: What Gets Computed

The engine produces three distinct things for each class/region/date snapshot:

1. **Seeding odds** — per-team probabilities of finishing 1st, 2nd, 3rd, 4th, and making playoffs. Always computed and stored, regardless of how many games remain.

2. **Scenario data** — the explicit list of game outcomes that lead to each seeding result. Two layers:
   - `scenario_atoms`: a compact per-team, per-seed boolean expression (e.g., "Pearl beats Petal AND wins by ≥3"). Used to generate human-readable scenario text.
   - `complete_scenarios`: the full cross-product enumeration of all outcome combinations, each paired with its resulting seeding. Drives the rendered scenario list shown in the UI.

3. **Key insights** — simple, unconditionally-true conditional statements extracted from `scenario_atoms` (e.g., "Taylorsville clinches 1st seed: Taylorsville beats Stringer" or "Murrah is eliminated: Starkville beats Terry"). Each insight has 1–3 `GameResult` conditions and is margin-verified before storage. Stored at all tiers where atoms exist (R ≤ 10). Shown at all R values: as a headlines banner at R ≤ 6 alongside the full scenario list, and as the only scenario-level content at R 7–10.

> **Note on margin accuracy at R = 6:** At R = 6, scenarios and insights are win/loss-only (no margin conditions). Full margin-sensitive computation is bounded at R ≤ 5 due to the memory cost of 12^6 enumeration at backfill scale.

---

## R: Remaining Region Games

`R` is the count of unplayed region games at a given snapshot date. It determines how the engine behaves. For reference, the 2025 season regions have:

- 4–5 team regions: ~6 total region games, R reaches 0 after ~3 game-weeks
- 6–7 team regions: up to 21 total region games (C(7,2) = 21 for a 7-team round-robin), R reaches 0 after all games are played

---

## Computation Tiers

### R ≤ 5 — Full margin-sensitive computation

The engine runs the complete `12^R × 2^R` enumeration: every possible win/loss combination AND every possible point margin combination for each outcome. This produces exact, margin-aware scenario atoms and complete scenarios.

Both `scenario_atoms` and `complete_scenarios` are stored and are eligible for UI display (subject to the display threshold below).

**Why the full enumeration is feasible here:** R ≤ 5 means at most `12^5 × 2^5 = ~8M` combinations — runs in a few seconds. `_is_margin_sensitive_mask()` skips the 12^R inner loop for masks where margin doesn't affect tiebreakers, so actual runtime is typically well under this ceiling.

### R 6–10 — Win/loss enumeration, no margin

Margin sensitivity is skipped entirely. All 2^R outcomes are enumerated once at a fixed default margin. `scenario_atoms` and `complete_scenarios` are stored.

Key insights are extracted and stored at this tier. Because atoms are computed with `ignore_margins=True`, each insight candidate is spot-checked across all 12^k margin combinations for its k condition games before being emitted — only claims that hold for every combination are stored (`margin_verified=True`). This makes them unconditionally true even at this tier despite the win/loss-only atoms.

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

At R ≤ 5, the engine guarantees full margin accuracy synchronously. At R = 6, scenarios are win/loss-only (no margin conditions) but are still compact and actionable: at most 64 distinct outcomes for a 6-game remaining window.

At R > 6, the number of distinct outcomes and conditions grows too large to present readably. The frontend shows seeding odds (always available) and key insights (when atoms exist, R ≤ 10), but omits the full scenario list.

**API contract:** The `scenarios_available` flag on every standings response is `true` when `r_remaining ≤ 6`. The `key_insights` list is non-empty whenever actionable insights were extractable from the stored atoms (R ≤ 10, non-trivial standings). Both are computed at pipeline time and read directly from the snapshot.

---

## Summary Table

| Remaining games (R) | Odds method | Atoms stored | Complete scenarios stored | Key insights stored | Shown in UI |
|---|---|---|---|---|---|
| 0 | Exact (1 outcome) | Yes | Yes | Yes (facts only) | Yes |
| 1–5 | Exact (2^R × 12^R) | Yes, margin-accurate | Yes | Yes, margin-accurate | Yes |
| 6–10 | Exact (2^R, no margin) | Yes, win/loss only | Yes | Yes, 12^k verified | Yes (R=6), Key insights only (R 7–10) |
| 11–15 | Exact (2^R, no margin) | Empty (QMC limit) | Yes, flat | Empty | No |
| > 15 | Monte Carlo, 50K samples, Elo-weighted | Empty | Empty | Empty | No |

---

## Relevant constants in `region_scenarios_pipeline.py`

```python
_R_ALWAYS_MARGIN = 5   # R ≤ this: full 12^R margin enumeration, synchronous
_R_MAX_COMPUTE = 15    # R > this: Monte Carlo odds only, skip all scenario enumeration
```

And in `scenario_viewer.py`:

```python
# build_scenario_atoms() line ~1479:
if R > 10:
    return {}  # QMC complexity too high; atoms are empty at this range
```
