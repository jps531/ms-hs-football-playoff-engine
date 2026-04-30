-- Geographic data for schools not reachable by the NCES pipeline:
-- private/parochial schools (not in the NCES public school dataset)
-- and Enterprise Lincoln (ambiguous name shared with Enterprise Clarke).
--
-- Run once after the AHSFHS schedule pipeline has populated the schools table.
-- Safe to re-run (updates are idempotent).

UPDATE schools SET city = 'Brookhaven',    zip = 39601, latitude =  31.473294, longitude =  -90.384857 WHERE school = 'Enterprise Lincoln';
UPDATE schools SET city = 'Hattiesburg',   zip = 39401, latitude =  31.285334, longitude =  -89.311145 WHERE school = 'Presbyterian Christian';
UPDATE schools SET city = 'Pascagoula',    zip = 39567, latitude =  30.366031, longitude =  -88.559577 WHERE school = 'Resurrection';
UPDATE schools SET city = 'Hattiesburg',   zip = 39401, latitude =  31.322615, longitude =  -89.294269 WHERE school = 'Sacred Heart';
UPDATE schools SET city = 'Shaw',          zip = 38773, latitude =  33.598529, longitude =  -90.771071 WHERE school = 'Shaw';
UPDATE schools SET city = 'Ridgeland',     zip = 39157, latitude =  32.433642, longitude =  -90.152878 WHERE school = 'St. Andrew' || chr(8217) || 's';
UPDATE schools SET city = 'Biloxi',        zip = 39532, latitude =  30.551911, longitude =  -89.020895 WHERE school = 'St. Patrick';
UPDATE schools SET city = 'Bay St. Louis', zip = 39520, latitude =  30.306702, longitude =  -89.329070 WHERE school = 'St. Stanislaus';
UPDATE schools SET city = 'Belden',        zip = 38826, latitude =  34.309487, longitude =  -88.795701 WHERE school = 'Tupelo Christian';
