import { test } from "node:test";
import assert from "node:assert/strict";
import { compareChanges, compareChangesHtml, hoverHtml, hoverSpot, keepInView, mapsViews, nameIn, notOnMapHtml, pickedHtml, placeLabels, regionView, regionsLists, namesIn, timelineSeasons, timelineTable, timelineSpan, wholeView } from "../html/static/js/regions.js";
import * as regions from "../html/static/js/regions.js";

const BASE = { width: 3324, height: 5355 };
const TIP = { w: 100, h: 24 };
const FRAME = { w: 400, h: 640 };

test("the whole view has room around the state, in the state's shape", () => {
  const v = wholeView(BASE);
  assert.ok(v.x < 0 && v.y < 0 && v.x + v.w > BASE.width && v.y + v.h > BASE.height);
  assert.ok(Math.abs(v.w / v.h - BASE.width / BASE.height) < 1e-9);
  // A region's view never shows more than the whole view.
  const r = regionView([0, 0, BASE.width, BASE.height], BASE);
  assert.ok(r.w <= v.w + 1e-9 && r.h <= v.h + 1e-9);
});

test("a dot's name goes above it, below it near the top, and stays inside the map at the sides", () => {
  assert.deepEqual(hoverSpot(200, 300, 11, TIP, FRAME), { left: 150, top: 300 - 11 - 6 - 24 });
  assert.deepEqual(hoverSpot(200, 20, 11, TIP, FRAME), { left: 150, top: 20 + 11 + 6 });
  assert.equal(hoverSpot(10, 300, 11, TIP, FRAME).left, 4);
  assert.equal(hoverSpot(395, 300, 11, TIP, FRAME).left, 400 - 100 - 4);
});

const PAYLOAD = {
  prior_season: 2026,
  schools: [
    { school: "Bay", slug: "bay", class: 4, region: 8, city: "Bay St. Louis", county: "Hancock", before: { class: 4, region: 8 } },
    { school: "Moss Point", slug: "moss-point", class: 4, region: 8, city: "Moss Point", county: "Jackson", before: null },
    { school: "Greene County", slug: "greene-county", class: 4, region: 8, city: "Leakesville", county: "Greene", before: null },
    { school: "Corinth", slug: "corinth", class: 4, region: 1, city: "Corinth", county: "Alcorn", before: null },
    { school: "Pass Christian", slug: "pass-christian", class: 5, region: 8, city: "Pass Christian", county: "Harrison", before: null },
  ],
};

test("a picked team's details: its name and region, where it is, and its region's other schools by name", () => {
  const html = pickedHtml(PAYLOAD.schools[0], PAYLOAD);
  assert.match(html, /<span class="picked__name">Bay<\/span>/);
  assert.match(html, /<strong>Region 8-4A<\/strong>/);
  assert.match(html, /Bay St\. Louis, Hancock County · Also Region 8-4A in 2026/);
  const others = [...html.matchAll(/data-team="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(others, ["greene-county", "moss-point"]); // not Bay, Region 1 or another class's Region 8
  assert.match(html, /href="\/maps\/regions\/4a\?team=moss-point"/);
});

test("a team alone in its region lists no others", () => {
  assert.doesNotMatch(pickedHtml(PAYLOAD.schools[3], PAYLOAD), /picked__others/);
});

test("a region's name isn't a link; its standings, when it has some, are a link of their own", () => {
  const played = regionsLists(4, { ...PAYLOAD, standings_season: 2026 }, 2026);
  assert.match(played, /<h2 class="regions-list__name">[^]*?Region 8<\/h2>/);
  assert.doesNotMatch(played, /<h2[^>]*>(?:(?!<\/h2>)[^])*<a /);
  assert.match(played, /<a class="regions-list__standings" href="\/standings\/4a\/8"><span class="visually-hidden">Region 8 <\/span>2026 standings/);
  assert.doesNotMatch(regionsLists(4, { ...PAYLOAD, standings_season: null }, 2026), /regions-list__standings/);
});

test("the map can't be dragged away from the state: the view's middle stays over it", () => {
  const view = { x: 0, y: 0, w: 400, h: 600 };
  assert.deepEqual(keepInView({ ...view, x: 100, y: 200 }, BASE), { x: 100, y: 200 }); // over the state: left as is
  assert.deepEqual(keepInView({ ...view, x: -5000, y: -9000 }, BASE), { x: -200, y: -300 }); // dragged off: back to its corner
  assert.deepEqual(keepInView({ ...view, x: 9000, y: 9000 }, BASE), { x: BASE.width - 200, y: BASE.height - 300 });
  // The whole view (wider than the state) stays where it is.
  const whole = wholeView(BASE);
  const kept = keepInView(whole, BASE);
  assert.ok(Math.abs(kept.x - whole.x) < 1e-9 && Math.abs(kept.y - whole.y) < 1e-9);
});

// Two seasons of one class, for Compare (2025, before Leake Central's rename, and 2027): Bay changes region, Moss Point moves up into 4A, Corinth moves
// down out of it, Leake Central is renamed Leake (and stays put), Walnut closes into North Tippah (a new
// school, in 3A), Greene County stays put.
const OLD = { season: 2025, label: "2025", clazz: 4, payload: { schools: [
  { school: "Bay", slug: "bay", class: 4, region: 7 },
  { school: "Moss Point", slug: "moss-point", class: 3, region: 8 },
  { school: "Corinth", slug: "corinth", class: 4, region: 1 },
  { school: "Leake Central", slug: "leake-central", class: 4, region: 5 },
  { school: "Walnut", slug: "walnut", class: 4, region: 2 },
  { school: "Greene County", slug: "greene-county", class: 4, region: 8 },
] } };
const NEW = { season: 2027, label: "2027 and 2028", clazz: 4, payload: { schools: [
  { school: "Bay", slug: "bay", class: 4, region: 8 },
  { school: "Moss Point", slug: "moss-point", class: 4, region: 8 },
  { school: "Corinth", slug: "corinth", class: 3, region: 1 },
  { school: "Leake", slug: "leake", class: 4, region: 5 },
  { school: "North Tippah", slug: "north-tippah", class: 3, region: 2, successor_of: "Walnut" },
  { school: "Greene County", slug: "greene-county", class: 4, region: 8 },
] } };

test("a renamed school keeps its place across seasons, under the name each season knows it by", () => {
  assert.equal(nameIn("Leake Central", 2025, 2027), "Leake");
  assert.equal(nameIn("Leake", 2027, 2025), "Leake Central");
  assert.equal(nameIn("Leake", 2026, 2027), "Leake");
  assert.equal(nameIn("Bay", 2026, 2027), "Bay");
});

test("what changed between two maps, in either order: moved in, moved out, changed region, same region", () => {
  for (const [a, b] of [[OLD, NEW], [NEW, OLD]]) {
    const { older, newer, groups } = compareChanges(a, b);
    assert.equal(older.season, 2025);
    assert.equal(newer.season, 2027);
    const names = (k) => groups[k].map((r) => r.school);
    assert.deepEqual(names("in"), ["Moss Point"]);
    assert.deepEqual(names("out"), ["Corinth", "Walnut"]);
    assert.deepEqual(names("moved"), ["Bay"]);
    assert.deepEqual(names("same"), ["Greene County", "Leake"]);
  }
  assert.equal(compareChanges(NEW, { ...NEW, clazz: 3 }), null); // the same season: nothing changed
});

test("what changed, as it reads: which way a school moved, and where a closed one went", () => {
  const html = compareChangesHtml(compareChanges(OLD, NEW));
  assert.match(html, /What changed from 2025 4A to 2027 and 2028 4A/);
  assert.match(html, /Moved into 4A/);
  assert.match(html, /Moss Point<\/span><span class="compare-changes__detail">Moved up from Region 8-3A in 2025/);
  assert.match(html, /Corinth<\/span><span class="compare-changes__detail">Moved down to Region 1-3A in 2027 and 2028/);
  assert.match(html, /Walnut<\/span><span class="compare-changes__detail">Now part of North Tippah/);
  assert.match(html, /Bay<\/span><span class="compare-changes__detail">Region 7-4A → Region 8-4A/);
  assert.match(html, /<details class="compare-changes__group"><summary><h3>Same region/);
  // Each school picks itself on both maps, by its name in its season.
  assert.match(html, /data-school="Walnut" data-season="2025"/);
  assert.match(html, /data-school="Bay" data-season="2027"/);
  assert.match(compareChangesHtml(null), /same season/);
});

test("the views every map page has, the one shown marked", () => {
  const html = mapsViews("compare", {
    map: "/maps/regions/4a?team=bay", compare: "/maps/regions/4a/compare?team=bay", timeline: "/maps/regions/4a/timeline?team=bay",
  });
  assert.match(html, /href="\/maps\/regions\/4a\?team=bay">Season<\/a>/);
  assert.match(html, /href="\/maps\/regions\/4a\/compare\?team=bay" aria-current="page">Compare<\/a>/);
  assert.match(html, /href="\/maps\/regions\/4a\/timeline\?team=bay">Timeline<\/a>/);
});

test("a team picked on one map says where it is when it isn't on the other", () => {
  assert.match(notOnMapHtml("Corinth", { class: 3, region: 1 }, "2027 and 2028"), /Corinth<\/strong> isn’t on this map: Region 1-3A in 2027 and 2028\./);
  assert.match(notOnMapHtml("Walnut", null, "2027 and 2028"), /not in a region in 2027 and 2028/);
});

test("the timeline: every season, oldest first, each in the class a followed team was in then", () => {
  const options = [{ season: 2027, seasons: [2027, 2028], label: "2027 and 2028" }, { season: 2025, seasons: [2025], label: "2025" }]; // newest first, as index.json
  const payloads = [NEW.payload, OLD.payload];
  // No team: every map is the page's class.
  assert.deepEqual(timelineSeasons(options, payloads, 4).map((s) => [s.option.season, s.clazz, s.row]), [[2025, 4, null], [2027, 4, null]]);
  assert.equal(timelineSpan(timelineSeasons(options, payloads, 4)), "2025 to 2028 seasons");
  assert.equal(timelineSpan(timelineSeasons(options.slice(1), payloads.slice(1), 4)), "2025 season");
  // Corinth: 4A in 2025, 3A in 2027 and 2028.
  const corinth = timelineSeasons(options, payloads, 4, { name: "Corinth", season: 2027 });
  assert.deepEqual(corinth.map((s) => [s.option.season, s.clazz, s.row.region]), [[2025, 4, 1], [2027, 3, 1]]);
  // Leake, as Leake Central in 2025 (and Leake County, merged into it).
  assert.equal(timelineSeasons(options, payloads, 4, { name: "Leake", season: 2027 })[0].row.school, "Leake Central");
  // North Tippah, before 2027: Walnut (its campus) and Falkner, the map in Walnut's class.
  const tippah = timelineSeasons(options, payloads, 4, { name: "North Tippah", season: 2027 });
  assert.deepEqual(tippah.map((s) => [s.clazz, s.rows.map((r) => r.school)]), [[4, ["Walnut"]], [3, ["North Tippah"]]]);
  const table = timelineTable("North Tippah", tippah);
  assert.match(table, /<th scope="row">2025<\/th><td><span class="timeline-table__place">Walnut: <span class="region-chip region-chip--2"[^>]*>2<\/span>Region 2-4A<\/span><\/td>/);
  // Each school merged into it gets its own line, under one season.
  const both = timelineTable("North Tippah", [{ ...tippah[0], rows: [tippah[0].rows[0], { school: "Falkner", slug: "falkner", class: 3, region: 5 }] }]);
  assert.match(both, /<th scope="row" rowspan="2">2025<\/th><td>[^]*Walnut: [^]*<\/tr><tr><td>[^]*Falkner: [^]*Region 5-3A/);
  assert.match(table, /<th scope="row">2027 and 2028<\/th><td><span class="timeline-table__place"><span class="region-chip region-chip--2"[^>]*>2<\/span>Region 2-3A/);
  // The region's other schools that season, not the team itself.
  assert.match(timelineTable("Corinth", corinth), /2025<\/th>.*?timeline-table__mates"><\/span><\/td>/s);
});

test("a consolidated school's earlier names, and a merged school's later one", () => {
  assert.deepEqual(namesIn("North Tippah", 2027, 2026), ["Walnut", "Falkner"]);
  assert.deepEqual(namesIn("Leake", 2027, 2025), ["Leake Central", "Leake County"]);
  assert.deepEqual(namesIn("Falkner", 2026, 2027), ["North Tippah"]);
  assert.deepEqual(namesIn("Leake County", 2025, 2026), ["Leake"]);
  assert.deepEqual(namesIn("North Tippah", 2027, 2028), ["North Tippah"]);
  assert.deepEqual(namesIn("Bay", 2026, 2027), ["Bay"]);
});

test("schools' names go beside their dots where they overlap nothing, the first in line getting first pick", () => {
  const r = 10;
  const size = 10;
  // Two dots well apart: each name right beside its own dot, no line.
  const spots = placeLabels([{ slug: "a", x: 0, y: 0, name: "Bay" }, { slug: "b", x: 200, y: 0, name: "Moss Point" }], r, size);
  assert.deepEqual(spots.a, { x: 14, y: 0, anchor: "start", line: null });
  assert.deepEqual(spots.b, { x: 214, y: 0, anchor: "start", line: null });
  // At the map's right edge, the name goes left rather than off the map.
  const edge = placeLabels([{ slug: "a", x: 90, y: 50, name: "Greene County" }], r, size, { x0: 0, y0: 0, x1: 100, y1: 100 });
  assert.equal(edge.a.anchor, "end");
  // Boxed in on every side: no name rather than one over a dot.
  const ring = [[0, 0], [25, 0], [-25, 0], [0, 25], [0, -25], [25, 25], [-25, -25], [25, -25], [-25, 25]]
    .map(([x, y], i) => ({ slug: `s${i}`, x, y, name: "Long School Name" }));
  assert.equal(placeLabels(ring, r, size).s0, undefined);
});

test("a name never sits nearer a neighbor's dot than its own (Purvis and Columbia)", () => {
  const r = 10;
  const size = 10;
  // Columbia just up and left of Purvis: Purvis's name can't go left (toward Columbia) or above it.
  const points = [{ slug: "purvis", x: 60, y: 30, name: "Purvis" }, { slug: "columbia", x: 20, y: 10, name: "Columbia" }];
  const spots = placeLabels(points, r, size);
  for (const [slug, own] of [["purvis", points[0]], ["columbia", points[1]]]) {
    const spot = spots[slug];
    const other = points.find((p) => p !== own);
    const w = own.name.length * size * 0.56;
    const x0 = spot.anchor === "start" ? spot.x : spot.anchor === "end" ? spot.x - w : spot.x - w / 2;
    const box = { x0, x1: x0 + w, y0: spot.y - size / 2, y1: spot.y + size / 2 };
    const reach = (q) => Math.hypot(Math.max(box.x0 - q.x, 0, q.x - box.x1), Math.max(box.y0 - q.y, 0, q.y - box.y1));
    assert.ok(reach(other) > reach(own) + r * 2, `${slug}'s name is plainly its own dot's`);
  }
  assert.equal(spots.purvis.anchor, "start"); // right of Purvis, away from Columbia
});

test("a dot's tooltip: helmet, name, mascot, region and town, edged in the team's color", () => {
  const school = { school: "Purvis", slug: "purvis", class: 4, region: 7, city: "Purvis", county: "Lamar" };
  const team = { mascot: "Tornadoes", color_variants: { primary: { raw: "#6B2D8B", light: { ui: "#6B2D8B" }, dark: { ui: "#9356B6" } } } };
  const html = hoverHtml(school, team);
  assert.match(html, /<strong class="map-tip__name">Purvis<\/strong><span class="map-tip__mascot">Tornadoes<\/span>/);
  assert.match(html, /region-chip--7[^>]*>7<\/span><span>Region 7-4A · Purvis, Lamar County<\/span>/);
  assert.match(html, /--team-ui-light:#6B2D8B/);
  // The seasons the map is of, for context.
  assert.match(hoverHtml(school, team, [2027, 2028]), /<span class="map-tip__when">2027 and 2028 seasons<\/span>/);
  assert.doesNotMatch(html, /map-tip__when/);
  // No /teams entry: still the name and region, initials for a helmet, no mascot or color.
  const bare = hoverHtml(school, undefined);
  assert.doesNotMatch(bare, /mascot|--team-ui/);
  assert.match(bare, /Region 7-4A/);
});

// ------------------------------------------------------------- a county's Compare and Timeline

const sch = (school, county, clazz, region, extra = {}) => ({ school, slug: school.toLowerCase().replace(/[^a-z]+/g, "-"), county, class: clazz, region, ...extra });
const LEAKE_2025 = { label: "2025", season: 2025, payload: { schools: [
  sch("Leake Central", "Leake", 4, 5), sch("Leake County", "Leake", 1, 5), sch("Raymond", "Hinds", 4, 6),
] } };
const LEAKE_2026 = { label: "2026", season: 2026, payload: { schools: [sch("Leake", "Leake", 5, 2), sch("Raymond", "Hinds", 4, 6)] } };
const TIPPAH_2026 = { label: "2026", season: 2026, payload: { schools: [
  sch("Walnut", "Tippah", 2, 1), sch("Falkner", "Tippah", 1, 2), sch("Ripley", "Tippah", 4, 3), sch("Gone", "Tippah", 1, 2),
] } };
const TIPPAH_2027 = { label: "2027 and 2028", season: 2027, payload: { schools: [
  sch("North Tippah", "Tippah", 3, 2, { successor_of: "Walnut" }), sch("Ripley", "Tippah", 3, 1),
] } };

test("a county's changes: a merger names the schools it was formed from, in either order of the maps", () => {
  const c = regions.countyChanges(LEAKE_2026, LEAKE_2025, "Leake");
  assert.equal(c.older.season, 2025);
  assert.deepEqual(c.groups.in.map((r) => [r.school, r.note]), [["Leake", "Formed from Leake Central (5-4A) and Leake County (5-1A)"]]);
  assert.deepEqual([c.groups.out.length, c.groups.moved.length, c.groups.same.length], [0, 0, 0]);
  assert.equal(regions.countyChanges(LEAKE_2025, LEAKE_2025, "Leake"), null);
});

test("a county's changes: moved, gone, and a school only in one season", () => {
  const c = regions.countyChanges(TIPPAH_2026, TIPPAH_2027, "Tippah");
  assert.deepEqual(c.groups.moved.map((r) => [r.school, r.older, r.newer]), [["Ripley", { class: 4, region: 3 }, { class: 3, region: 1 }]]);
  assert.deepEqual(c.groups.out.map((r) => [r.school, r.note]), [["Gone", "Not in a region in 2027 and 2028"]]);
  assert.match(c.groups.in[0].note, /^Formed from Walnut \(1-2A\) and Falkner \(2-1A\)$/);
  const html = regions.countyChangesHtml(c, "Tippah");
  assert.match(html, /What changed in Tippah County from 2026 to 2027 and 2028/);
  assert.match(html, /Region 3-4A → Region 1-3A/);
});

test("a county's timeline table: a row a school, a merger said on both ends", () => {
  const seasons = [{ option: { season: 2026, label: "2026" }, payload: TIPPAH_2026.payload }, { option: { season: 2027, label: "2027 and 2028" }, payload: TIPPAH_2027.payload }];
  const html = regions.countyTimelineTable("Tippah", seasons);
  assert.equal((html.match(/<tr><th scope="row">/g) ?? []).length, 5); // Falkner, Gone, North Tippah, Ripley, Walnut
  assert.match(html, /Walnut<\/span><span class="timeline-table__note muted">Part of North Tippah from 2027/);
  assert.match(html, /North Tippah<\/span><span class="timeline-table__note muted">From Walnut and Falkner, 2027/);
  assert.match(html, /class="county-pill"[^>]*>1-3A<\/span><span class="visually-hidden">Region 1-3A<\/span>/);
});

test("a county's nearby counties: each a link with its mark and its count of schools; none without map.json's neighbors", () => {
  const box = "M0 0L10 0L10 10L0 10Z";
  const base = { counties: [
    { name: "Rankin", d: box, neighbors: ["Hinds", "Madison"] },
    { name: "Hinds", d: box, neighbors: ["Rankin"] },
    { name: "Madison", d: box, neighbors: ["Rankin"] },
    { name: "Yazoo", d: box },
  ] };
  const payload = { schools: [{ county: "Hinds" }, { county: "Hinds" }, { county: "Madison" }] };
  const html = regions.countyNearby(base, "Rankin", payload);
  assert.match(html, /href="\/maps\/counties\/hinds" data-county="Hinds" aria-label="Hinds County: 2 MHSAA schools">.*county-mark.*<span>Hinds<\/span>/);
  assert.match(html, /aria-label="Madison County: 1 MHSAA school"/);
  assert.equal(regions.countyNearby(base, "Yazoo", payload), "");
  // Another county tapped on the map: next to this one or not, and a link to it.
  assert.match(regions.countyJumpHtml(base, "Madison", "Rankin", 1), /Madison County<\/span>.*1 MHSAA school · next to Rankin County.*href="\/maps\/counties\/madison"[^>]*>Open Madison County/);
  assert.doesNotMatch(regions.countyJumpHtml(base, "Yazoo", "Rankin", 0), /next to/);
});

test("the Timeline's Older and Newer buttons, hidden until the seasons don't all fit", () => {
  const html = regions.timelineSteps();
  assert.match(html, /^<div class="timeline-steps" role="group" aria-label="Seasons" hidden><button type="button" data-step="-1">.*Older<\/button><button type="button" data-step="1">Newer.*<\/button><\/div>$/);
});
