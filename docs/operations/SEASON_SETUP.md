# New Season Setup

## Playoff bracket format

When MHSAA reclassifies schools (every two years) or the bracket structure changes, add the new season's playoff format:

1. Copy `sql/seeds/playoff_format_template.yaml` to `sql/seeds/playoff_formats_YYYY.yaml` and fill in `season`, `classes`, and `slots` to match the MHSAA bracket.
2. Generate the matching SQL seed file by hand (follow the pattern in `sql/seeds/playoff_formats_2026.sql`) and save it as `sql/seeds/playoff_formats_YYYY.sql`.
3. Mount the SQL file in `docker-compose.yml` under the `db` service volumes so fresh deployments seed it automatically:
   ```yaml
   - ./sql/seeds/playoff_formats_YYYY.sql:/docker-entrypoint-initdb.d/NN_playoff_formats_YYYY.sql:ro
   ```
4. To seed an **already-running** database, run the script in the worker container, which has the code, `sql/seeds/` and the database settings. Pull and rebuild the worker first (`docker compose … up --build -d prefect-worker`) so the image has the new YAML, then check it with `--dry-run` and run it for real:
   ```
   docker compose --env-file .env.local --profile local-db exec prefect-worker \
     python backend/scripts/add_playoff_season.py --config sql/seeds/playoff_formats_YYYY.yaml --dry-run
   docker compose --env-file .env.local --profile local-db exec prefect-worker \
     python backend/scripts/add_playoff_season.py --config sql/seeds/playoff_formats_YYYY.yaml
   ```
   It checks the config first (classes 1–7, every slot complete, `north_south` of `N` or `S`), skips rows already there, and prints how many it added. Locally, add `-f docker-compose.yml -f docker-compose.local.yml` to the commands.

After the championship games are ingested by the AHSFHS pipeline, assign the venue:

1. `GET /api/v1/admin/locations` if you need to double-check the venue's name/`home_team` as it's stored.
2. `POST /api/v1/admin/championship-venue` with `{ "season": YYYY, "location": "Venue Name or School Name" }` — `location` is matched case-insensitively against `locations.name` or `locations.home_team` and must resolve to exactly one venue (404 if it matches none, 409 if it matches more than one). Add `"class": N` to target a single class; omit it to assign the venue to every class in the season.
3. Use `?dry_run=true` first to confirm which game rows will be updated.

This upserts `championship_venues` (the source of truth, usable even before that season's Championship Game rows exist) and mirrors the venue onto any existing Championship Game rows in `games`. Use `GET /api/v1/admin/championship-venue?season=YYYY` to review current assignments.

## Regions (every two years)

MHSAA assigns classes and regions on a two-year cycle and publishes the next cycle's regions in the
fall, about a year ahead. The site's regions come from one checked-in file per cycle,
`backend/data/regions/{first}-{last}.csv` (`2027-29.csv` for 2027 and 2028), one school a line:

```
school,class,region,seasons
North Tippah,3,2,
Leake Central,4,5,2025
```

`school` is the site's name for the school. `seasons` is blank for both seasons of the cycle, or
names the one season a line holds for (a mid-cycle move, a season without a team, or a rename).

**For a new cycle:**

1. Draft the file from MHSAA's article, in the worker container (it has the browser):
   ```
   docker compose --env-file .env.local --profile local-db exec prefect-worker \
     python -m backend.tools.draft_regions --season 2029 --url https://www.misshsaa.com/… > 2029-31.csv
   ```
   (Locally: `uv run python -m backend.tools.draft_regions --season 2029 --url … > backend/data/regions/2029-31.csv`.)
   It reads the article's tables, and those of a page embedded in it, in either layout MHSAA has
   used. Add the article to `ARTICLES` in `backend/tools/draft_regions.py` to skip `--url`. What it
   can't place it prints as `CHECK:` lines: a name the site doesn't know (fix the spelling to the
   site's name, or add MHSAA's spelling to `MHSAA_NAMES`), or a school from last season that isn't
   there (it stopped playing, was renamed or consolidated; see below).
2. Check the file, commit it, deploy.
3. Run `regions-data-pipeline` (Custom Run) for each season of the cycle. It checks the season
   against the database before writing anything and stops, listing every problem, if a name isn't a
   school the site knows, a region has fewer than three schools, a class's regions aren't numbered
   from 1, or a school from the season before has no place.
4. Run `share-assets` (or wait for the next daily update). The Regions page (`/regions/{class}a`)
   then opens on the new cycle, with its maps and images to share; the cycles before stay in its
   season picker. A school with no coordinates, or coordinates outside Mississippi, is listed but
   gets no dot (the run's log names it); fix its location with the admin overrides.

Loading a cycle early is safe: the site's current season is the newest one with games (`/seasons`),
so the loaded season stays out of sight until its schedule is in. Only the Regions page shows it.

## Consolidations, schools that stop playing, and renames

Record these in `backend/helpers/data_helpers.py`, next to the region file:

- **A school stopped playing** (closed, or fielded no team): `SCHOOL_STOPPED_PLAYING`, with its last
  season played and why. A school that comes back just gets a line in its season's region file again.
- **A new school carries on an old one** (a consolidation on one school's campus): `SCHOOL_SUCCESSORS`,
  (old school, new school, first season). The new school starts from the old one's Elo rating, and
  the regions load gives it the old school's campus (city, ZIP, coordinates) and home field when it
  has none of its own. Add the old team link to `FORMER_SLUGS` in `nginx/html/static/js/routes.js`.
  The schedule sources are asked for the new name.
- **A school goes by a new name while the sources still use the old one**: `SCHOOL_RENAMES`. The
  pipelines file everything under the new name and still ask the sources for the old one; see
  Leake below. Add it to `FORMER_SLUGS` too.

Then list the school under its new name in the region file. A school MHSAA moved mid-cycle gets a
line for each season (`seasons` 2025 on one, 2026 on the other).

**Identity data for a new school.** The MHSAA directory and NCES pipelines won't have a brand-new
school until those sources do. Set what's known with admin overrides (a successor already has its
old school's location):

```
PUT /api/v1/admin/schools/{school}/overrides   {"field": "mascot",           "value": "..."}
PUT /api/v1/admin/schools/{school}/overrides   {"field": "primary_color",    "value": "..."}
PUT /api/v1/admin/schools/{school}/overrides   {"field": "secondary_color",  "value": "..."}
```

Valid override fields: `display_name`, `mascot`, `primary_color`, `secondary_color`, `primary_color_hex`, `secondary_color_hex`, `latitude`, `longitude`. Overrides always win over pipeline values; clear one with `DELETE /api/v1/admin/schools/{school}/overrides/{field}`.

## 2027: North Tippah (Region 2-3A)

Falkner (Region 2-1A) and Walnut (Region 1-2A) consolidate into North Tippah (Region 2-3A) for 2027,
on Walnut's campus. `SCHOOL_SUCCESSORS` has Walnut → North Tippah from 2027: North Tippah starts from
Walnut's final 2026 Elo rating and takes Walnut's location and home field when the 2027 regions load.
`SCHOOL_STOPPED_PLAYING` has Falkner's last season, 2026. Old `?team=walnut` links open North Tippah on
2027 pages. Its mascot and colors aren't set yet; until they are, it shows the default helmet and colors.

## Thrasher (suspended)

Thrasher (Region 1-1A in 2025) suspended its program indefinitely after 2025 for lack of players.
`2025-27.csv` lists it for 2025 only, `SCHOOL_STOPPED_PLAYING` has its last season as 2025, and
MHSAA's 2027-29 list doesn't include it. If it comes back, add its line to that cycle's region file
(with `seasons` set if it's only one season of the cycle) and load the season again.

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

## 2026: Leake (Region 2-5A)

Leake County (Region 5-1A) and Leake Central (Region 5-4A) merged to form Leake (Region 2-5A),
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
