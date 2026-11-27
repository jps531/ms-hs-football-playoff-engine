import { test } from "node:test";
import assert from "node:assert/strict";
import {
  LOOK_FIELDS, SCHOOL_FIELDS, effectiveLook, imageUrl, invalid, logoRow, lookRow, overrideChanges, schoolHtml, spanLabel, withOverride,
} from "../html/static/js/moderate-schools.js";

const HAWKS = {
  id: 7, school: "Shaw", source: "file", note: null, color_variants: null,
  base: { first_season: null, last_season: 2019, mascot: "Hawks", primary_color: "Green", secondary_color: "Gold",
    primary_color_hex: "#00843D", secondary_color_hex: "#FFC72C", approximate: true },
  overrides: {},
};
const SHAW = {
  school: "Shaw", image_base: "https://img.example/x", overrides: { mascot: "Warriors" },
  base: { display_name: "Shaw", city: "Shaw", zip: null, latitude: 33.6, longitude: -90.77, mascot: "Warrior", primary_color: "Maroon",
    secondary_color: "Gold", primary_color_hex: "#800000", secondary_color_hex: "#FFD700", logo_primary: "", logo_secondary: "", logo_tertiary: "" },
};

test("a span of seasons reads as the site says it", () => {
  assert.equal(spanLabel(null, 2019), "Through 2019");
  assert.equal(spanLabel(2020, null), "2020 on");
  assert.equal(spanLabel(2015, 2019), "2015–2019");
  assert.equal(spanLabel(2017, 2017), "2017");
  assert.equal(spanLabel(null, null), "Every season");
});

test("an override wins, and a blank season override means open", () => {
  assert.deepEqual(withOverride(SHAW.base, SHAW.overrides, "mascot"), { value: "Warriors", stored: "Warrior", overridden: true });
  const look = effectiveLook({ ...HAWKS, overrides: { first_season: "2015", last_season: "", approximate: "false" } });
  assert.equal(look.first_season, 2015);
  assert.equal(look.last_season, null);
  assert.equal(look.approximate, false);
});

test("a form's changes become overrides set, or cleared back to the stored value", () => {
  // Mascot typed back to its stored value: the override is cleared. A new primary color: set.
  const changes = overrideChanges(SCHOOL_FIELDS, SHAW.base, SHAW.overrides, { mascot: "Warrior", primary_color: "Crimson", secondary_color: "Gold" });
  assert.deepEqual(changes, [{ field: "mascot", clear: true }, { field: "primary_color", value: "Crimson" }]);
  // A look's season emptied (open) is an override of "" when the file has a year.
  assert.deepEqual(overrideChanges(LOOK_FIELDS, HAWKS.base, {}, { last_season: "" }), [{ field: "last_season", value: "" }]);
});

test("each form value is checked before it's sent", () => {
  assert.equal(invalid("season", ""), "");
  assert.equal(invalid("season", "2019"), "");
  assert.notEqual(invalid("season", "19"), "");
  assert.notEqual(invalid("hex", "green"), "");
  assert.equal(invalid("hexes", "#FFD700, #000000"), "");
  assert.notEqual(invalid("hexes", "#FFD700, black"), "");
  assert.notEqual(invalid("number", "north"), "");
});

test("a past look shows its seasons, mascot, colors and where it's from; its form keeps the file's values", () => {
  const row = lookRow(HAWKS, null);
  assert.match(row, /Through 2019<\/span> · Hawks/);
  assert.match(row, /approximate colors/);
  assert.match(row, /from the file/);
  const form = lookRow({ ...HAWKS, overrides: { primary_color: "Kelly green" } }, "look-7");
  assert.match(form, /name="primary_color" type="text" value="Kelly green"/);
  assert.match(form, /From the file: Green/);
  assert.match(form, /Reset to the file/);
  assert.doesNotMatch(form, /data-delete-look/); // a file look is removed from the file, not here
  assert.match(lookRow({ ...HAWKS, source: "moderator" }, "look-7"), /data-delete-look="7"/);
});

test("a logo's image is served from the image base; a full URL passes through", () => {
  assert.equal(imageUrl("https://img.example/x", "logos/shaw.png"), "https://img.example/x/logos/shaw.png");
  assert.equal(imageUrl("https://img.example/x", "https://other/y.png"), "https://other/y.png");
  const row = logoRow({ id: 3, logo_type: "primary", image_url: "logos/shaw.png", year_start: 2020, year_end: null, is_primary: true, has_keyline: false, notes: null }, "https://img.example/x", null);
  assert.match(row, /Primary<\/span> · 2020 on/);
  assert.match(row, /src="https:\/\/img.example\/x\/logos\/shaw.png"/);
});

test("the whole school: its look now (an override marked), past looks, logos, helmets and each season", () => {
  const team = (season, mascot, p, s) => ({ school: "Shaw", season, mascot, city: "Shaw", class_: 1, region: 6, secondary_color_hex: s,
    color_variants: { primary: { raw: p, light: { ui: p, text: p }, dark: { ui: p, text: p } }, secondary: [] } });
  const html = schoolHtml({ school: SHAW, looks: [HAWKS], logos: [], helmets: [],
    seasons: [{ season: 2019, team: team(2019, "Hawks", "#00843D", "#FFC72C") }, { season: 2025, team: team(2025, "Warriors", "#800000", "#FFD700") }] }, null);
  assert.match(html, /Region 6-1A in 2025/);
  assert.match(html, /Warriors <span class="ms-tag ms-tag--override">override<\/span>/);
  assert.match(html, /Logos <button type="button" class="mod-button" data-edit="new-logo">/);
  assert.match(html, /None yet: a plain helmet in its colors/);
  assert.match(html, /2019<\/span>.*2025<\/span>/s);
});

test("each season's place, and its form: an independent's class and region come from the region file", async () => {
  const { seasonPlace, seasonsSection } = await import("../html/static/js/moderate-schools.js");
  assert.equal(seasonPlace({ class: 1, region: 6 }), "Region 6-1A");
  assert.equal(seasonPlace({ class: 1, region: null }), "1A Independent");
  const rows = [{ season: 2025, class: 1, region: 6, is_active: true }, { season: 2017, class: 1, region: null, is_active: false }];
  const html = seasonsSection(rows, null);
  assert.match(html, /2025<\/span><span>Region 6-1A<\/span>/);
  assert.match(html, /1A Independent <span class="ms-tag">not playing<\/span>/);
  assert.match(seasonsSection(rows, "season-2025"), /<select name="class">.*<option value="1" selected>1A/s);
  assert.match(seasonsSection(rows, "season-2017"), /an independent’s class and region come from the region file/);
  assert.doesNotMatch(seasonsSection(rows, "season-2017"), /name="region"/);
});
