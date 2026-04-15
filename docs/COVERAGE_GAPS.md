# Test Coverage Gaps

## Current state (2026-04-15)

| Module | Coverage | Notes |
|---|---|---|
| `data_classes.py` | **100%** | |
| `data_helpers.py` | **100%** | |
| `scenarios.py` | **100%** | |
| `scenario_serializers.py` | **100%** | |
| `tiebreakers.py` | **100%** | |
| `scenario_renderer.py` | **98%** | Weighted odds rendering untested (blocked on feature) |
| `scenario_viewer.py` | **99%** | Structurally unreachable guards only |
| `home_game_scenarios.py` | **100%** | |
| `bracket_home_odds.py` | **100%** | |
| **Total** | **99%** | 2803 tests passing |

Test files: 34 test files including synthetic coin-flip fixture, outer-stability-loop second-pass fixtures, and full-season R=0 tests.

---

## scenario_renderer.py — gap catalogue

### Weighted odds rendering (lines 141, 143, 414, 416)

- **Lines 141, 143**: Both-unweighted-and-weighted and weighted-only paths in `render_team_scenarios._odds_suffix`.
- **Lines 414, 416**: Both-odds and weighted-only paths in the standalone `_odds_pct` helper used by the home-game renderers.

Blocked on the weighted odds computation feature. `weighted_odds` is never passed in any current test.

---

## Not unit-testable (by design)

| Module / path | Reason |
|---|---|
| `data_helpers.py` scraping functions | Require live HTTP responses |
| `data_helpers.py` DB fetch path | Requires live PostgreSQL connection |
| `prefect/` pipeline files | Require Prefect runtime + live DB |
| `scripts/simulate_region_finish.py` DB fetch + `main` | Require live DB + CLI invocation |
| Weighted odds rendering (lines 141, 143, 414, 416) | `weighted_odds` computation not yet implemented |
| `_derive_atom` branch 519→526 — False path of `if non_rectangular:` to fallback return | When `non_rectangular=False` the valid set is rectangular, so all sum/diff extremes are achieved → no binding constraints → `margin_conds=[]` → early-exit at line 496 fires first; structurally unreachable |
| `_try_merge` line 670 — final `return None` after both rule blocks | For any well-formed two-team game pair, either Rule 1 (same winner) or Rule 2 (opposite winners) always matches; structurally unreachable |
| `_subsumes` line 684 — `return True` when atom is empty | Empty atoms trigger the early-exit `return [[]]` before subsumption is reached; structurally unreachable |
| `build_scenario_atoms` Step 4 line 1386 — `if not uncovered_positions: continue` | Sensitive masks always have at least one uncovered seed position by construction; structurally unreachable |
| Step 5 `absent_margins` False branch (line 1437→1432) | `sometimes_elim_only_masks` always produces groups with non-empty margin lists; False branch structurally unreachable |
| `enumerate_division_scenarios` duplicate-mask guard (line 1538) | Non-sensitive masks have exactly one seeding — structurally unreachable |
| `_simplify_atom_list` outer-loop R1/2 empty-atom guard (line 892) | Rule 2 producing `[]` from two fully-unconstrained opposite-winner atoms is handled by the pre-loop at line 768; atoms reaching the outer loop must have 2+ differences, preventing R1/2 from firing; outer-loop rules R3, R4, and subsumption never produce empty atoms; structurally unreachable |
