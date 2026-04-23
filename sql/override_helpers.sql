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
