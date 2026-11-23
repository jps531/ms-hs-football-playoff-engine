import { test } from "node:test";
import assert from "node:assert/strict";
import { compareChanges, compareChangesHtml, hoverSpot, keepInView, mapsViews, nameIn, notOnMapHtml, pickedHtml, regionsLists, regionView, wholeView } from "../html/static/js/regions.js";

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
  const html = mapsViews("compare", { map: "/maps/regions/4a?team=bay", compare: "/maps/regions/4a/compare?team=bay" });
  assert.match(html, /href="\/maps\/regions\/4a\?team=bay">Season<\/a>/);
  assert.match(html, /href="\/maps\/regions\/4a\/compare\?team=bay" aria-current="page">Compare<\/a>/);
});

test("a team picked on one map says where it is when it isn't on the other", () => {
  assert.match(notOnMapHtml("Corinth", { class: 3, region: 1 }, "2027 and 2028"), /Corinth<\/strong> isn’t on this map: Region 1-3A in 2027 and 2028\./);
  assert.match(notOnMapHtml("Walnut", null, "2027 and 2028"), /not in a region in 2027 and 2028/);
});
