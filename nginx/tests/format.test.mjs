import { test } from "node:test";
import assert from "node:assert/strict";
import {
  formatPct, oddsBucket, initials, marginText, joinNames, recordText, contrastRatio, clampToSurface,
  teamUiColors, inkFor, escapeHtml,
} from "../html/static/js/format.js";

test("0% and 100% are reserved for certainty", () => {
  assert.equal(formatPct(0), "0%");
  assert.equal(formatPct(1), "100%");
  assert.equal(formatPct(1.0000000000000027), "100%");
  assert.equal(formatPct(3e-17), "0%");
});

test("near-certain values never round to 0% or 100%", () => {
  assert.equal(formatPct(0.004), "<1%");
  assert.equal(formatPct(0.0049), "<1%");
  assert.equal(formatPct(0.996), ">99%");
  assert.equal(formatPct(0.995), ">99%"); // would round to 100
  assert.equal(formatPct(0.005), "1%");
  assert.equal(formatPct(0.994), "99%");
  assert.equal(formatPct(0.646), "65%");
  assert.equal(formatPct(null), "—");
});

test("odds bucket follows the displayed, rounded value", () => {
  assert.equal(oddsBucket(0.794), 4); // shows 79%
  assert.equal(oddsBucket(0.796), 5); // shows 80%
  assert.equal(oddsBucket(0.195), 2); // shows 20%
  assert.equal(oddsBucket(0.194), 1); // shows 19%
  assert.equal(oddsBucket(0), 1);
  assert.equal(oddsBucket(0.001), 1);
  assert.equal(oddsBucket(0.999), 5);
  assert.equal(oddsBucket(1), 5);
  assert.equal(oddsBucket(0.6), 4);
});

test("initials drop County / High / School / Academy, two letters max", () => {
  assert.equal(initials("Wilkinson County"), "W");
  assert.equal(initials("Oak Grove"), "OG");
  assert.equal(initials("Enterprise Clarke"), "EC");
  assert.equal(initials("Jefferson Davis County"), "JD");
  assert.equal(initials("Presbyterian Christian School"), "PC");
  assert.equal(initials("Raleigh"), "R");
});

test("margin text supports thresholds and bounded ranges", () => {
  assert.equal(marginText(1, null), "");
  assert.equal(marginText(undefined, undefined), "");
  assert.equal(marginText(11, null), " by 11+");
  assert.equal(marginText(8, 11), " by 8–10"); // max is exclusive
  assert.equal(marginText(1, 8), " by 1–7");
  assert.equal(marginText(7, 8), " by exactly 7");
});

test("names join newspaper-style", () => {
  assert.equal(joinNames(["A"]), "A");
  assert.equal(joinNames(["A", "B"]), "A and B");
  assert.equal(joinNames(["A", "B", "C"]), "A, B and C");
});

test("records add ties only when present", () => {
  assert.equal(recordText(4, 0, 0), "4–0");
  assert.equal(recordText(3, 1, 1), "3–1–1");
});

test("team color clamp hits 3:1 on both surfaces, lightness only", () => {
  // Royal blue reads on white but fails on a dark card (brief §5.5).
  assert.ok(contrastRatio("#2A3EAD", "#FFFFFF") > 8);
  assert.ok(contrastRatio("#2A3EAD", "#272727") < 2);
  const dark = clampToSurface("#2A3EAD", "#272727", 3);
  assert.ok(contrastRatio(dark, "#272727") >= 3);
  assert.equal(clampToSurface("#2A3EAD", "#FFFFFF", 3), "#2A3EAD");
  const light = clampToSurface("#FFD700", "#FFFFFF", 3);
  assert.ok(contrastRatio(light, "#FFFFFF") >= 3);
});

test("backend-clamped variants win over the client fallback", () => {
  const team = { color_variants: { primary: { raw: "#2A3EAD", light: { ui: "#2A3EAD" }, dark: { ui: "#6E80E6" } } } };
  assert.deepEqual(teamUiColors(team), { light: "#2A3EAD", dark: "#6E80E6" });
  const fallback = teamUiColors({ color_variants: { primary: { raw: "#2A3EAD" } } });
  assert.ok(contrastRatio(fallback.dark, "#272727") >= 3);
  assert.equal(teamUiColors({}), null);
});

test("ink picks the more readable of white and neutral-900", () => {
  assert.equal(inkFor("#137252"), "#FFFFFF");
  assert.equal(inkFor("#FBBF24"), "#272727");
});

test("escapeHtml neutralizes markup", () => {
  assert.equal(escapeHtml(`<b>"O'Bannon" & co</b>`), "&lt;b&gt;&quot;O&#39;Bannon&quot; &amp; co&lt;/b&gt;");
});
