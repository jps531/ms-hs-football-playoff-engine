-- Apply to an existing database (init.sql only runs when the database is first
-- created). Safe to run more than once.
--
--   docker compose exec -T db psql -U postgres -d mshsfootball < sql/migrations/2026_10_attended_games_follow_moves.sql
--
-- ---------------------------------------------------------------------------
-- Games people marked as attended follow a game to its new date
-- ---------------------------------------------------------------------------
-- When AHSFHS moves a game by a few days, the schedule pipeline now moves the
-- game's row to the new date instead of replacing it, so its approved
-- corrections and helmet stay. ON UPDATE CASCADE carries the attendance rows
-- along; without it the move fails. Replaces the (school, date) foreign key
-- whatever it's named.

DO $$
DECLARE
  fk TEXT;
BEGIN
  FOR fk IN
    SELECT conname FROM pg_constraint
    WHERE conrelid = 'user_attended_games'::regclass
      AND confrelid = 'games'::regclass
      AND contype = 'f'
  LOOP
    EXECUTE format('ALTER TABLE user_attended_games DROP CONSTRAINT %I', fk);
  END LOOP;
END $$;

ALTER TABLE user_attended_games
  ADD CONSTRAINT user_attended_games_school_date_fkey
  FOREIGN KEY (school, date) REFERENCES games(school, date) ON UPDATE CASCADE ON DELETE CASCADE;
