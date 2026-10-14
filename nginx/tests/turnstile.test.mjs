import { test } from "node:test";
import assert from "node:assert/strict";
import { turnstileToken, widgetOptions } from "../html/static/js/turnstile.js";

test("widget options: invisible unless needed, themed, tagged with the form", () => {
  assert.deepEqual(widgetOptions("0xKEY", { dark: true, action: "score" }), {
    sitekey: "0xKEY",
    action: "score",
    theme: "dark",
    size: "flexible",
    appearance: "interaction-only",
  });
  assert.equal(widgetOptions("0xKEY").theme, "light");
  assert.equal(widgetOptions("0xKEY").action, "feedback");
});

test("token: none needed while Turnstile is off", async () => {
  assert.deepEqual(await turnstileToken({ dataset: {} }), { token: null });
});

test("token: a widget that couldn't load says how to fix it", async () => {
  const { problem } = await turnstileToken({ dataset: { turnstile: "unavailable" } });
  assert.match(problem, /challenges\.cloudflare\.com/);
});
