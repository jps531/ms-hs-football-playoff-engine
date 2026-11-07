-- ---------------------------------------------------------------------------
-- Override helper functions
--
-- Use these to set and clear override values on schools, locations, and games.
-- The overrides JSONB column is user-managed only — no pipeline task writes it.
-- ---------------------------------------------------------------------------


-- SCHOOLS

CREATE OR REPLACE FUNCTION set_school_override(p_school TEXT, p_field TEXT, p_value TEXT)
RETURNS VOID AS $$
  UPDATE schools
  SET overrides = jsonb_set(overrides, ARRAY[p_field], to_jsonb(p_value))
  WHERE school = p_school;
$$ LANGUAGE sql;

CREATE OR REPLACE FUNCTION clear_school_override(p_school TEXT, p_field TEXT)
RETURNS VOID AS $$
  UPDATE schools SET overrides = overrides - p_field WHERE school = p_school;
$$ LANGUAGE sql;


-- LOCATIONS (keyed by id)

CREATE OR REPLACE FUNCTION set_location_override(p_id INT, p_field TEXT, p_value TEXT)
RETURNS VOID AS $$
  UPDATE locations
  SET overrides = jsonb_set(overrides, ARRAY[p_field], to_jsonb(p_value))
  WHERE id = p_id;
$$ LANGUAGE sql;

CREATE OR REPLACE FUNCTION clear_location_override(p_id INT, p_field TEXT)
RETURNS VOID AS $$
  UPDATE locations SET overrides = overrides - p_field WHERE id = p_id;
$$ LANGUAGE sql;


-- GAMES (keyed by school + date)

CREATE OR REPLACE FUNCTION set_game_override(p_school TEXT, p_date DATE, p_field TEXT, p_value TEXT)
RETURNS VOID AS $$
  UPDATE games
  SET overrides = jsonb_set(overrides, ARRAY[p_field], to_jsonb(p_value))
  WHERE school = p_school AND date = p_date;
$$ LANGUAGE sql;

CREATE OR REPLACE FUNCTION clear_game_override(p_school TEXT, p_date DATE, p_field TEXT)
RETURNS VOID AS $$
  UPDATE games SET overrides = overrides - p_field WHERE school = p_school AND date = p_date;
$$ LANGUAGE sql;


-- A game's opponent, corrected: when a school's AHSFHS page names the wrong
-- opponent. The row gets the corrected opponent, overrides.ahsfhs_opponent
-- keeps the one AHSFHS listed (the first time; a second correction keeps the
-- original), and the row joins the opponent's row of the same game (its
-- game_id), when the opponent has one within three days. The schedule pipeline
-- keeps the corrected opponent on every later pull (apply_opponent_corrections).
CREATE OR REPLACE FUNCTION set_game_opponent(p_school TEXT, p_date DATE, p_opponent TEXT)
RETURNS VOID AS $$
BEGIN
  UPDATE games
  SET overrides = CASE WHEN overrides ? 'ahsfhs_opponent' THEN overrides
                       ELSE overrides || jsonb_build_object('ahsfhs_opponent', opponent) END,
      opponent = p_opponent
  WHERE school = p_school AND date = p_date;
  IF NOT FOUND THEN
    RAISE EXCEPTION '% has no game on %', p_school, p_date;
  END IF;
  UPDATE games g
  SET game_id = o.game_id
  FROM games o
  WHERE g.school = p_school AND g.date = p_date
    AND o.school = p_opponent AND o.opponent = p_school AND o.season = g.season
    AND o.date BETWEEN g.date - 3 AND g.date + 3 AND o.game_id <> g.game_id;
END;
$$ LANGUAGE plpgsql;

-- Undo it: the row goes back to the opponent AHSFHS listed. Its game_id is
-- put back in line by the next schedule pull of its season.
CREATE OR REPLACE FUNCTION clear_game_opponent(p_school TEXT, p_date DATE)
RETURNS VOID AS $$
  UPDATE games
  SET opponent = overrides->>'ahsfhs_opponent', overrides = overrides - 'ahsfhs_opponent'
  WHERE school = p_school AND date = p_date AND overrides ? 'ahsfhs_opponent';
$$ LANGUAGE sql;

-- CONVENIENCE: view all active overrides across all tables

CREATE OR REPLACE FUNCTION list_overrides()
RETURNS TABLE(source TEXT, key TEXT, value TEXT) AS $$
  SELECT 'school:' || school, kv.key, kv.value
  FROM schools, jsonb_each_text(overrides) AS kv
  WHERE overrides != '{}'::jsonb
  UNION ALL
  SELECT 'location:' || id::text, kv.key, kv.value
  FROM locations, jsonb_each_text(overrides) AS kv
  WHERE overrides != '{}'::jsonb
  UNION ALL
  SELECT 'game:' || school || ':' || date::text, kv.key, kv.value
  FROM games, jsonb_each_text(overrides) AS kv
  WHERE overrides != '{}'::jsonb;
$$ LANGUAGE sql;
