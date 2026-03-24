# Test Coverage Gaps

## Current state (2026-03-24)

| Module | Coverage | Notes |
|---|---|---|
| `data_classes.py` | **100%** | All dataclasses fully exercised |
| `data_helpers.py` | **100%** | All pure helpers covered |
| `scenarios.py` | **100%** | Scenario enumeration + consolidation fully covered |
| `scenario_serializers.py` | **100%** | |
| `scenario_renderer.py` | **91%** | Home game rendering + weighted odds untested |
| `scenario_viewer.py` | **92%** | Edge cases in atom derivation; some structural paths |
| `tiebreakers.py` | **86%** | Biggest gap: pair tiebreaker Steps 2–5 never exercised |
| `home_game_scenarios.py` | **96%** | Minor edge cases |
| `bracket_home_odds.py` | **86%** | Some class-size branches |
| **Total (unit-testable)** | **~93%** | |

All scenario output tests are "one week out" (one remaining game per team). No mid-season tests exist yet.

---

## tiebreakers.py — most significant gaps

### Pair tiebreaker Steps 2–5 never executed (lines 357–376, 417–450)

**What it is:** `_resolve_pair_using_steps` restarts the full tiebreaker chain for a 2-team tie.
Step 1 = direct H2H result. Steps 2–5 = records vs outside opponents, H2H capped PD,
PD vs outside, fewest PA.

**Why not covered:** In every existing test, every pair sent to `_resolve_pair_using_steps`
has already played each other, so Step 1 resolves it immediately. Steps 2–5 and the entire
`_pair_h2h_pd_capped` function (357–376) are dead code from a test perspective.

**What would cover it:** A mid-season test (2+ games remaining) where two leading teams are
tied and have **not yet played each other**. Step 1 scores 0–0, falling through to Steps 2–5.
This is the single highest-value gap to close.

---

### No-opponent cases in step arrays (lines 189, 203)

**What it is:** `res_vs` and `pd_vs` return `None` when a bucket team has no game (completed
or remaining) against a specific outside opponent.

**Why not covered:** Region 3-7A is a complete round-robin; every team has played or will
play every other team. In regions with fewer cross-divisional matchups this fires.

**What would cover it:** A mid-season fixture where a tied team has an outside opponent they
haven't played and won't play — or a region that doesn't play a full round-robin.

---

### Tied/drawn game results (lines 49–50, 103–104, 186, 314, 321–322)

**What it is:** When `res_a == 0` (game ends in a draw), both teams get 0.5 H2H points,
`T` increments in W/L standings, and `res_vs` returns `1` (split).

**Why not covered:** All 2025 region games had decisive W/L outcomes. Not season-timing
related — requires a real or synthetic drawn game.

**What would cover it:** A synthetic fixture with one tied game, verifying that:
- `standings_from_mask` accumulates `T` correctly
- H2H points split as 0.5/0.5
- Downstream tiebreaker steps treat the split correctly

---

---

## scenario_viewer.py — edge cases and structural paths

### Constrained elimination via margin ranges (lines 847–854)

**What it is:** `sometimes_elim_only_masks` — teams that are eliminated only for certain
margin combinations, not all. These get constrained elimination atoms with explicit margin ranges.

**Why not covered:** In one-game-remaining regions, elimination is usually unconditional
(you lose and you're out) or tied to a specific win/loss. The margin-conditional elimination
path needs a region where a team is in the mix for 4th seed but margin of a specific game
determines whether they make it.

**What would cover it:** A mid-season fixture with 2+ remaining games where a team's
elimination is margin-sensitive.

---

### `_find_combined_atom` MarginCondition intersection (lines 109–114)

**What it is:** When two atoms for the same seeding outcome both contain `MarginCondition`
objects, their constraints are intersected (keeping the tighter bound).

**Why not covered:** In all tested regions, combined atoms only merge `GameResult` conditions,
not `MarginCondition`s.

**What would cover it:** A scenario where a team can achieve a seed via two different
margin-conditional paths that overlap.

---

### `_split_non_rectangular_atom` non-contiguous bail-out (lines 237–241)

**What it is:** The `valid_split = False` path fires when the valid margin set for a 2-game
scenario can't be decomposed into contiguous rectangular sub-atoms.

**Why not covered:** All current non-rectangular valid sets happen to decompose cleanly.
This is a defensive fallback — low priority to cover.

---

### `_derive_atom` fallback paths (lines 391–397, 406–415)

The unconstrained-atom shortcut (391–397) fires when any combination of margins in a
2-game scenario produces the same seeding — meaning per-game bounds are fully redundant.
The hard fallback (406–415) fires when joint constraints can't describe the valid set
AND non-rectangular splitting fails. Both are defensive; unlikely to trigger in practice.

---

### `scenario_atoms=False` path in `enumerate_division_scenarios` (line 983→988)

When `scenario_atoms=False` is passed, `conditions_atom` is set to `None` for all scenarios.
No test calls `enumerate_division_scenarios` with this flag. A one-line test change would cover it.

---

### "Eliminated:" line in `render_scenarios_text` (lines 1048–1051)

This branch renders the eliminated team list in the division scenarios text output. It's not
currently hit — likely because `render_scenarios_text` isn't being called with enough teams,
or the call is going through a different path. Worth investigating.

---

## scenario_renderer.py — feature gaps

### Weighted odds rendering (lines 138, 140, 411, 413)

The combined `(p_unweighted – p_weighted Weighted)` and weighted-only formats in
`render_team_scenarios` and `render_team_home_scenarios` are untested. **Blocked on
Priority 5 implementation** — the weighted odds fields are not yet computed.

---

### Home game scenario rendering (lines 344–345, 381–382, 460, 476, 539, 630)

`render_team_home_scenarios` and `_render_home_scenario_block` have no tests at all.
This includes:
- `_render_condition_label` with `kind="seed_required"` (344–345)
- Unconditional home blocks with an explanation string (381–382, 460)
- Will-Not-Host block structure (476, 539)

Not season-timing related — separate feature area.

---

### `_render_margin_condition` edge cases (lines 66, 73, 77–79)

Specific math patterns in margin condition rendering:
- `>=` or `>` op with `t < 0` (line 66): sub-team's margin doesn't exceed add-team's by more than N
- `>=` or `>` op with `t == 0` (line 73): add-team's margin is at least as large
- Multi-term fallback with `+`/`−` format (lines 77–79): conditions with more than one team in `add` or `sub`

These would require synthetic `MarginCondition` objects with specific threshold/sign combinations.

---

### Fallback renderer for unknown condition type (line 88)

`return str(cond)` in `_render_condition`. Defensive — won't appear in normal operation.

---

## Would "earlier in season" tests cover these gaps?

| Gap | Covered by mid-season tests? |
|-----|------------------------------|
| Pair tiebreaker Steps 2–5 (357–376, 417–450) | **Yes — directly.** Teams tied with no H2H yet → Step 1 = 0-0 → falls through |
| No-opponent cases (189, 203) | **Yes.** More games remaining → more teams without completed H2H games |
| Constrained elimination atoms (847–854) | **Likely yes.** More games remaining → margin-sensitive elimination more common |
| MarginCondition intersection in combined atoms (109–114) | **Maybe.** More complex atom structures increase likelihood |
| Tied/drawn game results | **No.** Requires a drawn game regardless of timing |
| Weighted odds rendering | **No.** Blocked on Priority 5 |
| Home game rendering | **No.** Separate feature |
| Margin condition rendering edge cases | **No.** Requires synthetic conditions |
| Defensive fallbacks | **No.** By design, these don't fire naturally |

---

## Not unit-testable (by design)

| Module / path | Reason |
|---|---|
| `data_helpers.py` scraping functions | Require live HTTP responses |
| `data_helpers.py` DB fetch path | Requires live PostgreSQL connection |
| `prefect/` pipeline files | Require Prefect runtime + live DB; excluded from coverage config |
| `scripts/simulate_region_finish.py` DB fetch + `main` | Require live DB + CLI invocation |

---

## Tiebreaker step coverage summary

| Tiebreaker step | Covered? | Notes |
|---|---|---|
| Step 1 — H2H record | ✅ | Multiple 2- and 3-team ties across all test regions |
| Step 2 — vs highest-ranked outside | ✅ | Used in several outcome branches |
| Step 3 — H2H capped PD | ✅ | GE threshold branches confirm this fires |
| Step 4 — capped PD vs outside | ✅ | Used in some branches |
| Step 5 — fewest PA (all region games) | ✅ | PA accumulation from `standings_from_mask` tested |
| Step 6 — coin flip | ❌ | No pair remains tied through all five steps in any test region |
| Pair Steps 2–5 restart | ❌ | All pairs resolved at Step 1 (they've played each other) |
| Tied/drawn game (`res_a = 0`) | ❌ | No drawn games in 2025 data |
| No H2H game between tied teams | ❌ | All test regions are complete round-robins at final week |
| Margin-sensitive GE thresholds | ✅ | Region 1-6A, 4-3A, 2-1A, 2-7A scenario output tests |
| `clinched` / `eliminated` detection | ✅ | Multiple regions exercise both flags |
| `sensitive_boundary_games` detection | ✅ | Verified via Region 1-6A GRE bug fix |
