import { test } from "node:test";
import assert from "node:assert/strict";
import { slugify, parseLocation, buildPath } from "../html/static/js/routes.js";

test("team slugs: lowercase, punctuation dropped, words hyphenated", () => {
  assert.equal(slugify("St. Martin"), "st-martin");
  assert.equal(slugify("D'Iberville"), "diberville");
  assert.equal(slugify("St. Andrew’s"), "st-andrews");
  assert.equal(slugify("H. W. Byers"), "h-w-byers");
  assert.equal(slugify("Madison Central"), "madison-central");
});

test("path routes: class, region, landing, and anything else is not found", () => {
  assert.deepEqual(
    (({ page, clazz, region }) => ({ page, clazz, region }))(parseLocation("/standings/3a/6", "")),
    { page: "region", clazz: 3, region: 6 },
  );
  assert.equal(parseLocation("/standings/7A", "").clazz, 7); // case-insensitive
  assert.equal(parseLocation("/standings/7a/", "").page, "class"); // trailing slash
  assert.equal(parseLocation("/", "").page, "landing");
  for (const bad of ["/standings/8a", "/standings/3a/x", "/standings/3a/6/extra", "/brackets/9a", "/brackets/3a/6", "/nope"]) {
    assert.equal(parseLocation(bad, "").page, "notfound", bad);
  }
});

test("view state comes from the query", () => {
  const r = parseLocation("/standings/3a/6", "?season=2025&week=9&odds=tossup&team=st-martin");
  assert.deepEqual([r.season, r.week, r.odds, r.team], [2025, 9, "tossup", "st-martin"]);
  assert.equal(parseLocation("/standings/3a", "?odds=bogus&week=-1").odds, null);
  assert.equal(parseLocation("/standings/3a", "?week=-1").week, null);
});

test("old query-string links are read as the page they meant", () => {
  const r = parseLocation("/", "?season=2026&class=7&region=2&team=Oxford");
  assert.deepEqual([r.page, r.clazz, r.region, r.season, r.team, r.legacy], ["region", 7, 2, 2026, "Oxford", true]);
  assert.equal(parseLocation("/", "?class=3").page, "class");
  assert.equal(parseLocation("/", "?class=9").page, "landing"); // not a class: just the landing page
});

test("canonical URLs leave defaults out", () => {
  const base = { page: "region", clazz: 3, region: 6, season: null, week: null, odds: null, team: null };
  assert.equal(buildPath(base, { currentSeason: 2026 }), "/standings/3a/6");
  assert.equal(buildPath({ ...base, season: 2026, odds: "projected" }, { currentSeason: 2026 }), "/standings/3a/6");
  assert.equal(
    buildPath({ ...base, season: 2025, week: 9, odds: "tossup", team: "st-martin" }, { currentSeason: 2026 }),
    "/standings/3a/6?season=2025&week=9&odds=tossup&team=st-martin",
  );
  assert.equal(buildPath({ ...base, page: "class" }, { currentSeason: 2026 }), "/standings/3a");
  assert.equal(buildPath({ ...base, page: "landing", odds: "tossup" }, { currentSeason: 2026 }), "/?odds=tossup");
});

test("a canonical URL reads back as the same route", () => {
  const url = "/standings/5a/2?season=2025&week=4&odds=tossup&team=leake-central";
  const [path, search] = url.split("?");
  const r = parseLocation(path, `?${search}`);
  assert.equal(buildPath(r, { currentSeason: 2026 }), url);
});

test("bracket pages: /brackets/{class}, sharing the view-state query", () => {
  const r = parseLocation("/brackets/3a", "?odds=tossup&team=st-martin");
  assert.deepEqual([r.page, r.clazz, r.odds, r.team], ["bracket", 3, "tossup", "st-martin"]);
  assert.equal(buildPath({ ...r, season: null, week: null }, { currentSeason: 2026 }), "/brackets/3a?odds=tossup&team=st-martin");
});
