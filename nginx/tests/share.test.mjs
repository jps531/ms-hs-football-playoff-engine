import { test } from "node:test";
import assert from "node:assert/strict";
import {
  shareVersions, shareDefaults, bracketImagePath, bracketImageName, bracketImageLabel,
} from "../html/static/js/share.js";

test("shareVersions: a Projected image only while there are Projected odds and the season is on", () => {
  assert.deepEqual(shareVersions({ projectedAvailable: true, final: false, pastSeason: false }), ["odds", "blank"]);
  assert.deepEqual(shareVersions({ projectedAvailable: false, final: false, pastSeason: false }), ["blank"]);
  assert.deepEqual(shareVersions({ projectedAvailable: true, final: true, pastSeason: false }), ["blank"]);
  assert.deepEqual(shareVersions({ projectedAvailable: true, final: false, pastSeason: true }), ["blank"]);
});

test("shareDefaults: the half on screen, the page's odds (Toss-up has no image: blank), its theme", () => {
  const both = ["odds", "blank"];
  assert.deepEqual(shareDefaults({ half: "N", mode: "projected", versions: both, dark: true }), { view: "north", version: "odds", theme: "dark" });
  assert.deepEqual(shareDefaults({ half: "S", mode: "tossup", versions: both, dark: false }), { view: "south", version: "blank", theme: "light" });
  assert.deepEqual(shareDefaults({ half: "both", mode: "projected", versions: ["blank"], dark: false }), { view: "all", version: "blank", theme: "light" });
});

test("the image's address, file name and label", () => {
  const c = { view: "north", version: "odds", theme: "dark" };
  assert.equal(bracketImagePath(2026, 3, c), "/static/bracket/2026/3a-north-odds-dark.png");
  assert.equal(bracketImageName(2026, 3, c), "class-3a-bracket-north-2026.png");
  assert.equal(bracketImageName(2025, 6, { view: "all", version: "blank" }), "class-6a-bracket-2025-blank.png");
  assert.equal(bracketImageLabel(3, c), "Class 3A Bracket, North half, with Projected odds");
  assert.equal(bracketImageLabel(3, { view: "all", version: "blank" }), "Class 3A Bracket");
});
