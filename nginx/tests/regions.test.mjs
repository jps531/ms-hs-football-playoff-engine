import { test } from "node:test";
import assert from "node:assert/strict";
import { hoverSpot, keepInView, pickedHtml, regionsLists, regionView, wholeView } from "../html/static/js/regions.js";

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
  assert.match(html, /href="\/regions\/4a\?team=moss-point"/);
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
