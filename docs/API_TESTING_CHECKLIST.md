# API Testing Checklist — Post Season Backfill

Use these checks in the Swagger UI after seeding a full season to verify data integrity and algorithm correctness.

---

## Standings (`GET /api/v1/standings/{clazz}/{region}`)

**1. Final-week odds should be 0.0 or 1.0 for all teams** ✅
Pick any class/region after the final regular-season date — every team should be either `clinched: true` or `eliminated: true`, and all four odds fields should be exactly `0.0` or `1.0`. If you see fractional odds at the final date, the pipeline didn't finish running.

**2. Odds sum to ≤ 1.0 per position** ✅
The sum of `odds_1st` across all teams should be ≤ 1.0 (exactly 1.0 when no team is eliminated yet, possibly less once some are). Same for 2nd/3rd/4th.

**3. Time-travel consistency with `?date=`** ✅
Hit the same region with `?date=YYYY-10-10` (mid-season), `?date=YYYY-10-24` (late season), and no date. Odds should move from fractional → sparser → binary. If mid-season returns the same binary result as end-of-season, the snapshot lookup is broken.

**4. `scenarios_available` flips at the right threshold** ✅
Early in the season (e.g. `?date=YYYY-09-12`), `scenarios_available` should be `false` (too many remaining games). Around the final 2 weeks it should flip to `true` with an actual `scenarios` list populated with `game_winners`, `tiebreaker_groups`, `coinflip_groups`, and `outcomes`.

**4a. Weighted seeding odds are present and plausible** ✅
Each team in `teams[].odds` should have `p1_weighted`, `p2_weighted`, `p3_weighted`, `p4_weighted`, and `p_playoffs_weighted` alongside the unweighted values. The weighted odds will differ from unweighted when margin-sensitive computation has run (they should be close but not identical). All weighted odds should sum to ≤ 1.0 across teams per position.

**4b. Bracket advancement odds are populated** ✅
Each team in `teams[].bracket_odds` should have `second_round` through `champion` (unweighted and weighted). For a clinched 1-seed, `second_round` should be ≥ 0.9. For an eliminated team, all bracket odds should be `0.0`.

**4c. Home game odds are populated** ✅
Each team in `teams[].home_game_odds` should have `first_round` through `semifinals` (unweighted and weighted). The 1-seed's `first_round` should be `1.0` once clinched.

**4d. `computation_state` reflects pipeline status** ✅
The response should include a `computation_state` object with `margin_sensitive` (boolean) and `margin_compute_status` (string: `not_needed`, `pending`, `running`, `complete`, or `skipped`). When `margin_sensitive` is `false` and `margin_compute_status` is `pending`, the UI should indicate that odds are being refined.

---

## Games (`GET /api/v1/games`)

**5. Game count sanity** ✅
`GET /api/v1/games?season=YYYY&class=7&region=3` — count the returned games. A typical 7-team region plays 6 games each, so ~21 unique matchups total. Fewer than expected means some scraping missed a week.

**6. No duplicate games** ✅
Each game should appear exactly once. If you see the same matchup twice on the same date, the dedup logic has a bug.

**7. All completed games have `status = "Final"` and `final: true`** ✅
After backfill, every game from before the season's end should have `final: true` and `status: "Final"`. Spot-check a known Week 1 game — score, status, and `final` should all be populated. Playoff games should have a non-null `round` (e.g. `"first_round"`, `"quarterfinals"`). Regular-season games should have `round: null`. Check that `overtime` is `0` for non-OT games and `> 0` for overtime results.

---

## Bracket (`GET /api/v1/bracket?season=YYYY&class=5`)

**8. Clinched slots show the correct school** ✅
The `school` field on each bracket entry should match the actual seeding outcome from that season. Compare a few known seeds against actual MHSAA results — this is the highest-confidence sanity check.

**9. Non-clinched slots have `school: null` early in the season** ✅
Query with `?date=YYYY-10-01` — most slots should have `school: null` and fractional odds. If every slot shows a school name even on that early date, `clinched` flags were written too aggressively.

**9a. Weighted advancement odds are present and differ from unweighted** ✅
Each entry should have `second_round_weighted` through `champion_weighted` populated (not `null`) for a season with Elo ratings. For a clinched strong 1-seed, `second_round_weighted` should be higher than `second_round`.

**9b. Hosting odds are present on every entry** ✅
Each entry should have a non-null `hosting` object with `first_round`, `second_round`, `quarterfinals`, `semifinals` — each with `conditional` and `marginal` fields. For a 5A–7A class, `hosting.second_round.conditional` and `.marginal` should both be `null`. For a 1A–4A class, `hosting.second_round` should be fully populated.

**9c. Seed-1 first_round hosting conditional is always 1.0** ✅
For every region, the seed-1 slot's `hosting.first_round.conditional` should be exactly `1.0` — seed-1 is always the home team in round 1 by bracket definition.

**9d. Weighted hosting fields are `null` for a season with no Elo data** ✅
Query the bracket for an older season that has no Elo ratings (e.g. `?season=2010`). All `*_weighted` fields — both advancement and hosting — should be `null`.

**9e. Simulate with winner/loser school names returns updated odds**
`POST /api/v1/bracket/simulate?season=YYYY&class=5` with body `{"results": [{"winner": "Team A", "loser": "Team B"}]}`. The losing team's slot should show `0.0` for all future-round advancement odds. The winning team's advancement odds should reflect one confirmed win. Non-weighted forward odds should approximate 50/50 geometric series.

**9f. Simulate with slot refs before clinching returns a valid response (not 404)**
Run `POST /api/v1/bracket/simulate?season=YYYY&class=5&date=YYYY-10-01` (before any seedings are locked) with body `{"results": [{"winner": {"region": 1, "seed": 1}, "loser": {"region": 2, "seed": 4}}]}`. The response should be 200 with R1S1's `second_round` odds boosted. Previously this returned 404 — it no longer does.

**9g. Old plain-string format still accepted (backward compat)**
`POST /api/v1/bracket/simulate` with `{"results": [{"winner": "Team A", "loser": "Team B"}]}` (strings, not objects) should return 200 and behave identically to `{"winner": {"school": "Team A"}, "loser": {"school": "Team B"}}`.

**9h. Mixed school-name and slot-ref in the same request works**
`POST /api/v1/bracket/simulate` (playoff mode) with `{"results": [{"winner": "School A", "loser": {"region": 2, "seed": 4}}]}`. The slot-ref loser's slot should show `0.0` advancement odds.

---

## Ratings (`GET /api/v1/ratings?season=YYYY`)

**10. Elo ordering makes intuitive sense** ✅
The highest-Elo teams per class should roughly match the teams that went deepest in the playoffs. If the #1 Elo team in 6A is a team that missed the playoffs, the cross-season carryover or K-factor is misconfigured.

**11. Every active team has a rating** ✅
`GET /api/v1/ratings?season=YYYY&class=7` — the count should match the number of 7A schools. A team missing a rating usually means they had no games scraped.

**11a. Ratings include freshness metadata** ✅
Each rating entry should include `as_of_date` (the pipeline run date), `games_played` (number of games contributing to the Elo/RPI), and `computed_at` (timestamp). If `games_played` is `0` for a team with known results, the pipeline didn't associate those games with ratings.

---

## Hosting (`GET /api/v1/hosting/{clazz}/{region}`)

**12. 1-seeds always have the highest hosting odds** ✅
For any completed region, the 1-seed's round-1 hosting odds should be `1.0` (they always host). If a lower seed shows higher odds than the 1-seed, there's a bracket-slot mapping bug.

**12a. Eliminated playoff teams show correct historical hosting facts** ✅
For a team eliminated mid-bracket (e.g. lost in QF), their hosting odds for rounds they *played* should reflect the actual result (0 or 1), not all-zeros. Example: Leake County (1A region 5) on `?date=2025-11-21` — first_round and quarterfinals conditional should be `1`, second_round conditional should be `0`, semifinals should be `null`.

---

## Simulate (`POST /api/v1/standings/{clazz}/{region}/simulate`)

**13. Simulating all remaining games produces binary odds** ✅
Take a mid-season snapshot (`?date=` week before the final week) and POST a `simulate` body filling in all remaining region games. Every team's odds should collapse to `0.0` or `1.0`. If they stay fractional, `apply_region_game_results` isn't draining the remaining game list correctly.

---

## Admin (`/api/v1/admin`)

**14. `GET /locations` returns all venues**
The response should include M.M. Roberts Stadium (the usual championship site). If it's missing, the `locations` table wasn't seeded during init.

**15. `POST /playoff-format?dry_run=true` reports the right counts**
POST a known season's format (e.g. 2025) in dry-run mode. The response should show the exact number of classes and slots you expect from the YAML config — without writing anything. Then POST without `dry_run` and re-run with `dry_run=true` again; counts should stay the same (idempotency check).

**16. `POST /playoff-format` is truly idempotent**
Run the same POST twice without `dry_run`. The second call should succeed (no 500) and return the same `classes_inserted` / `slots_inserted` counts — ON CONFLICT DO NOTHING should swallow the duplicates silently.

**17. `POST /championship-venue?dry_run=true` lists the right games**
After the championship games are ingested, call with `?dry_run=true`. The `games` list in the response should contain exactly one row per class (7 rows for a full season). If a class is missing, the AHSFHS scraper didn't import that game yet.

**18. `POST /championship-venue` and re-run is safe**
Apply the venue assignment, then call it again. The second call should 404 with "No unassigned Championship Game rows found" — confirming the `location_id IS NULL` filter prevents double-assignment.
