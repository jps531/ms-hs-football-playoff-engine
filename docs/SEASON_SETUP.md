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

1. `GET /api/v1/admin/locations` to find the correct `location_id` for the venue.
2. `POST /api/v1/admin/championship-venue` with `{ "season": YYYY, "location_id": N }`.
3. Use `?dry_run=true` first to confirm which game rows will be updated.

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
psql $DATABASE_URL -f sql/corrections/<script>.sql
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
1. `region_standings_pipeline(season=2025)`
2. `playoff_bracket_update(season=2025)`

---

## 2026: Leake (5A Region 2)

Leake County (1A Region 5) and Leake Central (4A Region 5) merged to form Leake (5A Region 2).

After running the Regions pipeline for 2026:

```
PATCH /api/v1/admin/school-seasons/Leake%20County/2026   {"is_active": false}
PATCH /api/v1/admin/school-seasons/Leake%20Central/2026  {"is_active": false}
PUT   /api/v1/admin/school-seasons/Leake/2026            {"class": 5, "region": 2, "copy_identity_from": "Leake Central"}
```

The `copy_identity_from` field copies Leake Central's mascot, colors, city, zip, and coordinates into Leake's `schools` row immediately — before the MHSAA identity and NCES pipelines run, so identity is available from day one. The corresponding entries in `seed_mhsaa_identity.sql` and `seed_private_school_locations.sql` become no-ops once those fields are populated (both use `COALESCE` and won't overwrite). If Leake ever gets its own MHSAA directory entry or NCES record, those pipeline-sourced values take precedence. Elo starts at the 5A class prior — no manual seeding needed for a program moving up two classes.
