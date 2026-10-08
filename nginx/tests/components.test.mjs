import { test } from "node:test";
import assert from "node:assert/strict";
import {
  oddsCell, provenance, teamStatus, statusBadge, teamMark, conditionChip, conditionGroups, classScrubber,
} from "../html/static/js/components.js";

const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();

test("odds cell carries its ramp slot and honest text", () => {
  assert.equal(oddsCell(0.794), '<span class="odds odds--4">79%</span>');
  assert.equal(oddsCell(0.001), '<span class="odds odds--1">&lt;1%</span>');
});

test("provenance: segments own their separators", () => {
  const fmt = () => "Oct 24";
  assert.equal(text(provenance({ label: "Week 9", date: "2026-10-24" }, fmt)), "Through Week 9 · Oct 24");
  assert.equal(text(provenance({ label: "Week 9" }, fmt)), "Through Week 9");
  assert.equal(text(provenance({ date: "2026-10-24" }, fmt)), "Updated Oct 24");
  assert.equal(text(provenance({ live: true, label: "Week 9" }, fmt)), "LIVE · Week 9");
  assert.equal(provenance({}, fmt), "");
  assert.ok(!text(provenance({ label: "Week 9" }, fmt)).includes("·"));
});

test("status: only the highest badge, eliminated first", () => {
  const odds = (p1, p2 = 0, p3 = 0, p4 = 0) => ({ p1, p2, p3, p4, p_playoffs: p1 + p2 + p3 + p4 });
  assert.deepEqual(teamStatus({ odds: odds(1.0000000000000027), clinched: true }), { kind: "clinched", label: "Clinched #1" });
  assert.deepEqual(teamStatus({ odds: odds(0, 0.5, 0.5), clinched: true }), { kind: "clinched", label: "Clinched" });
  assert.deepEqual(teamStatus({ odds: odds(0, 0.5, 0.5), clinched: true, coin_flip_needed: true }), { kind: "coinflip", label: "Coin flip" });
  assert.deepEqual(teamStatus({ odds: odds(0), eliminated: true, coin_flip_needed: true }), { kind: "eliminated", label: "Eliminated" });
  assert.equal(teamStatus({ odds: odds(0.5, 0.5) }), null);
  const badge = statusBadge({ odds: odds(0), eliminated: true });
  assert.match(badge, /<svg/); // icon + text, never color alone
  assert.equal(text(badge), "Eliminated");
});

test("team mark: helmet image, else a generic helmet in team colors, else a squircle", () => {
  assert.match(teamMark("Oxford", { helmet_url: "h.png" }), /mark--helmet[^>]*src="h.png"[^>]*alt=""/);
  const colors = { color_variants: { primary: { raw: "#B22234" }, secondary: [{ raw: "#ffc72c" }] } };
  const generic = teamMark("Oxford", colors);
  assert.match(generic, /mark--generic/);
  assert.match(generic, /fill="#B22234"/); // shell is the raw primary: artwork, never clamped
  assert.match(generic, /stroke="#FFC72C"/); // crown stripe is the first secondary
  assert.match(generic, /aria-hidden="true"/);
  assert.match(teamMark("Oxford", { color_variants: { primary: { raw: "#2A3EAD" } } }), /stroke="#FFFFFF"/);
  assert.match(teamMark("Oxford", { color_variants: { primary: { raw: "#FFFFFF" } } }), /mark--pale/);
  assert.doesNotMatch(generic, /mark--pale/);
  const squircle = teamMark("Wilkinson County", { logo_primary: "l.png" });
  assert.match(squircle, /mark--initials/); // logos aren't used at mark size
  assert.equal(text(squircle), "W");
});

test("provenance carries the odds mode by glyph and type, not color", () => {
  const projected = provenance({ label: "Week 9", date: "x", mode: "projected" }, () => "Oct 24");
  assert.equal(text(projected), "Through Week 9 · Oct 24 · Projected");
  assert.match(projected, /mode--projected"><svg/);
  const tossup = provenance({ label: "Week 9", mode: "tossup" }, () => "");
  assert.match(tossup, /mode--tossup"><svg/);
  assert.equal(text(tossup), "Through Week 9 · Toss-up");
  assert.doesNotMatch(provenance({ label: "Week 9", mode: "bogus" }, () => ""), /mode/);
});

test("chip: subject team named, margin range shown", () => {
  const chip = conditionChip({ type: "game_result", school: "Raleigh", opponent: "Magee", required_result: "win", min_margin: 8, max_margin: 11 }, {});
  assert.equal(text(chip), "R Raleigh beats Magee by 8–10");
  assert.match(chip, /chip__subject">Raleigh</);
  const flip = conditionChip({ type: "coin_flip", description: "Petal wins coin flip vs Stringer" }, {});
  assert.match(flip, /<svg/);
});

test("AND / OR grammar is explicit text, not position", () => {
  const c = (w, l) => ({ type: "game_result", school: w, opponent: l, min_margin: 1, max_margin: null });
  const html = conditionGroups([[c("A", "B"), c("C", "D")], [c("E", "F")]], {});
  assert.equal((html.match(/class="and"/g) || []).length, 1);
  assert.equal((html.match(/class="or"/g) || []).length, 1);
  assert.match(text(html), /A beats B AND .* C beats D OR .* E beats F/);
  assert.doesNotMatch(conditionGroups([[c("A", "B")]], {}), /class="(and|or)"/);
});

test("class scrubber is one tab stop with the selection checked", () => {
  const html = classScrubber([1, 2, 3], 2);
  assert.equal((html.match(/tabindex="0"/g) || []).length, 1);
  assert.match(html, /aria-checked="true" tabindex="0" data-class="2"/);
  assert.match(classScrubber([1, 2, 3], null), /tabindex="0" data-class="1"/);
  assert.match(html, /role="radiogroup"/);
});
