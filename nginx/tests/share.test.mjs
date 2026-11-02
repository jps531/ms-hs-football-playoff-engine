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

import {
  regionModes, regionShareDefaults, regionImagePath, regionImageName, regionImageLabel,
} from "../html/static/js/share.js";

test("regionModes: Toss-up always, Projected only while there are Projected odds", () => {
  assert.deepEqual(regionModes({ projectedAvailable: true }), ["projected", "tossup"]);
  assert.deepEqual(regionModes({ projectedAvailable: false }), ["tossup"]);
});

test("regionShareDefaults: the overview, in the page's odds mode and theme", () => {
  const both = ["projected", "tossup"];
  assert.deepEqual(regionShareDefaults({ mode: "tossup", modes: both, dark: true }), { image: "overview", mode: "tossup", theme: "dark" });
  assert.deepEqual(regionShareDefaults({ mode: "projected", modes: ["tossup"], dark: false }), { image: "overview", mode: "tossup", theme: "light" });
});

test("a region image's address, file name and label", () => {
  const c = { image: "overview", mode: "projected", theme: "dark" };
  assert.equal(regionImagePath(2026, 3, 6, c), "/static/region/2026/3a-6-overview-projected-dark.png");
  assert.equal(regionImageName(2026, 3, 6, c), "region-6-3a-overview-2026.png");
  assert.equal(regionImageName(2026, 3, 6, { ...c, mode: "tossup" }), "region-6-3a-overview-2026-tossup.png");
  assert.equal(regionImageLabel(3, 6, c), "Region 6-3A overview, with Projected odds");
  assert.equal(regionImageLabel(3, 6, { ...c, mode: "tossup" }), "Region 6-3A overview, with Toss-up odds");
});

import { regionIndexPath, regionPages, regionImages } from "../html/static/js/share.js";

test("a region's index: which images it has, and how many pages each", () => {
  assert.equal(regionIndexPath(2026, 3, 6), "/static/region/2026/3a-6.json");
  const index = {
    overview: { "projected-dark": 1, "tossup-dark": 1 },
    scenarios: { "projected-dark": 3, "tossup-dark": 0 },
  };
  const c = { image: "scenarios", mode: "projected", theme: "dark" };
  assert.equal(regionPages(index, c), 3);
  assert.equal(regionPages(index, { ...c, mode: "tossup" }), 0);
  assert.deepEqual(regionImages(index, c).map((i) => i.key), ["overview", "scenarios"]);
  assert.deepEqual(regionImages(index, { ...c, mode: "tossup" }).map((i) => i.key), ["overview"]);
  // Without an index (not written yet): the overview alone.
  assert.equal(regionPages(null, { ...c, image: "overview" }), 1);
  assert.deepEqual(regionImages(null, c).map((i) => i.key), ["overview"]);
});

test("a page of several: its own address and file name", () => {
  const c = { image: "scenarios", mode: "tossup", theme: "light" };
  assert.equal(regionImagePath(2026, 6, 2, c, 2, 3), "/static/region/2026/6a-2-scenarios-tossup-light-2.png");
  assert.equal(regionImagePath(2026, 6, 2, c, 1, 1), "/static/region/2026/6a-2-scenarios-tossup-light.png");
  assert.equal(regionImageName(2026, 6, 2, c, 2, 3), "region-2-6a-scenarios-2026-tossup-2.png");
  assert.equal(regionImageLabel(6, 2, c), "Region 2-6A scenarios, with Toss-up odds");
});
