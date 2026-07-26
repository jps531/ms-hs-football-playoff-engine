-- Seed historical MHSAA state championship venues, all classes, 1992-2026.
-- Class count by year: 1-4 (<=1983), 1-5 (1984-2008), 1-6 (2009-2022), 1-7 (2023-present).
-- Safe to re-run; ON CONFLICT DO NOTHING skips rows that already exist.

WITH season_venue (season, venue_name) AS (
  SELECT s, 'Mississippi Veterans Memorial Stadium'
  FROM generate_series(1992, 2013) AS s
  UNION ALL
  VALUES
    (2014, 'Davis Wade Stadium'),
    (2015, 'Vaught-Hemingway Stadium'),
    (2016, 'Davis Wade Stadium'),
    (2017, 'Vaught-Hemingway Stadium'),
    (2018, 'M.M. Roberts Stadium'),
    (2019, 'M.M. Roberts Stadium'),
    (2020, 'Mississippi Veterans Memorial Stadium'),
    (2021, 'M.M. Roberts Stadium'),
    (2022, 'M.M. Roberts Stadium'),
    (2023, 'Vaught-Hemingway Stadium'),
    (2024, 'M.M. Roberts Stadium'),
    (2025, 'Davis Wade Stadium'),
    (2026, 'Davis Wade Stadium')
),
season_class AS (
  SELECT sv.season, sv.venue_name, gs.class
  FROM season_venue sv
  CROSS JOIN LATERAL generate_series(1, CASE
    WHEN sv.season <= 1983 THEN 4
    WHEN sv.season <= 2008 THEN 5
    WHEN sv.season <= 2022 THEN 6
    ELSE 7
  END) AS gs(class)
)
INSERT INTO championship_venues (season, class, location_id)
SELECT sc.season, sc.class, l.id
FROM season_class sc
JOIN locations l ON l.name = sc.venue_name
ON CONFLICT (season, class) DO NOTHING;
