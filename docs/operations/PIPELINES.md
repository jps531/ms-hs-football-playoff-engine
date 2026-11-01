# Pipelines

Every Prefect deployment the worker serves (`backend/prefect/flows.py`), what it
does, and when to run it by hand. Open them in the Prefect UI under
**Deployments**: locally at `http://localhost:4200`, on the server through the
**Prefect** link on `/moderate`. Anything that takes a season defaults to the
current calendar year; use a **Custom Run** for another.

Schedules are America/Chicago.

## On a schedule

| Deployment | When | What it does |
|---|---|---|
| `daily-update` | Daily, 9:00 AM | Pulls the scores (`ahsfhs-schedule-data-pipeline`), then recalculates everything from them (`region-scenarios-data-pipeline`), all in one database transaction: the site keeps its last numbers, and the time they were calculated, until the whole update is done, then switches at once. If any part fails, none of it is kept. After the pull, AHSFHS's playoff games are checked against the bracket's settled games (a game is settled once both its teams are known: both seeds for a first-round game, both feeding games' winners for a later one). A team listed against a different opponent than the bracket pairs it with, or still playing after it was knocked out, stops the update (none of it is kept) and emails `ALERT_TO` (else `DIGEST_TO`) the list; a game the bracket hasn't settled, or one AHSFHS doesn't list yet, is fine. After the commit it lists the season's past games still without a final score, and draws the share images; if either fails, the update still counts as done. Any other failure, and anything to look at in a run that succeeded, is emailed (see [Emails to the owner](#emails-to-the-owner)). While it runs, an approval or other write that needs a game row it's updating waits at most 5 seconds, then gets "The daily update is running. Please try again in a few minutes." |
| `submission-digest` | Daily, 7:00 AM | Emails `DIGEST_TO` what's waiting in the moderation queue; sends nothing when the queue is clear, and only logs the email when SMTP isn't set up. Also removes the contact email from feedback decided more than 90 days ago. See [VM_DEPLOYMENT.md](VM_DEPLOYMENT.md#daily-digest-email). |
| `recompute-after-corrections` | Every 5 minutes | Works approved score and date corrections into the numbers. Approving one records its season and the earliest date it changes (`recompute_requests`); once no correction has been approved for 10 minutes, this recomputes that season's past snapshots from that date (`backfill-historical-snapshots` with `from_date`), then, for the current season, today's numbers and the share images (`region-scenarios-data-pipeline`). A correction approved meanwhile stops it between dates, and it starts over from the earliest date once they stop. Most runs find nothing waiting and finish at once. |
| `ahsfhs-score-probe` | Friday and Saturday, every 15 minutes 6:00–9:45 AM, and at 10:00 AM | A temporary measurement: checks one team page per region that played the night before and records how many of that night's games AHSFHS already shows a final score for (logged, and saved as the `ahsfhs-score-probe` table artifact). It writes nothing to the database. It's there to learn whether the 9:00 pull could run earlier; once the artifacts answer that, the 9:00 time can be adjusted and the probe removed from `flows.py`. |

### One heavy update at a time

The daily update, the schedule pull, the region update, the backfill, the playoff bracket update, the explanation refresh and the recompute after corrections share a lock (`backend/helpers/run_lock.py`, a Postgres advisory lock). Each waits for whichever is running to finish before it starts; the recompute instead skips its turn and tries again 5 minutes later. A flow run as part of another (the daily update's two halves, the backfill inside the recompute) goes straight through.

### Emails to the owner

These go to `ALERT_TO`, or `DIGEST_TO` when that's empty, through the digest's SMTP settings ([VM_DEPLOYMENT.md](VM_DEPLOYMENT.md#daily-digest-email)). Without SMTP they're logged as errors instead.

- **A failed run** of `daily-update`, `recompute-after-corrections` or `playoff-bracket-update` (`backend/prefect/failure_alerts.py`): which one, the error, and what the site shows meanwhile. Each sends at most one such email every 6 hours, so a recompute failing every 5 minutes sends one. Only a run started on its own emails: the playoff update inside the daily update fails the daily update, which emails once. A run killed outright (out of memory, a restart) sends nothing.
- **The daily update stopped itself** over a playoff game that disagrees with the bracket (above): the list of games, instead of the failure email.
- **The daily update finished, with things to look at** (`backend/helpers/attention.py`): one email, sent after the commit, listing by kind
  - games of the season dated before today (in Mississippi) that still have no final score, each once, a region game marked as one since it still counts as unplayed (`backend/helpers/missing_scores.py`; a canceled game isn't listed, and a forfeit is final);
  - schools whose AHSFHS page couldn't be read (their new scores aren't in);
  - scores AHSFHS changed under an approved correction (the correction still shows);
  - finished or corrected games no longer on AHSFHS, kept;
  - share images that failed to draw.

  A day with none of these sends nothing.

## The daily update's two halves

Run on their own after a fix, or with a Custom Run for another season.

| Deployment | What it does |
|---|---|
| `ahsfhs-schedule-data-pipeline` | Scrapes every school's AHSFHS schedule page into `games` (insert or update). First, a game whose date a moderator corrected (an approved "Wrong date?" report) is put back on its corrected date when AHSFHS lists it within three days of the date AHSFHS had then, so the correction sticks. Then it removes games a school's page no longer lists, such as the old date of a rescheduled game, so `games` mirrors AHSFHS. A game moved by up to three days keeps its row, moved to the new date, so its approved corrections, helmet and attendance go with it. It never removes a finished game or one with an approved correction; it logs a warning instead. It also warns when AHSFHS changes a score that has an approved correction to something else; the correction still shows. When AHSFHS changes it to match the correction (it caught up with a reported score), that's logged without a warning. Last, it gives each game's two rows the same `game_id` (a new row joins its opponent's row's id). It covers the schools already in the database for that season (from `regions-data-pipeline`). |
| `region-scenarios-data-pipeline` | From the games in the database: Elo and RPI, each region's seeding odds (Toss-up and Projected), playoff advancement and home-game odds, scenarios and key insights, written for today to `team_ratings`, `region_standings`, `region_seed_pairs`, `region_scenarios` and `region_computation_state`, plus each final game's pregame win probability. Classes already in the playoffs are left to `playoff-bracket-update`, which it runs at the end when any are; then it redraws the share assets (a failure there doesn't fail the update). |

## By hand

| Deployment | When to run it |
|---|---|
| `regions-data-pipeline` | Pre-season, and when MHSAA reclassifies (every two years): writes each school's class and region for the season to `school_seasons`, adding new schools to `schools`. |
| `nces-school-pipeline` | Pre-season, and when schools move: city, ZIP, latitude and longitude for public schools from the NCES EDGE API, then the private-school location seed. Fields with an override are left alone. |
| `misshsaa-school-pipeline` | Pre-season, and when schools rebrand: mascot and colors from the MHSAA school directory. |
| `backfill-historical-snapshots` | Once per season after importing a full season's games, again after re-importing them, and after any change that bumps `MODEL_VERSION` (so past weeks use the current model). Recomputes every game date's snapshot, runs `playoff-bracket-update` for the playoff dates, and deletes the season's regular-season rows dated between game dates, which would otherwise shadow them. Each snapshot uses only the games played by its date (`get_standings_for_region` applies the date to every aggregate; a game's date is its `game_date`, the same for both schools, see [SCHEMA.md](../architecture/SCHEMA.md)), so past weeks show the records and odds as they stood then. A region whose teams, games and win chances are what they were on its last date reuses that date's odds rather than working them out again, and its scenarios, team paths and insights carry over while its games stay the same (with five or fewer left, while the win chances do too); its bracket and hosting odds, which turn on the whole class, are always worked out. With six to fifteen games left, a date where only the win chances changed re-weights the region's last standings instead of working each outcome out again (the same counts, in a tenth of the time with fifteen left). The run's log says how many region-dates reused each. See [VM_DEPLOYMENT.md](VM_DEPLOYMENT.md#deploying-updates). |
| `refresh-scenario-explanations` | After a change to how the scenario explanations ("why this order") are worded or labelled, instead of a backfill: for each of the season's snapshots with 1 to 5 region games left, rebuilds the scenarios from the games as of that date and, when they match what's stored, writes back only the explanations (odds, standings, insights and brackets stay). A snapshot whose rebuilt scenarios don't match is left alone and counted as `mismatched` in the run's log; it needs `region-scenarios-data-pipeline` (today's) or `backfill-historical-snapshots`. Run `share-assets` afterwards so the pre-rendered pages show the new words. |
| `playoff-bracket-update` | Rarely: the daily update and the backfill both run it. It reads the completed playoff games, marks eliminated teams, and writes one `region_standings` snapshot per class, region and round date. Once a class's playoffs start, the daily region run leaves its rows to this flow: the regular-season odds ignore playoff results, and a newer row would hide the playoff-aware ones. Run it alone only to refresh those rows. |
| `share-assets` | After a deploy or a rerun, to redraw now rather than at the next daily update: the link-preview cards and meta tags, the pre-rendered page content, and `sitemap.xml`. See [VM_DEPLOYMENT.md](VM_DEPLOYMENT.md#share-cards-link-previews). |

## Pre-season order

Run these in order; each needs the previous step's data in the database.

1. `regions-data-pipeline`: each school's class and region for the season (`school_seasons`). A Quick Run is the current year; use a Custom Run for another season.
2. `nces-school-pipeline`: city, ZIP, latitude and longitude for public schools from the NCES EDGE API, then the private-school location seed.
3. `misshsaa-school-pipeline`: mascot and colors from the MHSAA school directory.
4. `ahsfhs-schedule-data-pipeline`: the season's `games` rows from each school's AHSFHS schedule.
5. `region-scenarios-data-pipeline` for the same season: odds, standings and scenarios for today.

For a completed past season, follow with `backfill-historical-snapshots` so every past week has its snapshot.

Re-run steps 2–3 if schools move or rebrand, and step 1 if MHSAA reclassifies (every two years). The bracket structure for 2025 and 2026 (`playoff_formats`, `playoff_format_slots`) is seeded when the database is created, from `sql/seeds/playoff_formats_2025.sql` and `_2026.sql`; a later season is added with the script in [SEASON_SETUP.md](SEASON_SETUP.md#playoff-bracket-format), along with any consolidations or closures.

## Scripts

Run from the repository root.

| Script | What it's for |
|---|---|
| `scripts/backup_db.sh` | Nightly database backup from cron; see [VM_DEPLOYMENT.md](VM_DEPLOYMENT.md#backups). |
| `scripts/posthog_dashboard.py` | Builds the PostHog "Site activity" dashboard once; see [ANALYTICS.md](../reference/ANALYTICS.md#the-dashboard). |
| `scripts/prefect_smoke.py` | CI only: checks that a real Prefect flow runs in the worker image. |
| `backend/scripts/add_playoff_season.py` | Seeds a new season's playoff bracket format (`playoff_formats`, `playoff_format_slots`) from a YAML config into a running database, run in the worker container; see [SEASON_SETUP.md](SEASON_SETUP.md#playoff-bracket-format). |
