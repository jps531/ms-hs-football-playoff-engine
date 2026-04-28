# API Testing Checklist — Post Season Backfill

Use these checks in the Swagger UI after seeding a full season to verify data integrity and algorithm correctness.

---

## Standings (`GET /api/v1/standings/{clazz}/{region}`)

**1. Final-week odds should be 0.0 or 1.0 for all teams**
Pick any class/region after the final regular-season date — every team should be either `clinched: true` or `eliminated: true`, and all four odds fields should be exactly `0.0` or `1.0`. If you see fractional odds at the final date, the pipeline didn't finish running.

**2. Odds sum to ≤ 1.0 per position**
The sum of `odds_1st` across all teams should be ≤ 1.0 (exactly 1.0 when no team is eliminated yet, possibly less once some are). Same for 2nd/3rd/4th.

**3. Time-travel consistency with `?date=`**
Hit the same region with `?date=YYYY-10-10` (mid-season), `?date=YYYY-10-24` (late season), and no date. Odds should move from fractional → sparser → binary. If mid-season returns the same binary result as end-of-season, the snapshot lookup is broken.

**4. `scenarios_available` flips at the right threshold**
Early in the season (e.g. `?date=YYYY-09-12`), `scenarios_available` should be `false` (too many remaining games). Around the final 2 weeks it should flip to `true` with an actual `scenarios` list.

---

## Games (`GET /api/v1/games`)

**5. Game count sanity**
`GET /api/v1/games?season=YYYY&class=7&region=3` — count the returned games. A typical 7-team region plays 6 games each, so ~21 unique matchups total. Fewer than expected means some scraping missed a week.

**6. No duplicate games**
Each game should appear exactly once. If you see the same matchup twice on the same date, the dedup logic has a bug.

**7. All completed games have `status = "Final"`**
After backfill, every game from before the season's end should have a final status. Spot-check a known Week 1 game — score and status should both be populated.

---

## Bracket (`GET /api/v1/bracket?season=YYYY&class=5`)

**8. Clinched slots show the correct school**
The `school` field on each bracket entry should match the actual seeding outcome from that season. Compare a few known seeds against actual MHSAA results — this is the highest-confidence sanity check.

**9. Non-clinched slots have `school: null` early in the season**
Query with `?date=YYYY-10-01` — most slots should have `school: null` and fractional odds. If every slot shows a school name even on that early date, `clinched` flags were written too aggressively.

---

## Ratings (`GET /api/v1/ratings?season=YYYY`)

**10. Elo ordering makes intuitive sense**
The highest-Elo teams per class should roughly match the teams that went deepest in the playoffs. If the #1 Elo team in 6A is a team that missed the playoffs, the cross-season carryover or K-factor is misconfigured.

**11. Every active team has a rating**
`GET /api/v1/ratings?season=YYYY&class=7` — the count should match the number of 7A schools. A team missing a rating usually means they had no games scraped.

---

## Hosting (`GET /api/v1/hosting/{clazz}/{region}`)

**12. 1-seeds always have the highest hosting odds**
For any completed region, the 1-seed's round-1 hosting odds should be `1.0` (they always host). If a lower seed shows higher odds than the 1-seed, there's a bracket-slot mapping bug.

---

## Simulate (`POST /api/v1/standings/{clazz}/{region}/simulate`)

**13. Simulating all remaining games produces binary odds**
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
