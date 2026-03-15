# Test Coverage Gaps

## Current state (2026-03-14)

| Module | Coverage | Trend |
|---|---|---|
| `scenarios.py` | 94% | ↑ from 11% (added pure helper + consolidation unit tests) |
| `tiebreakers.py` | 76% | ↑ from 59% (ground truth tests across all 44 regions) |
| `data_helpers.py` | 43% | Flat — uncovered lines are scraping/DB fetch paths, not unit-testable |
| `data_classes.py` | 70% | Flat — uncovered dataclass methods not exercised by current test paths |
| **Total** | **82%** | ↑ from ~32% |

---

## What's covered

### Ground truth tests (`ground_truth_2025_test.py`)
All 44 MHSAA regions × classes for the complete 2025 season are parametrized and passing.
Covers the full `determine_scenarios` → `determine_odds` pipeline with zero remaining games.

### Pure helper unit tests (`scenarios_helpers_test.py`)
Added in groups 1, 2, and 4 to cover:
- `pct_str()` — round and non-round percentage formatting
- `_parse_ge_key()` — valid key, missing `_GE`, non-integer threshold
- `_flip_base_key()` — matchup key with and without `>`
- `final_consolidation()` — contradictory key removal and deduplication
- `consolidate_all(debug=True)` — debug print branches
- `merge_full_partition_remove_base()` — overlapping/non-overlapping interval merging, contradictory GE bounds, base_true/false tracking
- `merge_ge_union_unified()` — adjacent-interval collapse, finite range collapse, skip conditions
- `merge_ge_union_by_signature()` — aggressive_upper paths, contradictory bounds skip, explicit-key skip
- `compute_bracket_odds()` — 4-round and 5-round brackets, all probability fields
- `compute_first_round_home_odds()` — all home-seed combinations

---

## Remaining gaps

### Group 3 — Margin-sensitive tiebreaker path (`scenarios.py` lines 766–996)

**What it is:** When `determine_scenarios` is called with remaining games AND tied teams
exist, the algorithm probes each possible margin (1–12) for intra-bucket games to detect
GE thresholds. This produces the margin-keyed scenario minterms (`"A>B_GE3": True`, etc.)
that the consolidation helpers then simplify.

**Why not covered:** The ground truth tests all pass `remaining=[]` (full season data),
so `intra_bucket_games` is always empty and the margin probe loop never runs.

**Tests needed:**
- A mid-season fixture for a region where 2+ teams are tied in W/L record with at least
  one game remaining between them — so `tie_bucket_groups()` returns a non-empty bucket
  and `unique_intra_bucket_games()` returns games.
- A case where margin doesn't change standings (no threshold) and one where it does
  (produces GE keys).
- A case where `interval_specs` is empty even with intra-bucket games (all thresholds empty).

---

### `tiebreakers.py` — specific step paths

#### Step 6 — Fewest PA across all region games
**Why not covered:** PD (Steps 3 or 5) always breaks ties before Step 6 in 2025 data.
**Test needed:** Two teams with identical H2H, outside record, capped PD, and PA vs outside
so that total points allowed is the deciding factor.

#### Step 7 — Coin flip
**Why not covered:** No pair of teams remains perfectly tied through all six steps in any
2025 region.
**Test needed:** A 2-team region where every numeric tiebreaker is equal, so `coin_flip_collector`
is populated and `coin_flip_needed` would be set.

#### Step 3 restart after team elimination (3+ way tie)
**What it is:** SCENARIO_RULES.md rule 3b/3b-i — when one team is eliminated from a
3-way bucket at Step 3 and the remaining two have identical capped PD, tiebreaking
**restarts at Step 1** for just those two.
**Test needed:** A 3-team tie where Team A breaks away at Step 3, leaving B and C with
identical capped PD forcing a restart.

#### Tie games (`res_a = 0`)
**Why not covered:** All 2025 region games had decisive W/L outcomes.
**Test needed:** At least one tied game in a fixture to verify 0.5 H2H point accumulation
and the `T` column in W/L standings.

#### Incomplete schedule (teams that never played each other)
**Why not covered:** Region 3-7A is a complete round-robin.
**Test needed:** A region where at least one pair has no H2H game, confirming those pairs
are excluded from Steps 1 and 3 but included in Steps 2, 4, and 5.

#### 5- or 6-way tie
**Why not covered:** All 2025 regions had at least some W/L separation.
**Test needed:** A region with all games remaining or a fully circular result set to exercise
`resolve_bucket()` with the full team list from the very first step.

---

## Not unit-testable (by design)

| Module / path | Reason |
|---|---|
| `data_helpers.py` scraping functions | Require live HTTP responses or BeautifulSoup fixtures |
| `data_helpers.py` DB fetch path (`get_completed_games` DB branch) | Requires a live PostgreSQL connection |
| Prefect pipeline files (`region_scenarios_pipeline.py`, etc.) | Require Prefect runtime + live DB; excluded from coverage config |

---

## Tiebreaker step coverage summary

| Tiebreaker step | Covered? | Notes |
|---|---|---|
| Step 1 — H2H record | ✅ | Multiple 2- and 3-team ties resolved here across 44 regions |
| Step 2 — vs highest-ranked outside | ✅ | Used in several outcome branches |
| Step 3 — H2H capped PD | ✅ | GE threshold branches confirm this fires |
| Step 4 — capped PD vs outside | ✅ | Used in some branches |
| Step 5 — fewest PA vs outside | ✅ | PA accumulation from `standings_from_mask` tested |
| Step 6 — fewest PA all games | ❌ | See gap above |
| Step 7 — coin flip | ❌ | See gap above |
| Margin-sensitive GE branches | ✅ | Unit tests directly exercise consolidation helpers |
| Zero remaining games path | ✅ | All 44 ground truth tests |
| Non-zero remaining games path | ❌ | Group 3 gap — needs mid-season synthetic fixture |
| `clinched` / `eliminated` detection | ✅ | Multiple regions exercise both flags |
| Step 3 restart after 3-way tie elimination | ❌ | See gap above |
| Tie game (`res_a = 0`) | ❌ | See gap above |
| Incomplete schedule (missing H2H pair) | ❌ | See gap above |
