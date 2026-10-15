import { test } from "node:test";
import assert from "node:assert/strict";
import { landingHtml, pickFeatured } from "../html/static/js/landing.js";

const card = (region, alive, volatility = 0.5) => ({ region, teams_alive: alive, volatility, num_clinched: 1, num_eliminated: 1 });
const team = (school, w, l, p, eliminated = false) => ({
  school, eliminated, clinched: false,
  record: { wins: w, losses: l, ties: 0, region_wins: w, region_losses: l, region_ties: 0 },
  odds: { p1: 0, p2: 0, p3: 0, p4: 0, p_playoffs: p, p1_weighted: 0, p2_weighted: 0, p3_weighted: 0, p4_weighted: 0, p_playoffs_weighted: p },
});

test("featured race: most undecided, then most volatile, then higher class", () => {
  const summary = { classes: [
    { class_: 3, regions: [card(1, 4, 0.9), card(2, 5, 0.1)] },
    { class_: 6, regions: [card(1, 5, 0.1), card(2, 2, 0.99)] },
  ] };
  assert.deepEqual([pickFeatured(summary).clazz, pickFeatured(summary).card.region], [6, 1]);
  summary.classes[0].regions[1].volatility = 0.3;
  assert.deepEqual([pickFeatured(summary).clazz, pickFeatured(summary).card.region], [3, 2]);
  assert.equal(pickFeatured({ classes: [{ class_: 1, regions: [card(1, 0)] }] }), null);
});

test("front page with a featured race", () => {
  const featured = {
    clazz: 5, card: card(3, 3),
    standings: { as_of_date: "2026-10-14", headline: "Three teams chase two spots <Friday>.", teams: [team("Brookhaven", 2, 1, 0.6), team("Natchez", 3, 0, 1), team("Vicksburg", 0, 3, 0, true)] },
  };
  const html = landingHtml(featured);
  assert.match(html, /Race to watch/);
  assert.match(html, /<a href="\/standings\/5a\/3">Region 3-5A<\/a>/);
  assert.match(html, /Three teams chase two spots &lt;Friday&gt;\./);
  assert.ok(html.indexOf("Natchez") < html.indexOf("Brookhaven"));
  assert.match(html, /1 clinched · 3 undecided · 1 out · Projected odds · Updated Oct 14/);
  assert.match(html, /See Region 3-5A/);
  assert.match(html, /<a class="landing-button" href="#team-search" data-focus-search>Find your team<\/a>/);
  for (let c = 1; c <= 7; c++) assert.ok(html.includes(`href="/standings/${c}a"`) && html.includes(`href="/brackets/${c}a"`));
});

test("front page without a race on", () => {
  const html = landingHtml(null);
  assert.ok(!html.includes("Race to watch"));
  assert.match(html, /See Class 1A/);
});
