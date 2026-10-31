import { test } from "node:test";
import assert from "node:assert/strict";
import {
  oddsCell, provenance, teamStatuses, statusBadges, infoButton, teamMark, conditionChip, conditionGroups, classScrubber,
  gameCard, outcomeScenarioCard, breadcrumbs, whyTies, scenarioCard, tableMode, allOfConditions, conditionsThen, championBanner, venueName, finalNote,
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

test("statuses: every one that applies, the clinch first", () => {
  const odds = (p1, p2 = 0, p3 = 0, p4 = 0) => ({ p1, p2, p3, p4, p_playoffs: p1 + p2 + p3 + p4 });
  const done = { regionComplete: true };
  const labels = (e, opts = done) => teamStatuses(e, opts).map((st) => st.label);
  assert.deepEqual(labels({ odds: odds(1.0000000000000027), clinched: true }), ["Clinched #1"]);
  assert.deepEqual(labels({ odds: odds(0, 0.5, 0.5), clinched: true }), ["Clinched"]);
  assert.deepEqual(labels({ odds: odds(0, 0.5, 0.5), clinched: true, coin_flip_needed: true }), ["Clinched", "Coin flip"]);
  assert.deepEqual(labels({ odds: odds(0), eliminated: true, coin_flip_needed: true }), ["Eliminated", "Coin flip"]);
  assert.deepEqual(labels({ odds: odds(0.5, 0.5) }), []);
  const badges = statusBadges({ odds: odds(0, 1), clinched: true, coin_flip_needed: true }, done);
  assert.equal((badges.match(/<svg/g) || []).length, 2); // icon + text, never color alone
  assert.equal(text(badges), "Clinched #2 Coin flip");
});

test("coin flip shows only once region play is complete", () => {
  const entry = { odds: { p1: 0.5, p2: 0.5, p3: 0, p4: 0, p_playoffs: 1 }, clinched: true, coin_flip_needed: true };
  assert.deepEqual(teamStatuses(entry).map((st) => st.label), ["Clinched"]);
  assert.deepEqual(teamStatuses(entry, { regionComplete: false }).map((st) => st.label), ["Clinched"]);
  assert.equal(text(statusBadges(entry)), "Clinched");
});

test("info button discloses a note instead of relying on hover", () => {
  const html = infoButton("mode-help", "What Projected means");
  assert.match(html, /<button type="button"[^>]*aria-expanded="false" aria-controls="mode-help"/);
  assert.equal(text(html), "What Projected means");
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
  const flip = conditionChip({ type: "coin_flip", description: "Petal wins the coin flip against Stringer" }, {});
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

test("class row is a nav of links with the current class marked", () => {
  const html = classScrubber([1, 2, 3], 2, (c) => `/brackets/${c}a`);
  assert.match(html, /^<nav class="scrubber" aria-label="Classification">/);
  assert.equal((html.match(/<a /g) || []).length, 3);
  assert.match(html, /href="\/brackets\/2a" data-class="2" aria-current="page">2A</);
  assert.equal((html.match(/aria-current/g) || []).length, 1);
  assert.doesNotMatch(classScrubber([1, 2, 3], null), /aria-current/);
  assert.match(classScrubber([1], 1), /href="\/standings\/1a"/);
});

test("scenario card titles read as a condition ending in IF", async () => {
  const { scenarioCard } = await import("../html/static/js/components.js");
  const html = scenarioCard({ title: "Stringer clinches the region", groups: [[{ type: "game_result", school: "Stringer", opponent: "Lumberton" }]], teams: {} });
  assert.match(text(html), /^Stringer clinches the region IF/);
  assert.match(html, /region\u00a0<span class="scenario__if">IF</); // non-breaking: IF never wraps alone
});

test("game card: visitor on top with the joiner, winner bolded, a readable summary", () => {
  const html = gameCard({ away: "Taylorsville", home: "Stringer", joiner: "at", awayScore: 0, homeScore: 48, winner: "Stringer" }, {}, { focus: "Stringer" });
  assert.match(html, /class="game-card is-focus"/);
  assert.ok(text(html).startsWith("Taylorsville 0, Stringer 48"));
  assert.ok(html.indexOf("Taylorsville") < html.indexOf(">at<"));
  assert.match(html, /game-card__team is-winner"><span class="team">.*Stringer/);
  const upcoming = gameCard({ away: "A", home: "B", joiner: "vs" }, {});
  assert.ok(text(upcoming).startsWith("A vs B"));
  assert.doesNotMatch(upcoming, /game-card__score/);
});

test("game card: a completed game can be reported as a wrong score, with everything the form needs", () => {
  const game = { date: "2026-10-09", away: "Seminary", home: "Raleigh", joiner: "at", awayScore: 21, homeScore: 28, winner: "Raleigh" };
  const html = gameCard(game, {}, { report: true });
  assert.match(html, /data-score-report data-date="2026-10-09" data-away="Seminary" data-home="Raleigh" data-joiner="at" data-away-score="21" data-home-score="28"/);
  assert.match(html, /Wrong score\?<span class="visually-hidden"> Report a correction for Seminary 21, Raleigh 28/);
  assert.doesNotMatch(gameCard(game, {}), /data-score-report/);
  assert.doesNotMatch(gameCard({ away: "A", home: "B", joiner: "vs" }, {}, { report: true }), /data-score-report/);
});

test("game card: a game with no score yet can have its final score reported from its day on", () => {
  const game = { date: "2026-10-30", away: "Seminary", home: "Raleigh", joiner: "at" };
  const html = gameCard(game, {}, { report: true, today: "2026-10-30" });
  assert.match(html, /data-score-report data-date="2026-10-30" data-away="Seminary" data-home="Raleigh" data-joiner="at">Report score<span class="visually-hidden"> for Seminary at Raleigh/);
  assert.doesNotMatch(html, /data-away-score/);
  assert.doesNotMatch(gameCard(game, {}, { report: true, today: "2026-10-29" }), /data-score-report/); // not played yet
  assert.doesNotMatch(gameCard({ ...game, date: null }, {}, { report: true, today: "2026-10-30" }), /data-score-report/); // date to be announced
  assert.doesNotMatch(gameCard(game, {}, { today: "2026-10-30" }), /data-score-report/);
});

test("game card: a game with a date can be reported as on the wrong date, before or after it's played", () => {
  const upcoming = { date: "2026-11-06", away: "Seminary", home: "Raleigh", joiner: "at" };
  const html = gameCard(upcoming, {}, { report: true, today: "2026-10-30" });
  assert.match(html, /data-date-report data-date="2026-11-06" data-away="Seminary" data-home="Raleigh" data-joiner="at">Wrong date\?<span class="visually-hidden"> Report the right date for Seminary at Raleigh/);
  assert.doesNotMatch(html, /data-score-report/); // not played yet: only the date
  const played = gameCard({ ...upcoming, date: "2026-10-09", awayScore: 21, homeScore: 28, winner: "Raleigh" }, {}, { report: true });
  assert.ok(played.indexOf("Wrong date?") < played.indexOf("Wrong score?"));
  assert.match(played, /class="game-card__reports"/);
  assert.doesNotMatch(gameCard({ ...upcoming, date: null }, {}, { report: true }), /game-card__reports/);
  assert.doesNotMatch(gameCard(upcoming, {}), /data-date-report/);
});

test("scenario box lists the seeds, who's out, then IF and the conditions", () => {
  const html = outcomeScenarioCard({
    label: "Scenario 2A",
    seeds: [{ seed: 1, team: "A" }, { seed: 2, team: "B" }],
    out: ["C"],
    groups: [[{ type: "game_result", school: "A", opponent: "B", required_result: "win", min_margin: 1, max_margin: null }]],
  }, {}, { focus: "C" });
  // Initials marks repeat each name in the text.
  assert.match(text(html), /^Scenario 2A 1 A A 2 B B Out C IF A A beats B$/);
  assert.match(html, /<strong>C<\/strong>/);
});

test("a tie row lists its teams over its places with what decides it, never an order", () => {
  const html = outcomeScenarioCard({
    label: "Scenario 1",
    seeds: [{ seed: 1, team: "A" }, { seed: "2–4", teams: ["B", "C", "D"], note: "Order decided by a coin flip" }],
    out: [],
    groups: [],
  }, {}, { focus: "C" });
  assert.match(text(html), /^Scenario 1 1 A A 2–4 B B C C D D Order decided by a coin flip$/);
  assert.match(html, /class="outcome__tie is-focus"/);
});

test("in the playoffs the run replaces the clinch; teams that missed stay Eliminated", () => {
  const bracket = (r) => ({ second_round: r[0], quarterfinals: r[1], semifinals: r[2], finals: r[3], champion: r[4] });
  const lost = { clinched: true, eliminated: true, odds: { p1: 1, p_playoffs: 1 }, bracket_odds: bracket([0, 0, 0, 0, 0]) };
  assert.deepEqual(teamStatuses(lost, { clazz: 2 }).map((st) => [st.kind, st.label]), [["eliminated", "Lost in First Round"]]);
  const alive = { clinched: true, odds: { p2: 1, p_playoffs: 1 }, bracket_odds: bracket([1, 1, 1, 0.5, 0.2]) };
  assert.deepEqual(teamStatuses(alive, { clazz: 2 }).map((st) => st.label), ["Advanced to Semifinals"]);
  const champ = { clinched: true, odds: { p1: 1, p_playoffs: 1 }, bracket_odds: bracket([1, 1, 1, 1, 1]) };
  assert.deepEqual(teamStatuses(champ, { clazz: 2 }).map((st) => [st.kind, st.label]), [["champion", "State Champion"]]);
  const missed = { eliminated: true, odds: { p_playoffs: 0 }, bracket_odds: bracket([0, 0, 0, 0, 0]) };
  assert.deepEqual(teamStatuses(missed, { clazz: 2 }).map((st) => st.label), ["Eliminated"]);
  assert.match(statusBadges(champ, { clazz: 2 }), /badge--champion/);
});

test("breadcrumbs link every level but the page itself (static_pages.breadcrumb_nav writes the same)", () => {
  assert.equal(
    breadcrumbs([["Home", "/"], ["Class 3A", "/standings/3a"], ["Region 6-3A", null]]),
    '<nav class="crumbs" aria-label="Breadcrumb"><ol><li><a href="/">Home</a></li>'
      + '<li><a href="/standings/3a">Class 3A</a></li><li aria-current="page">Region 6-3A</li></ol></nav>',
  );
  assert.match(breadcrumbs([["Home", "/"], ["A & B", null]]), /A &amp; B/);
});

test("a complete scenario shows its finish's chance, with what it covers, only when it has one", () => {
  const card = { label: "Scenario 2", seeds: [{ seed: 1, team: "A" }], out: [], groups: [] };
  const withOdds = outcomeScenarioCard(card, {}, { p: 0.391, provenanceHtml: '<p class="provenance">Through Week 9</p>' });
  assert.match(withOdds, /<div class="scenario__head"><h4 class="scenario__title">Scenario 2<\/h4><span class="odds odds--2">39%<\/span><\/div><p class="provenance">/);
  const without = outcomeScenarioCard(card, {});
  assert.doesNotMatch(without, /odds--|provenance/);
});

test("shared conditions come once, then the alternatives inside a box headed AND ONE OF (static_pages writes the same)", () => {
  const win = (school, opponent) => ({ type: "game_result", school, opponent, required_result: "win", min_margin: 1, max_margin: null });
  const card = { label: "Scenario 3", seeds: [{ seed: 1, team: "A" }], out: [], common: [win("A", "B")], groups: [[win("C", "D")], [win("D", "C")]] };
  const html = outcomeScenarioCard(card, {});
  const box = html.indexOf('<div class="oneof" role="group" aria-label="And one of"><span class="oneof__label" aria-hidden="true">AND ONE OF</span>');
  assert.ok(box > html.indexOf(">A</span> beats B") && box < html.indexOf(">C</span> beats D"));
  assert.ok(html.indexOf('class="or"') > box);
  // Without shared conditions there's nothing to scope: no box, just the alternatives.
  assert.doesNotMatch(outcomeScenarioCard({ ...card, common: [] }, {}), /oneof/);
});

test("a card with ties has an Explanation button to its sheet; the sheet's ties are escaped", () => {
  const why = [{ title: "A <b> and B, tied for 1st and 2nd", when: "If C beats D", steps: ["one", "two & three"] }];
  const html = whyTies(why);
  assert.ok(html.includes("A &lt;b&gt; and B") && html.includes("If C beats D:") && html.includes("<li>two &amp; three</li>"));
  assert.ok(!whyTies([{ ...why[0], when: null }]).includes("why-tie__when"));
  const card = { label: "Scenario 1", seeds: [], out: [], groups: [], why };
  const withButton = outcomeScenarioCard(card, {}, { explainId: 3 });
  assert.match(withButton, /<button type="button" class="outcome__explain" data-explain-open="3" aria-haspopup="dialog">/);
  assert.equal(text(withButton.slice(withButton.indexOf("<button"))), "Explanation of Scenario 1");
  assert.match(withButton, /<svg class="outcome__explain-icon"[^>]*aria-hidden="true"/);
  assert.ok(!withButton.includes("why-tie")); // the steps are in the sheet, not the card
  assert.ok(!outcomeScenarioCard(card, {}).includes("outcome__explain")); // in the sheet itself: no button
  assert.ok(!outcomeScenarioCard({ ...card, why: [] }, {}, { explainId: 3 }).includes("outcome__explain")); // no ties
});

test("table mode: the odds mode over a table's odds columns, as static_pages.py's table_mode draws it", () => {
  assert.equal(text(tableMode("projected")), "Projected odds");
  assert.equal(text(tableMode("tossup")), "Toss-up odds");
  assert.ok(tableMode("tossup").includes('aria-hidden="true"')); // the caption's own words say it to screen readers
  assert.equal(tableMode(null), "");
});

test("scenario cards: the heading level is one below the heading they sit under", () => {
  const card = { title: "Raleigh clinches the region", groups: [], teams: {} };
  assert.ok(scenarioCard(card).includes('<h4 class="scenario__title">'));
  assert.ok(scenarioCard({ ...card, level: 3 }).includes('<h3 class="scenario__title">'));
  const outcome = { label: "Scenario 1", seeds: [], out: [], groups: [] };
  assert.ok(outcomeScenarioCard(outcome, {}).includes('<h4 class="scenario__title">Scenario 1</h4>'));
  assert.ok(outcomeScenarioCard(outcome, {}, { level: 3, p: 0.5 }).includes('<h3 class="scenario__title">Scenario 1</h3>'));
});

test("conditions that must all hold: shared ones first, then each set of alternatives in its own box", () => {
  const c = (w, l) => ({ type: "game_result", school: w, opponent: l, required_result: "win", min_margin: 1, max_margin: null });
  // One team's single way, the other's two: the way, then "AND ONE OF" the two.
  const both = text(allOfConditions({ common: [c("A", "B")], alternatives: [[[c("C", "D")], [c("E", "F")]]] }, {}));
  assert.match(both, /^A A beats B AND ONE OF C C beats D OR E E beats F$/); // each chip starts with its helmet's initial
  // Two sets of alternatives and nothing shared: the first box says ONE OF.
  const two = text(allOfConditions({ common: [], alternatives: [[[c("A", "B")], [c("C", "D")]], [[c("E", "F")], [c("G", "H")]]] }, {}));
  assert.match(two, /^ONE OF A A beats B OR C C beats D AND ONE OF E E beats F OR G G beats H$/);
  // A lone set of alternatives needs no box.
  assert.doesNotMatch(allOfConditions({ common: [], alternatives: [[[c("A", "B")], [c("C", "D")]]] }, {}), /oneof/);
});

test("a playoff game to win reads as one chip, naming the opponent when it's known", () => {
  const chip = (o) => text(conditionChip({ type: "playoff_win", school: "Center Hill", ...o }, {}));
  assert.match(chip({ round: "First Round", opponent: "Region 2 #2 Seed", byPosition: true }), /Center Hill wins its First Round game vs the Region 2 #2 Seed$/);
  assert.match(chip({ round: "Quarterfinals", opponent: "Neshoba Central", byPosition: false }), /Center Hill wins its Quarterfinal game vs Neshoba Central$/);
  assert.match(chip({ round: "Semifinals", opponent: null }), /Center Hill wins its Semifinal game$/);
});

test("conditions read in the order they're played: the regular season, then the playoff games", () => {
  const c = (w, l) => ({ type: "game_result", school: w, opponent: l, required_result: "win", min_margin: 1, max_margin: null });
  const win = { type: "playoff_win", school: "W", round: "First Round", opponent: "Region 1 #3 Seed", byPosition: true };
  // Several ways to a seed: the ONE OF box first, then AND the games (even with nothing shared).
  const two = text(conditionsThen({ common: [], alternatives: [[[c("A", "B")], [c("C", "D")]]] }, [win], {}));
  assert.match(two, /^ONE OF A A beats B OR C C beats D AND W W wins its First Round game vs the Region 1 #3 Seed$/);
  // Shared results, then two teams' alternatives, then the games.
  const both = text(conditionsThen({ common: [c("S", "T")], alternatives: [[[c("A", "B")], [c("C", "D")]], [[c("E", "F")], [c("G", "H")]]] }, [win], {}));
  assert.match(both, /^S S beats T AND ONE OF .* AND ONE OF .* G G beats H AND W W wins/);
  // One way: its results, then the games, in one line of ANDs.
  assert.match(text(conditionsThen({ common: [c("A", "B")], alternatives: [] }, [win], {})), /^A A beats B AND W W wins its First Round game/);
  // Nothing before the games: just the games. No games left: no AND after the box.
  assert.match(text(conditionsThen({ common: [], alternatives: [] }, [win], {})), /^W W wins its First Round game/);
  assert.doesNotMatch(conditionsThen({ common: [], alternatives: [[[c("A", "B")], [c("C", "D")]]] }, [], {}), /class="and"/);
});

test("championBanner: the trophy, the champion and the championship game", () => {
  const html = championBanner(2025, 3, { winner: "Raleigh", loser: "Mize", winnerScore: 12, loserScore: 6 }, {});
  assert.match(html, /<section class="champion" aria-label="State champion"><svg class="trophy" viewBox="0 0 40 56" width="40" height="56" aria-hidden="true">/);
  assert.match(html, /<p class="champion__label">2025 Class 3A State Champion<\/p>/);
  assert.match(html, /Beat Mize 12–6 in the Championship Game/);
  assert.doesNotMatch(championBanner(2025, 3, { winner: "Raleigh", loser: "Mize" }, {}), /–/);
});


test("venueName, finalNote and the banner's venue: where the championship game is played", () => {
  const venue = { name: "Davis Wade Stadium", city: "Starkville, MS" };
  assert.equal(venueName(venue), "Davis Wade Stadium • Starkville");
  assert.equal(venueName({ name: "M.M. Roberts Stadium", city: null }), "M.M. Roberts Stadium");
  assert.equal(venueName(null), null);
  const note = finalNote(venue, { team: "Winona", p: 0.22 });
  assert.equal(text(note), "Davis Wade Stadium • Starkville Projected champion: Winona · 22%");
  assert.equal(finalNote(null, null), "");
  assert.equal(text(finalNote(venue, null)), "Davis Wade Stadium • Starkville");
  const banner = championBanner(2025, 3, { winner: "Raleigh", loser: "Mize", winnerScore: 12, loserScore: 6 }, {}, venue);
  assert.match(banner, /Beat Mize 12–6 in the Championship Game at Davis Wade Stadium in Starkville<\/p>/);
});
