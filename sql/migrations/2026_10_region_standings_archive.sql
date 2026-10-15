-- Apply to an existing database (init.sql only runs when the database is first
-- created). Safe to run more than once.
--
--   docker compose exec -T db psql -U postgres -d mshsfootball < sql/migrations/2026_10_region_standings_archive.sql
--
-- ---------------------------------------------------------------------------
-- Odds snapshot archive (groundwork for publishing calibration)
-- ---------------------------------------------------------------------------
-- region_standings holds one row per team per day, and the site serves it. It
-- is also rewritten: reruns upsert the same day, the historical backfill
-- recomputes past days in place, and the playoff update deletes daily rows
-- once a class reaches the playoffs. That is right for what the site shows,
-- but a calibration report ("we said 70%; it happened 70% of the time") has to
-- measure the odds as they were published, not as they were recomputed later.
--
-- So every write to region_standings is also appended here, whole, by a
-- trigger, stamped with when the pipeline computed it and which model version
-- did. Nothing updates or deletes archive rows. The first archived version of
-- a team's (season, as_of_date) is what was published for that day; later
-- ones are recomputations (compare computed_at with as_of_date).
--
-- Rows copied in when this migration first runs have computed_at NULL: they
-- were already in region_standings, so when they were computed isn't known.

ALTER TABLE region_standings ADD COLUMN IF NOT EXISTS computed_at TIMESTAMPTZ;
ALTER TABLE region_standings ADD COLUMN IF NOT EXISTS model_version TEXT;

COMMENT ON COLUMN region_standings.computed_at IS
  'When the pipeline computed this row. NULL for rows written before the archive migration.';
COMMENT ON COLUMN region_standings.model_version IS
  'MODEL_VERSION in region_scenarios_pipeline.py at the time of the write. NULL before the archive migration.';

CREATE TABLE IF NOT EXISTS region_standings_archive (
  id             BIGSERIAL   PRIMARY KEY,
  school         TEXT        NOT NULL,
  season         INTEGER     NOT NULL,
  as_of_date     DATE        NOT NULL,
  class          INTEGER,
  region         INTEGER,
  computed_at    TIMESTAMPTZ,
  model_version  TEXT,
  archived_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  snapshot       JSONB       NOT NULL
);

COMMENT ON TABLE region_standings_archive IS
  'Append-only copy of every write to region_standings (see sql/migrations/2026_10_region_standings_archive.sql). '
  'The first row per (school, season, as_of_date) is what was published that day.';
COMMENT ON COLUMN region_standings_archive.snapshot IS
  'The full region_standings row as written (to_jsonb), so later schema changes never lose a field.';

CREATE INDEX IF NOT EXISTS idx_region_standings_archive_lookup
  ON region_standings_archive (season, school, as_of_date, archived_at);

-- Start the archive with what region_standings holds now (first run only).
INSERT INTO region_standings_archive (school, season, as_of_date, class, region, computed_at, model_version, snapshot)
SELECT rs.school, rs.season, rs.as_of_date, rs.class, rs.region, NULL, NULL, to_jsonb(rs)
FROM region_standings rs
WHERE NOT EXISTS (SELECT 1 FROM region_standings_archive);

CREATE OR REPLACE FUNCTION archive_region_standings() RETURNS trigger AS $$
BEGIN
  INSERT INTO region_standings_archive (school, season, as_of_date, class, region, computed_at, model_version, snapshot)
  VALUES (NEW.school, NEW.season, NEW.as_of_date, NEW.class, NEW.region, NEW.computed_at, NEW.model_version, to_jsonb(NEW));
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS region_standings_archive_write ON region_standings;
CREATE TRIGGER region_standings_archive_write
  AFTER INSERT OR UPDATE ON region_standings
  FOR EACH ROW EXECUTE FUNCTION archive_region_standings();

-- The archive is append-only. To prune it on purpose, drop this trigger first.
CREATE OR REPLACE FUNCTION region_standings_archive_append_only() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'region_standings_archive is append-only (drop trigger region_standings_archive_guard to prune it)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS region_standings_archive_guard ON region_standings_archive;
CREATE TRIGGER region_standings_archive_guard
  BEFORE UPDATE OR DELETE ON region_standings_archive
  FOR EACH ROW EXECUTE FUNCTION region_standings_archive_append_only();
