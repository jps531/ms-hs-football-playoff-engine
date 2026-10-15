import { test } from "node:test";
import assert from "node:assert/strict";
import { landingHtml, leaders } from "../html/static/js/landing.js";

const status = (school, w, l, t = 0) => ({ school, record: { region_wins: w, region_losses: l, region_ties: t } });
const card = (region, statuses, counts = [1, 3, 1]) => ({
  region, statuses, num_clinched: counts[0], teams_alive: counts[1], num_eliminated: counts[2],
});

test("leaders: everyone tied with the leader on region record", () => {
  assert.deepEqual(leaders(card(1, [status("Oxford", 1, 0), status("Germantown", 1, 0), status("Clinton", 0, 1)])),
    { names: "Oxford and Germantown", record: "1–0" });
  assert.deepEqual(leaders(card(1, [status("A", 3, 0), status("B", 2, 1)])), { names: "A", record: "3–0" });
  const four = ["A", "B", "C", "D"].map((s) => status(s, 1, 1));
  assert.equal(leaders(card(1, four)).names, "4 teams");
  assert.equal(leaders(card(1, [status("A", 0, 0), status("B", 0, 0)])), null);
  assert.equal(leaders(card(1, [])), null);
});

test("front page: every class in order, regions in order, counts and links", () => {
  const html = landingHtml({
    as_of_date: "2026-10-14",
    classes: [
      { class_: 7, regions: [card(2, [status("Oxford", 4, 0)]), card(1, [status("Tupelo", 2, 1)])] },
      { class_: 1, regions: [card(1, [status("A", 0, 0)], [0, 5, 0])] },
    ],
  }, 2026);
  assert.ok(html.indexOf("Class 1A") < html.indexOf("Class 7A"));
  assert.ok(html.indexOf('href="/standings/7a/1"') < html.indexOf('href="/standings/7a/2"'));
  assert.match(html, /2026 season · Updated Oct 14/);
  assert.match(html, /Oxford <span class="muted">4–0<\/span>/);
  assert.match(html, /No region games yet/);
  assert.match(html, /href="\/brackets\/7a">7A Bracket/);
  assert.match(html, /<th scope="col" class="col-num">Undecided<\/th>/);
});

test("front page escapes team names", () => {
  const html = landingHtml({ as_of_date: "2026-10-14", classes: [{ class_: 3, regions: [card(1, [status("<b>X</b>", 1, 0)])] }] }, 2026);
  assert.ok(!html.includes("<b>X</b>") && html.includes("&lt;b&gt;X&lt;/b&gt;"));
});
