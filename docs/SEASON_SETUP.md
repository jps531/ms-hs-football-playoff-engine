# New Season Setup

## Playoff bracket format

When MHSAA reclassifies schools (every two years) or the bracket structure changes, add the new season's playoff format:

1. Copy `sql/seeds/playoff_format_template.yaml` to `sql/seeds/playoff_formats_YYYY.yaml` and fill in `season`, `classes`, and `slots` to match the MHSAA bracket.
2. Generate the matching SQL seed file by hand (follow the pattern in `sql/seeds/playoff_formats_2026.sql`) and save it as `sql/seeds/playoff_formats_YYYY.sql`.
3. Mount the SQL file in `docker-compose.yml` under the `db` service volumes so fresh deployments seed it automatically:
   ```yaml
   - ./sql/seeds/playoff_formats_YYYY.sql:/docker-entrypoint-initdb.d/NN_playoff_formats_YYYY.sql:ro
   ```
4. To seed an **already-running** database without restarting, use the script (idempotent):
   ```
   uv run python backend/scripts/add_playoff_season.py --config sql/seeds/playoff_formats_YYYY.yaml
   ```
   Or POST directly to `POST /api/v1/admin/playoff-format` via the Swagger UI. Use `?dry_run=true` first to preview counts.

After the championship games are ingested by the AHSFHS pipeline, assign the venue:

1. `GET /api/v1/admin/locations` if you need to double-check the venue's name/`home_team` as it's stored.
2. `POST /api/v1/admin/championship-venue` with `{ "season": YYYY, "location": "Venue Name or School Name" }` — `location` is matched case-insensitively against `locations.name` or `locations.home_team` and must resolve to exactly one venue (404 if it matches none, 409 if it matches more than one). Add `"class": N` to target a single class; omit it to assign the venue to every class in the season.
3. Use `?dry_run=true` first to confirm which game rows will be updated.

This upserts `championship_venues` (the source of truth, usable even before that season's Championship Game rows exist) and mirrors the venue onto any existing Championship Game rows in `games`. Use `GET /api/v1/admin/championship-venue?season=YYYY` to review current assignments.

## School consolidations, closures, and mid-cycle changes

MHSAA publishes classification assignments on a 2-year cycle. The Regions pipeline reads the same article for both years in a cycle, so consolidations and closures that happen mid-cycle require manual steps after the pipeline runs.

**Step 1 — Deactivate closed/merged schools for the new season**

After running the Regions pipeline for the new season, suppress each closed or merged school:

```
PATCH /api/v1/admin/school-seasons/{old_school}/{season}
{"is_active": false}
```

Their `schools` rows and all historical game data are preserved; they stop appearing in the new season's standings and scenarios.

**Step 2 — Create the new school's season entry**

```
PUT /api/v1/admin/school-seasons/{new_school}/{season}
{"class": N, "region": N, "is_active": true}
```

This creates the `schools` row if it doesn't exist yet (safe to run before AHSFHS schedules publish), then upserts the `school_seasons` row with the correct class and region assignment.

**Step 3 — Set identity data for the new school**

The MHSAA school identity and NCES location pipelines won't have data for a brand-new consolidated school until MHSAA updates their directory. Set known fields immediately via admin overrides:

```
PUT /api/v1/admin/schools/{school}/overrides   {"field": "mascot",           "value": "..."}
PUT /api/v1/admin/schools/{school}/overrides   {"field": "primary_color",    "value": "..."}
PUT /api/v1/admin/schools/{school}/overrides   {"field": "secondary_color",  "value": "..."}
PUT /api/v1/admin/schools/{school}/overrides   {"field": "latitude",         "value": "..."}
PUT /api/v1/admin/schools/{school}/overrides   {"field": "longitude",        "value": "..."}
```

Valid override fields: `display_name`, `mascot`, `primary_color`, `secondary_color`, `primary_color_hex`, `secondary_color_hex`, `latitude`, `longitude`. (`city` is populated only by the NCES pipeline and will be NULL until that pipeline runs for the new school.)

Once MHSAA publishes the school's directory entry and the pipelines can fetch the data naturally, clear overrides with `DELETE /api/v1/admin/schools/{school}/overrides/{field}` — or leave them in place, as overrides always win over pipeline values.

**Elo ratings for consolidated schools**

Consolidated schools start the season at the class prior (no manual seeding needed). If the merged program is significantly stronger or weaker than a fresh entrant to their new class, you can seed a starting rating by inserting a synthetic `team_ratings` row for the prior season — the carryover calculation (`50% class prior + 50% prior season Elo`) will use it on the next pipeline run.

---

## Known data corrections (`sql/corrections/`)

Some scraped game results require manual correction because MHSAA overruled an outcome
after the initial scrape. These corrections are stored as overrides (not direct `games`
table updates) so they survive pipeline re-runs and leave the original scraped data intact.

**Applying corrections after a fresh deployment:**
After the season's games are scraped, run any relevant correction scripts before triggering
the standings or playoff pipelines:
```
docker compose --env-file .env.local --profile local-db exec -T db \
  psql -U postgres -d mshsfootball < sql/corrections/<script>.sql
```

Scripts are idempotent — re-running a script after pipelines have already processed is safe
(overrides are already in place; just re-run the standings and playoff pipelines afterward).

To inspect all active overrides:
```sql
SELECT * FROM list_overrides();
```

### Salem 2025 (`sql/corrections/salem_forfeit_2025.sql`)

AHSFHS recorded 6 Salem regular-season games as `final_forfeit` (opponents W, Salem L).
MHSAA later overruled the forfeits; actual game scores stand (Salem wins each game).

Games affected: Salem vs McLaurin (8/29), Wilkinson County (9/5), Richton (9/12),
Discovery Christian (10/3), West Lincoln (10/10), Mount Olive (10/24).

After applying the correction, re-run both pipelines:
1. `region-scenarios-data-pipeline` (Custom Run, season 2025)
2. `playoff-bracket-update` (Custom Run, season 2025)

Or run `backfill-historical-snapshots` for 2025, which does both and also redoes the past weeks.

---

## 2026: Leake (5A Region 2)

Leake County (1A Region 5) and Leake Central (4A Region 5) merged to form Leake (5A Region 2),
on Leake Central's campus and under its identity. AHSFHS and the MHSAA 2025–27 region page still
call it "Leake Central", so the site records the new name itself:

- `SCHOOL_RENAMES` in `backend/helpers/data_helpers.py` says "Leake Central" is "Leake" from 2026
  on. The regions, schedule and score pipelines file everything from 2026 under "Leake" (its own
  games and every opponent's), and still fetch AHSFHS's "Leake Central" page for it. 2025 and
  earlier keep Leake Central and Leake County as they were.
- Leake's first season carries Leake Central's final 2025 Elo rating (`with_predecessor_ratings`),
  as any school's does from one season to the next.
- Old team links (`?team=leake-central`) still open Leake on 2026 pages (`FORMER_SLUGS` in
  `nginx/html/static/js/routes.js`).

To move 2026 data stored before the rename, run
`sql/migrations/2026_10_leake_central_to_leake.sql`, then the daily update (or
`region-scenarios-data-pipeline` then `share-assets`) for 2026 so today's numbers pick up the Elo
carryover. Earlier 2026 snapshots keep the Projected odds they were published with; run
`backfill-historical-snapshots` for 2026 if past weeks should use the carried-over rating too.

For a future rename, add a line to `SCHOOL_RENAMES` and `FORMER_SLUGS`, and adapt the migration.
