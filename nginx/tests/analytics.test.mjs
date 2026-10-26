import { test } from "node:test";
import assert from "node:assert/strict";
import { campaignTags, withoutCampaignTags, urlWithoutClickIds, withoutClickIds } from "../html/static/js/analytics.js";

test("an arrival link's campaign tags are picked out, and taken off the rest of its query string", () => {
  const search = "?team=raleigh&utm_source=facebook&utm_medium=social&odds=tossup";
  assert.deepEqual(campaignTags(search), [["utm_source", "facebook"], ["utm_medium", "social"]]);
  assert.equal(withoutCampaignTags(search), "?team=raleigh&odds=tossup");
  assert.equal(withoutCampaignTags("?utm_source=facebook"), "");
  assert.deepEqual(campaignTags(""), []);
});

test("ad-click IDs never leave the browser, in their own fields or inside a URL", () => {
  assert.equal(
    urlWithoutClickIds("https://mshsfootball.com/standings/3a/6?utm_source=facebook&fbclid=IwAR1&gclid=x"),
    "https://mshsfootball.com/standings/3a/6?utm_source=facebook",
  );
  assert.equal(urlWithoutClickIds("$direct"), "$direct");
  assert.equal(urlWithoutClickIds(42), 42);
  const props = withoutClickIds({
    fbclid: "IwAR1", gclid: "x", utm_source: "facebook", $current_url: "https://mshsfootball.com/?fbclid=IwAR1", $browser: "Chrome",
  });
  assert.deepEqual(props, { utm_source: "facebook", $current_url: "https://mshsfootball.com/", $browser: "Chrome" });
  assert.equal(withoutClickIds(undefined), undefined);
});
