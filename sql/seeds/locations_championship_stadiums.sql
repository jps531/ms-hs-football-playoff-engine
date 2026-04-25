-- Seed the four Mississippi college stadiums used to host MHSAA state championship games.
-- Safe to re-run; ON CONFLICT DO NOTHING skips rows that already exist.

INSERT INTO locations (name, city, home_team, latitude, longitude)
VALUES
    ('M.M. Roberts Stadium',                  'Hattiesburg, MS', 'Southern Miss',  31.328889, -89.331389),
    ('Davis Wade Stadium',                    'Starkville, MS',  'Mississippi State', 33.456389, -88.793611),
    ('Vaught-Hemingway Stadium',              'Oxford, MS',      'Ole Miss',        34.361944, -89.331389),
    ('Mississippi Veterans Memorial Stadium', 'Jackson, MS',     'Jackson State',   32.329568, -90.179870)
ON CONFLICT (name, city, home_team) DO NOTHING;
