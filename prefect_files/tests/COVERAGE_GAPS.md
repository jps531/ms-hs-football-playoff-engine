# Test Coverage Gaps — Tiebreaker Paths Needing Synthetic Data

The Region 3-7A 2025 season data covers the happy path well but does not exercise
every branch of the 7-step MHSAA tiebreaker. The following scenarios require
synthetic (made-up) game data to test exhaustively.

## Uncovered paths

### Step 7 — Coin flip
**What it is:** When two teams are still exactly tied after all 6 prior steps, a coin
flip decides. The algorithm sets a `coin_flip_needed` flag via `coin_flip_collector`
inside `resolve_bucket()`.
**Why not covered:** No pair of teams in 3-7A remains perfectly tied through all six
steps in any of the 8 W/L outcome combinations.
**Test needed:** Construct a 2-team region where H2H record, PD, PA vs outside, and
fewest PA are all identical so the coin flip branch is reached and flagged.

---

### Step 3 restart after team elimination (3+ way tie)
**What it is:** SCENARIO_RULES.md rule 3b/3b-i — when more than two teams are tied and
one team is eliminated from the bucket, if the remaining two teams still have identical
PD the tiebreaker **restarts at Step 1** for just those two. The `_resolve_pair_using_steps()`
function in `tiebreakers.py` handles this.
**Why not covered:** In all 3-7A tie buckets, at least one team breaks away cleanly at
Step 3 without creating a two-team restart situation.
**Test needed:** A 3-team tie where Team A is eliminated at Step 3, leaving B and C with
identical capped PD, forcing restart to Step 1 (H2H between B and C only).

---

### Tie games (T result, `res_a = 0`)
**What it is:** A game ending in a draw contributes 0.5 points to H2H (Step 1) and 0 to
W/L record. The `res_a = 0` path exists in `get_completed_games()` and `standings_from_mask()`.
**Why not covered:** All Region 3-7A games had decisive W/L outcomes.
**Test needed:** At least one game in the fixture set should be a tie, verifying the 0.5
H2H point accumulation and the T column in W/L standings.

---

### Step 6 — Fewest PA as deciding factor
**What it is:** After H2H record (1), vs-outside record (2), capped H2H PD (3), capped PD
vs outside (4), and PA vs outside (5) — fewest total points allowed across all region games
is the final numeric tiebreaker before the coin flip.
**Why not covered:** PD (Step 3 or 5) always breaks ties before reaching Step 6 in 3-7A data.
**Test needed:** A scenario where Steps 1–5 are all equal between two teams so Step 6 PA
difference is the deciding factor.

---

### Incomplete schedule (teams that didn't play each other)
**What it is:** In some classes/regions, not every team plays every other team during the
regular season (unbalanced schedule). The H2H maps skip pairs that never played.
**Why not covered:** All 6 teams in Region 3-7A played all 5 region opponents (complete
round-robin).
**Test needed:** A 4- or 5-team region where at least one pair has no H2H game, confirming
those pairs are excluded from Steps 1 and 3 but included in Steps 2, 4, and 5.

---

### 5- or 6-way tie at start of tiebreaker
**What it is:** When every team in the region has the same W/L record (e.g., 0-0 at the
start of the season, or a circular-result schedule), `resolve_bucket()` is called with the
full team list.
**Why not covered:** Region 3-7A always has at least 2 teams separating by W/L record.
**Test needed:** A region with all games remaining (0 completed) or a fully circular
result set to exercise the multi-team bucket path from the very first step.

---

## Already covered by Region 3-7A data

| Tiebreaker step | Covered? | Notes |
|---|---|---|
| Step 1 — H2H record | ✅ | Multiple 2- and 3-team ties resolved here |
| Step 2 — vs highest-ranked outside | ✅ | Used in several outcome branches |
| Step 3 — H2H capped PD | ✅ | GE threshold branches confirm this fires |
| Step 4 — capped PD vs outside | ✅ | Used in some branches |
| Step 5 — fewest PA vs outside | ✅ | PA accumulation from `standings_from_mask` tested |
| Step 6 — fewest PA all games | ❌ | See gap above |
| Step 7 — coin flip | ❌ | See gap above |
| Margin-sensitive GE branches | ✅ | Multiple GE keys (GE3, GE4, GE6, GE9, GE10) appear |
| Zero remaining games path | ✅ | Full-season test |
| 3 remaining games path | ✅ | Pre-final-week test |
| `clinched` / `eliminated` detection | ✅ | Meridian and Pearl eliminated; Oak Grove and Petal clinched |
