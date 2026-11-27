-- list_overrides() (sql/override_helpers.sql) also lists past looks' overrides (school_looks), as
-- 'look:<id>:<school>', for /moderate's Overrides tab.
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
  WHERE overrides != '{}'::jsonb
  UNION ALL
  SELECT 'look:' || id::text || ':' || school, kv.key, kv.value
  FROM school_looks, jsonb_each_text(overrides) AS kv
  WHERE overrides != '{}'::jsonb;
$$ LANGUAGE sql;
