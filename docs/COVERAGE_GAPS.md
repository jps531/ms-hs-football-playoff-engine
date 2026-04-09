# Test Coverage Gaps

## Current state (2026-04-08)

| Module | Coverage | Notes |
|---|---|---|
| `data_classes.py` | **100%** | |
| `data_helpers.py` | **100%** | |
| `scenarios.py` | **100%** | |
| `scenario_serializers.py` | **100%** | |
| `scenario_renderer.py` | **91%** | Home game rendering + weighted odds untested |
| `scenario_viewer.py` | **92%** | Dropped from 95% — outer stability loop + Rule 4 added new uncovered paths |
| `tiebreakers.py` | **86%** | Pair tiebreaker Steps 2–5 still the dominant gap |
| `home_game_scenarios.py` | **96%** | Minor edge cases |
| `bracket_home_odds.py` | **86%** | Some class-size branches |
| **Total** | **93%** | 2559 tests passing |

Test files: 24 scenario output tests (including 1 midseason fixture for Region 4-4A).

---

## What changed since 2026-03-25

### Added
- **Generalized Rule 4** in `_simplify_atom_list`: range-containment splitting with shared lower bounds. Exercises new code paths in the outer loop's Rule 4 section.
- **Outer stability loop**: wraps all rules in `while globally_changed:` so later-rule results can re-expose earlier opportunities.

### Removed
- **Rule 5** (single-atom range narrowing): removed because multi-condition atoms with margin qualifiers were harder for coaches/fans to read than just "Team X beats Team Y."

### Net coverage effect
`scenario_viewer.py` dropped 3pp (95% → 92%) because the outer stability loop's **second-pass paths** are new uncovered code. The outer loop's first pass always fires (every call goes through it), but the `globally_changed = True` re-iteration only fires when R3 or R4 exposes a new R1/2 or subsumption opportunity — no current test creates that chain.

---

## scenario_viewer.py — gap catalogue

### NEW: Outer stability loop second pass (lines 831, 836, 840, 843–849, 850→834, 862–863, 875–880)

The outer `while globally_changed:` loop runs at least once per call. The second pass only fires when R3 or R4 produces an atom list where R1/2 can now merge more atoms, or subsumption now eliminates one. No current test creates this chain (R4 → new R1/2 opportunity, or R3 → new subsumption).

**What would cover it:** A region where Rule 4 splits one atom into two, and the two resulting pieces happen to be adjacent-range mergeable by Rule 1/2. Likely requires 3+ margin-sensitive games in play simultaneously. A 5A–7A region with 4 games remaining is the best candidate.

---

### NEW: `_derive_atom` unconstrained shortcut (lines 434–440)

When joint margin constraints alone (ignoring per-game bounds) exactly describe the valid 2D set, the per-game bounds are dropped and unconstrained `GameResult` objects are returned. No current region produces this shape.

**What would cover it:** A tiebreaker where the winning margin of game A plus game B must equal exactly N, and that sum constraint alone (with no individual game floor) describes all valid outcomes. Unusual but possible with specific H2H PD scenarios.

---

### NEW: `_try_rule3` non-overlapping guard (line 687)

`if ca_t.max_margin is not None and ca_t.max_margin <= cb_t.min_margin: continue` — guards against a spurious Rule 3 match where atom a's margin range doesn't actually overlap atom b's. Not yet triggered.

---

### Carried over: Reverse-direction splitting in `_split_non_rectangular_atom` (lines 280–284, 305→212)

The forward direction (game0-keyed grouping) is covered. The reverse direction (game1-keyed) bails at lines 280–281 or 283–284 for non-contiguous cases, or succeeds at line 305. All tested non-rectangular cases exhaust the forward direction — the reverse path is structurally reachable but not yet triggered.

---

### Carried over: `_find_combined_atom` MarginCondition intersection (lines 109–114)

Fires when two atoms for the same seeding both contain `MarginCondition` objects (requiring tightening by intersection). The `_derive_atom` unconstrained shortcut (above) would eventually produce these — still no test generates a combined atom with two MarginCondition paths to intersect.

---

### Carried over: `_find_combined_atom` no-match return (line 138)

`return None` fires when no atom in the stored list matches the sample margins for a given sub-scenario. Has never triggered — every sub-scenario always finds a matching atom. Defensive.

---

### Carried over: Constrained elimination atoms (line 1145→1140)

`sometimes_elim_only_masks` — teams eliminated only for specific margin combinations. Covered structurally (the path exists in 4-4A), but the specific branch `if absent_margins:` at line 1145 isn't confirmed hit. A mid-season region where one team is eliminated only when a specific game is lost by a large margin would nail this.

---

### Carried over: `render_scenarios_text` eliminated line (line 1345→1348)

The `if eliminated:` block in `render_scenarios_text` writes "Eliminated: X, Y" per scenario. `render_scenarios_text` is not called directly in any test — only `division_scenarios_as_dict` and `render_team_scenarios` are tested. Any test calling `render_scenarios_text` on a region with eliminated teams covers this.

**One-liner to cover it:** `render_scenarios_text(teams, completed, remaining)` on any existing 5-6 team fixture where some teams get eliminated.

---

### Carried over: `build_scenario_atoms` R=0 early exit (line 1039)

`if R == 0: return {}` — fires when no games remain. Never called with R=0. A post-season test (all games already played, cutoff = after last game) covers this trivially.

---

### Carried over: Rule 1/2 merge edge cases (lines 570, 583, 596–597, 604)

- **Line 570**: Rule 1 processes atoms where `ca.min_margin > cb.min_margin` — i.e., the atom with the higher lower bound is listed first. All tested merges happen to process atoms in ascending lower-bound order.
- **Line 583**: Rule 1 merge path when a `MarginCondition` is also present — never triggered because no atom currently has both a margin-restricted `GameResult` AND a `MarginCondition`.
- **Lines 596–597**: Rule 2 scan for `MarginCondition` references to the game being dropped — never triggered.
- **Line 604**: `return None` at end of `_try_merge` — fires when the two atoms share a game pair but neither Rule 1 nor Rule 2 applies (e.g., different winners and not complementary unconstrained). Defensive.

---

## tiebreakers.py — gap catalogue (unchanged)

### Pair tiebreaker Steps 2–5 (lines 357–376, 412–435)

`_resolve_pair_using_steps` with Step 1 returning 0–0 (teams have no H2H result yet). All current tests resolve pairs at Step 1 because the final-week fixture has every pair already having played each other. This is still the single highest-value gap.

**What would cover it:** A mid-season test where two leading teams are tied in region record and have **not yet played each other**. Step 1 scores 0–0, falling through to Step 2 (record vs common outside opponents) and beyond.

---

### No-opponent cases in step arrays (lines 186, 189, 203)

`res_vs` and `pd_vs` return `None` when a bucket team has played no game (completed or remaining) against a specific outside opponent. All current test regions are complete round-robins, so every team has at least a scheduled game against every other.

**What would cover it:** A region that doesn't play a full round-robin, OR a mid-season test early enough that some cross-divisional games haven't been scheduled yet.

---

### Tied/drawn game results (lines 49–50, 103–104, 314, 321–322)

Not season-timing related — requires a real or synthetic game ending in a draw (uncommon in high school football but legal). Would need a hand-crafted fixture.

---

## Proposed new tests — prioritized

### Priority 1: Post-season (R=0) test ⭐ **Trivially easy**

Pick any existing region fixture; set the cutoff to after the last game. `build_scenario_atoms` returns `{}` immediately (line 1039 covered), `render_team_scenarios` falls back to "Clinched #N" or "Eliminated" for every team. Also call `render_scenarios_text` to cover the eliminated rendering line (1345→1348).

**Gaps closed:** line 1039 (`build_scenario_atoms` R=0 exit), line 1345→1348 (`render_scenarios_text` eliminated block).

---

### Priority 2: Mid-season with no H2H yet between tied teams ⭐⭐ **High value**

A region at round 1–2 of the season. Two or more teams are tied in region record and their head-to-head game is still scheduled as a remaining game. Step 1 of `_resolve_pair_using_steps` returns 0–0, falling through to Steps 2–5.

Candidate regions: any 4-team 2A–4A region after round 2 (some H2H games played, others still remaining). This is exactly the "pair tiebreaker Steps 2–5" gap.

**Gaps closed:** tiebreakers.py lines 357–376, 412–435 (pair Steps 2–5). Likely also lines 186, 189 (no-opponent cases).

**Suggested fixtures from the 2025 data:** Look for regions where the cutoff is before the H2H matchup between the top two teams.

---

### Priority 3: 1 or 2 known final-week results (partial final weekend)

Set the cutoff between the semifinal and final weekend game. Some elimination results are already determined; others are pending. This exercises:
- `build_scenario_atoms` with R=1 or R=2 (smaller outcome space)
- Scenarios where some teams are already clinched/eliminated before all games finish
- The "constrained elimination atoms" path (line 1145) if a team is eliminated only for certain margins in the remaining game

**Gaps closed:** Possibly line 1145 (constrained elimination), confirms correctness at the in-season seam.

---

### Priority 4: 5A–7A region with 4 games remaining

2^4 = 16 win/loss masks, 12^4 = 20,736 margin combos per mask. Larger atom lists make it more likely that:
- Rule 4 fires AND the result is further reducible by R1/2 (outer stability loop second pass)
- The `_split_non_rectangular_atom` reverse direction (lines 280–284) is needed
- The constrained elimination path (line 1145) fires

**Gaps closed:** Likely closes outer stability loop second pass (lines 843–849, 862–863, 875–880). Also validates correctness at higher fan-out.

**Caveat:** Computationally expensive. 16 × 20,736 = ~330K evaluations. Feasible (the 4-4A midseason test at R=4 was already written and runs fine).

---

### Priority 5: 1A–4A region with 0 games played

**NOT recommended as written.** For a 5-team round-robin, R=10 games remaining → 12^10 ≈ 6 × 10^10 margin combinations per mask. Completely infeasible.

**Better alternative:** Test at round 1 (1 game played, 9 remaining) — still too expensive. Test at round 3 (3 games played, 7 remaining) — still R=7, 12^7 ≈ 35M per mask. Practically, R ≤ 4 is the safe limit.

**What to do instead:** The mid-season tests at R=3 or R=4 (Priorities 2 and 4) cover the intent of "early season with no H2H" while staying computationally tractable.

---

### Priority 6: Random score differentials for final-week games

Write a property test that picks random margins for each remaining game and verifies that the scenario engine places each team in the seed predicted by the tiebreaker logic. This is a correctness/regression test, not a coverage driver.

**Suggested approach:** For a region with known final standings, randomize margins while preserving the same winner/loser, and assert that the seeding is unchanged. Then intentionally cross a margin threshold (e.g., set margin to 11 vs 12 for a region with a threshold at 12) and assert the seeding flips correctly.

**Gaps closed:** None new, but high confidence value for margin threshold correctness.

---

### Recommended additions (not in user's list)

**`render_scenarios_text` call in an existing test:** One line addition to any existing test. Covers line 1345→1348 immediately.

**Synthetic tied-game fixture:** A hand-crafted fixture with one game ending in a draw. Covers tiebreakers.py lines 49–50, 103–104, 314, 321–322. Unlikely in real data but important for completeness.

---

## Tiebreaker step coverage summary

| Tiebreaker step | Covered? | Notes |
|---|---|---|
| Step 1 — H2H record | ✅ | Multiple 2- and 3-team ties |
| Step 2 — vs highest-ranked outside | ✅ | Used in several branches |
| Step 3 — H2H capped PD | ✅ | GE threshold branches confirm this fires |
| Step 4 — capped PD vs outside | ✅ | Used in some branches |
| Step 5 — fewest PA (all region games) | ✅ | PA accumulation tested |
| Step 6 — coin flip | ❌ | No pair tied through all five steps |
| Pair Steps 2–5 restart | ❌ | All pairs resolved at Step 1 (played each other) |
| Tied/drawn game (`res_a = 0`) | ❌ | No drawn games in any test region |
| No H2H game between tied teams | ❌ | All test regions are complete round-robins at final week |
| Margin-sensitive GE thresholds | ✅ | Multiple scenario output tests |
| `clinched` / `eliminated` detection | ✅ | Multiple regions |
| `sensitive_boundary_games` detection | ✅ | Verified via Region 1-6A GRE bug fix |

---

## Not unit-testable (by design)

| Module / path | Reason |
|---|---|
| `data_helpers.py` scraping functions | Require live HTTP responses |
| `data_helpers.py` DB fetch path | Requires live PostgreSQL connection |
| `prefect/` pipeline files | Require Prefect runtime + live DB |
| `scripts/simulate_region_finish.py` DB fetch + `main` | Require live DB + CLI invocation |
| Weighted odds rendering | Blocked on Priority 5 (fields not yet computed) |
| Home game rendering | Separate feature area, no tests yet |
