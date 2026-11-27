-- The schools of the 2015-2024 seasons (backend/data/regions/2015-17.csv to 2023-25.csv) the site
-- didn't have: closed, consolidated, or under a former name. Their towns, campuses, mascots and colors
-- are the site owner's (the hex colors are standard shades of the named colors, not the schools'
-- own). A school on another's campus takes its spot from that school's row. Run "Recompute all" on
-- /moderate (Overrides) afterwards for their color variants. Safe to run more than once: a school the
-- site has already is left as it is.

INSERT INTO schools (school, city, latitude, longitude, mascot, primary_color, secondary_color, primary_color_hex, secondary_color_hex)
VALUES
  ('Prentiss',          'Prentiss',     31.60594, -89.86849, 'Bulldogs', 'Red',        'Black',          '#C8102E', '#000000'),
  ('New Site',          'New Site',     34.56351, -88.41519, 'Royals',   'Red',        'White',          '#C8102E', '#FFFFFF'),
  ('J. F. Kennedy',     'Mound Bayou',  33.88157, -90.72656, 'Hornets',  'Blue',       'White',          '#0033A0', '#FFFFFF'),
  ('Durant',            'Durant',       33.07848, -89.85777, 'Tigers',   'Green',      'White',          '#00843D', '#FFFFFF'),
  ('Montgomery County', 'Kilmichael',   33.44470, -89.57507, 'Hornets',  'Green',      'Gold',           '#00843D', '#FFC72C'),
  ('Ray Brooks',        'Benoit',       33.63569, -91.02846, 'Tigers',   'Red',        'White',          '#C8102E', '#FFFFFF'),
  ('Hickory Flat',      'Hickory Flat', 34.61371, -89.19164, 'Rebels',   'Red',        'White and blue', '#C8102E', '#FFFFFF, #0033A0'),
  ('Coldwater',         'Coldwater',    34.68355, -89.97447, 'Cougars',  'Royal blue', 'Gold',           '#003DA5', '#FFC72C'),
  ('Coahoma AHS',       'Clarksdale',   34.25211, -90.56776, 'Tigers',   'Maroon',     'White',          '#800000', '#FFFFFF'),
  ('Coahoma Early College', 'Clarksdale', 34.25211, -90.56776, 'Tigers', 'Maroon',     'White',          '#800000', '#FFFFFF'),
  ('East Side',         'Cleveland',    33.73816, -90.71147, 'Trojans',  'Black',      'Gold',           '#000000', '#FFC72C'),
  ('Madison St. Joseph', 'Madison',     32.47478, -90.14645, 'Bruins',   'Navy blue',  'Gold',           '#0C2340', '#FFC72C'),
  ('Wingfield',         'Jackson',      32.28215, -90.24142, 'Falcons',  'Royal blue', 'Gold',           '#003DA5', '#FFC72C')
ON CONFLICT (school) DO NOTHING;

-- On another school's campus: Bassfield (Jefferson Davis County's), Benton County (Ashland's), Broad
-- Street (Northside's), Cleveland (Cleveland Central's).
INSERT INTO schools (school, city, latitude, longitude, mascot, primary_color, secondary_color, primary_color_hex, secondary_color_hex)
SELECT v.school, v.city, s.latitude, s.longitude, v.mascot, v.primary_color, v.secondary_color, v.primary_hex, v.secondary_hex
FROM (VALUES
  ('Bassfield',     'Bassfield', 'Jefferson Davis County', 'Yellow Jackets', 'Black', 'Gold',   '#000000', '#FFC72C'),
  ('Benton County', 'Ashland',   'Ashland',                'Buccaneers',     'Black', 'Silver', '#000000', '#A2AAAD'),
  ('Broad Street',  'Shelby',    'Northside',              'Jaguars',        'Blue',  'Gold',   '#0033A0', '#FFC72C'),
  ('Cleveland',     'Cleveland', 'Cleveland Central',      'Wildcats',       'Black', 'Gold',   '#000000', '#FFC72C')
) AS v(school, city, campus, mascot, primary_color, secondary_color, primary_hex, secondary_hex)
LEFT JOIN schools_effective s ON s.school = v.campus
ON CONFLICT (school) DO NOTHING;

-- Former names: McEvans (Shaw, 2020-22) has Shaw's town, campus and look; Ruleville Central (Thomas E.
-- Edwards before 2019) has its town and campus (its mascot and colors then aren't known).
INSERT INTO schools (school, city, zip, latitude, longitude, mascot, primary_color, secondary_color, primary_color_hex, secondary_color_hex)
SELECT 'McEvans', city, zip, latitude, longitude, mascot, primary_color, secondary_color, primary_color_hex, secondary_color_hex
FROM schools_effective WHERE school = 'Shaw'
ON CONFLICT (school) DO NOTHING;

INSERT INTO schools (school, city, zip, latitude, longitude)
SELECT 'Ruleville Central', city, zip, latitude, longitude
FROM schools_effective WHERE school = 'Thomas E. Edwards'
ON CONFLICT (school) DO NOTHING;
