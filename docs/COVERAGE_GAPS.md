# Test Coverage Gaps

## Current state (2026-04-22)

| Module | Coverage | Notes |
|---|---|---|
| `data_classes.py` | **100%** | |
| `data_helpers.py` | **100%** | |
| `scenarios.py` | **100%** | |
| `scenario_serializers.py` | **100%** | |
| `tiebreakers.py` | **100%** | |
| `home_game_scenarios.py` | **100%** | |
| `bracket_home_odds.py` | **100%** | |
| `scenario_renderer.py` | **100%** | |
| `scenario_viewer.py` | **99%** | Structurally unreachable guards only |
| `data_helpers.py` (game status) | **100%** | `normalize_game_status`, `parse_game_clock`, `game_seconds_remaining` |
| `win_probability.py` (in-game) | **100%** | `compute_in_game_win_prob`, `compute_ot_win_prob`, `_ot_score_distribution` |
| **Total** | **99%** | 3339 tests passing |

Test files: 37 test files.

---

## Not unit-testable (by design)

| Module / path | Reason |
|---|---|
| `data_helpers.py` scraping functions | Require live HTTP responses |
| `data_helpers.py` DB fetch path | Requires live PostgreSQL connection |
| `prefect/` pipeline files | Require Prefect runtime + live DB |
| `scripts/simulate_region_finish.py` DB fetch + `main` | Require live DB + CLI invocation |
| `_derive_atom` branch 528→535 — False path of `if non_rectangular:` to fallback return | When `non_rectangular=False` the valid set is rectangular, so all sum/diff extremes are achieved → no binding constraints → `margin_conds=[]` → early-exit at line 496 fires first; structurally unreachable |
| `_try_merge` line 690 — final `return None` after both rule blocks | For any well-formed two-team game pair, either Rule 1 (same winner) or Rule 2 (opposite winners) always matches; structurally unreachable |
| `_subsumes` line 704 — `return True` when atom is empty | Empty atoms trigger the early-exit `return [[]]` before subsumption is reached; structurally unreachable |
| `build_scenario_atoms` Step 4 line 1663 — `if not uncovered_positions: continue` | Sensitive masks always have at least one uncovered seed position by construction; structurally unreachable |
| Step 5 `absent_margins` False branch (line 1716→1711) | `sometimes_elim_only_masks` always produces groups with non-empty margin lists; False branch structurally unreachable |
| `_simplify_atom_list` outer-loop R1/2 empty-atom guard (line 912) | Rule 2 producing `[]` from two fully-unconstrained opposite-winner atoms is handled by the pre-loop at line 768; atoms reaching the outer loop must have 2+ differences, preventing R1/2 from firing; outer-loop rules R3, R4, and subsumption never produce empty atoms; structurally unreachable |
| `_find_tiebreaker_groups` lines 1261 and 1264→1266 — `break` when j ≥ n and False path of convergence check | Any two orderings of the same team set where positions differ must form at least one convergent group by the pigeonhole principle; the cross-boundary fallback is structurally unreachable with valid inputs |
| `enumerate_outcomes` line 1346→1318 — `if tg:` False path | `_find_tiebreaker_groups` is only called when `order_lo != order`; two distinct orderings of the same team set always produce at least one convergent group, so `tg` is always non-empty here; structurally unreachable |
| `build_scenario_atoms` line 1831 — "already processed this mask" duplicate-mask guard | `mask_seeding_margins` is a dict keyed by `(mask, seeding)` tuples; non-sensitive masks produce exactly one seeding for all margins, so each mask value appears at most once in that dict under the guard's prerequisite condition; structurally unreachable |
| `build_pre_playoff_home_scenarios` line 2219 — `continue` when `slot_index_for` returns `None` | `achievable_seeds` is derived from `range(1, playoff_seeds+1)` filtered by non-zero probability; all seeds 1–4 appear in the bracket half-slots for any valid region; structurally unreachable |
| `parse_game_clock` line 523→527 — `if ot_m:` False branch inside `IN_PROGRESS` block | `normalize_game_status` only returns `IN_PROGRESS` when `_REG_CLOCK_RE` or `_OT_PROGRESS_RE` matched; `parse_game_clock` re-runs the same regexes on the same string, so `ot_m` is always non-None here; structurally unreachable |
| `parse_game_clock` line 529→533 — `if ot_m:` False branch inside `END_OT` block | `normalize_game_status` only returns `END_OT` when `_OT_END_RE` matched; the re-match in `parse_game_clock` always succeeds; structurally unreachable |
