-- Apply to an existing database (init.sql only runs when the database is first
-- created). Safe to run more than once.
--
--   docker compose exec -T db psql -U postgres -d mshsfootball < sql/migrations/2026_10_region_seed_pairs.sql
--
-- ---------------------------------------------------------------------------
-- Region seed pairs
-- ---------------------------------------------------------------------------
-- One row per season/class/region/as_of_date, written alongside the region's
-- region_standings snapshot. Holds the probability that two teams from the
-- region land on two given playoff seeds together, which per-team seed odds
-- can't give: "Stringer is the 1 seed AND Lumberton the 4 seed". The bracket
-- matchup odds need it whenever two positions from one region can meet.
--
-- pairs / pairs_weighted: JSON arrays of [team_a, seed_a, team_b, seed_b, p]
-- with team_a < team_b, Toss-up and Projected respectively. Pairs that can't
-- happen are omitted. Readers fall back to the standings when every seed is
-- already locked (the pairs are then certain).

CREATE TABLE IF NOT EXISTS region_seed_pairs (
  season          INTEGER     NOT NULL,
  class           INTEGER     NOT NULL,
  region          INTEGER     NOT NULL,
  as_of_date      DATE        NOT NULL,
  pairs           JSONB       NOT NULL,
  pairs_weighted  JSONB       NOT NULL,
  computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (season, class, region, as_of_date)
);
