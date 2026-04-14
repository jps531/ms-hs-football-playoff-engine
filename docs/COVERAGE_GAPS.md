# Test Coverage Gaps

## Current state (2026-04-13)

| Module | Coverage | Notes |
|---|---|---|
| `data_classes.py` | **100%** | |
| `data_helpers.py` | **100%** | |
| `scenarios.py` | **100%** | |
| `scenario_serializers.py` | **100%** | |
| `tiebreakers.py` | **100%** | |
| `scenario_renderer.py` | **91%** | Weighted odds + home-game renderers untested |
| `scenario_viewer.py` | **96%** | Outer stability loop second pass + several edge cases |
| `home_game_scenarios.py` | **100%** | |
| `bracket_home_odds.py` | **100%** | |
| **Total** | **98%** | 2760 tests passing |

Test files: 31 test files including synthetic coin-flip fixture, precomputed-path coverage, and full-season R=0 tests.

---

## scenario_viewer.py — gap catalogue

### Rule 1/2 merge edge cases (lines 526, 651, 665, 670, 684)

- **Line 526**: Rule 1 processes atoms where `ca.min_margin > cb.min_margin` (reverse lower-bound order). All tested merges process atoms in ascending order.
- **Line 651**: Rule 1 merge path when a `MarginCondition` is also present — not yet triggered.
- **Lines 665, 670**: Rule 2 scan for `MarginCondition` references to the game being dropped — not yet triggered.
- **Line 684**: `return None` at end of `_try_merge` — defensive; fires when neither R1 nor R2 applies.

---

### `_try_rule3` — non-overlapping guard (line 753)

`if ca_t.max_margin is not None and ca_t.max_margin <= cb_t.min_margin: continue` — guards against a spurious Rule 3 match where atom a's range doesn't overlap atom b's range. Not yet triggered.

---

### `_try_rule4` — structural rejects (lines 859, 864)

Inside Rule 4 (range-containment splitting):
- **Line 859**: `if ca_t.min_margin != cb_t.min_margin: continue` — lower bounds must match; atoms with differing lower bounds are not Rule-4 candidates.
- **Line 864**: `if cb_t.max_margin is not None and ca_t.max_margin >= cb_t.max_margin: continue` — a's range must be strictly narrower than b's; equal or wider ranges are rejected.

These guards fire when the candidate pair (p_comp, p_tight) assignment fails the Rule 4 preconditions and the loop tries the reversed assignment. Not yet triggered in tested regions.

---

### Constrained elimination atoms — `absent_margins` False branch (line 1437→1432)

In Step 5, `sometimes_elim_only_masks` collects masks where a team is eliminated only for specific margin ranges. The inner `if absent_margins:` guard is structurally present but the False branch (no margin-specific conditions found) has not been triggered.

---

### Outer stability loop — second pass (lines 892, 897, 901, 904–910, 911→895, 920–921, 933–936, 938)

The outer `while globally_changed:` loop runs at least once. A second pass fires only when Rule 3 or Rule 4 produces an atom list where Rule 1/2 can now merge additional atoms, or subsumption can now eliminate one. No tested region creates this chain.

**What would cover it:** A region where Rule 4 splits an atom into two pieces that are adjacent-range-mergeable by Rule 1/2. Likely requires 3+ margin-sensitive games simultaneously (5A–7A with 4 games remaining is the best candidate).

---

### `build_scenario_atoms` Step 4 — all-covered `continue` (line 1386)

`if not uncovered_positions: continue` — fires when all seed positions in a mask's full seeding are already accounted for by always-at-seed masks and no per-game-range atoms are needed. In all tested regions there is always at least one uncovered position remaining.

---

### Coin flip under margin-sensitive mask (lines 1132, 1299, 1528)

`if flip_collector and mask not in coin_flips:` inside the full-enumeration loop — fires when a coin flip arises under a margin-sensitive mask (i.e. the same mask produces different orderings for different margins, but one of those orderings ends in a coin flip). This appears in `enumerate_outcomes` (line 1132), `build_scenario_atoms` (line 1299), and `enumerate_division_scenarios` (line 1528). No natural or synthetic fixture produces this combination.

---

### `enumerate_division_scenarios` — duplicate-mask guard (line 1538)

`continue` inside the coin-flip metadata loop when a non-sensitive mask has already been processed. A non-sensitive mask has exactly one seeding, so this guard is structurally unreachable for coin-flip masks (which are always non-sensitive in practice). Not unit-testable by design.

---

### `enumerate_division_scenarios` — margin-sensitive without `scenario_atoms` (line 1640→1649)

The `if scenario_atoms:` False branch inside the margin-sensitive scenario path. Fires when `enumerate_division_scenarios` is called without a pre-built atoms dict and has margin-sensitive scenarios to emit — in this case `conditions_atom` is left as `None`. Not yet covered by the current test suite.

---

## scenario_renderer.py — gap catalogue

### `_winner_label` — non-GameResult loop iteration (line 32→31)

The `isinstance(cond, GameResult)` False branch fires when a non-GameResult condition (e.g. `MarginCondition`) appears in the atom iteration before the matching `GameResult` is found. Since atoms are constructed with `GameResult` conditions first, the matching result is always found before non-`GameResult` conditions are reached, so this branch never triggers.

---

### `_render_margin_condition` — edge cases (lines 67, 74, 78–80)

- **Line 67**: `cond.op == "=="` with two add operands — combined total equals exactly N. No tested atom produces this shape.
- **Line 74**: `t == 0` in the 1-add/1-sub case — the two winning margins are equal. No tested atom produces this condition.
- **Lines 78–80**: General fallback for patterns with more than 2 operands (more than one add+sub term). Not produced by the current atom-building logic.

---

### `_render_condition` — unknown type fallback (line 91)

`return str(cond)` fires when the condition is none of `GameResult`, `MarginCondition`, or `CoinFlipResult`. Defensive; never triggered in practice.

---

### Weighted odds rendering (lines 141, 143)

- **Line 141**: Both unweighted and weighted odds provided — renders `"(XX.X% – XX.X% Weighted)"`.
- **Line 143**: Only weighted odds provided — renders `"(XX.X% Weighted)"`.

The `weighted_odds` parameter of `render_team_scenarios` is never passed in any current test; blocked on the weighted odds computation feature.

---

### Home-game renderer (lines 347–348, 384–385, 414, 416, 463, 479, 542, 633→635)

The home-game rendering family (`render_team_home_scenarios`, `team_home_scenarios_as_dict`, `render_team_matchups`, `team_matchups_as_dict`) has no tests. Specific uncovered paths:

- **Lines 347–348**: `kind == "seed_required"` branch in `_render_condition_label` — renders a team's finishing seed rather than an advancement condition.
- **Lines 384–385**: Unconditional host with an explanation note in `render_team_home_scenarios`.
- **Lines 414, 416**: Both-odds and weighted-only paths in `_odds_pct`.
- **Lines 463, 479**: Unconditional host/not-host with explanation in `render_team_home_scenarios`.
- **Line 542**: `elif label is None: label = f"Region..."` fallback in `team_home_scenarios_as_dict._cond_dict`.
- **Lines 633→635**: `entry.explanation` True branch in `render_team_matchups` — no tested matchup entry carries an explanation string.

---

## Proposed new tests — prioritized

### Priority 1: 5A–7A region with 4 games remaining ⭐⭐⭐ **High effort, high reward**

2^4 = 16 masks × 12^4 = 20,736 margin combos. Larger atom lists make it more likely that Rule 4 fires AND the result is further reducible by Rule 1/2 (outer stability loop second pass). Also the most likely trigger for `_try_rule4` lower-bound guards.

**Caveat:** Computationally expensive but tractable (the 4-4A midseason test at R=4 already runs fine).

---

## Not unit-testable (by design)

| Module / path | Reason |
|---|---|
| `data_helpers.py` scraping functions | Require live HTTP responses |
| `data_helpers.py` DB fetch path | Requires live PostgreSQL connection |
| `prefect/` pipeline files | Require Prefect runtime + live DB |
| `scripts/simulate_region_finish.py` DB fetch + `main` | Require live DB + CLI invocation |
| Weighted odds rendering (lines 141, 143) | `weighted_odds` computation not yet implemented |
| `enumerate_division_scenarios` duplicate-mask guard (line 1538) | Non-sensitive masks have exactly one seeding — structurally unreachable |
