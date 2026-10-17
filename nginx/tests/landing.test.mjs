import { test } from "node:test";
import assert from "node:assert/strict";
import { LANDING_FALLBACK, isFrontPage } from "../html/static/js/landing.js";

test("only the pipeline's page counts as the front page", () => {
  assert.ok(isFrontPage('<div class="page landing"><div class="landing-intro">…</div></div>\n'));
  assert.ok(!isFrontPage("<html><body>404 Not Found</body></html>"));
  assert.ok(!isFrontPage(null));
});

test("the fallback still gets readers to every class and bracket", () => {
  for (let c = 1; c <= 7; c++) {
    assert.ok(LANDING_FALLBACK.includes(`href="/standings/${c}a"`));
    assert.ok(LANDING_FALLBACK.includes(`href="/brackets/${c}a"`));
  }
  assert.match(LANDING_FALLBACK, /Mississippi High School Football/);
});

test("the fallback front page has every class's standings and bracket", async () => {
  const { classGrid, LANDING_FALLBACK } = await import("../html/static/js/landing.js");
  const grid = classGrid();
  assert.equal((grid.match(/class="landing-classes__item"/g) ?? []).length, 14);
  assert.ok(grid.includes('href="/brackets/7a">7A<span class="visually-hidden"> brackets</span>'));
  assert.ok(LANDING_FALLBACK.includes(grid));
});
