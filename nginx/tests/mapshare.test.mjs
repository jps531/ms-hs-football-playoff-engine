import { test } from "node:test";
import assert from "node:assert/strict";
import { MAP_VIEWS, countiesShareModel, regionsShareModel } from "../html/static/js/mapshare.js";

// Three choices of regions, as regions/index.json has them: 2027 (2027 and 2028), 2026 and 2025.
const INDEX = {
  default: 2027,
  options: [
    { season: 2027, seasons: [2027, 2028], label: "2027 and 2028" },
    { season: 2026, seasons: [2026], label: "2026" },
    { season: 2025, seasons: [2025], label: "2025" },
  ],
};
const row = (school, clazz, region, county = "Lee") => ({ school, slug: school.toLowerCase().replace(/\s+/g, "-"), class: clazz, region, county });
// Tupelo is 7A throughout; Pearl leaves 7A after 2026; Newcomer is new in 2027; Oldie stops after 2025.
const PAYLOADS = {
  2027: { schools: [row("Tupelo", 7, 1), row("Newcomer", 7, 2, "Hinds"), row("Pearl", 6, 3, "Rankin")] },
  2026: { schools: [row("Tupelo", 7, 1), row("Pearl", 7, 3, "Rankin")] },
  2025: { schools: [row("Tupelo", 7, 1), row("Pearl", 7, 3, "Rankin"), row("Oldie", 7, 2, "Hinds")] },
};
const regions = () => regionsShareModel(INDEX, PAYLOADS, [7]);
const choice = (c) => ({ subject: "class:7", view: "season", season: "2027", theme: "light", ...c });

test("the Maps sheet: the class, then every team that was ever in it, by name", () => {
  assert.deepEqual(regions().subjects.map((s) => s.label), ["Class 7A, every region", "Newcomer", "Oldie", "Pearl", "Tupelo"]);
  assert.deepEqual(MAP_VIEWS.map((v) => v.label), ["One season", "Compare", "Timeline"]);
  // Compare's two classes: both, and both classes' teams.
  assert.deepEqual(regionsShareModel(INDEX, PAYLOADS, [7, 6]).subjects.slice(0, 2).map((s) => s.key), ["class:7", "class:6"]);
});

test("the Season row: each season, each season against the one before, or every season", () => {
  const m = regions();
  assert.deepEqual(m.seasons(choice()).map((o) => o.label), ["2027 and 2028", "2026", "2025"]);
  assert.deepEqual(m.seasons(choice({ view: "compare" })).map((o) => o.label), ["2026 vs. 2027 and 2028", "2025 vs. 2026"]);
  assert.deepEqual(m.seasons(choice({ view: "timeline" })).map((o) => o.label), ["Every season, 2025 to 2028"]);
  assert.equal(m.when(choice({ view: "timeline" })), "2025 to 2028 seasons");
  assert.equal(m.when(choice({ view: "compare" })), "2026 vs. 2027 and 2028");
  assert.equal(m.when(choice()), "2027 and 2028 seasons");
});

test("a season a team has no image for is greyed out, with a note, and a choice moves to one it has", () => {
  const m = regions();
  const newcomer = choice({ subject: "team:Newcomer" });
  assert.deepEqual(m.seasons(newcomer).map((o) => o.disabled), [false, true, true]);
  assert.match(m.seasonNote(newcomer), /Newcomer wasn’t in an MHSAA region in 2026 or 2025/);
  assert.match(m.viewNote(newcomer), /Newcomer wasn’t in an MHSAA region in two seasons in a row/);
  // No season before 2027 to compare against: Compare is greyed out, and a choice of it moves on.
  assert.equal(m.viewOptions(newcomer).find((v) => v.key === "compare").disabled, true);
  assert.deepEqual(m.fix({ ...newcomer, view: "compare" }).view, "season");
  // Oldie's only season is 2025: a choice of 2027 moves to it.
  assert.equal(m.fix(choice({ subject: "team:Oldie" })).season, "2025");
  // Pearl left 7A, but its 2027 map (in 6A) and its 2026 vs. 2027 comparison are drawn.
  assert.deepEqual(m.seasons(choice({ subject: "team:Pearl", view: "compare" })).map((o) => o.disabled), [false, false]);
});

test("each choice names the file the share-assets step draws, and its page", () => {
  const m = regions();
  assert.equal(m.file(choice()), "2027/7a");
  assert.equal(m.file(choice({ view: "compare" })), "2027/compare/7a");
  assert.equal(m.file(choice({ view: "timeline" })), "timeline/7a");
  assert.equal(m.file(choice({ subject: "team:Tupelo", season: "2026" })), "2026/team/tupelo");
  assert.equal(m.file(choice({ subject: "team:Tupelo", view: "compare" })), "2027/compare/tupelo");
  assert.equal(m.file(choice({ subject: "team:Tupelo", view: "timeline" })), "timeline/team/tupelo");
  assert.equal(m.name(choice({ subject: "team:Tupelo", view: "compare" })), "tupelo-regions-2026-vs-2027");
  assert.equal(m.label(choice({ subject: "team:Tupelo", season: "2026" })), "Tupelo: Region 1-7A, 2026");
  assert.equal(m.title(choice({ subject: "team:Tupelo" })), "Share Tupelo’s regions");
  assert.equal(m.page(choice()), "/maps/regions/7a");
  assert.equal(m.page(choice({ subject: "team:Tupelo", view: "compare", season: "2026" })), "/maps/regions/7a/compare?season=2026&team=tupelo");
  // A team's map is its class's that season: Pearl in 2027 is on 6A's.
  assert.equal(m.page(choice({ subject: "team:Pearl" })), "/maps/regions/6a?team=pearl");
  assert.equal(m.page(choice({ view: "timeline" })), "/maps/regions/7a/timeline");
});

test("the Counties sheet: every county (one season only), or a county's season, comparison or timeline", () => {
  const m = countiesShareModel(INDEX, PAYLOADS, ["Hinds", "Lee", "Rankin", "Tishomingo"]);
  // Counties with a school in some season (Tishomingo has none here).
  assert.deepEqual(m.subjects.map((s) => s.label), ["Every county", "Hinds County", "Lee County", "Rankin County"]);
  const all = { subject: "all", view: "season", season: "2027", theme: "dark" };
  assert.deepEqual(m.viewOptions(all).map((v) => v.disabled), [false, true, true]);
  assert.match(m.viewNote(all), /drawn for each county/);
  assert.equal(m.seasonNote(all), "");
  assert.equal(m.file(all), "2027/counties");
  assert.equal(m.fix({ ...all, view: "timeline" }).view, "season");
  // Hinds: schools in 2025 and 2027, none in 2026. Its 2026 is greyed out; both comparisons are drawn
  // (a county is compared when it had a school in either season).
  const hinds = { ...all, subject: "county:Hinds" };
  assert.deepEqual(m.seasons(hinds).map((o) => o.disabled), [false, true, false]);
  assert.match(m.seasonNote(hinds), /Hinds County had no MHSAA school in 2026/);
  assert.equal(m.viewNote(hinds), "");
  assert.deepEqual(m.seasons({ ...hinds, view: "compare" }).map((o) => o.disabled), [false, false]);
  assert.equal(m.file({ ...hinds, view: "compare" }), "2027/county-compare/hinds");
  assert.equal(m.file({ ...hinds, view: "timeline" }), "timeline/county/hinds");
  assert.equal(m.name({ ...hinds, view: "compare" }), "hinds-county-2026-vs-2027");
  assert.equal(m.title(hinds), "Share Hinds County");
  assert.equal(m.page({ ...hinds, view: "compare", season: "2026" }), "/maps/counties/hinds/compare?season=2026");
});
