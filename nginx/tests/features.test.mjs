import { test } from "node:test";
import assert from "node:assert/strict";
import { isOn } from "../html/static/js/features.js";

test("a flag is on only when the server lists it for this viewer", () => {
  const config = { features: ["dark_map"] };
  assert.equal(isOn(config, "dark_map"), true);
  assert.equal(isOn(config, "new_bracket"), false);
});

test("a config without flags (an older API, or one that didn't load) has every flag off", () => {
  assert.equal(isOn({}, "dark_map"), false);
  assert.equal(isOn(null, "dark_map"), false);
  assert.equal(isOn({ features: "dark_map" }, "dark_map"), false);
});
