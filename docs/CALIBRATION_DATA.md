# Calibration data

The plan for 2027 is to publish how often stated odds come true: of everything
we called 70%, did about 70% happen? That has to be measured against the odds
as they were **published**, not as they were later recomputed.

`region_standings` can't answer that alone. It's the table the site serves,
and it gets rewritten:

- a rerun on the same day replaces that day's rows;
- `backfill_historical_snapshots` recomputes past game dates in place and
  deletes the regular-season rows dated between them;
- once a class reaches the playoffs, the playoff update deletes its daily rows
  between playoff dates.

## The archive

Every insert or update on `region_standings` is also appended to
`region_standings_archive` by a database trigger
(`sql/migrations/2026_10_region_standings_archive.sql`). Each archive row has:

| Column | What it is |
|---|---|
| `school`, `season`, `as_of_date`, `class`, `region` | Which snapshot row this is |
| `computed_at` | When the pipeline computed it (`NULL` for rows that existed before the archive) |
| `model_version` | `MODEL_VERSION` in `region_scenarios_pipeline.py` at the time |
| `archived_at` | When the archive received it |
| `snapshot` | The whole `region_standings` row as JSON: every odds field, both modes |

Nothing updates or deletes archive rows; a trigger refuses both. To prune on
purpose, drop `region_standings_archive_guard` first.

Bump `MODEL_VERSION` whenever a change alters the odds themselves (Elo
parameters, home-field advantage, tiebreakers, simulation counts, bracket or
hosting rules), so a report can separate one model's record from another's.

## Reading it

The first archived version of a team's day is what was published for it:

```sql
SELECT DISTINCT ON (school, season, as_of_date)
       school, season, as_of_date, computed_at, model_version,
       (snapshot->>'odds_playoffs')::real          AS playoffs,
       (snapshot->>'odds_playoffs_weighted')::real AS playoffs_projected
FROM region_standings_archive
WHERE season = 2026 AND computed_at IS NOT NULL
ORDER BY school, season, as_of_date, archived_at;
```

Join that to the outcome (final seeds from the last regular-season snapshot,
playoff results from the bracket) to compare stated odds with what happened.

## Before the archive

2026 rows written before the migration are in the archive with
`computed_at` `NULL`. They hold what `region_standings` contained on the day
of the migration: for dates covered by the 2026 backfill, those are
recomputations rather than what was shown at the time. Treat them as
reconstructed, not published.
