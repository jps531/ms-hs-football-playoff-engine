import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// A stray or missing brace makes browsers drop every rule after it, silently.
test("app.css braces balance, outside comments and strings", () => {
  const css = readFileSync(new URL("../html/static/css/app.css", import.meta.url), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/"[^"]*"/g, '""');
  let depth = 0;
  for (const [i, ch] of [...css].entries()) {
    if (ch === "{") depth += 1;
    if (ch === "}") depth -= 1;
    assert.ok(depth >= 0, `unmatched "}" near character ${i}`);
  }
  assert.equal(depth, 0, "unclosed block");
});
