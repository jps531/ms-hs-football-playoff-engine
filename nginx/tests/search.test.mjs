import { test } from "node:test";
import assert from "node:assert/strict";
import { matchTeams, normalize } from "../html/static/js/search.js";

const T = ["Oxford", "West Oxford", "Oxford Christian", "Saltillo", "Box Elder", "St. Martin", "Lake Cormorant"]
  .map((school) => ({ school }));

test("exact match first, then prefix, then word start, then anywhere", () => {
  assert.deepEqual(matchTeams(T, "oxford").map((t) => t.school), ["Oxford", "Oxford Christian", "West Oxford"]);
  assert.deepEqual(matchTeams(T, "ox").map((t) => t.school), ["Oxford", "Oxford Christian", "West Oxford", "Box Elder"]);
});

test("case, punctuation, and extra spaces don't matter", () => {
  assert.deepEqual(matchTeams(T, "  ST  martin").map((t) => t.school), ["St. Martin"]);
  assert.equal(normalize("Ste. Geneviève"), "ste genevieve");
});

test("an empty query or no match suggests nothing; the list is capped", () => {
  assert.deepEqual(matchTeams(T, "   "), []);
  assert.deepEqual(matchTeams(T, "zzz"), []);
  assert.equal(matchTeams(T, "o", 3).length, 3);
});
