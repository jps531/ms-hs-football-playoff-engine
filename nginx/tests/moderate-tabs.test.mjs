import { test } from "node:test";
import assert from "node:assert/strict";
import {
  centralLocal, championshipSection, describeOverride, gameChanges, gameForm, gameRow, gameValues, matchup, overridesTable, shortDate, venueRow,
} from "../html/static/js/moderate-tabs.js";

// Shaw at West Bolivar, Oct 9 2025 (its real score); the region game is the region alignment's.
const GAME = {
  date: "2025-10-09", opponent: "West Bolivar", helmet_design_id: null, venue: null, overrides: {},
  base: { points_for: 12, points_against: 6, game_status: "final", round: null, region_game: true, overtime: 0, location: "away", location_id: null, kickoff_time: "2025-10-10T00:00:00+00:00" },
};
const VENUES = [{ id: 4, base: { name: "Example Field", city: "Example", home_team: null, latitude: 33.1, longitude: -89.9 }, overrides: {} }];

test("a game reads from its school's side: its date, at or vs, and its score", () => {
  assert.equal(shortDate("2025-10-09"), "Oct 9");
  assert.equal(matchup("away", "West Bolivar"), "at West Bolivar");
  assert.equal(matchup("home", "Leland"), "vs Leland");
  assert.equal(matchup("neutral", "Leland"), "vs Leland (neutral site)");
  const row = gameRow("Shaw", GAME);
  assert.match(row, /Oct 9<\/span><span>at West Bolivar<\/span><b class="ms-score">12–6<\/b>/);
  assert.match(row, /<span class="ms-tag">Region<\/span>/);
  assert.match(gameRow("Shaw", { ...GAME, base: { ...GAME.base, round: "First Round" } }), /First Round/);
});

test("a kickoff is edited in Central time", () => {
  assert.equal(centralLocal("2025-10-10T00:00:00+00:00"), "2025-10-09T19:00"); // 7 PM CDT
  assert.equal(centralLocal(null), "");
});

test("a game's form shows each field, marks an override with what's stored, and offers only real rounds", () => {
  const over = { ...GAME, overrides: { region_game: "false" } };
  const form = gameForm("Shaw", over, VENUES, []);
  assert.match(form, /Shaw’s points/);
  assert.match(form, /West Bolivar’s points/);
  assert.match(form, /By the region alignment: Yes <span class="ms-tag ms-tag--override">override<\/span>/);
  assert.match(form, /<option value="" selected>Regular season<\/option>/);
  assert.match(form, /name="kickoff_time" value="2025-10-09T19:00"/);
  assert.match(form, /class="fb-submit"/);
  assert.equal(gameValues(over).region_game, "false");
});

test("a game form's changes: a score set, an override cleared back to the stored value, a kickoff in Central", () => {
  const over = { ...GAME, overrides: { region_game: "false" } };
  const values = { ...gameValues(over), points_for: "14", region_game: "true", kickoff_time: "2025-10-09T18:30" };
  assert.deepEqual(gameChanges(over, values), [
    { field: "points_for", value: "14" },
    { field: "region_game", clear: true },
    { field: "kickoff_time", value: "2025-10-09 18:30:00 America/Chicago" },
  ]);
});

test("a venue's row: its town, home team and spot", () => {
  assert.match(venueRow(VENUES[0]), /<b>Example Field<\/b><br><span class="ms-src">Example · 33.1000, -89.9000<\/span>/);
  assert.match(venueRow({ ...VENUES[0], overrides: { home_team: "Shaw" } }), /override.*home of Shaw/s);
});

test("each override says what it's on, opens on its tab, and clears through its endpoint", () => {
  assert.deepEqual(describeOverride({ source: "school:Shaw", key: "mascot", value: "Warriors II" }),
    { what: "School: Shaw", open: "?tab=schools&school=Shaw", clear: "/admin/schools/Shaw/overrides/mascot" });
  assert.deepEqual(describeOverride({ source: "look:7:Shaw", key: "primary_color_hex", value: "#006B3F" }),
    { what: "Past look: Shaw", open: "?tab=schools&school=Shaw", clear: "/admin/looks/7/overrides/primary_color_hex" });
  assert.deepEqual(describeOverride({ source: "location:4", key: "latitude", value: "33.1" }, { 4: "Example Field" }),
    { what: "Venue: Example Field", open: "?tab=venues", clear: "/admin/locations/4/overrides/latitude" });
  const game = describeOverride({ source: "game:St. Andrew’s:2025-10-09", key: "region_game", value: "true" });
  assert.equal(game.what, "Game: St. Andrew’s, Oct 9, 2025");
  assert.equal(game.open, "?tab=games&school=St.%20Andrew%E2%80%99s&season=2025");
  // An opponent correction's record isn't cleared here.
  assert.equal(describeOverride({ source: "game:Shaw:2025-10-09", key: "ahsfhs_opponent", value: "X" }).clear, null);
  assert.match(overridesTable([{ source: "game:Shaw:2025-10-09", key: "ahsfhs_opponent", value: "X" }], {}), /An opponent correction/);
  assert.match(overridesTable([], {}), /No overrides on file/);
});

test("championshipSection: each class's venue and kickoff, and the form to change both", () => {
  const assigned = [{ class_: 1, location_name: "Davis Wade Stadium", kickoff: "2026-12-05T18:00:00Z" }, { class_: 2, location_name: "Davis Wade Stadium", kickoff: null }];
  const venues = [{ base: { name: "Davis Wade Stadium" } }, { base: { name: "Renasant Stadium" } }];
  const html = championshipSection(2026, [2026, 2025], assigned, null, venues);
  assert.match(html, /1A<\/span><span>Davis Wade Stadium · Sat, Dec 5 · 12:00 PM CT<\/span>/);
  assert.match(html, /2A<\/span><span>Davis Wade Stadium<\/span>/);
  assert.match(html, /3A<\/span><span><span class="ms-src">Not set<\/span>/);
  const form = championshipSection(2026, [2026], assigned, "champ-1", venues);
  assert.match(form, /<input type="datetime-local" name="kickoff" value="2026-12-05T12:00">/);
  assert.match(form, /<option value="Davis Wade Stadium" selected>/);
});
